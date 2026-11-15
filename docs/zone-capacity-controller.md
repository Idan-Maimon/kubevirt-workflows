# Zone Capacity Controller — specification

Version 0.1. Normative. "MUST", "MUST NOT" and "SHOULD" carry their usual meaning.

---

## 1 :: Scope

### 1.1 In scope

| # | Responsibility |
|---|---|
| R1 | Choose the KV cluster for a new warm-pool VM and create it |
| R2 | Delete a warm-pool VM |
| R3 | Report zone capacity |
| R4 | Detect that the zone has insufficient spare clusters and request another |

### 1.2 Out of scope, with owner

| Not this controller | Owner |
|---|---|
| Growing a KV cluster's node count | `cluster-autoscaler`, native, driven by Pending pods |
| Keeping bare-metal Agents available | Inventory controller, deployed on the Seed |
| Creating the KV cluster objects | Temporal workflow `create-kv-cluster-<zone>` |
| Naming VMs | Caller |
| Choosing a hypervisor within a cluster | KubeVirt scheduler |
| Moving or migrating a VM | Nothing. Workers are replaced, not migrated |
| Maintaining the placeholder Deployment | Platform GitOps |

---

## 2 :: Deployment

| Property | Value |
|---|---|
| Instances | Exactly one per Seed cluster, which is one per zone |
| Leader election | Required. Lease in the controller's own namespace |
| On loss of lease | Exit immediately. In-flight requests MUST fail rather than complete |
| Zone identity | From configuration, immutable at runtime |

---

## 3 :: Configuration

ConfigMap, mounted file, re-read on change. Invalid configuration MUST leave the last good
configuration in effect and set `zcc_config_valid` to 0.

| Key | Type | Default | Constraint |
|---|---|---|---|
| `zone` | string | — | Required, non-empty |
| `reconcileInterval` | duration | `60s` | > 0 |
| `placementTimeout` | duration | `30s` | > 0 |
| `clusterReadTimeout` | duration | `5s` | > 0, < `placementTimeout` |
| `spareClustersTarget` | int | `1` | >= 1 |
| `infraEnvClusterCap` | int | `0` | >= 0. `0` disables the cap |
| `placeholderSelector` | label selector | `app.kubernetes.io/component=migration-reserve` | Valid selector |
| `sizes` | map[string]int | `{small:16, medium:32, large:64}` | Values > 0 |
| `poolNamespace` | string | `vm-pool` | Valid namespace name |

---

## 4 :: Inputs

Read from the Seed:

| Resource | Fields used |
|---|---|
| `hypershift.openshift.io/v1beta1 HostedCluster` | `metadata.name`, `status.kubeconfig`, `status.conditions` |
| `hypershift.openshift.io/v1beta1 NodePool` | `spec.clusterName`, `spec.autoScaling.max`, `status.replicas`, `status.conditions[type=AllMachinesReady]` |
| `v1 Secret` | The kubeconfig referenced by `HostedCluster.status.kubeconfig` |

Read from each KV cluster:

| Resource | Fields used |
|---|---|
| `v1 Node` | `status.allocatable.cpu`, `status.conditions[type=Ready]`, `spec.unschedulable`, labels identifying server type and variant |
| `v1 Pod` | `spec.nodeName`, `spec.containers[].resources.requests.cpu`, `status.phase`, labels |
| `kubevirt.io/v1 VirtualMachine` | `metadata.name`, `metadata.labels` |

---

## 5 :: Capacity model

Definitions, evaluated per pass and per request. All CPU quantities in whole cores.

```
eligible(H)        H.Ready == True AND H.spec.unschedulable == false
allocatable(H)     H.status.allocatable.cpu
used(H)            sum of cpu requests of every Pod with spec.nodeName == H
                   and status.phase not in {Succeeded, Failed}
free(H)            allocatable(H) - used(H)
reserve(H)         sum of cpu requests of Pods on H matching placeholderSelector
nodeCount(C)       count of eligible hypervisors in C
atCap(C)           nodeCount(C) >= NodePool.spec.autoScaling.max for C
usable(H, C)       free(H) + (atCap(C) ? 0 : reserve(H))
fits(C, n)         sum over eligible H in C of floor(usable(H, C) / n)
pendingLauncher(C) count of virt-launcher Pods in C with status.phase == Pending
```

**Rule 5.1.** `used(H)` MUST include Pending Pods. A Pending Pod has no `spec.nodeName`, so
it contributes to no hypervisor; see rule 6.2.4.

**Rule 5.2.** `usable` MUST treat the placeholder reserve as available below the node cap
and unavailable at it. Below the cap, admitting into the reserve is what preempts a
placeholder, which is what makes the autoscaler grow the cluster and refill the reserve. At
the cap nothing can refill it, so admitting would trade migration headroom permanently.

**Rule 5.3.** A single free-core total MUST NOT be published for a cluster or a zone. Only
`fits(C, n)` is a truthful capacity figure.

---

## 6 :: API

Served over HTTPS. All requests and responses `application/json`. Unknown request fields
MUST be rejected.

### 6.1 `POST /v1/vms`

Request:

```json
{
  "vm_name":     "ocp-conf203-zone-a-large-0042",
  "infra_env":   "conf203-zone-a-large",
  "server_type": "conf203",
  "variant":     null,
  "cores":       64,
  "spec":        { }
}
```

`vm_name` is the idempotency key. `spec` is the VirtualMachine manifest body.

| Status | Body | Meaning |
|---|---|---|
| `201` | `{kv_cluster, namespace, vm_name}` | Created |
| `200` | `{kv_cluster, namespace, vm_name}` | A VM of this name already exists in the zone. Nothing created |
| `409` | `{error: "NoCapacity", detail}` | No candidate cluster. See 8.1 |
| `422` | `{error, detail}` | Malformed, unknown field, or `cores` not in `sizes` |
| `503` | `{error, detail}` | Not the leader, or no KV cluster could be read |

**Rule 6.1.1.** `503` and `409` MUST NOT be conflated. An unreadable zone is not a full
zone.

### 6.2 Placement algorithm

**6.2.1 Serialization.** All `POST /v1/vms` and `DELETE /v1/vms/{name}` MUST be processed by
a single worker, one at a time, in arrival order. Concurrency is 1. A request waiting longer
than `placementTimeout` MUST return `503`.

**6.2.2 Unit of work.** The decision and the create MUST happen inside one serialized unit.
Returning a decision for a caller to act on later is prohibited.

**6.2.3 Freshness.** Cluster state MUST be read live at request time. A cached or periodic
snapshot MUST NOT be used. The VM object exists in the cluster API within a second of
creation, so a live read already accounts for the previous placement and no reservation or
in-flight accounting is required.

**6.2.4 Candidate filter.** A KV cluster `C` is a candidate when all hold:

| # | Predicate |
|---|---|
| F1 | `C` is in the controller's zone |
| F2 | `C` has at least one eligible hypervisor whose labels match `server_type` and `variant` |
| F3 | `fits(C, cores) >= 1` |
| F4 | `pendingLauncher(C) == 0` |
| F5 | `infraEnvClusterCap == 0` OR count of VMs in `C` labelled with this `infra_env` < `infraEnvClusterCap` |
| F6 | `C` was read successfully this request |

F4 exists because a Pending virt-launcher has not consumed a specific hypervisor yet, so a
per-host check would report that a second VM fits when the first has not landed.

**6.2.5 Ordering.** Candidates MUST be sorted by `sum over eligible H of usable(H, C)`
descending, ties broken by cluster name ascending.

**6.2.6 Create.** Write the VirtualMachine to the first candidate, into `poolNamespace`,
using create-if-absent semantics. An already-exists response MUST be treated as success and
returned as `200`.

**6.2.7 No candidate.** Return `409 NoCapacity`.

### 6.3 `DELETE /v1/vms/{vm_name}`

| Status | Meaning |
|---|---|
| `204` | Deleted, or already absent |
| `503` | Not leader, or the owning cluster could not be read |

### 6.4 `GET /v1/capacity`

```json
{
  "zone": "zone-a",
  "spare_clusters": 2,
  "clusters": [
    { "name": "kv-a-01", "server_type": "conf203", "nodes": 34, "node_cap": 40,
      "at_cap": false, "fits": { "small": 61, "medium": 24, "large": 9 } }
  ]
}
```

### 6.5 Operational endpoints

`GET /healthz`, `GET /readyz`, `GET /metrics`.

---

## 7 :: Reconcile loop

Runs every `reconcileInterval` on the leader only. Does not block the API worker.

```
spare = count of clusters C where NOT atCap(C) AND fits(C, max(sizes)) >= 1

if spare < spareClustersTarget:
    start Temporal workflow create-kv-cluster-<zone>-<n>
```

**Rule 7.1.** `n` is the lowest integer for which no KV cluster of that name exists. Temporal
workflow-id uniqueness is the only guard against starting two builds; the controller MUST
NOT keep its own in-flight state.

**Rule 7.2.** The controller MUST NOT create HostedCluster, NodePool or InfraEnv objects. A
KV cluster is cluster-level state and is committed to Git by the workflow (AD5, AD13).

**Rule 7.3.** A cluster that could not be read MUST NOT be counted as spare, and MUST NOT by
itself trigger a build. If no cluster in the zone could be read, the loop MUST take no
action.

---

## 8 :: Failure behaviour

**8.1** `NoCapacity` MUST be surfaced to the caller as the capacity failure class already
recognised by the install workflow, alongside `ServerNotAvailableError` and
`ServerReservedError`, so the Inventory Controller drops that InfraEnv to probe mode rather
than ordering at full rate.

**8.2** A cluster that cannot be read is excluded from candidates for that request only. It
is not marked unhealthy and no state is retained.

**8.3** The controller holds no durable state. Every figure is derived per pass. Restart
costs one pass.

---

## 9 :: Observability

### 9.1 Metrics

| Name | Type | Labels |
|---|---|---|
| `zcc_cluster_fits` | gauge | `cluster`, `server_type`, `size` |
| `zcc_cluster_nodes` | gauge | `cluster` |
| `zcc_cluster_node_cap` | gauge | `cluster` |
| `zcc_cluster_at_cap` | gauge | `cluster` |
| `zcc_cluster_reserve_cores` | gauge | `cluster` |
| `zcc_zone_spare_clusters` | gauge | — |
| `zcc_pending_virt_launcher` | gauge | `cluster` |
| `zcc_agent_stall` | gauge | `cluster` |
| `zcc_placements_total` | counter | `result` ∈ {`created`,`idempotent`,`no_capacity`,`error`} |
| `zcc_placement_duration_seconds` | histogram | — |
| `zcc_scale_out_requests_total` | counter | `result` |
| `zcc_cluster_read_errors_total` | counter | `cluster` |
| `zcc_config_valid` | gauge | — |

`zcc_agent_stall` is 1 when that cluster's NodePool reports
`AllMachinesReady=False`. This is the only signal that the autoscaler asked for a node and
no Agent was free; no Kubernetes Event is emitted for that condition.

### 9.2 Alerts

| Alert | Expression | For | Severity |
|---|---|---|---|
| `ZccNoSpareClusters` | `zcc_zone_spare_clusters == 0` | 15m | critical |
| `ZccAgentStall` | `zcc_agent_stall == 1` | 10m | warning |
| `ZccClusterUnreadable` | `increase(zcc_cluster_read_errors_total[10m]) > 0` | 10m | warning |
| `ZccNoCapacity` | `increase(zcc_placements_total{result="no_capacity"}[15m]) > 0` | 5m | warning |
| `ZccConfigInvalid` | `zcc_config_valid == 0` | 1m | warning |
| `ZccControllerDown` | `absent(zcc_config_valid)` | 10m | critical |

---

## 10 :: RBAC

On the Seed:

| API group | Resources | Verbs |
|---|---|---|
| `hypershift.openshift.io` | `hostedclusters`, `nodepools` | get, list, watch |
| `""` | `secrets` | get (hosted control plane namespaces only) |
| `coordination.k8s.io` | `leases` | get, list, watch, create, update, patch, delete |

On each KV cluster, via a dedicated ServiceAccount, not the admin kubeconfig:

| API group | Resources | Verbs |
|---|---|---|
| `""` | `nodes` | get, list, watch |
| `""` | `pods` | get, list, watch |
| `kubevirt.io` | `virtualmachines` | get, list, watch, create, delete |
| `cdi.kubevirt.io` | `datavolumes` | get, list, watch, create, delete |

**Rule 10.1.** The hosted control plane kubeconfig is an admin credential for a whole KV
cluster. It MUST be used only to bootstrap the ServiceAccount above, never for steady-state
operation.

---

## 11 :: Open items

| # | Item |
|---|---|
| O1 | `infraEnvClusterCap` default. `0` ships the cap disabled |
| O2 | Node labels identifying server type and variant are not yet defined |
| O3 | `poolNamespace` convention, pending the Section 9 naming decision |
| O4 | Memory as a second capacity dimension, if it is not proportional to cores |
| O5 | Placeholder shape must track the largest offered size. Nothing enforces this |
| O6 | Orphaned VMs, created but never registering an Agent, belong to Server Scanner |
