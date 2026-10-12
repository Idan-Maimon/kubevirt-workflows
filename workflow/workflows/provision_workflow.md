# Provision Workflow

Creates new KubeVirt VMs, registers them with MCE via BMH, and waits for them to appear as ready agents in the inventory. This runs when the Controller detects that the MCE agent pool is running low and needs replenishment. It fans out N parallel child workflows — one per VM — so all VMs are created and registered at the same time.

Triggered by the Fleet Engine Controller via `SignalWithStart`. One workflow instance per `(cluster, zone, node_type)` batch request.

---

## Signals

### provision

Requests creation of a specific number of new VMs for a given cluster and zone.

**Receives**
| Field | Type | Required | Description |
|---|---|---|---|
| cluster | str | ✅ | Target cluster name e.g. `OCP-A` |
| zone | str | ✅ | Zone to provision into e.g. `zone-1` |
| node_type | str | ✅ | Node flavour e.g. `vm-32-128` |
| count | int | ✅ | Number of new VMs to create |
| kv_cluster | str | ✅ | Which KubeVirt cluster to create the VMs on |
| infraenv_name | str | ✅ | InfraEnv the new agents should register from |
| infraenv_namespace | str | ✅ | Namespace of the InfraEnv |
| argocd_app | str | ✅ | ArgoCD application managing BMH resources |
| git_base_path | str | ✅ | Repo path for BMH/NMState/Secret files |

---

## Steps (top-level workflow)

| Step | What happens |
|---|---|
| 1 | Receive `provision` signal |
| 2 | Check the KubeVirt cluster is healthy (`kubevirt.check_cluster_healthy`) |
| 3 | Fan out `count` parallel `ProvisionOneVM` child workflows |
| 4 | Wait for all child workflows to complete |
| 5 | Report how many agents are now available |

---

## ProvisionOneVM child workflow

Each child workflow handles a single VM from creation to agent-ready. They all run in parallel.

| Step | Activity used | What happens |
|---|---|---|
| 1 | `kubevirt.create_vm` | Create a new VM on the KubeVirt cluster with zone labels |
| 2 | `kubevirt.wait_vm_running` | Wait until the VM is Running and has a MAC address |
| 3 | `mce.nmstate.create_nmstate_config` | Create NMState network config for the VM |
| 4 | `mce.bmh.create_bmh` | Create a BareMetalHost pointing to the VM via kubevirt-redfish Redfish URL |
| 5 | `git.commit_files` | Commit NMState secret + BMH manifest to Git in a single commit |
| 6 | `argocd.sync_app` | Trigger ArgoCD to apply the new BMH and NMState to the MCE cluster |
| 7 | `mce.bmh.wait_bmh_available` | Wait for BMH to become `available` (MCE completes hardware inspection) |
| 8 | `mce.agent.wait_agent_ready` | Wait for the agent to register and pass validation |
| 9 | — | Report success — the agent is now in the MCE inventory, ready for a NodePool |

> **Note:** Once step 5 (git commit) succeeds, the workflow does not cancel even if later steps fail. This preserves GitOps consistency — a committed resource must be decommissioned via a separate delete, never by abandoning it.

---

## Workflow ID

`provision-{cluster}-{zone}-{node_type}-{timestamp}` e.g. `provision-OCP-A-zone-1-vm-32-128-1728345600`

## Task Queue

`provision-manager`

## continue_as_new

Not applicable — provision workflows are short-lived and complete once all VMs are registered.

## Failure handling

If a single `ProvisionOneVM` child fails (e.g. VM never reached Running), the parent workflow logs the failure and continues waiting for the remaining children. Partial success is reported.
