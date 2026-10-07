from __future__ import annotations

import dataclasses
from datetime import timedelta
from typing import Optional

from temporalio import workflow
from temporalio.common import RetryPolicy

from shared.spread import distribute

from .models import (
    ZONES,
    ArgoCDInput,
    ClusterStateInput,
    CommitDistributionInput,
    DeleteSignal,
    ScaleSignal,
)
from .activities import (
    commit_cluster_distribution,
    read_cluster_state,
    sync_argocd_app,
    wait_argocd_healthy,
)

_MAX_ITERATIONS = 200
_MIN_REPLICAS = len(ZONES)  # every zone must have at least 1


@dataclasses.dataclass
class NodePoolManagerInput:
    cluster: str  # workflow identity only — all operational data travels in signals


@workflow.defn
class NodePoolManagerWorkflow:
    """
    Per-cluster Temporal workflow.

    Signals
    -------
    scale(ScaleSignal)   — set desired total replicas, distributed evenly across zones
    delete(DeleteSignal) — remove all zone manifests from git (ArgoCD prunes the NodePool)

    Both signals carry all required fields so any request is self-contained.
    Zones are a fixed constant (always 3).

    Minimum replicas: desired_total must be >= len(ZONES) so every zone
    gets at least 1 node. Requests below this floor are rejected via log
    and discarded — validation should happen at the API layer first.
    """

    def __init__(self) -> None:
        self._pending_scale: Optional[ScaleSignal] = None
        self._pending_delete: Optional[DeleteSignal] = None

    @workflow.signal
    def scale(self, signal: ScaleSignal) -> None:
        if signal.desired_total < _MIN_REPLICAS:
            workflow.logger.warning(
                f"scale signal rejected: desired_total={signal.desired_total} "
                f"is below minimum ({_MIN_REPLICAS}). Use delete() to remove the nodepool."
            )
            return
        self._pending_scale = signal  # last-write-wins

    @workflow.signal
    def delete(self, signal: DeleteSignal) -> None:
        self._pending_delete = signal
        self._pending_scale = None  # delete takes priority; discard any queued scale

    @workflow.run
    async def run(self, input: NodePoolManagerInput) -> None:
        iteration = 0

        while True:
            # --- Exit or history-reset when idle ---
            if self._pending_scale is None and self._pending_delete is None:
                if iteration >= _MAX_ITERATIONS:
                    workflow.continue_as_new(input)
                return

            # --- Delete takes priority over scale ---
            if self._pending_delete is not None:
                sig = self._pending_delete
                self._pending_delete = None
                await self._handle_delete(sig)
                iteration += 1
                continue

            # --- Process scale ---
            sig = self._pending_scale
            self._pending_scale = None
            await self._handle_scale(sig, input)
            iteration += 1

    async def _handle_scale(
        self, sig: ScaleSignal, input: NodePoolManagerInput
    ) -> None:
        # Read current state from Git
        current: dict[str, int] = await workflow.execute_activity(
            read_cluster_state,
            ClusterStateInput(git_base_path=sig.git_base_path, zones=ZONES),
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )

        # Pre-commit checkpoint: pivot if a newer signal arrived during git read
        if self._pending_scale is not None:
            sig = self._pending_scale
            self._pending_scale = None

        # Re-validate after potential pivot
        if sig.desired_total < _MIN_REPLICAS:
            return

        new_distribution = distribute(sig.desired_total, ZONES)

        if all(new_distribution[z] == current.get(z) for z in ZONES):
            return  # already at desired state, nothing to commit

        await workflow.execute_activity(
            commit_cluster_distribution,
            CommitDistributionInput(
                cluster=sig.cluster,
                git_base_path=sig.git_base_path,
                distribution=new_distribution,
                desired_total=sig.desired_total,
            ),
            start_to_close_timeout=timedelta(seconds=60),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )

        await workflow.execute_activity(
            sync_argocd_app,
            ArgoCDInput(argocd_app=sig.argocd_app),
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=RetryPolicy(maximum_attempts=5),
        )

        await workflow.execute_activity(
            wait_argocd_healthy,
            ArgoCDInput(argocd_app=sig.argocd_app),
            start_to_close_timeout=timedelta(minutes=10),
            retry_policy=RetryPolicy(maximum_attempts=1),
        )

    async def _handle_delete(self, sig: DeleteSignal) -> None:
        # TODO: implement delete_nodepool_from_git activity
        # Will remove all zone YAML files from git_base_path.
        # ArgoCD prune will remove the NodePool objects from the cluster.
        workflow.logger.warning(
            f"delete signal received for {sig.cluster} — not yet implemented"
        )
