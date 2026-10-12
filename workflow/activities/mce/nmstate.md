# NMState Activity

Manages NMState network configuration objects on the MCE cluster. NMState secrets define the network setup (static IPs, VLANs, bonds) that gets applied to a node when it is provisioned. Each VM that becomes a worker node needs an NMState config so MCE knows how to configure its networking.

---

## create_nmstate_config

Creates an NMState NetworkData secret for a specific node. This secret is referenced by the BareMetalHost and applied during provisioning.

**Receives**
| Field | Type | Required | Description |
|---|---|---|---|
| secret_name | str | ✅ | Name for the NMState secret (convention: `nmstate-{vm_name}`) |
| namespace | str | ✅ | Namespace to place it in |
| interface_name | str | ✅ | Network interface to configure e.g. `enp1s0` |
| ip_address | str | ✅ | Static IP to assign to the interface |
| prefix_length | int | ✅ | Subnet prefix length e.g. `24` |
| gateway | str | ✅ | Default gateway IP |
| dns_servers | list[str] | ✅ | List of DNS server IPs |
| mac_address | str | ❌ | MAC address to bind this config to (ensures the right interface is configured) |

**Provides**
| Field | Type | Description |
|---|---|---|
| secret_name | str | Name of the created secret |
| namespace | str | Namespace where it was created |

---

## get_nmstate_config

Reads an existing NMState config secret.

**Receives**
| Field | Type | Required | Description |
|---|---|---|---|
| secret_name | str | ✅ | Name of the NMState secret |
| namespace | str | ✅ | Namespace of the secret |

**Provides**
| Field | Type | Description |
|---|---|---|
| secret_name | str | Name of the secret |
| namespace | str | Namespace of the secret |
| network_data | dict | Parsed network configuration |

---

## delete_nmstate_config

Removes an NMState config secret.

**Receives**
| Field | Type | Required | Description |
|---|---|---|---|
| secret_name | str | ✅ | Name of the NMState secret |
| namespace | str | ✅ | Namespace of the secret |

**Provides**
| Field | Type | Description |
|---|---|---|
| deleted | bool | True if the secret was found and deleted |
