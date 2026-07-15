from __future__ import annotations

import importlib
import json
import os
from pathlib import Path

import pytest

from yts_core.components import load_component_manifest, resolve_component_paths

servctl = importlib.import_module("scripts.servctl")
supervisor = importlib.import_module("scripts.servctl.supervisor")


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _ready_result(name: str) -> servctl.ComponentResult:
    return servctl.ComponentResult(name=name, enabled=True, state="ready", detail="ok")


def test_start_local_runtime_uses_the_complete_component_sequence(tmp_path: Path) -> None:
    calls: list[str] = []

    class Lock:
        def release(self) -> None:
            calls.append("unlock")

    def acquire_lock(root: Path, owner: str, **kwargs) -> Lock:
        calls.append(f"lock:{owner}")
        return Lock()

    def verify(root: Path, names: list[str]) -> list[servctl.ComponentResult]:
        assert len(names) == 1
        calls.append(f"verify:{names[0]}")
        return [_ready_result(names[0])]

    supervisor.start_local_runtime(
        tmp_path,
        "local",
        host="127.0.0.1",
        port=8765,
        reload=False,
        frontend_host="127.0.0.1",
        frontend_port=1420,
        acquire_lock_func=acquire_lock,
        verify_components_func=verify,
        start_component_func=lambda root, profile, name, **kwargs: calls.append(
            f"start:{name}"
        ),
        wait_component_ready_func=lambda root, profile, name, **kwargs: calls.append(
            f"ready:{name}"
        ),
        start_backend_func=lambda root, profile, **kwargs: calls.append("start:backend"),
        write_runtime_config_func=lambda root, profile: calls.append("write:runtime-config"),
        start_frontend_func=lambda root, profile, **kwargs: calls.append("start:frontend"),
        stop_backend_func=lambda root, profile, **kwargs: calls.append("stop:backend"),
        stop_component_func=lambda root, profile, name, **kwargs: calls.append(
            f"stop:{name}"
        ),
    )

    assert calls == [
        "lock:servctl",
        "verify:llama",
        "verify:stable-diffusion",
        "verify:infer-gateway",
        "start:llama",
        "ready:llama",
        "start:infer-gateway",
        "ready:infer-gateway",
        "start:backend",
        "write:runtime-config",
        "start:frontend",
    ]


@pytest.mark.parametrize(
    ("fail_at", "expected_tail"),
    [
        ("verify:stable-diffusion", ["unlock"]),
        ("start:llama", ["unlock"]),
        ("ready:llama", ["stop:llama", "unlock"]),
        ("start:infer-gateway", ["stop:llama", "unlock"]),
        ("ready:infer-gateway", ["stop:infer-gateway", "stop:llama", "unlock"]),
        ("start:backend", ["stop:infer-gateway", "stop:llama", "unlock"]),
        ("write:runtime-config", ["stop:backend", "stop:infer-gateway", "stop:llama", "unlock"]),
        ("start:frontend", ["stop:backend", "stop:infer-gateway", "stop:llama", "unlock"]),
    ],
)
def test_start_local_runtime_rolls_back_after_each_boundary(
    tmp_path: Path,
    fail_at: str,
    expected_tail: list[str],
) -> None:
    calls: list[str] = []

    class Lock:
        def release(self) -> None:
            calls.append("unlock")

    def record(label: str) -> None:
        calls.append(label)
        if label == fail_at:
            raise servctl.ServctlError(f"failed at {label}")

    def verify(root: Path, names: list[str]) -> list[servctl.ComponentResult]:
        assert len(names) == 1
        record(f"verify:{names[0]}")
        return [_ready_result(names[0])]

    with pytest.raises(servctl.ServctlError, match=f"failed at {fail_at}"):
        supervisor.start_local_runtime(
            tmp_path,
            "local",
            host="127.0.0.1",
            port=8765,
            reload=False,
            frontend_host="127.0.0.1",
            frontend_port=1420,
            acquire_lock_func=lambda root, owner, **kwargs: (record(f"lock:{owner}") or Lock()),
            verify_components_func=verify,
            start_component_func=lambda root, profile, name, **kwargs: record(f"start:{name}"),
            wait_component_ready_func=lambda root, profile, name, **kwargs: record(
                f"ready:{name}"
            ),
            start_backend_func=lambda root, profile, **kwargs: record("start:backend"),
            write_runtime_config_func=lambda root, profile: record("write:runtime-config"),
            start_frontend_func=lambda root, profile, **kwargs: record("start:frontend"),
            stop_backend_func=lambda root, profile, **kwargs: record("stop:backend"),
            stop_component_func=lambda root, profile, name, **kwargs: record(f"stop:{name}"),
        )

    assert calls[-len(expected_tail) :] == expected_tail


def test_stop_local_runtime_reverses_start_order_and_aggregates_errors(tmp_path: Path) -> None:
    calls: list[str] = []

    def stop(label: str) -> None:
        calls.append(label)
        if label in {"stop:backend", "stop:infer-gateway"}:
            raise servctl.ServctlError(f"{label} failed")

    with pytest.raises(servctl.ServctlError) as exc_info:
        supervisor.stop_local_runtime(
            tmp_path,
            "local",
            host="127.0.0.1",
            port=8765,
            frontend_host="127.0.0.1",
            frontend_port=1420,
            check_lock_func=lambda root, owner, **kwargs: calls.append(f"check-lock:{owner}"),
            stop_frontend_func=lambda root, profile, **kwargs: stop("stop:frontend"),
            stop_backend_func=lambda root, profile, **kwargs: stop("stop:backend"),
            stop_component_func=lambda root, profile, name, **kwargs: stop(f"stop:{name}"),
            release_lock_func=lambda root, owner, **kwargs: calls.append(f"unlock:{owner}"),
        )

    assert calls == [
        "check-lock:servctl",
        "stop:frontend",
        "stop:backend",
        "stop:infer-gateway",
        "stop:llama",
        "unlock:servctl",
    ]
    message = str(exc_info.value)
    assert "backend: stop:backend failed" in message
    assert "infer-gateway: stop:infer-gateway failed" in message


def test_ownership_lock_refuses_live_tauri_owner_and_replaces_dead_stale_lock(
    tmp_path: Path,
) -> None:
    lock_path = supervisor.local_supervisor_lock_path(tmp_path)
    lock_path.parent.mkdir(parents=True)
    lock_path.write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "owner": "tauri",
                "pid": 424242,
                "startedAt": "2026-07-15T00:00:00Z",
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(servctl.ServctlError, match="owned by tauri"):
        supervisor.acquire_ownership_lock(
            tmp_path,
            "servctl",
            pid=111,
            process_exists=lambda pid: True,
        )

    lock = supervisor.acquire_ownership_lock(
        tmp_path,
        "servctl",
        pid=111,
        process_exists=lambda pid: False,
    )

    data = json.loads(lock_path.read_text(encoding="utf-8"))
    assert data["owner"] == "servctl"
    assert data["pid"] == 111
    lock.release()
    assert not lock_path.exists()


def test_component_pid_and_log_paths_are_profile_and_component_scoped(tmp_path: Path) -> None:
    assert (
        supervisor.component_pid_path(tmp_path, "local", "llama")
        == tmp_path / "run" / "yts-component-local-llama.pid"
    )
    assert (
        supervisor.component_log_path(tmp_path, "local", "infer-gateway")
        == tmp_path / "run" / "yts-component-local-infer-gateway.log"
    )


def test_gateway_environment_for_tracked_manifest_is_exact() -> None:
    root = _repo_root()
    manifest = load_component_manifest(root / "desktop" / "components.toml")
    image = resolve_component_paths(root, manifest, "stable-diffusion")

    gateway_env = supervisor.build_gateway_environment(root, manifest)

    assert gateway_env == {
        "YTS_GATEWAY_ADDR": "127.0.0.1:8799",
        "YTS_GATEWAY_SHUTDOWN_TIMEOUT_SECONDS": "15",
        "YTS_LLAMA_BASE_URL": "http://127.0.0.1:8080",
        "YTS_LLAMA_STARTUP_TIMEOUT_SECONDS": "120",
        "YTS_LLAMA_PROBE_TIMEOUT_SECONDS": "2",
        "YTS_LLAMA_COMPLETION_TIMEOUT_SECONDS": "120",
        "YTS_LLAMA_MODEL": "qwen",
        "YTS_IMAGEGEN_ENABLED": "true",
        "YTS_IMAGEGEN_ARGV": json.dumps(
            [
                str(image.artifact),
                "--diffusion-model",
                str(image.models["flux"]),
                "--vae",
                str(image.models["vae"]),
                "--clip_l",
                str(image.models["clip_l"]),
                "--t5xxl",
                str(image.models["t5xxl"]),
                "--prompt",
                "{prompt}",
                "--output",
                "{out}",
                "--width",
                "{width}",
                "--height",
                "{height}",
                "--steps",
                "{steps}",
                "--cfg-scale",
                "1.0",
                "--sampling-method",
                "euler",
            ],
            separators=(",", ":"),
        ),
        "YTS_IMAGEGEN_TIMEOUT_SECONDS": "600",
        "YTS_IMAGEGEN_MAX_OUTPUT_BYTES": "67108864",
        "YTS_IMAGEGEN_MAX_CONCURRENCY": "1",
        "YTS_IMAGEGEN_MAX_WIDTH": "2048",
        "YTS_IMAGEGEN_MAX_HEIGHT": "2048",
        "YTS_IMAGEGEN_MAX_STEPS": "100",
        "YTS_AUDIOGEN_ENABLED": "false",
    }


def test_gateway_environment_brackets_bare_ipv6_hosts() -> None:
    root = _repo_root()
    manifest = load_component_manifest(root / "desktop" / "components.toml")
    manifest.components["infer-gateway"].runtime.host = "2001:db8::1"
    manifest.components["llama"].runtime.host = "2001:db8::1"

    gateway_env = supervisor.build_gateway_environment(root, manifest)

    assert gateway_env["YTS_GATEWAY_ADDR"] == "[2001:db8::1]:8799"
    assert gateway_env["YTS_LLAMA_BASE_URL"] == "http://[2001:db8::1]:8080"


@pytest.mark.parametrize(
    ("case", "message"),
    [
        ("zero-models", "llama must declare exactly one model"),
        ("multiple-models", "llama must declare exactly one model"),
        ("missing-alias", "llama runtime argv must contain exactly one --alias"),
        ("duplicate-alias", "llama runtime argv must contain exactly one --alias"),
        ("dangling-alias", "llama runtime --alias must be followed by the model id"),
        ("mismatched-alias", "llama runtime --alias must match model id qwen"),
    ],
)
def test_gateway_environment_rejects_invalid_llama_model_alias_contract(
    case: str,
    message: str,
) -> None:
    root = _repo_root()
    manifest = load_component_manifest(root / "desktop" / "components.toml")
    llama = manifest.components["llama"]
    if case == "zero-models":
        llama.models = []
    elif case == "multiple-models":
        llama.models.append(
            llama.models[0].model_copy(
                update={"id": "second", "path": "llm-models/second.gguf"}
            )
        )
    elif case == "missing-alias":
        llama.runtime.argv = llama.runtime.argv[:-2]
    elif case == "duplicate-alias":
        llama.runtime.argv = [*llama.runtime.argv, "--alias", "qwen"]
    elif case == "dangling-alias":
        llama.runtime.argv = [*llama.runtime.argv[:-1]]
    elif case == "mismatched-alias":
        llama.runtime.argv = [*llama.runtime.argv[:-1], "other"]

    with pytest.raises(servctl.ServctlError, match=message):
        supervisor.build_gateway_environment(root, manifest)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("gateway_host", None, "infer-gateway runtime requires host"),
        ("gateway_port", None, "infer-gateway runtime requires port"),
        ("gateway_shutdown", None, "infer-gateway runtime requires shutdown_timeout_seconds"),
        (
            "gateway_request_timeout",
            None,
            "infer-gateway runtime requires request_timeout_seconds",
        ),
        ("llama_readiness", None, "llama runtime requires readiness"),
        ("stable_kind", "service", "stable-diffusion runtime must be command"),
        ("stable_limits_width", None, "stable-diffusion limits require max_width"),
    ],
)
def test_gateway_environment_rejects_missing_or_wrong_mapping_sources(
    field: str,
    value: object,
    message: str,
) -> None:
    root = _repo_root()
    manifest = load_component_manifest(root / "desktop" / "components.toml")
    if field == "gateway_host":
        manifest.components["infer-gateway"].runtime.host = value
    elif field == "gateway_port":
        manifest.components["infer-gateway"].runtime.port = value
    elif field == "gateway_shutdown":
        manifest.components["infer-gateway"].runtime.shutdown_timeout_seconds = value
    elif field == "gateway_request_timeout":
        manifest.components["infer-gateway"].runtime.request_timeout_seconds = value
    elif field == "llama_readiness":
        manifest.components["llama"].runtime.readiness = value
    elif field == "stable_kind":
        manifest.components["stable-diffusion"].runtime.kind = value
    elif field == "stable_limits_width":
        manifest.components["stable-diffusion"].runtime.limits.max_width = value

    with pytest.raises(servctl.ServctlError, match=message):
        supervisor.build_gateway_environment(root, manifest)


def test_cloud_start_does_not_touch_local_components(tmp_path: Path) -> None:
    calls: list[str] = []

    servctl.commands.start(
        tmp_path,
        "cloud",
        start_backend_func=lambda root, profile, **kwargs: calls.append("backend"),
        start_frontend_func=lambda root, profile, **kwargs: calls.append("frontend"),
        check_frontend_func=lambda root, profile, **kwargs: calls.append("check-frontend"),
    )

    assert calls == ["check-frontend", "backend", "frontend"]
