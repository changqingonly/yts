from __future__ import annotations

import hashlib
import os
import stat
import subprocess
import urllib.error
import urllib.request
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Literal
from urllib.parse import urlsplit, urlunsplit

from yts_core.components import (
    ComponentManifest,
    ModelAsset,
    ResolvedComponent,
    RuntimeSpec,
    current_platform,
    expand_argv,
    load_component_manifest,
    resolve_component_paths,
)

from .errors import ServctlError
from .process import _process_exists

_MANIFEST_PATH = Path("desktop/components.toml")
_SUPPORTED_PROFILES = frozenset({"cloud", "local"})
_HASH_CHUNK_SIZE = 1024 * 1024
_DOWNLOAD_CHUNK_SIZE = 1024 * 1024
_DEFAULT_RUN_COMMAND = subprocess.check_call
_ComponentState = Literal["disabled", "missing", "invalid", "stopped", "ready", "unhealthy"]
_InspectionState = Literal["missing", "invalid", "ready"]

__all__ = [
    "ComponentResult",
    "install_components",
    "status_components",
    "verify_components",
]


@dataclass(frozen=True)
class ComponentResult:
    name: str
    enabled: bool
    state: _ComponentState
    detail: str


@dataclass(frozen=True)
class _Inspection:
    state: _InspectionState
    detail: str


@dataclass(frozen=True)
class _PinnedDirectory:
    entry_name: str | None
    descriptor: int
    identity: os.stat_result


def _sha256_file(path: Path) -> str:
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(descriptor, "rb") as handle:
        return _sha256_stream(handle)


def _sha256_stream(handle: BinaryIO) -> str:
    digest = hashlib.sha256()
    while chunk := handle.read(_HASH_CHUNK_SIZE):
        digest.update(chunk)
    return digest.hexdigest()


def _download_model(url: str, destination: Path) -> None:
    parent_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    parent_descriptor = os.open(destination.parent, parent_flags)
    try:
        _download_model_at(url, destination.name, parent_descriptor)
    finally:
        os.close(parent_descriptor)


def _download_model_at(url: str, destination_name: str, parent_descriptor: int) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
    with urllib.request.urlopen(url) as response:
        descriptor = os.open(destination_name, flags, 0o600, dir_fd=parent_descriptor)
        with os.fdopen(descriptor, "wb") as output:
            while chunk := response.read(_DOWNLOAD_CHUNK_SIZE):
                output.write(chunk)


def _http_probe(host: str, port: int, path: str, timeout_seconds: int) -> bool:
    url = f"http://{host}:{port}{path}"
    try:
        with urllib.request.urlopen(url, timeout=timeout_seconds) as response:
            return 200 <= response.status < 300
    except (urllib.error.URLError, TimeoutError):
        return False


def install_components(
    root: Path,
    names: Sequence[str] | None = None,
    *,
    run_command: Callable[..., None] = subprocess.check_call,
    download: Callable[[str, Path], None] = _download_model,
) -> list[ComponentResult]:
    resolved_root, manifest = _load_manifest(root)
    selected = _select_components(manifest, names, include_disabled_by_default=False)
    results: list[ComponentResult] = []

    for name in selected:
        component = manifest.components[name]
        if not component.enabled:
            results.append(_disabled_result(name))
            continue

        resolved = _resolve_component(resolved_root, manifest, name)
        _prepare_source(resolved, run_command)
        _build_component(resolved, run_command)

        artifact = _inspect_artifact(resolved.artifact)
        if artifact.state != "ready":
            raise ServctlError(f"component {name}: {artifact.detail}")

        for model_spec in component.models:
            model_path = resolved.models[model_spec.id]
            existing = _inspect_model(model_path, model_spec, _sha256_file)
            if existing.state == "ready":
                continue
            _install_model(name, model_spec, resolved.root, model_path, download)

        inspection = _inspect_component(resolved, _sha256_file)
        if inspection.state != "ready":
            raise ServctlError(f"component {name}: {inspection.detail}")
        results.append(_result_from_inspection(name, True, inspection))

    return results


def verify_components(
    root: Path,
    names: Sequence[str] | None = None,
    *,
    hash_file: Callable[[Path], str] = _sha256_file,
) -> list[ComponentResult]:
    resolved_root, manifest = _load_manifest(root)
    selected = _select_components(manifest, names, include_disabled_by_default=False)
    results: list[ComponentResult] = []

    for name in selected:
        component = manifest.components[name]
        if not component.enabled:
            results.append(_disabled_result(name))
            continue
        resolved = _resolve_component(resolved_root, manifest, name)
        inspection = _inspect_component(resolved, hash_file)
        results.append(_result_from_inspection(name, True, inspection))
    return results


def status_components(
    root: Path,
    profile: str,
    names: Sequence[str] | None = None,
    *,
    process_exists: Callable[[int], bool] = _process_exists,
    http_probe: Callable[[str, int, str, int], bool] = _http_probe,
) -> list[ComponentResult]:
    if profile not in _SUPPORTED_PROFILES:
        supported = ", ".join(sorted(_SUPPORTED_PROFILES))
        raise ServctlError(
            f"unsupported component status profile {profile}; expected one of: {supported}"
        )

    resolved_root, manifest = _load_manifest(root)
    selected = _select_components(manifest, names, include_disabled_by_default=True)
    results: list[ComponentResult] = []

    for name in selected:
        component = manifest.components[name]
        if not component.enabled:
            results.append(_disabled_result(name))
            continue

        resolved = _resolve_component(resolved_root, manifest, name)
        inspection = _inspect_component(resolved, _sha256_file)
        if inspection.state != "ready":
            results.append(_result_from_inspection(name, True, inspection))
            continue

        if component.runtime.kind == "command":
            results.append(
                ComponentResult(
                    name=name,
                    enabled=True,
                    state="ready",
                    detail="assets verified; command component is on demand",
                )
            )
            continue

        results.append(
            _status_service(
                resolved_root,
                name,
                profile,
                component.runtime,
                process_exists,
                http_probe,
            )
        )
    return results


def _load_manifest(root: Path) -> tuple[Path, ComponentManifest]:
    resolved_root = Path(root).expanduser().resolve()
    manifest_path = resolved_root / _MANIFEST_PATH
    if not manifest_path.is_file():
        raise ServctlError(f"missing component manifest: {manifest_path}")
    try:
        manifest = load_component_manifest(manifest_path)
    except (OSError, ValueError) as exc:
        raise ServctlError(f"invalid component manifest: {exc}") from exc
    return resolved_root, manifest


def _select_components(
    manifest: ComponentManifest,
    names: Sequence[str] | None,
    *,
    include_disabled_by_default: bool,
) -> list[str]:
    if isinstance(names, str):
        raise ServctlError("component names must be a sequence of names, not one string")
    if names is None:
        if include_disabled_by_default:
            selected = list(manifest.components)
        else:
            try:
                selected = manifest.start_order()
            except ValueError as exc:
                raise ServctlError(f"invalid component dependency order: {exc}") from exc
    else:
        selected = list(names)
        seen: set[str] = set()
        for name in selected:
            if not isinstance(name, str):
                raise ServctlError("component names must be strings")
            if name in seen:
                raise ServctlError(f"duplicate component name {name}")
            seen.add(name)
            if name not in manifest.components:
                raise ServctlError(f"unknown component {name}")

    enabled = [name for name in selected if manifest.components[name].enabled]
    if not enabled:
        return selected
    try:
        platform_id = current_platform()
    except ValueError as exc:
        raise ServctlError(str(exc)) from exc
    for name in enabled:
        supported = manifest.components[name].platforms
        if platform_id not in supported:
            supported_text = ", ".join(supported)
            raise ServctlError(
                f"component {name} current platform {platform_id} is not supported; "
                f"supported platforms: {supported_text}"
            )
    return selected


def _resolve_component(root: Path, manifest: ComponentManifest, name: str) -> ResolvedComponent:
    try:
        return resolve_component_paths(root, manifest, name)
    except (TypeError, ValueError) as exc:
        raise ServctlError(f"invalid paths for component {name}: {exc}") from exc


def _disabled_result(name: str) -> ComponentResult:
    return ComponentResult(
        name=name,
        enabled=False,
        state="disabled",
        detail="disabled by component manifest",
    )


def _result_from_inspection(name: str, enabled: bool, inspection: _Inspection) -> ComponentResult:
    return ComponentResult(
        name=name,
        enabled=enabled,
        state=inspection.state,
        detail=inspection.detail,
    )


def _inspect_component(
    resolved: ResolvedComponent,
    hash_file: Callable[[Path], str],
) -> _Inspection:
    source = _inspect_source(resolved)
    if source.state != "ready":
        return source

    artifact = _inspect_artifact(resolved.artifact)
    if artifact.state != "ready":
        return artifact

    for model_spec in resolved.component.models:
        model = _inspect_model(resolved.models[model_spec.id], model_spec, hash_file)
        if model.state != "ready":
            return model
    return _Inspection("ready", "assets verified")


def _inspect_source(resolved: ResolvedComponent) -> _Inspection:
    source_dir = resolved.source_dir
    if not source_dir.exists():
        return _Inspection("missing", f"source directory is missing: {source_dir}")
    if not source_dir.is_dir():
        return _Inspection("invalid", f"source path is not a directory: {source_dir}")
    if resolved.component.source.kind == "workspace":
        return _Inspection("ready", "workspace source exists")
    return _inspect_external_source(resolved)


def _inspect_external_source(resolved: ResolvedComponent) -> _Inspection:
    remote = _inspect_external_remote(resolved)
    if remote.state != "ready":
        return remote

    if resolved.component.source.submodules:
        submodules = _inspect_external_submodules(resolved)
        if submodules.state != "ready":
            return submodules

    dirty = _inspect_external_dirty(resolved)
    if dirty.state != "ready":
        return dirty

    head = _git_output(resolved.source_dir, "rev-parse", "--verify", "HEAD")
    if head is None:
        return _Inspection("invalid", f"source has no readable Git HEAD: {resolved.source_dir}")
    expected_commit = resolved.component.source.commit
    if head != expected_commit:
        return _Inspection(
            "invalid",
            f"source commit mismatch: expected {expected_commit}, found {head}",
        )
    return _Inspection("ready", "source verified")


def _inspect_external_preconditions(resolved: ResolvedComponent) -> _Inspection:
    remote = _inspect_external_remote(resolved)
    if remote.state != "ready":
        return remote
    return _inspect_external_dirty(resolved)


def _inspect_external_remote(resolved: ResolvedComponent) -> _Inspection:
    remote = _git_output(resolved.source_dir, "config", "--get", "remote.origin.url")
    if remote is None:
        return _Inspection(
            "invalid", f"source is not a readable Git repository: {resolved.source_dir}"
        )
    expected_remote = resolved.component.source.url
    if remote != expected_remote:
        return _Inspection(
            "invalid",
            f"source remote mismatch: expected pinned remote {_display_url(expected_remote)}",
        )
    return _Inspection("ready", "source remote verified")


def _display_url(url: str) -> str:
    parsed = urlsplit(url)
    hostname = parsed.hostname or "<redacted-host>"
    if ":" in hostname:
        hostname = f"[{hostname}]"
    port = f":{parsed.port}" if parsed.port is not None else ""
    query = "<redacted>" if parsed.query else ""
    return urlunsplit((parsed.scheme, f"{hostname}{port}", parsed.path, query, ""))


def _inspect_external_dirty(resolved: ResolvedComponent) -> _Inspection:
    status = _git_output(
        resolved.source_dir,
        "status",
        "--porcelain",
        "--ignore-submodules=none",
        "--untracked-files=all",
    )
    if status is None:
        return _Inspection("invalid", f"source Git status failed: {resolved.source_dir}")
    if status:
        return _Inspection("invalid", f"source tree is dirty: {resolved.source_dir}")
    return _Inspection("ready", "source checkout preconditions verified")


def _inspect_external_submodules(resolved: ResolvedComponent) -> _Inspection:
    status = _git_output(resolved.source_dir, "submodule", "status", "--recursive")
    if status is None:
        return _Inspection(
            "invalid",
            f"recursive submodule status failed: {resolved.source_dir}",
        )
    for line in status.splitlines():
        if line.startswith("-"):
            return _Inspection("invalid", f"submodule is not initialized: {resolved.source_dir}")
        if line.startswith("+"):
            return _Inspection("invalid", f"submodule commit mismatch: {resolved.source_dir}")
        if line.startswith("U"):
            return _Inspection("invalid", f"submodule has merge conflicts: {resolved.source_dir}")
    return _Inspection("ready", "recursive submodules verified")


def _git_output(source_dir: Path, *arguments: str) -> str | None:
    try:
        completed = subprocess.run(
            ["git", *arguments],
            cwd=source_dir,
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        raise ServctlError(f"Git inspection failed in {source_dir}: {exc}") from exc
    if completed.returncode != 0:
        return None
    return completed.stdout.strip()


def _inspect_artifact(path: Path) -> _Inspection:
    if not path.exists():
        return _Inspection("missing", f"artifact is missing: {path}")
    if not path.is_file():
        return _Inspection("invalid", f"artifact is not a regular file: {path}")
    if not os.access(path, os.X_OK):
        return _Inspection("invalid", f"artifact is not executable: {path}")
    return _Inspection("ready", "artifact verified")


def _inspect_model(
    path: Path,
    model_spec: ModelAsset,
    hash_file: Callable[[Path], str],
) -> _Inspection:
    if path.is_symlink():
        return _Inspection("invalid", f"model {model_spec.id} is a symlink: {path}")
    if not path.exists():
        return _Inspection("missing", f"model {model_spec.id} is missing: {path}")
    try:
        model_stat = path.stat(follow_symlinks=False)
    except OSError as exc:
        return _Inspection("invalid", f"cannot inspect model {model_spec.id}: {path}: {exc}")
    if not stat.S_ISREG(model_stat.st_mode):
        return _Inspection("invalid", f"model {model_spec.id} is not a regular file: {path}")
    actual_size = model_stat.st_size
    if actual_size != model_spec.size:
        return _Inspection(
            "invalid",
            f"model size mismatch for {model_spec.id}: expected {model_spec.size}, "
            f"found {actual_size}: {path}",
        )
    try:
        actual_hash = hash_file(path)
    except OSError as exc:
        return _Inspection("invalid", f"cannot hash model {model_spec.id}: {path}: {exc}")
    if actual_hash != model_spec.sha256:
        return _Inspection(
            "invalid",
            f"model SHA256 mismatch for {model_spec.id}: expected {model_spec.sha256}, "
            f"found {actual_hash}: {path}",
        )
    return _Inspection("ready", f"model {model_spec.id} verified")


def _prepare_source(resolved: ResolvedComponent, run_command: Callable[..., None]) -> None:
    source = resolved.component.source
    if source.kind == "workspace":
        inspection = _inspect_source(resolved)
        if inspection.state != "ready":
            raise ServctlError(f"component {resolved.name}: {inspection.detail}")
        return

    if not resolved.source_dir.exists():
        resolved.source_dir.parent.mkdir(parents=True, exist_ok=True)
        _run_component_command(
            run_command,
            ["git", "clone", source.url, str(resolved.source_dir)],
            resolved.source_dir.parent,
            resolved.name,
            "clone",
        )
    elif not resolved.source_dir.is_dir():
        raise ServctlError(
            f"component {resolved.name}: source path is not a directory: {resolved.source_dir}"
        )

    precondition = _inspect_external_preconditions(resolved)
    if precondition.state != "ready":
        raise ServctlError(f"component {resolved.name}: {precondition.detail}")

    commit_object = _git_output(
        resolved.source_dir,
        "cat-file",
        "-e",
        f"{source.commit}^{{commit}}",
    )
    if commit_object is None:
        _run_component_command(
            run_command,
            ["git", "fetch", "--no-tags", "origin", source.commit],
            resolved.source_dir,
            resolved.name,
            "fetch",
        )

    _run_component_command(
        run_command,
        ["git", "checkout", "--detach", source.commit],
        resolved.source_dir,
        resolved.name,
        "checkout",
    )
    if source.submodules:
        _run_component_command(
            run_command,
            ["git", "submodule", "update", "--init", "--recursive"],
            resolved.source_dir,
            resolved.name,
            "submodule update",
        )

    inspection = _inspect_external_source(resolved)
    if inspection.state != "ready":
        raise ServctlError(f"component {resolved.name}: {inspection.detail}")


def _build_component(resolved: ResolvedComponent, run_command: Callable[..., None]) -> None:
    tokens = resolved.argv_tokens()
    try:
        configure_argv = expand_argv(resolved.component.build.configure_argv, tokens)
        build_argv = expand_argv(resolved.component.build.build_argv, tokens)
    except (TypeError, ValueError) as exc:
        raise ServctlError(f"invalid build argv for component {resolved.name}: {exc}") from exc
    if configure_argv:
        _run_component_command(
            run_command,
            configure_argv,
            resolved.root,
            resolved.name,
            "configure",
        )
    _run_component_command(
        run_command,
        build_argv,
        resolved.root,
        resolved.name,
        "build",
    )


def _run_component_command(
    run_command: Callable[..., None],
    argv: list[str],
    cwd: Path,
    component_name: str,
    operation: str,
) -> None:
    output_options = (
        {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
        if run_command is _DEFAULT_RUN_COMMAND and argv and argv[0] == "git"
        else {}
    )
    return_code: int | None = None
    try:
        run_command(argv, cwd=cwd, **output_options)
    except subprocess.CalledProcessError as exc:
        return_code = exc.returncode
    except OSError as exc:
        raise ServctlError(f"component {component_name} {operation} command failed: {exc}") from exc
    if return_code is not None:
        raise ServctlError(
            f"component {component_name} {operation} command failed with exit code {return_code}"
        )


def _install_model(
    component_name: str,
    model_spec: ModelAsset,
    root: Path,
    model_path: Path,
    download: Callable[[str, Path], None],
) -> None:
    model_parent = model_path.parent
    partial_path = model_path.with_name(f"{model_path.name}.partial")
    pinned_directories = _pin_model_directory_ancestry(component_name, root, model_parent)
    parent_descriptor = pinned_directories[-1].descriptor

    try:
        _require_model_directory_ancestry(
            component_name,
            model_parent,
            pinned_directories,
        )
        _reject_existing_partial(
            component_name,
            partial_path,
            parent_descriptor,
        )
        try:
            if download is _download_model:
                _download_model_at(model_spec.url, partial_path.name, parent_descriptor)
            else:
                download(model_spec.url, partial_path)
        except OSError as exc:
            raise ServctlError(
                f"component {component_name}: model download failed for {model_spec.id} "
                f"({type(exc).__name__})"
            ) from exc
        _require_model_directory_ancestry(
            component_name,
            model_parent,
            pinned_directories,
        )
        _verify_and_install_download(
            component_name,
            model_spec,
            partial_path,
            model_path,
            parent_descriptor,
            pinned_directories,
        )
    finally:
        _close_pinned_directories(pinned_directories)


def _pin_model_directory_ancestry(
    component_name: str,
    root: Path,
    model_parent: Path,
) -> list[_PinnedDirectory]:
    try:
        relative_parent = model_parent.relative_to(root)
    except ValueError as exc:
        raise ServctlError(
            f"component {component_name}: model directory ancestry escapes trusted root: "
            f"{model_parent}"
        ) from exc

    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    try:
        root_descriptor = os.open(root, directory_flags)
    except OSError as exc:
        raise ServctlError(
            f"component {component_name}: cannot pin trusted root for model directory ancestry: "
            f"{root}: {exc}"
        ) from exc

    try:
        root_identity = os.fstat(root_descriptor)
    except OSError as exc:
        os.close(root_descriptor)
        raise ServctlError(
            f"component {component_name}: cannot inspect trusted root for model directory "
            f"ancestry: {root}: {exc}"
        ) from exc

    pinned_directories = [_PinnedDirectory(None, root_descriptor, root_identity)]
    complete = False
    current_path = root
    try:
        for entry_name in relative_parent.parts:
            current_path /= entry_name
            descriptor = _open_model_directory_entry(
                component_name,
                entry_name,
                pinned_directories[-1].descriptor,
                current_path,
                directory_flags,
            )
            try:
                identity = os.fstat(descriptor)
            except OSError as exc:
                os.close(descriptor)
                raise ServctlError(
                    f"component {component_name}: cannot inspect model directory ancestry at "
                    f"{current_path}: {exc}"
                ) from exc
            pinned_directories.append(_PinnedDirectory(entry_name, descriptor, identity))

        _require_model_directory_ancestry(
            component_name,
            model_parent,
            pinned_directories,
        )
        complete = True
        return pinned_directories
    finally:
        if not complete:
            _close_pinned_directories(pinned_directories)


def _open_model_directory_entry(
    component_name: str,
    entry_name: str,
    parent_descriptor: int,
    display_path: Path,
    directory_flags: int,
) -> int:
    try:
        return os.open(
            entry_name,
            directory_flags,
            dir_fd=parent_descriptor,
        )
    except FileNotFoundError:
        try:
            os.mkdir(entry_name, 0o755, dir_fd=parent_descriptor)
        except OSError as exc:
            raise ServctlError(
                f"component {component_name}: cannot create model directory ancestry at "
                f"{display_path}: {exc}"
            ) from exc
        try:
            return os.open(
                entry_name,
                directory_flags,
                dir_fd=parent_descriptor,
            )
        except OSError as exc:
            raise ServctlError(
                f"component {component_name}: cannot pin newly created model directory "
                f"ancestry at {display_path}: {exc}"
            ) from exc
    except OSError as exc:
        raise ServctlError(
            f"component {component_name}: cannot pin model directory ancestry at "
            f"{display_path}: {exc}"
        ) from exc


def _require_model_directory_ancestry(
    component_name: str,
    model_parent: Path,
    pinned_directories: Sequence[_PinnedDirectory],
) -> None:
    for index, pinned_directory in enumerate(pinned_directories):
        try:
            opened_identity = os.fstat(pinned_directory.descriptor)
        except OSError as exc:
            raise ServctlError(
                f"component {component_name}: cannot verify model directory ancestry: "
                f"{model_parent}: {exc}"
            ) from exc
        if not stat.S_ISDIR(opened_identity.st_mode) or not _same_file(
            pinned_directory.identity,
            opened_identity,
        ):
            raise ServctlError(
                f"component {component_name}: model parent directory identity changed in "
                f"pinned ancestry: {model_parent}"
            )
        if index == 0:
            continue

        entry_name = pinned_directory.entry_name
        if entry_name is None:
            raise ServctlError(
                f"component {component_name}: invalid pinned model directory ancestry"
            )
        try:
            linked_identity = os.stat(
                entry_name,
                dir_fd=pinned_directories[index - 1].descriptor,
                follow_symlinks=False,
            )
        except OSError as exc:
            raise ServctlError(
                f"component {component_name}: cannot verify model directory ancestry: "
                f"{model_parent}: {exc}"
            ) from exc
        if not stat.S_ISDIR(linked_identity.st_mode) or not _same_file(
            pinned_directory.identity,
            linked_identity,
        ):
            raise ServctlError(
                f"component {component_name}: model parent directory identity changed in "
                f"pinned ancestry: {model_parent}"
            )


def _close_pinned_directories(pinned_directories: Sequence[_PinnedDirectory]) -> None:
    for pinned_directory in reversed(pinned_directories):
        os.close(pinned_directory.descriptor)


def _reject_existing_partial(
    component_name: str,
    partial_path: Path,
    parent_descriptor: int,
) -> None:
    try:
        partial_stat = os.stat(
            partial_path.name,
            dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
    except FileNotFoundError:
        return
    except OSError as exc:
        raise ServctlError(
            f"component {component_name}: cannot inspect partial download path: "
            f"{partial_path}: {exc}"
        ) from exc
    if stat.S_ISLNK(partial_stat.st_mode):
        raise ServctlError(
            f"component {component_name}: partial download path is a symlink: {partial_path}"
        )
    if not stat.S_ISREG(partial_stat.st_mode):
        raise ServctlError(
            f"component {component_name}: partial download path is not a regular file: "
            f"{partial_path}"
        )
    raise ServctlError(
        f"component {component_name}: partial download path already exists: {partial_path}"
    )


def _verify_and_install_download(
    component_name: str,
    model_spec: ModelAsset,
    partial_path: Path,
    model_path: Path,
    parent_descriptor: int,
    pinned_directories: Sequence[_PinnedDirectory],
) -> None:
    try:
        descriptor = os.open(
            partial_path.name,
            os.O_RDONLY | os.O_NOFOLLOW,
            dir_fd=parent_descriptor,
        )
    except OSError as exc:
        raise ServctlError(
            f"component {component_name}: downloaded model is invalid for {model_spec.id}: "
            f"cannot open {partial_path} without following links: {exc}"
        ) from exc

    with os.fdopen(descriptor, "rb") as handle:
        opened_stat = os.fstat(handle.fileno())
        if not stat.S_ISREG(opened_stat.st_mode):
            raise ServctlError(
                f"component {component_name}: downloaded model is not a regular file for "
                f"{model_spec.id}: {partial_path}"
            )
        if opened_stat.st_nlink != 1:
            raise ServctlError(
                f"component {component_name}: downloaded model has multiple hard links for "
                f"{model_spec.id}: {partial_path}"
            )
        if opened_stat.st_size != model_spec.size:
            raise ServctlError(
                f"component {component_name}: downloaded model size mismatch for {model_spec.id}: "
                f"expected {model_spec.size}, found {opened_stat.st_size}: {partial_path}"
            )
        actual_hash = _sha256_stream(handle)
        if actual_hash != model_spec.sha256:
            raise ServctlError(
                f"component {component_name}: downloaded model SHA256 mismatch for "
                f"{model_spec.id}: expected {model_spec.sha256}, found {actual_hash}: {partial_path}"
            )

        try:
            opened_stat_after_hash = os.fstat(handle.fileno())
            path_stat = os.stat(
                partial_path.name,
                dir_fd=parent_descriptor,
                follow_symlinks=False,
            )
        except OSError as exc:
            raise ServctlError(
                f"component {component_name}: downloaded model identity check failed for "
                f"{model_spec.id}: {partial_path}: {exc}"
            ) from exc
        if (
            not stat.S_ISREG(opened_stat_after_hash.st_mode)
            or not stat.S_ISREG(path_stat.st_mode)
            or opened_stat_after_hash.st_nlink != 1
            or path_stat.st_nlink != 1
            or not _same_file(opened_stat, opened_stat_after_hash)
            or not _same_file(opened_stat, path_stat)
        ):
            raise ServctlError(
                f"component {component_name}: downloaded model identity changed before install "
                f"for {model_spec.id}: {partial_path}"
            )

        _require_model_directory_ancestry(
            component_name,
            model_path.parent,
            pinned_directories,
        )
        try:
            os.replace(
                partial_path.name,
                model_path.name,
                src_dir_fd=parent_descriptor,
                dst_dir_fd=parent_descriptor,
            )
            opened_installed_stat = os.fstat(handle.fileno())
            installed_stat = os.stat(
                model_path.name,
                dir_fd=parent_descriptor,
                follow_symlinks=False,
            )
        except OSError as exc:
            raise ServctlError(
                f"component {component_name}: atomic model install failed for "
                f"{model_spec.id}: {exc}"
            ) from exc
        if (
            not stat.S_ISREG(opened_installed_stat.st_mode)
            or not stat.S_ISREG(installed_stat.st_mode)
            or opened_installed_stat.st_nlink != 1
            or installed_stat.st_nlink != 1
            or not _same_file(opened_stat, opened_installed_stat)
            or not _same_file(opened_stat, installed_stat)
        ):
            raise ServctlError(
                f"component {component_name}: installed model identity mismatch for "
                f"{model_spec.id}: {model_path}"
            )
        _require_model_directory_ancestry(
            component_name,
            model_path.parent,
            pinned_directories,
        )


def _same_file(left: os.stat_result, right: os.stat_result) -> bool:
    return left.st_dev == right.st_dev and left.st_ino == right.st_ino


def _component_pid_path(root: Path, name: str, profile: str) -> Path:
    return root / "run" / f"yts-component-{name}-{profile}.pid"


def _status_service(
    root: Path,
    name: str,
    profile: str,
    runtime: RuntimeSpec,
    process_exists: Callable[[int], bool],
    http_probe: Callable[[str, int, str, int], bool],
) -> ComponentResult:
    pid_path = _component_pid_path(root, name, profile)
    if not pid_path.exists():
        return ComponentResult(name, True, "stopped", f"missing pid file: {pid_path}")
    if not pid_path.is_file():
        return ComponentResult(name, True, "invalid", f"pid path is not a file: {pid_path}")
    try:
        raw_pid = pid_path.read_text(encoding="utf-8").strip()
    except UnicodeDecodeError:
        return ComponentResult(name, True, "invalid", f"pid file is not valid UTF-8: {pid_path}")
    except OSError as exc:
        return ComponentResult(name, True, "invalid", f"cannot read pid file: {pid_path}: {exc}")
    if not raw_pid:
        return ComponentResult(name, True, "invalid", f"pid file is empty: {pid_path}")
    try:
        pid = int(raw_pid)
    except ValueError:
        return ComponentResult(name, True, "invalid", f"pid file contains invalid pid: {pid_path}")
    if pid <= 0:
        return ComponentResult(name, True, "invalid", f"pid file contains invalid pid: {pid_path}")
    if not process_exists(pid):
        return ComponentResult(name, True, "stopped", f"process is not running: pid {pid}")

    readiness = runtime.readiness
    if http_probe(runtime.host, runtime.port, readiness.path, readiness.timeout_seconds):
        return ComponentResult(name, True, "ready", f"ready: pid {pid}")
    return ComponentResult(name, True, "unhealthy", f"readiness probe failed: pid {pid}")
