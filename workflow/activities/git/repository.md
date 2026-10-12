# Git Repository Activity

Reads from and writes to the GitOps repository that ArgoCD watches. All desired state changes (NodePool replicas, BMH objects, secrets) go through Git so ArgoCD can apply them consistently.

---

## read_file

Reads a single file from the repository and returns its parsed content.

**Receives**
| Field | Type | Required | Description |
|---|---|---|---|
| file_path | str | ✅ | Path to the file within the repo e.g. `nodepools/OCP-A/zone-1.yaml` |
| branch | str | ❌ | Branch to read from (default: configured default branch) |

**Provides**
| Field | Type | Description |
|---|---|---|
| content | str | Raw file content |
| parsed | dict | Parsed YAML/JSON content |
| commit_sha | str | The commit SHA this file was read from |

---

## write_file

Writes or updates a single file in the repository. Does not commit — call `commit_files` separately.

**Receives**
| Field | Type | Required | Description |
|---|---|---|---|
| file_path | str | ✅ | Path to write to within the repo |
| content | str | ✅ | File content to write (YAML string) |

**Provides**
| Field | Type | Description |
|---|---|---|
| file_path | str | Path that was written |

---

## commit_files

Commits all pending file changes to the repository and pushes to the remote. Groups multiple file changes into a single commit so ArgoCD applies them atomically.

**Receives**
| Field | Type | Required | Description |
|---|---|---|---|
| files | list[FileChange] | ✅ | List of `{path, content}` pairs to commit |
| commit_message | str | ✅ | Git commit message |
| author_name | str | ❌ | Commit author name (default: `temporal-workflow`) |
| author_email | str | ❌ | Commit author email |

**Provides**
| Field | Type | Description |
|---|---|---|
| commit_sha | str | SHA of the resulting commit |
| files_changed | int | Number of files included in the commit |

---

## read_all_replicas

Reads the current replica counts for all zones of a cluster from Git. This is the primary read used by the Scale Workflow to know the current desired state before computing changes.

**Receives**
| Field | Type | Required | Description |
|---|---|---|---|
| cluster_name | str | ✅ | Cluster name (determines which folder to read) |
| node_type | str | ✅ | Node type (determines which subfolder) |
| zones | list[str] | ✅ | Zone names to read e.g. `["zone-1", "zone-2", "zone-3"]` |

**Provides**
| Field | Type | Description |
|---|---|---|
| replicas_by_zone | dict[str, int] | Current replica count per zone e.g. `{"zone-1": 2, "zone-2": 2, "zone-3": 1}` |
| commit_sha | str | The commit SHA this data was read from |
