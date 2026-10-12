# ArgoCD App Activity

Interacts with ArgoCD applications that manage the GitOps sync of cluster resources. After committing changes to Git, the workflow uses these activities to trigger ArgoCD and wait until the cluster reflects the new state.

---

## sync_app

Triggers an immediate ArgoCD sync for an application, telling ArgoCD to apply any pending Git changes to the cluster now rather than waiting for the next polling interval.

**Receives**
| Field | Type | Required | Description |
|---|---|---|---|
| app_name | str | ✅ | Name of the ArgoCD application |
| force | bool | ❌ | Force sync even if already in sync (default: false) |

**Provides**
| Field | Type | Description |
|---|---|---|
| sync_started | bool | True if the sync was successfully triggered |
| operation_id | str | ArgoCD operation ID for tracking |

---

## wait_healthy

Blocks until an ArgoCD application reaches both `Synced` and `Healthy` status. This confirms the cluster has applied all Git changes and the resources are running correctly.

**Receives**
| Field | Type | Required | Description |
|---|---|---|---|
| app_name | str | ✅ | Name of the ArgoCD application |
| timeout_seconds | int | ❌ | Max wait time (default: 600) |

**Provides**
| Field | Type | Description |
|---|---|---|
| sync_status | str | Final sync status: `Synced` |
| health_status | str | Final health status: `Healthy` |
| revision | str | Git commit SHA that ArgoCD synced to |

---

## get_status

Returns the current sync and health status of an ArgoCD application without waiting.

**Receives**
| Field | Type | Required | Description |
|---|---|---|---|
| app_name | str | ✅ | Name of the ArgoCD application |

**Provides**
| Field | Type | Description |
|---|---|---|
| app_name | str | Name of the application |
| sync_status | str | `Synced`, `OutOfSync`, or `Unknown` |
| health_status | str | `Healthy`, `Progressing`, `Degraded`, or `Unknown` |
| revision | str | Git commit SHA currently applied |
| message | str | Status message if degraded or error |
