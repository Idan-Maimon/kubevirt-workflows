# create-vm: a worker inside every KV cluster, one placement at a time per zone

The design, in plain language, is `docs/design/create-vm-placement.md` (written 2026-11-17).
This file is the implementation plan for it. **Nothing is implemented until the operator approves.**

## Context

create-vm today runs ONE hub limb that reaches each KubeVirt (KV) cluster through two HTTP
agents behind Routes (`kv-capacity`, `kv-vm-api`), reads the zone's clusters from day1, and
ranks them itself. Two problems: every KV cluster needs two extra services, Routes, fleet tokens
and the repo's only unverified-TLS exception (`KV_AGENT_CA`); and nothing coordinates two runs,
so parallel creates all pick the same cluster (seen in the lab).

Decided with the operator, 2026-11-17 (reversing CLAUDE.md §4's "none to reopen" block):

1. **One `vm-lifecycle-worker` inside each KV cluster**, polling
   `vm-lifecycle-activity-<kv cluster>`, acting on its own API server as its own ServiceAccount,
   dialling out to the hub's Temporal over gRPC/TLS (the per-MCE `server-lifecycle-worker`
   pattern). It reports its cluster's capacity AND creates/reads/deletes VMs. The agents, their
   Routes and tokens, `KV_AGENT_CA`, the vendored agent contract and the hub vm-lifecycle limb go.
2. **server-scan takes no part** in placement or creation (the 2026-11-08 ledger proposal and
   this plan's earlier server-scan phase are dropped). No server-scan change at all.
3. **The zone's clusters come from day1** (`sites/<site>/mces/ocp4-seed-<site>-<zone>/hostedClusters/`),
   read on the **cluster-lifecycle limb** with `redbull-git-token`, the token provision-cluster uses.
4. **Placement is serialized per (site, zone)**: alphabetical scan, each cluster's figures read
   live from its worker, the FIRST that fits wins, and the scan stops. A **pending list** (chosen,
   not yet created) is added to what each cluster reports, because creation is parallel.
5. **Creation is parallel.** The run draws the MAC itself (no MAC bookkeeping); a MAC or name the
   cluster refuses is redrawn on the same cluster, **3 tries in total**, then the run fails.
6. Today there is one KV cluster per zone; nothing in the code assumes it.
7. **Nothing is pushed** in any repo.

---

## 0. Preconditions

- workflows: branch `feat/vm-lifecycle-per-kv-cluster` off `main`; follow `/redbull-workflows`.
- redbull-platform: the local checkout is a dirty `feat/cluster-lifecycle-worker` touching the
  files this plan replaces — work in a separate worktree off fresh `origin/main`.
- Operator: terminate any old-shape run (`WorkflowType='CreateVmWorkflow' AND
  ExecutionStatus='Running'`) — the hub limb is deployed (v1.0.7) but no agent is, so none can succeed.

---

## 1. The workflows

### 1.1 Zone placer — new `workflow_domains/vm_lifecycle/kv_placer.py`

`KvPlacerWorkflow`, one per zone: id `kv-placer-<site>-<zone>` (builder in
`shared/workflow_ids.py`), own queue `KV_PLACER_WORKFLOW_QUEUE = "kv-placer-workflow"`, registered
in `main_worker_init.py`'s `_WORKER_SPECS`. Long-lived; never completes on its own.

- **How requests reach it** (workflow code can only signal or start another workflow — verified
  in the installed SDK: `ExternalWorkflowHandle` has `signal`/`cancel` only; workflow-side
  `signal_with_start_workflow` exists in 1.32 but is marked experimental and the pin is
  `>=1.28`, so it is NOT used): the requester `start_child_workflow(KvPlacerWorkflow.run, …,
  id=…, parent_close_policy=ABANDON)` with its request as the first input; on
  `WorkflowAlreadyStartedError` it signals `request_placement` to the running placer instead.
- **How the answer comes back**: the placer signals the requester's workflow id
  (`placement_decided`); the requester `wait_condition`s on it, bounded (30 min →
  `KvPlacementUnansweredError`, WORKFLOW-RAISED). Later the requester signals the placer
  `placement_settled(request_id, created | failed)`.
- **The loop**: FIFO queue of requests. For each: walk its candidate list (from day1, sorted),
  `read_kv_capacity` on `vm_lifecycle_activity_queue(name)`, add that cluster's pending entries,
  apply the fit rule; first fit → add a pending entry, signal the requester, next request. No fit
  → signal "not placed" with the per-cluster table.
- **Nothing inside the loop may wait forever** (one stuck read would stall the zone):
  `read_kv_capacity` carries `schedule_to_start_timeout=30s` (→ `no-worker`) and
  `schedule_to_close_timeout≈60s` (→ `unreachable`), inside the best-effort `try` the checker
  allows (WF005). A skip row, never a failure of the placer.
- **Pending entries** `{request_id, requester workflow id, cluster, cpu_m, mem_b, added_at}` leave
  on `created`, on `failed`, or 30 min after `added_at` (`workflow.now()`).
- **History bound**: `continue_as_new` every N requests or when suggested, carrying the queue and
  the pending list, after `wait_condition(workflow.all_handlers_finished)`. A signal arriving
  during the CAN task makes the server refuse the completion, so none is lost.
- **Fit policy**: `workflow_domains/vm_lifecycle/placement.py`, pure and sandbox-safe —
  `activities/vm_lifecycle/placement.py` moved, its `KvProbeFailure` import cut, best-fit
  replaced by first-fit, a `pending` term added. `pod_cpu_millicores` / `pod_memory_bytes`,
  the fit-per-node and buffer-per-cluster rules, `SKIP_REASONS` are kept.
  The buffer comes back IN the capacity report (each cluster's worker setting): workflow code
  cannot read settings.
- `progress` query: the queue length, the pending list, the request in hand.

### 1.2 create-vm — `workflow_domains/vm_lifecycle/create_vm.py` (rewritten, no `workflow.patched`)

```
listing-kv-clusters   list_kv_clusters on CLUSTER_LIFECYCLE_ACTIVITY_QUEUE (outside the lock,
                      in parallel across runs); empty → NoKvClusterError
awaiting-placement    ask the zone placer (1.1); not placed → NoKvClusterFitsError (_SKIP_SUMMARY)
creating-vm           kv_queue = vm_lifecycle_activity_queue(chosen) as a LOCAL name;
                      suffix = workflow.uuid4().hex[-6:]; name = vm_name(infra_env, suffix);
                      create_vm_on_cluster (NO schedule_to_start); VmIdentityConflictError →
                      new suffix, same cluster; 3 tries then VmNameExhaustedError; then signal
                      the placer created | failed
awaiting-root-disk    await_vm_ready, unchanged (heartbeating, 8 s polls, 10 min own deadline)
removing-vm           only on the deadline: delete_vm_on_cluster (name AND MAC), then
                      VmRootDiskNotBoundError
completed             name, MAC, namespace, size, cluster, the placement table
```

- `known_macs` and the MAC-tail check go; the limb composes the MAC from the suffix and its own
  `VM_MAC_PREFIX` (today's `mac_for`).
- New WORKFLOW-RAISED `KvPlacementUnansweredError`; `VmNameInvalidError` for a `vm_name`
  `ValueError` (a plain exception in workflow code hangs the task).
- Queues are LOCAL names assigned from the builders (`tests/test_worker_registration.py::_resolve_queue`
  follows only that — the `add_server_to_mce.py:649` shape).

### 1.3 Contract

- `shared/consts.py`: `vm_lifecycle_activity_queue(kv_cluster)`, `KV_PLACER_WORKFLOW_QUEUE`;
  `VM_LIFECYCLE_ACTIVITY_QUEUE` stays as the prefix.
- `shared/models/vm_lifecycle.py`: keep `CreateVmInput`, `KvClusterListRequest/Entry/List`,
  `KvCapacityReport` / `KvNodeCapacity` / `KvHaltedReservation` (no longer a vendored contract;
  `+ buffer_percent`), `VmCreateRequest`, `VmCreated`, `VmReady*`, `VmDelete*`. New: the placer's
  run args, `KvPlacementRequest` (requester id, request id, size, candidates),
  `KvPlacementDecision` (chosen or not, the per-cluster table), `KvPlacementSettled`, the
  pending entry. Drop `KvVmCreateRequest/Response`, `KvVmConflict`, `KvRootDisk`, `KvVmState`,
  `KvApiError`, `known_macs`.
- `shared/interfaces/cluster_lifecycle.py`: `list_kv_clusters` under a "shared with the
  vm-lifecycle domain" header (the `get_inventory_segment` precedent).
  `shared/interfaces/vm_lifecycle.py`: `read_kv_capacity`, `create_vm_on_cluster`,
  `await_vm_ready`, `delete_vm_on_cluster`.
- `shared/exceptions.py`: − `KvAgentAuthError`, `KvCapacityUnavailableError`,
  `KvVmApiUnavailableError`; + `KvClusterApiError` (transient), `KvClusterAccessError` (403,
  permanent), the two WORKFLOW-RAISED above.
- `shared/settings/vm_lifecycle.py`: `KV_CLUSTER` (required, DNS label, NEVER canonicalised — it
  must equal the day1 file stem), `HEADROOM_BUFFER_PERCENT` (0..90), `VM_MAC_PREFIX` (validated as
  today), `VM_STORAGE_CLASS_NAME`, `VM_NETWORK` (JSON), `VM_NODE_SELECTOR` (JSON),
  `VM_REDFISH_LABEL`. − day1, `KV_*` URL templates, tokens, CA.
- `shared/cluster_names.py`: `seed_cluster`, `kv_cluster_prefix`, `is_kv_cluster_of` stay.

### 1.4 Limbs

- **cluster-lifecycle**: `activities/cluster_lifecycle/kv_clusters.py` (the seed-folder walk,
  moved from `activities/vm_lifecycle/day1_repo.py`, over the shared `activities/day1_repo.py`);
  a thin `list_kv_clusters` in its `activities.py`; registered in its `worker_init.py`. No new
  config. `tests/test_day1_repo.py` and CLAUDE.md §4 updated (the walk moves limbs).
- **vm-lifecycle** (`activities/vm_lifecycle/`, rewritten, runs inside a KV cluster):
  - `kubevirt_api.py`: in-cluster config, the sync client in `to_thread`, a request timeout on
    every call (the PATTERN of `activities/server_lifecycle/cluster_api.py`, own classification:
    5xx/401/transport → `KvClusterApiError`, 403 → `KvClusterAccessError`, 400/422 →
    `VmRequestRejectedError`; KubeMacPool's "failed to allocate requested mac address" →
    `VmIdentityConflictError` at ANY status, matched first); paged pod lists; bounded error text.
  - `capacity.py` (pure): nodes/pods/VMs/VMIs → `KvCapacityReport` — the port of kv-capacity
    with three corrections: labelled VMs counted in **any namespace**, with **any runStrategy**,
    and **+1 GiB** launcher pad (so a pending entry and the VM it becomes count the same).
  - `vm_spec.py` (pure): the VirtualMachine `kv-agents/templates/vm.yaml.j2` renders,
    `same_identity`, root-disk facts.
  - `activities.py` (thin): `read_kv_capacity`; `create_vm_on_cluster` (read by name → refuse a
    MAC another VM of the cluster has → create → on AlreadyExists re-read before deciding, so a
    retried create finds its own VM; namespace missing → `VmNamespaceNotFoundError`);
    `await_vm_ready`; `delete_vm_on_cluster` (by name AND MAC, VM then DataVolume).
  - `worker_init.py` on `vm_lifecycle_activity_queue(KV_CLUSTER)`; requirements + kubernetes
    − httpx/PyYAML; Dockerfile without git.
  - Deleted: `kv_capacity_api.py`, `kv_vm_api.py`, `day1_repo.py`, `placement.py` (moved, 1.1).

### 1.5 Chart and CI

- new `deploy/charts/vm-lifecycle-worker/` on the `cluster-upgrade-worker` model: `kvCluster`
  (render fails without it), `temporal.{host,namespace,tls}`, `config.{headroomBufferPercent,
  vmMacPrefix}`, `vm.*`, no Secret; ClusterRole per call (nodes, pods, namespaces,
  virtualmachineinstances, persistentvolumeclaims: get/list; virtualmachines:
  get/list/create/delete; datavolumes: get/delete); README with config, RBAC, network tables and
  "`kvCluster` = the day1 file name".
- `scripts/sync_platform_charts.sh` + the chart, **hardened** so a destination of the old hub
  shape (no `.image.repository`) is not "owned" (today it would write `null` as repository and
  tag); `tests/test_sync_platform_charts.py`.
- `.github/workflows/build.yml`: the `charts` filter, the render step, `git add`,
  `build-vm-lifecycle-worker`'s `helm-image-path: image`.

### 1.6 Tests

- new `tests/test_kv_placer_workflow.py`: FIFO; ten parallel requests over two 70-core clusters →
  2 + 2 then "no capacity", never past the ceiling; pending added to the reported figures;
  `created` / `failed` / 30-min expiry free the entry; a cluster with no worker is a `no-worker`
  row after 30 s and the next one is tried; the scan stops at the first fit (later clusters not
  read); continue-as-new keeps queue and pending; a request arriving during CAN is not lost.
- rewritten `tests/test_create_vm_workflow.py`: one worker per queue, each omittable; the name
  built from the suffix; a conflict redraws on the same cluster, three exhaust; created/failed
  signalled to the placer; rollback; the placer's "not placed" → `NoKvClusterFitsError`; empty
  day1 → `NoKvClusterError`; an unanswered placement → `KvPlacementUnansweredError`.
- `tests/test_create_vm_replay.py` + new `tests/test_kv_placer_replay.py`: the 7 old goldens
  deleted and new ones recorded in the same step (`create`, `no-capacity`, `no-cluster`,
  `no-kv-worker`, `mac-redraw`, `draws-exhausted`, `rollback`; placer: `two-requests`,
  `continue-as-new`).
- `tests/test_vm_lifecycle_placement.py` reshaped (first-fit, pending, `SKIP_REASONS` mirror);
  new `tests/test_vm_capacity.py` (cordoned/NotReady, terminal pods, label in any namespace, any
  runStrategy, VMI not double-counted, the 1 GiB, paging), `tests/test_vm_spec.py`; rewritten
  `tests/test_vm_lifecycle_limb.py` (fake kube client); `tests/test_vm_lifecycle_day1.py` moved
  to the cluster-lifecycle limb.
- edits: `test_worker_registration.py` (`_WORKERS`; create-vm reaches exactly
  `CLUSTER_LIFECYCLE_ACTIVITY_QUEUE` + `vm_lifecycle_activity_queue`; the placer only the
  latter), `test_contract.py`, `test_error_classification.py`, `test_image_changes.py`,
  `conftest.py`, `test_settings.py`.
- deleted: `kv_agents_simulator.py`, `test_create_vm_e2e.py`, `test_kv_agents_contract.py` + its fixture.

### 1.7 Docs (same change)

`docs/site/vm-lifecycle/create-vm.html` (every section, plus the placer), `nav.js`, README
(layout, charts, create-vm, API, config), `.env.example`, CLAUDE.md §1/§2/§4/§5/§8/§9 (the
create-vm block rewritten with the dated reversals; §5 gains the per-zone placer as the
serialization precedent), `.claude/rules/delivery.md` + the skill's synced-charts rows,
`docs/design/create-vm-placement.md` (corrected for anything that settled differently),
`kubevirt-vm-placement.md`, `kv-agents-api.md`, `kv-placement-server-scan.md` → superseded by it
(the latter rejected 2026-11-17), `docs/lab/create-vm/` → stale. Memory, after approval:
`create-vm-architecture-decisions.md`, `kubevirt-placement-read-path.md`,
`kv-placement-server-scan-proposal.md` (rejected), `MEMORY.md`.

**Gate**: `python3 scripts/check_conventions.py` (0 errors); `UPDATE_REPLAY_HISTORIES=1 …` once
for the two replay files; `.venv/bin/python -m pytest -q`; `helm lint` + `helm template` of the new chart.

---

## 2. redbull-platform (fresh worktree, not pushed)

Delete `gitops/services/vm-lifecycle-worker/app.yaml`, `gitops/charts/kv-capacity/`,
`gitops/charts/kv-vm-api/`; LEAVE `gitops/charts/vm-lifecycle-worker/` (CI's hardened sync
replaces it; removing it first breaks the next tag bump). Update its CLAUDE.md/README. No
`services/` entry for the new chart: each KV cluster gets it through day2.

---

## 3. Verification

1. The gate above, all green.
2. **Lab pass** (one real KV cluster, the worker from source, the brain local): a local day1 with
   a seed folder listing the real cluster plus a second name with no worker; ten separate
   create-vm POSTs → the no-worker cluster skipped in 30 s, the real one filled up to its buffer,
   then "no capacity"; each VM carries the MAC its name says; a forced duplicate MAC redrawn;
   record the HTTP status KubeMacPool answers for a duplicate; record one real history as a golden.

---

## 4. Deploy order (the operator's; nothing here is pushed)

1. Terminate old-shape runs (step 0).
2. Push the redbull-platform cleanup (the hub limb is pruned).
3. Push workflows `main` (CI: brain → cluster-lifecycle limb → chart sync → vm-lifecycle image).
4. Per zone: the seed folder in day1. Per KV cluster, through day2: the `vm-lifecycle-worker`
   chart (`kvCluster` = the day1 file name, Temporal host + CA, storage class — Immediate
   binding, RWX Filesystem — network, buffer, MAC prefix).

## Open points (also in the design page §11)

- **Cross-cluster MAC collisions** are not detected (≈0.7% with 500 VMs, 3% with 1,000, 11% with
  2,000, if those clusters share a network). Accepted as decided; a zone-wide check would read
  every cluster's VMs on each create.
- **Simpler variant offered**: hold the zone lock until the VM object exists (seconds), no
  pending list; creates of one zone then run one after another.
- The VMs' namespace (`inventory` vs the facade's `server-scan-vms`); the day1 seed folders don't
  exist yet; making the VM installable belongs to add-server-to-mce's KubeVirt branch.
