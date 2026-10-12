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
| SC5 | Scalability | The platform autonomously manages its own infrastructure capacity, provisioning new cells before existing ones reach saturation and decommissioning underutilized cells to reclaim resources |

### 2.1 :: Quality Scenarios

| ID | Quality Scenario | Description |
|---|---|---|
| SC1.1 | Ease of Use | A user who does not understand the solution can study it and operate it after familiarizing himself with documentation |
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
| C2 | Hosted cluster can be only deployed on single kubevirt clusters |
| C3 | Each MCE release supports the current OCP version plus several previous versions (typically up to $N - 3$ or $N - 4$ minor versions) |
| C4 | You cannot deploy or upgrade a Hosted Cluster to an OCP version newer than what your installed MCE Operator supports |
| C5 | It is impossible to accurately predict tenant cluster growth which may impact SLA when kubevirt clusters are full |
| C6 | A single HostedCluster's NodePools cannot span multiple MCE Hubs. The HostedCluster control plane runs on one MCE Hub, and that Hub must manage all NodePools for that cluster. This constrains tenant-to-Hub affinity and impacts capacity planning |
| C7 | KubeVirt Live Migration requires shared storage. VMs can only live-migrate between hypervisor nodes that share a storage backend (ODF). This is a KubeVirt/libvirt constraint that forced AD2 (ODF over LVMO). It also means live migration cannot cross AZ boundaries if ODF clusters are AZ-scoped |
| C8 | |

---

## 4 :: Quality Controls

|  | OCP Kubevirt cluster creation | OCP Kubevirt cluster Modification | OCP Kubevirt cluster Upgrade | OCP Kubevirt cluster Deletion |
|---|---|---|---|---|
| **Ease of Use** | 1. Self-service catalog exposes pre-packaged NodePool profiles abstracting Agent/Redfish complexity. 2. AZ allocation and KV/MCE placement complexity is hidden from users to ensure a smooth customer experience | 1. Common modification processes appear in the customer-facing interface as self-service features, eliminating the need to call or explain changes manually | 1. A self-service upgrade process is available for tenants so they can choose the upgrade window themselves | |
| **Autonomy** | 1. Each component in the solution is created before demand arrives to avoid waiting for other resources. For example, VMs are pre-registered in the registry before a hosted cluster claims them | 1. Automated unhealthy worker VM remediation (via Node Health Check) occur without human SRE intervention. | 1. SRE can update master pods independently of tenant workers. 2. NodePool controllers autonomously drive the rolling upgrade state machine (surge, cordon, drain, replace) across isolated AZs (ADB) without manual inspection. | |
| **Performance Efficiency** | 1. VMs allocated with 1:1 CPU/memory at KubeVirt level (AD16 — no hypervisor overcommit). 2. To ensure performance, cell boundaries are created for the KV cluster, hub cluster and hosted cluster. Check the cell boundaries with stress tests | 1. Pre-flight capacity checks confirm target hypervisors, Hub, and HostedCluster do not exceed cell boundaries. If they do, the request is routed to a different cell with headroom or rejected with capacity feedback. | 1. Rolling Machine Replacements are configured with a strict surge strategy (`maxSurge > 0`, `maxUnavailable = 0`); new worker VMs are fully provisioned before old nodes are drained, ensuring tenant compute capacity never drops during updates | |
| **Operational Efficiency** | 1. Cluster creation process is documented and tested to ensure no question asked during manual creation. 2. VMs are pre-registered to the to the MCEs inventory to minimize creation time. 3. VMs are dynamically created on BM nodes and added to server scanner to fulfill inventory requirements | 1. Background reconciliation loop evaluates MCE desired state vs. actual node count at a configurable interval and adds nodes accordingly. 2. Concurrent scale requests for the same cluster are serialized via Temporal workflow locking to prevent conflicting Git commits | 1. Separating Hub control plane updates from KubeVirt worker updates ensures that unpredictable tenant workload drain times cannot delay or block API availability. 2. Nodes can be loaned deterministic to allow a complete replacement of old nodes with newer nodes version by replacing old nodepool with new nodepool | 1. Deleted nodes return to inventory. If the inventory exceeds the required node count, excess nodes are removed from inventory and marked as available in the server scanner |
| **Resiliency** | 1. Control plane pods (Hub) and worker VMs (KubeVirt) are strictly provisioned using `podAntiAffinity` and `topologySpreadConstraints` to ensure no single hardware rack or AZ failure can take down a tenant's quorum. 2. Worker VMs are labeled with the hosted cluster name to evaluate `topologySpreadConstraints` against | 1. If underlying hypervisors require maintenance or exhibit partial degradation, KubeVirt Live Migration shifts active tenant worker VMs to healthy hosts without dropping network connections. 2. if a scale-up VM fails to join the cluster within a defined timeout, Temporal selects an alternative node from inventory and executes a compensating transaction to release the failed node back to quarantine. | 1. Hub control plane upgrades roll sequentially (e.g., `maxUnavailable=1`), ensuring ETCD and API servers retain a functional 2-of-3 quorum even if an AZ drops mid-upgrade. 2. Because upgrades use a surge replacement strategy, a failure in the upgrade process may only impact new nodes leaving older nodes intact. older nodes will evacuate only when new nodes provisioned successfully | 1. Deletion ensures the node has no workloads before removal from the cluster |
| **Uptime** | 1. Control plane components (3x API / 3x ETCD) and worker VMs are scheduled across 3 physical Availability Zones using strict `podAntiAffinity`. No single AZ failure causes API unavailability. | 1. Pre-flight health checks validate control plane health (API server responding, ETCD quorum intact, no degraded ClusterOperators) before executing any modification. If any check fails, the operation is queued and the requestor is notified. 2. KV clusters must have at least 15% of untouched servers for vmotion | 1. Pre-flight validates cluster health, ETCD backup taken, and no in-progress operations before starting. Rolling upgrade uses `maxSurge > 0`, `maxUnavailable = 0` for workers. 2. Control plane upgrades maintain ETCD 2-of-3 quorum throughout. 3. MCE upgrades must precheck hostedclusters version and calculate the version skew policy. 4. KV cluster must evacuate VMs before updating worker nodes | |
| **Resources efficiency** | 1. Worker VMs drawn from pre-provisioned MCE inventory (warm pool). Background process detects inventory drop and provisions replacement VMs on bare-metal nodes to replenish pool. Pool depth maintained above defined low watermark. 2. VM ratio of 1:8 is selected to eliminate waist of bare-metal resources | 1. Unused resources bounded to a user can be consumed by different user to a limited time | | |

---

## 5 :: Architectural Decisions

| ID | Decision | Reason |
|---|---|---|
| AD1 | Hypershift as control plan | Decoupling the control plane (running as pods on the Hub) from the data plane drastically reduces resource overhead and accelerates cluster provisioning times compared to traditional standalone OCP clusters. |
| AD2 | ODF (Shared) instead of LVMO (Local) Storage | ODF is selected as the primary storage provider. Shared storage is a strict prerequisite to enable KubeVirt Live Migration of VMs across physical hosts during hardware maintenance or failure. |
| AD3 | VM Lifecycle via Agent-Based Bare Metal Provisioning | Utilizing the `kubevirt/redfish-controller`, KubeVirt VMs are exposed with Virtual BMCs. This allows MCE and the Agent-based Installer to provision and manage VMs identically to physical bare-metal servers, unifying the automation pipeline. |
| AD4 | Bare metal to Kubevirt rolling migration | Using `kubevirt/redfish-controller` allowing rolling migration by adding VMs to hosted cluster and removing bare metal nodes that later can be added to KV cluster as worker nodes |
| AD5 | Zero-Trust Tenant Environments (GitOps Only) | Clusters are deployed with strict Read-Only access for tenants. Application and state management is exclusively driven via GitOps (ArgoCD). Banning manual `kubectl` intervention guarantees immutable state, enabling clean cluster restore procedures. |
| AD6 | Decoupled PVC Lifecycles (Static NFS over CSI) | PVC lifecycles are explicitly not managed via CSI drivers. Tested and verified static NFS provisioning detaches storage from the cluster lifecycle, providing the precise control needed to migrate or restore application state to a different cluster during DR. |
| AD7 | Topology-Aware Node Placement | We utilize standard `topologySpreadConstraints` to enforce per cluster worker VM distribution across physical BM nodes |
| AD8 | Isolated KubeVirt Clusters per AZ | KubeVirt clusters are strictly scoped to a single physical AZ. AZ redundancy for tenants is achieved by configuring a single `HostedCluster` with three distinct `NodePools`, each targeting a different KubeVirt cluster. A total KV cluster failure will only impact one AZ of the tenant's environment. |
| AD9 | Logical AZ Rack Segmentation | Physical data center racks are logically segmented into Availability Zones (e.g., Racks 1-15 = AZ1, Racks 16-30 = AZ3) to translate physical power/network boundaries into Kubernetes scheduling domains. |
| AD10 | Stretched Hub (MCE) Cluster Topology | The MCE Hub cluster is deployed on bare-metal nodes stretched across 3 distinct AZs to guarantee absolute management plane redundancy. |
| AD11 | Unique Redfish DNS per KubeVirt VM | This enables future flexability for cross-cluster VM live migration |
| AD12 | Dedicated KubeVirt Namespace per HostedCluster | Aligning with CAPK native behavior, every HostedCluster maps to a unique dedicated namespace on the target KubeVirt cluster. This allows direct HostedCluster-to-VM traceability and simplifies pod anti-affinity rules. |
| AD13 | Temporal for Imperative Orchestration | Complex, cross-cluster workflows (e.g., node reallocation, inventory refilling) are governed imperatively via Temporal. Temporal guarantees transactional safety by exclusively mutating the declarative SSOT (GitOps), maintaining ArgoCD as the sole state applicator. |
| AD14 | Asynchronous VM Warm Pools | To guarantee deterministic, low latency cluster provisioning, KubeVirt VMs are pre-provisioned asynchronously into an unassigned MCE inventory. Tenant creation requests draw from this ready inventory. |
| AD15 | Server Scanner as Unified State Tracker | A custom Server Scanner service bridges the visibility gap between MCE, the Agent, and the underlying KubeVirt hypervisors, tracking the strict lifecycle state (In-Use, Available, Draining) of virtual bare-metal capacity. |
| AD16 | No CPU/Memory Overcommitment on KubeVirt Infrastructure | The KubeVirt hypervisor layer runs with dedicated (1:1) CPU and memory allocation per VM. This eliminates the risk of double overcommitment, if both the KubeVirt scheduler and the tenant's OCP scheduler independently overcommit, resource contention compounds unpredictably, violating SC2 (Predictability). Overcommitment decisions are deferred to the tenant level, each HostedCluster's OCP scheduler may overcommit within its own allocated VM resources, where the blast radius is contained to that tenant. |

---

## 6 :: Risks

| ID | Risk | Mitigation Process | Mitigation Status |
|---|---|---|---|
| R1 | Cluster Operators may be degraded when hosted control plan are created but no nodepools (worker nodes) were attached, this may impact other process that lean on cluster operator health as a pre-requisite task | The automation checks whether a hosted cluster has worker nodes, if it does not, it bypasses the cluster operator health check | Not Implemented |
| R2 | | | |
| R3 | | | |
| R4 | | | |
| R5 | | | |
| R6 | | | |
| R7 | | | |
| R8 | | | |

---

## 7 :: Deployment View

### Add Node to Cluster

<!-- Diagram: PreChecks → Deployment → Post Checks flow for adding a node to a cluster -->
<!-- Original diagram to be embedded here -->

### Create Hosted Cluster

<!-- Diagram: PreChecks → Deployment → Post Checks flow for creating a hosted cluster -->
<!-- Original diagram to be embedded here -->

### Node Reconcile Checks

<!-- Diagram: Event-driven reconciliation flow -->
<!-- Original diagram to be embedded here -->

---

## Technical Decisions (Open)

| ID | TD |
|---|---|
| TD1 | Create helm for MCE, KV, HostedCluster, VM |
| TD2 | Create Flows for Hosted cluster, KV cluster, Update cluster node count, |
| TD3 | Create decisions for server→ rack → AZ, KV, MCE, hosted, server headroom, |
| TD4 | Research about MCE version policies |
| TD4 | Automate flow from task TD2 |
| TD5 | Create dashboards (TBD) |

### Open Items

1. AZ configuration
2. Git Repo layout
3. Decision criteria of which KV cluster new hosted cluster will use
4. Decide on allocations of nodes to hostedcluster SLA
5. Node benchmarks
6. Leaf sizes and control
7. Node types and cpu to memory ratio

### Test Cases

- create 28 VMs of 8/32 using 2:1 CPU overcommitment ratio \* num of workers
- create 14 VMs of 8/64 using with no overcommitment \* num of workers
