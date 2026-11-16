# VM Placement

**What:** Chooses the KV cluster a new warm-pool VM is created on, and creates it.
**Where:** The `create-vm` workflow in `team-redbull/workflows`, owned by the team (AD29).
Design in that repo: `docs/design/kubevirt-vm-placement.md`. This page is the architecture's
view of it, and the changes the architecture requires.

---

## Terms

| Term | Meaning |
|---|---|
| **InfraEnv** | The inventory pool. Server type, zone and VM size all come from its name. Never a NodePool: placement only sees supply. |
| **KV cluster** | Where the VM is created. The unit of decision. |
| **Hypervisor** | A bare-metal node inside a KV cluster. KubeVirt places the VM on one; placement never does. |
| **Buffer** | The share of a cluster's CPU and memory that must stay free after placing. The live-migration reserve, `freeCpuPercent` in the capacity policy (AD28, AD31). |
| **Halted reservation** | A VM created Halted and not yet started. It holds no node but counts as used, because kubevirt-redfish will start it. |

---

## What it does

`create-vm` knows it needs a VM of a given size for a given InfraEnv. It does not know which
KV cluster has room. Placement decides, creates the VM Halted, and returns where it landed.
The VM is then exposed by kubevirt-redfish, listed by server-scan as `ocp-<infraenv>-<suffix>`,
and installed by `add-server-to-mce` like any server.

Placement is a request-time decision, not a controller: it is decided once per VM and needs no
ongoing reconciliation. Keeping room available is a different job, owned by the
[KV Capacity Controller](kv-capacity-controller.md) on the Seed.

---

## The algorithm

```
1. List      the zone's KV clusters, from the day1 repo's seed folder
2. Read      every cluster's kv-capacity report at once
3. Filter    clusters where the VM fits on one node AND the buffer stays intact
4. Choose    the cluster fullest after placement (best-fit)
5. Create    the VM there, Halted, with a fixed MAC
6. Wait      for its root disk to bind, bounded; roll back on the deadline
```

**Fit is per node.** One schedulable node must have the headroom for the VM's pod. A cluster
with 200 free cores spread over ten nodes holds no 64-core VM.

**The buffer is per cluster.** After placing, used CPU and memory, Halted reservations
included, must stay at or under `1 − buffer` of the cluster's schedulable capacity.

**Best-fit fills one cluster before the next.** This is what makes the zone grow the way AD28
describes: the active cluster fills to its buffer, then placement overflows into the standby,
which becomes the active cluster.

**Nothing fitting is an alarm.** With the KV Capacity Controller keeping room ahead of demand,
`NoKvClusterFitsError` means the controller has fallen behind.

---

## Required changes to `create-vm`

The shipped workflow implements steps 1 to 6. Two architecture decisions need changes there,
for the workflows team to make.

### 1. One placement per zone at a time (AD29)

**Today:** no placement lock, by an explicit design choice. Halted reservations protect
sequential creates, but parallel ones all rank the same snapshot before any creates. The team
saw this in the lab on 2026-11-05: parallel runs landed on the same cluster.

**Why it matters:** herzi orders up to 20 machines per call, so parallel creates are the
normal case, not an edge case. Together they break the chosen cluster's buffer, which is the
live-migration reserve.

**Required:** steps 2 to 5 run one at a time per zone, keyed on site and zone, not on the MCE,
because every MCE of a site draws on the same KV clusters. The listing before and the disk
wait after can stay outside, so the zone is held only for a rank and a create. The
repository's existing slot pattern (`upgrade-control-plane-<mce>_<slot>`, an id that is
the lock) fits: a child workflow on `place-vm-<site>_<zone>`, with a busy slot retried on a
durable timer under a deadline. Failures should keep their current types, because callers
and alerts key on them.

### 2. The buffer comes from the capacity policy (AD31)

**Today:** `HEADROOM_BUFFER_PERCENT`, an environment value on the vm-lifecycle worker,
defaulting to 30.

**Required:** the value is `freeCpuPercent` from the capacity policy file (15), the same file
the KV Capacity Controller reads. If placement's buffer is stricter than the growth target,
placement refuses before growth starts. If it is looser, growth starts too late.

---

## What it deliberately does not do

- **It does not choose a hypervisor.** KubeVirt schedules within the cluster, with
  `HighNodeUtilization` packing VMs onto the fewest nodes (AD30).
- **It does not know about tenants.** A warm-pool VM has no hosted cluster yet.
- **It does not grow or create clusters.** That is the KV Capacity Controller.
- **It does not defragment.** The descheduler's `CompactAndScale` profile repacks churn (AD30).

---

## Open questions

1. **Namespace.** VMs go into the InfraEnv's namespace (`inventory` by default), which must
   exist as a kubevirt-redfish chassis namespace. The convention in §9 of the architecture is
   still TBD.
2. **Memory.** The InfraEnv name in the shipped code fixes memory at 8 GiB per vCPU, so memory
   is proportional to CPU. If that ratio ever varies, the buffer and the growth target need
   memory as a second dimension.
3. **Orphaned VMs.** A VM whose run died after the create will never register an Agent. The
   pool count self-heals, but the orphan holds its cores. Detecting a VM with no Agent belongs
   to Server Scanner, the only component that sees both sides.
4. **Warm-pool VMs cannot satisfy a tenant's topology spread (AD7).** A VM is created before
   any tenant exists, so three agents claimed by one NodePool may land on one hypervisor.
   Placement cannot fix this; it needs solving where agents are claimed.
5. **InfraEnv naming.** The shipped code parses `<conf>[-<opt>]-zone-<zone>-<cpu>`, for example
   `x201-zone-a-8`. §9 of the architecture says `<server-type>[-<variant>]-<zone>-<size>` with
   `small`, `medium` or `large`. One of the two has to move.
