from __future__ import annotations

from pathlib import Path

FRONTEND = Path("desktop/frontend/src")


def read_source(relative_path: str) -> str:
    return (FRONTEND / relative_path).read_text(encoding="utf-8")


def test_app_shell_does_not_probe_api_targets_on_initial_mount() -> None:
    source = read_source("app/AppShell.vue")
    mounted_block = source.split("onMounted(() => {", 1)[1].split("});", 1)[0]

    assert "environment.checkHealth" not in mounted_block
    assert "environment.checkAllHealth()" not in mounted_block


def test_app_shell_switches_environment_without_health_probe() -> None:
    source = read_source("app/AppShell.vue")

    assert "function switchEnvironmentTarget(item)" in source
    assert "environment.setTarget(item.value);" in source
    switch_block = source.split("function switchEnvironmentTarget(item) {", 1)[1].split("}", 1)[0]
    assert "checkHealth" not in switch_block
    assert '@click="switchEnvironmentTarget(item)"' in source


def test_environment_store_does_not_expose_health_probe_for_inactive_targets() -> None:
    source = read_source("stores/environment.js")

    assert "import { healthCheck }" not in source
    assert "async checkHealth(" not in source
    assert "async checkAllHealth()" not in source
    assert "this.options.map((item) => this.checkHealth(item.value))" not in source


def test_transport_does_not_expose_passive_health_probe() -> None:
    source = read_source("services/transport.js")

    assert "export async function healthCheck" not in source
    assert '"/health"' not in source
