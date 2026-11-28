# 24 :: Add Server to UPI Cluster

**Animation:** [`../animations/24-add-server-to-upi.html`](../animations/24-add-server-to-upi.html)
**Interfaces:** [`00-interfaces.md`](00-interfaces.md) — the inventory API, its install lock, the segment lookup
**Implementation:** `workflow_domains/upi_lifecycle/add_server_to_upi.py` in `team-redbull/workflows`,
branch `feat/upi-lifecycle` (not merged yet)

| | |
|---|---|
| **Trigger** | An operator naming a server, when a UPI cluster needs a worker of its own |
| **Workflow id** | `add-server-to-upi-<cluster>_<server>` |
| **Runs on** | The worker inside the target cluster, on that cluster's own queue `upi-server-activity-<cluster>`; the segment-lifecycle queue for the VLAN |
| **Scope** | A cluster installed with user-provisioned infrastructure (procedure 23, `create-upi-cluster`): an MCE's own workers, or any other UPI cluster's. Not a hosted cluster's worker, which is a NodePool change ([04](04-update-nodepool.md)) |
| **Adds** | One Node per run. N servers are N runs |

---

## 1 :: Purpose

Join one bare-metal server to a UPI cluster as a Node of that cluster. The run ends when the Node is
Ready and labelled.

This is not [01](01-add-server-to-mce.md). 01 puts a machine into an MCE's **inventory**, as an Agent
a NodePool will claim for a hosted cluster. This run makes a machine a Node of the UPI cluster
**itself**: an MCE's own capacity for the control planes and operators it runs.

It is the ignition path of [11](11-add-bm-to-seed-cluster.md)'s open decision, built for any UPI
cluster: an `oc adm node-image create` ISO, booted from the server's virtual media. It needs nothing
from the cluster's own MCE or assisted-service operators, only its API.

---

## 2 :: Inputs

### The request

`POST /workflows/upi-lifecycle/add-server-to-upi`

| Field | Required | Notes |
|---|---|---|
| `cluster` | ✅ | The UPI cluster, exactly as `create-upi-cluster` (procedure 23) named it. It selects the worker queue and the VLAN |
| `server_name` | ✅ | The server, by its server-scan name |
| `hostname` | | The Node's name. Default: the server's name, lowercased |
| `root_device` | | The install disk. Default: the worker's, `/dev/sda` |
| `bond_mode` | | `802.3ad` (default: the switch ports are configured for it) or `active-backup` |
| `node_labels` | | Labels set on the Node once it is Ready. Its role comes from the worker ignition: `node-role.kubernetes.io/worker` |
| `join_timeout_minutes` | | How long the server has to become a Ready Node. Default 90 |

### From elsewhere

| From | What |
|---|---|
| The Segments Manager | The cluster's node segment: its `MCE` segment, else its `UPI` one. Its VLAN goes on the bond |
| server-scan | The server, locked for the run: its BMC endpoint and vendor, its `interfaces[]` with link states |
| The worker | BMC credentials per vendor, server-scan's admin token, the ISO store and the URL it is served at |

---

## 3 :: Preconditions

| # | Check | Owner |
|---|---|---|
| 1 | The cluster's `upi-server-worker` runs inside it, polling `upi-server-activity-<cluster>` | The run waits, its activity pending, until it does |
| 2 | The node segment serves DHCP | The run refuses a segment marked `dhcp: false` |
| 3 | The BMC network reaches the worker's ISO URL over HTTP | Not checked: a BMC that cannot fetch the ISO never boots it, and the join times out |
| 4 | The pull secret the cluster was installed with includes the registry nodes are added from | `oc adm node-image create` fails otherwise |

---

## 4 :: Process flow

| # | Phase | Runs on | Action | On failure |
|---|---|---|---|---|
| 1 | `resolving-network` | Segment-lifecycle limb | The cluster's node segment, `MCE` then `UPI`: the VLAN for `bond0.<vlan>`. Nothing is locked yet | None: `UpiNetworkNotFoundError`. `dhcp: false`: `SegmentWithoutDhcpError` |
| 2 | `allocating-server` | The cluster's worker | server-scan's `POST /servers/available` for the named server: locked for the run (4 hours, holder `add-server-to-upi`), live-checked | server-scan's answer: `ServerNotAvailableError`, `ServerReservedError` |
| 3 | `selecting-bond` | The workflow | Two link-UP NICs on two distinct physical ports, from `interfaces[]` and never from the MAC list ([00](00-interfaces.md)); `nic1` is the first. The rule is 01's, reused | IPMI BMC: `VirtualMediaUnsupportedError`. Unknown vendor: `UnknownBmcVendorError`. No bond: `NoBondableInterfacesError`. Each gives the lock back first |
| 4 | `checking-cluster` | The cluster's worker | A Node of that name already Ready: the server is in, straight to step 8 | |
| 5 | `building-iso` | The cluster's worker | Write the host's nodes-config and run `oc adm node-image create` as the worker's ServiceAccount. The ISO is stored as `<hostname>.iso`, next to its config's hash | `NodeImageBuildError`, with oc's message |
| 6 | `booting` | The cluster's worker | Over Redfish: eject whatever the CD slot holds, insert the ISO's URL and read it back, set a one-time boot to CD, power on or force a restart | `RedfishAuthError`, `VirtualMediaUnavailableError`, `BmcCredentialsMissingError` |
| 7 | `joining` | The cluster's worker | Every 15 seconds, approve this host's CSRs, and only its: the node bootstrapper's client request for `system:node:<hostname>`, then the serving request from that node. Until the Node is Ready | After `join_timeout_minutes`: `NodeJoinTimeoutError`, with the Node's last state and the CSRs approved |
| 8 | `finishing` | The cluster's worker | Set `node_labels` and read them back; eject the media and delete the ISO, both best effort; extend the server-scan lock to a day, so the server is not drawn again before server-scan sees it in the cluster | |
| 9 | `completed` | | Return the Node, the VLAN, the bond's MACs and the CSRs approved | |

### The node's network

```yaml
# the nodes-config.yaml node-image reads, for one host
hosts:
- hostname: ocp-c200-mtl-five-7xk2m33
  rootDeviceHints: {deviceName: /dev/sda}
  interfaces:                                  # MAC -> logical name; the agent renames the NIC
  - {name: nic1, macAddress: "aa:bb:cc:00:00:01"}
  - {name: nic2, macAddress: "aa:bb:cc:00:00:02"}
  networkConfig:
    interfaces:
    - {name: nic1, type: ethernet, state: up, ipv4: {enabled: false}, ipv6: {enabled: false}}
    - {name: nic2, type: ethernet, state: up, ipv4: {enabled: false}, ipv6: {enabled: false}}
    - name: bond0
      type: bond
      state: up
      link-aggregation: {mode: 802.3ad, port: [nic1, nic2]}
      ipv4: {enabled: false}
      ipv6: {enabled: false}
    - name: bond0.105                          # the cluster's node VLAN
      type: vlan
      state: up
      vlan: {base-iface: bond0, id: 105}
      ipv4: {enabled: true, dhcp: true}
      ipv6: {enabled: false}
```

The names are logical, as in 01's NMStateConfig: nothing has to know what the kernel calls the NIC.
There is no single-NIC fallback. Half a bond is a host the fabric is not set up to carry.

### How the ISO reaches the server

The BMC fetches it. The worker inside the cluster builds the ISO onto its own volume, and an nginx
container of the same pod serves that volume behind a plain-HTTP Route: the URL it inserts is
`http://<the worker's route>/<hostname>.iso`. Plain HTTP because BMCs refuse a certificate they do not
trust; the ISO carries the cluster's ignition endpoint, not its credentials.

The Redfish calls are discovered, not hard-coded per vendor: the system is server-scan's BMC path or
the first under `/redfish/v1/Systems`; the slot is the manager's virtual media whose `MediaTypes`
name a CD or DVD; every action is read from its `Actions`. An iLO that refuses the full insert body
gets the minimal one, `{"Image": <url>}`.

### Only this host's CSRs

A UPI cluster approves its nodes' certificates by hand. The run approves a CSR only when it is this
host's, by the subject of its request and by its requester. A pending CSR of any other host, from any
other run or from a person, is left alone.

---

## 5 :: Idempotency

- The ISO is keyed on its config's hash: the same host with the same config is built once.
- A Node already Ready skips the build, the boot and the join.
- Approving a CSR already approved changes nothing, and the join's clock is kept in its heartbeat, so
  a retried wait resumes rather than restarts.
- After the allocation, a failure leaves the lock to its TTL and undoes nothing: half-done work may
  still name the machine. A re-run of the same server and cluster resumes.

---

## 6 :: Outputs

| Field | Notes |
|---|---|
| Node | Name, InternalIP, Ready, roles |
| Network | The segment, the VLAN, the bond's two MACs |
| Server | Its server-scan id and name, its BMC vendor |
| `csrs_approved` | The CSRs the run approved |
| `already_joined` | The Node was Ready when the run started |

---

## 7 :: Built today vs. the architecture

| # | Architecture | Built today |
|---|---|---|
| 1 | [11](11-add-bm-to-seed-cluster.md) leaves the join mechanism open: the Agent flow or ignition | This run is the ignition path, for any UPI cluster. Whether the Seed uses it is still 11's decision |
| 2 | 01 draws from a pool by labels (AD21) | A named server only. No pool draw for a UPI cluster's own workers |
| 3 | A released machine is wiped before reuse (AD23) | No removal path exists for a UPI cluster's Node yet |

---

## 8 :: Open questions

1. **IPMI blades.** A UCS-managed blade has no virtual media, so it is refused today. The PXE map 01
   uses for those blades could serve the node-image ISO's boot artifacts instead.
2. **BMC reachability.** Precondition 3 assumes the BMC network reaches the cluster's `*.apps` over
   HTTP. Where it does not, the ISO has to be served from a host the BMCs reach, such as the site's
   PXE VM.
3. **Removing a server.** Draining, deleting the Node, wiping the disk (AD23) and releasing the server
   in server-scan.
4. **The worker's permissions.** `oc adm node-image create` creates a namespace and a pod to build the
   ISO, and is documented for cluster-admin, which the worker holds by default.
