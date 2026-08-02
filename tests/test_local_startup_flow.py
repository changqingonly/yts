from __future__ import annotations

from pathlib import Path


FRONTEND = Path("desktop/frontend/src")


def read_source(relative_path: str) -> str:
    return (FRONTEND / relative_path).read_text(encoding="utf-8")


def test_local_startup_shares_one_promise_for_each_target() -> None:
    source = read_source("services/localStartup.js")

    assert "const startupByTarget = new Map();" in source
    assert "if (startupByTarget.has(target))" in source
    assert "return startupByTarget.get(target).promise;" in source
    assert "startupByTarget.set(target, entry);" in source


def test_local_startup_runs_sidecar_health_then_explicit_preparation_callback() -> None:
    source = read_source("services/localStartup.js")

    assert "prepare," in source
    assert "startSidecar: startSidecarCallback = startSidecar" in source
    assert "healthCheck: healthCheckCallback = healthCheck" in source
    assert "await runStage(\"sidecar\", () => startSidecarCallback());" in source
    assert "await runStage(\"health\", () => healthCheckCallback(target));" in source
    assert "await runStage(\"prepare\", () => prepare({ target }));" in source
    assert source.index('runStage("sidecar"') < source.index('runStage("health"')
    assert source.index('runStage("health"') < source.index('runStage("prepare"')


def test_local_startup_has_bounded_timeout_and_preserves_failure_stage() -> None:
    source = read_source("services/localStartup.js")

    assert "timeoutMs = 5000" in source
    assert "Promise.race([readinessPromise, timeoutPromise])" in source
    assert "clearTimeout(timeoutId);" in source
    assert "error.stage = stage;" in source
    assert "createStartupTimeoutError" in source
    assert 'error.stage = "timeout";' in source


def test_local_startup_reset_keeps_in_flight_work_and_clears_settled_entries() -> None:
    source = read_source("services/localStartup.js")
    reset_block = source.split("export function resetLocalPlaybackStartup()", 1)[1].split(
        "export function startLocalPlayback", 1
    )[0]

    assert "if (entry.status !== \"starting\")" in reset_block
    assert "startupByTarget.delete(target);" in reset_block


def test_local_startup_never_starts_the_inference_gateway() -> None:
    source = read_source("services/localStartup.js")

    assert "startGateway" not in source


def test_environment_health_reuses_local_startup_coordinator() -> None:
    source = read_source("stores/environment.js")

    assert 'import { startLocalPlayback } from "../services/localStartup";' in source
    assert 'await startLocalPlayback({ target: requestTarget, prepare: async () => {} });' in source
    assert 'import { startSidecar } from "../services/desktop";' not in source
    assert "void startSidecar()" not in source
