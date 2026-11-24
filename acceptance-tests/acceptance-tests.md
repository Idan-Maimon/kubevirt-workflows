# OCP KubeVirt Platform - Acceptance Tests

## 1. Purpose of the Document

To document the acceptance tests related to the implementation of the OCP KubeVirt platform.

## 2. Normative

### Normative Language Interpretation

For the purposes of this document, the following terms are to be interpreted as normative
requirements.

The word "must" indicates an absolute requirement and denotes a condition that is mandatory for
compliance.

The word "should" indicates a recommended practice, which is not mandatory but is strongly advised
unless a justified alternative is documented.

The word "may" indicates a permissible action and grants discretion without obligation. The word
"could" indicates a possible option or capability and does not imply a requirement or
recommendation.

A "test passed" condition indicates that all mandatory criteria defined in the applicable test
procedure have been satisfied and the system is considered compliant with the specified
requirement.

A "test failed" condition indicates that one or more mandatory criteria have not been satisfied,
and the system is considered non-compliant until corrective actions are taken and the test is
successfully re-executed.

A "test NA" condition indicates that the test could not be executed because a component it depends
on is not yet available. A test marked NA must be executed once that component is delivered.

### GITOPS (MUST REQUIREMENT)

The platform's cluster-level state, including HostedClusters, NodePools, InfraEnvs and cluster
configuration, MUST be deployed, configured and managed exclusively via a GitOps workflow (using
ArgoCD). Machine-level objects, including VirtualMachines, BareMetalHosts, NMStateConfigs, BMC
Secrets and Agents, MUST be created, changed and removed only by the platform's workflows
(architecture AD22). Manual intervention, direct kubectl commands for persistent configuration
changes, or console-based modifications are strictly prohibited and will result in a "Failed" test
result unless explicitly documented as a temporary troubleshooting step. All changes, rollbacks and
updates must be trackable and reproducible through version control and the workflow's history.

All commits made by a person to the Git repositories governing the platform must explicitly
reference the applicable test name and test identifier in the commit message. This reference must
be clear, unambiguous and traceable to the corresponding validation or compliance test. Commits made
by a platform workflow carry that workflow's id; the Evidence Document must map each such workflow
id to its test. Commits that cannot be traced to a test will be considered non-compliant and will
result in a "Failed" test result until corrected. This requirement applies to all changes, including
configuration updates, feature additions, fixes and rollbacks, and is intended to ensure full
auditability and traceability between changes and test outcomes.

### Evidence Document

For all tests whose acceptance criteria cannot be fully validated through Git history, ArgoCD
status or configuration review alone, an additional Evidence Document must be supplied. This
document must enumerate all relevant evidence (workflow ids and their history, commands and their
output, metric names and their measured values) and its explicit correlation to the applicable test
name and test identifier. Each item must be clearly annotated with pass/fail coloration (e.g., green
for compliant, red for non-compliant) relative to the defined acceptance criteria.

---

## 3. Provisioning (R1)

In this section the provisioning process, defined in `docs/procedures`, will be checked to confirm
the platform's readiness to create clusters from pre-provisioned inventory, with no human step.

**Prerequisites:**

1. Customer MCE `ocp4-test-mce-five-a` at site `five`, with admin access
2. One seed cluster per zone: `ocp4-test-seed-five-az1-a`, `-az2-a`, `-az3-a`; KV clusters
   `ocp4-test-kv-five-az2-a` and `ocp4-test-kv-five-az3-a` (az1's KV cluster is created in P1)
3. InfraEnvs on the MCE: bare metal `c200-mtl-az1/2/3`; VMs `c200-kv16-az1/2/3` and `c200-kv32-az1/2/3`
4. The platform workflows and the Inventory Controller deployed
5. Access to the day1 repository, ArgoCD, Temporal, server-scan and segments-manager

A cluster's day1 file is `sites/five/mces/ocp4-test-mce-five-a/hostedClusters/<cluster>.yaml`; its
ArgoCD Application is named after the file; its NodePools are `<cluster without ocp4->-<InfraEnv>`.
The KV cluster `ocp4-test-kv-five-az1-a`, created in P1, hosts the VMs of the later tests. Most
tenant tests in sections 4 to 6 build on the cluster `ocp4-test-eck-five-a`, created in P2.

**Tests**

| ID | Test | Procedure | Acceptance Criteria | Result |
|---|---|---|---|---|
| P1 | Create a KV cluster | 1. Create `ocp4-test-kv-five-az1-a` on the seed `ocp4-test-seed-five-az1-a`: one NodePool from the seed's `c200-mtl-az1`, 3 replicas.<br>2. Deploy its vm-lifecycle-worker through day2. | 1. HostedCluster Available on the seed; 3 bare-metal workers Ready, running KubeVirt.<br>2. Workflow `provision-cluster-ocp4-test-kv-five-az1-a` Completed; its segment Allocated in segments-manager.<br>3. Git: day1 file `sites/five/mces/ocp4-test-seed-five-az1-a/hostedClusters/ocp4-test-kv-five-az1-a.yaml` merged to `main`; every NodePool's `nodeLabels` zone is `az1`, equal to the zone in the name.<br>4. ArgoCD: Application `ocp4-test-kv-five-az1-a` on the seed Synced to the merge commit and Healthy.<br>5. A KV cluster file whose NodePools name another zone, or none, is refused when written.<br>6. The worker's ConfigMap holds `kvCluster: ocp4-test-kv-five-az1-a`, `site: five`, its `vlanId`, and `vmMacPrefix` = `0e` + that VLAN; the worker polls `vm-lifecycle-activity-ocp4-test-kv-five-az1-a`.<br>7. Node bin-packing configured: the `HighNodeUtilization` scheduler profile and the descheduler's compaction.<br>8. The next `create-vm` in az1 reads this cluster's figures. | |
| P2 | Create a hosted cluster on bare metal | 1. Create `ocp4-test-eck-five-a` on `ocp4-test-mce-five-a`.<br>2. One NodePool per zone from `c200-mtl-az1/2/3`, 2 replicas each. | 1. HostedCluster Available in namespace `hcp-test-eck-five-a`; 6 workers Ready, 2 per zone.<br>2. Workflow `provision-cluster-ocp4-test-eck-five-a` Completed, its child `allocate-segment-HC-ocp4-test-eck-five-a` Completed, no failed activity.<br>3. Git: day1 file `…/ocp4-test-eck-five-a.yaml` merged to `main`, holding `owner`, `mastertag`, three `nodepool` entries, `vlanId` and `dhcp_values`.<br>4. ArgoCD: Application `ocp4-test-eck-five-a` Synced to the merge commit and Healthy.<br>5. segments-manager: one HC segment Allocated to the cluster, its VLAN equal to the file's `vlanId`.<br>6. NodePools `test-eck-five-a-c200-mtl-az1/2/3` select `redbull.io/flavor=c200`, `redbull.io/size=mtl` and their zone, exclude `redbull.io/claimed`, and set their zone in `nodeLabels`.<br>7. Every worker named `ocp-c200-mtl-five-<serial>`; its Agent labelled `redbull.io/claimed`.<br>8. day2: the cluster's folder created in every sig, after the merge. | |
| P3 | Create a hosted cluster on VMs | 1. Empty the VM pools `c200-kv32-az1/2/3`.<br>2. Create `ocp4-test-eck-five-b` with one NodePool per zone from `c200-kv32-az1/2/3`, 1 replica each. | 1. HostedCluster Available; 3 workers Ready, 1 per zone.<br>2. Three VMs named `ocp-c200-kv32-five-<12-hex MAC>`, the az1 VM on `ocp4-test-kv-five-az1-a` and each other on its zone's KV cluster, its MAC starting with `0e` + that KV cluster's VLAN.<br>3. Each VM labelled `redbull.io/flavor`, `redbull.io/size=kv32`, `redbull.io/site`, `topology.kubernetes.io/zone`, `redbull.io/role=worker`, `redbull.io/mce`.<br>4. Each `add-server-to-mce-…_c200-kv32-az<n>_<slot>` run started `create-vm` as a child and installed that VM, with no server-scan draw.<br>5. Git and ArgoCD as in P2, for `ocp4-test-eck-five-b`. | |
| P4 | Create three clusters in parallel | 1. At the same moment, create `ocp4-test-eck-five-c`, `-d` and `-e`.<br>2. Each with one `c200-mtl` NodePool per zone, 1 replica each. | 1. All three HostedClusters Available, each with 3 workers Ready.<br>2. Three workflow runs, each Completed on its own id.<br>3. Three different segments; no VLAN shared.<br>4. No Agent bound to two clusters; no server locked by two runs.<br>5. Three day1 files and three Applications, each Synced and Healthy.<br>6. The pools are topped back up afterwards. | |
| P5 | Create while a pool is empty | 1. Empty `c200-mtl-az1`.<br>2. Create `ocp4-test-eck-five-f` with one `c200-mtl` NodePool per zone, 1 replica each. | 1. The control plane becomes Available without waiting for workers.<br>2. The az1 NodePool waits for an Agent and is not marked failed.<br>3. The Inventory Controller orders for `c200-mtl-az1` within two passes.<br>4. The az1 worker joins with no human step. | |
| P6 | Create with a node type that has no InfraEnv | 1. Create `ocp4-test-eck-five-g` with a NodePool from `c400-mtl-az1`, which does not exist on the MCE. | 1. The request is refused, naming the missing InfraEnv.<br>2. No branch, commit or merge request.<br>3. No segment allocated. | |
| P7 | Refuse names that break the convention | 1. Request `OCP4-test-eck-five-a` (uppercase).<br>2. Request `ocp4-test-eck-haifa-a` under site `five`.<br>3. Request `ocp4-test-kv-five-a` (reserved flavor).<br>4. Request `ocp4-test-eck-five-12` (numeric id). | 1. Every request refused, each naming the rule it breaks.<br>2. Nothing written to Git.<br>3. No segment allocated. | |
| P8 | Create when the site has no free segment | 1. Allocate every HC segment of site `five`.<br>2. Create `ocp4-test-eck-five-h`. | 1. The workflow fails at the segment allocation, with segments-manager's "none available".<br>2. Nothing committed; no branch, day2 folder or DHCP scope. | |
| P9 | The Inventory Controller draws by labels, not names | 1. Make `c200-mtl-az1` one Agent short.<br>2. In server-scan, make available server A, named `legacy-host-17`, with flavor `c200`, bare metal, site `five`, zone `az1`.<br>3. Make available server B, named `ocp-c200-mtl-five-<serial>`, with zone `az2`. | 1. The Inventory Controller identifies the pool by the InfraEnv's `redbull.io/flavor`, `redbull.io/size`, `redbull.io/site` and `topology.kubernetes.io/zone`.<br>2. Its server request to server-scan carries flavor, size, site and zone, and no name prefix.<br>3. Server A is installed into `c200-mtl-az1`; server B is not drawn.<br>4. An InfraEnv missing a `redbull.io` label is reported blocked, naming the label; nothing ordered for it. | |
| P10 | Add a second KV cluster in the same zone | 1. Create `ocp4-test-kv-five-az1-b` on the seed `ocp4-test-seed-five-az1-a`, as in P1. | 1. As in P1, for `ocp4-test-kv-five-az1-b`.<br>2. Its VLAN, and so its MAC prefix, differs from `ocp4-test-kv-five-az1-a`'s.<br>3. Placement in az1 tries `ocp4-test-kv-five-az1-a` first and `-b` second (oldest first). | |
| P11 | Create a Customer MCE | 1. Create `ocp4-test-mce-five-b`: one master VM per zone and three worker VMs. | 1. Exactly one master VM in each zone.<br>2. Every MCE VM labelled `redbull.io/role=mce` and `redbull.io/mce=ocp4-test-mce-five-b`.<br>3. No two of its VMs on the same hypervisor.<br>4. Every MCE Node labelled with its zone. | |

---

## 4. Modification (R2)

This section verifies that common daily modifications can be performed through the platform's
workflows and GitOps, without disrupting the hosted control plane.

**Prerequisites:**

1. The cluster `ocp4-test-eck-five-a` from P2, healthy
2. The cluster `ocp4-test-eck-five-c` from P4, with its control plane on 4.18
3. KV clusters `ocp4-test-kv-five-az1-a` (P1) and `ocp4-test-kv-five-az1-b` (P10) in az1
4. Access to the day1 repository, ArgoCD, Temporal and server-scan

The tests run in order on `ocp4-test-eck-five-a`, unless another cluster is named.

**Tests**

| ID | Test | Procedure | Acceptance Criteria | Result |
|---|---|---|---|---|
| M1 | Scale up one NodePool | 1. Set `test-eck-five-a-c200-mtl-az1` from 2 to 4. | 1. The NodePool's replicas 4; 4 workers Ready in az1; the other NodePools unchanged.<br>2. Workflow `update-nodepool-ocp4-test-eck-five-a` Completed.<br>3. Git: one commit on day1 `main` changing only that NodePool's `replicas`, 2 → 4.<br>4. ArgoCD: Application `ocp4-test-eck-five-a` Synced to that commit and Healthy.<br>5. The Inventory Controller tops `c200-mtl-az1` back up. | |
| M2 | Add a NodePool of a new node type | 1. Add `c200-kv16` to the cluster, 1 replica per zone. | 1. NodePools `test-eck-five-a-c200-kv16-az1/2/3` exist in the day1 file and on the MCE, each selecting `redbull.io/flavor=c200`, `redbull.io/size=kv16` and its zone, excluding `redbull.io/claimed`.<br>2. The `c200-mtl` NodePools unchanged.<br>3. Three VMs created through `create-vm`; 3 workers Ready.<br>4. One commit; Application Synced to it and Healthy. | |
| M3 | Add a node type the MCE has no InfraEnv for | 1. Add `c400-kv16`, 1 replica per zone. | 1. Refused, naming the missing InfraEnv.<br>2. Nothing committed. | |
| M4 | Scale by node type while NodePools are unbalanced | 1. With the `c200-mtl` NodePools at 4, 2, 2, request a total of 9 for `c200` bare metal. | 1. Refused as unbalanced, naming the NodePools and their replicas.<br>2. Nothing committed. | |
| M5 | Scale by node type, spread across zones | 1. Set the az2 and az3 NodePools to 4 each.<br>2. Request a total of 13 for `c200` bare metal. | 1. The `c200-mtl` NodePools end at 5, 4, 4.<br>2. The `c200-kv16` NodePools unchanged.<br>3. One commit for the total; Application Synced to it. | |
| M6 | Scale down, the workflow chooses the nodes | 1. Set `test-eck-five-a-c200-mtl-az1` from 5 to 3. | 1. Exactly 2 Machines deleted, and they are the 2 the workflow marked before its commit.<br>2. Both released Agents labelled `redbull.io/claimed`; no NodePool claims them again.<br>3. Both removed from the MCE by `remove-server-from-mce-<server>`; both servers `AVAILABLE` in server-scan.<br>4. The Inventory Controller orders nothing back.<br>5. One commit, 5 → 3; Application Synced to it. | |
| M7 | Remove a named node, control plane 4.19 or later | 1. Remove node `ocp-c200-mtl-five-<serial>` from the az1 NodePool, 3 → 2. | 1. That node, and only it, is removed; the result says `chosen_matches_requested: true`.<br>2. The UI offered "choose a node" for this cluster.<br>3. Its server removed from the MCE and `AVAILABLE` in server-scan. | |
| M8 | Remove a named node, control plane 4.18 | 1. On `ocp4-test-eck-five-c`, ask to remove a named node through the UI.<br>2. Ask again directly through the API.<br>3. Ask to remove any node. | 1. The UI shows "choose a node" disabled, with the reason.<br>2. The API request refused, naming the version rule.<br>3. Nothing committed; no Machine marked.<br>4. "Remove any node" works on the same cluster. | |
| M9 | Rapid successive requests | 1. On `test-eck-five-a-c200-mtl-az2` (4 replicas), request 2, then 3, then 1, 30 seconds apart. | 1. One change only: 4 → 1; 3 Machines removed; none added.<br>2. One commit, 4 → 1.<br>3. No request refused. | |
| M10 | A request after the commit | 1. Set the az3 NodePool from 4 to 2.<br>2. While its 2 Machines are still deleting, request 1.<br>3. Then request 3. | 1. To 1: one more healthy, non-deleting Machine removed; the deleting ones never chosen again.<br>2. To 3: nothing added until the deleting Machines are gone; the new workers come from fresh Agents, never the released ones. | |
| M11 | Scale during an upgrade | 1. Start an upgrade of the cluster.<br>2. Request a scale. | 1. The scale request refused, naming the running upgrade.<br>2. Nothing committed by it. | |
| M12 | Scale below the floor | 1. Request a NodePool below the agreed floor. | 1. Refused, naming the floor.<br>2. Nothing committed; no Machine marked. | |
| M13 | Day1 and the cluster disagree | 1. Change a NodePool's replicas on the MCE by hand.<br>2. Request a scale. | 1. Refused, naming the NodePool and both values.<br>2. Nothing committed. | |
| M14 | A repair during a scale-down | 1. Start a scale-down of the az1 NodePool by 1.<br>2. Between the commit and the sync, have a different, unmarked Machine deleted. | 1. The workflow reports that the deleting Machine is not the marked one.<br>2. It follows the Machine actually deleting: its Agent labelled `redbull.io/claimed`, the marked one left as it was.<br>3. The NodePool ends at its requested size. | |
| M15 | Change configuration without disruption | 1. Add a machine config to the az3 NodePool. | 1. The NodePool rolls in place, one node at a time; no VM or server replaced.<br>2. The cluster's API available throughout.<br>3. No draw from the warm pool. | |
| M16 | Twenty VMs at once in one zone | 1. Order 20 `c200-kv32-az1` VMs at once. | 1. Placements run one at a time in the zone.<br>2. `ocp4-test-kv-five-az1-a` fills to its 15% buffer before `-b` receives a VM.<br>3. No KV cluster above 85% of CPU or memory.<br>4. Runs that do not fit fail with `NoKvClusterFitsError`, listing every cluster and why; nothing created for them.<br>5. Every MAC unique. | |
| M17 | A KV cluster with no worker | 1. List a new KV cluster `ocp4-test-kv-five-az1-c` in day1 without deploying its worker.<br>2. Order an az1 VM. | 1. `-c` reported `no-worker`; the next cluster is tried.<br>2. The order completes on another KV cluster. | |
| M18 | KV capacity stays ahead of demand | 1. Keep ordering az1 VMs until the active KV cluster reaches 40 nodes. | 1. The active cluster grows before its free capacity falls below 15%.<br>2. A standby KV cluster exists in az1 throughout.<br>3. At 40 nodes, placement continues on the standby, and a new standby is started.<br>4. No VM order waits for a KV cluster to be built. | |

---

## 5. Upgrade (R3)

This section verifies that hosted, MCE and KubeVirt clusters can be upgraded with minimal downtime
and with no dependency on another team.

**Prerequisites:**

1. The cluster `ocp4-test-eck-five-a`, with a newer version available on the MCE's upgrade ladder
2. The cluster `ocp4-test-eck-five-c` from P4
3. The KV cluster `ocp4-test-kv-five-az1-a` from P1, holding tenant VMs
4. Access to the day1 repository, ArgoCD and Temporal

The tests run on `ocp4-test-eck-five-a`, unless another cluster is named.

**Tests**

| ID | Test | Procedure | Acceptance Criteria | Result |
|---|---|---|---|---|
| U1 | Upgrade the control plane only | 1. Upgrade the control plane one minor, without the workers. | 1. The control plane runs the target; every NodePool keeps its version.<br>2. Workflow `upgrade-cluster-ocp4-test-eck-five-a` Completed.<br>3. Git: `mastertag` committed by digest on day1 `main`.<br>4. ArgoCD: Application Synced to that commit and Healthy.<br>5. The cluster's API available throughout. | |
| U2 | Upgrade the workers in place | 1. Bring every NodePool to the control plane's version. | 1. One NodePool at a time; the next starts only after the previous is Ready and has soaked.<br>2. One node at a time within a NodePool; no VM or server replaced (same names before and after).<br>3. No draw from the warm pool.<br>4. One commit per NodePool; Application Synced after each. | |
| U3 | The worker version skew limit | 1. Leave the workers two minors behind.<br>2. Move the control plane a third minor. | 1. Two minors behind is allowed.<br>2. The third control-plane step refused until the workers are upgraded. | |
| U4 | A version the MCE cannot host | 1. Request a version above what `ocp4-test-mce-five-a` supports. | 1. Refused at planning, naming the MCE's limit.<br>2. Nothing committed. | |
| U5 | Pause and abort an upgrade | 1. Pause a worker upgrade between two NodePools.<br>2. Abort it. | 1. No commit after the pause.<br>2. On abort, `pausedUntil` committed.<br>3. The workflow Completed with the abort recorded. | |
| U6 | Upgrade an MCE hub | 1. Upgrade `ocp4-test-mce-five-a` while `ocp4-test-eck-five-c` runs a version the new MCE no longer supports.<br>2. Bring `ocp4-test-eck-five-c` into range and upgrade again. | 1. The precheck refuses, naming `ocp4-test-eck-five-c` and its version.<br>2. Once every hosted cluster is in range, the upgrade completes with every hosted control plane available throughout. | |
| U7 | Upgrade a KV cluster | 1. Upgrade `ocp4-test-kv-five-az1-a` while it holds tenant VMs. | 1. Every VM on a draining hypervisor live-migrates; no tenant VM restarts.<br>2. A hypervisor whose VMs have nowhere to go is reported, not drained by force. | |

---

## 6. Deletion (R4)

This section verifies that clusters are torn down cleanly, releasing compute, storage and network
safely.

**Prerequisites:**

1. The clusters `ocp4-test-eck-five-a`, `-c`, `-d`, `-e` and `-f` from the previous sections
2. The KV cluster `ocp4-test-kv-five-az1-b` from P10
3. Access to the day1 repository, ArgoCD, Temporal, server-scan and segments-manager

**Tests**

| ID | Test | Procedure | Acceptance Criteria | Result |
|---|---|---|---|---|
| D1 | Delete a hosted cluster | 1. Delete `ocp4-test-eck-five-a`, with its bare-metal and VM NodePools. | 1. Git: the day1 file removed from `main`; the cluster's day2 folders removed.<br>2. ArgoCD: Application `ocp4-test-eck-five-a` pruned and gone; no other Application affected.<br>3. HostedCluster and NodePools gone; every Agent unbound and labelled `redbull.io/claimed`.<br>4. Every machine removed from the MCE: bare-metal servers `AVAILABLE` in server-scan, every VM destroyed.<br>5. The DHCP scope deleted before the segment released; the segment `Available`, with no cluster.<br>6. No leftover BareMetalHost, NMStateConfig, BMC Secret, Agent, VM, PXE entry or install lock. | |
| D2 | Delete three clusters in parallel | 1. At the same moment, delete `ocp4-test-eck-five-c`, `-d` and `-e`. | 1. All three fully removed, each as in D1.<br>2. Their three segments released.<br>3. Machine removals run no more than the configured number at once. | |
| D3 | Delete with a stuck machine | 1. Make one server of `ocp4-test-eck-five-f` unreachable through its BMC.<br>2. Delete `ocp4-test-eck-five-f`. | 1. The workflow fails on that machine after its deadline, naming it.<br>2. The segment not released while the cluster's DHCP scope or Application still exists.<br>3. Every other machine removed. | |
| D4 | Decommission a KV cluster | 1. Decommission `ocp4-test-kv-five-az1-b`, which holds warm-pool and tenant VMs. | 1. No new VM placed on it once decommissioning starts.<br>2. Its tenant VMs replaced on other az1 KV clusters before it is removed.<br>3. Its VLAN released only after its VMs, BareMetalHosts and Agents are gone. | |
