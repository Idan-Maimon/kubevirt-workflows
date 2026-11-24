# 70 :: OCP Kubevirt

## 1 :: Requirements

| ID | Requirement | Description |
|---|---|---|
| R1 | OCP cluster creation | The ability to seamlessly orchestrate the end-to-end creation of MCE, KubeVirt, and Hosted clusters via zero-touch automation, leveraging pre-provisioned inventory |
| R2 | OCP Kubevirt cluster Modification | SREs/Admins must be able to dynamically scale tenant worker nodes, modify node pools, and update cluster configuration without disrupting active Hosted Control Planes |
| R3 | OCP Kubevirt cluster Upgrade | The ability to allow hosted/MCE/Kubevirt cluster to be updated with minimal down time and no cross teams operational dependency |
| R4 | OCP Kubevirt cluster Deletion | Clean lifecycle tear-down to release compute, storage, and network resources safely |

---

## 2 :: Quality Goals

| ID | Quality Category | Description |
|---|---|---|
| SC1 | Operability | The solution can be understood, learned and used |
| SC2 | Predictability | The platform must deliver deterministic execution times for administrative operations and consistent, benchmarkable performance under varying cluster loads |
| SC3 | Availability | The service remain available and perform at accepted level even during partial component degradation |
| SC4 | Utilization | The solution capable of producing desired results with little or no waste of time or materials |

### 2.1 :: Quality Scenarios

| ID | Quality Scenario | Description |
|---|---|---|
| SC1.1 | Ease of Use | A tenant can create, modify and upgrade a cluster through a self-service interface without knowing how the platform places it. Zone allocation, hub selection, node-type to hardware mapping and inventory state are never exposed, and no routine request requires a conversation with the platform team. |
| SC1.2 | Autonomy | The ability of the system or component to operate independently, without requiring continuous manual control or intervention from external entities |
| SC2.1 | Performance Efficiency | Ensures workload execution, latency, and resource consumption remain consistent |
| SC2.2 | Operational Efficiency | Ensures platform management operations (like spinning up Hosted Control Planes via HyperShift or scaling worker nodes) take a deterministic, repeatable amount of time |
| SC3.1 | Resiliency | The service remain available and may not impact SLA during partial hardware failures |
| SC3.2 | Uptime | Any of the solution components including Kubevirt clusters, MCE, hosted cluster, ETCD and so on should remain available at all time |
| SC4.1 | Resources efficiency | maximizing of the supply of materials in order to function effectively, with minimum wasted resource expenses. |

---

## 3 :: Constraints

| ID | Constraint |
|---|---|
| C1 | When using Kubevirt Platform we cannot mix BM (Agent) nodes with VM nodes |
| C2 | When using the **KubeVirt platform type**, a HostedCluster's NodePools can only target one KubeVirt infrastructure cluster. The platform therefore uses the **Agent platform type** instead (AD3), which draws workers from agent inventory and allows a single HostedCluster to span one KubeVirt cluster per zone (AD8). C2 is the reason for that choice, not a limit on it. |
| C3 | Each MCE release supports the current OCP version plus several previous versions (typically up to $N - 3$ or $N - 4$ minor versions) |
| C4 | You cannot deploy or upgrade a Hosted Cluster to an OCP version newer than what your installed MCE Operator supports |
| C5 | It is impossible to accurately predict tenant cluster growth which may impact SLA when kubevirt clusters are full |
| C6 | A single HostedCluster's NodePools cannot span multiple MCE Hubs. The HostedCluster control plane runs on one MCE Hub, and that Hub must manage all NodePools for that cluster. This constrains tenant-to-Hub affinity and impacts capacity planning |
| C7 | KubeVirt Live Migration requires shared storage. VMs can only live-migrate between hypervisor nodes that share a storage backend. This is a KubeVirt/libvirt constraint. It also means live migration cannot cross AZ boundaries if the storage backend is AZ-scoped. The choice of storage product is made in the storage design document, not here |
| C8 | A VM cannot live-migrate to a host with an older CPU generation, because the guest is exposed to the source host's CPU features and the destination must present at least the same set. Inventory therefore has to track back to the physical server type: a VM pool is bound to the hardware it was built on, which is why the InfraEnv name carries the server type and why the same VM size on two server types is two separate pools (AD21). Like C7, this bounds where a running VM may move |

---

## 4 :: Quality Controls

|  | OCP Kubevirt cluster creation | OCP Kubevirt cluster Modification | OCP Kubevirt cluster Upgrade | OCP Kubevirt cluster Deletion |
|---|---|---|---|---|
| **Ease of Use** | 1. Self-service catalog exposes pre-packaged NodePool profiles abstracting Agent/Redfish complexity. 2. AZ allocation and KV/MCE placement complexity is hidden from users to ensure a smooth customer experience | 1. Common modification processes appear in the customer-facing interface as self-service features, eliminating the need to call or explain changes manually | 1. A self-service upgrade process is available for tenants so they can choose the upgrade window themselves | |
| **Autonomy** | 1. Each component in the solution is created before demand arrives to avoid waiting for other resources. For example, VMs are pre-registered in the registry before a hosted cluster claims them | 1. Automated unhealthy worker VM remediation (via Node Health Check) occur without human SRE intervention. | 1. SRE can update master pods independently of tenant workers.<br>2. Within a zone the NodePool controller drives the roll itself, cordoning, draining, updating and rebooting each node and moving to the next with no human step between nodes. The gate between zones is the tenant choosing a window, not an inspection. | 1. A release destroys the machine; the Inventory Controller sees the gap on its next pass and rebuilds the pool with no human involvement. |
| **Performance Efficiency** | 1. VMs allocated with 1:1 CPU/memory at KubeVirt level (AD16 — no hypervisor overcommit). 2. To ensure performance, cell boundaries are created for the KV cluster, hub cluster and hosted cluster. Check the cell boundaries with stress tests | 1. Pre-flight capacity checks confirm target hypervisors, Hub, and HostedCluster do not exceed cell boundaries. If they do, the request is routed to a different cell with headroom or rejected with capacity feedback. | 1. Workers upgrade in place (`upgradeType: InPlace`, AD24): the node is drained, updated and rebooted, and no VM is replaced.<br>2. The roll is capped at one node at a time (`maxUnavailable: 1`), set explicitly rather than inherited, so the capacity dip is one node and the duration is a known multiple of a single node's roll. | |
| **Operational Efficiency** | 1. Cluster creation process is documented and tested to ensure no question asked during manual creation. 2. VMs are pre-registered to the to the MCEs inventory to minimize creation time. 3. VMs are dynamically created on BM nodes and added to server scanner to fulfill inventory requirements | 1. Background reconciliation loop evaluates MCE desired state vs. actual node count at a configurable interval and adds nodes accordingly. 2. Concurrent scale requests for the same cluster are serialized via Temporal workflow locking to prevent conflicting Git commits | 1. Separating Hub control plane updates from KubeVirt worker updates ensures that unpredictable tenant workload drain times cannot delay or block API availability. 2. Nodes can be loaned deterministic to allow a complete replacement of old nodes with newer nodes version by replacing old nodepool with new nodepool | 1. A worker released by a tenant is never reused as-is: a VM is destroyed and the pool rebuilds from the base image, a BM host is wiped and re-registered (AD23).<br>2. Agents that registered but were never claimed carry no tenant state and stay in the pool. |
| **Resiliency** | 1. Control plane pods (Hub) and worker VMs (KubeVirt) are strictly provisioned using `podAntiAffinity` and `topologySpreadConstraints` to ensure no single hardware rack or AZ failure can take down a tenant's quorum. 2. Worker VMs are labeled with the hosted cluster name to evaluate `topologySpreadConstraints` against | 1. If underlying hypervisors require maintenance or exhibit partial degradation, KubeVirt Live Migration shifts active tenant worker VMs to healthy hosts without dropping network connections. 2. if a scale-up VM fails to join the cluster within a defined timeout, Temporal selects an alternative node from inventory and executes a compensating transaction to release the failed node back to quarantine. | 1. Hub control plane upgrades roll sequentially (e.g., `maxUnavailable=1`), ensuring ETCD and API servers retain a functional 2-of-3 quorum even if an AZ drops mid-upgrade.<br>2. Blast radius is bounded by zone, not by a spare node. NodePools roll one zone at a time, and the next zone does not start until every node in the previous zone is ready and schedulable, every PodDisruptionBudget is back above zero, StatefulSets are ready, and all of it has held for a soak period. | 1. Deletion ensures the node has no workloads before removal from the cluster.<br>2. The machine to remove is marked explicitly before the replica count is reduced; selection is otherwise random and cordoning does not influence it.<br>3. Deleting the Machine object directly is prohibited: the MachineSet replaces it immediately, so the subsequent scale-down removes a second node. |
| **Uptime** | 1. Control plane components (3x API / 3x ETCD) and worker VMs are scheduled across 3 physical Availability Zones using strict `podAntiAffinity`. No single AZ failure causes API unavailability. | 1. Pre-flight health checks validate control plane health (API server responding, ETCD quorum intact, no degraded ClusterOperators) before executing any modification. If any check fails, the operation is queued and the requestor is notified. 2. KV clusters must have at least 15% of untouched servers for vmotion | 1. Pre-flight validates cluster health, ETCD backup taken, and no in-progress operations before starting. 2. Control plane upgrades maintain ETCD 2-of-3 quorum throughout. 3. MCE upgrades must precheck hostedclusters version and calculate the version skew policy. 4. KV cluster must evacuate VMs before updating worker nodes | |
| **Resources efficiency** | 1. Worker VMs drawn from pre-provisioned MCE inventory (warm pool). Background process detects inventory drop and provisions replacement VMs on bare-metal nodes to replenish pool. Pool depth maintained above defined low watermark. 2. VM ratio of 1:8 is selected to eliminate waist of bare-metal resources | 1. **Direction, not yet designed.** An opportunistic scheme letting a tenant borrow idle capacity from another tenant for a bounded period. AD16 rules out delivering this through hypervisor overcommitment, so any mechanism must reclaim and reassign whole VMs rather than oversubscribe shared CPU and memory. No design selected yet. | 1. An in-place upgrade draws nothing from the warm pool and returns nothing to it, so upgrade activity never competes with creation or scaling for inventory. | 1. The watermark governs only how quickly the pool rebuilds, so the buffer must absorb churn rather than only first-request latency. |

---

## 5 :: Architectural Decisions

| ID | Decision | Reason |
|---|---|---|
| AD1 | Hypershift as control plan | Decoupling the control plane (running as pods on the Hub) from the data plane drastically reduces resource overhead and accelerates cluster provisioning times compared to traditional standalone OCP clusters. |
| AD3 | VM Lifecycle via Agent-Based Bare Metal Provisioning | Utilizing the `kubevirt/redfish-controller`, KubeVirt VMs are exposed with Virtual BMCs. This allows MCE and the Agent-based Installer to provision and manage VMs identically to physical bare-metal servers, unifying the automation pipeline. |
| AD4 | Bare metal to Kubevirt rolling migration | Using `kubevirt/redfish-controller` allowing rolling migration by adding VMs to hosted cluster and removing bare metal nodes that later can be added to KV cluster as worker nodes |
| AD5 | Zero-Trust Tenant Environments (GitOps Only) | Clusters are deployed with strict Read-Only access for tenants. Application and state management is exclusively driven via GitOps (ArgoCD). Banning manual `kubectl` intervention guarantees immutable state, enabling clean cluster restore procedures. |
| AD6 | Decoupled PVC Lifecycles (Static NFS over CSI) | PVC lifecycles are explicitly not managed via CSI drivers. Tested and verified static NFS provisioning detaches storage from the cluster lifecycle, providing the precise control needed to migrate or restore application state to a different cluster during DR. |
| AD7 | Topology-Aware Node Placement | We utilize standard `topologySpreadConstraints` to enforce per cluster worker VM distribution across physical BM nodes |
| AD8 | Isolated KubeVirt Clusters per AZ | KubeVirt clusters are strictly scoped to a single physical AZ. AZ redundancy for tenants is achieved by configuring a single `HostedCluster` with three distinct `NodePools`, each targeting a different KubeVirt cluster. A total KV cluster failure will only impact one AZ of the tenant's environment. |
| AD9 | Logical AZ Rack Segmentation | Physical data center racks are logically segmented into Availability Zones (e.g., Racks 1-15 = AZ1, Racks 16-30 = AZ3) to translate physical power/network boundaries into Kubernetes scheduling domains. |
| AD10 | Stretched Hub (MCE) Cluster Topology | The MCE Hub cluster is deployed on bare-metal nodes stretched across 3 distinct AZs to guarantee absolute management plane redundancy. |
| AD11 | Unique Redfish DNS per KubeVirt VM | This enables future flexability for cross-cluster VM live migration |
| AD13 | Temporal for Imperative Orchestration | Complex, cross-cluster workflows (e.g., node reallocation, inventory refilling) are governed imperatively via Temporal. Temporal guarantees transactional safety by exclusively mutating the declarative SSOT (GitOps), maintaining ArgoCD as the sole state applicator. |
| AD14 | Asynchronous VM Warm Pools | To guarantee deterministic, low latency cluster provisioning, KubeVirt VMs are pre-provisioned asynchronously into an unassigned MCE inventory. Tenant creation requests draw from this ready inventory. |
| AD15 | Server Scanner as Unified State Tracker | A custom Server Scanner service bridges the visibility gap between MCE, the Agent, and the underlying KubeVirt hypervisors, tracking the strict lifecycle state (In-Use, Available, Draining) of virtual bare-metal capacity. |
| AD16 | No CPU/Memory Overcommitment on KubeVirt Infrastructure | The KubeVirt hypervisor layer runs with dedicated (1:1) CPU and memory allocation per VM. This eliminates the risk of double overcommitment, if both the KubeVirt scheduler and the tenant's OCP scheduler independently overcommit, resource contention compounds unpredictably, violating SC2 (Predictability). Overcommitment decisions are deferred to the tenant level, each HostedCluster's OCP scheduler may overcommit within its own allocated VM resources, where the blast radius is contained to that tenant. |
| AD17 | Seed BM Cluster per Zone as Infrastructure Management Plane | Each availability zone has a dedicated bare-metal cluster (Seed Cluster) installed via UPI, running MCE and HyperShift operators. The Seed Cluster is the zone's infrastructure management plane: it hosts the control planes of all KV clusters in that zone as HyperShift hosted clusters, and manages their lifecycle. Keeping the Seed Cluster per-zone (rather than stretching one management cluster across zones) ensures that a full Seed Cluster failure impacts only one zone's infrastructure management, leaving tenants in other zones unaffected. BM nodes are used for the Seed Cluster to avoid a bootstrapping dependency on the very VMs the cluster is responsible for creating. |
| AD18 | KV Cluster Control Planes as HyperShift Hosted Control Planes | KV cluster control planes run as HyperShift hosted control planes (pods) on the Seed Cluster's worker nodes, not as dedicated BM master nodes. This eliminates the need for BM master nodes per KV cluster, significantly reducing BM node count. A single Seed Cluster can host multiple KV cluster control planes simultaneously, enabling efficient utilisation of the Seed Cluster's compute. The control plane is fully decoupled from the data plane (BM workers with KubeVirt), aligning with AD1 and allowing the data plane to be scaled independently. |
| AD19 | Customer MCE Master VMs — One Per Zone | The Customer MCE Hub cluster control plane is composed of exactly one master VM sourced from each availability zone, giving 3 masters in total. This guarantees that the ETCD quorum (requiring 2-of-3) survives the complete loss of any single zone. Zone sourcing is enforced at VM placement time — the VM's physical host must be within the target zone's rack boundaries. This satisfies SC3.2 (Uptime) for the customer management plane and aligns with AD9 (Logical AZ Rack Segmentation). |
| AD20 | Customer MCE Worker VMs — Zone-Aware Distribution | Customer MCE worker VMs are distributed evenly across the three availability zones using `topologySpreadConstraints`. This ensures that MCE workloads (Assisted Installer agents, InfraEnv ISO generation, ArgoCD, Server Scanner) remain operational if a zone is lost, as the surviving two zones retain sufficient worker capacity. Zone affinity is enforced via the same topology labels used for hosted cluster worker VMs (AD7), keeping the scheduling model consistent across the platform. |
| AD21 | InfraEnv Scoped to Server Type, Zone and Size, Shared Across Consumers | InfraEnvs are provisioned at server-type, zone and size granularity, for example `conf203-zone-a-medium`, not per hosted cluster. The server type is in the key because a VM cannot live-migrate to an older CPU generation (C8), so a pool must track back to the physical hardware it was built on. All NodePools requiring the same combination draw agents from the same shared pool. The pool is indifferent to which consumer claims an agent — consistent with the scheduler analogy where the scheduler does not distinguish between a new deployment and a dead pod replacement. Physical servers use the same scheme with `metal` in place of a VM size. This minimises the number of InfraEnvs to manage and allows the warm pool to serve any consumer transparently. |
| AD22 | Machine-Level Objects Managed Imperatively, Not via GitOps | VMs, BareMetalHosts, BMC Secrets, NMStateConfigs and other per-machine objects are written directly to the hub or KubeVirt cluster API by Temporal activities, not committed to Git. This follows the Kubernetes Deployment and Pod model: Git holds the Deployment, not the Pods, and the Pods are created from it. Here Git holds the desired state (HostedClusters, NodePools, InfraEnvs and cluster configuration), and machines are created to satisfy it. These objects hold no state worth keeping. A machine is interchangeable inventory, and any one of them can be torn down and rebuilt from the inventory record. Putting them in Git would make the repository a churning log of short-lived machines, and would make ArgoCD fight the provisioning flow during rollback. Consistency comes from compensation instead. Each workflow rolls back its own failed candidate in a fixed order, and the Inventory Controller re-reads actual state every pass and closes any remaining gap. |
| AD23 | Released Workers Are Destroyed or Wiped, Never Reused As-Is | A worker that has carried a tenant's OS holds tenant data on its disk, and the pool it returns to is drawn from by other tenants. A VM is destroyed and rebuilt from the base image; a BM host, which cannot be recreated, is wiped and re-registered. Beyond removing the data, this changes what a lost race costs. A released agent is claimable within about a minute, measured, and the protections that would hold it are not dependable, since the bare-metal agent controller re-approves unconditionally. Under reuse, losing that race hands one tenant's data to another. Under destroy-or-wipe, a cluster that claims the machine mid-teardown fails to provision and retries. The cost is buffer depth: the spare pool must absorb churn that reuse previously served instantly. |
| AD24 | Tenant Workers Upgrade In Place, Not By Replacement | A replacement upgrade releases every worker it rolls, and under AD23 a released worker must be destroyed and rebuilt from the base image while a fresh agent is drawn for its replacement. Upgrading a thirty node cluster would cost thirty destroys, thirty rebuilds and thirty draws against a warm pool that also serves creation and scaling, repeated across the fleet. An in-place roll drains, updates and reboots the existing node, so it draws nothing, returns nothing, and completes in a reboot rather than a full assisted install. Replacement bought an intact old node to fall back on and a capacity floor that never dipped. Neither is surrendered for free: the roll is capped at one node at a time so the dip is bounded and known before the run starts, and blast radius is bounded by rolling one zone at a time behind a readiness gate and a soak rather than by a spare node. A failed in-place node is a broken node and is handled as a repair, not a rollback. |
| AD25 | Hosted Cluster Workers May Trail Their Control Plane By Two Minors | The control plane and the workers of a tenant cluster advance separately, so their versions drift. HyperShift permits three minors between a hosted control plane and its NodePools. The platform takes two, keeping a minor of margin for a cluster found out of compliance mid-cycle. The ceiling is what turns the tenant's freedom into a deadline. A tenant may decline the worker window once and again, but a third deferral would breach the limit, and from that point the workers must roll before the control plane may advance, so the tenant's window becomes a dependency of the platform's own cycle rather than only their own concern. One minor was rejected because it forces a worker roll every cycle and removes the choice entirely. Three was rejected because it leaves no margin below the supported limit. |
| AD26 | The Inventory Controller Only Adds, Never Reclaims | The controller enforces a floor, not a band. Its only job is to keep enough machines in the pool, ten percent of demand or two, whichever is larger. When demand falls the pool is left above that floor and nothing is removed, because a spare machine carries no tenant state and is immediately available to another tenant. Data safety is handled at release instead: a released worker is destroyed rather than returned, so nothing is left on a disk or in MCE etcd (AD23). Lowering demand or the buffer only stops additions, and a pool never shrinks on its own. |
| AD27 | KV Capacity Controller on Each Seed MCE | One controller per Seed, and so per zone, keeps the zone's KubeVirt capacity ahead of VM demand. It does two things: it raises the active KV cluster's NodePool total when that cluster's free CPU falls below target, and it keeps one standby KV cluster built in the zone, starting a new one through `provision-cluster` when none exists. It writes nothing directly: node totals go through `update-nodepool` and new clusters through `provision-cluster`, because both are cluster-level state held in Git (AD22). It is separate from herzi. herzi, deployed on the same Seed, keeps the zone's `-metal` pools filled, so a node total raised by this controller is met from ready agents. This mirrors the tenant layer: the controller is to KV clusters what a tenant is to its hosted cluster, the writer of demand, while herzi supplies. It keeps no state, re-reads the clusters on every pass, holds a leader lease and has a dry-run mode. It runs on the Seed rather than in Wingman because the Seed already holds the KV clusters' credentials, a failure is bounded to one zone (AD17), and supply keeps flowing when the portal is down. |
| AD28 | KV Clusters Grow on Demand to 40 Nodes, Keeping 15% CPU Free | A zone starts with one KV cluster. The active cluster grows node by node to `target = used CPU × 1.15`, rounded up to whole nodes, with a hard maximum of 40 nodes set organisation-wide. Used CPU counts every VM's request, including Halted VMs, because kubevirt-redfish will start them. The 15% is the live-migration reserve required by the Uptime quality control, and because clusters bin-pack (AD30) it exists as whole empty nodes. A second cluster is opened only when the first has reached 40 nodes and its reserve, so capacity is never spread across several half-grown clusters. A standby cluster with 1 to 5 bare-metal workers is always ready. Its nodes absorb the first VMs after promotion while it grows, so VM creation never waits for a cluster to be built. Active and standby are not stored: the active cluster is the oldest in the zone with fewer than 40 nodes, a standby is any later cluster holding no VMs, and promotion happens by itself when placement overflows into the standby. Clusters only grow; none is shrunk, consistent with AD26. |
| AD29 | One Install Workflow for VM and Bare Metal | `add-server-to-mce` installs every machine. For a VM InfraEnv it first runs `create-vm` as a child, then installs that VM. The Inventory Controller orders every pool through one route, and an open install run always means one machine on its way. |
| AD30 | KV Clusters Bin-Pack at the Node Level | Each KV cluster runs the `HighNodeUtilization` scheduler profile and the descheduler's `CompactAndScale` profile, so VMs fill the fewest nodes and churn is compacted back by live migration. Without them the default scheduler spreads VMs and the 15% free CPU breaks into fragments too small to take a large VM during a drain. `KubeVirtRelieveAndMigrate` balances load and must not be enabled on the same cluster. |
| AD31 | Capacity Policy Lives in One Git File, Edited Through Wingman | The organisation-wide capacity values, `maxNodes` (40), `freeCpuPercent` (15), `standbyWorkers` (1 to 5) and `standbyClusters` (1), live in one file in the platform repo. ArgoCD renders it as a ConfigMap on every Seed. Wingman displays the file and edits it by merge request; it never calls a controller directly. `create-vm` and the KV Capacity Controller read the same values, because if placement's buffer and the growth target differ, placement either refuses before growth starts or growth starts too late. |
| AD32 | VM Placement Serialised per Zone | Without it, two `create-vm` runs read the same capacity at the same time, unaware of each other, and pick the same KV cluster, breaking its buffer. |
| AD33 | VMs Placed on the First KV Cluster That Fits, in Creation Order | It fills the oldest cluster before the next, which is the active and standby model of AD28. |

---

## 6 :: Risks

| ID | Risk | Mitigation Process | Mitigation Status |
|---|---|---|---|
| R1 | Cluster Operators may be degraded when hosted control plan are created but no nodepools (worker nodes) were attached, this may impact other process that lean on cluster operator health as a pre-requisite task | The automation checks whether a hosted cluster has worker nodes, if it does not, it bypasses the cluster operator health check | Not Implemented |
| R2 | Seed Cluster failure in a zone causes all KV cluster control planes hosted on it to stop responding. No new KV clusters can be created, no scaling or upgrade operations can run, and zone BM agent inventory stops being managed. Existing tenant workload VMs continue running — the data plane is independent of the control plane. | | Not Implemented |
| R3 | Live-migration headroom is sized per KV cluster but constrained per CPU generation (C8). A cluster with mixed hardware can hold the required 15% of untouched servers overall and still have nowhere to move a VM off its oldest generation, stalling hypervisor maintenance and the evacuation phase of an upgrade on a host that cannot be drained. | | Not Mitigated |
| R4 | | | |
| R5 | | | |
| R6 | | | |
| R7 | | | |
| R8 | | | |

---

## 7 :: Deployment View

### 7.1 Static Deployment View

![Deployment View](images/deployment-view.png)

### 7.2 Runtime Views

<!-- Add Node to Cluster, Create Hosted Cluster, and Node Reconcile Check runtime diagrams to be added here -->

---

## 8 :: Context & Scope

The OCP KubeVirt platform provides a fully automated, GitOps-driven lifecycle for creating, scaling, upgrading, and deleting OpenShift hosted clusters running on KubeVirt infrastructure. The system manages all infrastructure from physical bare-metal racks through to tenant-facing hosted clusters, while enforcing a read-only model for tenants — all changes flow exclusively through Git.

### 8.1 External Actors

| Actor | Interaction with the System |
|---|---|
| **RedBull Team** (SRE / Platform Admin) | Operates the platform infrastructure. Creates and manages Seed Clusters, KV Clusters, and Customer MCE instances. Triggers platform-level operations (cell expansion, MCE upgrades, emergency remediation) via Temporal workflows and GitOps pipelines. |
| **OCP Team** | Responsible for workload and OCP cluster optimisations, and for adapting customer workloads to Kubernetes. Enables customer adoption of the GitOps-only model — since hosted clusters are read-only (AD5), tenants who previously used `kubectl` for day-to-day changes must migrate to Git-based workflows. The OCP Team guides and supports tenants through this transition and ensures workloads are correctly configured to run on the hosted cluster platform. |
| **Tenant / Customer** | Consumes hosted clusters. Requests scale changes and upgrades via the self-service catalog or API. Selects upgrade windows. Has read-only access to the hosted cluster — all mutations must be submitted through Git and applied by ArgoCD. |

### 8.2 External Systems

| System | Role |
|---|---|
| **OCP Release Registry** | Source of OCP release images (e.g., `quay.io/openshift-release-dev/ocp-release`). Referenced by HostedCluster and NodePool manifests to pin or upgrade OCP versions. Governed by version skew constraints C3/C4. |
| **Physical DC / Network** | Provides the bare-metal servers, rack infrastructure, power, and physical network connectivity that underpin all zones and clusters. AZ boundaries (AD9) are derived from physical rack groupings. |
| **Identity Provider (LDAP / SSO)** | Authenticates SREs, the OCP Team, and tenants. Controls access to the self-service catalog, GitOps repository, and cluster consoles. |
| **Ticketing System** | Origin of scale and upgrade requests (e.g., Jira, ServiceNow). Requests flow from the ticket into the self-service catalog or directly to Temporal workflows. |
| **Monitoring & Alerting Stack** | Receives metrics, logs, and alerts from all clusters (Seed, KV, Customer MCE, Hosted Clusters). Provides Grafana dashboards for platform operators and tenants. External to the platform itself but a critical operational dependency. |
| **DNS** | Provides service discovery for API endpoints, ingress routes, and Redfish BMC addresses across all clusters and zones. Unique Redfish DNS per KubeVirt VM is required for cross-cluster VM live migration (AD11). |
| **Git Repository** | The single source of truth (AD5, AD13). All desired state — NodePool manifests, BMH definitions, NMState configs — lives here. Temporal writes to it; ArgoCD reads from it and applies to clusters. External teams interact with the platform by submitting pull requests. |

### 8.3 Context Diagram

<!-- Diagram to be added -->

---

## 9 :: Naming Conventions

| Object | Convention | Reason |
|---|---|---|
| **OCP Cluster** | Infrastructure: `<env>-<site>[-<zone>]-<type><nn>`<br>Hosted clusters: `<env>-<site>-hc-<tenant>`<br><br>Examples:<br>`neta-batyam-mce01`<br>`neta-batyam-z1-seed01`<br>`neta-batyam-z1-kv02`<br>`neta-batyam-hc-payments` | Ordered from largest scope to smallest so clusters group by prefix across network, site and zone. The name is immutable, so every segment must be something that never changes for the cluster's life |
| **NodePool** | TBD | |
| **InfraEnv** | `<internal-server-type>[-<variant>]-<zone>-<size>`<br>where `<size>` is `metal` for a physical server, or `small`, `medium` or `large` for a VM<br><br>Examples:<br>`conf203-zone-a-metal`<br>`conf203-zone-a-small`<br>`conf203-infiniband-zone-b-large` | The InfraEnv name is the pool key and the prefix used to draw candidates from Server Scanner. The server type is the internal name for a hardware configuration, and the optional variant marks any change to it such as infiniband, networking or disks. The hub is not part of the name, because the Temporal workflow id carries the MCE as its own segment |
| **VM / BM hostname** | Must match `^ocp-<infra_env>` | Server Scanner draws candidates by this prefix and parses the site from the hostname. VMs must follow the same convention as BM servers or they will neither land in a site nor match a draw |
| **KubeVirt Namespace** | TBD | A warm-pool VM belongs to no HostedCluster when it is created, so the namespace cannot be keyed on one |
| **BareMetalHost** | TBD | |
| **NMStateConfig** | TBD | |
| **BMC Secret** | TBD | |
| **Temporal Workflow ID** | `install-server-<mce>_<infra-env>_<slot>` for a pool slot, numbered 1 to 100<br>`install-server-<mce>_<server>` for a named install<br>`update-nodepool-<cluster>-<node-type>`<br><br>Example:<br>`install-server-ocp4-mce01_32-128-zone-a_7` | The workflow id is the deduplication key. Temporal allows one running workflow per id, so the id must be stable per target and must not contain the mutable value. The MCE segment carries the `ocp4-` prefix and is rejected without it. The hundred pool slots are a fixed allocation shared with the install route, so the slot id is also how the controller discovers whether a slot is busy |

---

## 12 :: Glossary

### Infrastructure

| Term | Definition |
|---|---|
| **AZ (Availability Zone)** | A logical failure domain composed of a fixed set of physical DC racks (e.g., Racks 1–5 = Zone A). Power, network, and cooling boundaries align with AZ boundaries. |
| **BM (Bare Metal)** | A physical server node. In this architecture, BM nodes are the foundation for both the Seed Cluster and KV Cluster worker nodes. |
| **Cell** | A bounded unit of infrastructure capacity. A cell encompasses one KV Cluster, its hosting Seed Cluster resources, and the associated MCE inventory pool. Cell boundaries define the maximum number of VMs allowed before a new cell is created. |
| **KV Cluster (KubeVirt Cluster)** | A HyperShift hosted cluster whose control plane runs as pods on the Seed Cluster and whose worker nodes are BM machines with KubeVirt enabled. KV clusters are where tenant workload VMs physically run. |
| **Seed Cluster** | A per-zone bare-metal cluster (UPI-installed) running MCE and HyperShift operators. Hosts the control planes of all KV clusters in its zone and serves as the zone's infrastructure management plane (AD17). |
| **VM Type** | One of three fixed sizes: small at 16 cores, medium at 32, large at 64. The size, the underlying server type and the zone together index inventory and form the InfraEnv name. A physical server takes `metal` in place of a size. |
| **ODF (OpenShift Data Foundation)** | Red Hat's shared storage solution. One candidate for the shared backend that KubeVirt Live Migration requires (C7). The selection is made in the storage design document. |
| **LVMO (LVM Operator)** | Local volume management operator. Provides local, not shared, storage, so it cannot support live migration (C7). |

### Platform / Operators

| Term | Definition |
|---|---|
| **MCE (Multicluster Engine)** | Red Hat's operator for managing multiple OpenShift clusters. Provides HyperShift, Assisted Installer, and agent-based provisioning. In this architecture there are two distinct MCE roles: the Seed Cluster MCE (infrastructure) and the Customer MCE (tenant hub). |
| **Customer MCE** | The tenant-facing Hub cluster. Manages InfraEnvs, agents, and hosted clusters for one version band of OCP. Masters: one VM per zone; workers: VMs distributed across zones (AD19, AD20). |
| **HCP (Hosted Control Plane)** | The control plane of a hosted cluster running as pods on the Hub or Seed Cluster, rather than on dedicated master nodes. Enables decoupling of control plane from data plane (AD1, AD18). |
| **HC (Hosted Cluster)** | A tenant OpenShift cluster whose control plane runs as an HCP on the Customer MCE and whose workers are VMs provisioned via MCE inventory. |
| **NodePool** | A HyperShift resource defining a group of worker nodes for an HC, targeting a specific zone and VM type. Each HC has three NodePools — one per zone. |
| **InfraEnv** | An MCE resource that generates a discovery ISO. VMs boot this ISO and register as agents in the MCE inventory. One InfraEnv exists per zone per VM type. |
| **Agent** | A VM that has booted the InfraEnv discovery ISO, completed hardware discovery, and registered with MCE. Available to be claimed by a NodePool. |
| **BMH (BareMetalHost)** | A Metal3 resource representing a physical or virtual bare-metal host managed by the Ironic provisioning engine. In this architecture, VMs are exposed as BMHs via the `kubevirt-redfish-controller` (AD3). |
| **UPI (User Provisioned Infrastructure)** | An OpenShift installation method where the operator manually provisions the underlying servers. Used for Seed Clusters because no automation layer exists yet at that stage. |

### Inventory & Capacity

| Term | Definition |
|---|---|
| **Warm Pool** | A stock of pre-provisioned VMs already registered in the MCE inventory as agents, waiting to be claimed. Enables deterministic, low-latency cluster provisioning (AD14). |
| **Low Watermark** | The floor of spare capacity in one pool on a Customer MCE, owned by the Inventory Controller. Expressed as a percentage of demand with a minimum number of machines beneath it, so the target is demand plus that buffer. Falling below it is what causes machines to be ordered. |
| **High Watermark** | The upper bound on a cell's VM count, owned by the infrastructure MCE rather than by the Customer MCE's Inventory Controller. Reaching it triggers creation of a new KV Cluster within the same zone. The controller that enforces it is not yet designed. |
| **Server Scanner** | A global service that bridges MCE, the Assisted Installer agent state, and the underlying KubeVirt hypervisors. Tracks the strict lifecycle state of every VM across all KV clusters and zones, indexed by zone and VM type (AD15). |
| **VM Lifecycle States** | The four states tracked by Server Scanner: **Available** — in warm pool, ready to be claimed; **In-Use** — assigned to a NodePool; **Quarantined** — isolated due to failure or suspicious behaviour; **Draining** — workloads migrating away, pending removal. |

### Orchestration

| Term | Definition |
|---|---|
| **Temporal** | Durable workflow orchestration engine used for all imperative, cross-cluster operations. Guarantees transactional safety by committing exclusively to Git (AD13). |
| **ArgoCD** | GitOps continuous delivery tool. Watches the Git repository and applies desired-state changes to clusters. The sole state applicator; no component applies changes directly to clusters (AD5). |
| **GitOps / SSOT** | The practice of using Git as the single source of truth for all cluster state. All changes flow through Git commits observed by ArgoCD, ensuring immutable, auditable state (AD5, AD13). |
| **DLQ (Dead Letter Queue)** | Temporal's mechanism for capturing workflows that have exhausted all retries. Failed operations are sent to the DLQ for manual investigation and remediation. |
| **Compensating Transaction** | An idempotent operation that reverses or neutralises the effect of a previous step when a workflow fails mid-execution (e.g., releasing a quarantined node back to the warm pool). |
| **Redfish** | A REST-based DMTF standard API for out-of-band server hardware management. Used by the `kubevirt-redfish-controller` to expose KubeVirt VMs as virtual BMCs, enabling MCE to treat them as bare-metal hosts (AD3). |
| **IPMI** | Intelligent Platform Management Interface. An alternative hardware management protocol used by Server Scanner alongside Redfish to query VM and host state. |

### Upgrades

| Term | Definition |
|---|---|
| **Upgrade Type (InPlace / Replace)** | The two ways a HyperShift NodePool moves its workers to a new release. `Replace` provisions a new node and removes the old one. `InPlace` drains, updates and reboots the existing node, keeping the same VM and the same agent. Tenant workers use `InPlace` (AD24). |
| **Version Skew** | The difference in OCP minor version between the MCE Hub and the hosted clusters it manages. Constrained by C3 and C4 (MCE supports current OCP version ± up to 3–4 minor versions). |
| **Version Band** | A range of HC OCP versions managed by a single Customer MCE instance. Multiple MCE instances at different versions coexist to serve hosted clusters across different upgrade stages. |
| **Konnectivity** | A network tunnelling component that provides connectivity between the hosted cluster control plane (running on the Hub) and the worker nodes. Degradation silently breaks `kubectl exec`, logs, and webhooks. |
