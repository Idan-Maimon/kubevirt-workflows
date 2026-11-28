# 23 :: Create UPI Cluster

**Animation:** [`../animations/23-create-upi-cluster.html`](../animations/23-create-upi-cluster.html)
**Implementation:** `workflow_domains/upi_lifecycle/create_upi_cluster.py` in `team-redbull/workflows`,
branch `feat/upi-lifecycle` (not merged yet)
**Installer:** [`team-redbull/bootstrap-installer`](https://github.com/team-redbull/bootstrap-installer), `main` (vSphere)

| | |
|---|---|
| **Trigger** | An operator, or Wingman, creating an MCE or another user-provisioned cluster |
| **Workflow id** | `create-upi-cluster-<cluster>` |
| **Runs on** | The hub limb `upi-provisioning` (its Jobs, the installed cluster's admin kubeconfig, Argo CD); the cluster-lifecycle limb for day1; `allocate-segment` children for the networks |
| **Scope** | Every OpenShift cluster installed with user-provisioned infrastructure, `platform: none`: a Customer MCE (`kind: mce`) or any other UPI cluster (`kind: standalone`) |
| **Builds** | One running cluster, registered in the hub's Argo CD; for an MCE, its day1 folder, merged |

---

## 1 :: Purpose

Every hosted cluster runs on an MCE, and an MCE is not hosted: it is installed with user-provisioned
infrastructure, like the Seed. This run builds one, from its name to the moment Argo CD manages it.

An MCE is one kind of UPI cluster, the only kind with a GitOps step. Once its folder is merged to
day1, the hub's `<site>-mces` ApplicationSet makes its Application with the MCE as destination, and
from then on the MCE's own Argo CD deploys its day2 (`in-cluster`).

The install itself is the team's `bootstrap-installer`, run as it is: the workflow drives it, it
stays the one place the install logic lives. The run is the manual "Creation MCE" runbook, end to
end, with every wait and check made explicit.

---

## 2 :: Inputs

### The request

`POST /workflows/upi-lifecycle/create-upi-cluster`

| Field | Required | Notes |
|---|---|---|
| `cluster` | ✅ | The cluster's name, by the [naming convention](../naming-convention.md): `ocp4-<lifecycle>-mce-<site>-<id>` for an MCE. At most 27 characters, bootstrap-installer's limit. It is the Segments Manager's cluster, the Argo CD cluster name and, for an MCE, the day1 folder: one string |
| `site` | ✅ | A Segments Manager site, a bootstrap-installer site profile, and for an MCE a day1 `sites/<site>/` folder |
| `kind` | | `mce` (default) or `standalone` |
| `vm_network` | | The vSphere port group. Default: the worker's template filled from the allocated segment's EPG |
| `install_config` | | Any bootstrap-installer key on top of its defaults and the site profile: node sizing, `compute_ip_offsets`, `image_mirrors`. Never a key the run owns |
| `mce_values` | | `kind: mce` only: the text of the MCE's day1 `values.yaml`. Empty: the site's and the global layers apply alone |

### From elsewhere

| From | What |
|---|---|
| The Segments Manager | The node segment (`MCE` or `UPI`), and an MCE's `INVENTORY` segment |
| The site profile | vCenter, datacenter, compute cluster, datastore cluster, DVS, folder, RHCOS template, base domain, DNS servers, mirrors |
| The install Secret | Pull secret (it must include the registry nodes are later added from), trust bundle, SSH key, vSphere password |

---

## 3 :: Preconditions

| # | Check | Owner |
|---|---|---|
| 1 | The site has free segments in the Segments Manager | `allocate-segment` |
| 2 | The site has a bootstrap-installer profile in the worker's sites ConfigMap | The run refuses otherwise |
| 3 | The vSphere compute cluster carries the tag guard (`is_nvm_Allowed: yes`) | bootstrap-installer refuses otherwise |
| 4 | For an MCE, `sites/<site>/` exists in day1 and no MCE folder of that name exists anywhere | The run refuses otherwise |

---

## 4 :: Process flow

| # | Phase | Runs on | Action | On failure |
|---|---|---|---|---|
| 1 | `allocating-segment` | `allocate-segment` children | The node network: an `MCE` segment for an MCE, a `UPI` segment otherwise. An MCE also gets its `INVENTORY` segment, the BareMetalHost boot network [01](01-add-server-to-mce.md) resolves by the MCE's name. Each child on its own id, idempotent per cluster, site and type | The child's own type, in `AllocateSegmentFailedError` |
| 2 | `preparing` | `upi-provisioning` (a Job) | Job `upi-<cluster>-prepare-<token>` runs `bootstrap.py --skip-terraform --skip-argocd`: the IPs from the segment, the install-config, the `v4InternalSubnet` manifest, the ignition configs and the `*.apps` DNS record. Then it stores the admin kubeconfig and the node IPs in the hub Secret `upi-<cluster>-kubeconfig` | `InstallerJobFailedError`, with the Job's last log lines |
| 3 | `installing` | `upi-provisioning` (a Job) | Job `upi-<cluster>-install-<token>` runs `bootstrap.py --skip-ignition --skip-dns --skip-argocd`: `terraform apply` of the VMs and their DNS records, and bootstrap-installer's CSR loop | As above |
| 4 | `verifying-cluster` | `upi-provisioning` | As the cluster's admin, every 20 seconds: approve the pending CSRs of a node bootstrapper or a `system:node:*` user, read the Nodes and the ClusterVersion. Done when every recorded node IP is a Ready Node and the ClusterVersion is Available with a version | After 2 hours, `UpiClusterNotReadyError`, naming what is missing |
| 5 | `registering-argocd` | `upi-provisioning` | On the cluster, `kube-system/argocd-manager`, its token and a cluster-admin binding; on the hub, Argo CD's cluster Secret `cluster-<cluster>` with `name: <cluster>`, read back | A Secret of that name for another server: `ArgoClusterSecretConflictError` |
| 6 | `publishing-mce-folder` | Cluster-lifecycle limb | **MCE only.** `sites/<site>/mces/<cluster>/values.yaml` and `version.yaml` (`mastertag:` the installed version) on branch `create-upi-cluster/<cluster>` | `MceFolderConflictError`, `Day1SiteNotFoundError` |
| 7 | `opening-merge-request` | Cluster-lifecycle limb | **MCE only.** The merge request to day1 `main`, found or created | |
| 8 | `awaiting-merge` | Cluster-lifecycle limb | **MCE only.** A person merges. Polled every 5 minutes, no deadline | Closed without merging: `MergeRequestClosedError`. The cluster stands, registered |
| 9 | `completed` | | Return the cluster, its segments, API, version, nodes and Argo CD Secret | |

### The IP plan

From the node segment, by bootstrap-installer's offsets, overridable per site or per cluster:

| Offset | Node |
|---|---|
| `.1`–`.3` | Infra: `*.apps`, DNS round-robin |
| `.4`–`.6` | Control plane: `api`, `api-int`, DNS round-robin |
| `.7` | Bootstrap |
| `.8`+ | Compute, when `compute_ip_offsets` asks for it. Bare-metal workers join later through `add-server-to-upi` (procedure 24) |
| `.254` | Gateway |

There are no VIPs and no load balancer.

### Why the run checks readiness itself

bootstrap-installer's CSR loop ends without an error when its time runs out, so a finished install
Job does not prove a working cluster. Step 4 decides, on the nodes bootstrap-installer was asked
for.

### Why Argo CD registration is the run's

The hub's `<site>-mces` ApplicationSet targets `destination.name: <folder>`. The Argo CD cluster name,
the day1 folder and the Segments Manager's cluster are therefore one string, and the run writes the
Secret with it and reads it back. bootstrap-installer's own registration calls the hub with
`oc --server --token`, which cannot verify the hub's certificate from a pod on the hub.

---

## 5 :: Idempotency

- Within a run, every phase's outcome is kept in its state, across continue-as-new during the merge
  wait. Nothing is done twice.
- The run's token is in its Jobs' names: a retry attaches to the same Job, and a new run makes new
  Jobs.
- The work volume `upi-<cluster>-work` holds terraform's state and is never deleted. A new run's
  `prepare` refuses a volume whose state still lists resources: a failed install is destroyed
  (`bootstrap.py --destroy`) before the cluster is created again, so new ignition never meets old
  VMs.
- The segments are idempotent per cluster, site and type. The day1 folder already on `main` with
  this run's content is success, and opens nothing.

---

## 6 :: Outputs

| Field | Notes |
|---|---|
| Cluster | Name, site, kind, API URL, version, nodes |
| Segments | The node segment, VLAN and EPG; an MCE's inventory segment |
| Argo CD | The cluster Secret's name |
| day1 | The MCE folder, the merge request and its merged commit |

---

## 7 :: Built today vs. the architecture

| # | Architecture | Built today |
|---|---|---|
| 1 | A Customer MCE runs on KubeVirt VMs: one master per zone (AD19), workers spread across zones (AD20) ([12](12-create-customer-mce.md)) | On vSphere VMs: 3 masters and 3 infra, through bootstrap-installer. The installer step is where KubeVirt VMs would take vSphere's place; the rest of the run does not change |
| 2 | The MCE stretched across 3 zones (AD10) | One vSphere compute cluster per site profile. Zone placement of the VMs is not built |
| 3 | The Seed, user-provisioned bare metal per zone (AD17, [10](10-create-seed-cluster.md)) | Not covered: the installer step is vSphere only |
| 4 | Segments of type `MCE`, `INVENTORY` and `UPI` | `allocate-segment` allocates all three. A `UPI` segment may be shared by several clusters, and the run checks that it holds it |
| 5 | The MCE's day2 deployed by its own Argo CD | Day2 starts once the folder is merged; the run does not wait for it |

---

## 8 :: Open questions

1. **Where the MCE's hub-side configuration lives.** The GitOps operator, infra nodes, LDAP, the
   KubeletConfig, IDMS, the MCE and ACM operators and the AgentServiceConfig are applied from the hub
   with the MCE as destination. Should the run add the MCE to that source too, or does the MCE
   folder pull it in?
2. **The bootstrap VM.** bootstrap-installer leaves it running after the install. A later step of
   this run, or bootstrap-installer's?
3. **Masters on KubeVirt (row 1).** Whether the installer step gains a KubeVirt variant, or the
   Customer MCE stays on vSphere.
4. **Destroying a cluster.** There is no `delete-upi-cluster`: the segments, the Argo CD Secret, the
   day1 folder and the work volume are released by hand today.
