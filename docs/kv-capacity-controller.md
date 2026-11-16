# KV Capacity Controller — specification

Version 0.2. Normative. "MUST", "MUST NOT" and "SHOULD" carry their usual meaning.
Decisions: AD27, AD28, AD30, AD31 in [architecture.md](architecture.md).

---

## 1 :: Scope

### 1.1 In scope

| # | Responsibility |
|---|---|
| R1 | Grow the zone's active KV cluster so its free CPU stays at the policy's target |
| R2 | Keep the zone's standby KV clusters built, starting a new one when one is missing |
| R3 | Report zone capacity |

### 1.2 Out of scope, with owner

| Not this controller | Owner |
|---|---|
| Choosing the KV cluster for a VM, and creating it | `create-vm` workflow ([vm-placement.md](vm-placement.md)) |
| Keeping bare-metal Agents ready for a raised NodePool | herzi on the Seed ([inventory-controller.md](inventory-controller.md)) |
| Writing a NodePool total | `update-nodepool` workflow (Git, AD22) |
| Creating a KV cluster | `provision-cluster` workflow (Git, AD22) |
| Choosing a hypervisor within a cluster, packing VMs onto nodes | KubeVirt scheduler with `HighNodeUtilization`, descheduler `CompactAndScale` (AD30) |
| Shrinking or deleting a KV cluster | Nothing. Clusters only grow (AD26, AD28) |
| The capacity policy values | Platform repo, edited through Wingman (AD31) |

---

## 2 :: Deployment

| Property | Value |
|---|---|
| Instances | Exactly one per Seed cluster, which is one per zone |
| Leader election | Required. Lease in the controller's own namespace |
| On loss of lease | Exit immediately |
| Zone identity | From configuration, immutable at runtime |
| State | None. Every figure is derived per pass; a restart costs one pass |
| Dry run | Supported. Logs the orders it would send instead of sending them |

---

## 3 :: Configuration

Two sources, both mounted files, re-read on change. Invalid configuration MUST leave the
last good configuration in effect and set `kvcc_config_valid` to 0.

**The capacity policy (AD31).** A ConfigMap rendered by ArgoCD from the platform repo's
policy file. `create-vm` reads the same file; the controller MUST NOT carry its own copy of
these values.

| Key | Type | Value | Meaning |
|---|---|---|---|
| `maxNodes` | int | 40 | Hard size of a KV cluster, organisation-wide |
| `freeCpuPercent` | int | 15 | Free CPU kept above used CPU; the live-migration reserve |
| `standbyWorkers` | int | 1 to 5 | Bare-metal workers a standby cluster is built with |
| `standbyClusters` | int | 1 | Standby clusters kept per zone |

**The controller's own settings.**

| Key | Type | Default | Constraint |
|---|---|---|---|
| `zone` | string | — | Required, non-empty |
| `site` | string | — | Required, non-empty |
| `reconcileInterval` | duration | `60s` | > 0 |
| `clusterReadTimeout` | duration | `10s` | > 0 |
| `dryRun` | bool | `true` | Set false to send orders |

---

## 4 :: Inputs

Read from the Seed:

| Resource | Fields used |
|---|---|
| `hypershift.openshift.io/v1beta1 HostedCluster` | `metadata.name`, `metadata.creationTimestamp`, `status.conditions` |
| `hypershift.openshift.io/v1beta1 NodePool` | `spec.clusterName`, `spec.replicas`, `status.replicas`, `status.conditions` |

Read from each KV cluster's `kv-capacity` agent, `GET /v1/capacity`: the **same report
`create-vm` ranks on**, so placement and growth count used CPU the same way.

| Field | Used for |
|---|---|
| Schedulable nodes with allocatable CPU | `nodeCpu`, the cluster's capacity |
| Requests of Pending and Running pods | `used` |
| Halted VMs' reservations | `used`. kubevirt-redfish will start them |
| VMs present | Whether the cluster holds any VM |

---

## 5 :: Model

Clusters of the zone are ordered by creation, oldest first. Evaluated per pass.

```
replicas(C)      NodePool.spec.replicas of KV cluster C
used(C)          CPU requested on C: active pods + Halted VM reservations
nodeCpu(C)       allocatable CPU of one schedulable node of C
holdsVms(C)      C has at least one VM

active           the oldest C with replicas(C) < maxNodes
standby          every C after active where not holdsVms(C)

target(C)        ceil( used(C) × (1 + freeCpuPercent/100) / nodeCpu(C) )
                 bounded to [standbyWorkers, maxNodes]
```

**Rule 5.1.** Active and standby MUST be derived from observed state on every pass and
never stored. Promotion needs no action: when the active cluster reaches `maxNodes`, the
oldest cluster below it becomes active, and `create-vm` overflows into it once the old one
reaches its buffer.

**Rule 5.2.** `used` MUST include Halted VMs, as `create-vm`'s placement does. Otherwise
the controller sees room that placement has already promised.

**Rule 5.3.** Free CPU is meaningful as whole empty nodes only because clusters bin-pack
(AD30). The controller SHOULD alert when a cluster's free CPU is at target but it has no
empty node (`kvcc_cluster_empty_nodes == 0`), because the reserve then cannot take a drain.

---

## 6 :: Reconcile loop

Runs every `reconcileInterval` on the leader only.

```
1. grow     if target(active) > replicas(active):
                update-nodepool  cluster=active  total=target(active)
2. standby  if count(standby) < standbyClusters:
                provision-cluster  name=next KV cluster name  replicas=standbyWorkers
```

**Rule 6.1.** Totals are absolute, never deltas. A repeated order for the same total is a
no-op.

**Rule 6.2.** Only the active cluster is ever grown. A cluster at `maxNodes` is never grown,
and a standby is not grown until it becomes active.

**Rule 6.3.** Deduplication is the workflow id: `update-nodepool-<cluster>-<node-type>` and
`provision-cluster-<cluster>`. The controller MUST NOT keep its own record of what is in
flight. A `409` for a run already going is success.

**Rule 6.4.** The next cluster's name is the lowest unused `<env>-<site>-<zone>-kv<nn>`
(§9 of the architecture).

**Rule 6.5.** A cluster that could not be read MUST NOT be counted as standby, MUST NOT be
treated as active, and MUST NOT by itself trigger a new cluster. If no cluster in the zone
could be read, the loop takes no action.

---

## 7 :: Failure behaviour

**7.1** A rejected or failed order leaves the gap open, and the next pass sees it. The
evaluation cycle is the retry.

**7.2** `create-vm` returning `NoKvClusterFitsError` means this controller has fallen behind
(AD29). It is an alert, not a condition the controller acts on separately.

**7.3** A cluster that cannot be read is excluded for that pass only. Nothing is retained.

---

## 8 :: Observability

### 8.1 Metrics

| Name | Type | Labels |
|---|---|---|
| `kvcc_cluster_replicas` | gauge | `cluster` |
| `kvcc_cluster_target_nodes` | gauge | `cluster` |
| `kvcc_cluster_free_cpu_percent` | gauge | `cluster` |
| `kvcc_cluster_empty_nodes` | gauge | `cluster` |
| `kvcc_cluster_role` | gauge | `cluster`, `role` ∈ {`active`,`standby`,`full`} |
| `kvcc_zone_standby_clusters` | gauge | — |
| `kvcc_orders_total` | counter | `kind` ∈ {`grow`,`standby`}, `result` |
| `kvcc_cluster_read_errors_total` | counter | `cluster` |
| `kvcc_config_valid` | gauge | — |

### 8.2 Alerts

| Alert | Expression | For | Severity |
|---|---|---|---|
| `KvccNoStandby` | `kvcc_zone_standby_clusters < 1` | 30m | critical |
| `KvccBelowTarget` | `kvcc_cluster_free_cpu_percent{role="active"} < 15` | 30m | warning |
| `KvccNoEmptyNode` | `kvcc_cluster_empty_nodes == 0 and kvcc_cluster_free_cpu_percent >= 15` | 1h | warning |
| `KvccClusterUnreadable` | `increase(kvcc_cluster_read_errors_total[10m]) > 0` | 10m | warning |
| `KvccConfigInvalid` | `kvcc_config_valid == 0` | 1m | warning |
| `KvccControllerDown` | `absent(kvcc_config_valid)` | 10m | critical |

---

## 9 :: Access

| Where | What | Verbs |
|---|---|---|
| Seed | `hostedclusters`, `nodepools` | get, list, watch |
| Seed | `leases` in its namespace | get, create, update |
| Each KV cluster | `kv-capacity` agent, with its fleet token | `GET /v1/capacity` |
| Orchestrator API | `update-nodepool`, `provision-cluster` | start |

The controller holds no credential that can write to a KV cluster. Every change goes through
a workflow and Git.

---

## 10 :: Open items

| # | Item |
|---|---|
| O1 | `update-nodepool` does not exist in the workflows repo yet. Until it does, the controller has no way to grow a cluster |
| O2 | `provision-cluster` waits for a human merge. A standby cluster therefore needs a person to merge it, which the lead time of one standby must absorb |
| O3 | A zone holding KV clusters of more than one server type: one active/standby chain per server type, or one per zone |
| O4 | The capacity policy file's path and owner in the platform repo |
| O5 | `HEADROOM_BUFFER_PERCENT` in `create-vm` defaults to 30 and is set per deployment, not read from the policy file (AD31) |
| O6 | `HighNodeUtilization` and `CompactAndScale` are not confirmed on any KV cluster (AD30) |
