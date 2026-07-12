from __future__ import annotations

import hashlib
import importlib
import os
import subprocess
import urllib.error
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

servctl = importlib.import_module("scripts.servctl")
component_commands = importlib.import_module("scripts.servctl.component_commands")

ComponentResult = component_commands.ComponentResult
install_components = component_commands.install_components
status_components = component_commands.status_components
verify_components = component_commands.verify_components

SOURCE_URL = "https://example.test/llama.git"
MODEL_URL = "https://example.test/llama.gguf"
MODEL_BYTES = b"verified model bytes"
MODEL_SHA256 = hashlib.sha256(MODEL_BYTES).hexdigest()


@dataclass(frozen=True)
class ManifestComponent:
    name: str = "llama"
    enabled: bool = True
    platforms: tuple[str, ...] = ("darwin-arm64",)
    dependencies: tuple[str, ...] = ()
    source_kind: str = "external"
    source_url: str = SOURCE_URL
    commit: str = "a" * 40
    submodules: bool = False
    source_dir: str = "llama-src"
    artifact: str = "llama-src/build/llama-server"
    model_bytes: bytes | None = MODEL_BYTES
    model_size: int | None = None
    model_sha256: str | None = None
    runtime_kind: str = "service"
    port: int = 8080


@pytest.fixture(autouse=True)
def _supported_platform(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(component_commands, "current_platform", lambda: "darwin-arm64")


def _toml_string(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _render_component(component: ManifestComponent) -> str:
    name = component.name
    platforms = ", ".join(_toml_string(value) for value in component.platforms)
    dependencies = ", ".join(_toml_string(value) for value in component.dependencies)
    lines = [
        f"[components.{name}]",
        f"enabled = {'true' if component.enabled else 'false'}",
        f"platforms = [{platforms}]",
        f"dependencies = [{dependencies}]",
    ]
    if component.model_bytes is None:
        lines.append("models = []")

    lines.extend(
        [
            "",
            f"[components.{name}.source]",
            f"kind = {_toml_string(component.source_kind)}",
            f"source_dir = {_toml_string(component.source_dir)}",
        ]
    )
    if component.source_kind == "external":
        lines.extend(
            [
                f"url = {_toml_string(component.source_url)}",
                f"commit = {_toml_string(component.commit)}",
                f"submodules = {'true' if component.submodules else 'false'}",
            ]
        )

    build_dir = str(Path(component.artifact).parent)
    lines.extend(
        [
            "",
            f"[components.{name}.build]",
            f"target = {_toml_string(Path(component.artifact).name)}",
            'configure_argv = ["cmake", "-S", "{source}", "-B", "{build}"]',
            'build_argv = ["cmake", "--build", "{build}", "--target", '
            f"{_toml_string(Path(component.artifact).name)}]",
            f"build_dir = {_toml_string(build_dir)}",
            f"artifact = {_toml_string(component.artifact)}",
        ]
    )

    if component.model_bytes is not None:
        model_size = (
            len(component.model_bytes) if component.model_size is None else component.model_size
        )
        model_sha256 = component.model_sha256 or hashlib.sha256(component.model_bytes).hexdigest()
        lines.extend(
            [
                "",
                f"[[components.{name}.models]]",
                'id = "model"',
                f"url = {_toml_string(MODEL_URL.replace('llama', name))}",
                f"size = {model_size}",
                f"sha256 = {_toml_string(model_sha256)}",
                f"path = {_toml_string(f'models/{name}.gguf')}",
            ]
        )

    lines.extend(["", f"[components.{name}.runtime]"])
    if component.runtime_kind == "service":
        runtime_argv = ['"{artifact}"']
        if component.model_bytes is not None:
            runtime_argv.extend(['"--model"', '"{model:model}"'])
        lines.extend(
            [
                'kind = "service"',
                f"argv = [{', '.join(runtime_argv)}]",
                'host = "127.0.0.1"',
                f"port = {component.port}",
                "startup_timeout_seconds = 10",
                "shutdown_timeout_seconds = 5",
                "",
                f"[components.{name}.runtime.health]",
                'path = "/health"',
                "timeout_seconds = 2",
                "",
                f"[components.{name}.runtime.readiness]",
                'path = "/ready"',
                "timeout_seconds = 2",
            ]
        )
    else:
        runtime_argv = ['"{artifact}"', '"--prompt"', '"{prompt}"', '"--out"', '"{out}"']
        lines.extend(
            [
                'kind = "command"',
                f"argv = [{', '.join(runtime_argv)}]",
                "execution_timeout_seconds = 30",
            ]
        )
    return "\n".join(lines)


def _write_manifest(root: Path, *components: ManifestComponent) -> Path:
    manifest_path = root / "desktop" / "components.toml"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    source = ["schema_version = 1", 'vendor_dir = "desktop/vendor"', ""]
    source.extend(_render_component(component) for component in components)
    manifest_path.write_text("\n\n".join(source) + "\n", encoding="utf-8")
    return manifest_path


def _git(cwd: Path, *arguments: str) -> str:
    return subprocess.check_output(
        ["git", *arguments],
        cwd=cwd,
        text=True,
        stderr=subprocess.STDOUT,
    ).strip()


def _create_source(root: Path, component: ManifestComponent, *, remote: str | None = None) -> str:
    source_dir = root / "desktop" / "vendor" / component.source_dir
    source_dir.mkdir(parents=True)
    _git(source_dir, "init", "--quiet")
    _git(source_dir, "config", "user.email", "servctl@example.test")
    _git(source_dir, "config", "user.name", "servctl tests")
    (source_dir / "source.txt").write_text("source\n", encoding="utf-8")
    (source_dir / ".gitignore").write_text("build/\n", encoding="utf-8")
    _git(source_dir, "add", "source.txt", ".gitignore")
    _git(source_dir, "commit", "--quiet", "-m", "source")
    _git(source_dir, "remote", "add", "origin", remote or component.source_url)
    return _git(source_dir, "rev-parse", "HEAD")


def _write_artifact(root: Path, component: ManifestComponent, *, executable: bool = True) -> Path:
    base = root if component.source_kind == "workspace" else root / "desktop" / "vendor"
    artifact = base / component.artifact
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    artifact.chmod(0o755 if executable else 0o644)
    return artifact


def _write_model(root: Path, component: ManifestComponent, content: bytes | None = None) -> Path:
    assert component.model_bytes is not None
    model = root / "desktop" / "vendor" / "models" / f"{component.name}.gguf"
    model.parent.mkdir(parents=True, exist_ok=True)
    model.write_bytes(component.model_bytes if content is None else content)
    return model


def _ready_external_component(root: Path, component: ManifestComponent | None = None):
    draft = component or ManifestComponent()
    commit = _create_source(root, draft)
    configured = ManifestComponent(**{**draft.__dict__, "commit": commit})
    _write_manifest(root, configured)
    _write_artifact(root, configured)
    if configured.model_bytes is not None:
        _write_model(root, configured)
    return configured


def test_verify_fails_when_manifest_is_missing(tmp_path: Path) -> None:
    with pytest.raises(servctl.ServctlError, match="missing component manifest"):
        verify_components(tmp_path)


def test_verify_ready_component_with_injected_hash_file(tmp_path: Path) -> None:
    component = _ready_external_component(tmp_path)
    hashed: list[Path] = []

    def fake_hash(path: Path) -> str:
        hashed.append(path)
        return hashlib.sha256(path.read_bytes()).hexdigest()

    result = verify_components(tmp_path, names=["llama"], hash_file=fake_hash)

    assert result == [
        ComponentResult(name="llama", enabled=True, state="ready", detail="assets verified")
    ]
    assert hashed == [tmp_path / "desktop" / "vendor" / "models" / "llama.gguf"]
    assert component.commit != "a" * 40


@pytest.mark.parametrize(
    ("change", "detail"),
    [
        ("remote", "source remote mismatch"),
        ("commit", "source commit mismatch"),
        ("dirty", "source tree is dirty"),
    ],
)
def test_verify_rejects_wrong_or_dirty_source(
    tmp_path: Path,
    change: str,
    detail: str,
) -> None:
    component = ManifestComponent()
    actual_commit = _create_source(
        tmp_path,
        component,
        remote="https://example.test/wrong.git" if change == "remote" else None,
    )
    expected_commit = "f" * 40 if change == "commit" else actual_commit
    configured = ManifestComponent(commit=expected_commit)
    _write_manifest(tmp_path, configured)
    _write_artifact(tmp_path, configured)
    _write_model(tmp_path, configured)
    if change == "dirty":
        source_dir = tmp_path / "desktop" / "vendor" / configured.source_dir
        (source_dir / "uncommitted.txt").write_text("dirty\n", encoding="utf-8")

    result = verify_components(tmp_path, names=["llama"])

    assert result[0].state == "invalid"
    assert detail in result[0].detail


def test_verify_does_not_expose_observed_remote_credentials(tmp_path: Path) -> None:
    component = ManifestComponent()
    secret = "remote-secret-marker"
    observed_remote = f"https://user:{secret}@example.test/wrong.git"
    commit = _create_source(tmp_path, component, remote=observed_remote)
    configured = ManifestComponent(commit=commit)
    _write_manifest(tmp_path, configured)

    result = verify_components(tmp_path, names=["llama"])

    assert result[0].state == "invalid"
    assert SOURCE_URL in result[0].detail
    assert observed_remote not in result[0].detail
    assert secret not in result[0].detail


def test_verify_rejects_uninitialized_recursive_submodule(tmp_path: Path) -> None:
    submodule = tmp_path / "submodule-seed"
    submodule.mkdir()
    _git(submodule, "init", "--quiet")
    _git(submodule, "config", "user.email", "servctl@example.test")
    _git(submodule, "config", "user.name", "servctl tests")
    (submodule / "dependency.txt").write_text("dependency\n", encoding="utf-8")
    _git(submodule, "add", "dependency.txt")
    _git(submodule, "commit", "--quiet", "-m", "dependency")

    parent = tmp_path / "parent-seed"
    parent.mkdir()
    _git(parent, "init", "--quiet")
    _git(parent, "config", "user.email", "servctl@example.test")
    _git(parent, "config", "user.name", "servctl tests")
    (parent / ".gitignore").write_text("build/\n", encoding="utf-8")
    _git(parent, "add", ".gitignore")
    _git(parent, "commit", "--quiet", "-m", "parent")
    _git(
        parent,
        "-c",
        "protocol.file.allow=always",
        "submodule",
        "add",
        str(submodule),
        "deps/submodule",
    )
    _git(parent, "commit", "--quiet", "-am", "add submodule")
    commit = _git(parent, "rev-parse", "HEAD")

    component = ManifestComponent(commit=commit, submodules=True)
    source_dir = tmp_path / "desktop" / "vendor" / component.source_dir
    source_dir.parent.mkdir(parents=True)
    subprocess.check_call(["git", "clone", "--quiet", str(parent), str(source_dir)])
    _git(source_dir, "remote", "set-url", "origin", component.source_url)
    _write_manifest(tmp_path, component)
    _write_artifact(tmp_path, component)
    _write_model(tmp_path, component)

    result = verify_components(tmp_path, names=["llama"])

    assert result[0].state == "invalid"
    assert "submodule is not initialized" in result[0].detail


@pytest.mark.parametrize(
    ("artifact_mode", "expected_state", "detail"),
    [
        ("missing", "missing", "artifact is missing"),
        ("not-executable", "invalid", "artifact is not executable"),
    ],
)
def test_verify_rejects_missing_or_non_executable_artifact(
    tmp_path: Path,
    artifact_mode: str,
    expected_state: str,
    detail: str,
) -> None:
    component = ManifestComponent()
    commit = _create_source(tmp_path, component)
    configured = ManifestComponent(commit=commit)
    _write_manifest(tmp_path, configured)
    _write_model(tmp_path, configured)
    if artifact_mode == "not-executable":
        _write_artifact(tmp_path, configured, executable=False)

    result = verify_components(tmp_path, names=["llama"])

    assert result[0].state == expected_state
    assert detail in result[0].detail


@pytest.mark.parametrize(
    ("content", "fake_hash", "detail"),
    [
        (b"short", None, "model size mismatch"),
        (MODEL_BYTES, "0" * 64, "model SHA256 mismatch"),
    ],
)
def test_verify_rejects_model_size_and_hash_mismatches(
    tmp_path: Path,
    content: bytes,
    fake_hash: str | None,
    detail: str,
) -> None:
    component = ManifestComponent()
    commit = _create_source(tmp_path, component)
    configured = ManifestComponent(commit=commit)
    _write_manifest(tmp_path, configured)
    _write_artifact(tmp_path, configured)
    _write_model(tmp_path, configured, content)

    hash_file = component_commands._sha256_file if fake_hash is None else lambda path: fake_hash
    result = verify_components(tmp_path, names=["llama"], hash_file=hash_file)

    assert result[0].state == "invalid"
    assert detail in result[0].detail


def test_component_operations_reject_unsupported_current_platform(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_manifest(tmp_path, ManifestComponent())
    monkeypatch.setattr(component_commands, "current_platform", lambda: "linux-x86_64")

    with pytest.raises(servctl.ServctlError, match=r"llama.*linux-x86_64.*not supported"):
        verify_components(tmp_path, names=["llama"])


def test_component_operations_reject_unknown_name(tmp_path: Path) -> None:
    _write_manifest(tmp_path, ManifestComponent())

    with pytest.raises(servctl.ServctlError, match="unknown component missing"):
        verify_components(tmp_path, names=["missing"])


def test_component_operations_reject_bare_string_names(tmp_path: Path) -> None:
    _write_manifest(tmp_path, ManifestComponent())

    with pytest.raises(servctl.ServctlError, match="component names must be a sequence"):
        verify_components(tmp_path, names="llama")


def test_component_operations_reject_enabled_dependency_on_disabled_component(
    tmp_path: Path,
) -> None:
    disabled = ManifestComponent(name="disabled", enabled=False, source_dir="disabled-src")
    enabled = ManifestComponent(
        name="enabled",
        dependencies=("disabled",),
        source_dir="enabled-src",
        artifact="enabled-src/build/enabled",
    )
    _write_manifest(tmp_path, disabled, enabled)

    with pytest.raises(
        servctl.ServctlError,
        match=r"enabled component enabled depends on disabled component disabled",
    ):
        verify_components(tmp_path)


def test_default_verify_selection_uses_enabled_dependency_order(tmp_path: Path) -> None:
    final = ManifestComponent(
        name="final",
        dependencies=("alpha", "beta"),
        source_dir="final-src",
        artifact="final-src/build/final",
        model_bytes=None,
        runtime_kind="command",
    )
    beta = ManifestComponent(
        name="beta",
        source_dir="beta-src",
        artifact="beta-src/build/beta",
        model_bytes=None,
        runtime_kind="command",
    )
    disabled = ManifestComponent(
        name="disabled",
        enabled=False,
        source_dir="disabled-src",
        artifact="disabled-src/build/disabled",
        model_bytes=None,
    )
    alpha = ManifestComponent(
        name="alpha",
        source_dir="alpha-src",
        artifact="alpha-src/build/alpha",
        model_bytes=None,
        runtime_kind="command",
    )
    _write_manifest(tmp_path, final, beta, disabled, alpha)

    result = verify_components(tmp_path)

    assert [item.name for item in result] == ["alpha", "beta", "final"]
    assert all(item.state == "missing" for item in result)


def test_explicit_selection_preserves_order_and_reports_disabled(tmp_path: Path) -> None:
    enabled = ManifestComponent(model_bytes=None, runtime_kind="command")
    disabled = ManifestComponent(
        name="disabled",
        enabled=False,
        source_dir="disabled-src",
        artifact="disabled-src/build/disabled",
        model_bytes=None,
    )
    _write_manifest(tmp_path, enabled, disabled)

    result = verify_components(tmp_path, names=["disabled", "llama"])

    assert [(item.name, item.state) for item in result] == [
        ("disabled", "disabled"),
        ("llama", "missing"),
    ]


def test_install_clones_pinned_source_builds_and_atomically_installs_model(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed = tmp_path / "seed"
    seed.mkdir()
    _git(seed, "init", "--quiet")
    _git(seed, "config", "user.email", "servctl@example.test")
    _git(seed, "config", "user.name", "servctl tests")
    (seed / "source.txt").write_text("seed\n", encoding="utf-8")
    (seed / ".gitignore").write_text("build/\n", encoding="utf-8")
    _git(seed, "add", "source.txt", ".gitignore")
    _git(seed, "commit", "--quiet", "-m", "seed")
    commit = _git(seed, "rev-parse", "HEAD")
    component = ManifestComponent(commit=commit, submodules=True)
    _write_manifest(tmp_path, component)

    calls: list[tuple[list[str], Path]] = []
    source_dir = tmp_path / "desktop" / "vendor" / component.source_dir

    def run_command(command: list[str], *, cwd: Path) -> None:
        calls.append((command, cwd))
        if command[:2] == ["git", "clone"]:
            subprocess.check_call(
                ["git", "clone", "--quiet", str(seed), str(source_dir)],
                cwd=cwd,
            )
            _git(source_dir, "remote", "set-url", "origin", component.source_url)
        elif command[:2] == ["git", "checkout"]:
            subprocess.check_call(command, cwd=cwd)
        elif command[:3] == ["git", "submodule", "update"]:
            subprocess.check_call(command, cwd=cwd)
        elif command[0:2] == ["cmake", "--build"]:
            _write_artifact(tmp_path, component)

    downloads: list[tuple[str, Path]] = []

    def download(url: str, destination: Path) -> None:
        downloads.append((url, destination))
        assert destination.name == "llama.gguf.partial"
        assert not (destination.parent / "llama.gguf").exists()
        destination.write_bytes(MODEL_BYTES)

    replacements: list[tuple[Path, Path]] = []
    real_replace = os.replace

    def replace(source: Path, destination: Path) -> None:
        replacements.append((Path(source), Path(destination)))
        real_replace(source, destination)

    monkeypatch.setattr(component_commands.os, "replace", replace)

    result = install_components(
        tmp_path,
        names=["llama"],
        run_command=run_command,
        download=download,
    )

    build_dir = tmp_path / "desktop" / "vendor" / "llama-src" / "build"
    assert calls == [
        (["git", "clone", SOURCE_URL, str(source_dir)], source_dir.parent),
        (["git", "checkout", "--detach", commit], source_dir),
        (["git", "submodule", "update", "--init", "--recursive"], source_dir),
        (
            ["cmake", "-S", str(source_dir), "-B", str(build_dir)],
            tmp_path,
        ),
        (
            ["cmake", "--build", str(build_dir), "--target", "llama-server"],
            tmp_path,
        ),
    ]
    model = tmp_path / "desktop" / "vendor" / "models" / "llama.gguf"
    partial = model.with_name(f"{model.name}.partial")
    assert downloads == [(MODEL_URL, partial)]
    assert replacements == [(partial, model)]
    assert model.read_bytes() == MODEL_BYTES
    assert not partial.exists()
    assert result == [
        ComponentResult(name="llama", enabled=True, state="ready", detail="assets verified")
    ]


def test_install_rejects_dirty_source_before_checkout_or_build(tmp_path: Path) -> None:
    component = ManifestComponent()
    commit = _create_source(tmp_path, component)
    configured = ManifestComponent(commit=commit)
    _write_manifest(tmp_path, configured)
    source_dir = tmp_path / "desktop" / "vendor" / configured.source_dir
    (source_dir / "dirty.txt").write_text("dirty\n", encoding="utf-8")
    commands: list[list[str]] = []

    with pytest.raises(servctl.ServctlError, match="source tree is dirty"):
        install_components(
            tmp_path,
            names=["llama"],
            run_command=lambda command, **kwargs: commands.append(command),
            download=lambda url, destination: pytest.fail("dirty source must not download"),
        )

    assert commands == []


def test_install_rejects_wrong_remote_before_checkout_or_build(tmp_path: Path) -> None:
    component = ManifestComponent()
    commit = _create_source(tmp_path, component, remote="https://example.test/wrong.git")
    configured = ManifestComponent(commit=commit)
    _write_manifest(tmp_path, configured)
    commands: list[list[str]] = []

    with pytest.raises(servctl.ServctlError, match="source remote mismatch"):
        install_components(
            tmp_path,
            names=["llama"],
            run_command=lambda command, **kwargs: commands.append(command),
            download=lambda url, destination: pytest.fail("wrong remote must not download"),
        )

    assert commands == []


def test_verify_translates_missing_git_tool_to_servctl_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    component = ManifestComponent()
    commit = _create_source(tmp_path, component)
    _write_manifest(tmp_path, ManifestComponent(commit=commit))
    monkeypatch.setattr(
        component_commands.subprocess,
        "run",
        lambda *args, **kwargs: (_ for _ in ()).throw(FileNotFoundError("git is missing")),
    )

    with pytest.raises(servctl.ServctlError, match=r"Git inspection failed.*git is missing"):
        verify_components(tmp_path, names=["llama"])


def test_install_translates_missing_build_tool_to_servctl_error(tmp_path: Path) -> None:
    component = ManifestComponent(
        source_kind="workspace",
        source_dir="workspace/llama",
        artifact="workspace/llama/build/llama-tool",
        model_bytes=None,
        runtime_kind="command",
    )
    _write_manifest(tmp_path, component)
    (tmp_path / component.source_dir).mkdir(parents=True)

    with pytest.raises(
        servctl.ServctlError,
        match=r"component llama.*configure command failed.*cmake is missing",
    ):
        install_components(
            tmp_path,
            names=["llama"],
            run_command=lambda command, **kwargs: (_ for _ in ()).throw(
                FileNotFoundError("cmake is missing")
            ),
        )


def test_cli_component_command_failure_does_not_expose_manifest_url_query(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    secret = "manifest-query-secret-marker"
    source_url = f"{SOURCE_URL}?token={secret}"

    def install(root: Path, names: list[str] | None):
        raise subprocess.CalledProcessError(
            7,
            ["git", "clone", source_url, "/cache/llama-src"],
        )

    api = SimpleNamespace(
        __file__=str(tmp_path / "scripts" / "servctl" / "__init__.py"),
        Path=Path,
        install_components=install,
    )

    assert servctl.main(["components", "install", "llama"], api=api) == 7
    error = capsys.readouterr().err
    assert "command failed with exit code 7" in error
    assert "git clone" in error
    assert "/cache/llama-src" in error
    assert source_url not in error
    assert secret not in error


def test_default_clone_child_output_cannot_expose_manifest_url_query(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
) -> None:
    secret = "child-fd-secret-marker"
    source_url = f"{SOURCE_URL}?token={secret}"
    _write_manifest(tmp_path, ManifestComponent(source_url=source_url))

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake_git = bin_dir / "git"
    fake_git.write_text(
        '#!/bin/sh\necho "fake git stdout: $*"\necho "fake git stderr: $*" >&2\nexit 7\n',
        encoding="utf-8",
    )
    fake_git.chmod(0o755)
    monkeypatch.setenv("PATH", str(bin_dir))

    def install(root: Path, names: list[str] | None):
        return install_components(root, names)

    api = SimpleNamespace(
        __file__=str(tmp_path / "scripts" / "servctl" / "__init__.py"),
        Path=Path,
        install_components=install,
    )

    assert servctl.main(["components", "install", "llama"], api=api) == 7
    captured = capfd.readouterr()
    combined = f"{captured.out}\n{captured.err}"
    assert "command failed with exit code 7" in captured.err
    assert "git clone" in captured.err
    assert secret not in combined
    assert source_url not in combined


def test_install_stops_before_dependents_when_build_artifact_is_missing(tmp_path: Path) -> None:
    first = ManifestComponent(
        name="first",
        source_kind="workspace",
        source_dir="workspace/first",
        artifact="workspace/first/build/first",
        model_bytes=None,
        runtime_kind="command",
    )
    second = ManifestComponent(
        name="second",
        source_kind="workspace",
        source_dir="workspace/second",
        artifact="workspace/second/build/second",
        model_bytes=None,
        runtime_kind="command",
    )
    _write_manifest(tmp_path, first, second)
    (tmp_path / first.source_dir).mkdir(parents=True)
    (tmp_path / second.source_dir).mkdir(parents=True)
    commands: list[list[str]] = []

    with pytest.raises(servctl.ServctlError, match=r"component first.*artifact is missing"):
        install_components(
            tmp_path,
            run_command=lambda command, **kwargs: commands.append(command),
            download=lambda url, destination: pytest.fail("components have no models"),
        )

    first_source = tmp_path / first.source_dir
    first_build = tmp_path / "workspace" / "first" / "build"
    assert commands == [
        ["cmake", "-S", str(first_source), "-B", str(first_build)],
        ["cmake", "--build", str(first_build), "--target", "first"],
    ]


def test_install_explicitly_disabled_component_has_no_side_effects(tmp_path: Path) -> None:
    component = ManifestComponent(enabled=False)
    _write_manifest(tmp_path, component)

    result = install_components(
        tmp_path,
        names=["llama"],
        run_command=lambda command, **kwargs: pytest.fail(
            "disabled component must not run commands"
        ),
        download=lambda url, destination: pytest.fail("disabled component must not download"),
    )

    assert result == [
        ComponentResult(
            name="llama",
            enabled=False,
            state="disabled",
            detail="disabled by component manifest",
        )
    ]


def test_install_never_uses_destructive_git_commands(tmp_path: Path) -> None:
    component = ManifestComponent()
    first_commit = _create_source(tmp_path, component)
    source_dir = tmp_path / "desktop" / "vendor" / component.source_dir
    (source_dir / "source.txt").write_text("second\n", encoding="utf-8")
    _git(source_dir, "add", "source.txt")
    _git(source_dir, "commit", "--quiet", "-m", "second")
    second_commit = _git(source_dir, "rev-parse", "HEAD")
    assert second_commit != first_commit
    configured = ManifestComponent(commit=first_commit)
    _write_manifest(tmp_path, configured)
    commands: list[list[str]] = []

    def run_command(command: list[str], *, cwd: Path) -> None:
        commands.append(command)
        if command[:2] == ["git", "checkout"]:
            subprocess.check_call(command, cwd=cwd)
        elif command[:2] == ["cmake", "--build"]:
            _write_artifact(tmp_path, configured)

    install_components(
        tmp_path,
        names=["llama"],
        run_command=run_command,
        download=lambda url, destination: destination.write_bytes(MODEL_BYTES),
    )

    assert ["git", "checkout", "--detach", first_commit] in commands
    assert not any(command[:2] == ["git", "reset"] for command in commands)
    assert not any(command[:2] == ["git", "clean"] for command in commands)


def test_install_rejects_download_with_wrong_exact_size_before_replace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    component = ManifestComponent()
    commit = _create_source(tmp_path, component)
    configured = ManifestComponent(commit=commit)
    _write_manifest(tmp_path, configured)

    def run_command(command: list[str], *, cwd: Path) -> None:
        if command[:2] == ["git", "checkout"]:
            subprocess.check_call(command, cwd=cwd)
        elif command[:2] == ["cmake", "--build"]:
            _write_artifact(tmp_path, configured)

    monkeypatch.setattr(
        component_commands.os,
        "replace",
        lambda source, destination: pytest.fail("invalid partial must not be renamed"),
    )

    with pytest.raises(servctl.ServctlError, match="downloaded model size mismatch"):
        install_components(
            tmp_path,
            names=["llama"],
            run_command=run_command,
            download=lambda url, destination: destination.write_bytes(b"short"),
        )


def test_install_rejects_download_with_wrong_sha_before_replace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    component = ManifestComponent()
    commit = _create_source(tmp_path, component)
    configured = ManifestComponent(commit=commit)
    _write_manifest(tmp_path, configured)

    def run_command(command: list[str], *, cwd: Path) -> None:
        if command[:2] == ["git", "checkout"]:
            subprocess.check_call(command, cwd=cwd)
        elif command[:2] == ["cmake", "--build"]:
            _write_artifact(tmp_path, configured)

    monkeypatch.setattr(
        component_commands.os,
        "replace",
        lambda source, destination: pytest.fail("wrong SHA partial must not be renamed"),
    )
    wrong_content = b"x" * len(MODEL_BYTES)
    assert hashlib.sha256(wrong_content).hexdigest() != MODEL_SHA256

    with pytest.raises(servctl.ServctlError, match="downloaded model SHA256 mismatch"):
        install_components(
            tmp_path,
            names=["llama"],
            run_command=run_command,
            download=lambda url, destination: destination.write_bytes(wrong_content),
        )


def test_install_rejects_preexisting_partial_symlink_before_download(tmp_path: Path) -> None:
    component = ManifestComponent(
        source_kind="workspace",
        source_dir="workspace/llama",
        artifact="workspace/llama/build/llama-tool",
        runtime_kind="command",
    )
    _write_manifest(tmp_path, component)
    (tmp_path / component.source_dir).mkdir(parents=True)
    model_dir = tmp_path / "desktop" / "vendor" / "models"
    model_dir.mkdir(parents=True)
    outside = tmp_path / "outside-model"
    outside.write_bytes(b"must remain unchanged")
    partial = model_dir / "llama.gguf.partial"
    partial.symlink_to(outside)

    def run_command(command: list[str], *, cwd: Path) -> None:
        if command[:2] == ["cmake", "--build"]:
            _write_artifact(tmp_path, component)

    with pytest.raises(servctl.ServctlError, match="partial download path is a symlink"):
        install_components(
            tmp_path,
            names=["llama"],
            run_command=run_command,
            download=lambda url, destination: pytest.fail("unsafe partial must not be opened"),
        )

    assert partial.is_symlink()
    assert outside.read_bytes() == b"must remain unchanged"


def test_install_raises_when_atomic_replace_does_not_create_final(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    component = ManifestComponent(
        source_kind="workspace",
        source_dir="workspace/llama",
        artifact="workspace/llama/build/llama-tool",
        runtime_kind="command",
    )
    _write_manifest(tmp_path, component)
    (tmp_path / component.source_dir).mkdir(parents=True)

    def run_command(command: list[str], *, cwd: Path) -> None:
        if command[:2] == ["cmake", "--build"]:
            _write_artifact(tmp_path, component)

    monkeypatch.setattr(component_commands.os, "replace", lambda source, destination: None)

    with pytest.raises(servctl.ServctlError, match=r"component llama.*atomic model install failed"):
        install_components(
            tmp_path,
            names=["llama"],
            run_command=run_command,
            download=lambda url, destination: destination.write_bytes(MODEL_BYTES),
        )


def test_install_translates_download_io_failure_to_servctl_error(tmp_path: Path) -> None:
    component = ManifestComponent(
        source_kind="workspace",
        source_dir="workspace/llama",
        artifact="workspace/llama/build/llama-tool",
        runtime_kind="command",
    )
    _write_manifest(tmp_path, component)
    (tmp_path / component.source_dir).mkdir(parents=True)

    def run_command(command: list[str], *, cwd: Path) -> None:
        if command[:2] == ["cmake", "--build"]:
            _write_artifact(tmp_path, component)

    secret = "download-secret-marker"
    failed_url = f"{MODEL_URL}?token={secret}"
    with pytest.raises(
        servctl.ServctlError, match=r"component llama.*model download failed"
    ) as error:
        install_components(
            tmp_path,
            names=["llama"],
            run_command=run_command,
            download=lambda url, destination: (_ for _ in ()).throw(
                urllib.error.URLError(f"network unavailable for {failed_url}")
            ),
        )
    assert "URLError" in str(error.value)
    assert failed_url not in str(error.value)
    assert secret not in str(error.value)


def test_default_downloader_does_not_follow_symlink_created_after_precheck(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    component = ManifestComponent(
        source_kind="workspace",
        source_dir="workspace/llama",
        artifact="workspace/llama/build/llama-tool",
        runtime_kind="command",
    )
    _write_manifest(tmp_path, component)
    (tmp_path / component.source_dir).mkdir(parents=True)
    partial = tmp_path / "desktop" / "vendor" / "models" / "llama.gguf.partial"
    outside = tmp_path / "outside-model"
    outside.write_bytes(b"must remain unchanged")
    chunks = iter([MODEL_BYTES, b""])

    class RacingResponse:
        status = 200

        def __enter__(self):
            partial.symlink_to(outside)
            return self

        def __exit__(self, exc_type, exc, traceback) -> None:
            return None

        def read(self, size: int) -> bytes:
            return next(chunks)

    monkeypatch.setattr(
        component_commands.urllib.request,
        "urlopen",
        lambda url: RacingResponse(),
    )

    def run_command(command: list[str], *, cwd: Path) -> None:
        if command[:2] == ["cmake", "--build"]:
            _write_artifact(tmp_path, component)

    with pytest.raises(servctl.ServctlError, match=r"component llama.*model download failed"):
        install_components(
            tmp_path,
            names=["llama"],
            run_command=run_command,
        )

    assert outside.read_bytes() == b"must remain unchanged"


def test_default_downloader_rejects_partial_swapped_to_symlink_after_close(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    component = ManifestComponent(
        source_kind="workspace",
        source_dir="workspace/llama",
        artifact="workspace/llama/build/llama-tool",
        runtime_kind="command",
    )
    _write_manifest(tmp_path, component)
    (tmp_path / component.source_dir).mkdir(parents=True)
    partial = tmp_path / "desktop" / "vendor" / "models" / "llama.gguf.partial"
    final = partial.with_name("llama.gguf")
    outside = tmp_path / "outside-model"
    outside.write_bytes(MODEL_BYTES)
    chunks = iter([MODEL_BYTES, b""])

    class SwapAfterCloseResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback) -> None:
            partial.unlink()
            partial.symlink_to(outside)

        def read(self, size: int) -> bytes:
            return next(chunks)

    monkeypatch.setattr(
        component_commands.urllib.request,
        "urlopen",
        lambda url: SwapAfterCloseResponse(),
    )
    monkeypatch.setattr(
        component_commands.os,
        "replace",
        lambda source, destination: pytest.fail("swapped partial must not be renamed"),
    )

    def run_command(command: list[str], *, cwd: Path) -> None:
        if command[:2] == ["cmake", "--build"]:
            _write_artifact(tmp_path, component)

    with pytest.raises(servctl.ServctlError, match=r"component llama.*downloaded model"):
        install_components(
            tmp_path,
            names=["llama"],
            run_command=run_command,
        )

    assert not final.exists()
    assert outside.read_bytes() == MODEL_BYTES


def test_default_downloader_streams_with_bounded_reads(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reads: list[int] = []
    chunks = iter([b"first", b"second", b""])

    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback) -> None:
            return None

        def read(self, size: int) -> bytes:
            reads.append(size)
            return next(chunks)

    monkeypatch.setattr(component_commands.urllib.request, "urlopen", lambda url: Response())
    destination = tmp_path / "model.partial"

    component_commands._download_model(MODEL_URL, destination)

    assert destination.read_bytes() == b"firstsecond"
    assert reads == [1024 * 1024, 1024 * 1024, 1024 * 1024]


def test_workspace_verify_and_install_never_run_git(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    component = ManifestComponent(
        source_kind="workspace",
        source_dir="workspace/llama",
        artifact="workspace/llama/build/llama-tool",
        runtime_kind="command",
    )
    _write_manifest(tmp_path, component)
    (tmp_path / component.source_dir).mkdir(parents=True)
    _write_artifact(tmp_path, component)
    _write_model(tmp_path, component)
    monkeypatch.setattr(
        component_commands.subprocess,
        "run",
        lambda *args, **kwargs: pytest.fail("workspace verification must not run Git"),
    )

    verified = verify_components(tmp_path, names=["llama"])

    assert verified[0].state == "ready"

    (tmp_path / component.artifact).unlink()
    (tmp_path / "desktop" / "vendor" / "models" / "llama.gguf").unlink()
    commands: list[list[str]] = []

    def run_command(command: list[str], *, cwd: Path) -> None:
        commands.append(command)
        if command[:2] == ["cmake", "--build"]:
            _write_artifact(tmp_path, component)

    installed = install_components(
        tmp_path,
        names=["llama"],
        run_command=run_command,
        download=lambda url, destination: destination.write_bytes(MODEL_BYTES),
    )

    assert installed[0].state == "ready"
    assert commands
    assert all(command[0] != "git" for command in commands)


def test_status_reports_disabled_without_inspecting_assets(tmp_path: Path) -> None:
    disabled = ManifestComponent(enabled=False)
    _write_manifest(tmp_path, disabled)

    result = status_components(
        tmp_path,
        "local",
        process_exists=lambda pid: pytest.fail("disabled component must not inspect a process"),
        http_probe=lambda *args: pytest.fail("disabled component must not probe HTTP"),
    )

    assert result == [
        ComponentResult(
            name="llama",
            enabled=False,
            state="disabled",
            detail="disabled by component manifest",
        )
    ]


def test_status_reports_missing_and_invalid_assets(tmp_path: Path) -> None:
    missing_root = tmp_path / "missing"
    _write_manifest(missing_root, ManifestComponent())
    missing = status_components(missing_root, "local", names=["llama"])

    invalid_root = tmp_path / "invalid"
    component = ManifestComponent()
    commit = _create_source(invalid_root, component)
    configured = ManifestComponent(commit=commit)
    _write_manifest(invalid_root, configured)
    _write_artifact(invalid_root, configured, executable=False)
    _write_model(invalid_root, configured)
    invalid = status_components(invalid_root, "local", names=["llama"])

    assert missing[0].state == "missing"
    assert invalid[0].state == "invalid"


def test_status_reports_stopped_service_when_pid_file_is_missing(tmp_path: Path) -> None:
    _ready_external_component(tmp_path)

    result = status_components(tmp_path, "local", names=["llama"])

    assert result == [
        ComponentResult(
            name="llama",
            enabled=True,
            state="stopped",
            detail=f"missing pid file: {tmp_path / 'run' / 'yts-component-llama-local.pid'}",
        )
    ]


@pytest.mark.parametrize(
    ("healthy", "state", "detail"),
    [
        (True, "ready", "ready: pid 12345"),
        (False, "unhealthy", "readiness probe failed: pid 12345"),
    ],
)
def test_status_probes_running_service_health(
    tmp_path: Path,
    healthy: bool,
    state: str,
    detail: str,
) -> None:
    _ready_external_component(tmp_path)
    pid_path = tmp_path / "run" / "yts-component-llama-local.pid"
    pid_path.parent.mkdir()
    pid_path.write_text("12345\n", encoding="utf-8")
    probes: list[tuple[str, int, str, int]] = []

    def http_probe(host: str, port: int, path: str, timeout_seconds: int) -> bool:
        probes.append((host, port, path, timeout_seconds))
        return healthy

    result = status_components(
        tmp_path,
        "local",
        names=["llama"],
        process_exists=lambda pid: pid == 12345,
        http_probe=http_probe,
    )

    assert result == [ComponentResult(name="llama", enabled=True, state=state, detail=detail)]
    assert probes == [("127.0.0.1", 8080, "/ready", 2)]


def test_status_reports_ready_for_command_component_without_pid(tmp_path: Path) -> None:
    component = ManifestComponent(runtime_kind="command")
    configured = _ready_external_component(tmp_path, component)
    assert configured.runtime_kind == "command"

    result = status_components(tmp_path, "local", names=["llama"])

    assert result == [
        ComponentResult(
            name="llama",
            enabled=True,
            state="ready",
            detail="assets verified; command component is on demand",
        )
    ]


def test_status_reports_pid_file_read_error_as_invalid(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ready_external_component(tmp_path)
    pid_path = tmp_path / "run" / "yts-component-llama-local.pid"
    pid_path.parent.mkdir()
    pid_path.write_text("12345\n", encoding="utf-8")
    real_read_text = Path.read_text

    def read_text(path: Path, *args, **kwargs) -> str:
        if path == pid_path:
            raise PermissionError("permission denied")
        return real_read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", read_text)

    result = status_components(tmp_path, "local", names=["llama"])

    assert result == [
        ComponentResult(
            name="llama",
            enabled=True,
            state="invalid",
            detail=f"cannot read pid file: {pid_path}: permission denied",
        )
    ]


def test_status_with_no_names_includes_all_manifest_components(tmp_path: Path) -> None:
    enabled = ManifestComponent(model_bytes=None, runtime_kind="command")
    disabled = ManifestComponent(
        name="acestep",
        enabled=False,
        source_dir="acestep-src",
        artifact="acestep-src/build/acestep",
        model_bytes=None,
    )
    _write_manifest(tmp_path, enabled, disabled)

    result = status_components(tmp_path, "local")

    assert [(item.name, item.state) for item in result] == [
        ("llama", "missing"),
        ("acestep", "disabled"),
    ]


def test_cli_dispatches_component_commands_and_preserves_name_order(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    calls: list[tuple[Any, ...]] = []
    fake_file = tmp_path / "scripts" / "servctl" / "__init__.py"

    def install(root: Path, names: list[str] | None):
        calls.append(("install", root, names))
        return [ComponentResult("llama", True, "ready", "assets verified")]

    def verify(root: Path, names: list[str] | None):
        calls.append(("verify", root, names))
        return [ComponentResult("llama", True, "ready", "assets verified")]

    def status(root: Path, profile: str, names: list[str] | None):
        calls.append(("status", root, profile, names))
        return [ComponentResult("llama", True, "ready", "ready: pid 12345")]

    api = SimpleNamespace(
        __file__=str(fake_file),
        Path=Path,
        install_components=install,
        verify_components=verify,
        status_components=status,
    )

    assert servctl.main(["components", "install"], api=api) == 0
    assert (
        servctl.main(
            ["components", "install", "llama", "stable-diffusion"],
            api=api,
        )
        == 0
    )
    assert servctl.main(["components", "verify", "llama"], api=api) == 0
    assert (
        servctl.main(
            ["components", "status", "llama", "--profile", "local"],
            api=api,
        )
        == 0
    )

    assert calls == [
        ("install", tmp_path, None),
        ("install", tmp_path, ["llama", "stable-diffusion"]),
        ("verify", tmp_path, ["llama"]),
        ("status", tmp_path, "local", ["llama"]),
    ]
    assert capsys.readouterr().out.splitlines() == [
        "llama: ready - assets verified",
        "llama: ready - assets verified",
        "llama: ready - assets verified",
        "llama: ready - ready: pid 12345",
    ]


@pytest.mark.parametrize(
    ("state", "expected_exit"),
    [
        ("ready", 0),
        ("disabled", 0),
        ("missing", 1),
        ("invalid", 1),
        ("stopped", 1),
        ("unhealthy", 1),
    ],
)
def test_cli_component_status_returns_nonzero_for_enabled_failures(
    tmp_path: Path,
    state: str,
    expected_exit: int,
) -> None:
    enabled = state != "disabled"
    api = SimpleNamespace(
        __file__=str(tmp_path / "scripts" / "servctl" / "__init__.py"),
        Path=Path,
        status_components=lambda root, profile, names: [
            ComponentResult("llama", enabled, state, "detail")
        ],
    )

    assert servctl.main(["components", "status", "--profile", "local"], api=api) == expected_exit


def test_cli_component_verify_does_not_treat_disabled_as_ready(tmp_path: Path) -> None:
    api = SimpleNamespace(
        __file__=str(tmp_path / "scripts" / "servctl" / "__init__.py"),
        Path=Path,
        verify_components=lambda root, names: [
            ComponentResult("acestep", False, "missing", "disabled asset is absent")
        ],
    )

    assert servctl.main(["components", "verify", "acestep"], api=api) == 1
