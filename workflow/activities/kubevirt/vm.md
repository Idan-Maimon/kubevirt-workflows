# VM Activity

Manages individual virtual machines on KubeVirt clusters. These are the VMs that will eventually become worker nodes in a hosted cluster.

---

## create_vm

Creates a new KubeVirt VirtualMachine object in the target cluster.

**Receives**
| Field | Type | Required | Description |
|---|---|---|---|
| cluster_name | str | ✅ | Name of the KubeVirt cluster to create the VM in |
| namespace | str | ✅ | Namespace to place the VM in |
| vm_name | str | ✅ | Unique name for the new VM |
| memory | str | ✅ | Memory allocation e.g. `16Gi` |
| cpu_cores | int | ✅ | Number of CPU cores |
| disk_size | str | ✅ | Root disk size e.g. `50Gi` |
| storage_class | str | ❌ | Storage class for the root disk (defaults to cluster default) |
| labels | dict | ❌ | Labels to apply to the VM (used later for zone matching) |

**Provides**
| Field | Type | Description |
|---|---|---|
| vm_name | str | Name of the created VM |
| namespace | str | Namespace where the VM was created |
| uid | str | Kubernetes UID of the VM object |

---

## get_vm

Reads the current state of an existing VM.

**Receives**
| Field | Type | Required | Description |
|---|---|---|---|
| cluster_name | str | ✅ | Name of the KubeVirt cluster |
| namespace | str | ✅ | Namespace of the VM |
| vm_name | str | ✅ | Name of the VM |

**Provides**
| Field | Type | Description |
|---|---|---|
| vm_name | str | Name of the VM |
| phase | str | Current phase: `Pending`, `Running`, `Stopped`, etc. |
| ip_address | str | IP address assigned to the VM (empty if not yet running) |
| node_name | str | Worker node hosting the VM (empty if not scheduled) |
| labels | dict | Current labels on the VM |

---

## list_vms

Returns all VMs in a namespace, optionally filtered by labels. Used by the Server Scanner to detect newly created VMs.

**Receives**
| Field | Type | Required | Description |
|---|---|---|---|
| cluster_name | str | ✅ | Name of the KubeVirt cluster |
| namespace | str | ✅ | Namespace to search in |
| label_selector | dict | ❌ | Filter VMs by labels e.g. `{"zone": "zone-1"}` |

**Provides**
| Field | Type | Description |
|---|---|---|
| vms | list[VMSummary] | List of VMs with name, phase, ip_address, labels |
| count | int | Total number of VMs found |

---

## delete_vm

Removes a VM and its associated storage.

**Receives**
| Field | Type | Required | Description |
|---|---|---|---|
| cluster_name | str | ✅ | Name of the KubeVirt cluster |
| namespace | str | ✅ | Namespace of the VM |
| vm_name | str | ✅ | Name of the VM to remove |
| delete_disks | bool | ❌ | Also delete PVCs (default: true) |

**Provides**
| Field | Type | Description |
|---|---|---|
| deleted | bool | True if the VM was found and deleted |

---

## wait_vm_running

Blocks until the VM reaches the Running phase. Used to confirm a VM is up before scanning for its MAC address.

**Receives**
| Field | Type | Required | Description |
|---|---|---|---|
| cluster_name | str | ✅ | Name of the KubeVirt cluster |
| namespace | str | ✅ | Namespace of the VM |
| vm_name | str | ✅ | Name of the VM |
| timeout_seconds | int | ❌ | Max wait time (default: 300) |

**Provides**
| Field | Type | Description |
|---|---|---|
| ip_address | str | IP address of the running VM |
| mac_address | str | MAC address of the primary network interface |
| node_name | str | Worker node the VM is running on |
