from __future__ import annotations

import os
import tempfile
from pathlib import Path

import git
import yaml


_REPO_URL = os.environ["GIT_REPO_URL"]
_TOKEN = os.environ["GIT_TOKEN"]
_BRANCH = os.getenv("GIT_BRANCH", "main")

_AUTH_URL = _REPO_URL.replace("https://", f"https://{_TOKEN}@")


def _clone(tmpdir: str) -> git.Repo:
    repo = git.Repo.clone_from(_AUTH_URL, tmpdir, branch=_BRANCH, depth=1)
    repo.config_writer().set_value("user", "name", "workflow-bot").release()
    repo.config_writer().set_value("user", "email", "workflow-bot@hypershift").release()
    return repo


def _zone_path(base_path: str, zone: str) -> str:
    """Return the relative path within the repo for a zone's nodepool manifest."""
    return f"{base_path}/{zone}.yaml"


def read_all_replicas(base_path: str, zones: list[str]) -> dict[str, int]:
    """Clone the repo and return current spec.replicas for every zone."""
    with tempfile.TemporaryDirectory() as tmpdir:
        _clone(tmpdir)
        result: dict[str, int] = {}
        for zone in zones:
            manifest = Path(tmpdir) / _zone_path(base_path, zone)
            with open(manifest) as f:
                doc = yaml.safe_load(f)
            result[zone] = int(doc["spec"]["replicas"])
        return result


def commit_distribution(
    base_path: str,
    distribution: dict[str, int],
    commit_message: str,
) -> None:
    """
    Patch spec.replicas for every zone in distribution and push in a single commit.
    Zones whose value is unchanged are skipped and not staged.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        repo = _clone(tmpdir)
        staged: list[str] = []

        for zone, desired in distribution.items():
            manifest_path = Path(tmpdir) / _zone_path(base_path, zone)
            with open(manifest_path) as f:
                doc = yaml.safe_load(f)

            if int(doc["spec"]["replicas"]) == desired:
                continue  # no change for this zone

            doc["spec"]["replicas"] = desired
            with open(manifest_path, "w") as f:
                yaml.dump(doc, f, default_flow_style=False)

            repo.index.add([str(manifest_path)])
            staged.append(zone)

        if not staged:
            return  # nothing changed

        repo.index.commit(commit_message)
        origin = repo.remote("origin")
        origin.set_url(_AUTH_URL)
        origin.push()
