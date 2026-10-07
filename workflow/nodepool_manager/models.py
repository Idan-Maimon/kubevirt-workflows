from __future__ import annotations

import dataclasses

# Zones are always 3 and follow a fixed naming convention.
ZONES: list[str] = ["zone-1", "zone-2", "zone-3"]


@dataclasses.dataclass
class ScaleSignal:
    cluster: str           # e.g. "OCP-A"
    desired_total: int     # absolute total replicas across all zones
    argocd_app: str        # e.g. "ocp-a"
    git_base_path: str     # e.g. "nodepools/OCP-A"
    # Future: argocd_app and git_base_path will be derived from cluster name.
    # Naming schema: argocd_app = cluster.lower(), git_base_path = "nodepools/{cluster}"


@dataclasses.dataclass
class DeleteSignal:
    cluster: str
    argocd_app: str
    git_base_path: str


@dataclasses.dataclass
class ClusterStateInput:
    git_base_path: str
    zones: list[str]


@dataclasses.dataclass
class CommitDistributionInput:
    cluster: str
    git_base_path: str
    distribution: dict[str, int]
    desired_total: int


@dataclasses.dataclass
class ArgoCDInput:
    argocd_app: str
