# Inventory Controller (herzi)

**What:** Keeps each InfraEnv pool of ready Agents at demand plus a spare buffer.
**Where:** One instance on every MCE hub: each Customer MCE (tenant pools) and each Seed
(the zone's `-metal` pools that KV clusters grow from, AD27).
**Implementation:** `team-redbull/herzi`, owned by the team. Its design is
`docs/design/herzi-design.md` in that repo; this page is the architecture's view of it.

---

## Terms

| Term | Meaning |
|---|---|
| **NodePool** | Demand. A HostedCluster's request for workers from one InfraEnv. On a Seed, a KV cluster's NodePool is demand on a `-metal` pool. |
| **Agent** | Supply. A machine that booted the discovery image and registered with the hub. |
| **InfraEnv** | What agents register into, `<server-type>[-<variant>]-<zone>-<size>`, shared by every consumer (AD21). |
| **Pool** | One InfraEnv's inventory, keyed by the InfraEnv name. The unit the controller works in. |

---

## What it does

NodePools say how many workers clusters want. Agents are the machines that exist. The
controller compares the two every pass and asks Temporal for the difference.

It does not know or care why demand changed. A new cluster, a scale-up and a worker replaced
by a repair all look the same: the pool is short. One code path handles all of them,
modelled on how Kubernetes schedules pods.

It is the same controller at both layers. On a Customer MCE the demand comes from tenants. On
a Seed it comes from the KV Capacity Controller raising a KV cluster's NodePool
([kv-capacity-controller.md](kv-capacity-controller.md)).

---

## The loop

Every pass, default 60 seconds, for each pool on the hub:

```
buffer = max(minFree, round(highPct × demand))
target = demand + buffer
need   = target − (assigned + claimable + settling + open)
```

| Name | Meaning |
|---|---|
| `demand` | Sum of desired replicas across the NodePools drawing on this pool |
| `assigned` | Agents bound to a NodePool |
| `claimable` | Agents free to be claimed now: unbound, approved, connected, not deleting |
| `settling` | Agents free but not claimable yet: rebooting after a release, just registered. Counted for up to an hour, then alerted on |
| `open` | Install runs for this pool still running in Temporal. Machines being built are not Agents yet |

`need > 0` orders that many. Otherwise the controller says nothing.

- **Only adds, never reclaims (AD26).** Lowering demand or the buffer only stops additions.
  A pool never shrinks on its own.
- **Size off demand, not off assigned.** The two agree only while every NodePool is full; a
  short NodePool hides its shortfall in the assigned count.
- **Subtract what is in flight.** The install route is additive: it starts as many runs as
  asked. Ask for two every pass through a twenty-minute build and you get twenty machines.
- **`minFree` protects small and new pools.** A new node type has demand zero, and any
  percentage of zero is zero.
- **Every pass starts from scratch.** The controller keeps no memory of what it asked for, so
  a restart costs one pass.

---

## Release

A worker a tenant releases is never handed to another tenant as-is (AD23).

- **Bare metal** reboots into the discovery image and is wiped before it registers as free.
  It counts as `settling` while that happens, so the controller does not order machines that
  are on their way back.
- **A VM** is destroyed, and the gap is rebuilt from the base image like any other shortfall.

---

## Talking to Temporal

| | |
|---|---|
| Read in-flight | Temporal: open runs on the pool's slots, `add-server-to-mce-<mce>_<infraEnv>_<slot>` |
| Ask for more | `POST /workflows/server-lifecycle/add-server-to-mce` with `count` |
| Limits | At most 20 per call, at most 15 open per pool, 100 slots |

- **Slots deduplicate.** A run is one machine in one numbered slot. "How many are building"
  is a question anyone can ask Temporal; no parent workflow holds the count.
- **The evaluation cycle is the retry.** A failed run leaves the gap open and the next pass
  sees it.
- **No hardware means probe mode.** When runs fail for lack of machines, the pool orders one
  machine every 20 minutes and alerts, instead of ordering at full rate against nothing.
- **Unknown state blocks growth.** A missing worker queue, an unclear reply or an
  unreadable object stops ordering for that pool rather than guessing.
- **Two runs cannot take one machine.** Each run takes server-scan's install lock before
  writing anything.

---

## Config

A ConfigMap on the hub, re-read on change. Every pool starts in dry run.

```yaml
defaults:
  highPct: 10          # spare buffer, percent of demand
  minFree: 2           # spare buffer floor, whole agents
  maxOpenRunsPerPool: 15
  probeInterval: 20m
  dryRunGrow: true     # log intended orders; set false per pool to go live
pools:
  conf203-zone-a-medium:
    minFree: 5
```

---

## Why it is built this way

| Decision | Reason |
|---|---|
| One controller per hub | Blast radius is one hub. In-cluster credentials only. |
| Works per pool, not per tenant | The InfraEnv is already shared (AD21). Bulk orders fall out for free. |
| Ignores what caused the demand | One code path instead of one per cause. |
| Reads state, never events | Restart recovery is a single pass. |
| Same controller on the Seed | KV clusters are hosted clusters on the Seed; their workers are a pool like any other (AD27). |
| Never in the tenant's request path | An outage slows replenishment. It does not fail tenant requests. |

---

## Open

- **VM pools have no builder.** herzi orders `add-server-to-mce`, which installs a machine
  server-scan already lists. For a VM pool that machine must first be created by `create-vm`,
  and nothing calls `create-vm` today. Either herzi orders `create-vm` for VM pools, or
  `add-server-to-mce` starts `create-vm` as a child for a VM InfraEnv. The workflows repo
  names the second as the planned step; it is not built.
- **Live rollout.** herzi has not run against a real hub, and every pool defaults to dry run.
