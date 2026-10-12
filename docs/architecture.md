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
| AD17 | Seed BM Cluster per Zone as Infrastructure Management Plane | Each availability zone has a dedicated bare-metal cluster (Seed Cluster) installed via UPI, running MCE and HyperShift operators. The Seed Cluster is the zone's infrastructure management plane: it hosts the control planes of all KV clusters in that zone as HyperShift hosted clusters, and manages their lifecycle. Keeping the Seed Cluster per-zone (rather than stretching one management cluster across zones) ensures that a full Seed Cluster failure impacts only one zone's infrastructure management, leaving tenants in other zones unaffected. BM nodes are used for the Seed Cluster to avoid a bootstrapping dependency on the very VMs the cluster is responsible for creating. |

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

### 7.1 Static Deployment View

![Deployment View](deployment-view.png)

### 7.2 Runtime Views

<!-- Add Node to Cluster, Create Hosted Cluster, and Node Reconcile Check runtime diagrams to be added here -->

---

## HIGH — Production Prerequisites

| ID | Source | Category | Task |
|---|---|---|---|
| H1 | TD1 | GitOps | **Create Helm charts for MCE, KV, HostedCluster, and VM resources.** These are the foundational GitOps artifacts — ArgoCD (AD5) has nothing to sync without them. Blocks all automation workflows. |
| H2 | TD2 | Orchestration | **Create Temporal saga workflows for: Hosted Cluster creation, KV cluster provisioning, and node count updates.** Each workflow must commit to Git only (AD13), observe ArgoCD convergence, and execute compensating transactions on failure. |
| H3 | SC1.1 × R1, SC1.1 × R2 | Self-Service | **Build self-service catalog with pre-packaged NodePool profiles.** Must abstract Agent/Redfish complexity (AD3) and hide AZ allocation / KV-MCE placement logic from users. Include OpenAPI schema validation and GitOps pre-commit checks to reject invalid parameters (overlapping CIDRs, duplicate cluster names) before triggering pipelines. |
| H4 | SC1.2 × R1, SC2.2 × R1, SC4.1 × R1 | Provisioning | **Implement warm pool (MCE inventory) pre-provisioning pipeline.** VMs must be pre-registered in MCE inventory before hosted clusters claim them. Background process provisions VMs on bare-metal nodes, maintains pool depth above defined low watermark, and alerts on depletion. Includes the 1:8 VM-to-BM ratio enforcement. |
| H5 | AD15, SC2.2 × R1 | State Mgmt | **Build Server Scanner as live CMDB.** Must track strict VM lifecycle states (Available, In-Use, Quarantined, Draining) across KubeVirt hypervisors and MCE inventory. Provides capacity queries to Temporal for placement decisions and to dashboards for operational visibility. |
| H6 | SC3.1 × R1, SC3.2 × R1 | Scheduling | **Configure pod scheduling topology across 3 AZs.** Implement `podAntiAffinity` for control plane pods (Hub) and `topologySpreadConstraints` for worker VMs. Worker VMs must be labeled with their hosted cluster name to evaluate spread constraints. Guarantees no single rack or AZ failure takes down a tenant's quorum. |
| H7 | SC3.2 × R2, SC3.2 × R3, SC2.1 × R2 | Health | **Implement pre-flight health check engine.** Before any modification or upgrade: validate API server responding, ETCD quorum intact, no degraded ClusterOperators, target hypervisors have sufficient 1:1 capacity (AD16). If any check fails, queue the operation and notify the requestor. For upgrades: additionally verify ETCD backup taken and no in-progress operations. |
| H8 | SC1.2 × R2, SC3.1 × R2 | Remediation | **Implement Node Health Check with automated unhealthy VM remediation.** Detect unhealthy worker VMs, quarantine them, draw replacement from warm pool, and coordinate fencing and replacement through Git via Temporal — all without human SRE intervention. If replacement VM fails to join within timeout, select alternative node and quarantine the failed one. |
| H9 | SC2.1 × R2, Open item #3 | Capacity | **Build capacity-aware cell placement and routing logic.** Formalize which KV cluster receives new VMs based on cell utilization, 1:1 resource availability (AD16), and health status. If target cell lacks headroom, route to a different cell or reject with capacity feedback. Feeds into the future policy engine (AD17). |
| H10 | R4 controls, SC2.2 × R4, SC3.1 × R4 | Lifecycle | **Complete cluster deletion workflow.** Create Temporal saga, runtime view diagram, and resource reclamation logic. Sequence: remove `deletionProtection` → delete NodePool manifests → wait for VM termination → delete HostedCluster manifest → clean up namespace/network. Verify workloads drained before node removal. Return deleted nodes to inventory; remove excess nodes and mark as available in Server Scanner. |
| H11 | TD3, Open items #1, #3, #4 | Architecture | **Define infrastructure topology decisions: server → rack → AZ → KV → MCE → hosted mappings.** Includes AZ configuration, decision criteria for which KV cluster hosts new HostedClusters, and node-to-hostedcluster SLA allocation rules. These are prerequisites for the placement engine (H9). |
| H12 | TD4 (automate) | Automation | **Automate Temporal workflows from TD2.** Move from manual/tested flows to fully automated pipelines triggered by self-service catalog events. Includes end-to-end GitOps integration: catalog request → Temporal workflow → Git commit → ArgoCD sync → convergence observation. |
| H13 | Risks R2-R8 | Risk Mgmt | **Populate risk register R2-R8.** Identified failure modes to document: network partition (Hub ↔ KV), warm pool exhaustion under burst, MCE version skew during rolling upgrades, live migration failure cascade, Temporal outage impact, ODF storage saturation, Konnectivity tunnel degradation. |

---

## MEDIUM — Operational Maturity

| ID | Source | Category | Task |
|---|---|---|---|
| M1 | SC2.2 × R2 | Reconciliation | **Build background MCE reconciliation loop.** Evaluate MCE desired state vs. actual node count at a configurable interval and add nodes accordingly. Must detect inventory shortfalls and trigger warm pool replenishment. |
| M2 | SC2.2 × R2 | Concurrency | **Implement Temporal workflow locking for concurrent cluster operations.** Concurrent scale requests for the same cluster must be serialized to prevent conflicting Git commits. Includes lock acquisition, timeout, and dead-lock prevention. |
| M3 | SC2.1 × R3, SC3.1 × R3 | Upgrades | **Configure rolling upgrade with strict surge strategy.** Set `maxSurge > 0`, `maxUnavailable = 0` on NodePool controllers. Surge VMs allocated from warm pool. Ensure tenant compute capacity never drops below pre-upgrade levels. If surge would deplete warm pool below critical watermark, reduce upgrade parallelism. |
| M4 | SC3.1 × R2, AD2, AD4, C7 | Resilience | **Set up and validate KubeVirt Live Migration for hypervisor maintenance.** Requires ODF shared storage (AD2). VMs live-migrate to healthy hosts without dropping network connections. Must validate migration doesn't cross AZ boundaries (C7). Define failure handling: retry → cold-migrate fallback → alert. |
| M5 | TD4, SC3.2 × R3 | Versioning | **Research and implement MCE version skew policies.** MCE upgrades must precheck hostedclusters versions and calculate version skew against C3/C4 constraints. Design rolling cross-AZ upgrade strategy handling version differences between Hubs. Prevent tenants from requesting versions ahead of their MCE Hub's support. |
| M6 | SC2.2 × R3 | Upgrades | **Separate Hub control plane upgrade path from KubeVirt worker upgrade path.** Hub updates must not block tenant operations. Worker NodePool manifests updated per-AZ in Git, triggering zone-by-zone rolling replacement independently of Hub lifecycle. |
| M7 | SC3.2 × R3 | Upgrades | **Implement KV cluster VM evacuation before worker node updates.** Before updating KubeVirt cluster worker nodes, all tenant VMs on affected nodes must be evacuated via live migration. Ensures no tenant disruption during infrastructure-level updates. |
| M8 | SC3.2 × R2 | Capacity | **Enforce minimum 15% vmotion headroom on KV clusters.** KV clusters must retain at least 15% of servers untouched (no tenant VMs) to serve as live migration targets during maintenance. Pre-flight checks must block modifications that would violate this threshold. |
| M9 | SC4.1 × R1, Open items #5, #6, #7 | Capacity | **Define node types, VM sizes, CPU/memory ratios, and VM-per-host ratios.** Codify the 1:8 VM-to-BM ratio. Determine which VM sizes (e.g., 8/64) to offer as standard profiles. Validate fit with AD16 (1:1 at KubeVirt level). Feed results into placement engine and self-service catalog profiles. |
| M10 | Open item #2 | Architecture | **Design Git repository layout for all manifest types.** Structure for MCE, KV, HostedCluster, NodePool, and ArgoCD Application manifests. Layout directly impacts ArgoCD application topology, drift detection granularity, RBAC, and team access control. |
| M11 | TD5, SC1.1 × R3 | Observability | **Build Grafana dashboards for platform operators and tenants.** Platform: warm pool inventory levels, provisioning latency, cell utilization heatmap, ArgoCD sync health. Tenant: upgrade progress, cluster health status, stalled upgrade notifications. Serves SC1.1 (Ease of Use). |
| M12 | SC2.2 × R1 | State Mgmt | **Implement Server Scanner ↔ MCE inventory reconciliation.** Server Scanner must reconcile against MCE inventory as source of truth. Divergence (Scanner says "Available" but MCE has host in error state) must be detected and resolved before Temporal selects nodes for placement. |
| M13 | SC3.1 × R2 | Resilience | **Build compensating transaction framework.** Temporal must handle: Git commit revert on failure, node quarantine on join timeout, alternative node selection and retry, and dead letter queue for exhausted retries. Each compensation step must be idempotent. |
| M14 | Risk R1 | Risk | **Implement Risk R1 mitigation: cluster operator health bypass when no nodepools attached.** Automation must check whether a hosted cluster has worker nodes before evaluating cluster operator health. Skip health check on control-plane-only clusters to prevent blocking downstream processes. |
| M15 | SC3.1 (critique) | HA | **Deploy Temporal in HA configuration.** Cross-AZ topology (3-node minimum), persistent storage backend, and documented workflow recovery behavior on restart. Temporal is the orchestration brain — its unavailability blocks all provisioning, scaling, and compensating transactions. |

---

## LOW — Hardening & Operational Excellence

| ID | Source | Category | Task |
|---|---|---|---|
| L1 | SC1.1 × R3 | Self-Service | **Build tenant self-service upgrade portal with version filtering.** Surface available target versions filtered by MCE compatibility (C3/C4). Allow tenants to select upgrade window. Display upgrade progress and stall notifications via dashboards. |
| L2 | SC4.1 × R2 | Efficiency | **Design resource sharing/lending mechanism for idle tenant-bounded resources.** Unused resources bounded to a user can be consumed by a different user for a limited time. Requires resource reclamation SLA, tenant notification, and graceful eviction when the original tenant needs capacity back. |
| L3 | SC1.2 × R3 | Automation | **Configure auto-rollback on post-upgrade health check failure.** If NodePool controller detects health degradation after upgrading worker nodes, automatically roll back to previous version. Requires health check definition, rollback trigger threshold, and notification to tenant. |
| L4 | SC2.2 × R3 | Upgrades | **Implement deterministic node loaner/replacement via nodepool swap.** Nodes can be loaned deterministically to allow a complete replacement of old nodes with newer versions by replacing old nodepool with new nodepool. Ensures clean upgrade path without in-place mutation. |
| L5 | SC3.2 × R3 | Upgrades | **Implement MCE upgrade hostedcluster version pre-check.** Before upgrading an MCE Hub, pre-check all hosted clusters' versions and calculate version skew policy compliance. Block MCE upgrade if it would violate C3/C4 for any hosted cluster. |
| L6 | AD17, SC5 | Scaling | **Implement cell scaling policy engine (AD17).** Centralized, configurable policy engine governing cell lifecycle: creation triggers at high watermark, drain triggers at low watermark, cooldown/hysteresis to prevent flapping, provisioning lead time awareness (~30-60 min). Configuration-driven, not code-driven. |
| L7 | Cross-cutting | Observability | **Build ArgoCD drift detection alerting.** Surface sync failures and out-of-sync resources to Temporal workflows and SRE dashboards. The saga pattern assumes ArgoCD syncs successfully — silent failures create invisible state divergence. |
| L8 | Critique #1 | Networking | **Implement MCE Hub ↔ KV cluster connectivity monitoring with Temporal circuit-breaker.** Dedicated health probes from each MCE Hub member to each KV cluster API. If connectivity degrades, Temporal stops scheduling NodePool operations for that AZ until connectivity is restored. |
| L9 | Critique #2 | Networking | **Monitor Konnectivity tunnel health as a first-class SLI per HostedCluster.** Tunnel degradation silently breaks `kubectl exec`, logs, metrics, and webhooks while all components appear healthy individually. Define alerting thresholds and remediation actions. |
| L10 | SC2 measurement | Testing | **Define SLA benchmarking framework.** Establish provisioning latency baselines (P50/P95/P99), cluster health check definitions, and AZ failover recovery time targets. Required to measure SC2 (Predictability) and SC3.2 (99.95% uptime) compliance. |
| L11 | SC2.1 × R1 | Testing | **Run cell boundary stress tests.** Validate cell capacity limits with stress tests at 1:1 CPU/memory allocation (AD16). Confirm the 14 VMs of 8/64 (no overcommitment) test case. Revise or remove the 28 VMs of 8/32 with 2:1 overcommit test case (contradicts AD16). |
| L12 | Operations | Runbooks | **Design operational runbooks.** Cover: Temporal DLQ handling, fenced node investigation, AZ isolation response, warm pool emergency replenishment, live migration failure escalation, partial deletion recovery. |
