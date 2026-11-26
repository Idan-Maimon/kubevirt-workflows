# 04 :: Update NodePool

**Animation:** [`../animations/04-update-nodepool.html`](../animations/04-update-nodepool.html)
**Implementation:** [`update_nodepool.py`](https://github.com/team-redbull/workflows/blob/main/workflow_domains/server_lifecycle/update_nodepool.py), with its children `scale_up_nodepool.py` and `scale_down_nodepool.py`, in `team-redbull/workflows`

| | |
|---|---|
| **Trigger** | A tenant through Wingman, or an SRE: set how many workers one NodePool runs. The KV Capacity Controller, growing a KV cluster's NodePool ([kv-capacity-controller.md](../kv-capacity-controller.md), R1) |
| **Workflow id** | `update-nodepool-<cluster>`, one run per cluster; its children `scale-up-nodepool-<cluster>` and `scale-down-nodepool-<cluster>` |
| **Runs on** | The MCE's server-lifecycle queue; day1 Git, applied by ArgoCD |
| **Writes** | The NodePool's replicas in the cluster's day1 file, on `main`; for a scale-down, the `cluster.x-k8s.io/delete-machine` mark on the Machines that leave |
| **Ends at** | ArgoCD synced to the commit and the NodePool read back; for a scale-down, every marked Machine deleting |

> **The desired worker count enters the system here, and only here.** Supplying the machines
> (the Inventory Controller, AD26) and collecting the ones that leave (AD34) follow from it.

---

## 1 :: Purpose

Set one NodePool's replicas exactly as asked. Only the cluster's own NodePools count, and each
NodePool is set on its own, with no balance rule across its siblings. For a scale-down, choose which
servers leave: named servers, a policy, or CAPI's own pick.

---

## 2 :: Inputs

`POST /workflows/server-lifecycle/update-nodepool`

| Field | Required | Notes |
|---|---|---|
| `mce_cluster` | ✅ | The MCE, by cluster name. It selects the worker queue and the day1 folder |
| `cluster` | ✅ | The hosted cluster, whose day1 file holds its NodePools |
| `nodepool` | ✅ | The NodePool to change |
| `replicas` | ✅ | The NodePool's new total, absolute: a repeat changes nothing |
| `scale_down_policy` | | Scale-down only: `fewest-pods`, `least-requested` or `least-utilized`, ahead of the NodePool's own `redbull.io/scale-down-policy` |
| `server_names` | | Scale-down only: exactly the servers that leave, as many as the replicas removed. Sent without `scale_down_policy` |

A run that scales up, or changes nothing, lists the two scale-down fields in its result's `ignored`.

---

## 3 :: Process flow

### `update-nodepool`

| # | Phase | Action | On failure |
|---|---|---|---|
| 1 | `reading-day1` | Read the cluster's day1 file: its HostedCluster, and every NodePool's replicas and InfraEnv | A file with problems is refused |
| 2 | `reading-nodepools` | Read the HostedCluster's NodePools on the MCE. Live and Git agree both ways: the same NodePools, InfraEnvs and replicas | `NodePoolReplicasDriftError`, nothing written. A NodePool on neither side: `NodePoolNotFoundError` |
| 3 | `planning` | The NodePool takes the number asked. A NodePool already there completes with direction `none` | Named servers that do not match the replicas removed: `ScaleDownServersInvalidError`, nothing written |
| 4 | `scaling-up` or `scaling-down` | The child of that direction, awaited, on its own id and queue | |

### `scale-up-nodepool`

| # | Phase | Action |
|---|---|---|
| 1 | `committing-day1` | The new replicas on day1 `main`, compare-and-set on the file the parent read |
| 2 | `syncing-argo` | The cluster's ArgoCD Application synced to exactly that commit |
| 3 | `verifying-nodepools` | Every NodePool read back on the MCE with its new replicas |

### `scale-down-nodepool`

| # | Phase | Action | On failure |
|---|---|---|---|
| 1 | `selecting-servers` | Named servers: each one's Machine, found by its Agent's BareMetalHost, else its hostname, else its Node. A policy: the NodePool's Machines ranked by it. Neither: CAPI picks at random | Refused, with nothing written: an unknown policy, a Machine already deleting or marked by another run, a rollout, a named server that no Machine of the NodePool is, or an unnamed CAPI-unhealthy Machine that CAPI would take instead |
| 2 | `marking-machines` | Put `cluster.x-k8s.io/delete-machine` on each chosen Machine, and read it back, before the commit | |
| 3 | `committing-day1` | As in scale-up | A refused commit takes the marks off again, and the run fails |
| 4 | `syncing-argo` | As in scale-up. Once the commit has landed the marks stay: they make CAPI take the right servers | |
| 5 | `verifying-nodepools` | As in scale-up | |
| 6 | `verifying-machines` | With marks: every marked Machine deleting or gone | An unmarked Machine deleting fails the run |

### Why mark first, then lower the count

CAPI deletes a marked Machine before any other, under every delete policy, so lowering the replicas
then removes exactly the Machines marked. Deleting a Machine directly makes its MachineSet replace it
at once, so the node comes back on another machine.

---

## 4 :: What happens next

**Scaling up.** The NodePool's new workers wait for Agents. The Inventory Controller orders a
machine for each waiting worker, using a spare first (AD26, [01](01-add-server-to-mce.md)).

**Scaling down.** CAPI deletes the marked Machines, their nodes drain, and their Agents come free.
Each of those Agents is used, labelled `redbull.io/claimed`, so no NodePool claims it again. The
Inventory Controller collects it through `remove-server-from-mce`, which deletes a VM as its last
step (AD34, AD36, [02](02-remove-server-from-mce.md)). A machine that has served a cluster is never
reused as it is (AD23).

Demand and supply meet only in what the hub shows.

---

## 5 :: Idempotency

- One run per cluster, so requests for one cluster run one at a time.
- Replicas are absolute, so a repeat commits nothing new.
- A re-run resumes: when day1 already holds the number but the MCE does not show it yet, the run
  carries on from the sync.
- Marks are read back, and an earlier attempt's mark on a Machine no longer chosen is taken off
  first.

---

## 6 :: Built today vs. the architecture

`team-redbull/workflows`, `main`, as of 2026-11-26:

| # | Architecture | Built today |
|---|---|---|
| 1 | The phases above | Built |
| 2 | The Inventory Controller collects the Agents a scale-down frees (AD34) | Still to be built in herzi (herzi PR #1). Today a freed Agent goes back to its pool as it is |
| 3 | `update-nodepool` creates a NodePool that is missing: the KV Capacity Controller opens a node type on the standby this way (kv-capacity-controller.md, R1) | Refused with `NodePoolNotFoundError` |

---

## 7 :: Open questions

1. **The NodePool floor.** A KV cluster's NodePools keep at least 5 nodes. For tenant NodePools
   the recommendation is one, so a zone stays in the cluster (procedure 19, D2). Where the floor is
   enforced is still open.
