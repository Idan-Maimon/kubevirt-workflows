# 19 :: Remove Server from NodePool

**Animation:** [`../animations/19-remove-server-from-nodepool.html`](../animations/19-remove-server-from-nodepool.html)

| | |
|---|---|
| **Trigger** | A tenant (through Wingman) or an SRE: shrink one NodePool by one worker |
| **Two modes** | **Named:** remove this node. **Any:** remove one node, the NodePool's policy or CAPI chooses |
| **Built as** | A scale-down of `update-nodepool` (`team-redbull/workflows`, on `main`), **not a separate workflow** |
| **Workflow id** | `update-nodepool-<cluster>`, one in flight per cluster |
| **Ends at** | The marked Machine deleting. The Inventory Controller then collects the machine: a VM is deleted, and bare metal goes back to server-scan for a full reinstall (AD34, AD36) |

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

### 3.2 The Inventory Controller collects the machine (AD34)

The run ends once the marked Machine is deleting, and leaves the machine to the Inventory
Controller:

| Step | Who | Action |
|---|---|---|
| Drain and unbind | CAPI and the Agent provider | The Node drains, the Machine and AgentMachine go, and the Agent comes free |
| Held out of the pool | Every NodePool | The Agent has carried `redbull.io/claimed` since it was bound (R2), and every NodePool excludes the label |
| Collect | The Inventory Controller | It starts `remove-server-from-mce-<server>` for the used Agent (R3) |
| VM | `remove-server-from-mce` | The VM is deleted as the run's last step, by its run-id label (AD36) |
| Bare metal | server-scan | Reinstalled from scratch by the next install that draws it |

The cluster's run slot is free as soon as the Machine is deleting, so the cluster takes its next
change while the machine is still being collected. The Inventory Controller orders nothing back,
since no worker is waiting for an Agent (AD26).

#### Alerts on what follows a NodePool change

| Alert | Fires when | Usually means |
|---|---|---|
| Machine stuck deleting | A Machine has been deleting for more than 30 minutes | A drain blocked by a PodDisruptionBudget, or a stuck finalizer |
| NodePool not converged | A NodePool's ready nodes differ from its replicas for more than 60 minutes | Something in the scale is stuck |
| Worker waiting for an Agent | An AgentMachine has shown `NoSuitableAgents` for more than 60 minutes | Supply is short: herzi or server-scan is out of hardware |
| Used Agent not collected | herzi's own alert (R3) | Collection is stuck |

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
