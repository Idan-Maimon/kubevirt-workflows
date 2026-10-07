from __future__ import annotations

import dataclasses

# ---------------------------------------------------------------------------
# Naming convention
# ---------------------------------------------------------------------------
# Node type format:  vm-{cpu}-{ram}   e.g. vm-32-128  (32 vCPU, 128 GB RAM)
#
# From (cluster, node_type) all names are derived:
#   Workflow ID    : scale-{cluster}-{node_type}          scale-OCP-A-vm-32-128
#   ArgoCD app     : {cluster.lower()}-{node_type}        ocp-a-vm-32-128
#   Git base path  : nodepools/{cluster}/{node_type}      nodepools/OCP-A/vm-32-128
#   NodePool names : {cluster.lower()}-{node_type}-{zone} ocp-a-vm-32-128-zone-1
#   Zone files     : {git_base_path}/{zone}.yaml          nodepools/OCP-A/vm-32-128/zone-1.yaml
#
# argocd_app and git_base_path are still required fields in signals.
# They will be auto-derived once the naming schema is finalised.
# ---------------------------------------------------------------------------

ZONES: list[str] = ["zone-1", "zone-2", "zone-3"]


def workflow_id(cluster: str, node_type: str) -> str:
    return f"scale-{cluster}-{node_type}"


def argocd_app_name(cluster: str, node_type: str) -> str:
    return f"{cluster.lower()}-{node_type}"


def git_base_path(cluster: str, node_type: str) -> str:
    return f"nodepools/{cluster}/{node_type}"


# ---------------------------------------------------------------------------
# Signal types
# ---------------------------------------------------------------------------

@dataclasses.dataclass
class ScaleSignal:
    """
    Sent via SignalWithStart to request a scale operation.
    All fields are required — every request must be self-contained.

    cluster       : cluster name,            e.g. "OCP-A"
    node_type     : VM profile identifier,   e.g. "vm-32-128"
    desired_total : absolute replica count across all zones (min = len(ZONES) = 3)
    argocd_app    : ArgoCD Application name  e.g. "ocp-a-vm-32-128"  [auto-derived later]
    git_base_path : path in git repo         e.g. "nodepools/OCP-A/vm-32-128" [auto-derived later]
    """
    cluster: str
    node_type: str
    desired_total: int
    argocd_app: str
    git_base_path: str


@dataclasses.dataclass
class DeleteSignal:
    """
    Sent to remove all zone NodePool manifests from git.
    ArgoCD prune deletes the NodePool objects from the cluster.

    cluster       : cluster name,            e.g. "OCP-A"
    node_type     : VM profile identifier,   e.g. "vm-32-128"
    argocd_app    : ArgoCD Application name  [auto-derived later]
    git_base_path : path in git repo         [auto-derived later]
    """
    cluster: str
    node_type: str
    argocd_app: str
    git_base_path: str


# ---------------------------------------------------------------------------
# Activity input types
# ---------------------------------------------------------------------------

@dataclasses.dataclass
class ClusterStateInput:
    git_base_path: str
    zones: list[str]


@dataclasses.dataclass
class CommitDistributionInput:
    cluster: str
    node_type: str
    git_base_path: str
    distribution: dict[str, int]
    desired_total: int


@dataclasses.dataclass
class ArgoCDInput:
    argocd_app: str
