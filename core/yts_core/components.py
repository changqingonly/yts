"""Strict, versioned desktop component manifest contract."""

from __future__ import annotations

import ipaddress
import platform
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from heapq import heappop, heappush
from pathlib import Path
from string import Formatter
from types import MappingProxyType
from typing import Literal
from urllib.parse import urlsplit

import tomli
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    TypeAdapter,
    ValidationError,
    field_validator,
    model_validator,
)

_IDENTIFIER_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
_DNS_LABEL_PATTERN = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$")
_COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_SUPPORTED_PLATFORMS = frozenset(
    {
        "darwin-arm64",
        "darwin-x86_64",
        "linux-x86_64",
    }
)
_PATH_TOKENS = frozenset({"root", "vendor", "source", "build", "artifact"})
_REQUEST_TOKENS = frozenset({"prompt", "out", "width", "height", "steps", "seconds"})
_F32_MAX = 3.4028234663852886e38
_FORMATTER = Formatter()
_HTTP_URL_ADAPTER = TypeAdapter(HttpUrl)


class _StrictManifestModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ModelAsset(_StrictManifestModel):
    id: str = Field(min_length=1)
    url: str = Field(min_length=1)
    size: int = Field(gt=0)
    sha256: str
    path: str = Field(min_length=1)

    @field_validator("id")
    @classmethod
    def _validate_id(cls, value: str) -> str:
        _require_identifier(value, "model id")
        return value

    @field_validator("url")
    @classmethod
    def _validate_url(cls, value: str) -> str:
        return _require_https_url(value, "model URL")

    @field_validator("sha256")
    @classmethod
    def _validate_sha256(cls, value: str) -> str:
        if _SHA256_PATTERN.fullmatch(value) is None:
            raise ValueError("SHA256 must be a 64-character lowercase hexadecimal value")
        return value

    @field_validator("path")
    @classmethod
    def _validate_path(cls, value: str) -> str:
        _require_relative_path(value, "model path")
        return value


class SourceSpec(_StrictManifestModel):
    kind: Literal["external", "workspace"]
    source_dir: str = Field(min_length=1)
    url: str | None = None
    commit: str | None = None
    submodules: bool | None = None

    @field_validator("source_dir")
    @classmethod
    def _validate_source_dir(cls, value: str) -> str:
        _require_relative_path(value, "source_dir")
        return value

    @field_validator("url")
    @classmethod
    def _validate_url(cls, value: str | None) -> str | None:
        if value is not None:
            return _require_https_url(value, "source URL")
        return value

    @field_validator("commit")
    @classmethod
    def _validate_commit(cls, value: str | None) -> str | None:
        if value is not None and _COMMIT_PATTERN.fullmatch(value) is None:
            raise ValueError("commit must be a 40-character lowercase hexadecimal value")
        return value

    @model_validator(mode="after")
    def _validate_kind_contract(self) -> SourceSpec:
        if self.kind == "external":
            if self.url is None:
                raise ValueError("external source requires url")
            if self.commit is None:
                raise ValueError("external source requires commit")
            if self.submodules is None:
                raise ValueError("external source requires submodules")
            return self

        if self.url is not None or self.commit is not None or self.submodules is not None:
            raise ValueError("workspace source forbids remote fields url, commit, and submodules")
        return self


class BuildSpec(_StrictManifestModel):
    target: str = Field(min_length=1)
    configure_argv: list[str]
    build_argv: list[str] = Field(min_length=1)
    build_dir: str = Field(min_length=1)
    artifact: str = Field(min_length=1)

    @field_validator("configure_argv", "build_argv")
    @classmethod
    def _validate_argv(cls, value: list[str]) -> list[str]:
        if any(not argument for argument in value):
            raise ValueError("build argv entries must not be empty")
        return value

    @field_validator("build_dir", "artifact")
    @classmethod
    def _validate_paths(cls, value: str, info) -> str:
        _require_relative_path(value, info.field_name)
        return value


class ProbeSpec(_StrictManifestModel):
    path: str = Field(min_length=1)
    timeout_seconds: int = Field(gt=0)

    @field_validator("path")
    @classmethod
    def _validate_path(cls, value: str) -> str:
        if not value.startswith("/") or value.startswith("//"):
            raise ValueError("probe path must start with exactly one slash")
        parsed = urlsplit(value)
        if parsed.scheme or parsed.netloc or parsed.fragment:
            raise ValueError("probe path must be an HTTP path without scheme, host, or fragment")
        return value


class CommandLimits(_StrictManifestModel):
    max_output_bytes: int = Field(gt=0)
    max_concurrency: int = Field(gt=0)
    max_width: int | None = Field(default=None, gt=0)
    max_height: int | None = Field(default=None, gt=0)
    max_steps: int | None = Field(default=None, gt=0)
    max_seconds: float | None = Field(
        default=None,
        gt=0,
        le=_F32_MAX,
        allow_inf_nan=False,
    )


class RuntimeSpec(_StrictManifestModel):
    kind: Literal["service", "command"]
    argv: list[str] = Field(min_length=1)
    host: str | None = Field(default=None, min_length=1)
    port: int | None = Field(default=None, ge=1, le=65535)
    health: ProbeSpec | None = None
    readiness: ProbeSpec | None = None
    startup_timeout_seconds: int | None = Field(default=None, gt=0)
    shutdown_timeout_seconds: int | None = Field(default=None, gt=0)
    execution_timeout_seconds: int | None = Field(default=None, gt=0)
    request_timeout_seconds: int | None = Field(default=None, gt=0)
    limits: CommandLimits | None = None

    @field_validator("argv")
    @classmethod
    def _validate_argv(cls, value: list[str]) -> list[str]:
        if any(not argument for argument in value):
            raise ValueError("runtime argv entries must not be empty")
        return value

    @field_validator("host")
    @classmethod
    def _validate_host(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _require_service_host(value)

    @model_validator(mode="after")
    def _validate_kind_contract(self) -> RuntimeSpec:
        service_fields = (
            "host",
            "port",
            "health",
            "readiness",
            "startup_timeout_seconds",
            "shutdown_timeout_seconds",
        )
        if self.kind == "service":
            for field_name in service_fields:
                if getattr(self, field_name) is None:
                    raise ValueError(f"service runtime requires {field_name}")
            if self.execution_timeout_seconds is not None:
                raise ValueError("service runtime forbids execution_timeout_seconds")
            if self.limits is not None:
                raise ValueError("service runtime forbids limits")
            return self

        if self.execution_timeout_seconds is None:
            raise ValueError("command runtime requires execution_timeout_seconds")
        if self.request_timeout_seconds is not None:
            raise ValueError("command runtime forbids request_timeout_seconds")
        configured_service_fields = [
            field_name for field_name in service_fields if getattr(self, field_name) is not None
        ]
        if configured_service_fields:
            names = ", ".join(configured_service_fields)
            raise ValueError(f"command runtime forbids service fields: {names}")
        if self.limits is None:
            raise ValueError("command runtime requires limits")

        request_tokens = {
            token_name
            for argument in self.argv
            for _, token_name in _parse_argument(argument)
            if token_name in _REQUEST_TOKENS
        }
        numeric_limits = {
            "width": "max_width",
            "height": "max_height",
            "steps": "max_steps",
            "seconds": "max_seconds",
        }
        for token_name, field_name in numeric_limits.items():
            configured = getattr(self.limits, field_name) is not None
            used = token_name in request_tokens
            if used and not configured:
                raise ValueError(
                    f"request token {token_name} requires limits.{field_name}"
                )
            if configured and not used:
                raise ValueError(
                    f"limits.{field_name} requires a matching request token {token_name}"
                )
        return self


class ComponentSpec(_StrictManifestModel):
    enabled: bool
    platforms: list[str] = Field(min_length=1)
    dependencies: list[str]
    source: SourceSpec
    build: BuildSpec
    models: list[ModelAsset]
    runtime: RuntimeSpec

    @field_validator("platforms")
    @classmethod
    def _validate_platforms(cls, value: list[str]) -> list[str]:
        seen: set[str] = set()
        for platform_id in value:
            if platform_id not in _SUPPORTED_PLATFORMS:
                raise ValueError(f"unsupported platform {platform_id}")
            if platform_id in seen:
                raise ValueError(f"duplicate platform {platform_id}")
            seen.add(platform_id)
        return value

    @field_validator("dependencies")
    @classmethod
    def _validate_dependencies(cls, value: list[str]) -> list[str]:
        seen: set[str] = set()
        for dependency in value:
            _require_identifier(dependency, "dependency")
            if dependency in seen:
                raise ValueError(f"duplicate dependency {dependency}")
            seen.add(dependency)
        return value

    @model_validator(mode="after")
    def _validate_models_and_argv(self) -> ComponentSpec:
        model_ids: set[str] = set()
        model_paths: set[str] = set()
        for model in self.models:
            if model.id in model_ids:
                raise ValueError(f"duplicate model id {model.id}")
            if model.path in model_paths:
                raise ValueError(f"duplicate model path {model.path}")
            model_ids.add(model.id)
            model_paths.add(model.path)

        _validate_argv_tokens(self.build.configure_argv, set(), allow_request=False)
        _validate_argv_tokens(self.build.build_argv, set(), allow_request=False)
        _validate_argv_tokens(
            self.runtime.argv,
            model_ids,
            allow_request=self.runtime.kind == "command",
        )
        return self


class ComponentManifest(_StrictManifestModel):
    schema_version: int
    vendor_dir: str = Field(min_length=1)
    components: dict[str, ComponentSpec] = Field(min_length=1)

    @field_validator("schema_version")
    @classmethod
    def _validate_schema_version(cls, value: int) -> int:
        if value != 1:
            raise ValueError(f"unsupported component manifest schema_version {value}")
        return value

    @field_validator("vendor_dir")
    @classmethod
    def _validate_vendor_dir(cls, value: str) -> str:
        _require_relative_path(value, "vendor_dir")
        return value

    @field_validator("components")
    @classmethod
    def _validate_component_names(cls, value: dict[str, ComponentSpec]) -> dict[str, ComponentSpec]:
        for name in value:
            _require_identifier(name, "component name")
        return value

    @model_validator(mode="after")
    def _validate_graph(self) -> ComponentManifest:
        model_ids: dict[str, str] = {}
        model_paths: dict[str, str] = {}
        for name, component in self.components.items():
            for dependency in component.dependencies:
                if dependency == name:
                    raise ValueError(f"component {name} cannot depend on itself")
                dependency_spec = self.components.get(dependency)
                if dependency_spec is None:
                    raise ValueError(f"component {name} has unknown dependency {dependency}")
                if component.enabled and not dependency_spec.enabled:
                    raise ValueError(
                        f"enabled component {name} depends on disabled component {dependency}"
                    )
            for model in component.models:
                id_owner = model_ids.get(model.id)
                if id_owner is not None:
                    raise ValueError(
                        f"model id {model.id} is shared by components {id_owner} and {name}"
                    )
                model_ids[model.id] = name
                owner = model_paths.get(model.path)
                if owner is not None:
                    raise ValueError(
                        f"model path {model.path} is shared by components {owner} and {name}"
                    )
                model_paths[model.path] = name

        cycle = _dependency_cycle(self.components)
        if cycle is not None:
            raise ValueError(f"dependency cycle: {' -> '.join(cycle)}")
        return self

    def start_order(self) -> list[str]:
        enabled_names = {name for name, component in self.components.items() if component.enabled}
        indegree = {
            name: sum(
                dependency in enabled_names for dependency in self.components[name].dependencies
            )
            for name in enabled_names
        }
        dependents: dict[str, list[str]] = {name: [] for name in enabled_names}
        for name in enabled_names:
            for dependency in self.components[name].dependencies:
                if dependency in enabled_names:
                    dependents[dependency].append(name)

        ready: list[str] = []
        for name, count in indegree.items():
            if count == 0:
                heappush(ready, name)

        order: list[str] = []
        while ready:
            name = heappop(ready)
            order.append(name)
            for dependent in sorted(dependents[name]):
                indegree[dependent] -= 1
                if indegree[dependent] == 0:
                    heappush(ready, dependent)

        if len(order) != len(enabled_names):
            raise ValueError("enabled component dependency graph contains a cycle")
        return order


@dataclass(frozen=True)
class ResolvedComponent:
    name: str
    component: ComponentSpec
    root: Path
    vendor: Path
    source_dir: Path
    build_dir: Path
    artifact: Path
    models: Mapping[str, Path]

    def argv_tokens(self) -> Mapping[str, str]:
        values = {
            "root": str(self.root),
            "vendor": str(self.vendor),
            "source": str(self.source_dir),
            "build": str(self.build_dir),
            "artifact": str(self.artifact),
        }
        values.update({f"model:{model_id}": str(path) for model_id, path in self.models.items()})
        return MappingProxyType(values)


def load_component_manifest(path: str | Path) -> ComponentManifest:
    manifest_path = Path(path)
    try:
        source = manifest_path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"component manifest {manifest_path} is not valid UTF-8: {exc}") from exc

    try:
        raw_manifest = tomli.loads(source)
    except tomli.TOMLDecodeError as exc:
        raise ValueError(
            f"component manifest {manifest_path} contains invalid TOML: {exc}"
        ) from exc

    try:
        return ComponentManifest.model_validate(raw_manifest)
    except ValidationError as exc:
        details = _format_validation_errors(exc)
        raise ValueError(f"invalid component manifest {manifest_path}: {details}") from None


def current_platform() -> str:
    pair = (platform.system(), platform.machine())
    platform_id = {
        ("Darwin", "arm64"): "darwin-arm64",
        ("Darwin", "x86_64"): "darwin-x86_64",
        ("Linux", "x86_64"): "linux-x86_64",
    }.get(pair)
    if platform_id is None:
        raise ValueError(f"unsupported platform: {pair[0]}/{pair[1]}")
    return platform_id


def resolve_component_paths(
    root: str | Path,
    manifest: ComponentManifest,
    name: str,
) -> ResolvedComponent:
    component = manifest.components.get(name)
    if component is None:
        raise ValueError(f"unknown component {name}")

    resolved_root = Path(root).expanduser().resolve()
    vendor = _resolve_below(resolved_root, manifest.vendor_dir, "vendor_dir")
    source_base = vendor if component.source.kind == "external" else resolved_root
    build_base = vendor if component.source.kind == "external" else resolved_root
    source_dir = _resolve_below(source_base, component.source.source_dir, "source_dir")
    build_dir = _resolve_below(build_base, component.build.build_dir, "build_dir")
    artifact = _resolve_below(build_base, component.build.artifact, "artifact")
    models = MappingProxyType(
        {
            model.id: _resolve_below(vendor, model.path, f"model {model.id} path")
            for model in component.models
        }
    )
    return ResolvedComponent(
        name=name,
        component=component,
        root=resolved_root,
        vendor=vendor,
        source_dir=source_dir,
        build_dir=build_dir,
        artifact=artifact,
        models=models,
    )


def expand_argv(
    argv: Sequence[str],
    tokens: Mapping[str, str | Path],
) -> list[str]:
    declared: dict[str, str] = {}
    for name, value in tokens.items():
        if name not in _PATH_TOKENS and not _is_model_token(name):
            raise ValueError(f"invalid token declaration {name}")
        if not isinstance(value, (str, Path)):
            raise TypeError(f"token {name} value must be a string or Path")
        declared[name] = str(value)

    expanded: list[str] = []
    for argument in argv:
        if not isinstance(argument, str):
            raise TypeError("argv entries must be strings")
        pieces: list[str] = []
        for literal, token_name in _parse_argument(argument):
            pieces.append(literal)
            if token_name is None:
                continue
            if token_name in _REQUEST_TOKENS:
                pieces.append(f"{{{token_name}}}")
                continue
            if token_name not in _PATH_TOKENS and not _is_model_token(token_name):
                raise ValueError(f"unknown argv token {token_name}")
            value = declared.get(token_name)
            if value is None:
                raise ValueError(f"undeclared argv token {token_name}")
            pieces.append(value)
        expanded.append("".join(pieces))
    return expanded


def _require_identifier(value: str, label: str) -> None:
    if _IDENTIFIER_PATTERN.fullmatch(value) is None:
        raise ValueError(f"{label} must match {_IDENTIFIER_PATTERN.pattern}")


def _require_https_url(value: str, label: str) -> str:
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise ValueError(f"{label} must not contain ASCII control characters")
    try:
        parsed = _HTTP_URL_ADAPTER.validate_python(value, strict=True)
    except ValidationError:
        raise ValueError(f"{label} must be a valid absolute HTTPS URL") from None
    if parsed.scheme != "https":
        raise ValueError(f"{label} must use HTTPS")
    if parsed.host is None:
        raise ValueError(f"{label} must have a valid hostname")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError(f"{label} must not include user information")
    if parsed.fragment is not None:
        raise ValueError(f"{label} must not include a fragment")
    return str(parsed)


def _require_service_host(value: str) -> str:
    error = (
        "service host must be a valid IPv4 address, bare IPv6 address, "
        "or ASCII DNS hostname"
    )
    if (
        not value.isascii()
        or any(ord(character) <= 32 or ord(character) == 127 for character in value)
        or "%" in value
    ):
        raise ValueError(error)

    try:
        return str(ipaddress.ip_address(value))
    except ValueError:
        pass

    if any(character in value for character in "/@[]:"):
        raise ValueError(error)
    trailing_dot = value.endswith(".")
    hostname = value[:-1] if trailing_dot else value
    if (
        not hostname
        or len(hostname) > 253
        or ("." in hostname and all(character in "0123456789." for character in hostname))
        or any(_DNS_LABEL_PATTERN.fullmatch(label) is None for label in hostname.split("."))
    ):
        raise ValueError(error)
    normalized = hostname.lower()
    return f"{normalized}." if trailing_dot else normalized


def _format_validation_errors(error: ValidationError) -> str:
    details: list[str] = []
    for item in error.errors(include_input=False, include_url=False):
        location = ".".join(str(part) for part in item["loc"])
        message = item["msg"]
        details.append(f"{location}: {message}" if location else message)
    return "; ".join(details)


def _require_relative_path(value: str, label: str) -> None:
    if (
        value.startswith("/")
        or "\\" in value
        or any(part in {"", ".", ".."} for part in value.split("/"))
    ):
        raise ValueError(f"{label} must be a relative path without traversal")


def _resolve_below(base: Path, relative_path: str, label: str) -> Path:
    resolved_base = base.resolve()
    candidate = (resolved_base / relative_path).resolve()
    try:
        candidate.relative_to(resolved_base)
    except ValueError as exc:
        raise ValueError(f"{label} escapes {resolved_base}: {relative_path}") from exc
    return candidate


def _is_model_token(name: str) -> bool:
    if not name.startswith("model:"):
        return False
    model_id = name.removeprefix("model:")
    return _IDENTIFIER_PATTERN.fullmatch(model_id) is not None


def _parse_argument(argument: str) -> list[tuple[str, str | None]]:
    try:
        parsed = list(_FORMATTER.parse(argument))
    except ValueError as exc:
        raise ValueError(f"invalid argv template {argument!r}: {exc}") from exc

    parts: list[tuple[str, str | None]] = []
    for literal, field_name, format_spec, conversion in parsed:
        parts.append((literal, None))
        if field_name is None:
            continue
        if conversion is not None:
            raise ValueError(f"argv token {field_name} cannot use conversion")
        if field_name == "model" and format_spec:
            token_name = f"model:{format_spec}"
            if not _is_model_token(token_name):
                raise ValueError(f"invalid model argv token {token_name}")
        else:
            if format_spec:
                raise ValueError(f"argv token {field_name} cannot use a format specifier")
            token_name = field_name
        parts.append(("", token_name))
    return parts


def _validate_argv_tokens(
    argv: Sequence[str],
    model_ids: set[str],
    *,
    allow_request: bool,
) -> None:
    for argument in argv:
        for _, token_name in _parse_argument(argument):
            if token_name is None or token_name in _PATH_TOKENS:
                continue
            if token_name in _REQUEST_TOKENS:
                if not allow_request:
                    raise ValueError(f"request token {token_name} requires command runtime")
                continue
            if _is_model_token(token_name):
                model_id = token_name.removeprefix("model:")
                if model_id not in model_ids:
                    raise ValueError(f"undeclared model token {token_name}")
                continue
            raise ValueError(f"unknown argv token {token_name}")


def _dependency_cycle(components: Mapping[str, ComponentSpec]) -> list[str] | None:
    state: dict[str, int] = {name: 0 for name in components}
    stack: list[str] = []
    stack_positions: dict[str, int] = {}

    def visit(name: str) -> list[str] | None:
        state[name] = 1
        stack_positions[name] = len(stack)
        stack.append(name)
        for dependency in sorted(components[name].dependencies):
            if state[dependency] == 0:
                cycle = visit(dependency)
                if cycle is not None:
                    return cycle
            elif state[dependency] == 1:
                return stack[stack_positions[dependency] :] + [dependency]
        stack.pop()
        stack_positions.pop(name)
        state[name] = 2
        return None

    for name in sorted(components):
        if state[name] == 0:
            cycle = visit(name)
            if cycle is not None:
                return cycle
    return None
