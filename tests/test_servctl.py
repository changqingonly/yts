from __future__ import annotations

import importlib.util
import signal
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
                "YTS_INFERENCE_BACKEND=echo",
                "YTS_DATABASE_URL=sqlite+aiosqlite:///./test.db",
                "YTS_AUTH_JWT_SECRET=test-secret-that-is-long-enough-for-hs256",
            ]
        ),
        encoding="utf-8",
    )


def _write_frontend_dist(root: Path) -> None:
    dist_dir = root / "desktop" / "frontend" / "dist"
    dist_dir.mkdir(parents=True)
    (dist_dir / "index.html").write_text("<div id=\"app\"></div>", encoding="utf-8")


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
    )

    assert calls == [
        "backend:cloud:127.0.0.1:8000:False",
        "frontend:cloud:127.0.0.1:1420",
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
            start_backend_func=lambda root, profile, **kwargs: calls.append(
                f"backend:{profile}"
            ),
            start_frontend_func=fail_frontend,
            stop_backend_func=lambda root, profile: calls.append(f"stop-backend:{profile}"),
        )

    assert calls == ["backend:cloud", "frontend:cloud", "stop-backend:cloud"]


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


def test_stop_fails_and_removes_stale_pid_file_when_process_is_missing(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "yts-server-cloud.pid").write_text("12345\n", encoding="utf-8")

    with pytest.raises(servctl.ServctlError, match="process is not running"):
        servctl.stop_server(
            tmp_path,
            "cloud",
            is_process_running_func=lambda pid: False,
        )

    assert not (run_dir / "yts-server-cloud.pid").exists()


def test_stop_attempts_backend_even_when_frontend_stop_fails(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "yts-frontend-cloud.pid").write_text("222\n", encoding="utf-8")
    calls: list[str] = []

    def fail_frontend(root: Path, profile: str) -> None:
        calls.append(f"frontend:{profile}")
        raise servctl.ServctlError("pid file exists but process is not running: 222")

    def stop_backend(root: Path, profile: str) -> None:
        calls.append(f"backend:{profile}")

    with pytest.raises(servctl.ServctlError, match="frontend: pid file exists"):
        servctl.stop(
            tmp_path,
            "cloud",
            stop_frontend_func=fail_frontend,
            stop_backend_func=stop_backend,
        )

    assert calls == ["frontend:cloud", "backend:cloud"]


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
    )

    assert not (run_dir / "yts-server-cloud.pid").exists()


def test_terminate_process_sends_sigterm_to_process_group(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    signals: list[tuple[int, signal.Signals]] = []

    monkeypatch.setattr(servctl.os, "getpgid", lambda pid: 67890)
    monkeypatch.setattr(servctl.os, "killpg", lambda pgid, sig: signals.append((pgid, sig)))

    servctl._terminate_process(12345)

    assert signals == [(67890, signal.SIGTERM)]


def test_stop_stops_running_backend_when_frontend_was_never_started(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "yts-server-cloud.pid").write_text("12345\n", encoding="utf-8")
    calls: list[str] = []

    servctl.stop(
        tmp_path,
        "cloud",
        stop_backend_func=lambda root, profile: calls.append(f"backend:{profile}"),
        stop_frontend_func=lambda root, profile: calls.append(f"frontend:{profile}"),
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
    )

    assert output.splitlines() == [
        "backend: running: profile=cloud pid=111",
        f"frontend: stale pid: profile=cloud pid=222 pid_file={run_dir / 'yts-frontend-cloud.pid'}",
    ]


def test_restart_runs_deploy_then_stop_then_start(tmp_path: Path) -> None:
    calls: list[str] = []

    servctl.restart(
        tmp_path,
        "cloud",
        deploy_func=lambda root, profile: calls.append(f"deploy:{profile}"),
        stop_func=lambda root, profile: calls.append(f"stop:{profile}"),
        start_func=lambda root, profile, **kwargs: calls.append(
            f"start:{profile}:{kwargs['host']}:{kwargs['port']}:{kwargs['reload']}"
        ),
        host="127.0.0.1",
        port=9000,
        reload=True,
    )

    assert calls == [
        "deploy:cloud",
        "stop:cloud",
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
        servctl, "stop", lambda root, profile: calls.append(f"stop:{profile}")
    )
    monkeypatch.setattr(servctl, "install", lambda root: calls.append("install"))
    monkeypatch.setattr(
        servctl,
        "restart",
        lambda root, profile, **kwargs: calls.append(
            f"restart:{profile}:{kwargs['host']}:{kwargs['port']}:{kwargs['reload']}"
        ),
    )
    monkeypatch.setattr(servctl, "status", lambda root, profile: f"running:{profile}")

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
