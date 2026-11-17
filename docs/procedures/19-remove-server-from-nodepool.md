# 19 :: Remove Server from NodePool

| | |
|---|---|
| **Trigger** | A tenant (through Wingman) or an SRE: shrink one NodePool by one worker |
| **Two modes** | **Named:** remove this node. **Any:** remove one node, the NodePool's policy or CAPI chooses |
| **Built as** | A scale-down of `update-nodepool` (`team-redbull/workflows`, branch `feat/update-nodepool`), **not a separate workflow** |
| **Workflow id** | `update-nodepool-<cluster>`, one in flight per cluster |
| **Ends at** | The machine is out of the cluster and out of the MCE, and destroyed (VM) or handed back for reinstall (bare metal) |

> **A shrink is a lower replica count, never a deleted Machine.** Deleting a Machine object
> makes the MachineSet replace it at once, so the node comes back on another machine and the
> next scale-down removes a second one. The only correct order is: mark the Machine, then
> lower the count, then let CAPI delete what it marked.

---

## 1 :: Purpose

Take exactly one worker out of one NodePool and lower that NodePool's desired count by one.
The machine released is never handed to another tenant as it is (AD23).

It is the counterpart of `uninstall-server-from-hc`, which removes a node **and lets the NodePool
replace it**, leaving the count unchanged. Use that one to evict a bad machine. Use this one to
make the cluster smaller.

---

## 2 :: What `update-nodepool` already does

Its scale-down, `scale-down-nodepool`, already follows the order above:

| Step | Already built |
|---|---|
| Read | day1 `main` and the live NodePools, which must agree both ways; refuses during an `upgrade-cluster` run or a rollout |
| Choose | The NodePool's own `redbull.io/scale-down-policy` (`fewest-pods`, `least-requested`, `least-utilized`), or no policy and CAPI picks at random |
| Mark | `cluster.x-k8s.io/delete-machine` on the chosen Machines, read back, **before** the commit. CAPI-unhealthy Machines are ordered first, so CAPI's ranking matches the choice in every CAPI version |
| Commit | `nodepool[].replicas` on day1 `main`, compare-and-set on the file. A refused commit takes the marks off; a landed one never does |
| Apply | ArgoCD synced to exactly that commit, then the NodePools read back |
| Verify | The marked Machines are the ones deleting; an unmarked one deleting fails the run |

Calling it with `nodepool` and `replicas` = current − 1 is the **Any** mode, as far as the
replica change goes.

---

## 3 :: What has to be added

Each item matches a finding in [`../review/update-nodepool-assessment.md`](../review/update-nodepool-assessment.md).

### 3.1 Named mode (finding 2)

Add an optional `node_name` to the request, valid only with `nodepool` and
`replicas` = current − 1.

1. Trace the node to its Machine: Node → `spec.providerID` (`agent://<agent>`) → Agent →
   AgentMachine → Machine. It must belong to the requested NodePool's MachineSet.
2. Make that Machine the chosen one, in place of the policy's choice, then mark, commit, apply and
   verify as today.
3. **Refuse if the MachineSet holds a CAPI-unhealthy Machine.** CAPI 4.18 ties a marked Machine
   with an unhealthy one and breaks the tie by name, so the named node is not guaranteed to go.
   Report the unhealthy Machine and let the caller decide.
4. Report `chosen_matches_requested` in the result.

### 3.2 Release the machine per AD23 (finding 1)

Today the run ends once the NodePool shows the new count, and the released machine returns to
its InfraEnv as a free Agent. Instead, the run follows the Machine CAPI deleted to the end:

| Step | Action |
|---|---|
| Await drain and unbind | The Machine and AgentMachine gone, the Node gone, the Agent unbound. Bounded waits that name what blocks them |
| Remove from the MCE | `remove-server-from-mce` as an awaited child: power off, BareMetalHost, NMStateConfig, Agent, PXE map |
| Destroy a VM | Delete the VirtualMachine on its KV cluster by name **and** MAC |
| Bare metal | Returns to server-scan and is reinstalled from scratch by the next install that draws it |

Reuse `uninstall-server-from-hc`'s verification steps for the waits rather than writing new ones.
The Inventory Controller sees the pool's demand drop and orders nothing back (AD26).

### 3.3 Guards (findings 4 and 5)

- **Floor:** refuse a count below the NodePool floor, taken from one configured policy value.
- **Autoscaling:** refuse a NodePool that autoscales.

---

## 4 :: Decisions

| # | Decision | State |
|---|---|---|
| D1 | Commit to `main` or wait for a merge request | **Settled** by `update-nodepool`: it commits to `main` |
| D2 | The NodePool floor | **Open.** Recommendation: one per NodePool, so a zone never disappears from a cluster by shrinking |
| D3 | Zone balance after shrinking one NodePool | **Settled** by `update-nodepool`: a NodePool set by name has no balance rule, and a later change by kind is refused until the NodePools are evened out again |
| D4 | ArgoCD sync | **Settled** by `update-nodepool`: it syncs to the exact commit itself |
| D5 | Wiping bare metal. Reinstalling overwrites the install disk only; other disks keep their data | **Open.** A wipe step in `remove-server-from-mce` for bare metal, or a decision that reinstall is enough |
