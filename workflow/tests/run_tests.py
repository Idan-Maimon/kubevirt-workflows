"""
NodePool Manager Workflow — integration test suite.

Usage:
    cd workflow/
    .venv/bin/python -I tests/run_tests.py
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path

# Load .env
_ENV = Path(__file__).parent.parent / ".env"
if _ENV.exists():
    for line in _ENV.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

os.environ["TEMPORAL_HOST"] = "localhost:7233"
sys.path.insert(0, str(Path(__file__).parent.parent))

from temporalio.client import Client, WorkflowExecutionStatus
from temporalio.common import WorkflowIDConflictPolicy

from nodepool_manager.workflow import NodePoolManagerInput, NodePoolManagerWorkflow
from nodepool_manager.models import ScaleSignal, DeleteSignal, ZONES
from shared.git_client import read_all_replicas

TEMPORAL_HOST      = os.environ["TEMPORAL_HOST"]
TEMPORAL_NAMESPACE = os.getenv("TEMPORAL_NAMESPACE", "default")
TEMPORAL_QUEUE     = os.getenv("TEMPORAL_TASK_QUEUE", "nodepool-manager")

CLUSTER       = "OCP-A"
ARGOCD_APP    = "ocp-a"
GIT_BASE      = "nodepools/OCP-A"
WORKFLOW_ID   = f"scale-{CLUSTER}"
STARTUP_INPUT = NodePoolManagerInput(cluster=CLUSTER)


@dataclass
class TestResult:
    name: str
    passed: bool
    note: str
    duration_s: float
    issues: list[str]


results: list[TestResult] = []


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def make_signal(desired_total: int) -> ScaleSignal:
    return ScaleSignal(
        cluster=CLUSTER,
        desired_total=desired_total,
        argocd_app=ARGOCD_APP,
        git_base_path=GIT_BASE,
    )


async def signal_with_start(client: Client, signal: ScaleSignal) -> None:
    await client.start_workflow(
        NodePoolManagerWorkflow.run,
        STARTUP_INPUT,
        id=WORKFLOW_ID,
        task_queue=TEMPORAL_QUEUE,
        id_conflict_policy=WorkflowIDConflictPolicy.USE_EXISTING,
        start_signal="scale",
        start_signal_args=[signal],
    )


async def wait_for_idle(client: Client, timeout: int = 120) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            handle = client.get_workflow_handle(WORKFLOW_ID)
            desc = await handle.describe()
            if desc.status != WorkflowExecutionStatus.RUNNING:
                return True
        except Exception:
            return True
        await asyncio.sleep(2)
    return False


def read_git() -> dict[str, int]:
    return read_all_replicas(GIT_BASE, ZONES)


def record(name: str, expected: dict[str, int], actual: dict[str, int], note: str, t0: float) -> None:
    issues = [
        f"{z}: expected {expected.get(z)}, got {actual.get(z)}"
        for z in ZONES if actual.get(z) != expected.get(z)
    ]
    passed = not issues
    duration = time.time() - t0
    results.append(TestResult(name, passed, note, duration, issues))
    print(f"  [{'PASS' if passed else 'FAIL'}] {name} ({duration:.1f}s) — {note}")
    for i in issues:
        print(f"         ✗ {i}")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
async def test_basic_scale_up(client: Client) -> None:
    print("\n[1] Basic scale up: total 5 → 10")
    t0 = time.time()
    await signal_with_start(client, make_signal(10))
    await wait_for_idle(client)
    record("basic_scale_up",
           {"zone-1": 4, "zone-2": 3, "zone-3": 3}, read_git(),
           "10 // 3 = 3 r1 → zone-1 gets extra (alphabetical)", t0)


async def test_noop(client: Client) -> None:
    print("\n[2] No-op: desired == current")
    current = read_git()
    total = sum(current.values())
    t0 = time.time()
    await signal_with_start(client, make_signal(total))
    await wait_for_idle(client, timeout=30)
    record("noop_same_total", current, read_git(),
           f"desired_total={total} matches git — no commit", t0)


async def test_scale_down(client: Client) -> None:
    print("\n[3] Scale down: total 10 → 6")
    t0 = time.time()
    await signal_with_start(client, make_signal(6))
    await wait_for_idle(client)
    record("scale_down",
           {"zone-1": 2, "zone-2": 2, "zone-3": 2}, read_git(),
           "6 // 3 = 2 r0 → all zones equal", t0)


async def test_signal_coalescing(client: Client) -> None:
    print("\n[4] Signal coalescing: 20, 9, 14 fired rapidly")
    await signal_with_start(client, make_signal(6))
    await wait_for_idle(client)

    t0 = time.time()
    await signal_with_start(client, make_signal(20))
    await signal_with_start(client, make_signal(9))
    await signal_with_start(client, make_signal(14))
    await wait_for_idle(client)

    actual = read_git()
    total = sum(actual.values())
    issues = [] if total == 14 else [f"expected total=14, got {total} — intermediate leaked"]
    passed = not issues
    duration = time.time() - t0
    results.append(TestResult("signal_coalescing", passed,
                              "only desired_total=14 should apply", duration, issues))
    print(f"  [{'PASS' if passed else 'FAIL'}] signal_coalescing ({duration:.1f}s)"
          + (f" ✗ {issues[0]}" if issues else ""))


async def test_below_minimum_rejected(client: Client) -> None:
    """desired_total < len(ZONES) must be rejected by the workflow signal handler."""
    print("\n[5] Below-minimum rejected: desired_total=2 (min is 3)")
    before = read_git()
    t0 = time.time()
    await signal_with_start(client, make_signal(2))
    await wait_for_idle(client, timeout=20)
    after = read_git()
    issues = []
    if after != before:
        issues.append(f"git changed despite below-minimum signal: {before} → {after}")
    passed = not issues
    duration = time.time() - t0
    results.append(TestResult("below_minimum_rejected", passed,
                              "signal discarded, git unchanged", duration, issues))
    print(f"  [{'PASS' if passed else 'FAIL'}] below_minimum_rejected ({duration:.1f}s)")
    for i in issues:
        print(f"         ✗ {i}")


async def test_delete_signal_stub(client: Client) -> None:
    """delete() signal must be accepted without crashing — implementation is a stub."""
    print("\n[6] Delete signal: accepted, logs warning, no git change")
    before = read_git()
    t0 = time.time()
    handle = await client.start_workflow(
        NodePoolManagerWorkflow.run,
        STARTUP_INPUT,
        id=WORKFLOW_ID,
        task_queue=TEMPORAL_QUEUE,
        id_conflict_policy=WorkflowIDConflictPolicy.USE_EXISTING,
        start_signal="delete",
        start_signal_args=[DeleteSignal(cluster=CLUSTER, argocd_app=ARGOCD_APP, git_base_path=GIT_BASE)],
    )
    await wait_for_idle(client, timeout=20)
    after = read_git()
    issues = []
    if after != before:
        issues.append("git changed unexpectedly after delete stub")
    passed = not issues
    duration = time.time() - t0
    results.append(TestResult("delete_signal_stub", passed,
                              "stub logged warning, no git mutation", duration, issues))
    print(f"  [{'PASS' if passed else 'FAIL'}] delete_signal_stub ({duration:.1f}s)")
    for i in issues:
        print(f"         ✗ {i}")


async def test_restore(client: Client) -> None:
    print("\n[7] Restore to starting state (total=5)")
    t0 = time.time()
    await signal_with_start(client, make_signal(5))
    await wait_for_idle(client)
    record("restore_original_state",
           {"zone-1": 2, "zone-2": 2, "zone-3": 1}, read_git(),
           "5 // 3 = 1 r2 → zone-1:2, zone-2:2, zone-3:1", t0)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
async def main() -> None:
    print("=" * 60)
    print("NodePool Manager — Integration Tests")
    print(f"Temporal: {TEMPORAL_HOST}  queue: {TEMPORAL_QUEUE}")
    print("=" * 60)

    client = await Client.connect(TEMPORAL_HOST, namespace=TEMPORAL_NAMESPACE)

    await test_basic_scale_up(client)
    await test_noop(client)
    await test_scale_down(client)
    await test_signal_coalescing(client)
    await test_below_minimum_rejected(client)
    await test_delete_signal_stub(client)
    await test_restore(client)

    passed = [r for r in results if r.passed]
    failed = [r for r in results if not r.passed]

    print("\n" + "=" * 60)
    print(f"RESULTS  {len(passed)}/{len(results)} passed")
    print("=" * 60)
    for r in results:
        icon = "✓" if r.passed else "✗"
        print(f"  {icon} {r.name:<35} {r.duration_s:5.1f}s")
        for issue in r.issues:
            print(f"      → {issue}")

    print("\nIMPROVEMENT FLAGS:")
    print("  ⚠  Naming schema not yet auto-derived — argocd_app and git_base_path are still required fields")
    print("  ⚠  delete() is a stub — implement delete_nodepool_from_git activity")
    print("  ⚠  ArgoCD JWT token expires ~24h — use a service account token")
    print("  ⚠  git clone per activity call — consider persistent shallow clone")


if __name__ == "__main__":
    asyncio.run(main())
