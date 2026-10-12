# Agent Activity

Manages Agent objects on the MCE cluster. An Agent appears automatically when a VM boots the discovery ISO and registers with MCE. Agents are the "available inventory" that NodePools draw from when scaling up.

---

## list_available_agents

Returns agents that have registered from a given InfraEnv and are not yet assigned to a NodePool. Used by the Controller to decide how many new VMs to create.

**Receives**
| Field | Type | Required | Description |
|---|---|---|---|
| namespace | str | ✅ | Namespace to search in |
| infraenv_name | str | ❌ | Filter agents by InfraEnv name |
| label_selector | dict | ❌ | Additional label filters e.g. `{"zone": "zone-1"}` |

**Provides**
| Field | Type | Description |
|---|---|---|
| agents | list[AgentSummary] | List of available agents with name, hostname, approved, ready |
| count | int | Total number of available agents |

---

## get_agent

Reads the current state of a specific agent.

**Receives**
| Field | Type | Required | Description |
|---|---|---|---|
| agent_name | str | ✅ | Name of the Agent |
| namespace | str | ✅ | Namespace of the Agent |

**Provides**
| Field | Type | Description |
|---|---|---|
| agent_name | str | Name of the Agent |
| hostname | str | Hostname reported by the agent |
| approved | bool | Whether the agent has been approved |
| ready | bool | Whether the agent passed hardware validation |
| role | str | Assigned role: `worker`, `master`, or empty |
| cluster_name | str | Name of the cluster this agent is bound to (if any) |
| infraenv_name | str | InfraEnv the agent registered from |

---

## wait_agent_ready

Blocks until a specific agent is ready — meaning it has completed hardware discovery and passed validation. Used after a VM boots the discovery ISO to confirm it is ready to be consumed by a NodePool.

**Receives**
| Field | Type | Required | Description |
|---|---|---|---|
| agent_name | str | ✅ | Name of the Agent |
| namespace | str | ✅ | Namespace of the Agent |
| timeout_seconds | int | ❌ | Max wait time (default: 600) |

**Provides**
| Field | Type | Description |
|---|---|---|
| hostname | str | Hostname of the ready agent |
| approved | bool | Whether the agent was auto-approved |

---

## approve_agent

Approves an agent so it can be used by a NodePool. Required if auto-approval is not configured.

**Receives**
| Field | Type | Required | Description |
|---|---|---|---|
| agent_name | str | ✅ | Name of the Agent |
| namespace | str | ✅ | Namespace of the Agent |

**Provides**
| Field | Type | Description |
|---|---|---|
| approved | bool | True if the agent was successfully approved |

---

## delete_agent

Removes an Agent. Used when a node is being decommissioned.

**Receives**
| Field | Type | Required | Description |
|---|---|---|---|
| agent_name | str | ✅ | Name of the Agent |
| namespace | str | ✅ | Namespace of the Agent |

**Provides**
| Field | Type | Description |
|---|---|---|
| deleted | bool | True if the agent was found and deleted |
