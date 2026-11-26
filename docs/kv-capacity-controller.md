# KV Capacity Controller

The KV Capacity Controller automates the manual work of sizing KV clusters. Its job is to grow KV
clusters' NodePools as VMs fill them, and to keep an empty standby KV cluster ready. It runs on
every Seed and manages the KV clusters that Seed hosts.

**Implementation:** not started.

**Version:** 0.3

**Decisions:** AD27, AD28, AD30, AD31, AD33, AD35 in [architecture.md](architecture.md).

---

## Requirements

| ID | Requirement | Description |
|---|---|---|
| R1 | Update KV cluster NodePool replicas | Watch the NodePool's capacity, and increase its replicas based on the free-CPU policy. |
| R2 | Keep a standby KV cluster | Keep an empty KV cluster ready on the Seed, so a node type that outgrows the working clusters finds room at once (AD35). It is created through `provision-cluster`. |

---

## Terms

| Term | Meaning |
|---|---|
| **KV cluster** | A hosted cluster on the Seed whose bare-metal workers run KubeVirt VMs |
| **Working cluster** | A KV cluster with at least one NodePool |
| **Standby cluster** | A KV cluster on the Seed with its control plane only |
| **Requested CPU** | CPU requested on a NodePool: the pods running on its nodes, plus the Halted VMs that would start on it, each at its pod's request |
| **Reserve** | The share of a cluster's CPU kept free: `freeCpuPercent` from the capacity policy, the live-migration reserve. It exists as whole empty nodes only because clusters bin-pack (AD30) |

---

## R1 · Update KV cluster NodePool replicas

The controller checks every KV cluster's NodePools and adds a node to any NodePool that is 70% or
more requested.

| Rule | What the controller does |
|---|---|
| **Every 2 minutes** | One pass over the NodePools of every KV cluster on the Seed |
| **NodePool by NodePool** | Each NodePool is measured on its own nodes. A cluster can hold NodePools of different CPU architectures, and VMs can't migrate between them, so one NodePool's free CPU is no use to another |
| **Grows at 70% requested** | When the CPU requested on a NodePool reaches 70% of its capacity, the controller adds a node to it. Requested means the pods running on its nodes plus the Halted VMs that would start on it. Capacity includes nodes still joining, so the controller adds another node only if the NodePool would still be at 70% or more with them |
| **One node at a time** | It raises that NodePool's replicas by one |
| **40 nodes per cluster** | A cluster's size is the sum of replicas across all its NodePools. At 40, none of its NodePools grows |
| **Opens the standby when clusters are full** | When a node type's NodePools are at 70% and every working cluster holding them is at 40 nodes, the controller calls `update-nodepool` on the standby for that node type, with `standbyWorkers` (5) replicas. `update-nodepool` creates the NodePool, and R1 grows it from then on |

```
every 2 minutes, for each NodePool P of each working KV cluster C:
    requested(P) = CPU requests of pods on P's nodes + Halted VMs that would start on P
    capacity(P)  = replicas(P) × CPU of one node        # nodes still joining included
    if requested(P) ≥ growAtCpuPercent of capacity(P):
        if sum of replicas over C's NodePools < maxNodes:
            update-nodepool  cluster=C  nodepool=P  replicas=replicas(P) + 1
        else if every working cluster with P's node type is at maxNodes:
            update-nodepool  cluster=standby  nodetype=type(P)  replicas=standbyWorkers
```

### What it reads

Each KV cluster is read through its admin kubeconfig, which lives on the Seed beside the cluster's
hosted control plane. Requests are counted the way `create-vm`'s placement counts them
([design](https://github.com/team-redbull/workflows/blob/docs/create-vm-placement/docs/design/create-vm-placement.md), §6), Halted VMs included (AD31).

| Read | From | Used for |
|---|---|---|
| `HostedCluster` (`hypershift.openshift.io/v1beta1`): `metadata.name`, `status.conditions` | The Seed | The KV clusters |
| `NodePool` (`hypershift.openshift.io/v1beta1`): `spec.clusterName`, `spec.replicas`, `status.replicas`, `status.conditions` | The Seed | Each NodePool's capacity, and its cluster's size |
| Nodes, Ready and not cordoned, by their `hypershift.openshift.io/nodePool` label, with allocatable CPU | Each KV cluster | The CPU of one node of each NodePool |
| CPU requests of every non-finished pod on those nodes | Each KV cluster | Requested |
| Every Halted VM, at its pod's request (vCPU × 15/16, memory + 1 GiB), on the NodePool it would start on | Each KV cluster | Requested. kubevirt-redfish will start them |

### Talking to Temporal

| | |
|---|---|
| Order | `update-nodepool` with `cluster=C`, `nodepool=P`, `replicas=replicas(P) + 1`; on the standby, `nodetype=type(P)`, `replicas=standbyWorkers` |
| Deduplication | The workflow id, `update-nodepool-<cluster>-<node-type>`. The controller keeps no record of what is in flight; a `409` for a run already going is success |

- **A rejected or failed order leaves the gap open,** and the next pass sees it. The evaluation
  cycle is the retry.
- **A cluster that cannot be read** is left out for that pass only. Nothing is retained.

---

## R2 · Keep a standby KV cluster

The controller keeps one empty KV cluster ready on the Seed: a hosted cluster with its control plane
running and no NodePools. It costs only control-plane pods, and node types get NodePools on it when
they need room (R1).

| Rule | What the controller does |
|---|---|
| **A standby is an empty KV cluster** | A KV cluster on the Seed with its control plane only |
| **Keeps one ready** | When the Seed has fewer standbys than `standbyClusters` (1), the controller orders a new KV cluster through `provision-cluster`, with no NodePools |
| **Hands over by itself** | Once the standby gets its first NodePool, it is a working cluster, and the controller orders the next standby |
| **Acts on change** | It runs whenever a HostedCluster or NodePool on the Seed changes, and every 30 minutes as a safety net. It reads only the Seed |
| **Names the next cluster** | The lowest unused `ocp4-<lifecycle>-kv-<site>-<zone>-<id>` ([naming convention](naming-convention.md)) |
| **Deduplicates by workflow ID** | `provision-cluster-<cluster>`. A `409` for a run that is already going counts as success |

```
on a HostedCluster or NodePool change, and every 30 minutes:
    standby = KV clusters on the Seed with zero NodePools
    if count(standby) < standbyClusters:
        provision-cluster  name=next KV cluster name  nodepools=none
```

A node type new to the Seed gets its first NodePool from an operator through Wingman, with one
`update-nodepool` call on the standby. R1 grows it from then on.

---

## Config

| ConfigMap | Purpose |
|---|---|
| `capacity-policy` | The organisation-wide capacity values (AD31), shared with `create-vm` |
| `kv-capacity-controller-config` | The controller's own settings for its Seed |

```yaml
# capacity-policy.yml
data:
  maxNodes: "40"               # hard size of a KV cluster, organisation-wide
  freeCpuPercent: "15"         # free CPU kept above used CPU; the live-migration reserve
  growAtCpuPercent: "70"       # requested CPU, as a share of a NodePool's capacity, at which the controller adds a node
  standbyWorkers: "5"          # the replicas a node type's first NodePool on the standby gets
  standbyClusters: "1"         # standby clusters kept per Seed
```

```yaml
# kv-capacity-controller-config.yml
data:
  zone: az1                    # required; never changes at runtime
  site: five                   # required; never changes at runtime
  reconcileInterval: 2m        # greater than zero
  standbyCheckInterval: 30m    # R2's safety check, on top of reacting to changes
  clusterReadTimeout: 10s      # greater than zero
  dryRun: "true"               # logs the orders it would send; set false to send them
```

---

## Access

| Where | What | Verbs |
|---|---|---|
| Seed | `hostedclusters`, `nodepools` | get, list, watch |
| Seed | `leases` in its namespace | get, create, update |
| Each KV cluster | Nodes, pods, VirtualMachines, VirtualMachineInstances, through the admin kubeconfig on the Seed | get, list |
| Orchestrator API | `update-nodepool`, `provision-cluster` | start |

The controller holds no credential that can write to a KV cluster. Every change goes through a
workflow and Git.

---

## Why it is built this way

| Decision | Reason |
|---|---|
| Exactly one controller per Seed cluster | It reads and orders only for the KV clusters its own Seed hosts, so a zone with a second Seed simply has a second, independent controller |
| Leader election, and exit on losing the lease | Two pods during a rollout never order at the same time |
| Stores nothing; derives every figure each pass | A restart costs one pass |
| Counts requested CPU as `create-vm` does, Halted VMs included | Placement and growth agree on what is free (AD31) |
| Orders absolute totals, deduplicated by workflow id | A repeated order is harmless, and the controller keeps no record of what is in flight |
| Every change through a workflow and Git | NodePool totals and new clusters stay in Git (AD22) |
| Starts in dry run | It logs the orders it would send until it is trusted to send them |

---

## Open

| # | Item |
|---|---|
| O1 | `update-nodepool` exists on the branch `feat/update-nodepool`, not yet merged. It addresses a cluster's NodePools by name or by kind, with id `update-nodepool-<cluster>`; the deduplication in R1 still uses `update-nodepool-<cluster>-<node-type>` |
| O2 | `provision-cluster` waits for a human merge. A standby cluster therefore needs a person to merge it, and that wait comes out of the standby's lead time |
| O3 | The capacity policy file's path and owner in the platform repo |
| O4 | `HEADROOM_BUFFER_PERCENT` in `create-vm` defaults to 30 and is set per KV cluster worker, not rendered from the policy file (AD31) |
| O5 | `HighNodeUtilization` and `CompactAndScale` are not confirmed on any KV cluster (AD30) |
| O6 | Credentials: each KV cluster is read through its admin kubeconfig, which can write, while Access says the controller holds no credential that can write. Either a read-only ServiceAccount on each KV cluster, created by `provision-cluster`, or keep the admin kubeconfig and drop that sentence |
| O7 | `create-vm` checks whether a VM fits per KV cluster, not per NodePool. With NodePools of different CPU architectures it has to check the NodePool that matches the VM, or `create-vm` and the controller count capacity differently (AD31) |
| O8 | `update-nodepool` creates a NodePool when it is missing, from the cluster, the node type and the replicas. Today it changes existing NodePools only |
| O9 | The Seed's limit: how many KV clusters a Seed holds. The controller orders a standby while the Seed is below it |
