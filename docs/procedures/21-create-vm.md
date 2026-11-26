# 21 :: Create VM

**Animation:** [`../animations/21-create-vm.html`](../animations/21-create-vm.html)
**Implementation:** [`create_vm.py`](https://github.com/team-redbull/workflows/blob/main/workflow_domains/vm_lifecycle/create_vm.py) in `team-redbull/workflows`
**Design:** [`create-vm-placement.md`](https://github.com/team-redbull/workflows/blob/main/docs/design/create-vm-placement.md)

| | |
|---|---|
| **Trigger** | `add-server-to-mce` for a VM pool, as its child (AD29) |
| **Workflow id** | `create-vm-<mce>_<infraEnv>_<slot>`, the parent's slot. The run id names the VM's owner |
| **Runs on** | The cluster-lifecycle limb, for day1; the zone's `kv-zone-lock` run; the worker inside each KV cluster, on that cluster's own queue |
| **Builds** | One VirtualMachine, Halted, on the oldest KV cluster of the zone that fits (AD32, AD33) |

---

## 1 :: Purpose

Build one VM for a KubeVirt InfraEnv, `<flavor>-kv<cpu>-<zone>`: `<cpu>` vCPUs and `<cpu> × 7.5` GiB,
Halted, named `ocp-<flavor>-kv<cpu>-<site>-<serial>`. kubevirt-redfish then exposes it as a Redfish
system, server-scan lists it, and `add-server-to-mce` installs it
([01 :: Add Server to MCE](01-add-server-to-mce.md)).

---

## 2 :: Inputs

| From | What |
|---|---|
| The InfraEnv | Flavor, vCPUs, zone; the site is the MCE's |
| The parent | The MCE, the namespace (a kubevirt-redfish chassis namespace), the slot |
| day1 `main` | The zone's KV clusters, oldest first, and the placement buffer |
| Each KV cluster's worker | The cluster's figures: allocatable and requested CPU and memory, per node, with Halted VMs counted |

---

## 3 :: Process flow

| # | Phase | Runs on | Action | On failure |
|---|---|---|---|---|
| 1 | `listing-kv-clusters` | Cluster-lifecycle limb | Read the zone's KV clusters, oldest first, and the placement buffer from day1 `main`, before taking the lock | None usable: `NoKvClusterError` |
| 2 | `awaiting-zone-lock` | `kv-zone-lock` run | Ask the zone's lock and wait for it: one run per site and zone hands the zone to one `create-vm` run at a time | After 30 minutes, `KvZoneLockTimeoutError` |
| 3 | `choosing-kv-cluster` | Each KV cluster's worker | Holding the lock, read each cluster's figures, oldest first, and stop at the first that fits: a node with room for the VM's CPU and memory, and the cluster still within `1 − buffer`. A cluster whose worker answers within 30 seconds is read; the others are skipped | None fits: `NoKvClusterFitsError`, with the reasons |
| 4 | `creating-vm` | The chosen cluster's worker | The worker draws the serial, builds the VirtualMachine and creates it Halted, without a MAC, so KubeMacPool assigns one. Labels: the convention's, `redbull.io/created-by: <run id>` and `redfish-enabled: "true"`. A taken name is drawn again, up to 3 times. The worker creates nothing after the create's deadline: 90 seconds, or the lease's end | See `checking-kv-cluster` |
| 4a | `checking-kv-cluster` | The same worker | **Only when the create failed.** Wait out its deadline, then ask the cluster for the run's VM by its run-id label | A VM is there: the run keeps it. None: on to the next cluster. No answer: on to the next cluster, and a `delete-stray-vm` child removes any VM of the run there once the cluster answers ([22](22-delete-vm.md)) |
| 5 | `releasing-zone-lock` | `kv-zone-lock` run | Release the lock as soon as the VM object exists. The next run's figures already count it, as a stopped VM | |
| 6 | `awaiting-root-disk` | The chosen cluster's worker | Wait until the root disk's DataVolume is Succeeded and bound and the VM admitted, outside the lock and in parallel with other runs | After 10 minutes, `VmRootDiskNotBoundError` |
| 7 | `removing-vm` | The chosen cluster's worker | **Only when the run ends without its VM:** the deadline, a permanent failure, a cancel. Delete the run's own VM, found by its run-id label | |
| 8 | `completed` | | Return the name, MAC, namespace, size and KV cluster | |

### The lease

The lock is held for at most five minutes. The run checks the clock before every read and before
the create; a spent lease is given up and the lock asked for again, and the scan carries on from the
cluster it had reached. The create carries the lease's end, less 45 seconds, and the cluster's worker
enforces it.

### A run is known by its run id

The slot's workflow id is reused by later runs, so the VM's `redbull.io/created-by` label and the
lock's line both carry the run id. A retried create finds its own VM by that label, and a delete
removes only a VM that carries it.

### A cancel rolls back

Waiting, the run leaves the line; holding, it releases the lock; after the create, it deletes its
VM. A terminated run leaves the lock to pass on at the lease's end, and its VM to be found by its
`redbull.io/created-by` label.

---

## 4 :: Outputs

| Field | Notes |
|---|---|
| VM | Name, MAC, namespace, vCPUs, memory, KV cluster |
| Placement table | Each cluster read, and why it did or did not fit |
| `stray_cleanups` | The `delete-stray-vm` children started for clusters that did not answer |

---

## 5 :: Built today vs. the architecture

`team-redbull/workflows`, `main`, as of 2026-11-26:

| # | Architecture | Built today |
|---|---|---|
| 1 | `add-server-to-mce` starts this run as a child for a VM pool (AD29) | Started through its own route, `POST /workflows/vm-lifecycle/create-vm` |
| 2 | The VM carries `redbull.io/kv-cluster` | Still to be built (naming convention, open item 5) |
| 3 | The zone's lock, the oldest cluster that fits, the serial name, KubeMacPool's MAC, `redbull.io/created-by` | Built |

---

## 6 :: Open questions

1. **KubeMacPool on the KV clusters.** The KV clusters run upstream KubeVirt, and KubeMacPool comes
   with OpenShift Virtualization's network add-ons. Each KV cluster needs it, with a MAC range of
   its own, since all of a site's KV clusters put their VMs on the MCE's one inventory VLAN.
