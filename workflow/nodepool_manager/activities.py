from __future__ import annotations

import dataclasses

from temporalio import activity

from shared.argocd_client import sync_app, wait_until_healthy
from shared.git_client import commit_distribution, read_all_replicas
from .models import ArgoCDInput, ClusterStateInput, CommitDistributionInput


@activity.defn
async def read_cluster_state(input: ClusterStateInput) -> dict[str, int]:
    """Return the current spec.replicas for every zone from Git."""
    return read_all_replicas(input.git_base_path, input.zones)


@activity.defn
async def commit_cluster_distribution(input: CommitDistributionInput) -> None:
    """Patch spec.replicas for all changed zones and push in a single commit."""
    zones_summary = ", ".join(f"{z}={r}" for z, r in sorted(input.distribution.items()))
    message = (
        f"scale {input.cluster}/{input.node_type} → total={input.desired_total} ({zones_summary})"
    )
    commit_distribution(input.git_base_path, input.distribution, message)


@activity.defn
async def sync_argocd_app(input: ArgoCDInput) -> None:
    """Trigger an ArgoCD sync via the ArgoCD REST API."""
    await sync_app(input.argocd_app)


@activity.defn
async def wait_argocd_healthy(input: ArgoCDInput) -> None:
    """Poll the ArgoCD API until the application is Healthy and Synced."""
    await wait_until_healthy(input.argocd_app)
