# Architecture & Procedures Gap Analysis

Last reviewed after completing Procedures 01–03.

---

## Architecture Document Gaps

### Empty / Placeholder Sections

| Section | Status | Notes |
|---|---|---|
| C8 | Empty | Last constraint row — blank since original PDF |
| R2 | Risk documented, mitigation empty | Seed Cluster failure — mitigation not agreed yet |
| R3–R8 | All empty | 6 risks not yet identified or written |
| 7.2 Runtime Views | Placeholder only | Was in original PDF — Add Node, Create Hosted Cluster, Node Reconcile |
| 8.3 Context Diagram | Placeholder only | Diagram to be drawn and embedded |
| Building Block View | Missing entirely | No component structure diagram exists anywhere in the doc |

### Missing Architectural Decisions

| Gap | Why it matters |
|---|---|
| How ignition configs are applied to KubeVirt VMs | Procedures 02 and 03 reference "boot VM with ignition" but KubeVirt VMs can't be booted with ignition the same way BM nodes can. The mechanism is undocumented. |
| kubevirt-redfish-controller installation and placement | AD3/AD4 depend on it. No AD captures where it runs, how it is installed, or how it is configured. Skipped entirely in all procedures. |
| ArgoCD installation and Git repository structure | AD5/AD13 depend on ArgoCD being operational. No decision on where ArgoCD runs, how the Git repo is structured, or how ArgoCD Applications are created. M10 flags this as open. |
| Multiple Customer MCE version bands lifecycle | Deployment view shows MCE 4.18 and 4.22 coexisting. No AD captures when to create a new Customer MCE, when to decommission an old one, or how tenants migrate between version bands. |
| Server Scanner API and data model | AD15 references Server Scanner as a component. Procedure 03 uses `curl /api/vms?...` and `PATCH /api/vms/<id>` but this API is not defined anywhere. |

---

## Procedure Gaps

### Items Used in Procedures But Not Defined

| Item | Used in | Issue |
|---|---|---|
| Server Scanner REST API | Procedure 03 | URL pattern and data model assumed — not specified |
| Bootstrap node | Procedures 01, 03 | Term used but not in Glossary |
| Ignition application to KubeVirt VMs | Procedure 03 | Mechanism for applying ignition to a running/stopped KubeVirt VM is not described |

### Missing Foundation Procedures

These procedures are dependencies of the 3 completed ones but do not exist yet.
They should be created before or alongside the remaining infrastructure procedures.

| Missing Procedure | Blocks | Notes |
|---|---|---|
| Install kubevirt-redfish-controller | Procedure 02 (KV Cluster) | VMs need to be exposed as BMCs before agents can register |
| Install ArgoCD + configure Git repository | Procedures 02, 04–07 | GitOps pipeline assumed operational in scaling/upgrade procedures |
| Create InfraEnvs for warm pool (`32-128-<zone>`, `bm-<zone>`) | Procedure 03 (Customer MCE) | Procedure 03 starts from "VMs already registered as agents" but no procedure creates the InfraEnvs that enable this |
| Install Temporal + deploy workers | Procedures 06–15 | AD13 depends on Temporal; no setup procedure exists |
| Seed Cluster kubeconfig distribution | All procedures | Procedures reference `--kubeconfig=<seed-kubeconfig>` but no procedure obtains or distributes it |

### Procedure Ordering Issue

Procedure 03 (Customer MCE) starts from "KV Clusters running and warm pool available" but:
- InfraEnvs don't exist yet (no procedure created them)
- VMs aren't registered as agents yet (depends on InfraEnvs)
- A step between Procedure 02 and 03 is missing

---

## Ideas

| Idea | Rationale |
|---|---|
| Split "Infrastructure Setup" into Zone tier and Platform tier | Zone infrastructure (Seed, KV, ArgoCD, Temporal, kubevirt-redfish) is a prerequisite for Platform (InfraEnvs, warm pool, Customer MCE). Currently both are lumped as "Infrastructure Setup." |
| Reusable Pre-flight Check procedure | Quality Controls reference pre-flight checks for almost every operation. A standalone pre-flight procedure that others call would reduce repetition and make it testable independently. |
| MCE version band lifecycle procedure | How to create a new Customer MCE at a new OCP version, how tenants migrate between version bands, and when to decommission an old MCE. Significant operational gap given the multi-MCE deployment model. |
| Server Scanner API spec | Foundational for Procedures 13, 15 and the Controller. Should be specified before those procedures are written. |

---

## Suggested Priority Order

1. **Server Scanner API** — blocks Procedures 13, 15 and the Controller (Procedure 15)
2. **Missing foundation procedures** — kubevirt-redfish, ArgoCD/Git, InfraEnvs, Temporal
3. **Risks R3–R8** — fill the risk register
4. **R2 mitigation** — agree and document
5. **Runtime Views (7.2)** — the 3 flows from the original PDF
6. **Building Block View** — component structure diagram
