# Scale Workflow

Handles requests to change the number of worker nodes in a hosted cluster. When someone asks for "+5 nodes on OCP-A", this workflow figures out how to distribute them across zones, commits the change to Git, and waits for ArgoCD to apply it. It runs forever, processing one scale request at a time, and picks up newer requests that arrive while it is busy.

One workflow instance per `(cluster, node_type)` pair. Started via `SignalWithStart` — never call `StartWorkflow` directly.

---

## Signals

### scale

Requests a new total node count for the cluster. Carries the absolute desired total, not a delta.

**Receives**
| Field | Type | Required | Description |
|---|---|---|---|
| cluster | str | ✅ | Target cluster name e.g. `OCP-A` |
| node_type | str | ✅ | Node flavour e.g. `vm-32-128` |
| desired_total | int | ✅ | Total nodes wanted across all zones (absolute, not a delta) |
| argocd_app | str | ✅ | ArgoCD application to sync after committing |
| git_base_path | str | ✅ | Path prefix in the repo e.g. `nodepools/OCP-A/vm-32-128` |

### delete

Requests removal of a cluster's NodePools from Git. Stub — logs a warning, full implementation pending.

**Receives**
| Field | Type | Required | Description |
|---|---|---|---|
| cluster | str | ✅ | Cluster to delete NodePools for |
| node_type | str | ✅ | Node type to remove |

---

## Steps

| Step | Activity used | What happens |
|---|---|---|
| 1 | — | Wait for a `scale` or `delete` signal |
| 2 | — | If `delete`, handle deletion and return (stub) |
| 3 | `git.read_all_replicas` | Read current replica counts per zone from Git |
| 4 | — | Check if a newer signal arrived during the Git read — if yes, pivot to it |
| 5 | — | Compute zone distribution: `desired_total // 3`, extras go to earlier zones alphabetically |
| 6 | — | If distribution unchanged, skip steps 7-9 and loop back to step 1 |
| 7 | `git.commit_files` | Commit all changed zone files in a single commit |
| 8 | `argocd.sync_app` | Trigger ArgoCD sync |
| 9 | `argocd.wait_healthy` | Wait up to 10 minutes for ArgoCD to confirm Healthy + Synced |
| 10 | — | Loop back to step 1, or `continue_as_new` if 200 iterations reached |

---

## Workflow ID

`scale-{cluster}-{node_type}` e.g. `scale-OCP-A-vm-32-128`

## Task Queue

`nodepool-manager`

## continue_as_new

After 200 iterations to bound event history size.

## Minimum replicas

3 (one per zone). Scale signals requesting fewer than 3 nodes are silently discarded.
