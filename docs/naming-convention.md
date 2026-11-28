# Naming, zones and labels

How clusters, nodes, InfraEnvs, NodePools and ConfigMaps are named, how a server reaches the right zone,
and which labels each object carries.

---

## 1. Names

All names are lowercase (Kubernetes names must be).

| Object | Pattern | Examples |
|---|---|---|
| **Cluster** (tenant, MCE) | `ocp4-<lifecycle>-<flavor>-<site>-<id>` | `ocp4-prod-eck-five-a` |
| **Cluster** (seed, KV) | `ocp4-<lifecycle>-<seed\|kv>-<site>-<zone>-<id>` | `ocp4-prod-seed-five-az1-a`<br>`ocp4-prod-kv-five-az1-a` |
| **Node** (VM or bare metal) | `ocp-<flavor>-<mtl\|kv<cpu>>-<site>-<serial>` | `ocp-c200-mtl-five-fch2145v1ab`<br>`ocp-c200-kv32-five-k7q2m9xd` |
| **InfraEnv** | `<flavor>-<mtl\|kv<cpu>>-<zone>` | `c200-mtl-az1`<br>`c200-mtl-az3`<br>`c200-kv32-az1` |
| **NodePool** | `<infraEnv>[-<suffix>]` | `c200-mtl-az1`<br>`c200-mtl-az1-primary`<br>`c200-mtl-az1-replica` |
| **Controller ConfigMap** | `<controller>-config`, where `<controller>` is the controller's name, in the controller's own namespace | `inventory-controller-config`<br>`kv-capacity-controller-config` |
| **Capacity policy ConfigMap** | `capacity-policy`, on every Seed | `capacity-policy` |

| Segment | Meaning |
|---|---|
| `lifecycle` | `prod`, `prep` or `test` |
| `flavor` | Cluster: the cluster's flavor, or `mce`, `seed` or `kv` for an infrastructure cluster (below). Node and InfraEnv: the server configuration, with an optional variant letter (below) |
| `mtl` or `kv<cpu>` | `mtl` for bare metal; `kv` plus the vCPU count for a VM, e.g. `kv32` |
| `site` | The physical site. Not in InfraEnv names: an InfraEnv belongs to one MCE, and so to that MCE's site |
| `zone` | The availability zone. In InfraEnv, seed and KV cluster names; never in node, tenant cluster or MCE names |
| `id` | Cluster: a sequence letter, `a` to `z` |
| `serial` | Node: the server's serial number for bare metal. For a VM, 8 random lowercase letters and digits, drawn by `create-vm` when it builds the VM and also written as the VM's SMBIOS serial |
| `suffix` | NodePool: what the pool's nodes are for inside their cluster. Free text: lowercase letters, digits and `-`, e.g. `primary`, `replica`. Needed when two NodePools of one cluster draw from the same InfraEnv ([NodePool suffix](#nodepool-suffix)) |

### Cluster flavors

| Cluster | Flavor | Example |
|---|---|---|
| Tenant hosted cluster | The cluster's own flavor | `ocp4-prod-eck-five-a` |
| Customer MCE | `mce` | `ocp4-prod-mce-five-a` |
| Seed | `seed` | `ocp4-prod-seed-five-az1-a` |
| KV cluster | `kv` | `ocp4-prod-kv-five-az1-a` |

`mce`, `seed` and `kv` are reserved: no tenant flavor may use them. They are how a seed's folder
and a KV cluster's file are told apart from an MCE's and a tenant's in day1.

### Examples

| Example | Machine |
|---|---|
| `ocp-c200-mtl-five-fch2145v1ab` | Cisco bare metal (11-character serial) |
| `ocp-c200n-mtl-five-fch2145v1ab` | Cisco bare metal, extra NIC |
| `ocp-c200-mtl-five-7xk2m33` | Dell bare metal (7-character service tag) |
| `ocp-c200-kv32-five-k7q2m9xd` | VM, 32 vCPU (8-character serial) |

### Flavor variants

| Variant | Meaning | Example |
|---|---|---|
| *(none)* | Standard configuration | `ocp-c200-mtl-five-fch2145v1ab` |
| `n` | Extra NIC | `ocp-c200n-mtl-five-fch2145v1ab` |
| `d` | Extra disk | `ocp-c200d-mtl-five-fch2145v1ab` |
| `x` | Other deviation (to be defined) | `ocp-c200x-mtl-five-fch2145v1ab` |

### NodePool suffix

A NodePool's name is its InfraEnv's, or the InfraEnv's and a suffix: `<infraEnv>[-<suffix>]`. There
is no cluster part. Each cluster's NodePools sit in their own namespace on the MCE,
`hcp-<clusterName>`, which already scopes the name (Wingman ADR-0071).

Some clusters need two or more NodePools on the **same** InfraEnv, because their nodes do different
jobs. The suffix names that job.

**The scenario: a Solr cluster.** Solr runs primary and replica shards. Both run on the same
servers, `c200` bare metal in `az1`, so both NodePools draw from InfraEnv `c200-mtl-az1`. But the
two kinds of node are not interchangeable:

| NodePool | Its nodes get | Tuning | Why it differs |
|---|---|---|---|
| `c200-mtl-az1-primary` | `redbull.io/nodepool-role: primary` | The primaries' profile, e.g. for indexing: I/O and dirty-page settings | Primary shards take every write |
| `c200-mtl-az1-replica` | `redbull.io/nodepool-role: replica` | The replicas' profile, e.g. for queries and caches: memory settings | Replica shards serve reads |

Without a suffix both NodePools would be `c200-mtl-az1`. Wingman refuses the clash at the field,
and the hostedclusters-setup chart refuses a file whose two entries render one name ("nodepool
name … is used twice"). With a suffix, each NodePool has its own name, and so its own:

| Per NodePool | Field in the day1 entry | Effect |
|---|---|---|
| Node labels | `nodeLabels` | The Solr workloads place primaries and replicas by `nodeSelector` on `redbull.io/nodepool-role` |
| Tuning | `tuningConfig` (Tuned, PerformanceProfile) and `configs` (MachineConfigs) | Each role gets the node tuning its shards need, without tuning the other role's nodes |
| Size | `replicas` | `update-nodepool` sets one NodePool by name ([04](procedures/04-update-nodepool.md)): replicas grow without touching primaries |
| Supply | The NodePool's waiting workers | The Inventory Controller orders machines per NodePool (AD26), so one role's waiting workers never wait on the other's |
| Upgrade | The NodePool's version | Upgrade one role, let it soak, then the other ([13](procedures/13-upgrade-hosted-cluster-workers.md)) |

**How the name is entered.** Nobody types a whole NodePool name. On Wingman's create form, and in a
flavor (Wingman ADR-0071, ADR-0072):

| Part | Entered as | Values |
|---|---|---|
| Node type, `<flavor>-<mtl\|kv<cpu>>` | **Picked** from the Node type dropdown: the node types the cluster's MCE has InfraEnvs for, each with its zones | `c200-mtl` (bare metal), `c200-kv32` (VM, 32 vCPU) |
| Zone | **Not picked.** A node type gives one NodePool per zone it has, each with its own replicas (0 allowed) and the same configuration | `az1`, `az2`, `az3` |
| Suffix | **Free text**, the Name suffix field, or preset by the flavor. Optional | `primary`, `replica`, `ingest` |

Node type and zone together are the InfraEnv's name, so a composed name always points at an
InfraEnv that exists. One node type with one suffix is one *logical* nodepool to the customer:
`c200-mtl-az1-primary`, `c200-mtl-az2-primary` and `c200-mtl-az3-primary` are its three NodePools.
Only when Wingman cannot read the MCE's list is the node type typed with its zone, `c200-mtl-az1`,
as one NodePool. [04](procedures/04-update-nodepool.md) changes one NodePool, one zone, by its name.

**Decode.** An InfraEnv name has an exact grammar, `^[a-z][0-9a-z]*-(mtl|kv[1-9][0-9]*)-az[1-9][0-9]*$`,
whose flavor has no dash. So any NodePool name decodes: its first three parts are the InfraEnv
(flavor, size, zone) and whatever follows is the suffix, dashes included. Wingman groups a cluster
file's NodePools into logical nodepools this way, by node type and suffix, from the names alone, for
drift, sync and the cluster page.

**Prefill.** A flavor presets each of its nodepools: the node type, the suffix, the configs and
tuning, the node labels, the replicas or a ratio. A Solr flavor presets two nodepools on `c200-mtl`:
suffix `primary` with the primaries' tuning, and suffix `replica` with the replicas'. A cluster
created from it gets six NodePools, two per zone, each tuned for its job. Wingman adds
`topology.kubernetes.io/zone` to every NodePool's `nodeLabels` itself, from its InfraEnv.

**The role label.** A workload selects a role's nodes by `redbull.io/nodepool-role: <suffix>`. Today
the flavor presets it in each nodepool's node labels. Wingman writing it from the suffix, as it
writes the zone label, is open item 8.

Rules for the suffix:

1. Optional when the cluster has one NodePool on that InfraEnv. Two NodePools on one InfraEnv need
   different suffixes, and at most one of them none.
2. Free text, checked where it is typed: lowercase letters, digits and `-`, not starting or ending
   with `-`. The whole name is a DNS label of at most 63 characters, because HyperShift labels each
   of the NodePool's Nodes with it (`hypershift.openshift.io/nodePool`).
3. The same suffix on every zone's NodePool of one logical nodepool, which Wingman writes so. The
   suffix is the job, the zone is where.
4. The day1 entry carries the composed name as `name`. Wingman writes it on every NodePool it adds,
   so the chart never derives one.
5. **An existing NodePool keeps its name.** Another name is another NodePool: Argo CD deletes the old
   one with its Machines, and the new one installs new nodes. Older NodePools carry the chart's
   derived name, `<clusterName>-<infraEnv>` (`prod-eck-five-a-c200-mtl-az1`), and the workflows find
   both shapes: `name`, else `<clusterName>-<infraEnv>`.

---

## 2. How a server reaches the right zone

```
ACI leaf -> server-scan: zone = az1
             |
             v  draw: name ocp-c200-mtl-five-*  AND  server-scan zone = az1
add-server-to-mce installs the server into InfraEnv c200-mtl-az1
             |
             v  the host boots that InfraEnv's discovery image
Agent registers, labelled by the InfraEnv (section 3)
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

## 3. Labels

A VM appears as three objects at three layers, and each layer carries the labels its own workflow
writes (rule 1, section 3.4):

```
KV cluster
 └─ Node (a bare-metal hypervisor)      <- KV hypervisor Node
     └─ VirtualMachine                   <- the VM's definition, in the KV cluster
            │  boots, registers as an Agent, is installed
            ▼
Tenant hosted cluster or Customer MCE
 └─ Node                                 <- the same VM, as a Node of the cluster it serves
```

The section is a reference in four parts: 3.1 lists every label, 3.2 shows each object's labels,
3.3 gives examples, and 3.4 states the rules.

### 3.1 The labels

<table border="1" cellpadding="6">
<thead>
<tr><th>Label</th><th>Value</th><th>On</th><th>Set by</th><th>Read by</th><th>Why</th></tr>
</thead>
<tbody>
<tr><th colspan="6" align="left">Which machine</th></tr>
<tr><td><code>redbull.io/flavor</code></td><td>The server configuration, e.g. <code>c200</code></td><td>Agent, VirtualMachine</td><td>The InfraEnv's <code>agentLabels</code>; <code>create-vm</code></td><td>NodePool selectors; <code>add-server-to-mce</code>'s draw</td><td>A NodePool names a server configuration explicitly: "c200 bare metal across all zones" is <code>flavor=c200, size=mtl</code>, where a name prefix would also sweep in other sizes and variants</td></tr>
<tr><td><code>redbull.io/size</code></td><td><code>mtl</code> for bare metal, or <code>kv&lt;cpu&gt;</code> for a VM, e.g. <code>kv32</code></td><td>Agent, VirtualMachine</td><td>The InfraEnv's <code>agentLabels</code>; <code>create-vm</code></td><td>NodePool selectors; <code>add-server-to-mce</code>'s draw, and its choice between bare metal and a VM</td><td>As for <code>flavor</code></td></tr>
<tr><td><code>redbull.io/site</code></td><td>The site, e.g. <code>five</code></td><td>Agent, VirtualMachine</td><td>The InfraEnv's <code>agentLabels</code>; <code>create-vm</code></td><td><code>add-server-to-mce</code>'s draw</td><td>The site is in no InfraEnv's name, because it is its MCE's, so the InfraEnv states it</td></tr>
<tr><td><code>topology.kubernetes.io/zone</code></td><td>The zone, e.g. <code>az1</code></td><td>Agent; every Node (tenant, Customer MCE, KV hypervisor); VirtualMachine</td><td>The InfraEnv's <code>agentLabels</code>; a NodePool's <code>nodeLabels</code>; per-zone kubelet node labels on Customer MCE Nodes; <code>create-vm</code></td><td>NodePool selectors; schedulers (<code>topologySpreadConstraints</code>, AD7); <code>create-vm</code></td><td>Each zone's NodePool claims only its zone's Agents. Tenant workloads, and the hosted control planes on a Customer MCE, spread across zones. On KV hypervisors it is where <code>create-vm</code> learns a cluster's zone (rule 2)</td></tr>
<tr><th colspan="6" align="left">Who may claim it</th></tr>
<tr><td><code>redbull.io/claimed</code></td><td><code>"true"</code></td><td>Agent</td><td>The Inventory Controller, once the Agent is bound (R2 in <a href="inventory-controller.md">inventory-controller.md</a>)</td><td>Every NodePool's selector, as <code>DoesNotExist</code> (rule 3); the collector (R3)</td><td>An Agent that has served a cluster is claimed by no NodePool again, and is collected (AD34)</td></tr>
<tr><td><code>redbull.io/inventory-managed</code></td><td><code>"true"</code></td><td>NodePool</td><td>The hostedclusters-setup chart, on every NodePool it renders</td><td>The Inventory Controller</td><td>The controller orders machines for the waiting workers of the NodePools carrying it</td></tr>
<tr><th colspan="6" align="left">Who made it (AD37)</th></tr>
<tr><td><code>redbull.io/installed-by</code></td><td>The run id of the <code>add-server-to-mce</code> run</td><td>BareMetalHost, NMStateConfig, BMC Secret</td><td><code>add-server-to-mce</code>, when it creates them</td><td>The Inventory Controller</td><td>An install run stays open after its Agent appears; matching the two counts the machine once</td></tr>
<tr><td><code>redbull.io/created-by</code></td><td>The run id of the <code>create-vm</code> run</td><td>VirtualMachine; the VM's BareMetalHost</td><td><code>create-vm</code> on the VM; <code>add-server-to-mce</code> on the BareMetalHost of the VM it had <code>create-vm</code> build (section 2, rule 3)</td><td><code>create-vm</code>, to find its own VM on a retry; every workflow that deletes a VM (AD36)</td><td>A VM's name is drawn inside the run, so the run id is what identifies the VM. A delete removes only a VM carrying it, so a VM made by hand, or another run's VM of the same name, stays</td></tr>
<tr><th colspan="6" align="left">Where a VM lives</th></tr>
<tr><td><code>redbull.io/kv-cluster</code></td><td>The KV cluster's name, e.g. <code>ocp4-prod-kv-five-az1-a</code></td><td>VirtualMachine; the VM's BareMetalHost</td><td><code>create-vm</code> on the VM; <code>add-server-to-mce</code> on the BareMetalHost</td><td><code>remove-server-from-mce</code>, to delete the VM (AD36); inventory</td><td>On the VM: an inventory gathered from many KV clusters says where each VM lives. On the BareMetalHost: the MCE's one record of where the VM lives, since a VM's name carries no zone and no KV cluster, and a zone may hold several KV clusters</td></tr>
<tr><th colspan="6" align="left">How a VM is reached</th></tr>
<tr><td><code>redfish-enabled</code></td><td><code>"true"</code></td><td>VirtualMachine</td><td><code>create-vm</code></td><td>kubevirt-redfish, which exposes the VM as a Redfish system</td><td>Ironic installs and powers the VM through that system, as it does a server through its BMC, and server-scan lists the VM from it</td></tr>
<tr><th colspan="6" align="left">Placement of VMs</th></tr>
<tr><td><code>redbull.io/role</code></td><td><code>mce</code>: a master or worker MCE node; <code>worker</code>: a tenant warm-pool VM</td><td>VirtualMachine</td><td><code>create-vm</code>, or the procedure creating an MCE's VMs</td><td>MCE VM anti-affinity</td><td>Rule 5</td></tr>
<tr><td><code>redbull.io/mce</code></td><td>The MCE's name: the MCE it is part of (<code>role=mce</code>), or the MCE whose InfraEnv it serves (<code>role=worker</code>)</td><td>VirtualMachine</td><td><code>create-vm</code>, or the procedure creating an MCE's VMs</td><td>MCE VM anti-affinity; reporting</td><td>Rule 5</td></tr>
<tr><th colspan="6" align="left">What a node is for</th></tr>
<tr><td><code>redbull.io/nodepool-role</code></td><td>The NodePool's <code>suffix</code>, e.g. <code>primary</code>, <code>replica</code></td><td>NodePool <code>nodeLabels</code>; tenant Node</td><td>The cluster's day1 entry, preset by its flavor in the nodepool's node labels (open item 8), rendered into the NodePool's <code>nodeLabels</code> by the hostedclusters-setup chart</td><td>The tenant's workloads (<code>nodeSelector</code>, affinity); day1 CI's check (rule 7); reporting</td><td>Two NodePools on one InfraEnv do different jobs and need different placement and tuning (<a href="#nodepool-suffix">NodePool suffix</a>). Not <code>redbull.io/role</code>, which places VMs on a KV cluster (rule 5)</td></tr>
<tr><th colspan="6" align="left">Set by the platform</th></tr>
<tr><td><code>infraenvs.agent-install.openshift.io</code></td><td>The InfraEnv's name</td><td>Agent; BareMetalHost and NMStateConfig</td><td>assisted-service on the Agent; <code>add-server-to-mce</code> on the BareMetalHost and NMStateConfig</td><td>assisted-service; the Inventory Controller, to tell which pool an Agent is in</td><td>It ties a host, its network config and its Agent to one InfraEnv</td></tr>
</tbody>
</table>

### 3.2 By object

<table border="1" cellpadding="6">
<thead>
<tr><th>Layer</th><th>Object</th><th>Labels</th></tr>
</thead>
<tbody>
<tr><td>MCE</td><td>InfraEnv</td><td><code>agentLabels</code>: <code>redbull.io/flavor</code>, <code>redbull.io/size</code>, <code>redbull.io/site</code>, <code>topology.kubernetes.io/zone</code>, passed to its Agents</td></tr>
<tr><td>MCE</td><td>Agent</td><td><code>redbull.io/flavor</code>, <code>redbull.io/size</code>, <code>redbull.io/site</code>, <code>topology.kubernetes.io/zone</code> from its InfraEnv; <code>infraenvs.agent-install.openshift.io</code>; <code>redbull.io/claimed</code> once bound</td></tr>
<tr><td>MCE</td><td>NodePool</td><td><code>redbull.io/inventory-managed</code> on itself; it selects <code>redbull.io/flavor</code>, <code>redbull.io/size</code> and <code>topology.kubernetes.io/zone</code>, excluding <code>redbull.io/claimed</code>, and sets <code>topology.kubernetes.io/zone</code> on its Nodes, and <code>redbull.io/nodepool-role</code> when it has a suffix</td></tr>
<tr><td>MCE</td><td>BareMetalHost, NMStateConfig, BMC Secret</td><td><code>redbull.io/installed-by</code>; <code>infraenvs.agent-install.openshift.io</code> on the BareMetalHost and NMStateConfig; a VM's BareMetalHost also <code>redbull.io/kv-cluster</code> and <code>redbull.io/created-by</code></td></tr>
<tr><td>Hosted cluster</td><td>Tenant Node</td><td><code>topology.kubernetes.io/zone</code>, and <code>redbull.io/nodepool-role</code> when its NodePool has a suffix, from its NodePool's <code>nodeLabels</code></td></tr>
<tr><td>Customer MCE</td><td>Customer MCE Node</td><td><code>topology.kubernetes.io/zone</code>, from per-zone kubelet node labels (a MachineConfig per zone) or labels set at install, taken from its KV cluster's zone</td></tr>
<tr><td>KV cluster</td><td>KV hypervisor Node</td><td><code>topology.kubernetes.io/zone</code>, required, from the KV NodePool's <code>nodeLabels</code></td></tr>
<tr><td>KV cluster</td><td>VirtualMachine</td><td><code>redbull.io/flavor</code>, <code>redbull.io/size</code>, <code>redbull.io/site</code>, <code>topology.kubernetes.io/zone</code>, <code>redbull.io/role</code>, <code>redbull.io/mce</code>, <code>redbull.io/kv-cluster</code>, <code>redbull.io/created-by</code>, <code>redfish-enabled</code></td></tr>
</tbody>
</table>

### 3.3 Examples

```yaml
# InfraEnv c200-mtl-az1. assisted-service also stamps infraenvs.agent-install.openshift.io on its Agents
spec:
  agentLabels:
    redbull.io/flavor: c200
    redbull.io/size: mtl              # or kv<cpu> for a VM pool, e.g. kv32
    redbull.io/site: five
    topology.kubernetes.io/zone: az1
```

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

```yaml
# sites/five/mces/ocp4-prod-seed-five-az1-a/hostedClusters/ocp4-prod-kv-five-az1-a.yaml
nodepool:
- infraEnvName: c200-mtl-az1
  replicas: 12
  nodeLabels:
    topology.kubernetes.io/zone: az1
```

```yaml
# sites/five/mces/ocp4-prod-mce-five-a/hostedClusters/ocp4-prod-solr-five-a.yaml
# Two NodePools on InfraEnv c200-mtl-az1, told apart by their suffix (and two each for az2, az3)
nodepool:
- infraEnvName: c200-mtl-az1
  name: c200-mtl-az1-primary
  replicas: 3
  nodeLabels:
    topology.kubernetes.io/zone: az1
    redbull.io/nodepool-role: primary
  tuningConfig: solr-primary
- infraEnvName: c200-mtl-az1
  name: c200-mtl-az1-replica
  replicas: 6
  nodeLabels:
    topology.kubernetes.io/zone: az1
    redbull.io/nodepool-role: replica
  tuningConfig: solr-replica
```

```yaml
# VirtualMachine ocp-c200-kv32-five-k7q2m9xd, on KV cluster ocp4-prod-kv-five-az1-a
metadata:
  labels:
    redbull.io/flavor: c200
    redbull.io/size: kv32
    redbull.io/site: five
    topology.kubernetes.io/zone: az1
    redbull.io/role: worker
    redbull.io/mce: ocp4-prod-mce-five-a
    redbull.io/kv-cluster: ocp4-prod-kv-five-az1-a
    redbull.io/created-by: <the create-vm run id>
    redfish-enabled: "true"
```

```yaml
# BareMetalHost of that VM, on MCE ocp4-prod-mce-five-a
metadata:
  labels:
    infraenvs.agent-install.openshift.io: c200-kv32-az1
    redbull.io/installed-by: <the add-server-to-mce run id>
    redbull.io/kv-cluster: ocp4-prod-kv-five-az1-a
    redbull.io/created-by: <the create-vm run id>
```

### 3.4 Rules

1. **Each layer carries the labels its own workflow writes.** A VM's labels stay on the VM; its
   Agent takes its InfraEnv's labels, and its Node its NodePool's. `redbull.io/kv-cluster` and
   `redbull.io/created-by` sit on both the VM and its BareMetalHost because each layer's workflow
   writes them: `create-vm` on the VM, and `add-server-to-mce` on the BareMetalHost when it
   installs that VM.
2. **One zone per KV cluster file.** Every NodePool of a KV cluster carries
   `topology.kubernetes.io/zone` in its `nodeLabels`, the same on all of them and equal to the zone
   in the cluster's name, since a KV cluster is single-zone (AD8). `create-vm` reads a KV cluster's
   zone from there, so a file naming no zone, or two zones, would leave the cluster's capacity
   outside placement. `provision-cluster` or day1 CI refuses such a file when it is written.
3. **Every NodePool excludes `redbull.io/claimed`** (`DoesNotExist`), so an Agent that has served
   a cluster is claimed by no NodePool again (R2 and R3 in
   [inventory-controller.md](inventory-controller.md)). Adding the exclusion changes the
   NodePool's template hash, so the NodePool is confirmed `InPlace` before rollout.
4. **NodePools select by label.** Every Agent is labelled by the InfraEnv it registers from, so a
   NodePool reads labels and no node names.
5. **MCE VM anti-affinity selects `redbull.io/role=mce` and `redbull.io/mce=<name>` together.**
   With `mce` alone it would also keep an MCE's VMs away from every host running that MCE's tenant
   VMs, and could leave them unschedulable. A warm-pool VM carries no tenant-cluster label: its
   cluster is known only once it is claimed.
6. **A label naming a run carries the run id** (AD37). A pool slot's workflow id is used again by
   later runs, and each of them makes a different machine.
7. **A NodePool's suffix and its `redbull.io/nodepool-role` label are one value.** The name's
   suffix and the label in its `nodeLabels` agree, or the entry is refused, so a tool can decode the
   role from the name and a workload can select it by the label ([NodePool suffix](#nodepool-suffix)).

---

## 4. Open items

| # | Item |
|---|---|
| 1 | Definition of variant `x` |
| 2 | Whether server-scan's availability query can already filter by zone |
| 3 | The hostedclusters-setup chart rendering `agentLabels`, the selector and `nodeLabels` |
| 4 | How Customer MCE Nodes get their zone label: kubelet node labels per zone, or labels at install |
| 5 | `create-vm` labelling a VM `redbull.io/kv-cluster`, and `add-server-to-mce` labelling a VM's BareMetalHost `redbull.io/kv-cluster` and `redbull.io/created-by` (section 3). The VM's name and its `redbull.io/created-by` label are already built this way |
| 6 | `provision-cluster` or day1 CI refusing a KV cluster file whose NodePools do not all carry one identical zone label, equal to the zone in the cluster's name |
| 7 | `provision-cluster` or day1 CI refusing a NodePool whose suffix and `redbull.io/nodepool-role` label differ (rule 7). Two NodePools on one InfraEnv with one name are already refused, by Wingman and by the chart |
| 8 | Wingman writing `redbull.io/nodepool-role` from the suffix, as it writes `topology.kubernetes.io/zone` from the InfraEnv (Wingman ADR-0072, amendment of 2026-11-28). Until then a flavor presets it in each nodepool's node labels |
| 9 | That NodePool `nodeLabels` reach the tenant Nodes for a custom key on the HyperShift version in use, as they do for the zone label |
