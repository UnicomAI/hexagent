# ruff: noqa: T201
"""Integration test: verify E2B sandbox auto-reconnects after expiry.

Requires E2B_API_KEY in environment.

Usage:
    uv run pytest tests/integration_tests/computer/test_e2b_reconnect.py -v -s
"""

from __future__ import annotations

import asyncio
import os

import pytest

from hexagent.computer.remote.e2b import RemoteE2BComputer

pytestmark = pytest.mark.skipif(
    "E2B_API_KEY" not in os.environ,
    reason="E2B_API_KEY not set",
)

SHORT_LIFETIME = 15  # seconds — shortest practical value


async def test_reconnects_after_timeout() -> None:
    """Sandbox auto-pauses on timeout, then auto-reconnects on next run()."""
    computer = RemoteE2BComputer(lifetime=SHORT_LIFETIME)
    await computer.start()

    # First command works
    result = await computer.run("echo before-pause")
    assert result.exit_code == 0
    assert "before-pause" in result.stdout

    sandbox_id = computer.sandbox_id

    # Wait for the sandbox to expire / auto-pause
    print(f"\nWaiting {SHORT_LIFETIME + 5}s for sandbox {sandbox_id} to auto-pause...")
    await asyncio.sleep(SHORT_LIFETIME + 5)

    # This should detect the expired sandbox and reconnect transparently
    result = await computer.run("echo after-reconnect")
    assert result.exit_code == 0
    assert "after-reconnect" in result.stdout

    # Sandbox ID should be preserved (same sandbox resumed, not a new one)
    assert computer.sandbox_id == sandbox_id

    await computer.stop()


async def test_concurrent_runs_after_expiry() -> None:
    """Multiple concurrent run() calls after expiry don't crash."""
    computer = RemoteE2BComputer(lifetime=SHORT_LIFETIME)
    await computer.start()
    await computer.run("echo setup")

    print(f"\nWaiting {SHORT_LIFETIME + 5}s for sandbox to auto-pause...")
    await asyncio.sleep(SHORT_LIFETIME + 5)

    # Fire two commands concurrently — the exact scenario from the bug report
    results = await asyncio.gather(
        computer.run("echo concurrent-1"),
        computer.run("echo concurrent-2"),
    )
    for r in results:
        assert r.exit_code == 0

    await computer.stop()
