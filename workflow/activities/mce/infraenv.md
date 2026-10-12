# InfraEnv Activity

Manages InfraEnv objects on the MCE cluster. An InfraEnv generates the discovery ISO that new VMs boot from to register as agents in the MCE inventory.

---

## create_infraenv

Creates a new InfraEnv that will generate a discovery ISO for a specific zone.

**Receives**
| Field | Type | Required | Description |
|---|---|---|---|
| infraenv_name | str | ✅ | Name for the InfraEnv (convention: `{cluster}-{zone}`) |
| namespace | str | ✅ | Namespace to place it in |
| pull_secret_name | str | ✅ | Name of the pull secret in the same namespace |
| ssh_authorized_key | str | ✅ | SSH public key injected into discovered nodes |
| agent_labels | dict | ❌ | Labels automatically applied to agents that register from this InfraEnv |
| image_type | str | ❌ | `full-iso` or `minimal-iso` (default: `full-iso`) |

**Provides**
| Field | Type | Description |
|---|---|---|
| infraenv_name | str | Name of the created InfraEnv |
| namespace | str | Namespace where it was created |
| iso_download_url | str | URL of the generated discovery ISO (available after a few seconds) |

---

## get_infraenv

Reads the current state of an InfraEnv, including its ISO URL and creation time.

**Receives**
| Field | Type | Required | Description |
|---|---|---|---|
| infraenv_name | str | ✅ | Name of the InfraEnv |
| namespace | str | ✅ | Namespace of the InfraEnv |

**Provides**
| Field | Type | Description |
|---|---|---|
| infraenv_name | str | Name of the InfraEnv |
| iso_download_url | str | Current discovery ISO URL |
| iso_created_at | str | Timestamp of last ISO generation |
| ready | bool | True if the ISO is available for download |

---

## get_agent_count

Returns how many agents have registered from this InfraEnv and are currently available in the MCE inventory. Used by the Controller to detect when VMs need replenishment.

**Receives**
| Field | Type | Required | Description |
|---|---|---|---|
| infraenv_name | str | ✅ | Name of the InfraEnv |
| namespace | str | ✅ | Namespace of the InfraEnv |

**Provides**
| Field | Type | Description |
|---|---|---|
| total_agents | int | Total agents registered from this InfraEnv |
| available_agents | int | Agents not yet bound to a NodePool |
| bound_agents | int | Agents currently assigned to a NodePool |

---

## delete_infraenv

Removes an InfraEnv. Does not remove agents that already registered from it.

**Receives**
| Field | Type | Required | Description |
|---|---|---|---|
| infraenv_name | str | ✅ | Name of the InfraEnv |
| namespace | str | ✅ | Namespace of the InfraEnv |

**Provides**
| Field | Type | Description |
|---|---|---|
| deleted | bool | True if the InfraEnv was found and deleted |
