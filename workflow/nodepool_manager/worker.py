from __future__ import annotations

import asyncio
import os

from temporalio.client import Client
from temporalio.worker import Worker
from temporalio.worker.workflow_sandbox import SandboxedWorkflowRunner, SandboxRestrictions

from .activities import (
    commit_cluster_distribution,
    read_cluster_state,
    sync_argocd_app,
    wait_argocd_healthy,
)
from .workflow import NodePoolManagerWorkflow

# git and aiohttp use subprocess/sockets — mark as passthrough so the
# workflow sandbox doesn't block them when activities are co-located.
_PASSTHROUGH = SandboxRestrictions.default.with_passthrough_modules(
    "git", "aiohttp", "gitpython", "gitdb", "smmap", "yaml"
)

TEMPORAL_HOST = os.getenv("TEMPORAL_HOST", "temporal-frontend.temporal.svc.cluster.local:7233")
TEMPORAL_NAMESPACE = os.getenv("TEMPORAL_NAMESPACE", "default")
TEMPORAL_TASK_QUEUE = os.getenv("TEMPORAL_TASK_QUEUE", "nodepool-manager")


async def main() -> None:
    client = await Client.connect(TEMPORAL_HOST, namespace=TEMPORAL_NAMESPACE)

    worker = Worker(
        client,
        task_queue=TEMPORAL_TASK_QUEUE,
        workflows=[NodePoolManagerWorkflow],
        activities=[
            read_cluster_state,
            commit_cluster_distribution,
            sync_argocd_app,
            wait_argocd_healthy,
        ],
        workflow_runner=SandboxedWorkflowRunner(restrictions=_PASSTHROUGH),
    )

    print(f"Worker started — queue: {TEMPORAL_TASK_QUEUE}, namespace: {TEMPORAL_NAMESPACE}")
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
