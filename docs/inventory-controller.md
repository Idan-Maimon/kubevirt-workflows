# Inventory Controller (herzi)

The Inventory Controller automates the manual work of managing Agents on an MCE. Its job is to ask
for new nodes to join, and to remove claimed Agents from the inventory. It runs on every MCE hub:
each Customer MCE, and each Seed.

**Implementation:** [team-redbull/herzi](https://github.com/team-redbull/herzi)

**Version:** 0.2

---

## Requirements

| ID | Requirement | Description |
|---|---|---|
| R1 | Detect and provision new nodes | Keep a set number of spare Agents ready in each pool, and order a machine for every worker that waits for one. A pool is identified by its InfraEnv's `redbull.io` labels, and servers are asked of server-scan by those attributes. |
| R2 | Tag claimed Agents | Label every Agent bound to a cluster `redbull.io/claimed: "true"`. Once that Agent is released, no NodePool can claim it again. herzi does this itself, on every pass. |
| R3 | Garbage-collect used nodes | When a claimed Agent is free again, remove its server from the MCE through `remove-server-from-mce`, so a machine that has served a cluster is never reused as it is (AD23). |

---

## Terms

| Term | Meaning |
|---|---|
| **InfraEnv** | What Agents register into: `<flavor>-<mtl\|kv<cpu>>-<zone>` (naming convention), one per node type and zone on a hub, shared by every consumer (AD21). It stamps its `agentLabels` on every Agent: `redbull.io/flavor`, `redbull.io/size`, `redbull.io/site`, `topology.kubernetes.io/zone` |
| **Pool** | One InfraEnv's inventory. The unit the controller works in, identified by the InfraEnv's labels |
| **NodePool** | Demand: a HostedCluster's request for workers. It selects Agents by `redbull.io/flavor`, `redbull.io/size` and zone, and excludes `redbull.io/claimed`. herzi watches the NodePools labelled `redbull.io/inventory-managed: "true"`. On a Seed, a KV cluster's NodePool is demand on a bare-metal pool |
| **Agent** | Supply: a machine that booted the discovery image and registered with the hub |
| **Fresh Agent** | An Agent that has never been bound to a cluster: no `redbull.io/claimed` label, no sign of use |
| **Used Agent** | An Agent that has been bound to a cluster: labelled `redbull.io/claimed`, or caught while unbinding |
| **Spare** | A fresh Agent that is free in its pool: unbound, approved and connected |
| **Waiting claim** | A worker waiting for an Agent: an AgentMachine with condition `AgentReserved=False`, reason `NoSuitableAgents`. It carries its NodePool's selector (`spec.agentLabelSelector`) |

---

## R1 · Detect and provision new nodes

The controller keeps machines ready before anyone waits for one, and orders a machine for every
worker that does wait. It works per pool, every pass (default 60 seconds), with two rules:

| Rule | What the controller does |
|---|---|
| **Spares** | Keeps a set number of spares ready in each pool. When a spare is claimed, it orders a replacement |
| **Waiting claims** | Orders one machine for every waiting claim the pool can satisfy |

A new cluster, a scale-up and a repaired worker all reach the controller the same way: as waiting
claims, once the pool's spares are taken. On a Customer MCE the claims come from tenants' NodePools;
on a Seed, from the KV clusters' NodePools that the KV Capacity Controller grows
([kv-capacity-controller.md](kv-capacity-controller.md)).

### Watched NodePools

herzi watches every NodePool labelled `redbull.io/inventory-managed: "true"`, and orders machines for
their waiting claims. It finds a claim's NodePool through the claim's Machine, which HyperShift
annotates `hypershift.openshift.io/nodePool: <namespace>/<name>`.

- **Set by the hostedclusters-setup chart** on every NodePool it renders, tenant clusters and KV
  clusters alike, so every cluster created through day1 is watched.
- **Visible in Wingman** on the cluster's NodePools.

### The calculation

For each pool:

```
spares    = the number of spares to keep in this pool, from herzi's ConfigMap
pending   = AgentMachines with no Agent (condition AgentReserved=False, reason NoSuitableAgents)
free      = fresh, free Agents in this pool now
inFlight  = machines on their way to this pool: install runs currently running in Temporal
need      = pending + spares − (free + inFlight)
```

When `need` is above zero, the controller orders that many machines.

| Name | Meaning | Read from |
|---|---|---|
| `spares` | The number of spares to keep in this pool: a fixed number, set in the ConfigMap | herzi's ConfigMap: `spares` for the pool, else the default (see Config) |
| `pending` | Waiting claims of watched NodePools that this pool can satisfy | AgentMachines of NodePools labelled `redbull.io/inventory-managed: "true"`, which the Agent provider (cluster-api-provider-agent) left without an Agent: `status.agentRef` empty and condition `AgentReserved=False`, reason `NoSuitableAgents`. Each carries its NodePool's selector in `spec.agentLabelSelector` |
| `free` | Fresh Agents free in this pool now | Agents carrying the pool's labels, without `redbull.io/claimed` |
| `inFlight` | Machines on their way to this pool | Install runs currently running in Temporal on the pool's slots, `add-server-to-mce-<mce>_<infraEnv>_<slot>`. A run whose Agent already exists (labelled `redbull.io/installed-by: <workflow id>`) is counted once, as that Agent in `free` |

- **Each claim is counted once,** in the pool whose InfraEnv's `agentLabels` satisfy its selector.
  A claim that no pool can satisfy is reported as unsatisfiable, naming its NodePool and selector.
- **Each NodePool's supply depends on its own claims.** A NodePool slow to release machines, such
  as one held by a PodDisruptionBudget, leaves every other NodePool's supply intact.
- **Spares stay in the pool until claimed** (AD26); used Agents leave it through R3.
- **Each pass starts from what the hub shows,** so a restart costs one pass.

### Sizing the spares

The spares cover the time it takes to build a new machine: about 45 minutes for bare metal and
about 20 for a VM.

- **To start:** a fixed number per pool, set in herzi's config for each machine type.
- **Later:** the controller sizes each pool from its own history, as the claims that arrive during
  one build. For example, 4 claims an hour on a busy day × a 45-minute build = 3 spares. A floor and
  a ceiling bound it.

### Pools by label

The controller identifies each pool from its InfraEnv's labels, and asks server-scan for servers by
the same attributes:

| Pool label | Asked of server-scan as |
|---|---|
| `redbull.io/flavor` | the server configuration |
| `redbull.io/size` | bare metal (`mtl`), or the VM size (`kv<cpu>`) |
| `redbull.io/site` | the site |
| `topology.kubernetes.io/zone` | the zone, which server-scan holds from the server's ACI leaf |

An InfraEnv missing any of these labels is reported blocked, naming the label. For a VM pool, the
install run builds the VM through its `create-vm` child and installs exactly that VM (AD29).

### Talking to Temporal

| | |
|---|---|
| Read in-flight | Open runs on the pool's slots, `add-server-to-mce-<mce>_<infraEnv>_<slot>`, and the objects labelled with their workflow id |
| Order | `POST /workflows/server-lifecycle/add-server-to-mce` with `count`, carrying the pool's attributes |
| Limits | At most 20 per call, at most 15 open per pool, 100 slots |

- **Each run is one machine,** in one numbered slot.
- **A failed run leaves its claim waiting,** and the next pass orders again.
- **When runs fail for lack of hardware,** the pool orders one machine every 20 minutes and alerts
  (probe mode).
- **When a worker queue is missing or an object is unreadable,** the pool holds its orders and
  reports why.
- **Each run takes server-scan's install lock** before writing anything.

---

## R2 · Tag claimed Agents

Every pass, the controller labels each Agent bound to a cluster (`spec.clusterDeploymentName` set)
`redbull.io/claimed: "true"`.

- **Safe on a bound Agent.** The Agent provider reads a NodePool's selector only when it picks a free
  Agent, so the label does not disturb a running node.
- **Never removed.** The label stays until the Agent is deleted. A server installed again registers a
  new Agent, without it.
- **Catches what a pass missed.** An Agent bound and released between two passes would carry no
  label. The controller also treats an Agent as used when it shows evidence of an unbind: the
  `Unbinding` condition reason, the `unbinding` or `reclaiming` states, or `status.deprovision_info`.
  An Agent with no evidence of use stays fresh.
- **Requires every NodePool to exclude the label** (`redbull.io/claimed DoesNotExist`). Wingman writes
  that exclusion into every NodePool (`DAY1_EXCLUDED_AGENT_LABELS`, Wingman#109); the
  hostedclusters-setup chart renders it.

---

## R3 · Garbage-collect used nodes

When a used Agent is free again, the controller removes its server from the MCE.

| Rule | Detail |
|---|---|
| **When** | A used Agent that is unbound, not deleting, and unchanged for a grace period |
| **How** | Start `remove-server-from-mce-<server>`: it powers the host off, deletes the BareMetalHost and NMStateConfig, deletes the Agent last and clears the PXE entry. The bare-metal server returns to server-scan for a full reinstall |
| **Never deletes the Agent itself** | A host still running discovery would register again within a minute, as a fresh, unlabelled Agent |
| **Never fights a run** | A server with an open uninstall, remove or named install run is skipped. The workflow id is the server, so a repeated start is a 409, never a second removal |
| **Paced** | At most a set number of removals open per pool, so a deleted cluster does not start all its removals at once |
| **Opt-out** | An Agent carrying `herzi.redbull.io/ignore` is not collected |
| **Starts in dry run** | `dryRunCollect: true` logs the removals it would start |
| **Watched** | Metrics, events, and an alert for a used Agent that is not collected |

A fresh Agent is never removed; only used Agents are collected (AD34).

---

## Config

| ConfigMap | Purpose |
|---|---|
| `inventory-controller-config` | The controller's own settings for its hub |

```yaml
# inventory-controller-config.yml
data:
  config.yaml: |
    defaults:
      spares: 2              # R1: fresh Agents kept ready in each pool
      maxOpenRunsPerPool: 15
      probeInterval: 20m
      dryRunGrow: true       # R1: log intended orders; set false per pool to go live
      dryRunCollect: true    # R3: log intended removals; set false to go live
    pools:
      c200-mtl-az1:
        spares: 3
      c200-kv32-az1:
        spares: 5
```

The collector's grace period and its limit of removals open per pool are set in the same file.

---

## Why it is built this way

| Decision | Reason |
|---|---|
| One controller per hub | Blast radius is one hub. In-cluster credentials only |
| Works per pool | The InfraEnv is shared by every consumer (AD21), so orders group naturally |
| Pools identified by labels | Labels are explicit, and server-scan is asked by the same attributes |
| Driven by spares and waiting claims | Each waiting worker is counted exactly once, from its own selector, and every NodePool's supply depends only on its own claims |
| Reads the hub's state each pass | A restart recovers in one pass |
| Tags and collects used Agents itself | One place covers every way a machine is released: a scale-down, a repair, an uninstall, a deleted cluster |
| Same controller on the Seed | KV clusters are hosted clusters on the Seed; their workers are a pool like any other (AD27) |
| Never in the tenant's request path | An outage slows replenishment and collection. It does not fail tenant requests |

---

## Open

- **Destroying a VM after collection.** `remove-server-from-mce` takes the machine out of the MCE.
  For a VM server, either it also deletes the VM, or the collector calls the VM delete as well.
- **A claim that several pools can satisfy:** which pool the controller orders from, when a
  NodePool's selector matches more than one InfraEnv. How InfraEnvs are ranked is not decided.
- **The spares per pool:** the starting number for each machine type.
- **VM pools: decided, not built.** `add-server-to-mce` starts `create-vm` as a child for a VM
  InfraEnv (AD29).
- **Live rollout.** herzi has not run against a real hub, and every pool defaults to dry run.
