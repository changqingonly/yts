from __future__ import annotations

import importlib.util
import signal
import socket
import subprocess
import sys
from pathlib import Path

import pytest

_SERVCTL_PATH = Path(__file__).resolve().parents[1] / "scripts" / "servctl.py"
_SERVCTL_SPEC = importlib.util.spec_from_file_location("servctl", _SERVCTL_PATH)
assert _SERVCTL_SPEC is not None
servctl = importlib.util.module_from_spec(_SERVCTL_SPEC)
assert _SERVCTL_SPEC.loader is not None
sys.modules[_SERVCTL_SPEC.name] = servctl
_SERVCTL_SPEC.loader.exec_module(servctl)


def _write_profile_config(root: Path, profile: str = "cloud") -> None:
    conf_dir = root / "conf"
    conf_dir.mkdir()
    (conf_dir / f"{profile}.env").write_text(
        "\n".join(
            [
                f"YTS_PROFILE={profile}",
                "YTS_INFERENCE_BACKEND=cloud",
                "YTS_DATABASE_URL=sqlite+aiosqlite:///./test.db",
                "YTS_AUTH_JWT_SECRET=test-secret-that-is-long-enough-for-hs256",
            ]
        ),
        encoding="utf-8",
    )


def _write_frontend_dist(root: Path) -> None:
    dist_dir = root / "desktop" / "frontend" / "dist"
    dist_dir.mkdir(parents=True)
    (dist_dir / "index.html").write_text('<div id="app"></div>', encoding="utf-8")


def _unused_tcp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def test_require_profile_config_rejects_missing_real_env_file(tmp_path: Path) -> None:
    conf_dir = tmp_path / "conf"
    conf_dir.mkdir()
    (conf_dir / "cloud.example.env").write_text("YTS_PROFILE=cloud\n", encoding="utf-8")

    with pytest.raises(servctl.ServctlError, match="missing required config file"):
        servctl.require_profile_config(tmp_path, "cloud")


def test_load_profile_env_parses_values_without_shell_fallback(tmp_path: Path) -> None:
    _write_profile_config(tmp_path)
    config_path = tmp_path / "conf" / "cloud.env"
    config_path.write_text(
        "\n".join(
            [
                "YTS_PROFILE=cloud",
                "YTS_OPENAI_API_KEY='sk-test'",
                'YTS_OPENAI_TEXT_MODEL="gpt-4.1-mini"',
                "YTS_EMPTY=",
                "# ignored",
            ]
        ),
        encoding="utf-8",
    )

    env = servctl.load_profile_env(tmp_path, "cloud")

    assert env["YTS_PROFILE"] == "cloud"
    assert env["YTS_OPENAI_API_KEY"] == "sk-test"
    assert env["YTS_OPENAI_TEXT_MODEL"] == "gpt-4.1-mini"
    assert env["YTS_EMPTY"] == ""


def test_servctl_product_inference_backends_are_local_and_cloud_only() -> None:
    assert servctl.SUPPORTED_INFERENCE_BACKENDS == ("local", "cloud")


def test_validate_profile_config_rejects_unsupported_inference_backend(tmp_path: Path) -> None:
    _write_profile_config(tmp_path)
    config_path = tmp_path / "conf" / "cloud.env"
    config_path.write_text(
        "\n".join(
            [
                "YTS_PROFILE=cloud",
                "YTS_INFERENCE_BACKEND=deepseek",
                "YTS_DATABASE_URL=sqlite+aiosqlite:///./test.db",
                "YTS_AUTH_JWT_SECRET=test-secret-that-is-long-enough-for-hs256",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(servctl.ServctlError, match="unsupported YTS_INFERENCE_BACKEND=deepseek"):
        servctl.validate_profile_config(tmp_path, "cloud")


def test_validate_profile_config_accepts_product_local_backend(tmp_path: Path) -> None:
    _write_profile_config(tmp_path, "local")
    config_path = tmp_path / "conf" / "local.env"
    config_path.write_text(
        "\n".join(
            [
                "YTS_PROFILE=local",
                "YTS_INFERENCE_BACKEND=local",
                "YTS_DATABASE_URL=sqlite+aiosqlite:///./test.db",
                "YTS_AUTH_JWT_SECRET=test-secret-that-is-long-enough-for-hs256",
            ]
        ),
        encoding="utf-8",
    )

    servctl.validate_profile_config(tmp_path, "local")


@pytest.mark.parametrize("backend", ["echo", "openai", "gateway", "pro-fixture"])
def test_validate_profile_config_rejects_removed_inference_backends(
    tmp_path: Path,
    backend: str,
) -> None:
    _write_profile_config(tmp_path)
    config_path = tmp_path / "conf" / "cloud.env"
    config_path.write_text(
        "\n".join(
            [
                "YTS_PROFILE=cloud",
                f"YTS_INFERENCE_BACKEND={backend}",
                "YTS_DATABASE_URL=sqlite+aiosqlite:///./test.db",
                "YTS_AUTH_JWT_SECRET=test-secret-that-is-long-enough-for-hs256",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(servctl.ServctlError, match=f"unsupported YTS_INFERENCE_BACKEND={backend}"):
        servctl.validate_profile_config(tmp_path, "cloud")


def test_validate_profile_config_rejects_missing_deepseek_key_for_cloud_backend(
    tmp_path: Path,
) -> None:
    _write_profile_config(tmp_path)
    config_path = tmp_path / "conf" / "cloud.env"
    config_path.write_text(
        "\n".join(
            [
                "YTS_PROFILE=cloud",
                "YTS_INFERENCE_BACKEND=cloud",
                "YTS_DEFAULT_TEXT_MODEL=deepseek/deepseek-chat",
                "YTS_DEEPSEEK_API_KEY=",
                "YTS_DATABASE_URL=sqlite+aiosqlite:///./test.db",
                "YTS_AUTH_JWT_SECRET=test-secret-that-is-long-enough-for-hs256",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(servctl.ServctlError, match="YTS_DEEPSEEK_API_KEY must be configured"):
        servctl.validate_profile_config(tmp_path, "cloud")


def test_validate_profile_config_rejects_missing_deepseek_key_for_v4_model(tmp_path: Path) -> None:
    _write_profile_config(tmp_path)
    config_path = tmp_path / "conf" / "cloud.env"
    config_path.write_text(
        "\n".join(
            [
                "YTS_PROFILE=cloud",
                "YTS_INFERENCE_BACKEND=cloud",
                "YTS_DEFAULT_TEXT_MODEL=deepseek-v4-pro",
                "YTS_DEEPSEEK_API_KEY=",
                "YTS_DATABASE_URL=sqlite+aiosqlite:///./test.db",
                "YTS_AUTH_JWT_SECRET=test-secret-that-is-long-enough-for-hs256",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(servctl.ServctlError, match="YTS_DEEPSEEK_API_KEY must be configured"):
        servctl.validate_profile_config(tmp_path, "cloud")


@pytest.mark.parametrize("model", ["openai/gpt-4.1-mini", "gpt-5.5"])
def test_validate_profile_config_rejects_missing_openai_key_for_cloud_backend(
    tmp_path: Path,
    model: str,
) -> None:
    _write_profile_config(tmp_path)
    config_path = tmp_path / "conf" / "cloud.env"
    config_path.write_text(
        "\n".join(
            [
                "YTS_PROFILE=cloud",
                "YTS_INFERENCE_BACKEND=cloud",
                f"YTS_DEFAULT_TEXT_MODEL={model}",
                "YTS_OPENAI_API_KEY=",
                "YTS_DATABASE_URL=sqlite+aiosqlite:///./test.db",
                "YTS_AUTH_JWT_SECRET=test-secret-that-is-long-enough-for-hs256",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(servctl.ServctlError, match="YTS_OPENAI_API_KEY must be configured"):
        servctl.validate_profile_config(tmp_path, "cloud")


def test_deploy_checks_python_and_node_environment_before_building(tmp_path: Path) -> None:
    _write_profile_config(tmp_path)
    frontend_dir = tmp_path / "desktop" / "frontend"
    frontend_dir.mkdir(parents=True)
    (frontend_dir / "package-lock.json").write_text("{}", encoding="utf-8")
    (tmp_path / "uv.lock").write_text("", encoding="utf-8")
    (tmp_path / ".venv").mkdir()
    commands: list[tuple[str, ...]] = []

    def run_command(command: list[str], **kwargs) -> None:
        commands.append(tuple(command))
        if command == ["npm", "run", "build"]:
            dist_dir = frontend_dir / "dist"
            dist_dir.mkdir()
            (dist_dir / "index.html").write_text("<div></div>", encoding="utf-8")

    servctl.deploy(tmp_path, "cloud", run_command=run_command)

    assert commands == [
        ("uv", "run", "python", "-c", "from yts_core.config import get_settings; get_settings()"),
        ("npm", "run", "build"),
    ]


def test_deploy_requires_installed_local_venv(tmp_path: Path) -> None:
    _write_profile_config(tmp_path)
    frontend_dir = tmp_path / "desktop" / "frontend"
    frontend_dir.mkdir(parents=True)
    (frontend_dir / "package-lock.json").write_text("{}", encoding="utf-8")
    (tmp_path / "uv.lock").write_text("", encoding="utf-8")

    with pytest.raises(servctl.ServctlError, match="missing local Python environment"):
        servctl.deploy(tmp_path, "cloud", run_command=lambda command, **kwargs: None)


def test_deploy_fails_when_frontend_dist_is_missing(tmp_path: Path) -> None:
    _write_profile_config(tmp_path)
    frontend_dir = tmp_path / "desktop" / "frontend"
    frontend_dir.mkdir(parents=True)
    (frontend_dir / "package-lock.json").write_text("{}", encoding="utf-8")
    (tmp_path / "uv.lock").write_text("", encoding="utf-8")
    (tmp_path / ".venv").mkdir()

    def run_command(command: list[str], **kwargs) -> None:
        return None

    with pytest.raises(servctl.ServctlError, match="frontend build did not produce"):
        servctl.deploy(tmp_path, "cloud", run_command=run_command)


def test_start_runs_preflight_before_exposing_port(tmp_path: Path) -> None:
    _write_profile_config(tmp_path)
    calls: list[str] = []

    def preflight(root: Path, profile: str, port: int, host: str) -> None:
        calls.append(f"preflight:{profile}:{host}:{port}")

    def spawn(config: servctl.ServerProcessConfig) -> int:
        calls.append(f"spawn:{config.profile}:{config.host}:{config.port}")
        return 12345

    def wait_health(host: str, port: int, timeout_seconds: float) -> None:
        calls.append(f"health:{host}:{port}:{timeout_seconds}")

    servctl.start_server(
        tmp_path,
        "cloud",
        host="127.0.0.1",
        port=8000,
        reload=False,
        preflight=preflight,
        spawn=spawn,
        wait_health=wait_health,
        is_process_running=lambda pid: False,
    )

    assert calls == [
        "preflight:cloud:127.0.0.1:8000",
        "spawn:cloud:127.0.0.1:8000",
        "health:127.0.0.1:8000:30.0",
    ]
    assert (tmp_path / "run" / "yts-server-cloud.pid").read_text(encoding="utf-8") == "12345\n"


def test_start_server_prepares_log_before_preflight_and_port_bind(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_profile_config(tmp_path)
    calls: list[str] = []

    def prepare_log(path: Path) -> None:
        calls.append(f"log:{path.name}")

    def preflight(root: Path, profile: str, port: int, host: str) -> None:
        calls.append("preflight")

    def spawn(config: servctl.ServerProcessConfig) -> int:
        calls.append("spawn")
        assert config.env["YTS_SKIP_STARTUP_DB_BOOTSTRAP"] == "1"
        return 12345

    monkeypatch.setattr(servctl, "_prepare_log_file", prepare_log)

    servctl.start_server(
        tmp_path,
        "cloud",
        host="127.0.0.1",
        port=8000,
        reload=False,
        preflight=preflight,
        spawn=spawn,
        wait_health=lambda host, port, timeout_seconds: calls.append("health"),
        is_process_running=lambda pid: False,
        progress=lambda message: calls.append(f"progress:{message}"),
    )

    assert calls == [
        "progress:preparing backend log: yts-server-cloud.log",
        "log:yts-server-cloud.log",
        "progress:checking backend dependencies: http://127.0.0.1:8000",
        "preflight",
        "progress:starting backend listener: http://127.0.0.1:8000",
        "spawn",
        "health",
        "progress:backend ready: http://127.0.0.1:8000",
    ]


def test_preflight_python_code_uses_plain_message_dict_literals() -> None:
    code = servctl._preflight_python_code(port=8000, host="127.0.0.1")

    assert 'messages = [{"role": "user", "content": "Return the word ok."}]' in code
    assert "YTS_PRO_STAGE" not in code
    assert "pro-fixture" not in code
    assert "from yts_core.orchestration.checkpointing import setup_langgraph_checkpointer" in code
    assert "from yts_server.db.bootstrap import create_all_tables" in code
    assert "await create_all_tables()" in code
    assert 'if settings.langgraph_checkpoint_backend.strip().lower() == "postgres":' in code
    assert "setup_langgraph_checkpointer(settings)" in code
    assert "LLM preflight failed" in code
    assert "servctl preflight failed" in code
    assert "raise SystemExit" in code
    assert "{{" not in code
    assert "}}" not in code
    assert code.index("await create_all_tables()") < code.index("backend = make_backend")
    assert code.index("setup_langgraph_checkpointer(settings)") < code.index(
        "backend = make_backend"
    )
    assert code.index("backend = make_backend") < code.index("app = create_app()")


def test_run_python_probe_reports_subprocess_failure_without_dumping_probe_code(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    probe_code = "print('probe implementation details')"

    def fail_if_check_call_is_used(command: list[str], **kwargs) -> None:
        raise AssertionError("_run_python_probe must capture probe output")

    def fake_run(command: list[str], **kwargs):
        assert command == ["uv", "run", "python", "-c", probe_code]
        return subprocess.CompletedProcess(
            command,
            1,
            stdout="preflight stdout\n",
            stderr="servctl preflight failed: RuntimeError: LLM preflight failed\n",
        )

    monkeypatch.setattr(servctl.subprocess, "check_call", fail_if_check_call_is_used)
    monkeypatch.setattr(servctl.subprocess, "run", fake_run)

    with pytest.raises(servctl.ServctlError) as exc_info:
        servctl._run_python_probe(tmp_path, {"PATH": "/bin"}, probe_code)

    message = str(exc_info.value)
    assert "preflight probe failed with exit code 1" in message
    assert "servctl preflight failed: RuntimeError: LLM preflight failed" in message
    assert probe_code not in message


def test_start_does_not_run_deploy_environment_installation(tmp_path: Path) -> None:
    _write_profile_config(tmp_path)
    commands: list[list[str]] = []

    def forbidden_deploy_command(command: list[str], **kwargs) -> None:
        commands.append(command)

    servctl.start_server(
        tmp_path,
        "cloud",
        preflight=lambda root, profile, port, host: None,
        spawn=lambda config: 12345,
        wait_health=lambda host, port, timeout_seconds: None,
        is_process_running=lambda pid: False,
    )

    assert commands == []


def test_process_log_paths_come_from_profile_logging_config(tmp_path: Path) -> None:
    _write_profile_config(tmp_path)
    config_path = tmp_path / "conf" / "cloud.env"
    with config_path.open("a", encoding="utf-8") as handle:
        handle.write(
            "\n".join(
                [
                    "",
                    "YTS_LOGGING_DIR=logs/runtime",
                    "YTS_LOGGING_BACKEND_FILE=backend-{profile}.log",
                    "YTS_LOGGING_FRONTEND_FILE=frontend-{profile}.log",
                ]
            )
        )

    server_config = servctl._server_process_config(
        tmp_path,
        "cloud",
        host="127.0.0.1",
        port=8000,
        reload=False,
    )
    frontend_config = servctl._frontend_process_config(
        tmp_path,
        "cloud",
        host="127.0.0.1",
        port=1420,
    )

    assert server_config.log_path == tmp_path / "logs" / "runtime" / "backend-cloud.log"
    assert frontend_config.log_path == tmp_path / "logs" / "runtime" / "frontend-cloud.log"


def test_log_file_template_rejects_unknown_variables(tmp_path: Path) -> None:
    _write_profile_config(tmp_path)
    config_path = tmp_path / "conf" / "cloud.env"
    with config_path.open("a", encoding="utf-8") as handle:
        handle.write("\nYTS_LOGGING_BACKEND_FILE=backend-{unknown}.log\n")

    with pytest.raises(servctl.ServctlError, match="unsupported log file template variable"):
        servctl._server_process_config(
            tmp_path,
            "cloud",
            host="127.0.0.1",
            port=8000,
            reload=False,
        )


def test_start_runs_backend_then_frontend_preview(tmp_path: Path) -> None:
    _write_profile_config(tmp_path)
    _write_frontend_dist(tmp_path)
    calls: list[str] = []

    servctl.start(
        tmp_path,
        "cloud",
        host="127.0.0.1",
        port=8000,
        reload=False,
        frontend_host="127.0.0.1",
        frontend_port=1420,
        start_backend_func=lambda root, profile, **kwargs: calls.append(
            f"backend:{profile}:{kwargs['host']}:{kwargs['port']}:{kwargs['reload']}"
        ),
        start_frontend_func=lambda root, profile, **kwargs: calls.append(
            f"frontend:{profile}:{kwargs['host']}:{kwargs['port']}"
        ),
        check_frontend_func=lambda root, profile, **kwargs: None,
    )

    assert calls == [
        "backend:cloud:127.0.0.1:8000:False",
        "frontend:cloud:127.0.0.1:1420",
    ]


def test_start_checks_frontend_preconditions_before_backend(tmp_path: Path) -> None:
    _write_profile_config(tmp_path)
    calls: list[str] = []

    def check_frontend(root: Path, profile: str, **kwargs) -> None:
        calls.append(f"check-frontend:{profile}:{kwargs['host']}:{kwargs['port']}")
        raise servctl.ServctlError("frontend port is already in use")

    def start_backend(root: Path, profile: str, **kwargs) -> None:
        calls.append(f"backend:{profile}")

    with pytest.raises(servctl.ServctlError, match="frontend port is already in use"):
        servctl.start(
            tmp_path,
            "cloud",
            frontend_host="127.0.0.1",
            frontend_port=1420,
            check_frontend_func=check_frontend,
            start_backend_func=start_backend,
            start_frontend_func=lambda root, profile, **kwargs: calls.append("frontend"),
        )

    assert calls == ["check-frontend:cloud:127.0.0.1:1420"]


def test_start_reports_backend_and_frontend_progress(tmp_path: Path) -> None:
    _write_profile_config(tmp_path)
    _write_frontend_dist(tmp_path)
    progress: list[str] = []
    backend_port = _unused_tcp_port()
    frontend_port = _unused_tcp_port()

    servctl.start_server(
        tmp_path,
        "cloud",
        host="127.0.0.1",
        port=backend_port,
        reload=False,
        preflight=lambda root, profile, port, host: None,
        spawn=lambda config: 12345,
        wait_health=lambda host, port, timeout_seconds: None,
        is_process_running=lambda pid: False,
        progress=progress.append,
    )
    servctl.start_frontend(
        tmp_path,
        "cloud",
        host="127.0.0.1",
        port=frontend_port,
        spawn=lambda config: 24680,
        wait_ready=lambda host, port, timeout_seconds: None,
        is_process_running=lambda pid: False,
        progress=progress.append,
    )

    assert progress == [
        "preparing backend log: yts-server-cloud.log",
        f"checking backend dependencies: http://127.0.0.1:{backend_port}",
        f"starting backend listener: http://127.0.0.1:{backend_port}",
        f"backend ready: http://127.0.0.1:{backend_port}",
        "preparing frontend log: yts-frontend-cloud.log",
        f"checking frontend build: {tmp_path / 'desktop' / 'frontend' / 'dist' / 'index.html'}",
        f"starting frontend listener: http://127.0.0.1:{frontend_port}",
        f"frontend ready: http://127.0.0.1:{frontend_port}",
    ]


def test_start_stops_backend_when_frontend_start_fails(tmp_path: Path) -> None:
    _write_profile_config(tmp_path)
    _write_frontend_dist(tmp_path)
    calls: list[str] = []

    def fail_frontend(root: Path, profile: str, **kwargs) -> None:
        calls.append(f"frontend:{profile}")
        raise servctl.ServctlError("frontend failed")

    with pytest.raises(servctl.ServctlError, match="frontend failed"):
        servctl.start(
            tmp_path,
            "cloud",
            start_backend_func=lambda root, profile, **kwargs: calls.append(f"backend:{profile}"),
            start_frontend_func=fail_frontend,
            check_frontend_func=lambda root, profile, **kwargs: None,
            stop_backend_func=lambda root, profile, **kwargs: calls.append(
                f"stop-backend:{profile}:{kwargs['host']}:{kwargs['port']}"
            ),
        )

    assert calls == ["backend:cloud", "frontend:cloud", "stop-backend:cloud:127.0.0.1:8000"]


def test_start_frontend_requires_built_frontend_dist(tmp_path: Path) -> None:
    _write_profile_config(tmp_path)

    with pytest.raises(servctl.ServctlError, match="missing frontend build"):
        servctl.start_frontend(
            tmp_path,
            "cloud",
            spawn=lambda config: 12345,
            wait_ready=lambda host, port, timeout_seconds: None,
            is_process_running=lambda pid: False,
        )


def test_spawn_frontend_process_runs_vite_preview(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = servctl.FrontendProcessConfig(
        root=tmp_path,
        profile="cloud",
        host="127.0.0.1",
        port=1420,
        env={"PATH": "/bin"},
        frontend_dir=tmp_path / "desktop" / "frontend",
        pid_path=tmp_path / "run" / "yts-frontend-cloud.pid",
        log_path=tmp_path / "run" / "yts-frontend-cloud.log",
    )
    captured: dict[str, object] = {}

    class FakePopen:
        pid = 24680

        def __init__(self, command: list[str], **kwargs) -> None:
            captured["command"] = command
            captured["kwargs"] = kwargs

    monkeypatch.setattr(servctl.subprocess, "Popen", FakePopen)

    pid = servctl.spawn_frontend_process(config)

    assert pid == 24680
    assert captured["command"] == [
        "npm",
        "run",
        "preview",
        "--",
        "--host",
        "127.0.0.1",
        "--port",
        "1420",
        "--strictPort",
    ]
    assert captured["kwargs"]["cwd"] == config.frontend_dir
    assert captured["kwargs"]["env"] == config.env
    assert captured["kwargs"]["stdin"] == subprocess.DEVNULL


def test_spawn_server_process_detaches_stdin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = servctl.ServerProcessConfig(
        root=tmp_path,
        profile="cloud",
        host="127.0.0.1",
        port=8000,
        reload=False,
        env={"PATH": "/bin"},
        pid_path=tmp_path / "run" / "yts-server-cloud.pid",
        log_path=tmp_path / "run" / "yts-server-cloud.log",
    )
    captured: dict[str, object] = {}

    class FakePopen:
        pid = 12345

        def __init__(self, command: list[str], **kwargs) -> None:
            captured["command"] = command
            captured["kwargs"] = kwargs

    monkeypatch.setattr(servctl.subprocess, "Popen", FakePopen)

    pid = servctl.spawn_server_process(config)

    assert pid == 12345
    assert captured["command"] == [
        "uv",
        "run",
        "uvicorn",
        "yts_server.main:app",
        "--host",
        "127.0.0.1",
        "--port",
        "8000",
    ]
    assert captured["kwargs"]["cwd"] == config.root
    assert captured["kwargs"]["env"] == config.env
    assert captured["kwargs"]["stdin"] == subprocess.DEVNULL


def test_start_fails_when_preflight_fails_and_does_not_spawn(tmp_path: Path) -> None:
    _write_profile_config(tmp_path)

    def preflight(root: Path, profile: str, port: int, host: str) -> None:
        raise servctl.ServctlError("db check failed")

    def spawn(config: servctl.ServerProcessConfig) -> int:
        raise AssertionError("spawn must not run when preflight fails")

    with pytest.raises(servctl.ServctlError, match="db check failed"):
        servctl.start_server(
            tmp_path,
            "cloud",
            preflight=preflight,
            spawn=spawn,
            wait_health=lambda host, port, timeout_seconds: None,
            is_process_running=lambda pid: False,
        )


def test_start_rejects_removed_config_env_before_subprocess(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_profile_config(tmp_path)
    monkeypatch.setenv("YTS_CONFIG_FILE", "/tmp/old.env")

    with pytest.raises(servctl.ServctlError, match="YTS_CONFIG_FILE is no longer supported"):
        servctl.start_server(
            tmp_path,
            "cloud",
            preflight=lambda root, profile, port, host: None,
            spawn=lambda config: 12345,
            wait_health=lambda host, port, timeout_seconds: None,
            is_process_running=lambda pid: False,
        )


def test_start_cleans_up_spawned_process_when_health_check_fails(tmp_path: Path) -> None:
    _write_profile_config(tmp_path)
    terminated: list[int] = []

    def wait_health(host: str, port: int, timeout_seconds: float) -> None:
        raise servctl.ServctlError("health failed")

    with pytest.raises(servctl.ServctlError, match="health failed"):
        servctl.start_server(
            tmp_path,
            "cloud",
            preflight=lambda root, profile, port, host: None,
            spawn=lambda config: 12345,
            wait_health=wait_health,
            is_process_running=lambda pid: False,
            terminate_process=lambda pid: terminated.append(pid),
        )

    assert terminated == [12345]
    assert not (tmp_path / "run" / "yts-server-cloud.pid").exists()


def test_stop_removes_stale_pid_file_when_process_is_missing(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "yts-server-cloud.pid").write_text("12345\n", encoding="utf-8")

    servctl.stop_server(
        tmp_path,
        "cloud",
        is_process_running_func=lambda pid: False,
        wait_port_release_func=lambda host, port, timeout_seconds, process_name: None,
    )

    assert not (run_dir / "yts-server-cloud.pid").exists()


def test_run_preflight_checks_rejects_busy_backend_port_before_python_probe(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_profile_config(tmp_path)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        sock.listen()
        port = sock.getsockname()[1]

        monkeypatch.setattr(
            servctl,
            "_run_python_probe",
            lambda root, env, code: pytest.fail("python probe must not run for a busy port"),
        )

        with pytest.raises(
            servctl.ServctlError,
            match=f"backend port is already in use: 127.0.0.1:{port}",
        ):
            servctl.run_preflight_checks(tmp_path, "cloud", port, "127.0.0.1")


def test_start_frontend_rejects_busy_preview_port_before_spawn(tmp_path: Path) -> None:
    _write_profile_config(tmp_path)
    _write_frontend_dist(tmp_path)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        sock.listen()
        port = sock.getsockname()[1]

        with pytest.raises(
            servctl.ServctlError,
            match=f"frontend port is already in use: 127.0.0.1:{port}",
        ):
            servctl.start_frontend(
                tmp_path,
                "cloud",
                port=port,
                spawn=lambda config: pytest.fail("frontend spawn must not run for a busy port"),
                wait_ready=lambda host, port, timeout_seconds: None,
                is_process_running=lambda pid: False,
            )


def test_stop_attempts_backend_even_when_frontend_stop_fails(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "yts-frontend-cloud.pid").write_text("222\n", encoding="utf-8")
    calls: list[str] = []

    def fail_frontend(root: Path, profile: str, **kwargs) -> None:
        calls.append(f"frontend:{profile}")
        raise servctl.ServctlError("pid file exists but process is not running: 222")

    def stop_backend(root: Path, profile: str, **kwargs) -> None:
        calls.append(f"backend:{profile}")

    with pytest.raises(servctl.ServctlError, match="frontend: pid file exists"):
        servctl.stop(
            tmp_path,
            "cloud",
            stop_frontend_func=fail_frontend,
            stop_backend_func=stop_backend,
        )

    assert calls == ["frontend:cloud", "backend:cloud"]


def test_stop_reports_frontend_then_backend_progress(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "yts-frontend-cloud.pid").write_text("222\n", encoding="utf-8")
    calls: list[str] = []
    progress: list[str] = []

    servctl.stop(
        tmp_path,
        "cloud",
        stop_frontend_func=lambda root, profile, **kwargs: calls.append(f"frontend:{profile}"),
        stop_backend_func=lambda root, profile, **kwargs: calls.append(f"backend:{profile}"),
        progress=progress.append,
    )

    assert calls == ["frontend:cloud", "backend:cloud"]
    assert progress == [
        "stopping frontend",
        "frontend stopped",
        "stopping backend",
        "backend stopped",
    ]


def test_stop_server_terminates_recorded_process_group(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "yts-server-cloud.pid").write_text("12345\n", encoding="utf-8")
    calls: list[str] = []

    def is_running(pid: int) -> bool:
        calls.append(f"check:{pid}")
        return calls.count(f"check:{pid}") == 1

    servctl.stop_server(
        tmp_path,
        "cloud",
        timeout_seconds=0.1,
        is_process_running_func=is_running,
        wait_port_release_func=lambda host, port, timeout_seconds, process_name: None,
    )

    assert not (run_dir / "yts-server-cloud.pid").exists()


def test_stop_server_waits_for_backend_port_release_after_pid_stops(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "yts-server-cloud.pid").write_text("12345\n", encoding="utf-8")
    calls: list[str] = []

    def is_running(pid: int) -> bool:
        calls.append(f"check:{pid}")
        return calls.count(f"check:{pid}") == 1

    monkeypatch.setattr(servctl, "_terminate_process", lambda pid: calls.append(f"term:{pid}"))

    servctl.stop_server(
        tmp_path,
        "cloud",
        host="127.0.0.1",
        port=9000,
        timeout_seconds=0.1,
        is_process_running_func=is_running,
        wait_port_release_func=lambda host, port, timeout_seconds, process_name: calls.append(
            f"wait:{process_name}:{host}:{port}:{timeout_seconds}"
        ),
    )

    assert calls == [
        "check:12345",
        "term:12345",
        "check:12345",
        "wait:backend:127.0.0.1:9000:0.1",
    ]
    assert not (run_dir / "yts-server-cloud.pid").exists()


def test_terminate_process_sends_sigterm_to_process_group(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    signals: list[tuple[int, signal.Signals]] = []

    monkeypatch.setattr(servctl.os, "getpgid", lambda pid: 67890)
    monkeypatch.setattr(servctl.os, "killpg", lambda pgid, sig: signals.append((pgid, sig)))

    servctl._terminate_process(12345)

    assert signals == [(67890, signal.SIGTERM)]


def test_process_exists_reaps_exited_direct_child(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(servctl.os, "waitpid", lambda pid, flags: (pid, 0))
    monkeypatch.setattr(
        servctl.os,
        "kill",
        lambda pid, signal_number: pytest.fail("exited child must not be probed with kill"),
    )

    assert not servctl._process_exists(12345)


def test_stop_stops_running_backend_when_frontend_was_never_started(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "yts-server-cloud.pid").write_text("12345\n", encoding="utf-8")
    calls: list[str] = []

    servctl.stop(
        tmp_path,
        "cloud",
        stop_backend_func=lambda root, profile, **kwargs: calls.append(f"backend:{profile}"),
        stop_frontend_func=lambda root, profile, **kwargs: calls.append(f"frontend:{profile}"),
    )

    assert calls == ["backend:cloud"]


def test_status_reports_backend_and_frontend(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "yts-server-cloud.pid").write_text("111\n", encoding="utf-8")
    (run_dir / "yts-frontend-cloud.pid").write_text("222\n", encoding="utf-8")

    output = servctl.status(
        tmp_path,
        "cloud",
        is_process_running_func=lambda pid: pid == 111,
        is_port_in_use_func=lambda host, port, process_name: False,
    )

    assert output.splitlines() == [
        "backend: running: profile=cloud pid=111",
        f"frontend: stale pid: profile=cloud pid=222 pid_file={run_dir / 'yts-frontend-cloud.pid'}",
    ]


def test_status_reports_unmanaged_frontend_port_when_pid_is_missing(tmp_path: Path) -> None:
    backend_port = _unused_tcp_port()
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as frontend_sock:
        frontend_sock.bind(("127.0.0.1", 0))
        frontend_sock.listen()
        frontend_port = frontend_sock.getsockname()[1]

        output = servctl.status(
            tmp_path,
            "cloud",
            port=backend_port,
            frontend_port=frontend_port,
        )

    assert output.splitlines() == [
        f"backend: stopped: profile=cloud pid_file={tmp_path / 'run' / 'yts-server-cloud.pid'}",
        "frontend: unmanaged port in use: "
        f"profile=cloud port=127.0.0.1:{frontend_port} "
        f"pid_file={tmp_path / 'run' / 'yts-frontend-cloud.pid'}",
    ]


def test_restart_runs_deploy_then_stop_then_start(tmp_path: Path) -> None:
    calls: list[str] = []

    servctl.restart(
        tmp_path,
        "cloud",
        deploy_func=lambda root, profile: calls.append(f"deploy:{profile}"),
        stop_func=lambda root, profile, **kwargs: calls.append(
            "stop:"
            f"{profile}:{kwargs['host']}:{kwargs['port']}:"
            f"{kwargs['frontend_host']}:{kwargs['frontend_port']}"
        ),
        start_func=lambda root, profile, **kwargs: calls.append(
            f"start:{profile}:{kwargs['host']}:{kwargs['port']}:{kwargs['reload']}"
        ),
        host="127.0.0.1",
        port=9000,
        reload=True,
    )

    assert calls == [
        "deploy:cloud",
        "stop:cloud:127.0.0.1:9000:127.0.0.1:1420",
        "start:cloud:127.0.0.1:9000:True",
    ]


def test_restart_stops_when_deploy_fails(tmp_path: Path) -> None:
    calls: list[str] = []

    def fail_deploy(root: Path, profile: str) -> None:
        calls.append(f"deploy:{profile}")
        raise servctl.ServctlError("deploy failed")

    with pytest.raises(servctl.ServctlError, match="deploy failed"):
        servctl.restart(
            tmp_path,
            "cloud",
            deploy_func=fail_deploy,
            stop_func=lambda root, profile: calls.append(f"stop:{profile}"),
            start_func=lambda root, profile, **kwargs: calls.append("start"),
        )

    assert calls == ["deploy:cloud"]


def test_cli_uses_short_servctl_commands(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls: list[str] = []

    monkeypatch.setattr(
        servctl, "Path", lambda value: tmp_path if value == servctl.__file__ else Path(value)
    )
    monkeypatch.setattr(servctl, "deploy", lambda root, profile: calls.append(f"deploy:{profile}"))
    monkeypatch.setattr(
        servctl,
        "start",
        lambda root, profile, **kwargs: calls.append(
            "start:"
            f"{profile}:{kwargs['host']}:{kwargs['port']}:{kwargs['reload']}:"
            f"{kwargs['frontend_host']}:{kwargs['frontend_port']}"
        ),
    )
    monkeypatch.setattr(
        servctl, "stop", lambda root, profile, **kwargs: calls.append(f"stop:{profile}")
    )
    monkeypatch.setattr(servctl, "install", lambda root: calls.append("install"))
    monkeypatch.setattr(
        servctl,
        "restart",
        lambda root, profile, **kwargs: calls.append(
            f"restart:{profile}:{kwargs['host']}:{kwargs['port']}:{kwargs['reload']}"
        ),
    )
    monkeypatch.setattr(servctl, "status", lambda root, profile, **kwargs: f"running:{profile}")

    assert servctl.main(["install"]) == 0
    assert servctl.main(["deploy", "--profile", "cloud"]) == 0
    assert servctl.main(["start", "--profile", "cloud", "--port", "9000", "--reload"]) == 0
    assert servctl.main(["stop", "--profile", "cloud"]) == 0
    assert servctl.main(["restart", "--profile", "cloud", "--host", "0.0.0.0"]) == 0
    assert servctl.main(["status", "--profile", "cloud"]) == 0

    assert calls == [
        "install",
        "deploy:cloud",
        "start:cloud:127.0.0.1:9000:True:127.0.0.1:1420",
        "stop:cloud",
        "restart:cloud:0.0.0.0:8000:False",
    ]


def test_cli_start_prints_progress_to_console(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        servctl, "Path", lambda value: tmp_path if value == servctl.__file__ else Path(value)
    )

    def fake_start(root: Path, profile: str, **kwargs) -> None:
        kwargs["progress"]("checking backend dependencies: http://127.0.0.1:9000")
        kwargs["progress"]("backend ready: http://127.0.0.1:9000")
        kwargs["progress"]("frontend ready: http://127.0.0.1:1420")

    monkeypatch.setattr(servctl, "start", fake_start)

    assert servctl.main(["start", "--profile", "cloud", "--port", "9000"]) == 0

    output = capsys.readouterr().out.splitlines()
    assert output == [
        "servctl: starting profile=cloud",
        "servctl: checking backend dependencies: http://127.0.0.1:9000",
        "servctl: backend ready: http://127.0.0.1:9000",
        "servctl: frontend ready: http://127.0.0.1:1420",
        "servctl: started profile=cloud backend=http://127.0.0.1:9000 frontend=http://127.0.0.1:1420",
    ]


def test_cli_stop_prints_progress_to_console(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        servctl, "Path", lambda value: tmp_path if value == servctl.__file__ else Path(value)
    )

    def fake_stop(root: Path, profile: str, **kwargs) -> None:
        kwargs["progress"]("stopping frontend")
        kwargs["progress"]("frontend stopped")
        kwargs["progress"]("stopping backend")
        kwargs["progress"]("backend stopped")

    monkeypatch.setattr(servctl, "stop", fake_stop)

    assert servctl.main(["stop", "--profile", "cloud"]) == 0

    output = capsys.readouterr().out.splitlines()
    assert output == [
        "servctl: stopping profile=cloud",
        "servctl: stopping frontend",
        "servctl: frontend stopped",
        "servctl: stopping backend",
        "servctl: backend stopped",
        "servctl: stopped profile=cloud",
    ]
