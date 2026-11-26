# Naming, zones and labels

How clusters, nodes and InfraEnvs are named, how a server's zone is known, how a NodePool draws
only the Agents of its zone, and how a machine that has served a cluster is kept out of the pool
and collected.

---

## 1. Names

All names are lowercase (Kubernetes names must be).

| Object | Pattern | Examples |
|---|---|---|
| **Cluster** (tenant, MCE) | `ocp4-<lifecycle>-<flavor>-<site>-<id>` | `ocp4-prod-eck-five-a` |
| **Cluster** (seed, KV) | `ocp4-<lifecycle>-<seed\|kv>-<site>-<zone>-<id>` | `ocp4-prod-seed-five-az1-a`<br>`ocp4-prod-kv-five-az1-a` |
| **Node** (VM or bare metal) | `ocp-<flavor>-<mtl\|kv<cpu>>-<site>-<serial>` | `ocp-c200-mtl-five-fch2145v1ab`<br>`ocp-c200-kv32-five-k7q2m9xd` |
| **InfraEnv** | `<flavor>-<mtl\|kv<cpu>>-<zone>` | `c200-mtl-az1`<br>`c200-mtl-az3`<br>`c200-kv32-az1` |
| **Controller ConfigMap** | `<controller>-config`, where `<controller>` is the controller's name, in the controller's own namespace | `inventory-controller-config`<br>`kv-capacity-controller-config` |
| **Capacity policy ConfigMap** | `capacity-policy`, on every Seed | `capacity-policy` |

| Segment | Meaning |
|---|---|
| `lifecycle` | `prod`, `prep` or `test` |
| `flavor` | Cluster: the cluster's flavor, or `mce`, `seed` or `kv` for an infrastructure cluster (below). Node and InfraEnv: the server configuration, with an optional variant letter (below) |
| `mtl` or `kv<cpu>` | `mtl` for bare metal; `kv` plus the vCPU count for a VM, e.g. `kv32` |
| `site` | The physical site. Not in InfraEnv names: an InfraEnv belongs to one MCE, and so to that MCE's site |
| `zone` | The availability zone. In InfraEnv, seed and KV cluster names; never in node, tenant cluster or MCE names (section 2) |
| `id` | Cluster: a sequence letter, `a` to `z` |
| `serial` | Node: the server's serial number for bare metal. For a VM, 8 random lowercase letters and digits, drawn by `create-vm` when it builds the VM and also written as the VM's SMBIOS serial (below) |

### Cluster flavors

| Cluster | Flavor | Example |
|---|---|---|
| Tenant hosted cluster | The cluster's own flavor | `ocp4-prod-eck-five-a` |
| Customer MCE | `mce` | `ocp4-prod-mce-five-a` |
| Seed | `seed` | `ocp4-prod-seed-five-az1-a` |
| KV cluster | `kv` | `ocp4-prod-kv-five-az1-a` |

`mce`, `seed` and `kv` are reserved: no tenant flavor may use them. They are how a seed's folder
and a KV cluster's file are told apart from an MCE's and a tenant's in day1.

### Examples and lengths

| Example | Machine | Length |
|---|---|---|
| `ocp-c200-mtl-five-fch2145v1ab` | Cisco bare metal (11-character serial) | 29 |
| `ocp-c200n-mtl-five-fch2145v1ab` | Cisco bare metal, extra NIC | 30 |
| `ocp-c200-mtl-five-7xk2m33` | Dell bare metal (7-character service tag) | 25 |
| `ocp-c200-kv32-five-k7q2m9xd` | VM, 32 vCPU (8-character serial) | 27 |

### Length

**Bare-metal names must be at most 32 characters,** the limit Cisco UCS sets on a server's name:

```
ocp- (4) + flavor with variant (5) + - + mtl (3) + - + <site> + - + serial (11)  = 26 + site
```

With an 11-character Cisco serial, a site name can be at most 6 characters. The provisioning
workflow checks the whole name's length before writing it to OME or UCS. VM names are not under
the UCS limit; Kubernetes allows 63 characters, and `create-vm` keeps a VM's name to 58 so that
its root disk, `<name>-root`, fits too.

### Why a VM carries a serial, not its MAC

A VM is named before it exists, and its MAC is not known then: KubeMacPool assigns the MAC when
the VirtualMachine is admitted, and `create-vm` never requests one. Requesting a MAC, so that the
name could carry it, is not safe. KubeMacPool admits the same requested MAC on several VMs (tested
on OpenShift Virtualization, 2026-11-25, inside and outside its range); it keeps unique only the
MACs it assigns itself. A requested MAC would also need a MAC prefix configured for every KV
cluster.

So `create-vm` draws a **serial**: 8 random lowercase letters and digits. It is the last segment of
the name and the VM's SMBIOS serial (`firmware.serial`), so the Agent's inventory reports the
serial the name carries, as a bare-metal node's name carries its hardware serial.

| Where | How the name stays unique |
|---|---|
| Within one KV cluster | Checked: a name that any VM of the cluster already has is drawn again |
| Across the KV clusters of a site | By chance: 36^8 is about 2.8 trillion serials. For 10,000 VMs of one flavor and size at one site, the chance that any two share a serial is about 1 in 55,000 |

A clash is never silent: the install fails on the BareMetalHost that already has the name.

### Flavor variants

| Variant | Meaning | Example |
|---|---|---|
| *(none)* | Standard configuration | `ocp-c200-mtl-five-fch2145v1ab` |
| `n` | Extra NIC | `ocp-c200n-mtl-five-fch2145v1ab` |
| `d` | Extra disk | `ocp-c200d-mtl-five-fch2145v1ab` |
| `x` | Other deviation (to be defined) | `ocp-c200x-mtl-five-fch2145v1ab` |

---

## 2. Zones

**A server's zone is physical.** It comes from the Cisco ACI leaf the server is cabled to, and
server-scan collects and stores it. server-scan is the zone's only source of truth.

**The zone is not part of a node's name.** A name is fixed when the server is provisioned; a zone
changes if the server is recabled to another leaf. server-scan picks up the new zone on its next
collection, and nothing is renamed.

| Machine | Where its zone comes from |
|---|---|
| Bare metal | server-scan, from the ACI leaf |
| VM | Its KV cluster's zone. server-scan records it when it scans the KV clusters |

---

## 3. How a server reaches the right zone

```
ACI leaf -> server-scan: zone = az1
             |
             v  draw: name ocp-c200-mtl-five-*  AND  server-scan zone = az1
add-server-to-mce installs the server into InfraEnv c200-mtl-az1
             |
             v  the host boots that InfraEnv's discovery image
Agent registers, labelled by the InfraEnv (section 4)
             |
             v
the az1 NodePool selects Agents by those labels, and claims only az1 Agents
```

| # | Rule | Owner |
|---|---|---|
| 1 | **The draw filters by name and by zone.** InfraEnv `<flavor>-<mtl\|kv<cpu>>-<zone>` draws servers named `ocp-<flavor>-<mtl\|kv<cpu>>-<site>-*`, where `<site>` is its MCE's site, whose server-scan zone is `<zone>`. Zones of one site never share servers | `add-server-to-mce`, server-scan |
| 2 | **server-scan's availability query filters by zone.** | server-scan (to confirm, or add) |
| 3 | **A VM needs no draw.** `create-vm` builds it on a KV cluster in the zone, and the install puts exactly that VM into the zone's InfraEnv (AD29) | `add-server-to-mce`, `create-vm` |
| 4 | **Check the zone after registration.** Once the Agent registers, the install run checks that server-scan's zone for the server equals the InfraEnv's zone, and rolls back if not | `add-server-to-mce` |

---

## 4. Labels

A VM appears as three objects at three layers, and a label on one is never copied to another:

```
KV cluster
 └─ Node (a bare-metal hypervisor)      <- KV hypervisor Node
     └─ VirtualMachine                   <- the VM's definition, in the KV cluster
            │  boots, registers as an Agent, is installed
            ▼
Tenant hosted cluster or Customer MCE
 └─ Node                                 <- the same VM, as a Node of the cluster it serves
```

Section 4.a covers the labels on the MCE side, where Agents are claimed and Nodes are scheduled.
Section 4.b covers the labels on the KV cluster's own objects.

### 4.a Labels on MCE-side objects: Agents, NodePools and the Nodes they create

NodePools never read node names. They select Agents by label, and every Agent is labelled by the
InfraEnv it registers from.

#### InfraEnv: the labels its Agents receive

assisted-service always stamps `infraenvs.agent-install.openshift.io: <InfraEnv name>`. Each InfraEnv
also lists every part of its name, and its MCE's site, as an explicit label:

```yaml
# InfraEnv c200-mtl-az1
spec:
  agentLabels:
    redbull.io/flavor: c200
    redbull.io/size: mtl              # or kv<cpu> for a VM pool, e.g. kv32
    redbull.io/site: five
    topology.kubernetes.io/zone: az1
```

#### NodePool: what it selects, and what its Nodes carry

```yaml
# NodePool of a cluster, for az1
metadata:
  labels:
    redbull.io/inventory-managed: "true"
spec:
  platform:
    agent:
      agentLabelSelector:
        matchLabels:
          redbull.io/flavor: c200
          redbull.io/size: mtl
          topology.kubernetes.io/zone: az1
        matchExpressions:
          - { key: redbull.io/claimed, operator: DoesNotExist }
  nodeLabels:
    topology.kubernetes.io/zone: az1
```

| Label | Reason |
|---|---|
| `redbull.io/flavor`, `redbull.io/size` | A NodePool selects a server configuration and size explicitly. "c200 bare metal across all zones" is `flavor=c200, size=mtl`, not a name prefix, which would also sweep in other sizes and variants |
| `topology.kubernetes.io/zone` on the Agent | Each zone's NodePool claims only Agents of its zone |
| `topology.kubernetes.io/zone` on the Node (`nodeLabels`) | Tenant workloads spread across zones with `topologySpreadConstraints` (AD7) |
| `redbull.io/claimed DoesNotExist` | An Agent that has ever served a cluster is never claimed again by any NodePool (section 5). Adding it changes the NodePool's template hash, so confirm the NodePool is `InPlace` before rollout |
| `redbull.io/inventory-managed: "true"` on the NodePool | The Inventory Controller watches the NodePools carrying it, and orders machines for their waiting workers (`docs/inventory-controller.md`). Set by the hostedclusters-setup chart on every NodePool it renders |

#### Where each label lives, MCE side

| Object | Labels | Set by | Read by |
|---|---|---|---|
| **Agent** | `redbull.io/flavor`, `redbull.io/size`, `redbull.io/site`, `topology.kubernetes.io/zone`, `redbull.io/claimed` | The InfraEnv's `agentLabels`; `claimed` by the Inventory Controller (section 5) | NodePool selectors |
| **NodePool** | `redbull.io/inventory-managed: "true"` | The hostedclusters-setup chart, on every NodePool it renders | The Inventory Controller |
| **Tenant Node** | `topology.kubernetes.io/zone` | The NodePool's `nodeLabels` | The tenant's scheduler: `topologySpreadConstraints` (AD7) |
| **Customer MCE Node** | `topology.kubernetes.io/zone` | Per-zone kubelet node labels (a MachineConfig per zone), or labels set at install, from the KV cluster's zone | The MCE's scheduler: hosted control planes spread their etcd and API servers across zones, and the rule does nothing without this label |
| **BareMetalHost of a VM** | `redbull.io/kv-cluster`, `redbull.io/created-by` | `add-server-to-mce`, when it installs the VM it had `create-vm` build (section 3, rule 3) | `remove-server-from-mce`: which KV cluster the VM is on, and which VM there, so the VM can be destroyed after its host is removed (section 5, rule 6) |

**A VM's BareMetalHost says where its VM lives.** Nothing else on the MCE does: a VM's name carries
no zone and no KV cluster, a zone may have several KV clusters, and a label on the VM is not
copied to the MCE (above). Without the two labels, the run that removes the host would have to
search every KV cluster of the site for a VM of that name. Their values are in section 4.b.

### 4.b Labels on KV cluster objects: hypervisors and VirtualMachines

| Object | Labels | Set by | Read by |
|---|---|---|---|
| **KV hypervisor Node** | `topology.kubernetes.io/zone` (**required**) | The KV NodePool's `nodeLabels` | `create-vm`: the only place it learns which zone a KV cluster is in (below) |
| **VirtualMachine** | `redbull.io/flavor`, `redbull.io/size`, `redbull.io/site`, `topology.kubernetes.io/zone`, `redbull.io/role`, `redbull.io/mce`, `redbull.io/kv-cluster`, `redbull.io/created-by` | `create-vm`, or the procedure creating an MCE's VMs; `kv-cluster` and `created-by` by `create-vm` only | Inventory and reporting; `role` and `mce` also by MCE VM anti-affinity; `created-by` also by every workflow that deletes a VM |

**The zone label is required on every KV cluster's NodePools, and must equal the zone in the KV
cluster's name.** `create-vm` reads a KV cluster's zone from the `topology.kubernetes.io/zone` its NodePools set in
`nodeLabels`, in the cluster's day1 file. A KV cluster is single-zone (AD8), so every NodePool of the
file names the same zone:

```yaml
# sites/five/mces/ocp4-prod-seed-five-az1-a/hostedClusters/ocp4-prod-kv-five-az1-a.yaml
nodepool:
- infraEnvName: c200-mtl-az1
  replicas: 12
  nodeLabels:
    topology.kubernetes.io/zone: az1
```

A KV cluster file whose NodePools name no zone, or two different zones, is never offered to
placement: its capacity silently does not exist for `create-vm`. So the file is **refused when it
is written**, by `provision-cluster` or day1 CI, unless every NodePool carries exactly one, identical
zone, equal to the zone in the cluster's name.

**`redbull.io/role` and `redbull.io/mce` on VMs:**

| Label | Values |
|---|---|
| `redbull.io/role` | `mce`: A master or worker mce node. `worker`: a tenant warm-pool VM |
| `redbull.io/mce` | The MCE's name: the MCE it is part of (`role=mce`), or the MCE whose InfraEnv it serves (`role=worker`) |

Both are needed: anti-affinity between an MCE's own VMs selects `role=mce` **and** `mce=<name>`.
With `mce` alone it would also keep MCE VMs away from every host running that MCE's tenant VMs,
and could leave them unschedulable. A warm-pool VM carries no tenant-cluster label: the cluster is
not known until it is claimed.

**`redbull.io/kv-cluster` and `redbull.io/created-by`, on a VM and on its BareMetalHost:**

| Label | Value | Reason |
|---|---|---|
| `redbull.io/kv-cluster` | The KV cluster's name, e.g. `ocp4-prod-kv-five-az1-a` | On the VM: an inventory gathered from many KV clusters says where each VM lives without keeping track of where each row was read. On the BareMetalHost: the only record on the MCE of where the VM lives (section 4.a) |
| `redbull.io/created-by` | The Temporal run id of the `create-vm` run that built the VM | A VM's name is drawn inside the run, so nothing known beforehand identifies it. A retried create finds its own VM by this label instead of building a second one, and a delete removes only a VM that carries it, so a VM made by hand, or another run's VM of the same name, is never deleted. A run id, not a workflow id: a pool slot's workflow id is used again by later runs, and each of them owns a different VM |

Neither is copied between the layers: `create-vm` writes them on the VM, and `add-server-to-mce`
writes the same two values on the BareMetalHost when it installs that VM.

---

## 5. Claimed Agents and garbage collection

A machine that has served a cluster is never reused as it is (AD23). Instead of each workflow
releasing the machines it frees, **the Inventory Controller marks every Agent bound to a cluster,
and collects marked Agents once they are free.**

```
Agent bound to a cluster  ->  label redbull.io/claimed=true  (by the Inventory Controller)
             |
             v  the machine leaves the cluster, by any path
Agent free again, still labelled  ->  no NodePool can claim it (selector, section 4)
             |
             v
Inventory Controller: claimed + unbound  ->  remove-server-from-mce, then destroy a VM
```

| # | Rule | Owner |
|---|---|---|
| 1 | **A label, not an annotation.** A NodePool's `agentLabelSelector` selects labels only | — |
| 2 | **Marked by the Inventory Controller** on every pass: each Agent bound to a cluster (`spec.clusterDeploymentName` set) gets the label. Labelling a bound Agent is safe, and the mark stays until the Agent is deleted | Inventory Controller |
| 3 | **A missed label is caught:** an Agent showing evidence of an unbind (the `Unbinding` condition reason, the `unbinding` or `reclaiming` states, or `status.deprovision_info`) is treated as used, with or without the label | Inventory Controller |
| 4 | **Every NodePool excludes the label** (`redbull.io/claimed DoesNotExist`). The provider applies the selector only when it picks a free Agent, so a bound Agent's running node is not affected | hostedclusters-setup chart |
| 5 | **Collect:** Agents labelled `claimed`, unbound (no `clusterDeploymentName`, no AgentMachine), not deleting, unchanged for a grace period | Inventory Controller |
| 6 | **Act through a workflow:** start `remove-server-from-mce-<server>`, then destroy a VM; bare metal returns to server-scan for reinstall. The id is the server, so a repeat, or `uninstall-server-from-hc`'s own child, is a 409, not a duplicate | Inventory Controller |
| 7 | **Bounded parallelism,** so a deleted cluster does not start all its removals at once | Inventory Controller |
| 8 | **Marked free Agents are not spare.** The Inventory Controller does not count them as claimable, so it does not under-order while they wait | Inventory Controller |
| 9 | **Backfill at rollout:** label every currently bound Agent before turning on the NodePool exclusion | Rollout |

**What this covers:** every path that frees a machine: a scale-down, CAPI choosing another
Machine, a repair replacing a node, `uninstall-server-from-hc`, a deleted cluster.

**What it simplifies:** `update-nodepool` no longer releases machines. A scale-down marks the
Machine only when the customer picked it, commits the count, syncs, and checks the deleting set.

**In the architecture:** AD34.

**One label instead of two:** `claimed` replaces `redbull.io/uninstalling`, since every machine
being uninstalled was claimed first.

---

## 6. Open items

| # | Item |
|---|---|
| 1 | Definition of variant `x` |
| 2 | Whether server-scan's availability query can already filter by zone |
| 3 | The hostedclusters-setup chart rendering `agentLabels`, the selector and `nodeLabels` |
| 4 | The Inventory Controller labelling bound Agents |
| 5 | The Inventory Controller's collection loop |
| 6 | How Customer MCE Nodes get their zone label: kubelet node labels per zone, or labels at install |
| 7 | Site names of at most 6 characters, or a shortened serial, so Cisco bare-metal names stay within 32 |
| 8 | `create-vm` labelling a VM `redbull.io/kv-cluster`, and `add-server-to-mce` labelling a VM's BareMetalHost `redbull.io/kv-cluster` and `redbull.io/created-by` (section 4). The VM's name and its `redbull.io/created-by` label are already built this way |
| 9 | `provision-cluster` or day1 CI refusing a KV cluster file whose NodePools do not all carry one identical zone label, equal to the zone in the cluster's name |
| 10 | Updating architecture §9 to this convention once agreed |
