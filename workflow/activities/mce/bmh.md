# BareMetalHost Activity

Manages BareMetalHost (BMH) objects on the MCE cluster. A BMH represents a VM that has been registered as a "bare metal" node via the kubevirt-redfish interface, making it manageable by MCE's provisioning engine.

---

## create_bmh

Creates a BareMetalHost object that points to a KubeVirt VM via its Redfish endpoint. Once created, MCE will boot the VM with a discovery ISO and register it as an agent.

**Receives**
| Field | Type | Required | Description |
|---|---|---|---|
| bmh_name | str | ✅ | Name for the BareMetalHost (usually matches the VM name) |
| namespace | str | ✅ | Namespace to place it in |
| redfish_url | str | ✅ | Redfish endpoint URL e.g. `redfish-virtualmedia+https://kubevirt-redfish.apps.../redfish/v1/Systems/{vm-name}` |
| bmc_secret_name | str | ✅ | Name of the Secret containing Redfish credentials |
| boot_mac_address | str | ✅ | MAC address of the VM's primary network interface |
| boot_mode | str | ❌ | `UEFI` or `legacy` (default: `UEFI`) |
| infra_env_name | str | ❌ | InfraEnv to associate with (sets label for auto-discovery) |
| root_device_hints | dict | ❌ | Hints to identify the root disk e.g. `{"name": "/dev/vda"}` |

**Provides**
| Field | Type | Description |
|---|---|---|
| bmh_name | str | Name of the created BareMetalHost |
| namespace | str | Namespace where it was created |

---

## get_bmh

Reads the current provisioning state of a BareMetalHost.

**Receives**
| Field | Type | Required | Description |
|---|---|---|---|
| bmh_name | str | ✅ | Name of the BareMetalHost |
| namespace | str | ✅ | Namespace of the BareMetalHost |

**Provides**
| Field | Type | Description |
|---|---|---|
| bmh_name | str | Name of the BareMetalHost |
| state | str | Provisioning state: `registering`, `available`, `provisioning`, `provisioned`, `deprovisioning`, `error` |
| error_message | str | Error detail if state is `error` (empty otherwise) |
| online | bool | Whether the BMH is set to be powered on |
| consumer | str | Name of the resource that consumed this BMH (if any) |

---

## wait_bmh_available

Blocks until the BareMetalHost reaches the `available` state, meaning MCE has completed hardware inspection and it is ready to be used.

**Receives**
| Field | Type | Required | Description |
|---|---|---|---|
| bmh_name | str | ✅ | Name of the BareMetalHost |
| namespace | str | ✅ | Namespace of the BareMetalHost |
| timeout_seconds | int | ❌ | Max wait time (default: 600) |

**Provides**
| Field | Type | Description |
|---|---|---|
| state | str | Final state reached (`available`) |

---

## delete_bmh

Removes a BareMetalHost, which also powers off and deprovisions the underlying VM.

**Receives**
| Field | Type | Required | Description |
|---|---|---|---|
| bmh_name | str | ✅ | Name of the BareMetalHost |
| namespace | str | ✅ | Namespace of the BareMetalHost |

**Provides**
| Field | Type | Description |
|---|---|---|
| deleted | bool | True if the BMH was found and deletion initiated |
