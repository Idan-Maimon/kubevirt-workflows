# NodePool Activity

Manages HyperShift NodePool objects on the MCE cluster. A NodePool defines how many worker nodes a hosted cluster has in a given zone, and which OCP version they run.

---

## create_nodepool

Creates a new NodePool for a hosted cluster.

**Receives**
| Field | Type | Required | Description |
|---|---|---|---|
| cluster_name | str | ✅ | Name of the parent HostedCluster |
| nodepool_name | str | ✅ | Name for the new NodePool (convention: `{cluster}-{zone}`) |
| namespace | str | ✅ | Namespace (same as the HostedCluster) |
| replicas | int | ✅ | Number of worker nodes to provision |
| release_image | str | ✅ | OCP release image digest |
| platform_type | str | ✅ | `Agent` or `KubeVirt` |
| agent_label_selector | dict | ❌ | Labels to match agents (required for Agent platform) |
| upgrade_type | str | ❌ | `Replace` or `InPlace` (default: `Replace`) |

**Provides**
| Field | Type | Description |
|---|---|---|
| nodepool_name | str | Name of the created NodePool |
| namespace | str | Namespace where it was created |

---

## get_nodepool_status

Reads the current state of a NodePool — how many nodes are desired vs. actually ready.

**Receives**
| Field | Type | Required | Description |
|---|---|---|---|
| nodepool_name | str | ✅ | Name of the NodePool |
| namespace | str | ✅ | Namespace of the NodePool |

**Provides**
| Field | Type | Description |
|---|---|---|
| nodepool_name | str | Name of the NodePool |
| desired_replicas | int | How many nodes are requested |
| current_replicas | int | How many nodes are actually ready |
| version | str | OCP version the nodes are running |
| updating_version | bool | True if a version rollout is in progress |
| message | str | Status message (e.g. reason for degraded state) |

---

## set_replicas

Updates the replica count on an existing NodePool. This is the primary write operation used by the Scale Workflow.

**Receives**
| Field | Type | Required | Description |
|---|---|---|---|
| nodepool_name | str | ✅ | Name of the NodePool |
| namespace | str | ✅ | Namespace of the NodePool |
| replicas | int | ✅ | New desired replica count (absolute, not a delta) |

**Provides**
| Field | Type | Description |
|---|---|---|
| previous_replicas | int | Replica count before the update |
| new_replicas | int | Replica count after the update |

---

## set_release_image

Patches the release image on a NodePool to trigger a worker upgrade.

**Receives**
| Field | Type | Required | Description |
|---|---|---|---|
| nodepool_name | str | ✅ | Name of the NodePool |
| namespace | str | ✅ | Namespace of the NodePool |
| release_image | str | ✅ | Target release image digest |

**Provides**
| Field | Type | Description |
|---|---|---|
| previous_image | str | The release image before the update |
| new_image | str | The newly applied release image |

---

## delete_nodepool

Removes a NodePool, draining and terminating all its worker nodes.

**Receives**
| Field | Type | Required | Description |
|---|---|---|---|
| nodepool_name | str | ✅ | Name of the NodePool |
| namespace | str | ✅ | Namespace of the NodePool |

**Provides**
| Field | Type | Description |
|---|---|---|
| deleted | bool | True if the NodePool was found and deletion initiated |

---

## wait_nodepool_ready

Blocks until the NodePool reaches the desired replica count with all nodes healthy.

**Receives**
| Field | Type | Required | Description |
|---|---|---|---|
| nodepool_name | str | ✅ | Name of the NodePool |
| namespace | str | ✅ | Namespace of the NodePool |
| timeout_seconds | int | ❌ | Max wait time (default: 3600) |

**Provides**
| Field | Type | Description |
|---|---|---|
| current_replicas | int | Final ready node count |
| version | str | OCP version running on the nodes |
