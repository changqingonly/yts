from __future__ import annotations

import subprocess
from pathlib import Path

FRONTEND = Path("desktop/frontend/src")


def read_source(relative_path: str) -> str:
    return (FRONTEND / relative_path).read_text(encoding="utf-8")


def test_local_startup_shares_one_promise_for_each_target() -> None:
    source = read_source("services/localStartup.js")

    assert "const apiReadinessByTarget = new Map();" in source
    assert "const playbackByTarget = new Map();" in source
    assert "const existingEntry = playbackByTarget.get(target);" in source
    assert "return existingEntry.promise;" in source
    assert "playbackByTarget.set(target, entry);" in source


def test_local_startup_runs_sidecar_health_then_explicit_preparation_callback() -> None:
    source = read_source("services/localStartup.js")

    assert "prepare," in source
    assert "export function startLocalApiReadiness" in source
    assert "startSidecar," in source
    assert "healthCheck," in source
    assert "await runStage(\"sidecar\", () => startSidecarCallback());" in source
    assert "await runStage(\"health\", () => healthCheckCallback(target));" in source
    assert "await runStage(\"prepare\", () => prepareCallback({ target }));" in source
    api_block = source.split("function getLocalApiReadinessEntry", 1)[1].split(
        "function createEntry", 1
    )[0]
    playback_block = source.split("export function startLocalPlayback", 1)[1].split(
        "function getLocalApiReadinessEntry", 1
    )[0]
    assert api_block.index('runStage("sidecar"') < api_block.index('runStage("health"')
    assert "await apiEntry.readinessPromise;" in playback_block
    assert "await runStage(\"prepare\"" in playback_block


def test_local_startup_has_bounded_timeout_and_preserves_failure_stage() -> None:
    source = read_source("services/localStartup.js")

    assert "export const LOCAL_STARTUP_TIMEOUT_MS = 30000;" in source
    assert "timeoutMs = LOCAL_STARTUP_TIMEOUT_MS" in source
    assert "async function waitForHealth" in source
    assert "for (;;)" in source
    assert "HEALTH_RETRY_INTERVAL_MS" in source
    assert "entry.lastError = error;" in source
    assert "createEntry(apiEntry)" in source
    assert "entry.lastError || entry.errorSource?.lastError || null" in source
    assert "const deadline" not in source
    assert "Promise.race([entry.readinessPromise, timeoutPromise])" in source
    assert "clearTimeout(timeoutId);" in source
    assert "error.stage = stage;" in source
    assert "createStartupTimeoutError" in source
    assert 'error.stage = "timeout";' in source


def test_local_startup_reset_keeps_in_flight_work_and_clears_settled_entries() -> None:
    source = read_source("services/localStartup.js")
    reset_block = source.split("export function resetLocalPlaybackStartup()", 1)[1].split(
        "export function startLocalPlayback", 1
    )[0]

    assert "clearSettledEntries(apiReadinessByTarget);" in reset_block
    assert "clearSettledEntries(playbackByTarget);" in reset_block
    assert "if (entry.status === \"starting\") continue;" in source


def test_local_startup_never_starts_the_inference_gateway() -> None:
    source = read_source("services/localStartup.js")

    assert "startGateway" not in source


def test_environment_health_reuses_local_startup_coordinator() -> None:
    source = read_source("stores/environment.js")

    assert 'import { startLocalApiReadiness } from "../services/localStartup";' in source
    assert 'await startLocalApiReadiness({ target: requestTarget, startSidecar, healthCheck });' in source
    assert 'import { startSidecar } from "../services/desktop";' in source
    assert "prepare: async () => {}" not in source


def test_local_startup_runtime_contracts() -> None:
    result = subprocess.run(
        ["node", "--test", "desktop/frontend/tests/localStartup.runtime.test.mjs"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "pass 7" in result.stdout
