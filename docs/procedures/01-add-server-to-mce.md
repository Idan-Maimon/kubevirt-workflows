# 01 :: Add Server to MCE

**Interfaces:** [`00-interfaces.md`](00-interfaces.md) — exact endpoints, payloads and resource bodies
**Animation:** [`../animations/01-add-server-to-mce.html`](../animations/01-add-server-to-mce.html)
**Implementation:** [`add_server_to_mce.py`](https://github.com/team-redbull/workflows/blob/main/workflow_domains/server_lifecycle/add_server_to_mce.py) in `team-redbull/workflows`

| | |
|---|---|
| **Trigger** | The Inventory Controller, for each machine a pool needs ([inventory-controller.md](../inventory-controller.md), AD26), or an operator naming servers |
| **Workflow id** | `add-server-to-mce-<mce>_<infraEnv>_<slot>` for a draw from the pool; `add-server-to-mce-<mce>_<server>` for a named server |
| **Runs on** | The MCE's server-lifecycle queue; the segment-lifecycle queue for the VLAN; the `create-vm` child for a VM |
| **Scope** | Every MCE hub, a Customer MCE or a Seed; bare-metal and VM pools alike (AD29) |
| **Adds** | One Agent per run. A request for N machines starts N runs, one per slot |

---

## 1 :: Purpose

Put one machine into one pool. A pool is one InfraEnv, `<flavor>-<mtl|kv<cpu>>-<zone>`, on one MCE
([naming convention](../naming-convention.md)). The run ends when the machine has booted the
discovery image and registered as an Agent carrying the InfraEnv's labels, ready for a NodePool to
claim.

Bare metal and VMs take the same run (AD29). For a VM pool, the run first builds the VM through its
`create-vm` child, then installs exactly that VM. A machine that has served a cluster comes back
through `remove-server-from-mce` (AD34), and this run installs it again from scratch.

---

## 2 :: Inputs

### The request

`POST /workflows/server-lifecycle/add-server-to-mce`

| Field | Required | Notes |
|---|---|---|
| `mce_cluster` | ✅ | The MCE, by cluster name. It selects the worker queue and the inventory VLAN |
| `infra_env` | ✅ | The pool |
| `count` | | A draw from the pool: N runs in parallel, one server each, in free slots. Without `count` or names, one run |
| `server_names` | | Named servers, 1 to 20, one run each. Sent alone, without `count` |
| `namespace` | | Defaults to `inventory` |

A request starts at most 20 runs, across 100 slots per pool.

### Read from the InfraEnv

| What | From |
|---|---|
| Which servers | Its agentLabels: `redbull.io/flavor`, `redbull.io/size`, `redbull.io/site`, `topology.kubernetes.io/zone` |
| Bare metal or VM | `redbull.io/size`: `mtl` for bare metal, `kv<cpu>` for a VM of that size |
| The VLAN | The MCE's inventory segment, from the Segments Manager |

---

## 3 :: Preconditions

- The InfraEnv exists on the MCE with its four labels (naming convention §4).
- The MCE has its inventory segment allocated.
- A worker polls the MCE's server-lifecycle queue.
- For a VM pool, the zone has a KV cluster with room, or a standby
  ([kv-capacity-controller.md](../kv-capacity-controller.md)).

---

## 4 :: Process flow

### 4.1 Who orders, and how many

The Inventory Controller works out each pool's need, `pending + spares − (free + inFlight)`, and
orders that many runs with `count` (inventory-controller.md, R1). Each run takes one free slot, so
the runs in flight are visible in Temporal by their ids. Every run labels what it creates
`redbull.io/installed-by: <workflow id>`; once its Agent exists, the controller counts the machine
once, as a free Agent.

### 4.2 Steps for one run

| # | Phase | Runs on | Action | On failure |
|---|---|---|---|---|
| 1 | `resolving-vlan` | Segment-lifecycle queue | Read the MCE's inventory segment by cluster name | Run fails before any server is drawn |
| 2 | `validating-infraenv` | MCE queue | Check that the InfraEnv exists and that its labels name its servers | Run fails before any server is drawn |
| 3 | `creating-vm` | `create-vm` child | **VM pools only (AD29).** Build the VM, as in §4.3 | Run fails |
| 4 | `acquiring-server` | MCE queue | server-scan allocates one server matching the flavor, size, site and zone, locks it for this run and live-checks it while locked. A VM pool takes the VM its child built, by name | Run fails; the controller's next pass orders again |
| 5 | `selecting-server` | MCE queue | Check the server: a usable name, a known BMC, no BareMetalHost yet. Its two bond NICs come from server-scan | Lock returned, run fails with the reason |
| 6 | `checking-nmstateconfig` | MCE queue | Replace an NMStateConfig under the server's name that differs from this install | |
| 7 | `registering-pxe-boot` | MCE queue | **IPMI only.** Map both bond MACs to the InfraEnv's boot entry, `<mce>/<infraenv>.ipxe`, on the site's PXE VM, before the BareMetalHost exists | Run fails |
| 8 | `creating-nmstateconfig`, `publishing-pxe-boot` | MCE queue | **IPMI only.** Write the NMStateConfig first, wait up to 10 minutes for a discovery image that includes it, then publish its iPXE script as the boot entry | Rolled back, run fails |
| 9 | `creating-secret`, `creating-baremetalhost`, `creating-nmstateconfig` | MCE queue | Write the BMC Secret, the BareMetalHost named after the server, and the NMStateConfig, each labelled `redbull.io/installed-by`. A VM's BareMetalHost points at its Redfish endpoint on kubevirt-redfish | |
| 10 | `awaiting-agent` | MCE queue | Wait up to an hour for the Agent. It registers with the InfraEnv's labels | Rolled back (§5) |
| 11 | `holding-server`, `awaiting-server-scan`, `releasing-lock` | MCE queue | Extend the lock to a day, read server-scan every 5 minutes, and release the lock once server-scan shows the server installed. A lock still held after the day expires, and the run completes | |

### 4.3 A VM pool (AD29)

For an InfraEnv of size `kv<cpu>`, the run starts `create-vm-<mce>_<infraEnv>_<slot>` as a child
before it draws:

1. `create-vm` takes the zone's lock (AD32) and places the VM on the first KV cluster that fits, in
   creation order (AD33).
2. It creates the VM Halted, with `<cpu>` vCPUs, a fixed MAC and the name
   `ocp-<flavor>-kv<cpu>-<site>-<mac>`. kubevirt-redfish exposes it, and server-scan lists it.
3. The parent installs exactly that VM, from step 4 on.

---

## 5 :: Failure handling

### Rollback when no Agent appears

1. Remove the NMStateConfig and the BareMetalHost.
2. IPMI: delete the server's MACs from the site's PXE VM, while the lock is still the run's.
3. Put the server in `MAINTENANCE` in server-scan, so it stays out of every draw until a person
   clears it.
4. Release the lock, and fail with `AgentNeverAppearedError`, naming where the host's own state
   points.

### Cancellation

A cancelled run that has written to the MCE removes the server through a
`remove-server-from-mce-<server>` child.

### Classification

| Condition | Treatment |
|---|---|
| VLAN or InfraEnv missing, InfraEnv labels incomplete | Run fails before any server is drawn |
| No server available | Run fails. The controller's next pass orders again; after repeated hardware failures it probes every 20 minutes |
| Server unusable at selection | Lock returned, run fails with the reason. A new run draws another server |
| No Agent within the hour | Rolled back, server to `MAINTENANCE`, run fails |
| Anything else | Retried with capped backoff |

---

## 6 :: Idempotency

- One running workflow per id: each slot, and each named server, runs once at a time.
- Every create is create-if-absent; an existing resource is success.
- server-scan's lock is held in the run's id, so a retry continues with the same server.
- Publishing a boot entry older than the one already there is success.

---

## 7 :: Outputs

| Field | Notes |
|---|---|
| Per-slot report | `started`, `already_running` or `failed`, with the workflow id |
| Per-run result | The Agent produced, or the reason the run failed |

---

## 8 :: Built today vs. the architecture

`team-redbull/workflows`, `main`, as of 2026-11-25:

| # | Architecture | Built today |
|---|---|---|
| 1 | A VM pool's run builds its VM through a `create-vm` child, then installs that VM (AD29) | `create-vm` runs as its own workflow, and `add-server-to-mce` draws a VM pool from server-scan like any other pool |
| 2 | The draw matches the zone, which server-scan holds from the ACI leaf (naming convention §3) | The draw matches flavor, size and site (`_POOL_LABELS`) |
| 3 | Every run labels its objects `redbull.io/installed-by: <workflow id>` (inventory-controller.md) | Still to be built |
| 4 | `create-vm` places a VM on the first KV cluster that fits, under the zone's lock (AD32, AD33) | `create-vm` ranks the zone's clusters by best-fit bin packing (`placement.py`). The lock and first fit are in the design on branch `docs/create-vm-placement` |
| 5 | VM names `ocp-<flavor>-kv<cpu>-<site>-<mac>` (naming convention §1) | `create-vm` names VMs `ocp-<infraenv>-<6 hex>` and reads the earlier InfraEnv names (`<conf>[-<opt>]-zone-<zone>-<cpu>`), so a draw by flavor, size and site misses its VMs |

---

## 9 :: Open questions

1. **How fast server-scan lists a new VM.** The parent takes the VM its child built right away;
   server-scan has to list it by then, or the child hands the VM over directly.
