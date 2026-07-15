from __future__ import annotations

import json
from pathlib import Path


def test_frontend_lockfile_includes_rolldown_wasm_transitive_packages() -> None:
    lock_path = Path(__file__).resolve().parents[1] / "desktop" / "frontend" / "package-lock.json"
    lock_data = json.loads(lock_path.read_text(encoding="utf-8"))
    packages = lock_data["packages"]

    assert "node_modules/@emnapi/core" in packages
    assert packages["node_modules/@emnapi/core"]["version"] == "1.11.1"
    assert "node_modules/@emnapi/runtime" in packages
    assert packages["node_modules/@emnapi/runtime"]["version"] == "1.11.1"


def test_frontend_install_scripts_are_explicitly_approved() -> None:
    package_path = Path(__file__).resolve().parents[1] / "desktop" / "frontend" / "package.json"
    package_data = json.loads(package_path.read_text(encoding="utf-8"))

    assert package_data["allowScripts"] == {
        "vue-demi@0.14.10": True,
        "fsevents@2.3.3": True,
    }


def test_frontend_runtime_config_is_loaded_before_vue_mount() -> None:
    root = Path(__file__).resolve().parents[1]
    http_source = (root / "desktop" / "frontend" / "src" / "services" / "http.js").read_text(
        encoding="utf-8"
    )
    main_source = (root / "desktop" / "frontend" / "src" / "main.js").read_text(
        encoding="utf-8"
    )
    runtime_config_source = (
        root / "desktop" / "frontend" / "src" / "services" / "runtimeConfig.js"
    ).read_text(encoding="utf-8")
    environment_source = (
        root / "desktop" / "frontend" / "src" / "services" / "environment.js"
    ).read_text(encoding="utf-8")
    environment_store_source = (
        root / "desktop" / "frontend" / "src" / "stores" / "environment.js"
    ).read_text(encoding="utf-8")
    creation_source = (
        root / "desktop" / "frontend" / "src" / "pages" / "CreationPage.vue"
    ).read_text(encoding="utf-8")
    music_source = (root / "desktop" / "frontend" / "src" / "pages" / "MusicPage.vue").read_text(
        encoding="utf-8"
    )
    shell_source = (root / "desktop" / "frontend" / "src" / "app" / "AppShell.vue").read_text(
        encoding="utf-8"
    )
    package_data = json.loads(
        (root / "desktop" / "frontend" / "package.json").read_text(encoding="utf-8")
    )
    public_runtime_config = json.loads(
        (root / "desktop" / "frontend" / "public" / "runtime-config.json").read_text(
            encoding="utf-8"
        )
    )

    assert 'import { loadRuntimeConfig } from "./services/runtimeConfig";' in main_source
    assert "await loadRuntimeConfig();" in main_source
    assert main_source.index("await loadRuntimeConfig();") < main_source.index("createApp(App)")
    assert "renderFatalConfigurationError" in main_source
    assert "throw error;" in main_source
    assert "export function validateRuntimeConfig" in runtime_config_source
    assert "cache: \"no-store\"" in runtime_config_source
    assert "export function configureEnvironment" in environment_source
    assert "getRuntimeConfig" in environment_source
    assert "export const ENVIRONMENT_TARGETS = {" not in environment_source
    assert "DEFAULT_ENVIRONMENT_TARGET" not in environment_source
    assert "VITE_YTS_DEFAULT_TARGET" not in environment_source
    assert "http://127.0.0.1:8765" not in environment_source
    assert "ws://127.0.0.1:8799" not in environment_source
    assert "http://127.0.0.1:8000" not in environment_source
    assert "export function endpointForTarget(target)" in environment_source
    assert 'export const API_TARGET_CHANGED_EVENT = "yts-target-changed";' in environment_source
    assert "export function selectedApiTarget()" in environment_source
    assert (
        "return stored ? assertApiTarget(stored) : getRuntimeConfig().defaultTarget;"
        in environment_source
    )
    assert "export function setSelectedApiTarget(target)" in environment_source
    assert "window.dispatchEvent(" in environment_source
    assert "new CustomEvent(API_TARGET_CHANGED_EVENT" in environment_source
    assert (
        'export const useEnvironmentStore = defineStore("environment"' in environment_store_source
    )
    assert "target: selectedApiTarget()" in environment_store_source
    assert "health: Object.fromEntries(environmentOptions().map" in environment_store_source
    assert "setSelectedApiTarget(nextTarget)" in environment_store_source
    assert "async checkHealth(target = this.target)" in environment_store_source
    assert "healthCheck" in environment_store_source
    assert "VITE_YTS_DEFAULT_TARGET" not in http_source
    assert 'from "./transport"' in http_source
    assert "apiBase, requestJson, websocketBase" in http_source
    assert package_data["scripts"]["test:runtime-config"] == (
        "node --test tests/runtime-config.test.mjs"
    )
    assert public_runtime_config == {
        "schemaVersion": 1,
        "profile": "local",
        "defaultTarget": "local",
        "targets": {
            "local": {
                "apiBase": "http://127.0.0.1:8765",
                "musicWsBase": "ws://127.0.0.1:8799",
            },
            "cloud": {
                "apiBase": "http://127.0.0.1:8000",
                "musicWsBase": "ws://127.0.0.1:8000",
            },
        },
    }
    assert "const environment = useEnvironmentStore();" in shell_source
    assert "environment.setTarget(item.value)" in shell_source
    assert "return selectedApiTarget();" in creation_source
    assert "selectedApiTarget()" in music_source


def test_frontend_shared_requests_follow_the_selected_api_target() -> None:
    root = Path(__file__).resolve().parents[1]
    http_source = (root / "desktop" / "frontend" / "src" / "services" / "http.js").read_text(
        encoding="utf-8"
    )
    music_service_source = (
        root / "desktop" / "frontend" / "src" / "services" / "music.js"
    ).read_text(encoding="utf-8")

    environment_source = (
        root / "desktop" / "frontend" / "src" / "services" / "environment.js"
    ).read_text(encoding="utf-8")

    assert "function assertApiTarget(target)" in environment_source
    assert (
        "return stored ? assertApiTarget(stored) : getRuntimeConfig().defaultTarget;"
        in environment_source
    )
    assert "throw new Error(`Unsupported API target: ${target}`);" in environment_source
    assert 'from "./transport"' in http_source
    assert 'uploadForm("/api/music/upload", form)' in music_service_source
    assert "/api/music/local_import/upload" not in music_service_source


def test_frontend_network_outlets_are_centralized_in_transport_service() -> None:
    root = Path(__file__).resolve().parents[1]
    frontend_src = root / "desktop" / "frontend" / "src"
    allowed = {
        frontend_src / "services" / "runtimeConfig.js",
        frontend_src / "services" / "transport.js",
    }
    offenders: list[str] = []
    for path in frontend_src.rglob("*"):
        if not path.is_file() or path.suffix not in {".js", ".vue"} or path in allowed:
            continue
        source = path.read_text(encoding="utf-8")
        if "fetch(" in source or "new WebSocket(" in source:
            offenders.append(str(path.relative_to(frontend_src)))

    assert offenders == []


def test_frontend_transport_defaults_to_websocket_rpc_with_http_fallback() -> None:
    root = Path(__file__).resolve().parents[1]
    transport_source = (
        root / "desktop" / "frontend" / "src" / "services" / "transport.js"
    ).read_text(encoding="utf-8")

    assert "export async function requestJson(path, options = {})" in transport_source
    assert "await requestJsonOverWebSocket" in transport_source
    assert "return requestJsonOverHttp(path, options);" in transport_source
    assert "new WebSocket(rpcWebSocketUrl(target))" in transport_source
    assert 'code === "WS_CONNECT_FAILED"' in transport_source
    assert (
        "export function openJsonStream(path, payload, handlers = {}, options = {})"
        in transport_source
    )
    assert "if (!opened && fallbackJson)" in transport_source
