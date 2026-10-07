from __future__ import annotations

import asyncio
import os
from typing import Literal

import aiohttp

_ARGOCD_URL = os.getenv(
    "ARGOCD_URL",
    "https://openshift-gitops-server-openshift-gitops.apps.cluster-98dwb.dyn.redhatworkshops.io",
)
_ARGOCD_TOKEN = os.environ["ARGOCD_TOKEN"]

_HEADERS = {
    "Authorization": f"Bearer {_ARGOCD_TOKEN}",
    "Content-Type": "application/json",
}

# ArgoCD in OpenShift uses a self-signed cert — skip verification inside the cluster.
_SSL = False

_POLL_INTERVAL_SECONDS = 10
_HEALTHY: Literal["Healthy"] = "Healthy"
_SYNCED: Literal["Synced"] = "Synced"


async def sync_app(app_name: str) -> None:
    """Trigger an ArgoCD sync for the given application."""
    url = f"{_ARGOCD_URL}/api/v1/applications/{app_name}/sync"
    async with aiohttp.ClientSession(headers=_HEADERS) as session:
        async with session.post(url, ssl=_SSL) as resp:
            resp.raise_for_status()


async def wait_until_healthy(app_name: str, timeout_seconds: int = 600) -> None:
    """Poll until the ArgoCD application is Healthy and Synced, or raise on timeout."""
    url = f"{_ARGOCD_URL}/api/v1/applications/{app_name}"
    deadline = asyncio.get_event_loop().time() + timeout_seconds

    async with aiohttp.ClientSession(headers=_HEADERS) as session:
        while True:
            if asyncio.get_event_loop().time() > deadline:
                raise TimeoutError(
                    f"ArgoCD app {app_name!r} did not become healthy within {timeout_seconds}s"
                )

            async with session.get(url, ssl=_SSL) as resp:
                resp.raise_for_status()
                body = await resp.json()

            health = body.get("status", {}).get("health", {}).get("status")
            sync = body.get("status", {}).get("sync", {}).get("status")

            if health == _HEALTHY and sync == _SYNCED:
                return

            await asyncio.sleep(_POLL_INTERVAL_SECONDS)
