# Assessment: `update-nodepool` and the server-lifecycle domain

| | |
|---|---|
| **Branch assessed** | `team-redbull/workflows` → `feat/update-nodepool` at `43c8ee2` (2026-11-16) |
| **Assessed against** | `kubevirt-workflows/docs/architecture.md` (AD21–AD31) and the platform's capacity design |
| **Scope** | The server-lifecycle domain only: `update-nodepool`, `scale-up-nodepool`, `scale-down-nodepool`, `add-server-to-mce`, `uninstall-server-from-hc`, the worker's activities and chart |
| **Out of scope** | The branch's changes to other domains: `activities/cluster_upgrade/upgrade_state.py`, `shared/models/cluster_upgrade.py`, `activities/upgrade_gitops/day1_repo.py` and `day1_values.py`, `shared/upgrade_layout.py` |
| **Method** | Code and design notes read. **Tests were not run**, so test status is unverified |

---

## Summary

The engineering is strong, and in several places goes further than our own design:

- Machines are marked before the commit, the marks come off only if the commit fails, and the run checks that the marked Machines are the ones CAPI deletes.
- The Machine order is chosen so CAPI's ranking makes the same choice in every CAPI version HyperShift ships.
- Totals are absolute, the commit is compare-and-set, day1 and the live cluster are checked against each other both ways, and the run refuses during an upgrade or a rollout.
- A cancelled install rolls back, and every uninstall ends in `remove-server-from-mce`.

Four issues need attention before this is built on:

1. A scale-down hands used workers back to the pool as they are (AD23).
2. A named node cannot be removed.
3. A "kind" is a name prefix, which does not fit the InfraEnv naming.
4. Install runs now stay open after the Agent exists, which skews herzi's count. A label on the Agent naming the run fixes it with a small change in each repo.

---

## Issues and suggested fixes

Ordered by severity.

| # | Severity | Where the defect is | Finding | In scope? | Where the fix goes | Suggested fix (approach) |
|---|---|---|---|---|---|---|
| 1 | **Critical** | `scale_down_nodepool.py`, and CLAUDE.md "the servers that leave stay in the MCE" | **Scale-down hands used workers back to the pool as they are.** The released Agent goes back to its InfraEnv and can be claimed by another tenant with the previous tenant's disk, which breaks AD23. (Decided 2026-11-03; AD23 was published 2026-11-15.) | Yes | server-lifecycle: `scale-down-nodepool` | After the commit, follow each Machine CAPI deletes until its Agent is unbound, then release it by kind. **VM:** take it out of the MCE with `remove-server-from-mce` as an awaited child, then delete the VM by name and MAC. **Bare metal:** `remove-server-from-mce`, and it returns to server-scan for a full reinstall. Treat "done" as "released", not "replicas set". Reuse `uninstall-server-from-hc`'s verification steps (Machine gone, Node gone, Agent unbound) instead of writing new ones. Until the bare-metal wipe decision is made, record that only reinstall applies. |
| 2 | **High** | `UpdateNodePoolRequest` in `router.py` | **No way to remove a named node.** The request takes `infra_env_kind` or `nodepool` plus `replicas`; which server leaves comes only from the NodePool's policy or CAPI's random pick. | Yes | server-lifecycle: `update-nodepool` and `scale-down-nodepool` | Add an optional `node_name`, valid only with `nodepool` and `replicas = current − 1`. Trace the node to its Machine (Node → providerID → Agent → AgentMachine → Machine), check it belongs to that NodePool's MachineSet, and make it the chosen Machine in place of the policy's choice. **Refuse if the MachineSet holds a CAPI-unhealthy Machine:** CAPI 4.18 ties marked and unhealthy Machines and breaks the tie by name, so the named node isn't guaranteed to go. Report the unhealthy Machine and leave the decision to the caller. Report `chosen_matches_requested` in the result, which `ScaleDownWrongMachineError` already guards. |
| 3 | **High** | `nodepool_replicas.belongs_to_kind` | **A "kind" is an InfraEnv name prefix, which doesn't fit AD21's naming.** The zone sits mid-name (`conf203-zone-a-medium`), so no prefix means "this size across all zones". `conf203` sweeps in `-large` and `conf203-infiniband-*`, and the run then balances replicas across different VM sizes. | Yes | server-lifecycle, plus a naming decision in the architecture | Define a kind as the InfraEnv name with only the zone segment removed: server type, variant and size must all match. Parse names with the one shared parser (`shared/infraenv_names.py`) instead of string-prefix matching, and refuse names it can't parse. The InfraEnv naming has to be settled first, since code, chart and §9 currently differ. Until then, refuse a kind that matches more than one size or variant. |
| 9 | **High** | `add_server_to_mce.py`, phase `awaiting-server-scan` | **Install runs stay open after the Agent exists** (15–30 min, up to a day). herzi counts open runs as machines on their way, so it under-orders, uses up `maxOpenRunsPerPool` (15), and raises false stuck-run alerts. herzi's design accepted this double count only because it used to last seconds (`herzi-design.md`, L10). | Yes | server-lifecycle and herzi (a small change in each) | **Label the Agent with the run that installed it, and have herzi drop that run.** (1) `add-server-to-mce`: when the Agent appears, label it `redbull.io/installed-by: <workflow-id>`, behind `workflow.patched(...)` so runs in flight replay unchanged. The worker can already patch Agents (`uninstall-server-from-hc` labels them the same way). The label stays until the Agent is deleted. (2) herzi: while building a pool's counts, collect the `installed-by` values from its Agents and remove those run ids from `open`. The run then counts once, as the Agent. Apply the same filter to the open-runs limit and the stuck-run alert. This fixes all three symptoms. A label left behind by a failed or terminated run names a closed run, so it matches nothing and does no harm. Don't instead make herzi ignore the labelled Agent: that fixes only the double count, still uses up the open-runs limit and raises the false alerts, and a leftover label would hide a real Agent for good. A gap of one poll remains between the Agent registering and being labelled, which herzi already accepts (L10). |
| 4 | Medium | `UpdateNodePoolRequest.replicas`, `Field(ge=0)` | **No floor.** A NodePool can be set to 0, against procedure 04 (at least 3 at creation) and procedure 19 (at least 1 per NodePool). | Yes | server-lifecycle; the value is the architect's decision | Take the floor from one configured policy value rather than hardcoding it, and refuse below it with a message saying what to do instead (delete the NodePool or the cluster). Check it in both modes: the per-kind total and a single NodePool. |
| 5 | Medium | `update_nodepool.py` (no `autoScaling` handling) | **No autoscaling guard.** Writing `replicas` on an autoscaling NodePool fights the autoscaler. | Yes | server-lifecycle | In the read phase, refuse any NodePool whose live spec or day1 entry has autoscaling. Name it in the error and change nothing. If autoscaling will never be used, write that down and keep the refusal as a safety net. |
| 6 | Medium | server-lifecycle worker: `DAY1_GIT_TOKEN` on every MCE | **Day1 write access is now on every MCE.** The code allows only replica edits, but the token can push anything, so compromising one MCE reaches the fleet's desired state. | Yes | server-lifecycle chart, and token issuing | Give the worker a token scoped to the day1 repo only, with no write to the sig repos or anything else, separate from the group token. Better: keep git writes on a hub worker and have the MCE worker only read the cluster and mark Machines. Either way, record the credential's reach in the architecture. |
| 7 | Medium | `redbull.io/scale-down-policy` annotation | **The air-gapped GitLab chart doesn't render the policy annotation**, so production NodePools have no policy and the scale-down is always random. | Yes (depends on another repo) | hostedclusters-setup chart, GitLab copy | Port the GitHub chart change (`feat/nodepool-annotations`) to the GitLab copy and verify it renders on one production NodePool before relying on policies. Until then, have the run say clearly in its result that no policy was found and CAPI chose at random. |
| 11 | Medium | `uninstall_server_from_hc.py`, the `redbull.io/uninstalling` label | **The label does nothing until NodePools exclude it,** and the chart doesn't render that selector yet. Adding it changes the NodePool template hash: a Replace NodePool rolls every node, an InPlace one doesn't. | Yes (depends on another repo) | hostedclusters-setup chart | Add the `DoesNotExist` selector expression to the chart for all NodePools. Before rolling it out, confirm every tenant NodePool is `InPlace` (AD24), so the hash change doesn't trigger a full roll. Roll out per MCE and check one NodePool first. |
| 12 | Medium | `deploy/charts/server-lifecycle-worker/` (RBAC) | **The MCE worker's permissions grew:** `nodepools` get/list, `machines` patch, ArgoCD `applications` patch, the day1 token, plus the existing cluster-wide Secret read. Together it can steer every hosted cluster on the hub. | Yes | server-lifecycle chart, plus a risk entry in the architecture | Keep each grant as narrow as the call needs: Applications limited to the hosted-cluster AppSet's, Machines limited to control-plane namespaces where possible. List the worker's full reach in one table in the chart README. Add a risk to the architecture (§6) for "MCE worker compromise". |
| 8 | Low | Our `architecture.md` §9 and procedure 04 | **Workflow id mismatch:** the code uses `update-nodepool-<cluster>`, our docs say `update-nodepool-<cluster>-<node-type>`. The code is right: one day1 file and one ArgoCD Application per cluster. | Ours | `kubevirt-workflows` | Update §9 and procedure 04 to `update-nodepool-<cluster>`, with the reason. No code change. |
| 10 | Note | herzi `claimable` | **Agents marked `redbull.io/uninstalling` still count as spare** in herzi, so it under-orders during an uninstall. The server-lifecycle code is correct; the effect lands in herzi. | No (herzi) | herzi | Exclude Agents carrying the label from `claimable` and count them separately, like `settling`. Raise it with the herzi owner as a dependency of finding 11. |

---

## Suggested order

1. **First:** the cross-tenant exposure, finding 1.
2. **Next:** the two design issues and herzi's count, findings 2, 3 and 9. Finding 3 needs the InfraEnv naming decision.
3. **Before production:** the guards and access issues, findings 4 to 7, 11 and 12.
4. **On the architecture side:** finding 8, plus decisions on the floor (finding 4) and the bare-metal wipe (finding 1).
