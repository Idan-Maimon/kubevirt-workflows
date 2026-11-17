# Assessment: create-vm placement design and plan

| | |
|---|---|
| **Documents assessed** | [`create-vm-placement.md`](create-vm-placement.md) (the design) and [`i-want-to-make-optimized-shamir.md`](i-want-to-make-optimized-shamir.md) (the implementation plan), both dated 2026-11-17 |
| **Assessed against** | `docs/architecture.md` (AD21–AD31), `docs/vm-placement.md`, `docs/kv-capacity-controller.md`, `docs/inventory-controller.md` |
| **Architect's direction** | **create-vm runs as a child workflow of the server-lifecycle domain**, started by `add-server-to-mce` when the requested InfraEnv is a VM pool rather than bare metal |
| **Status of the plan** | Not implemented; awaiting approval |

---

## Summary

The design solves the two problems it sets out to solve, and improves on what is built today:

- **One placement at a time per zone**, which AD32 requires. Parallel creates no longer pile onto
  one cluster.
- **A worker inside each KV cluster** that only dials out. The two HTTP agents, their Routes, the
  fleet tokens and the repository's only unverified-TLS exception all go, and the hub holds no
  credential for any KV cluster.
- **First-fit over clusters in name order.** With KV clusters named in creation order, this fills
  the oldest cluster first, which is exactly how AD28's active and standby clusters are meant to
  behave. AD33 now adopts it.

Five things need changing before it is built:

1. **It stands alone.** create-vm is its own route, and wiring it into `add-server-to-mce` is
   explicitly left out (§11.7). The architect's direction is that it is a child of
   `add-server-to-mce` for VM pools.
2. **MAC addresses can collide across KV clusters** (about 3% at 1,000 VMs, 11% at 2,000), which
   breaks the boot of both machines. The design already has the tool to prevent it.
3. **The buffer is a per-cluster setting defaulting to 30%**, where AD31 says one shared value,
   15%, read by placement and the KV Capacity Controller alike.
4. **The pending list adds a long-lived workflow with remembered state.** The design's own
   "simpler variant" meets AD32 with none of it.
5. **A cluster listed in day1 but without its worker** costs every placement in the zone 30
   seconds. Under AD28 a standby cluster is always being built, so this is routine, not rare.

---

## Issues and suggested fixes

Ordered by severity.

| # | Severity | Where the defect is | Finding | In scope? | Where the fix goes | Suggested fix (approach) |
|---|---|---|---|---|---|---|
| 1 | **High** | Design §11.7; plan "Context" and §1.2 | **create-vm is not a child of `add-server-to-mce`.** It is its own route (`POST /workflows/vm-lifecycle/create-vm`), and making the VM installable is left to "add-server-to-mce's KubeVirt branch". So nothing turns herzi's order for a VM pool into a VM: herzi only calls `add-server-to-mce`, which draws machines server-scan already lists, and server-scan does not offer a Halted VM. | Yes | server-lifecycle (`add-server-to-mce`) and vm-lifecycle (`create-vm`) | **When the InfraEnv is a VM pool, `add-server-to-mce`'s first step is create-vm as an awaited child,** on an id built from the parent's own slot (`create-vm-<mce>_<infraEnv>_<slot>`), so the two are traceable and a re-run finds the same child. **The parent then installs exactly that VM**, by name, from the child's result (name, MAC, cluster, namespace). **It does not draw from server-scan or take its lock for a VM:** the VM was created for this run, so nobody else knows it. It still builds the BMC address from the kubevirt-redfish system the child reports. **If the install fails after the VM exists, the parent deletes it** (name and MAC), as part of its own rollback and its cancel rollback. herzi needs no change: an open `add-server-to-mce` run still means one machine on its way. Keep create-vm's own route only for manual and lab use, without `count`. |
| 2 | **High** | Design §7, §11.1 | **MACs are unique only within a cluster.** Two VMs on different KV clusters can draw the same MAC. Every VM boots on its MCE's inventory network, whichever zone or cluster it runs in, so a collision breaks both installs (address conflict, a BareMetalHost booting the wrong machine). The design puts the risk at 0.7% with 500 VMs, 3% with 1,000 and 11% with 2,000. | Yes | vm-lifecycle chart and day1 | **Make collisions impossible instead of unlikely: give every KV cluster its own `VM_MAC_PREFIX`, unique across the fleet.** The setting already exists per cluster. Record each cluster's prefix in its day1 file, so uniqueness is checked where cluster names are, and refuse a duplicate at review. Three random bytes stay per cluster (16 million MACs), and the in-cluster check plus KubeMacPool still catch a repeat inside one cluster. KubeMacPool's own range can be set to the same prefix. |
| 3 | **High** | Design §6.5; plan §1.3 `HEADROOM_BUFFER_PERCENT` | **The buffer is set per KV cluster, default 30%.** AD31 makes it one organisation-wide value, `freeCpuPercent` (15%), read by placement and the KV Capacity Controller from one policy file. If placement's buffer differs from the controller's growth target, placement either refuses before growth starts or growth starts too late. | Yes | vm-lifecycle chart, rendered from the platform repo | Render each worker's `HEADROOM_BUFFER_PERCENT` from the shared capacity policy file, not from a per-cluster value, so every cluster and the KV Capacity Controller read the same number. Default 15. Allow no per-cluster override unless the architect adds one to AD31. The design's approach of returning the buffer inside the capacity report is good: keep it, so the placer always applies the value the cluster was deployed with. |
| 4 | Medium | Design §4 and §8; plan §1.1 (`KvPlacerWorkflow`) | **The pending list makes placement stateful.** A long-lived placer per zone holds a queue and a list of placements chosen but not yet created, with signals in both directions, a 30-minute expiry, continue-as-new, and a double count while a report is in flight. AD32 asks only that placements run one at a time, and the platform's controllers are deliberately stateless. The design offers a simpler variant: hold the zone until the VM object exists, then release it before the disk wait. | Yes | vm-lifecycle | **Use the simpler variant.** Take the zone's slot with a child workflow whose id is the lock (the repository's upgrade-control-plane slot precedent), and inside it read, choose and create the VM object. The cluster's own figures then include every earlier VM, so no pending list, expiry or signals are needed, and a crash leaves nothing to reconcile. Cost: creates in one zone run one after another. A create call takes seconds, so herzi's largest batch of 20 clears in a minute or two, which is small next to a VM install. |
| 5 | Medium | Design §6.5 `no-worker`, §8, §11.4 | **A cluster in day1 without a running worker slows every placement in the zone by 30 seconds.** Under AD28 a standby cluster is always being built, and its day1 file exists before its worker is deployed through day2, so every zone pays this for the whole build. | Yes | vm-lifecycle, day1 | Have the day1 file mark when a cluster joins placement (for example `placement: ready`), set once its worker is deployed and answering, and skip clusters without it. The listing step already reads the file, so this costs nothing. Shorten the remaining "no worker" wait to a few seconds; a worker that does not pick up a capacity read in that time is not healthy. |
| 6 | Medium | Design §11.2 | **Halted VMs sit on no node,** so the one-node check cannot see them. With ten 64-core nodes and a 30% buffer, thirteen 32-vCPU VMs are admitted, and three of them cannot start. | Yes | vm-lifecycle (`placement.py`) | **Simulate the packing:** place the Halted reservations, largest first, onto the nodes' free room, then check that the new VM still fits on some node. It is a few lines of pure code over figures the report already has. Under AD28 the KV Capacity Controller also grows the active cluster when Halted VMs push it past its target, so the gap should only matter on a cluster at its 40-node maximum. |
| 7 | Medium | Our `docs/kv-capacity-controller.md` §4 and §9 | **Our controller spec reads capacity from the `kv-capacity` agents, which this design removes.** AD31 needs placement and growth to count used CPU the same way. | Ours | `kubevirt-workflows` | Change the spec to compute capacity with the design's `capacity.py` rules (the one definition of used CPU, Halted VMs and the 1 GiB pad included), reading each KV cluster from the Seed, where its admin kubeconfig lives, not through the agents. See also finding 8. |
| 8 | Medium | Our `docs/kv-capacity-controller.md` §5 | **Our growth target does not match the placement ceiling.** The controller grows to `used × (1 + 15%)`, which lets a cluster fill to about 87%. Placement refuses anything that would push it past `1 − 15%` = 85%. A cluster at 86% turns VMs away, and the controller sees nothing to grow. | Ours | `kubevirt-workflows` | Use one formula on both sides: grow to `ceil((used + largest VM) ÷ (1 − buffer) ÷ node CPU)`. Dividing by `1 − buffer` matches placement's ceiling, and adding the largest VM keeps room for the next request instead of growing only after it is refused. |
| 9 | Low | Design §3; plan §1.3 | **Naming.** The design uses seed `ocp4-seed-<site>-<zone>` and KV clusters `ocp4-kubevirt-<site>-<zone>…`; architecture §9 says `<env>-<site>-<zone>-seed<nn>` and `…-kv<nn>`. First-fit by name equals first-fit by age only if names sort in creation order. | Yes | Architecture §9 and day1 | Settle the KV cluster convention, and require a zero-padded sequence (`kv01`, `kv02`, …) so alphabetical order is creation order. Already an open item in §9. |
| 10 | Low | Design §11.5 | **Namespace.** create-vm defaults to `inventory`; the kubevirt-redfish facade exposes `server-scan-vms`. | Yes | Architecture §9 | One namespace per KV cluster for warm-pool VMs, named in §9, created with the cluster. Already an open item. |

---

## What the design gets right, and the architecture should adopt

- **First-fit in creation order instead of best-fit.** It fills the oldest cluster before the next,
  which is AD28's active and standby model; best-fit could prefer a young, small, nearly full
  cluster. **AD33 adopts it.**
- **A worker inside each KV cluster, dialling out.** No Routes, no fleet tokens, no hub credential
  for any KV cluster.
- **The buffer travels with the capacity report,** so the placer applies the value the cluster
  runs with.
- **The capacity rules:** CPU at 15/16 of vCPU, memory plus 1 GiB, Halted VMs counted in every
  namespace, nodes Ready and uncordoned only, memory checked as well as CPU.
- **The MAC drawn by the run and the name derived from it,** so a new MAC is a new name and the two
  never disagree.

---

## Suggested order

1. **Decide:** create-vm as a child of `add-server-to-mce` (finding 1), the simpler zone lock
   (finding 4), per-cluster MAC prefixes (finding 2).
2. **Before building:** the shared buffer (finding 3) and the `placement: ready` marker (finding 5).
3. **With the build:** packing simulation for Halted VMs (finding 6).
4. **On the architecture side:** done in AD29 (one install workflow) and AD33 (first-fit); the KV Capacity
   Controller's inputs and formula (findings 7 and 8); KV cluster naming and the VM namespace
   (findings 9 and 10).
