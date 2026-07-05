from __future__ import annotations

from pathlib import Path

FRONTEND = Path("desktop/frontend/src")


def read_source(relative_path: str) -> str:
    return (FRONTEND / relative_path).read_text(encoding="utf-8")


def test_app_shell_checks_only_selected_environment_on_initial_mount() -> None:
    source = read_source("app/AppShell.vue")
    mounted_block = source.split("onMounted(() => {", 1)[1].split("});", 1)[0]

    assert "environment.checkHealth(environment.target)" in mounted_block
    assert "environment.checkAllHealth()" not in mounted_block


def test_app_shell_checks_target_after_user_switches_environment() -> None:
    source = read_source("app/AppShell.vue")

    assert "function switchEnvironmentTarget(item)" in source
    assert "environment.setTarget(item.value);" in source
    assert "void environment.checkHealth(item.value);" in source
    assert '@click="switchEnvironmentTarget(item)"' in source


def test_environment_store_does_not_expose_bulk_health_probe_for_inactive_targets() -> None:
    source = read_source("stores/environment.js")

    assert "async checkAllHealth()" not in source
    assert "this.options.map((item) => this.checkHealth(item.value))" not in source


def test_health_check_uses_http_probe_without_websocket_rpc() -> None:
    source = read_source("services/transport.js")
    health_block = source.split("export async function healthCheck", 1)[1].split(
        "\n}\n\nexport function openJsonStream",
        1,
    )[0]

    assert "requestJsonOverHttp(\"/health\"" in health_block
    assert "requestJson(\"/health\"" not in health_block
    assert "requestJsonOverWebSocket" not in health_block
