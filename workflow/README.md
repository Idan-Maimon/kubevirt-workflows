# HyperShift Fleet Engine — Workflows

Temporal-based orchestration for scaling HyperShift HostedCluster worker nodes
across a fleet of OpenShift clusters backed by KubeVirt infrastructure.

---

## Naming Convention

Every resource name in the system is derived from two values: **cluster** and **node_type**.
No other input is needed to locate or create any resource.

### Node Type Format

```
vm-{cpu}-{ram}

Examples:
  vm-32-128    32 vCPU, 128 GB RAM
  vm-16-64     16 vCPU,  64 GB RAM
  vm-8-32       8 vCPU,  32 GB RAM
```

### Derived Names

| Resource | Pattern | Example (OCP-A, vm-32-128) |
|---|---|---|
| Temporal Workflow ID | `scale-{cluster}-{node_type}` | `scale-OCP-A-vm-32-128` |
| ArgoCD Application | `{cluster.lower()}-{node_type}` | `ocp-a-vm-32-128` |
| Git base path | `nodepools/{cluster}/{node_type}` | `nodepools/OCP-A/vm-32-128` |
| NodePool name (per zone) | `{cluster.lower()}-{node_type}-{zone}` | `ocp-a-vm-32-128-zone-1` |
| Zone manifest file | `{git_base_path}/{zone}.yaml` | `nodepools/OCP-A/vm-32-128/zone-1.yaml` |

> `argocd_app` and `git_base_path` are currently required fields in signals.
> Once the naming schema is confirmed they will be auto-derived and removed.

### Zones

Always exactly 3, fixed names: `zone-1`, `zone-2`, `zone-3`.

---

## Part 1 — NodePool Manager Workflow

### What it does

Handles scale requests for one `(cluster, node_type)` pair. Distributes the requested
total replica count evenly across the 3 zones and commits the change to Git.
ArgoCD picks up the commit and syncs the NodePool objects to the MCE cluster.

### Temporal interface

#### Workflow startup

Started automatically via `SignalWithStart` — callers never call `StartWorkflow` directly.

```
Workflow name : NodePoolManagerWorkflow
Task queue    : nodepool-manager
Workflow ID   : scale-{cluster}-{node_type}    e.g. scale-OCP-A-vm-32-128
Input         : NodePoolManagerInput { cluster: str }
```

`NodePoolManagerInput` carries only the cluster name for identity purposes.
All operational data travels in signals.

---

#### Signal: `scale`

Request to set the desired total replica count for a `(cluster, node_type)` pair.

```
Signal name: scale
Payload type: ScaleSignal
```

| Field | Type | Required | Description |
|---|---|---|---|
| `cluster` | `str` | ✓ | Cluster name, e.g. `"OCP-A"` |
| `node_type` | `str` | ✓ | VM profile, e.g. `"vm-32-128"` |
| `desired_total` | `int` | ✓ | Absolute total replicas across **all 3 zones combined** |
| `argocd_app` | `str` | ✓ | ArgoCD Application name, e.g. `"ocp-a-vm-32-128"` |
| `git_base_path` | `str` | ✓ | Git directory for this node type, e.g. `"nodepools/OCP-A/vm-32-128"` |

**Constraints:**
- `desired_total` must be `>= 3` (minimum 1 replica per zone)
- Signals below the minimum are silently discarded with a warning log
- Use the `delete` signal to remove a node type entirely

**Behaviour:**
- Last-write-wins: if multiple signals arrive, only the latest `desired_total` is applied
- If `desired_total` already matches the current git state, no commit is made
- Signals arriving while a commit is in flight are buffered and processed after ArgoCD syncs

**Example (Python):**
```python
from temporalio.client import Client
from temporalio.common import WorkflowIDConflictPolicy
from nodepool_manager.workflow import NodePoolManagerInput, NodePoolManagerWorkflow
from nodepool_manager.models import ScaleSignal, workflow_id

signal = ScaleSignal(
    cluster="OCP-A",
    node_type="vm-32-128",
    desired_total=10,
    argocd_app="ocp-a-vm-32-128",
    git_base_path="nodepools/OCP-A/vm-32-128",
)

await client.start_workflow(
    NodePoolManagerWorkflow.run,
    NodePoolManagerInput(cluster="OCP-A"),
    id=workflow_id("OCP-A", "vm-32-128"),   # "scale-OCP-A-vm-32-128"
    task_queue="nodepool-manager",
    id_conflict_policy=WorkflowIDConflictPolicy.USE_EXISTING,
    start_signal="scale",
    start_signal_args=[signal],
)
```

---

#### Signal: `delete`

Remove all zone NodePool manifests for a `(cluster, node_type)` pair from git.
ArgoCD prune deletes the NodePool objects from the MCE cluster.

```
Signal name: delete
Payload type: DeleteSignal
```

| Field | Type | Required | Description |
|---|---|---|---|
| `cluster` | `str` | ✓ | Cluster name |
| `node_type` | `str` | ✓ | VM profile to remove |
| `argocd_app` | `str` | ✓ | ArgoCD Application name |
| `git_base_path` | `str` | ✓ | Git directory to delete |

**Behaviour:**
- Takes priority over any pending `scale` signal
- Pending scale signals are discarded when delete is received
- Implementation is currently a stub (logged warning, no git mutation)

---

### Zone distribution algorithm

`desired_total` is spread across zones using even integer division:

```
base     = desired_total // 3
extras   = desired_total %  3
zones    = sorted alphabetically → zone-1, zone-2, zone-3
result   = first `extras` zones get base+1, rest get base
```

Examples:
```
desired_total=10  →  zone-1:4, zone-2:3, zone-3:3
desired_total=9   →  zone-1:3, zone-2:3, zone-3:3
desired_total=6   →  zone-1:2, zone-2:2, zone-3:2
desired_total=5   →  zone-1:2, zone-2:2, zone-3:1
desired_total=3   →  zone-1:1, zone-2:1, zone-3:1  ← minimum
```

---

### Workflow lifecycle

```
SignalWithStart("scale", ScaleSignal)
  │
  ├─ if workflow not running → start + deliver signal
  └─ if workflow running     → deliver signal to existing execution

Workflow loop:
  1. Check _pending_scale / _pending_delete
     └─ if both None → EXIT (next request starts a fresh execution)
  2. delete takes priority if set
  3. Read current replicas from Git (all 3 zones in one clone)
  4. Pre-commit checkpoint: pivot to latest signal if newer one arrived
  5. Compute new distribution
  6. If no change → back to step 1
  7. Commit all changed zone files in one git commit
  8. Trigger ArgoCD sync
  9. Wait for ArgoCD Healthy + Synced (up to 10 min)
 10. Back to step 1

After 200 iterations → continue_as_new (history reset, no data loss)
```

---

### Adding a new node type

No configuration changes required. A new node type is onboarded by:

1. Creating the 3 zone YAML files in git under `nodepools/{cluster}/{node_type}/`
2. Creating the ArgoCD Application `{cluster.lower()}-{node_type}` pointing to that path
3. Sending the first `scale` signal — Temporal starts the workflow automatically

The first signal IS the registration.

---

## Part 3 — Replenishment Workflow

> See `replenishment/` (not yet implemented).

Triggered by the Fleet Engine controller when an InfraEnv drops below its agent
low-watermark. Fans out N parallel `ProvisionOneVM` child workflows.

---

## Part 2 — Fleet Engine Controller

> Lives in a separate repository.

Watches InfraEnv objects on the MCE cluster. When available agent count drops
below the low-watermark annotation, triggers the Replenishment workflow.

---

## Repository layout

```
workflow/
├── README.md
├── PLAN.md
├── Dockerfile
├── requirements.txt
├── .gitignore
├── nodepool_manager/
│   ├── models.py       naming convention helpers + all signal/input types
│   ├── workflow.py     Temporal workflow definition
│   ├── activities.py   git read/commit, ArgoCD sync/wait
│   └── worker.py       Temporal worker entry point
├── shared/
│   ├── git_client.py   clone, read replicas, commit distribution
│   ├── argocd_client.py sync + poll ArgoCD REST API
│   └── spread.py       even zone distribution algorithm
├── tests/
│   └── run_tests.py    7 integration tests (requires port-forward to Temporal)
└── deploy/
    ├── deployment.yaml       worker Deployment (hypershift-workflows namespace)
    └── secret.example.yaml   credential template — copy to secret.yaml, never commit
```

---

## Environment variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `GIT_REPO_URL` | ✓ | — | HTTPS URL of the git repo |
| `GIT_TOKEN` | ✓ | — | Git personal access token (read + write) |
| `ARGOCD_TOKEN` | ✓ | — | ArgoCD API bearer token |
| `ARGOCD_URL` | | cluster route | ArgoCD server URL |
| `GIT_BRANCH` | | `main` | Git branch for commits |
| `TEMPORAL_HOST` | | `temporal-frontend.temporal.svc.cluster.local:7233` | Temporal frontend |
| `TEMPORAL_NAMESPACE` | | `default` | Temporal namespace |
| `TEMPORAL_TASK_QUEUE` | | `nodepool-manager` | Task queue name |

> The ArgoCD JWT token expires in ~24 hours. For production, use a long-lived
> service account token obtained via the ArgoCD API.

---

## Key design decisions

| ID | Decision | Rationale |
|---|---|---|
| ADR-O6 | Deterministic workflow IDs | Temporal deduplicates; no external locking needed |
| ADR-O8 | VM creation via direct Kubernetes API | Not via Git — KubeVirt owns VM lifecycle |
| ADR-O9 | Last-write-wins signal field | Desired-state semantics; stale intermediates are irrelevant |
| ADR-O10 | No cancellation past git commit | Once committed, ArgoCD reconciles; mid-sync abort creates inconsistency |
