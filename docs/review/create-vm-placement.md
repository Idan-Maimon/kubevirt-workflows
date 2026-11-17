# How create-vm places a VM: one placement at a time per zone, a worker in every KubeVirt cluster

This page explains, end to end, how a create-vm run decides which KubeVirt cluster (KV cluster)
a new VM goes on, how it gets its MAC address, and who talks to what. It replaces
`kubevirt-vm-placement.md` (every run ranks the clusters on its own) and `kv-agents-api.md` (two
HTTP agents on every KV cluster). It also replaces `kv-placement-server-scan.md`: **server-scan
takes no part in placing or creating a VM.**

---

## 1. The idea in one paragraph

**The zone's clusters come from day1, their numbers come from the clusters themselves, and one
placement at a time is decided per zone.** A create-vm run reads the zone's KV clusters from the
day1 repo. It then asks the zone's **placer** for a cluster. The placer handles one request at a
time: it goes through the clusters in alphabetical order, asks each one's
`vm-lifecycle-worker` for its current figures, and picks the **first** cluster where the VM
fits. It remembers that choice until the VM exists, so the next request does not see the
cluster as emptier than it is. Once a run has its cluster, it creates the VM **in parallel**
with every other run, through the worker inside that cluster, with a MAC it draws itself. A MAC
that is already taken is drawn again, up to three times.

---

## 2. Who runs where

| piece | where it runs | what it does | what it holds |
| --- | --- | --- | --- |
| create-vm workflow | hub, in the brain | one per VM: lists the clusters, asks the placer, creates the VM | nothing |
| zone placer workflow | hub, in the brain | **one per (site, zone)**: decides placements one at a time | the placements chosen but not yet created |
| `cluster-lifecycle-worker` | hub (already deployed) | lists the zone's KV clusters from day1 | the day1 git token (`redbull-git-token`), the same one provision-cluster uses |
| `vm-lifecycle-worker` | **inside each KV cluster** | reports its cluster's figures; creates, reads and deletes VMs | its own ServiceAccount |

The worker inside a KV cluster only makes **outbound** connections: to the hub's Temporal, over
gRPC with TLS through a Route, exactly as the `server-lifecycle-worker` does from each MCE. The
KV cluster exposes nothing, and nothing on the hub holds a credential for it.

**How a run reaches a given cluster:** by Temporal queue name. Each worker polls
`vm-lifecycle-activity-<its cluster's name>`. The name is the day1 file's name, so the list
read from day1 is also the list of queues to send work to.

---

## 3. Where the list of KV clusters comes from

From the day1 repo's `main`, read by the `cluster-lifecycle-worker` on the hub:

```
sites/<site>/mces/ocp4-seed-<site>-<zone>/hostedClusters/<cluster>.yaml
```

- **One file per KV cluster** of that zone. The site comes from the MCE's name, the zone from
  the InfraEnv's name, both parsed once when the request arrives.
- The files are sorted **alphabetically by name**. That is the order the placer tries them in.
- **The file's name (without `.yaml`) is the cluster's name everywhere**: the sort key, the queue
  name, and the `kvCluster` value the worker is deployed with. All three must be the same string.
- No folder, or an empty one: the run fails at once with "no KV cluster in this zone".
- The read happens in each create-vm run, **before** it asks the placer, so the slow part (a
  git clone) runs in parallel and the placer only does the quick part.

Today there is one KV cluster per zone. Nothing depends on that: with several, `-a` is tried
before `-b`.

---

## 4. Why placement is serialized, and what that alone does not fix

**The problem.** Each run reads the clusters' figures and picks one. If ten runs read at the
same moment, they all see the same empty cluster and all pick it, even if it only has room for
two. So placements go through **one placer per zone, one request at a time**: the second
request is answered only after the first one's choice is made.

**Serializing alone is not enough.** The VM is created after the choice, in parallel. So when
the placer answers request 2, the VM of request 1 usually does not exist yet, and the cluster's
own figures do not show it. Request 2 would still see the cluster as if request 1 had never
happened.

**So the placer keeps a list of pending placements**: VMs it has sent to a cluster that do not
exist there yet. When it reads a cluster's figures, it adds that cluster's pending placements
on top, as if those VMs already existed. A pending placement leaves the list when:

| event | why it can leave |
| --- | --- |
| the run reports **the VM was created** | the VM now exists, Halted, and the cluster's own figures count it (section 6) |
| the run reports **the create failed** | nothing will take that room |
| it is **30 minutes old** | the run died without reporting; the room is given back |

Between "created" and the run's report, the VM is counted twice. That only makes the placer
more careful for a few seconds.

**The trade-off you accepted:** a request waits in the zone's queue while the requests ahead
of it are decided, and the placer may be more careful than needed while a report is on its way.
Neither can overbook a cluster.

> **A simpler variant, if preferred:** keep the zone locked until the VM object is created (a
> few seconds), and release it before the 10-minute wait for the disk. Then the cluster's own
> figures always include every earlier choice and no pending list is needed. The cost is that
> the create calls of one zone run one after another instead of in parallel.

---

## 5. The flow, end to end

```mermaid
sequenceDiagram
    participant U as caller
    participant WF as create-vm run (hub)
    participant G as cluster-lifecycle-worker (hub)
    participant P as zone placer (hub)
    participant A as worker in kv-a
    participant B as worker in kv-b

    U->>WF: POST /workflows/vm-lifecycle/create-vm (MCE, InfraEnv)
    WF->>G: list the zone's KV clusters (day1)
    G-->>WF: [kv-a, kv-b]
    WF->>P: place a VM of this size on one of [kv-a, kv-b]
    Note over P: one request at a time
    P->>A: your figures?
    A-->>P: figures
    P->>P: kv-a + its pending VMs + this VM: over the buffer, skip
    P->>B: your figures?
    B-->>P: figures
    P->>P: kv-b fits: add this VM to kv-b's pending list
    P-->>WF: kv-b
    Note over WF: from here, in parallel with other runs
    WF->>WF: draw a MAC; name = ocp-<infraenv>-<MAC's last six hex>
    WF->>B: create the VM, Halted, with that MAC
    B-->>WF: created
    WF->>P: created (drop it from the pending list)
    WF->>B: wait for the root disk (up to 10 min)
    B-->>WF: ready
```

| phase | what happens | sent to |
| --- | --- | --- |
| `listing-kv-clusters` | Read the zone's clusters from day1. None: the run fails. | `cluster-lifecycle-worker` |
| `awaiting-placement` | Ask the zone's placer and wait for its answer. No cluster fits: the run fails, listing every cluster and why it was skipped. | the zone placer |
| `creating-vm` | Draw a MAC, build the name from it, create the VM Halted. MAC or name already used: draw again, at most 3 tries in total. Then tell the placer "created" or "failed". | the chosen cluster's worker, then the placer |
| `awaiting-root-disk` | Wait until the root disk is ready, up to 10 minutes. | the chosen cluster's worker |
| `removing-vm` | Only if the disk never became ready: delete the VM, then fail. | the chosen cluster's worker |
| `completed` | The VM's name, MAC, cluster and namespace. | |

---

## 6. The capacity calculation, in full

### 6.1 How big a VM is, in the scheduler's terms

An InfraEnv's name gives the VM's size: `x201-zone-a-32` means 32 vCPUs and `32 × 8` = 256 GiB.
Capacity is measured by what the VM's pod **requests** from the Kubernetes scheduler:

- **CPU request** = vCPU × 15 / 16, rounded down, at least 1 core
- **memory request** = guest memory + 1 GiB (KubeVirt's own overhead; the lab measured about
  0.3 GiB, so 1 GiB errs on the safe side)

| VM (vCPU / memory) | CPU request | memory request |
| --- | --- | --- |
| 8 / 64 GiB | 7 cores | 65 GiB |
| 16 / 128 GiB | 15 cores | 129 GiB |
| 32 / 256 GiB | 30 cores | 257 GiB |
| 64 / 512 GiB | 60 cores | 513 GiB |

Every number below is in these request terms, never in vCPUs.

### 6.2 What the worker reads on its cluster when the placer asks

With its own read-only permissions, at the moment of the request:

1. **Nodes.** A node is *usable* when it is Ready and not cordoned. Only usable nodes count.
2. **Pods**, in every namespace, except finished ones (Succeeded or Failed): the sum of each
   one's container requests, and the node it runs on.
3. **VirtualMachines** and **VirtualMachineInstances**, in every namespace.

### 6.3 What it reports

| figure | how |
| --- | --- |
| **allocatable** | the sum of `allocatable` CPU and memory over the usable nodes |
| **requested by pods** | the sum of the requests of the pods on usable nodes |
| **requested by stopped VMs** | for every VM labelled `redfish-enabled=true` with **no running instance**, whatever its namespace and run strategy: the request its pod will make when it starts (section 6.1, with the 1 GiB). These VMs have no pod yet, but kubevirt-redfish will start them, so their room is already taken. |
| **requested** | requested by pods + requested by stopped VMs |
| **node headroom** | per usable node: its allocatable minus the requests of the pods on it; the report gives the **largest**, for CPU and for memory |
| **buffer** | the share of this cluster to keep free (section 6.5) |

### 6.4 What the placer adds

**requested, as the placer sees it** = the reported requested + the requests of the VMs still
on this cluster's pending list (section 4).

### 6.5 The fit rule

A VM fits on a cluster when ALL of these hold:

1. **CPU stays under the buffer:** `(requested CPU + the VM's CPU) / allocatable CPU <= 1 − buffer`
2. **Memory stays under the buffer:** the same, for memory
3. **One node can hold it:** the largest node headroom is at least the VM's request, on CPU and on memory

- The **buffer** is set per KV cluster, in that cluster's worker (`HEADROOM_BUFFER_PERCENT`,
  default 30), and comes back with the figures. With 30%, a cluster of 100 cores takes at most
  70 cores of requests. It applies to the **whole cluster**, never to one node: nodes may fill
  completely, and the free share is the room live migration needs when a node is drained.
- **Memory is checked as well as CPU**, although it follows CPU. A VM asks for about 8.5 GiB per
  requested core, so on a node with 8 GiB per core memory runs out first: on a 64-core, 512 GiB
  node a second 32-vCPU VM fits on CPU (60 of 64) but not on memory (514 of 512 GiB).
- The placer **never chooses a node**. The VM is created Halted; when it is started, the
  Kubernetes scheduler chooses the node. Check 3 only makes sure such a node exists.
- The **first** cluster in alphabetical order that fits is chosen; the ones after it are not
  even read.

The reasons a cluster is skipped, as the run reports them:

| reason | meaning |
| --- | --- |
| `no-worker` | No worker answered on the cluster's queue within 30 seconds. |
| `unreachable` | The worker answered but could not read its cluster in time. |
| `no-nodes` | The cluster has no usable node. |
| `fit-node` | No single node has room for the VM. |
| `fit-buffer` | The VM would push the cluster past its buffer, on CPU or memory. |

### 6.6 Example: ten 32-vCPU VMs requested at the same moment

Two clusters `kv-a` and `kv-b`, each 100 cores allocatable and empty, buffer 30% (so 70 cores
each). The placer answers the ten requests one after another:

| request | the placer sees on `kv-a` | result | pending `kv-a` | pending `kv-b` |
| --- | --- | --- | --- | --- |
| 1 | 0 + 30 = 30 ≤ 70 | **`kv-a`** | 30 | 0 |
| 2 | 30 + 30 = 60 ≤ 70 | **`kv-a`** | 60 | 0 |
| 3 | 60 + 30 = 90 > 70, skip; `kv-b`: 30 | **`kv-b`** | 60 | 30 |
| 4 | `kv-a` full; `kv-b`: 60 | **`kv-b`** | 60 | 60 |
| 5–10 | both full | **no capacity** | 60 | 60 |

As each VM is created, its 30 cores move from the pending list into the cluster's own figures,
so the totals the placer sees do not change.

---

## 7. The MAC address

- **The run draws it**, while creating the VM: a fixed, locally administered prefix (set per KV
  cluster in its worker, `VM_MAC_PREFIX`, for example `02:a1:b2`) plus three random bytes. No
  list of used MACs is kept anywhere.
- **The VM's name carries it**: `ocp-<infraenv>-<last six hex digits of the MAC>`. So the name
  and the MAC always agree, and a new MAC is also a new name.
- **The cluster refuses a MAC already in use.** Before creating, the worker checks that no other
  VM on its cluster has that MAC, and OpenShift Virtualization's KubeMacPool refuses a duplicate
  too. A refusal, or a name already taken, makes the run draw a new MAC and try again **on the
  same cluster**: at most 3 tries in total, then the run fails.

---

## 8. When things go wrong

| what happens | what the design does |
| --- | --- |
| The zone has no cluster in day1 | The run fails at once with "no KV cluster in this zone". |
| No cluster fits | The run fails, listing every cluster and its reason. Nothing was created. |
| A cluster's worker is down | That cluster is skipped as `no-worker` after 30 seconds, and the next one is tried. Every placement in the zone pays those 30 seconds until the worker is back. |
| The MAC or name is already used | New MAC, new name, same cluster; at most 3 tries. |
| The cluster refuses the VM for another reason (namespace missing, request invalid) | The placer is told "failed", the run fails. |
| The root disk is not ready in 10 minutes | The VM is deleted, the run fails. |
| The worker's pod restarts mid-create | Temporal retries; the create finds its own VM by name and MAC and carries on; the disk wait resumes its own clock. |
| A run dies after being placed | Its pending placement is dropped after 30 minutes. |
| The placer is restarted | Its queue and pending list are part of its Temporal state; it carries on where it was. |

---

## 9. Deploying a KV cluster into placement

1. **Its day1 file**, in the zone's seed folder. Its name is the cluster's name from then on.
2. **The `vm-lifecycle-worker` chart** on the cluster, with:
   - `kvCluster`: exactly the day1 file's name
   - the hub Temporal address and its CA
   - the VM's per-cluster values: storage class, network, node selector
   - `HEADROOM_BUFFER_PERCENT` and `VM_MAC_PREFIX`
3. **Its permissions** (all on its own cluster):
   - read: nodes, pods, namespaces, VirtualMachineInstances, PersistentVolumeClaims
   - VirtualMachines: get, list, create, delete
   - DataVolumes: get, delete

A cluster that is in day1 but has no worker is skipped as `no-worker` (section 6.5).

The storage class must bind immediately and allow a `ReadWriteMany` + `Filesystem` volume. The
lab found that otherwise every root disk stays unbound and every run ends in the rollback.

---

## 10. What changes compared to today

| | today | this design |
| --- | --- | --- |
| Which clusters exist | the day1 seed folder, read by the hub vm-lifecycle worker | the day1 seed folder, read by the `cluster-lifecycle-worker` with provision-cluster's token |
| Where the figures come from | an HTTP agent (`kv-capacity`) on each cluster | the worker inside each cluster |
| Order | best fit across all clusters | alphabetical, first that fits |
| Two runs at once | can pick the same cluster and overbook it | cannot: one placement at a time per zone, with a pending list |
| How the VM is created | an HTTP agent (`kv-vm-api`) behind a Route, with a fleet token | the worker inside the cluster, with its own ServiceAccount |
| The MAC | drawn by the run, checked against every MAC the zone's agents reported | drawn by the run, refused by the cluster if taken, up to 3 tries |
| What a KV cluster exposes | two Routes | nothing |
| Credentials for KV clusters on the hub | two fleet tokens, TLS not verified by default | none |
| Buffer and MAC prefix | settings of the hub worker | settings of each cluster's worker |

---

## 11. Known limits and open points

1. **A MAC is only checked against its own cluster.** Two VMs on two different KV clusters can
   draw the same MAC, and if those clusters share a network, both VMs break (address
   conflicts, a BareMetalHost booting the wrong machine). With three random bytes, the chance
   that some pair in the fleet collides is about 0.7% with 500 VMs, 3% with 1,000, and 11% with
   2,000. Checking the whole zone would mean reading every cluster's VMs on each create.
2. **Halted VMs are on no node**, so the "one node can hold it" check cannot see them. Ten nodes
   of 64 cores can really run ten 32-vCPU VMs, but a 30% buffer admits thirteen; the extra
   three would be created and then fail to start.
3. **The node check uses two separate maximums.** The node with the most free CPU and the node
   with the most free memory may be different nodes. It is unlikely here, because memory
   follows CPU on every node.
4. **A worker that is down slows the whole zone.** Every placement in the zone waits up to 30
   seconds for it before moving on.
5. **Which namespace the VMs go in.** create-vm's default is `inventory`, but the kubevirt-redfish
   facade on the platform exposes `server-scan-vms`. Capacity is right either way, because the
   worker counts labelled VMs in every namespace. The namespace itself is still to be settled.
6. **The day1 seed folders do not exist yet.** Until a zone has one, every run for it fails with
   "no KV cluster in this zone".
7. **Not part of this design: making the new VM installable.** server-scan does not offer a
   Halted VM in `/servers/available`, because its links read as unknown. add-server-to-mce also
   cannot yet build a BMC address for a kubevirt-redfish system. Both belong to
   add-server-to-mce's KubeVirt branch.
