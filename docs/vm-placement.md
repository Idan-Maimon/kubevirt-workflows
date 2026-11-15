# VM Placement

**What:** Chooses the KV cluster a new warm-pool VM is created on, and creates it.
**Where:** The [Zone Capacity Controller](zone-capacity-controller.md) on the Seed. Called
by `add_server_to_mce` when the InfraEnv name does not end in `-metal`.

---

## Terms

| Term | Meaning |
|---|---|
| **InfraEnv** | The inventory pool: `<server-type>[-<variant>]-<zone>-<size>`. Server type, zone and size all come from this name. Never a NodePool: a NodePool is a tenant's demand, an InfraEnv is where supply lives, and this function only sees supply. |
| **KV cluster** | Where the VM is created. The unit of decision. |
| **Hypervisor** | A bare-metal node inside a KV cluster. KubeVirt places the VM on one; this function never does. |
| **Hole** | Free capacity on one hypervisor large enough for the requested size. A VM cannot be split across hosts, so holes are what capacity means. |
| **Placeholder** | A negative-priority pause pod reserving a hole for live migration. Preempted by a real VM. |

---

## What it does

The workflow knows it needs a VM of a given size, in a given zone, on a given server type.
It does not know which KV cluster has room. This function decides, creates the object, and
returns where it landed.

It does not name the VM. The name follows a convention and Temporal builds it before
calling. That name is also the idempotency key: calling twice returns the same answer and
creates nothing further.

---

## The call

**In:** `vm_name`, `infra_env`, `server_type`, `variant`, `zone`, `cores`, VM spec
**Out:** `{ kv_cluster, namespace }`, or `NoCapacity`

Deciding and creating are one call rather than two. Splitting them would mean holding the
decision open while a caller acts on it, which is a reservation, with a lease, an expiry and
a reconciliation pass to repair what expiry breaks. Keeping them together removes all of it.
The cost is that the controller holds write credentials for the KV clusters in its zone,
which it needs anyway to read their capacity.

---

## The algorithm

```
1. Already placed?   a VM with this name exists in the zone  ->  return where, done
2. Candidates        KV clusters that match and can fit
3. Order             most free capacity first
4. Create            write the VM to the chosen cluster
5. No candidate      -> NoCapacity
```

**Step 2, the filter.** A KV cluster is a candidate when all of these hold:

- it is in the requested `zone` and holds hypervisors of the requested `server_type` and
  `variant`, because a VM cannot live-migrate to an older CPU generation (C8)
- at least one schedulable hypervisor has a hole of `cores`, computed per host
- it has no Pending virt-launcher pod
- fewer than `infra_env_cluster_cap` VMs of this same InfraEnv are already in it

The second condition is the one that is easy to leave out and expensive to miss. A cluster
can hold five hundred free cores spread as forty on each of a dozen hosts and have nowhere
to put a 64-core VM. Without it the VM is created, sits Pending, and the run times out
instead of this function returning a clean `NoCapacity`.

The third exists because a Pending virt-launcher has not consumed any specific host yet, so
a per-host check will cheerfully say a second VM fits when the first has not landed.
Waiting is cheap; it resolves in seconds.

**Step 3, the order.** Most free capacity first. Keeping clusters at similar utilisation
preserves live-migration headroom in each, which matters while R3 is unmitigated, and stops
one cluster failure taking a disproportionate share of one InfraEnv.

---

## Serialization, and why there is no reservation

**One placement at a time per zone.** This is the Kubernetes scheduler's answer to the same
problem and it buys better placements as well as safer ones. Seven concurrent deciders all
pick the cluster with the most room and concentrate the batch. One decider places, sees the
result, and spreads.

**Read the KV clusters live, never a cached scan.** The VM object exists in the cluster API
within a second of creation, long before the guest boots or an Agent registers. A live read
therefore already accounts for what was just placed, which is why no reservation, no
in-memory assume cache and no reconciliation pass are needed. Capacity is counted from the
resource requests of every non-terminal virt-launcher pod, including Pending ones.

Server Scanner stays out of this path. It remains the periodic view that answers how full a
zone is, which is a reporting question where a minute of staleness is free. Placement is an
admission question where it is not.

---

## The placeholder interaction

Placeholder pods hold the migration reserve, and they consume real resource requests. So a
cluster whose holes are all held by placeholders looks full to a naive capacity read, even
though a real VM would simply preempt one. How this function treats that capacity has to
depend on whether the cluster can still grow.

**Below the node cap, the reserve is a buffer.** Count placeholder-held capacity as
available. The VM is admitted, a placeholder is preempted and goes Pending, the cluster
autoscaler adds a node, and the reserve refills itself. Migration headroom is reduced for
the minutes that takes, which is the price of the cluster being able to grow at all. Treat
it as unavailable instead and no VM is ever admitted into the reserve, so no placeholder is
ever preempted, so the autoscaler is never triggered and the cluster never grows.

**At the node cap, the reserve is a wall.** Count placeholder-held capacity as unavailable.
Nothing can restore the reserve once it is eaten, so eating it would silently trade
migration headroom for one more VM, permanently. This is also the point at which the
cluster stops being a candidate, which is the signal that the zone needs another one.

---

## Capacity, and what "full" means

Never publish a single free-core total for a zone. It lies. Three clusters with 48 free
cores on every host have plenty of cores and nowhere to put a 64-core VM.

Capacity is counted per hypervisor and then summed, once per size:

```
fits(size) = sum over schedulable hypervisors of floor(free cores / size)
```

Exposed per cluster, per server type and per size. This is also the number that says a zone
needs another KV cluster.

---

## Failure

`NoCapacity` must be returned as the same error class the install workflow already treats as
a capacity failure, alongside `ServerNotAvailableError` and `ServerReservedError`. The
Inventory Controller drops that InfraEnv to one probe every twenty minutes on that class. If
a full zone returns anything else, the controller keeps ordering at full rate against a zone
that cannot answer, and the signal that the zone needs another cell never surfaces.

---

## What it deliberately does not do

- **It does not name the VM.** Temporal builds the name from the convention.
- **It does not choose a hypervisor.** KubeVirt schedules within the cluster and live
  migration moves the VM afterwards, so a host chosen here would be wrong within minutes.
- **It does not know about tenants.** A warm-pool VM has no hosted cluster yet.
- **It does not grow or create clusters.** It returns `NoCapacity`; the scale-out loop in
  the Zone Capacity Controller acts on that.
- **It does not defragment.** Nothing moves a VM to make room for a larger one. The
  `KubeVirtRelieveAndMigrate` descheduler profile is the supported tool for that, separately.

---

## Open questions

1. **Namespace.** AD12 is withdrawn, so there is no per-hosted-cluster namespace rule, and a
   warm-pool VM has no hosted cluster. The convention is still TBD in Section 9.
2. **Memory.** The filter counts cores. If memory is strictly proportional to cores across
   all three sizes that is enough; if a 16-core VM can ever ask for large memory, every
   capacity figure here needs a second dimension.
3. **`infra_env_cluster_cap`.** Needs a value. It is the only guard on how much of one
   InfraEnv's inventory a single KV cluster failure can remove.
4. **Orphaned VMs.** A VM created by a run that then died will never register an Agent. The
   pool count self-heals, because the Inventory Controller orders a replacement, but the
   orphan holds its cores forever. Detecting a VM with no Agent after a threshold belongs to
   Server Scanner, the only component that sees both sides.
5. **Warm-pool VMs cannot satisfy a tenant's topology spread (AD7).** A VM is created before
   any tenant exists, so three agents claimed by one NodePool may land on one hypervisor.
   This function cannot fix it. It needs solving where agents are claimed.
