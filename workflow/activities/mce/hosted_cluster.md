# HostedCluster Activity

Manages HyperShift HostedCluster objects on the MCE cluster. A HostedCluster is the control plane of a customer-facing OpenShift cluster — the workers are separate NodePools.

---

## create_hosted_cluster

Creates a new HyperShift HostedCluster on the MCE cluster.

**Receives**
| Field | Type | Required | Description |
|---|---|---|---|
| cluster_name | str | ✅ | Name for the new HostedCluster |
| namespace | str | ✅ | Namespace to place it in (usually `clusters`) |
| release_image | str | ✅ | OCP release image digest e.g. `quay.io/openshift-release-dev/ocp-release@sha256:...` |
| platform_type | str | ✅ | `Agent` or `KubeVirt` |
| agent_namespace | str | ❌ | Namespace where agents will register (required for Agent platform) |
| pull_secret_name | str | ✅ | Name of the pull secret in the same namespace |
| ssh_key_name | str | ✅ | Name of the SSH key secret |
| infra_id | str | ✅ | Unique infrastructure identifier |

**Provides**
| Field | Type | Description |
|---|---|---|
| cluster_name | str | Name of the created HostedCluster |
| namespace | str | Namespace where it was created |
| kubeconfig_secret | str | Name of the admin kubeconfig secret once available |

---

## get_hosted_cluster

Reads the current state of a HostedCluster.

**Receives**
| Field | Type | Required | Description |
|---|---|---|---|
| cluster_name | str | ✅ | Name of the HostedCluster |
| namespace | str | ✅ | Namespace of the HostedCluster |

**Provides**
| Field | Type | Description |
|---|---|---|
| cluster_name | str | Name of the cluster |
| version | str | Current OCP version running |
| control_plane_version | str | Version the control plane is running |
| available | bool | True if the control plane is healthy |
| progress | str | `Partial`, `Complete` |
| message | str | Human-readable status message |
| kubeconfig_secret | str | Secret name containing the admin kubeconfig |

---

## update_release_image

Patches the release image on a HostedCluster to trigger a control plane upgrade.

**Receives**
| Field | Type | Required | Description |
|---|---|---|---|
| cluster_name | str | ✅ | Name of the HostedCluster |
| namespace | str | ✅ | Namespace of the HostedCluster |
| release_image | str | ✅ | Target release image digest |

**Provides**
| Field | Type | Description |
|---|---|---|
| previous_image | str | The release image before the update |
| new_image | str | The newly applied release image |

---

## delete_hosted_cluster

Removes a HostedCluster and its control plane.

**Receives**
| Field | Type | Required | Description |
|---|---|---|---|
| cluster_name | str | ✅ | Name of the HostedCluster |
| namespace | str | ✅ | Namespace of the HostedCluster |

**Provides**
| Field | Type | Description |
|---|---|---|
| deleted | bool | True if the cluster was found and deletion initiated |

---

## wait_control_plane_available

Blocks until the HostedCluster control plane is fully available.

**Receives**
| Field | Type | Required | Description |
|---|---|---|---|
| cluster_name | str | ✅ | Name of the HostedCluster |
| namespace | str | ✅ | Namespace of the HostedCluster |
| timeout_seconds | int | ❌ | Max wait time (default: 1800) |

**Provides**
| Field | Type | Description |
|---|---|---|
| version | str | OCP version the control plane is running |
| kubeconfig_secret | str | Secret name containing the admin kubeconfig |
