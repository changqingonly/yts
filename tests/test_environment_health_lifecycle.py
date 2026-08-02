from __future__ import annotations

from pathlib import Path

FRONTEND = Path("desktop/frontend/src")


def read_source(relative_path: str) -> str:
    return (FRONTEND / relative_path).read_text(encoding="utf-8")


def test_app_shell_checks_selected_api_target_on_initial_mount() -> None:
    source = read_source("app/AppShell.vue")
    mounted_block = source.split("onMounted(() => {", 1)[1].split("});", 1)[0]

    assert "void environment.checkHealth(environment.target)" in mounted_block
    assert "environment.checkAllHealth()" not in mounted_block


def test_app_shell_switches_environment_and_checks_selected_target() -> None:
    source = read_source("app/AppShell.vue")

    assert "function switchEnvironmentTarget(item)" in source
    assert "environment.setTarget(item.value);" in source
    switch_block = source.split("function switchEnvironmentTarget(item) {", 1)[1].split("}", 1)[0]
    assert "void environment.checkHealth(item.value);" in switch_block
    assert '@click="switchEnvironmentTarget(item)"' in source


def test_environment_store_exposes_selected_target_health_probe_only() -> None:
    source = read_source("stores/environment.js")

    assert 'import { healthCheck } from "../services/transport";' in source
    assert 'import { startLocalPlayback } from "../services/localStartup";' in source
    assert "const pendingHealthChecks = new Map();" in source
    assert "async checkHealth(target = this.target)" in source
    assert "if (pendingHealthChecks.has(requestTarget))" in source
    assert "return pendingHealthChecks.get(requestTarget);" in source
    assert "pendingHealthChecks.delete(requestTarget);" in source
    assert 'this.health[requestTarget] = "checking";' in source
    assert 'this.health[requestTarget] = "online";' in source
    assert 'this.health[requestTarget] = "offline";' in source
    assert 'await startLocalPlayback({ target: requestTarget, prepare: async () => {} });' in source
    assert "void startSidecar()" not in source
    assert "async checkAllHealth()" not in source
    assert "this.options.map((item) => this.checkHealth(item.value))" not in source


def test_transport_exposes_explicit_health_probe() -> None:
    source = read_source("services/transport.js")

    assert "export async function healthCheck(target = selectedApiTarget())" in source
    assert 'path: "/health"' in source
    assert "fetch(`${baseUrl}/health`" in source
