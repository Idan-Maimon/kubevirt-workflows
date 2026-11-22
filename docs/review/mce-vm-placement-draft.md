# MCE and tenant VMs on shared KubeVirt hosts (DRAFT, for discussion)

**The risk:** Customer MCE masters and workers, and tenant hosted cluster workers, all run as VMs
on the same KV clusters. VMs of one cluster, or of different clusters, can land on the same
bare-metal host.

---

## 1. What can share one host today

On a single hypervisor in a zone's KV cluster:

- the Customer MCE's master VM for that zone (AD19);
- Customer MCE worker VMs, which run the tenants' hosted control plane pods, etcd included;
- tenant worker VMs, of one or many tenants.

---

## 2. Scenarios

| Scenario | Impact when the host fails | Protected today? |
|---|---|---|
| **MCE master and MCE workers on one host** | The MCE loses its master in that zone (1 of 3) and some workers | **Yes.** One master per zone and one KV cluster per zone (AD8, AD19): etcd keeps 2 of 3 |
| **Several hosted control planes' etcd members on MCE workers sharing one host** | Each tenant loses the members on that host | **Yes, if the Customer MCE's worker Nodes carry their zone label.** Verified in HyperShift (`support/controlplane-component/defaults.go`, `setMultizoneSpread`). The rule places a hosted cluster's **control plane pods** (etcd, API servers) on the **MCE's worker Nodes**; it does not concern workers. It is **required** because our HostedClusters use the **Agent** platform (AD3); HyperShift relaxes it to preferred only for its own `KubeVirt` and `OpenStack` platform types, which we do not use. With it, a highly-available control plane's etcd members are in different zones, so on different KV clusters and hosts. **Catch:** a Node without `topology.kubernetes.io/zone` matches no zone, and the zone rule silently does nothing; only the host rule remains, and two MCE worker VMs can share a physical host |
| **Several workers of one tenant on one host** | The tenant loses several workers in one zone at once | **No.** Warm-pool VMs are created before a tenant exists, so placement cannot spread by tenant (AD7). Contained to one zone |
| **Several MCE workers on one host** | Many control plane pods reschedule at once, hurting many tenants' API latency | **No** |
| **Noisy neighbour:** a busy tenant VM next to an MCE master or an etcd-hosting MCE worker | etcd is sensitive to disk and network latency. Slow writes destabilise the API of the MCE and of every hosted control plane on it | **Partly.** AD16 dedicates CPU and memory; disk and network bandwidth are shared |
| **Capacity contention** | Tenant growth fills the KV cluster and the MCE cannot add a worker VM | **No.** Placement treats MCE and tenant VMs alike |

---

## 3. Recommendations

| # | Recommendation | Closes |
|---|---|---|
| R1 | **Customer MCE Nodes carry `topology.kubernetes.io/zone`,** set from the KV cluster their VM runs on (section 3.1). Verify on a live MCE | The etcd-members row |
| R2 | **Required host anti-affinity between VMs of the same MCE.** The platform creates MCE VMs knowing their MCE, so the VM spec carries `podAntiAffinity` `requiredDuringScheduling…`, `topologyKey: kubernetes.io/hostname`, selecting `redbull.io/role=mce` **and** `redbull.io/mce=<name>` (labels in the naming draft). Selecting `mce` alone would also match that MCE's tenant VMs | Several MCE workers on one host |
| R3 | **Dedicated management hosts in each KV cluster:** a small group (3–5 per zone) tainted `redbull.io/role=management:NoSchedule`. MCE VMs tolerate and select it; tenant VMs cannot land there. *Stronger alternative:* a separate management KV cluster per zone | Noisy neighbour, capacity contention |
| R4 | **A higher priority class for MCE VMs** than for tenant warm-pool VMs | Capacity contention |
| R5 | **Tenant same-host placement stays an open item,** not a blocker. It is contained to one zone; a real fix needs placement to know the tenant | Several workers of one tenant on one host (documented, not closed) |

### 3.1 How the Customer MCE Nodes get their zone label

The label is needed on the **Node** objects inside the Customer MCE, not on the VirtualMachine
objects in the KV cluster: a label on a VirtualMachine never reaches the Node that VM becomes. The
Customer MCE is a regular OpenShift cluster, not a hosted one, so no NodePool stamps it.

| Option | How | Notes |
|---|---|---|
| **kubelet node labels** | A MachineConfig per zone sets `--node-labels=topology.kubernetes.io/zone=<zone>`, one machine config pool per zone | The kubelet is allowed to set this label on its own Node. Declarative, in Git |
| **Labels at install** | Per-host node labels set when each VM is installed | The install knows the VM's KV cluster, so the zone. Check support in the MCE version |
| **Day-2 labelling** | A job or controller labels each Node from its VM's zone | Simplest, but another moving part that can lag |

Recommended: the first or the second, set once from the KV cluster's zone and kept in Git.

---

## 4. Why bin-packing does not cancel the anti-affinity

The scheduler works in two phases:

| Phase | What happens | Rules acting there |
|---|---|---|
| **1. Filter** | Removes every node the pod is not allowed on | **Required** anti-affinity (the `InterPodAffinity` filter) |
| **2. Score** | Ranks the remaining nodes and picks the highest | `HighNodeUtilization` (bin-packing, AD30), and **preferred** anti-affinity as one weighted score |

Bin-packing only ranks nodes that passed the filter, so it cannot override a required rule. A
preferred rule competes with bin-packing's score and can lose. **MCE VMs must use the required
form.**

| Component that moves VMs | Respects the rule? |
|---|---|
| Descheduler `CompactAndScale` | Yes. Its eviction of a VM is a live migration, and the target pod goes through the filter |
| Live migration (maintenance, drain) | Yes. Same filter |
| `IgnoredDuringExecution` | Only means a later label change evicts nothing. Not an issue here |

---

## 5. The cost of a required rule

If no host satisfies it, the VM stays **Pending**, or a live migration fails and **blocks a host
drain**. Size the eligible hosts to the MCE VMs in the zone **plus one** for maintenance: a zone
with one MCE master and four MCE workers needs at least 6 eligible hosts. With R3, that is the size
of the management group.

Tenant warm-pool VMs keep bin-packing with no anti-affinity.

---

## 6. To discuss

| # | Question |
|---|---|
| D1 | Dedicated management hosts in each KV cluster, or a separate management KV cluster per zone (R3) |
| D2 | Size of the management group per zone, against the MCE's expected growth |
| D3 | Whether the MCE master, which holds the MCE's etcd, should be isolated further than the MCE workers |
| D4 | Storage for etcd-bearing VMs: local disks versus the shared backend, given the noisy-neighbour row |
| D5 | Whether tenant same-host placement (R5) needs a fix, and where: at claim time, or by tying warm-pool VMs to tenants |
| D6 | One new AD, "Management VMs on dedicated, spread hypervisors", plus a risk entry for R5 |
