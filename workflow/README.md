# HyperShift Fleet Engine — Workflows

Temporal-based orchestration for scaling HyperShift HostedCluster worker nodes
across a fleet of OpenShift clusters backed by KubeVirt infrastructure.

---

## Repository layout

```
workflow/
├── nodepool_manager/     # Part 1 — NodePool scale workflow
├── replenishment/        # Part 3 — VM provisioning workflow
├── shared/               # Shared clients (Git, ArgoCD, MCE, KubeVirt)
└── api/                  # REST API entry point (SignalWithStart)
```

The Fleet Engine controller (Part 2) lives in a separate repository.

---

## Part 1 — NodePool Manager Workflow

### What it does

Handles scale requests for a HyperShift NodePool. A user (or an automation layer)
sends a desired replica count. The workflow commits the change to Git and waits for
ArgoCD to sync it to the MCE cluster.

### Design: short-lived workflow per NodePool (Strategy B)

One Temporal workflow execution per NodePool, identified by a deterministic ID:

```
scale-{cluster}-{nodepool}    e.g.  scale-OCP-A-zone1
```

The workflow starts on the first request and exits when no more signals are pending.
The next request starts a new execution with the same ID. Temporal's `SignalWithStart`
API guarantees no signal is ever lost in the gap between executions.

### Signal model — last-write-wins

All scale requests arrive as Temporal signals carrying a `desired_replicas` integer.
The signal handler always overwrites a single `_pending` field — it does not queue:

```python
@workflow.signal
def scale(self, desired: int):
    self._pending = desired   # always latest, always overwrites previous
```

This means if three signals arrive (15, 12, 14), the workflow will only ever act on
the latest value it sees at each checkpoint. Intermediate values are discarded.

### Checkpoint model — when can we pivot?

The workflow has one hard checkpoint: the Git commit.

```
BEFORE git commit   → safe to pivot to latest _pending (skip stale desired)
AFTER  git commit   → must complete current path; process latest on next loop
```

Once a commit is pushed, ArgoCD owns the reconciliation. The workflow waits for
ArgoCD to report Healthy + Synced before looping.

### Full workflow loop

```
START (via SignalWithStart)
  LOOP:
    1. Wait for _pending to be set (blocks; workflow exits here if nothing arrives)
    2. Read _pending → clear it
    3. Read current replicas from Git (values.yaml)
    4. If _pending changed while reading Git → use latest value (pivot)
    5. If desired == current → back to step 1 (nothing to do)
    6. [activity] CommitNodePoolPatch  — patch spec.replicas in values.yaml, push to main
    7. [activity] SyncArgoCDApp        — POST /api/v1/applications/{name}/sync
    8. [activity] WaitArgoCDHealthy    — poll until health=Healthy, sync=Synced
    9. Back to step 1
    (after N loops → continue_as_new to reset Temporal event history)
```

### Activities

| Activity | What it does | Timeout |
|---|---|---|
| `read_replicas_from_git` | Clone/pull repo, parse values.yaml, return current replicas | 30s |
| `commit_nodepool_patch` | Pull latest, patch `spec.replicas`, commit, push to main | 60s |
| `sync_argocd_app` | POST to ArgoCD API to trigger a sync | 30s |
| `wait_argocd_healthy` | Poll ArgoCD API until `health=Healthy` and `sync=Synced` | 10m |

### Entry point — REST API

Callers do not start workflows directly. A thin REST API layer receives scale requests
and calls `SignalWithStart`:

```
POST /scale
{
  "cluster":          "OCP-A",
  "nodepool":         "zone-1",
  "desired_replicas": 15
}
```

This atomically starts the workflow if it is not running, or signals the existing
execution if it is. The caller gets an immediate `202 Accepted` response; the
workflow runs asynchronously.

### Scaling behaviour at fleet size (500 clusters, 3–6 NodePools each)

- **1,500–3,000 possible concurrent workflows** — Temporal handles this with ease.
  Workflows that are idle (waiting on step 1) hold no worker threads; they are pure
  state in Temporal's database.
- **Burst handling** — if many NodePools scale simultaneously, Temporal dispatches
  work to however many Python workers are running. Workers scale horizontally.
- **continue_as_new** — after a configurable number of loop iterations (default: 200),
  the workflow calls `continue_as_new` to reset its event history and avoid hitting
  Temporal's history size limit.

### Configuration

All connection details are supplied via environment variables:

| Variable | Description | Default |
|---|---|---|
| `TEMPORAL_HOST` | Temporal frontend address | `temporal-frontend.temporal.svc.cluster.local:7233` |
| `TEMPORAL_NAMESPACE` | Temporal namespace | `default` |
| `TEMPORAL_TASK_QUEUE` | Task queue name | `nodepool-manager` |
| `GIT_REPO_URL` | Git repository URL | — |
| `GIT_TOKEN` | Git personal access token | — |
| `GIT_BRANCH` | Target branch | `main` |
| `ARGOCD_URL` | ArgoCD server URL | — |
| `ARGOCD_TOKEN` | ArgoCD API token | — |

---

## Part 3 — Replenishment Workflow

> Documentation in `replenishment/README.md` (to be written).

Triggered by the Fleet Engine controller when an InfraEnv drops below its agent
low-watermark. Fans out N parallel `ProvisionOneVM` child workflows, one per VM
needed. Each child handles the full path: VM creation → BMH + NMState → Agent ready.

---

## Part 2 — Fleet Engine Controller

> Lives in a separate repository.

A Kubernetes controller that watches InfraEnv objects on the MCE cluster. When
available agent count drops below the low-watermark annotation, it calls
`SignalWithStart` on the Replenishment workflow.

---

## Key design decisions

| ID | Decision | Rationale |
|---|---|---|
| ADR-O6 | Deterministic workflow IDs | Temporal deduplicates; no external locking needed |
| ADR-O8 | VM creation via direct Kubernetes API | Not via Git — KubeVirt owns the VM lifecycle |
| ADR-O9 | Last-write-wins signal field, not a queue | Desired-state semantics; stale intermediate values are irrelevant |
| ADR-O10 | No in-flight cancellation past git commit | Once committed, ArgoCD reconciles; aborting mid-sync creates inconsistency |
