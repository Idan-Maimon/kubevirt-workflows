# 02 :: Remove Server from MCE

**Interfaces:** [`00-interfaces.md`](00-interfaces.md) — exact endpoints, payloads and resource bodies
**Animation:** [`../animations/02-remove-server-from-mce.html`](../animations/02-remove-server-from-mce.html)
**Implementation:** [`remove_server_from_mce.py`](https://github.com/team-redbull/workflows/blob/main/workflow_domains/server_lifecycle/remove_server_from_mce.py) in `team-redbull/workflows`

| | |
|---|---|
| **Trigger** | The Inventory Controller, collecting a used Agent that is free again (AD34); `uninstall-server-from-hc`, as its child; a cancelled `add-server-to-mce`, rolling back; an operator |
| **Workflow id** | `remove-server-from-mce-<server>`: one per server, so a repeated start returns 409 |
| **Runs on** | The MCE's server-lifecycle queue; for a VM, the queue of the worker inside its KV cluster |
| **Scope** | Every MCE hub; bare metal and VMs alike |
| **Removes** | One server's BareMetalHost, NMStateConfig, Agent and PXE entries; for a VM, the VM too |

---

## 1 :: Purpose

Take one server out of an MCE's inventory, so a machine that has served a cluster is never reused
as it is (AD23). Bare metal goes back to server-scan, and the next install draws it and installs it
from scratch. A VM is deleted as soon as metal3 has let its BareMetalHost go, before the Agent
([22 :: Delete VM](22-delete-vm.md)), so one start covers both (AD36).

The run covers a server that is inventory only. An Agent still bound to a cluster refuses the run
before anything changes.

---

## 2 :: Inputs

`POST /workflows/server-lifecycle/remove-server-from-mce`

| Field | Required | Notes |
|---|---|---|
| `server_name` | ✅ | The server, as server-scan and the BareMetalHost name it |
| `mce_cluster` | ✅ | The MCE, by cluster name. It selects the worker queue and the PXE VM of the MCE's site |

| Caller | When |
|---|---|
| Inventory Controller (R3) | A used Agent, labelled `redbull.io/claimed` or showing an unbind, is free again ([inventory-controller.md](../inventory-controller.md)) |
| `uninstall-server-from-hc` | As its child, once the node has left the hosted cluster |
| `add-server-to-mce` | A cancelled run that has already written to the MCE |
| Operator | By name |

---

## 3 :: Process flow

| # | Phase | Runs on | Action | On failure |
|---|---|---|---|---|
| 1 | `inspecting` | MCE queue | Read the BareMetalHost, the NMStateConfig and the Agents matched to the host, by BMAC's `bmh` label or by any MAC of the machine, from either resource or from server-scan. For a VM, read the BareMetalHost's `redbull.io/kv-cluster` and `redbull.io/created-by` now, before the host is deleted | Nothing found at all: success, nothing to do |
| 2 | Refusal | MCE queue | An Agent bound to a cluster (`spec.clusterDeploymentName`) ends the run with `AgentBoundToClusterError` | Nothing has changed |
| 3 | `removing-host` | MCE queue | Delete the NMStateConfig and the BareMetalHost, re-checking first that no Agent is bound. metal3 deprovisions the deleted host: it powers the host off through its BMC (a VM through kubevirt-redfish), deletes its Ironic node, and only then releases its finalizer | |
| 4 | `awaiting-bmh-deletion` | MCE queue | Read the BareMetalHost every 15 seconds until metal3 releases it, then delete its BMC Secret | After 15 minutes, `BmhDeletionTimeoutError` with the Agent untouched; usually a BMC that is not answering |
| 5 | `deleting-vm` | KV cluster's worker | **VMs only.** Delete the VM on the KV cluster named by `redbull.io/kv-cluster`, found by its `redbull.io/created-by` label ([22](22-delete-vm.md)) | Retried until the cluster answers. A failure no retry can fix does not stop the removal: steps 6 and 7 still run, and the run then fails naming the VM's KV cluster and run id |
| 6 | `removing-agent`, `removing-pxe-boot` | MCE queue | Delete the Agent, re-checked as unbound right before. Clear every MAC of the host from the PXE VM of the MCE's site, keeping any MAC that points at another MCE's boot entry | The PXE cleanup is best effort: a failure is reported in `pxe_failed`, and the removal completes |
| 7 | `verifying` | MCE queue | Inspect again until no Agent, BareMetalHost or NMStateConfig is left | `ServerStillPresentError`, naming what is left |

### Why the VM goes right after its host

The VM is deleted as soon as metal3 has let its BareMetalHost go, not after the rest of the
removal:

- **Not before.** metal3 releases a host only after powering it off through its BMC, and a VM's
  BMC is its own kubevirt-redfish. A VM deleted under a live BareMetalHost would leave metal3
  unable to finish, and would leave the boot ISO disk kubevirt-redfish made for it, which it deletes
  only when metal3 ejects the media.
- **Not later.** Once the BareMetalHost is gone, its two labels are gone too: the only record of
  which KV cluster holds the VM, and which VM there, is the running removal itself. Every step
  between "host gone" and "VM gone" is a step where a failure or a terminate leaves a Halted VM
  that a re-run can no longer find (open question 1). Deleting it right away leaves only the
  delete's own failure or a terminate.
- **And it settles the host.** A deleted VM cannot boot again and register a fresh Agent while the
  Agent and PXE entries are being cleared.

For the same reason a failure to delete the VM does not stop the removal: the Agent and the PXE
entries are cleared and checked as for any server, and the run fails at the end, naming the KV
cluster and the run id, so a person can finish the VM's delete.

### Why the Agent goes last

The host is still running the discovery image, and its agent registers again within a minute once
its Agent disappears. So the host is powered off first. metal3's own delete does that: a
BareMetalHost that is really gone means a host powered off and an Ironic node deleted.

### Why metal3 is left to finish

The run deletes the BareMetalHost and waits, with no separate power-off and no finalizer dropped.
metal3 ignores `spec.online` while a deploy is in progress, and a finalizer dropped early cut metal3
off mid-way and left an orphaned Ironic node forcing a stale power state every minute.

### The lock stays with its holder

The run ends at the check, leaving server-scan's install lock to whoever holds it.
`uninstall-server-from-hc` releases its own after this run completes, a cancelled
`add-server-to-mce` releases its own in its rollback, and a removal started alone leaves any lock to
its TTL.

---

## 4 :: Idempotency

- One running workflow per server: a repeated start returns 409.
- A run that finds nothing succeeds, so a re-run after a partial removal finishes the job.
- Every delete is re-checked against a bound Agent right before it is made.
- A VM is deleted only when it carries the `redbull.io/created-by` label read from its
  BareMetalHost, so a hand-made VM, or another run's VM of the same name, stays.

---

## 5 :: Outputs

| Field | Notes |
|---|---|
| Removed | What was deleted: BareMetalHost, NMStateConfig, Secret, Agents |
| `pxe_kept`, `pxe_failed` | MACs left on the PXE VM because they belong to another MCE, and cleanups that failed |
| VM | For a VM: the KV cluster and the VM deleted |

---

## 6 :: Built today vs. the architecture

`team-redbull/workflows`, `main`, as of 2026-11-26:

| # | Architecture | Built today |
|---|---|---|
| 1 | The Inventory Controller starts this run for every used Agent that is free again (AD34) | herzi starts only `add-server-to-mce`; the collector is a proposal (herzi PR #1) |
| 2 | For a VM, the run deletes the VM right after metal3 releases its BareMetalHost (AD36) | Still to be built. Today the VM stays on its KV cluster, Halted: counted against its cluster's capacity, and still offered by server-scan while it keeps its `redfish-enabled` label |
| 3 | A VM's BareMetalHost carries `redbull.io/kv-cluster` and `redbull.io/created-by` | Still to be built (naming convention, open item 5) |
| 4 | Phases 1 to 6, as above | Built |

---

## 7 :: Open questions

1. **A VM whose BareMetalHost is already gone.** Its two labels went with it, so the run needs
   another way to find the VM: by name across the site's KV clusters, or from server-scan.
2. **Wiping bare metal.** Reinstalling overwrites the install disk only; other disks keep their
   data (procedure 19, D5).
