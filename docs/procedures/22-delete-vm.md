# 22 :: Delete VM

**Animation:** [`../animations/22-delete-vm.html`](../animations/22-delete-vm.html)
**Implementation:** [`delete_stray_vm.py`](https://github.com/team-redbull/workflows/blob/main/workflow_domains/vm_lifecycle/delete_stray_vm.py) and the worker's `delete_vm_on_cluster` activity in `team-redbull/workflows`

| | |
|---|---|
| **Trigger** | `remove-server-from-mce`, as its last step, for a VM server (AD36); `create-vm`, for a VM left on a cluster it moved on from (`delete-stray-vm`) or for its own VM when it ends without it |
| **Runs on** | The worker inside the VM's KV cluster, on that cluster's own queue |
| **Finds the VM by** | Its `redbull.io/created-by` label: the id of the `create-vm` run that built it |
| **Deletes** | That VM and its root disk |

---

## 1 :: Purpose

Destroy a VM that has served a cluster, so it is never reused as it is (AD23), and give its CPU and
memory back to its KV cluster: a Halted VM counts as used, both for `create-vm`'s placement and for
the KV Capacity Controller.

---

## 2 :: How the VM is found

A VM's name is drawn inside the `create-vm` run, so the run's id is what identifies it:

| Label | Where | Tells the delete |
|---|---|---|
| `redbull.io/kv-cluster` | The VM's BareMetalHost on the MCE, and the VM | Which KV cluster to ask |
| `redbull.io/created-by` | The VM's BareMetalHost on the MCE, and the VM | Which VM there: the one carrying this run id |

The delete removes only a VM carrying that run id, so a hand-made VM, or another run's VM of the
same name, stays.

---

## 3 :: Process flow

### After a removal (the VM of a server)

| # | Step | Runs on | Action |
|---|---|---|---|
| 1 | Read the labels | MCE queue | `remove-server-from-mce` reads the BareMetalHost's `redbull.io/kv-cluster` and `redbull.io/created-by` in its first step, before it deletes the host |
| 2 | Host gone | MCE queue | metal3 has powered the VM off through kubevirt-redfish, and the BareMetalHost, NMStateConfig and Agent are deleted ([02](02-remove-server-from-mce.md)) |
| 3 | `deleting-vm` | KV cluster's worker | `delete_vm_on_cluster` deletes every VM labelled with that run id, in every namespace, retried until the cluster answers |
| 4 | Room given back | KV cluster | The VM and its root disk are gone: kubevirt-redfish drops the system, server-scan drops the server at its next collection, and the cluster's figures show the room |

### After a create that moved on (`delete-stray-vm`)

| # | Step | Runs on | Action |
|---|---|---|---|
| 1 | Started | `create-vm` | A create failed and the cluster could not be asked whether it landed. `create-vm` moves on and starts `delete-stray-vm` as an abandoned child, on `delete-stray-vm-<cluster>-<run id>` |
| 2 | `deleting` | That cluster's worker | `delete_vm_on_cluster` by the run-id label, in every namespace, retried for as long as the cluster takes to answer |
| 3 | `completed` | | `deleted` true, or false when the create had never landed. A refusal no retry can fix fails the run, naming the label to delete by hand |

`create-vm` also deletes its own VM, by the same label, when the run ends without it (procedure 21,
`removing-vm`).

---

## 4 :: Built today vs. the architecture

`team-redbull/workflows`, `main`, as of 2026-11-26:

| # | Architecture | Built today |
|---|---|---|
| 1 | `remove-server-from-mce` deletes a VM server's VM as its last step | Still to be built: the `deleting-vm` step, and the two labels on the BareMetalHost |
| 2 | `delete-stray-vm` removes a VM left on a cluster `create-vm` moved on from | Built |
| 3 | `create-vm` deletes its own VM when it ends without it | Built |
| 4 | `delete_vm_on_cluster`, on each KV cluster's worker, deletes by the run-id label | Built |

---

## 5 :: Open questions

1. **A VM whose BareMetalHost is already gone.** The labels went with it, so the delete needs
   another way to find the VM (procedure 02, open question 1).
