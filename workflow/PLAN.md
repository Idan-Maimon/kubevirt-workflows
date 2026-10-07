# Workflow Implementation Plan
## NodePool Scale Automation — Fleet Engine

---

## Context

This implements the orchestration layer for scaling HyperShift HostedCluster worker nodes
on top of KubeVirt infrastructure. The system manages a warm pool of MCE Agents so that
NodePool scaling is fast (agents already available) rather than blocking on VM provisioning.

Existing architectural decisions (from nodepool-scale-flow.html):
- **ADR-O9**: NodePool mutations are signals to a long-running Temporal workflow (one per NodePool)
- **ADR-O6**: Deterministic workflow IDs — Temporal deduplicates restarts safely
- **ADR-O8**: VM creation via direct Kubernetes API on KV Clusters (NOT via Git)
- **ADR-O2**: Durable resources (BMH, NMStateConfig, Secret) go through Git → ArgoCD
- **ADR-O10**: No in-flight cancellation — excess VMs land in warm pool

---

## Technology Stack

| Layer | Choice | Reason |
|---|---|---|
| Workflow engine | Temporal | Already decided; signal/FIFO semantics, child workflows |
| Language | Python | Confirmed |
| Kubernetes client | `kubernetes` Python client | Watch NodePools, InfraEnvs, Agents on MCE |
| Git operations | **Deferred** — direct MCE API for now | Git/ArgoCD path added later when environment is ready |
| Temporal SDK | `temporalio` Python SDK | Python Temporal SDK |

---

## Repository Structure

```
workflow/
├── PLAN.md                          ← this file
├── go.mod
├── go.sum
├── cmd/
│   ├── nodepool-worker/
│   │   └── main.go                  # Temporal worker for Parts 1 + 3
│   └── fleet-engine/
│       └── main.go                  # Kubernetes controller (Part 2)
├── internal/
│   ├── gitops/
│   │   ├── client.go                # Git clone, commit, push helpers
│   │   └── templates/               # Kustomize patches or raw YAML templates
│   │       ├── nodepool_patch.yaml
│   │       └── bmh_bundle.yaml
│   ├── mce/
│   │   └── client.go                # MCE/InfraEnv/NodePool watch helpers
│   └── kv/
│       └── client.go                # KubeVirt VM create helpers (ADR-O8)
└── workflows/
    ├── nodepool_manager/            # Part 1
    │   ├── workflow.go
    │   ├── signals.go
    │   └── activities.go
    ├── fleet_engine/                # Part 2
    │   ├── controller.go
    │   └── watcher.go
    └── replenishment/               # Part 3
        ├── workflow.go
        ├── provision_vm.go
        ├── activities.go
        └── server_scanner.go
```

---

## Part 1 — NodePool Manager Workflow

**What it is**: A long-running Temporal workflow, one instance per NodePool (e.g., `np-manager-OCP-A`).
It serializes all replica mutations via its signal queue so there are never concurrent Git writes.

**Diagram steps covered**: 1, 2, 3, 4, 5

### Inputs
```go
type NodePoolManagerInput struct {
    ClusterName   string // "OCP-A"
    NodePoolName  string // "OCP-A-zone1"
    GitRepoURL    string
    GitBranch     string
    MCECluster    string // kubeconfig context or API URL
}
```

### Signals
```go
type ScaleSignal struct {
    Delta     int    // +5 or -1
    RequestID string // idempotency key
    Requester string
}
```

### Workflow Logic
```
LOOP (long-running):
  1. Receive ScaleSignal from queue (blocks until signal arrives)
  2. Compute new replica count = current + delta
  3. Commit NodePool replicas patch to Git (activity: CommitNodePoolPatch)
  4. Wait for ArgoCD to sync (activity: WaitArgoSync, timeout 5m)
  5. Wait for MCE to allocate agents to NodePool (activity: WaitNodePoolReady, timeout 10m)
  6. Emit InfraEnvLevelChanged event (Fleet Engine picks this up via watch)
  REPEAT
```

### Activities
| Activity | What it does |
|---|---|
| `CommitNodePoolPatch` | git pull → patch replicas field → git commit → git push |
| `WaitArgoSync` | Poll ArgoCD Application until health=Healthy, sync=Synced |
| `WaitNodePoolReady` | Watch NodePool .status.conditions until Ready |

### Files to implement (in order)
1. `workflows/nodepool_manager/signals.go` — signal type definitions
2. `workflows/nodepool_manager/activities.go` — CommitNodePoolPatch, WaitArgoSync, WaitNodePoolReady
3. `workflows/nodepool_manager/workflow.go` — main workflow loop
4. `internal/gitops/client.go` — git helpers used by activities
5. `cmd/nodepool-worker/main.go` — worker registration

---

## Part 2 — Fleet Engine Controller

**What it is**: A Kubernetes controller (controller-runtime) running against the MCE cluster.
It watches InfraEnv objects. When an InfraEnv's available agent count drops below the
low-watermark, it signals (or starts) the Replenishment Temporal workflow.

**Diagram step covered**: 6

### Watch target
```
Resource: agent.open-cluster-management.io/v1beta1 / InfraEnv
Trigger:  status.agents count < spec.lowWatermark annotation
```

### Controller Logic
```
ON InfraEnv reconcile:
  1. Count agents in state = Available
  2. Read low-watermark from annotation: fleet-engine/low-watermark
  3. If available < low-watermark:
       deficit = low-watermark - available
       Start or Signal Temporal workflow: replenish-{clusterName}-{zone}
       Payload: { Zone, KVCluster, InfraEnvName, Count: deficit }
  4. Record last-evaluated timestamp in annotation to avoid tight loops
```

### Deterministic workflow ID (ADR-O6)
```
workflowID = fmt.Sprintf("replenish-%s-%s", clusterName, zone)
Temporal.StartWorkflowOptions{ WorkflowIDReusePolicy: AllowDuplicate }
```

### Files to implement (in order)
1. `workflows/fleet_engine/watcher.go` — InfraEnv inventory count helper
2. `workflows/fleet_engine/controller.go` — controller-runtime Reconciler
3. `cmd/fleet-engine/main.go` — manager setup, leader election

---

## Part 3 — Replenishment Workflow

**What it is**: A Temporal workflow started by the Fleet Engine. It fans out N parallel
`ProvisionOneVM` child workflows, one per VM needed. Each child completes the full
VM → BMH → Agent path independently.

**Diagram steps covered**: 8 → end (VM creation, Server Scanner, BMH/NMState to Git, Agent ready)

> The other Claude session is implementing the bare steps (VM → kubevirt+redfish → BMH →
> InfraEnv → NodePool) manually. Once that is validated, those steps map 1:1 to activities here.

### Parent Workflow Input
```go
type ReplenishInput struct {
    Zone         string
    KVCluster    string // KubeVirt infra cluster kubeconfig or API URL
    InfraEnvName string
    MCECluster   string
    GitRepoURL   string
    Count        int    // number of VMs to provision
}
```

### Parent Workflow Logic (ADR-O10: no cancellation)
```
1. Fan-out: for i in 0..Count, start ProvisionOneVM child workflow (parallel)
2. Wait for all children (collect results — do not cancel on partial failure)
3. Log summary: succeeded N, quarantined M
```

### ProvisionOneVM Child Workflow
```
Step 8:  CreateVM         — direct API to KV Cluster (ADR-O8)
Step 9:  WaitVMRunning    — poll VM phase == Running
Step 10: ScanForVM        — Server Scanner confirms VM in inventory
Step 11: CommitBMHBundle  — git commit BMH + NMStateConfig + Secret (ADR-O2)
Step 12: WaitArgoApplyBMH — ArgoCD applies BMH to MCE Hub
Step 13: WaitAgentReady   — watch Agent CR in InfraEnv until state = Available
ON ERROR at any step: quarantine VM, emit QuarantineEvent, return failure
```

### Activities
| Activity | What it does |
|---|---|
| `CreateVM` | Apply KubeVirt VM manifest to KV Cluster via direct API |
| `WaitVMRunning` | Poll VM .status.phase until Running (timeout 10m) |
| `ScanForVM` | Query Server Scanner / KV Cluster API to confirm VM visible |
| `CommitBMHBundle` | git commit BMH + NMStateConfig + BMC Secret for this VM |
| `WaitArgoApplyBMH` | Poll BMH .status.provisioning.state until available |
| `WaitAgentReady` | Watch Agent CR until status.conditions Ready=True |
| `QuarantineVM` | Label VM + record in quarantine ConfigMap; never returns to pool |

### Files to implement (in order)
1. `internal/kv/client.go` — KubeVirt VM create + status helpers
2. `workflows/replenishment/activities.go` — all activities above
3. `workflows/replenishment/provision_vm.go` — ProvisionOneVM child workflow
4. `workflows/replenishment/workflow.go` — parent fan-out workflow
5. `internal/gitops/templates/bmh_bundle.yaml` — BMH + NMState + Secret template
6. `workflows/replenishment/server_scanner.go` — Server Scanner query helper

---

## Development Sequence

```
Phase 0 — Scaffold
  [ ] go.mod init, Temporal + controller-runtime deps
  [ ] internal/gitops/client.go skeleton
  [ ] internal/mce/client.go skeleton
  [ ] internal/kv/client.go skeleton

Phase 1 — NodePool Manager (Part 1)
  [ ] signals.go
  [ ] activities.go (CommitNodePoolPatch first — most critical path)
  [ ] workflow.go
  [ ] cmd/nodepool-worker/main.go
  [ ] Integration test: signal → Git commit observed

Phase 2 — Fleet Engine Controller (Part 2)
  [ ] watcher.go
  [ ] controller.go
  [ ] cmd/fleet-engine/main.go
  [ ] Integration test: InfraEnv drops below watermark → workflow started

Phase 3 — Replenishment Workflow (Part 3)
  [ ] activities.go (CreateVM, WaitVMRunning — unblock on KV API)
  [ ] provision_vm.go child workflow
  [ ] workflow.go parent fan-out
  [ ] server_scanner.go
  [ ] Integration test: replenishment workflow ends with Agent in Available state

Phase 4 — Wiring
  [ ] End-to-end: signal NodePool Manager → Fleet Engine triggers → Replenishment completes
  [ ] Error paths: quarantine on activity failure
  [ ] Metrics / observability hooks
```

---

## Open Decisions

| ID | Question | Default assumption |
|---|---|---|
| L1 | Go confirmed as language? | Yes (Go) |
| G1 | Git auth method? (SSH key, HTTPS token) | SSH key via mounted secret |
| G2 | Git repo structure — one repo or separate repos for NodePool vs BMH? | One repo, separate directories |
| A1 | ArgoCD — poll REST API or watch Application CR? | Watch Application CR via kubeconfig |
| S1 | Server Scanner — existing service or implement from scratch? | Implement as Temporal activity scanning KV Cluster API |
| W1 | Watermark config — static annotation or CRD? | Annotation for MVP, CRD later |
| T1 | Temporal namespace and address — local dev or shared cluster? | Local dev (localhost:7233) initially |
