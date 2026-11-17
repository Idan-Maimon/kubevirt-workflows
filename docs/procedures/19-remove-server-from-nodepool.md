# 19 :: Remove Server from NodePool

| | |
|---|---|
| **Trigger** | A tenant (through Wingman) or an SRE: shrink one NodePool by one worker |
| **Two modes** | **Named:** remove this node. **Any:** remove one node, CAPI chooses |
| **Workflow id** | `remove-server-from-nodepool-<cluster>-<nodepool>`, one in flight per NodePool |
| **Runs on** | Hub git limb (the replica count), the MCE's server-lifecycle limb (Machine, Agent), vm-lifecycle limb (destroying a VM) |
| **Writes** | Git: `nodepool[].replicas` minus one. MCE: one annotation on one Machine. Then the release of that one machine |
| **Ends at** | The machine is out of the cluster and out of the MCE, and destroyed (VM) or handed back for reinstall (bare metal) |

> **A shrink is a lower replica count, never a deleted Machine.** Deleting a Machine object
> makes the MachineSet replace it at once, so the node comes back on another machine and the
> next scale-down removes a second one. The only correct order is: mark the Machine, then
> lower the count, then let CAPI delete what it marked.

---

## 1 :: Purpose

Take exactly one worker out of one NodePool and lower that NodePool's desired count by one,
so the cluster keeps one node fewer. The machine released is never handed to another tenant
as it is (AD23).

It is the counterpart of `uninstall-server-from-hc` in the workflows repo, which removes a
node **and lets the NodePool replace it** (the replica count does not change). Use that one to
evict a bad machine. Use this one to make the cluster smaller.

---

## 2 :: Inputs

```json
POST /workflows/server-lifecycle/remove-server-from-nodepool
{
  "mce_cluster": "ocp4-prod-mce-bat-yam-a",
  "cluster":     "ocp4-prod-payments-bat-yam-a",
  "node_name":   "ocp-conf203-zone-a-medium-0a1b2c",
  "nodepool":    null,
  "requested_by": "<from the caller's identity, never from the body>"
}
```

| Field | Type | Required | Notes |
|---|---|---|---|
| `mce_cluster` | str | ✅ | The hub running the cluster's control plane. Canonicalised with its `ocp4-` prefix, as every server-lifecycle route does |
| `cluster` | str | ✅ | The day1 file stem of the hosted cluster |
| `node_name` | str | one of | **Named mode.** The Node to remove, as the hosted cluster names it. The NodePool is derived from it |
| `nodepool` | str | one of | **Any mode.** The NodePool to shrink. CAPI chooses the machine |
| `requested_by` | str | ✅ | Filled by the caller (Wingman) from the signed-in user |

Exactly one of `node_name` and `nodepool`; both or neither is a 422. With `node_name`, a
`nodepool` that is also sent must match the derived one, or 422.

---

## 3 :: Process flow

| # | Phase | Runs on | Action | On failure |
|---|---|---|---|---|
| 1 | `validating` | brain | Inputs as in §2. No other run of this workflow, of `update-nodepool` or of `upgrade-cluster` is open for this cluster and NodePool | Terminal, nothing changed. Name the run in the way |
| 2 | `reading-nodepool` | git + MCE | Read the cluster file at day1 `main`: the NodePool's `replicas`, its `upgradeType`, no `autoScaling`. Read the NodePool and its MachineSet on the MCE: replicas equal Git's, no update in progress | Terminal on autoscaling, a count already being changed, or an update rolling. Retry on read errors |
| 3 | `checking-floor` | brain | `replicas − 1` must not go below the NodePool floor (§6, decision D2) | Terminal: tell the caller the floor, and to delete the NodePool or cluster instead |
| 4 | `resolving-machine` | MCE | **Named:** Node → `spec.providerID` (`agent://<agent>`) → Agent → AgentMachine → Machine → owning MachineSet → NodePool. **Any:** skip | Terminal if the Node is not in this cluster, belongs to another NodePool, or any link is missing or contradictory |
| 5 | `reserving-server` | server-scan | Take the install lock on the server, holder this run, so no install draws it while it leaves | Terminal if another run holds it |
| 6 | `marking-machine` | MCE | **Named:** annotate the Machine `cluster.x-k8s.io/delete-machine: "yes"`. **Any:** skip. Re-read the annotation | Retry. **Nothing after this point is undone**; a re-run resumes |
| 7 | `lowering-replicas` | git | Set `nodepool[<name>].replicas` to the value read in step 2 minus one, by compare-and-set on the file: refuse if it no longer holds the value read. One commit to `main` (decision D1) | Retry on push races; terminal if the value moved, after removing the step 6 annotation |
| 8 | `awaiting-sync` | MCE | ArgoCD synced the Application; the NodePool and its MachineSet show the new count | Bounded wait (decision D4), then fail naming the Application |
| 9 | `identifying-deletion` | MCE | Find the one Machine of this MachineSet that now has a `deletionTimestamp`. **Named:** it must be the marked one. **Any:** record which one CAPI chose, and resolve its Agent and server | Terminal if none appears in time, or if more than one, or (Named) if CAPI chose a different Machine: report both |
| 10 | `awaiting-drain` | MCE | CAPI cordons and drains the Node. Watch the Machine and the Agent | Bounded (20 min from first observed draining), then fail naming the pods that block the drain and the PodDisruptionBudgets involved |
| 11 | `awaiting-unbind` | MCE | The Agent provider's pre-terminate hook unbinds the Agent; the Machine and AgentMachine go | Bounded (1 h), then fail naming the conditions and remaining hooks |
| 12 | `verifying-gone` | MCE + hosted cluster | No AgentMachine, no Machine, no Node for this server, Agent unbound | Bounded (5 min), then fail naming what is still there |
| 13 | `removing-from-mce` | child | Start `remove-server-from-mce` as an awaited child on its own id: power off, BareMetalHost, NMStateConfig, Agent, PXE map | Child's own failure, carried with its type |
| 14 | `destroying-vm` | vm-lifecycle | **VM only.** Delete the VirtualMachine on its KV cluster by name **and** MAC. Already gone is success | Retry. A 409 (someone replaced the VM) is terminal and left alone |
| 15 | `releasing-server` | server-scan | Release this run's install lock | Never fails the run; a refused release is reported |
| 16 | `completed` | — | Report: mode, the Machine and server removed, the NodePool's new count, the commit | |

### What the two modes hand to CAPI

```
Named:  annotate one Machine  ->  replicas - 1  ->  CAPI deletes the annotated Machine
Any:    replicas - 1          ->  CAPI deletes: an unhealthy Machine first, else one at random
```

The MachineSet's delete policy is `Random` by default. It puts Machines carrying the
`delete-machine` annotation and unhealthy Machines first, then picks at random. **Cordoning a
node does not influence the choice**; only the annotation does. In Any mode, an unhealthy
node will be chosen before a healthy one, which is usually what you want.

---

## 4 :: Steps that are easy to get wrong

**Step 6 before step 7, always.** If replicas drop first, CAPI may choose a different Machine
before the annotation lands, and the named node stays.

**Never delete the Machine, the Node or the Agent to start this.** Deleting the Machine makes
the MachineSet create a replacement, and the following replica drop removes a second node.
Deleting the Node or the Agent breaks the chain CAPI and the Agent provider use to drain and
unbind.

**Verify the chosen Machine (step 9).** In Named mode, an unhealthy Machine in the same
MachineSet competes with the annotated one. If CAPI removed the wrong Machine, the cluster
still shrank by one, but the named node is still there: report it, do not try to correct it
by deleting anything.

**Read the replica count once and write it by compare-and-set (steps 2 and 7).** Two
concurrent requests computing `current − 1` from the same read would remove one node, not
two, and leave an annotation behind. The workflow id serialises requests for one NodePool;
the compare-and-set catches a change made by anything else, a person's edit or Wingman's.

**Remove the annotation if step 7 fails terminally.** An annotation left on a Machine with no
replica drop makes that Machine the first choice of the next, unrelated scale-down.

**Follow the Machine CAPI deleted, not the one you expected (steps 9 to 15).** Everything after
the commit acts on the machine identified in step 9.

---

## 5 :: The release (AD23)

A worker that ran a tenant's workloads is never put back in the pool as it is.

| Machine | What happens | Who refills the pool |
|---|---|---|
| **VM** | Taken out of the MCE (step 13), then the VirtualMachine is deleted (step 14) | herzi sees the pool below target and orders a new VM; it is built from the base image |
| **Bare metal** | Taken out of the MCE (step 13). It returns to server-scan as available and is reinstalled from scratch by the next `add-server-to-mce` that draws it | herzi, the same way |

The cluster's demand drops by one, so herzi's target for that pool drops too. Because herzi
only adds (AD26), nothing is removed from the pool as a result.

---

## 6 :: Decisions needed before this is built

| # | Decision | Recommendation |
|---|---|---|
| D1 | **Commit straight to `main`, or open a merge request and wait for a person to merge.** `upgrade-cluster` commits to `main`; `provision-cluster` waits for a merge | Commit to `main`. The tenant's request through Wingman is the approval, and SC1.1 says a routine change needs no conversation with the platform team. With a merge request, steps 6 to 7 can sit for days with the Machine annotated |
| D2 | **The NodePool floor.** Procedure 03 requires at least three workers per zone at creation | One per NodePool, so a zone never disappears from a cluster by shrinking. Removing the last worker of a zone is a NodePool deletion, not a shrink |
| D3 | **Even spread.** Procedure 04 spreads a worker type's total evenly across zones. This workflow shrinks one zone, and the next `update-nodepool` would rebalance it | Accept the imbalance, and have `update-nodepool` rebalance only when it changes the total |
| D4 | **ArgoCD sync.** In production the cluster Applications may not auto-sync (unverified) | Bounded wait of 30 min, then fail asking for a sync. Verify on a live MCE |
| D5 | **Wiping bare metal.** AD23 says a bare-metal worker is wiped before reuse. Reinstalling overwrites the install disk only; other disks keep their data. No wipe step exists in any workflow | A wipe step in `remove-server-from-mce` for bare metal, or a decision that reinstall is enough |

---

## 7 :: Reuse, not reimplementation

Most of the machinery already exists in `team-redbull/workflows`. Build on it.

| Need | Already in the workflows repo |
|---|---|
| Node → Agent → AgentMachine → Machine → HostedCluster resolution, including broken chains | `uninstall-server-from-hc`, `inspect_bound_host`, `hosted_resources.py` |
| Watching drain and unbind, with their timeouts and error types | `uninstall-server-from-hc`, phases `awaiting-machine-deletion`, `verifying-agentmachine`, `verifying-node`, `verifying-agent` |
| Taking the server out of the MCE, PXE cleanup included | `remove-server-from-mce`, as an awaited child |
| The install lock | `reserve_server` / `release_server` |
| Editing one key of the day1 cluster file by compare-and-set | The upgrade-gitops limb's commit path (`Day1FileChangedError`, `Day1ChangeRejectedError`) |
| Deleting a VM by name and MAC | vm-lifecycle `delete_vm_on_cluster` |

**New in this workflow:** the `delete-machine` annotation, the replica commit, identifying the
Machine CAPI chose, and destroying the VM afterwards.

**Access it needs beyond `uninstall-server-from-hc`'s:** `patch` on `machines` in the control-plane
namespace (the annotation). It needs no write on NodePools or MachineSets: the count changes
only through Git.

---

## 8 :: Idempotency and re-runs

- The workflow id is the NodePool, so requests for one NodePool run one at a time, and a
  second while one runs is a 409.
- Before step 6 nothing has changed; a failure is clean.
- From step 6 on, nothing is undone. A re-run of the same id finds the annotation already
  there, the count already lowered (the compare-and-set sees its own value and treats it as
  done), and resumes at the first step whose outcome is not yet true.
- Every wait is bounded and fails naming what it waited for.

---

## 9 :: Progress and result

`progress` query: `phase`, `mode`, `nodepool`, `replicas_before`, `replicas_after`,
`machine` (the one marked or chosen), `server`, `kind` (`vm` or `metal`), `commit`, `waiting_for`.

Result: the same fields plus `removed_from_mce`, `vm_destroyed`, `lock_released`, and in Named
mode `chosen_matches_requested`.

Wingman shows the run on the cluster's Nodes tab, as it does for `uninstall-server-from-hc`.
