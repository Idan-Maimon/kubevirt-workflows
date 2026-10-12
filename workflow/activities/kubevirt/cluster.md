# KubeVirt Cluster Activity

Manages connections to and information about KubeVirt infrastructure clusters. A KV Cluster is where the worker VMs physically run before they join a hosted cluster.

---

## get_cluster

Reads the current state and capacity of a KubeVirt cluster.

**Receives**
| Field | Type | Required | Description |
|---|---|---|---|
| cluster_name | str | ✅ | Name of the KubeVirt cluster |

**Provides**
| Field | Type | Description |
|---|---|---|
| cluster_name | str | Name of the cluster |
| zone | str | Availability zone this cluster belongs to |
| api_url | str | Kubernetes API endpoint |
| healthy | bool | Whether the cluster is reachable and healthy |
| node_count | int | Number of physical nodes available |
| allocatable_cpu | str | Total allocatable CPU across all nodes |
| allocatable_memory | str | Total allocatable memory across all nodes |

---

## list_clusters

Lists all known KubeVirt clusters, optionally filtered by zone.

**Receives**
| Field | Type | Required | Description |
|---|---|---|---|
| zone | str | ❌ | Filter by zone e.g. `zone-1` |

**Provides**
| Field | Type | Description |
|---|---|---|
| clusters | list[ClusterSummary] | List with name, zone, healthy, node_count per cluster |
| count | int | Total number of clusters found |

---

## check_cluster_healthy

Verifies that a KubeVirt cluster is reachable and ready to accept new VMs. Used as a pre-check before creating VMs.

**Receives**
| Field | Type | Required | Description |
|---|---|---|---|
| cluster_name | str | ✅ | Name of the KubeVirt cluster |

**Provides**
| Field | Type | Description |
|---|---|---|
| healthy | bool | True if the cluster is reachable and operational |
| reason | str | Human-readable reason if unhealthy (empty if healthy) |

---

## get_cluster_kubeconfig

Retrieves the kubeconfig for a KubeVirt cluster so activities can interact with it directly.

**Receives**
| Field | Type | Required | Description |
|---|---|---|---|
| cluster_name | str | ✅ | Name of the KubeVirt cluster |
| secret_name | str | ❌ | Name of the secret holding the kubeconfig (auto-detected if omitted) |
| secret_namespace | str | ❌ | Namespace of the secret (auto-detected if omitted) |

**Provides**
| Field | Type | Description |
|---|---|---|
| kubeconfig | str | Base64-encoded kubeconfig content |
| api_url | str | API server URL extracted from the kubeconfig |
