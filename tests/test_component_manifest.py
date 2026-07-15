from __future__ import annotations

import re
from copy import deepcopy
from pathlib import Path

import pytest
from pydantic import ValidationError
from yts_core import components
from yts_core.components import (
    ComponentManifest,
    expand_argv,
    load_component_manifest,
    resolve_component_paths,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = REPO_ROOT / "desktop" / "components.toml"


def _external_component(*, enabled: bool = True) -> dict[str, object]:
    return {
        "enabled": enabled,
        "platforms": ["darwin-arm64"],
        "dependencies": [],
        "source": {
            "kind": "external",
            "url": "https://example.test/source.git",
            "commit": "a" * 40,
            "submodules": False,
            "source_dir": "source",
        },
        "build": {
            "target": "example-server",
            "configure_argv": ["cmake", "-S", "{source}", "-B", "{build}"],
            "build_argv": ["cmake", "--build", "{build}"],
            "build_dir": "source/build",
            "artifact": "source/build/example-server",
        },
        "models": [
            {
                "id": "example",
                "url": "https://example.test/example.gguf",
                "size": 1,
                "sha256": "b" * 64,
                "path": "models/example.gguf",
            }
        ],
        "runtime": {
            "kind": "service",
            "argv": ["{artifact}", "--model", "{model:example}"],
            "host": "127.0.0.1",
            "port": 8080,
            "health": {"path": "/health", "timeout_seconds": 2},
            "readiness": {"path": "/ready", "timeout_seconds": 2},
            "startup_timeout_seconds": 60,
            "shutdown_timeout_seconds": 10,
        },
    }


def _workspace_component(*, dependencies: list[str] | None = None) -> dict[str, object]:
    return {
        "enabled": True,
        "platforms": ["darwin-arm64"],
        "dependencies": [] if dependencies is None else dependencies,
        "source": {
            "kind": "workspace",
            "source_dir": "desktop/example",
        },
        "build": {
            "target": "example",
            "configure_argv": [],
            "build_argv": ["cargo", "build", "--release"],
            "build_dir": "desktop/example/target/release",
            "artifact": "desktop/example/target/release/example",
        },
        "models": [],
        "runtime": {
            "kind": "command",
            "argv": ["{artifact}", "--prompt", "{prompt}", "--out", "{out}"],
            "execution_timeout_seconds": 30,
            "limits": {"max_output_bytes": 1024, "max_concurrency": 1},
        },
    }


def _manifest_data(
    components_data: dict[str, dict[str, object]] | None = None,
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "vendor_dir": "desktop/vendor",
        "components": components_data or {"example": _external_component()},
    }


def test_real_manifest_records_audited_component_facts() -> None:
    manifest = load_component_manifest(MANIFEST_PATH)

    assert manifest.schema_version == 1
    assert manifest.vendor_dir == "desktop/vendor"
    assert list(manifest.components) == [
        "llama",
        "stable-diffusion",
        "acestep",
        "infer-gateway",
    ]
    assert manifest.components["llama"].source.commit == (
        "72874f559c598b8f89fbb24864868337cf5afb4c"
    )
    assert manifest.components["stable-diffusion"].source.commit == (
        "e790073e1c311feb1ff423ba910f398df01bb60e"
    )
    assert "-DSD_METAL=ON" in manifest.components["stable-diffusion"].build.configure_argv
    assert manifest.components["acestep"].source.commit == (
        "da5bc90f8664c242a7bb42eaa0c778762c02c6e3"
    )
    assert manifest.components["acestep"].enabled is False
    assert manifest.components["infer-gateway"].source.kind == "workspace"
    assert manifest.components["infer-gateway"].dependencies == [
        "llama",
        "stable-diffusion",
    ]
    assert manifest.start_order() == ["llama", "stable-diffusion", "infer-gateway"]


def test_real_manifest_records_audited_runtime_argv() -> None:
    manifest = load_component_manifest(MANIFEST_PATH)

    llama = manifest.components["llama"]
    assert len(llama.models) == 1
    llama_model_id = llama.models[0].id
    assert llama.runtime.argv == [
        "{artifact}",
        "--host",
        "127.0.0.1",
        "--port",
        "8080",
        "--model",
        "{model:qwen}",
        "--alias",
        llama_model_id,
    ]
    assert manifest.components["stable-diffusion"].runtime.argv == [
        "{artifact}",
        "--diffusion-model",
        "{model:flux}",
        "--vae",
        "{model:vae}",
        "--clip_l",
        "{model:clip_l}",
        "--t5xxl",
        "{model:t5xxl}",
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
    ]
    assert manifest.components["acestep"].runtime.argv == [
        "{artifact}",
        "--host",
        "127.0.0.1",
        "--port",
        "8085",
        "--models",
        "{vendor}/acestep-models",
    ]


def test_real_manifest_records_runtime_resource_limits() -> None:
    manifest = load_component_manifest(MANIFEST_PATH)

    image_runtime = manifest.components["stable-diffusion"].runtime
    assert image_runtime.limits is not None
    assert image_runtime.limits.max_output_bytes == 67_108_864
    assert image_runtime.limits.max_width == 2_048
    assert image_runtime.limits.max_height == 2_048
    assert image_runtime.limits.max_steps == 100
    assert image_runtime.limits.max_seconds is None
    assert image_runtime.limits.max_concurrency == 1

    gateway_runtime = manifest.components["infer-gateway"].runtime
    assert gateway_runtime.request_timeout_seconds == 120


@pytest.mark.parametrize(
    ("component_name", "model_id", "expected"),
    [
        (
            "llama",
            "qwen",
            (
                "https://huggingface.co/bartowski/Qwen2.5-7B-Instruct-GGUF/resolve/8911e8a47f92bac19d6f5c64a2e2095bd2f7d031/Qwen2.5-7B-Instruct-Q4_K_M.gguf?download=true",
                "llm-models/Qwen2.5-7B-Instruct-Q4_K_M.gguf",
                4_683_074_240,
                "65b8fcd92af6b4fefa935c625d1ac27ea29dcb6ee14589c55a8f115ceaaa1423",
            ),
        ),
        (
            "stable-diffusion",
            "flux",
            (
                "https://huggingface.co/Green-Sky/flux.1-schnell-GGUF/resolve/646b4e7a585efbfeb5b57132def0395df5756854/flux1-schnell-q4_k.gguf?download=true",
                "sd-models/flux1-schnell-q4_k.gguf",
                6_884_606_880,
                "0c7148f5b7e47edaea99a6cec058a8e2bc8ded52e3bba55519c81aa1a38df5d3",
            ),
        ),
        (
            "stable-diffusion",
            "vae",
            (
                "https://huggingface.co/Green-Sky/flux.1-schnell-GGUF/resolve/646b4e7a585efbfeb5b57132def0395df5756854/ae-f16.gguf?download=true",
                "sd-models/ae-f16.gguf",
                167_656_704,
                "1bed7b05318709e46a8cb9accc211168fc7f0b61ab594661860bbfe4d785cc46",
            ),
        ),
        (
            "stable-diffusion",
            "clip_l",
            (
                "https://huggingface.co/Green-Sky/flux.1-schnell-GGUF/resolve/646b4e7a585efbfeb5b57132def0395df5756854/clip_l-q8_0.gguf?download=true",
                "sd-models/clip_l-q8_0.gguf",
                130_769_600,
                "59cbe002c3e75d2b89d38787e81d12fb4e512fd76176884c470737ad87a1d309",
            ),
        ),
        (
            "stable-diffusion",
            "t5xxl",
            (
                "https://huggingface.co/Green-Sky/flux.1-schnell-GGUF/resolve/646b4e7a585efbfeb5b57132def0395df5756854/t5xxl_q4_k.gguf?download=true",
                "sd-models/t5xxl_q4_k.gguf",
                2_752_844_256,
                "b235e9a108ccc1803c576464e937cf5ec4d8eb34d83776e5199450400d4e0bcb",
            ),
        ),
        (
            "acestep",
            "qwen3-embedding",
            (
                "https://huggingface.co/Serveurperso/ACE-Step-1.5-GGUF/resolve/9b3707625776cc4cf775e9b12ab82f9fe48335ff/Qwen3-Embedding-0.6B-Q8_0.gguf?download=true",
                "acestep-models/Qwen3-Embedding-0.6B-Q8_0.gguf",
                784_144_960,
                "972f23255e46adfe744a0eb9a0039f3c63988f65753b0968d776e8b27168c321",
            ),
        ),
        (
            "acestep",
            "acestep-lm",
            (
                "https://huggingface.co/Serveurperso/ACE-Step-1.5-GGUF/resolve/9b3707625776cc4cf775e9b12ab82f9fe48335ff/acestep-5Hz-lm-0.6B-Q8_0.gguf?download=true",
                "acestep-models/acestep-5Hz-lm-0.6B-Q8_0.gguf",
                709_846_656,
                "bdaf9e292d4470f31c19cafeaca1b74936a114667e3a85e5d33b65247e9908ec",
            ),
        ),
        (
            "acestep",
            "acestep-turbo",
            (
                "https://huggingface.co/Serveurperso/ACE-Step-1.5-GGUF/resolve/9b3707625776cc4cf775e9b12ab82f9fe48335ff/acestep-v15-turbo-Q8_0.gguf?download=true",
                "acestep-models/acestep-v15-turbo-Q8_0.gguf",
                2_549_528_000,
                "288f708a61cfc241013a98a62f98ba331f83fe34d0d3559acdd9b0f6a2f7cd6b",
            ),
        ),
        (
            "acestep",
            "acestep-vae",
            (
                "https://huggingface.co/Serveurperso/ACE-Step-1.5-GGUF/resolve/9b3707625776cc4cf775e9b12ab82f9fe48335ff/vae-BF16.gguf?download=true",
                "acestep-models/vae-BF16.gguf",
                337_420_928,
                "0599862ac5d15cd308e1d2e368373aea6c02e25ebd1737ad4a4562a0901b0ef8",
            ),
        ),
    ],
)
def test_real_manifest_records_exact_model_integrity(
    component_name: str,
    model_id: str,
    expected: tuple[str, str, int, str],
) -> None:
    manifest = load_component_manifest(MANIFEST_PATH)
    model = next(
        model for model in manifest.components[component_name].models if model.id == model_id
    )

    url, path, size, sha256 = expected
    assert model.url == url
    assert model.path == path
    assert model.size == size
    assert model.sha256 == sha256


def test_real_manifest_pins_hugging_face_models_to_immutable_revisions() -> None:
    manifest = load_component_manifest(MANIFEST_PATH)
    immutable_revision = re.compile(r"/resolve/[0-9a-f]{40}/")

    for component in manifest.components.values():
        for model in component.models:
            if model.url.startswith("https://huggingface.co/"):
                assert immutable_revision.search(model.url) is not None, model.url


def test_models_forbid_unknown_fields_and_type_coercion() -> None:
    data = _manifest_data()
    data["unknown"] = "value"

    with pytest.raises(ValidationError, match="extra_forbidden"):
        ComponentManifest.model_validate(data)

    data = _manifest_data()
    data["schema_version"] = "1"
    with pytest.raises(ValidationError, match="int_type"):
        ComponentManifest.model_validate(data)


def test_component_requires_explicit_boolean_enabled() -> None:
    component = _external_component()
    component.pop("enabled")

    with pytest.raises(ValidationError, match=r"components\.example\.enabled"):
        ComponentManifest.model_validate(_manifest_data({"example": component}))

    component["enabled"] = "true"
    with pytest.raises(ValidationError, match="bool_type"):
        ComponentManifest.model_validate(_manifest_data({"example": component}))


@pytest.mark.parametrize(
    ("field", "value", "error"),
    [
        ("url", "http://example.test/source.git", "HTTPS"),
        ("commit", "a" * 39, "40-character lowercase"),
        ("commit", "A" * 40, "40-character lowercase"),
        ("source_dir", "../source", "relative path without traversal"),
    ],
)
def test_external_source_rejects_invalid_remote_contract(
    field: str,
    value: object,
    error: str,
) -> None:
    component = _external_component()
    source = component["source"]
    assert isinstance(source, dict)
    source[field] = value

    with pytest.raises(ValidationError, match=error):
        ComponentManifest.model_validate(_manifest_data({"example": component}))


def test_external_source_requires_explicit_submodule_policy() -> None:
    component = _external_component()
    source = component["source"]
    assert isinstance(source, dict)
    source.pop("submodules")

    with pytest.raises(ValidationError, match="external source requires submodules"):
        ComponentManifest.model_validate(_manifest_data({"example": component}))


@pytest.mark.parametrize("remote_field", ["url", "commit", "submodules"])
def test_workspace_source_forbids_remote_fields(remote_field: str) -> None:
    component = _workspace_component()
    source = component["source"]
    assert isinstance(source, dict)
    source[remote_field] = {
        "url": "https://example.test/source.git",
        "commit": "a" * 40,
        "submodules": False,
    }[remote_field]

    with pytest.raises(ValidationError, match=r"workspace source forbids remote fields"):
        ComponentManifest.model_validate(_manifest_data({"example": component}))


@pytest.mark.parametrize("argv_field", ["configure_argv", "build_argv"])
def test_build_commands_require_structured_argv(argv_field: str) -> None:
    component = _external_component()
    build = component["build"]
    assert isinstance(build, dict)
    build[argv_field] = "cmake --build source/build"

    with pytest.raises(ValidationError, match="list_type"):
        ComponentManifest.model_validate(_manifest_data({"example": component}))


def test_runtime_rejects_shell_command_strings() -> None:
    component = _external_component()
    runtime = component["runtime"]
    assert isinstance(runtime, dict)
    runtime["argv"] = "example-server --port 8080"

    with pytest.raises(ValidationError, match="list_type"):
        ComponentManifest.model_validate(_manifest_data({"example": component}))


@pytest.mark.parametrize(
    "missing_field",
    [
        "host",
        "port",
        "health",
        "readiness",
        "startup_timeout_seconds",
        "shutdown_timeout_seconds",
    ],
)
def test_service_runtime_requires_network_and_timeout_fields(missing_field: str) -> None:
    component = _external_component()
    runtime = component["runtime"]
    assert isinstance(runtime, dict)
    runtime.pop(missing_field)

    with pytest.raises(ValidationError, match=rf"service runtime requires {missing_field}"):
        ComponentManifest.model_validate(_manifest_data({"example": component}))


@pytest.mark.parametrize(
    "host",
    [
        pytest.param("bad host", id="whitespace"),
        pytest.param("http://example.test", id="scheme"),
        pytest.param("user@example.test", id="userinfo"),
        pytest.param("example.test:8080", id="port"),
        pytest.param("[::1]", id="bracketed-ipv6"),
        pytest.param("2001:db8::1]", id="unbalanced-bracket"),
        pytest.param("bad..example", id="empty-label"),
        pytest.param("-bad.example", id="leading-hyphen"),
        pytest.param("bad-.example", id="trailing-hyphen"),
        pytest.param("bad_example", id="invalid-label-character"),
        pytest.param("example.test\x01", id="control-character"),
        pytest.param("example.\u6d4b\u8bd5", id="non-ascii"),
    ],
)
def test_service_runtime_rejects_invalid_host(host: str) -> None:
    component = _external_component()
    runtime = component["runtime"]
    assert isinstance(runtime, dict)
    runtime["host"] = host

    with pytest.raises(ValidationError, match="service host"):
        ComponentManifest.model_validate(_manifest_data({"example": component}))


@pytest.mark.parametrize(
    ("host", "expected"),
    [
        ("127.0.0.1", "127.0.0.1"),
        ("2001:0DB8:0:0:0:0:0:1", "2001:db8::1"),
        ("LOCALHOST", "localhost"),
        ("API.Example.TEST", "api.example.test"),
    ],
)
def test_service_runtime_normalizes_valid_host(host: str, expected: str) -> None:
    component = _external_component()
    runtime = component["runtime"]
    assert isinstance(runtime, dict)
    runtime["host"] = host

    manifest = ComponentManifest.model_validate(_manifest_data({"example": component}))

    assert manifest.components["example"].runtime.host == expected


def test_load_manifest_rejects_invalid_service_host(tmp_path: Path) -> None:
    source = MANIFEST_PATH.read_text(encoding="utf-8")
    original = 'host = "127.0.0.1"'
    assert original in source
    invalid_path = tmp_path / "invalid-host.toml"
    invalid_path.write_text(
        source.replace(original, 'host = "bad host"', 1),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=r"runtime\.host.*service host"):
        load_component_manifest(invalid_path)


def test_command_runtime_requires_execution_timeout_and_forbids_service_fields() -> None:
    component = _workspace_component()
    runtime = component["runtime"]
    assert isinstance(runtime, dict)
    runtime.pop("execution_timeout_seconds")

    with pytest.raises(ValidationError, match="command runtime requires execution_timeout_seconds"):
        ComponentManifest.model_validate(_manifest_data({"example": component}))

    runtime["execution_timeout_seconds"] = 30
    runtime["port"] = 8080
    with pytest.raises(ValidationError, match="command runtime forbids service fields"):
        ComponentManifest.model_validate(_manifest_data({"example": component}))


def test_command_runtime_requires_limits() -> None:
    component = _workspace_component()
    runtime = component["runtime"]
    assert isinstance(runtime, dict)
    runtime.pop("limits")

    with pytest.raises(ValidationError, match="command runtime requires limits"):
        ComponentManifest.model_validate(_manifest_data({"example": component}))


def test_command_limits_require_max_output_bytes() -> None:
    component = _workspace_component()
    runtime = component["runtime"]
    assert isinstance(runtime, dict)
    runtime["limits"] = {}

    with pytest.raises(ValidationError, match="max_output_bytes"):
        ComponentManifest.model_validate(_manifest_data({"example": component}))


def test_command_limits_require_max_concurrency() -> None:
    component = _workspace_component()
    runtime = component["runtime"]
    assert isinstance(runtime, dict)
    limits = runtime["limits"]
    assert isinstance(limits, dict)
    limits.pop("max_concurrency")

    with pytest.raises(ValidationError, match="max_concurrency"):
        ComponentManifest.model_validate(_manifest_data({"example": component}))

    limits["max_concurrency"] = 0
    with pytest.raises(ValidationError, match="greater than 0"):
        ComponentManifest.model_validate(_manifest_data({"example": component}))


@pytest.mark.parametrize(
    "max_seconds",
    [
        pytest.param(float("inf"), id="infinite"),
        pytest.param(3.402823466385289e38, id="greater-than-f32-max"),
    ],
)
def test_command_limits_reject_max_seconds_outside_f32_range(max_seconds: float) -> None:
    component = _workspace_component()
    runtime = component["runtime"]
    assert isinstance(runtime, dict)
    argv = runtime["argv"]
    assert isinstance(argv, list)
    argv.extend(["--seconds", "{seconds}"])
    runtime["limits"] = {
        "max_output_bytes": 1024,
        "max_concurrency": 1,
        "max_seconds": max_seconds,
    }

    with pytest.raises(ValidationError, match="max_seconds"):
        ComponentManifest.model_validate(_manifest_data({"example": component}))


@pytest.mark.parametrize("max_seconds", [0.25, 3.4028234663852886e38])
def test_command_limits_accept_finite_positive_max_seconds(max_seconds: float) -> None:
    component = _workspace_component()
    runtime = component["runtime"]
    assert isinstance(runtime, dict)
    argv = runtime["argv"]
    assert isinstance(argv, list)
    argv.extend(["--seconds", "{seconds}"])
    runtime["limits"] = {
        "max_output_bytes": 1024,
        "max_concurrency": 1,
        "max_seconds": max_seconds,
    }

    manifest = ComponentManifest.model_validate(_manifest_data({"example": component}))

    assert manifest.components["example"].runtime.limits.max_seconds == max_seconds


@pytest.mark.parametrize(
    ("token", "limit_field"),
    [
        ("width", "max_width"),
        ("height", "max_height"),
        ("steps", "max_steps"),
        ("seconds", "max_seconds"),
    ],
)
def test_command_limits_require_numeric_token_limits(
    token: str,
    limit_field: str,
) -> None:
    component = _workspace_component()
    runtime = component["runtime"]
    assert isinstance(runtime, dict)
    argv = runtime["argv"]
    assert isinstance(argv, list)
    argv.extend([f"--{token}", f"{{{token}}}"])
    runtime["limits"] = {"max_output_bytes": 1024, "max_concurrency": 1}

    with pytest.raises(ValidationError, match=rf"{token}.*{limit_field}"):
        ComponentManifest.model_validate(_manifest_data({"example": component}))


@pytest.mark.parametrize(
    "limit_field",
    ["max_width", "max_height", "max_steps", "max_seconds"],
)
def test_command_limits_forbid_unused_numeric_token_limits(limit_field: str) -> None:
    component = _workspace_component()
    runtime = component["runtime"]
    assert isinstance(runtime, dict)
    runtime["limits"] = {
        "max_output_bytes": 1024,
        "max_concurrency": 1,
        limit_field: 10,
    }

    with pytest.raises(ValidationError, match=rf"{limit_field}.*matching request token"):
        ComponentManifest.model_validate(_manifest_data({"example": component}))


def test_command_runtime_accepts_complete_limits() -> None:
    component = _workspace_component()
    runtime = component["runtime"]
    assert isinstance(runtime, dict)
    runtime["limits"] = {"max_output_bytes": 1024, "max_concurrency": 1}

    manifest = ComponentManifest.model_validate(_manifest_data({"example": component}))

    assert manifest.components["example"].runtime.limits.max_output_bytes == 1024


def test_service_runtime_allows_request_timeout_and_forbids_limits() -> None:
    component = _external_component()
    runtime = component["runtime"]
    assert isinstance(runtime, dict)
    runtime["request_timeout_seconds"] = 120

    manifest = ComponentManifest.model_validate(_manifest_data({"example": component}))
    assert manifest.components["example"].runtime.request_timeout_seconds == 120

    runtime["limits"] = {"max_output_bytes": 1024, "max_concurrency": 1}
    with pytest.raises(ValidationError, match="service runtime forbids limits"):
        ComponentManifest.model_validate(_manifest_data({"example": component}))


def test_command_runtime_forbids_request_timeout() -> None:
    component = _workspace_component()
    runtime = component["runtime"]
    assert isinstance(runtime, dict)
    runtime["limits"] = {"max_output_bytes": 1024, "max_concurrency": 1}
    runtime["request_timeout_seconds"] = 120

    with pytest.raises(ValidationError, match="command runtime forbids request_timeout_seconds"):
        ComponentManifest.model_validate(_manifest_data({"example": component}))


@pytest.mark.parametrize(
    ("field", "value", "error"),
    [
        ("url", "http://example.test/example.gguf", "HTTPS"),
        ("size", 0, "greater than 0"),
        ("sha256", "b" * 63, "64-character lowercase"),
        ("sha256", "B" * 64, "64-character lowercase"),
    ],
)
def test_model_assets_require_exact_integrity_fields(
    field: str,
    value: object,
    error: str,
) -> None:
    component = _external_component()
    models = component["models"]
    assert isinstance(models, list)
    model = models[0]
    assert isinstance(model, dict)
    model[field] = value

    with pytest.raises(ValidationError, match=error):
        ComponentManifest.model_validate(_manifest_data({"example": component}))


@pytest.mark.parametrize("target", ["source", "model"])
@pytest.mark.parametrize(
    ("url", "error"),
    [
        pytest.param("https://@/a", "URL", id="empty-host"),
        pytest.param("https://example.test:bad/a", "URL", id="invalid-port"),
        pytest.param(
            "https://user:password@example.test/a",
            "user information",
            id="userinfo",
        ),
        pytest.param("https://example.test/a#fragment", "fragment", id="fragment"),
        pytest.param("https://example.test/a\x01b", "control", id="ascii-control"),
    ],
)
def test_remote_urls_reject_malformed_or_unsafe_values(
    target: str,
    url: str,
    error: str,
) -> None:
    component = _external_component()
    if target == "source":
        source = component["source"]
        assert isinstance(source, dict)
        source["url"] = url
    else:
        models = component["models"]
        assert isinstance(models, list)
        model = models[0]
        assert isinstance(model, dict)
        model["url"] = url

    with pytest.raises(ValidationError, match=error):
        ComponentManifest.model_validate(_manifest_data({"example": component}))


def test_load_manifest_redacts_user_information_from_url_errors(tmp_path: Path) -> None:
    original_url = "https://github.com/ggml-org/llama.cpp.git"
    credential_url = "https://manifest-user:private-password@example.test/source.git"
    source = MANIFEST_PATH.read_text(encoding="utf-8")
    assert original_url in source
    credential_path = tmp_path / "credential.toml"
    credential_path.write_text(source.replace(original_url, credential_url), encoding="utf-8")

    with pytest.raises(ValueError, match=r"components\.llama\.source\.url") as error:
        load_component_manifest(credential_path)

    message = str(error.value)
    assert "manifest-user" not in message
    assert "private-password" not in message


@pytest.mark.parametrize("target", ["source", "model"])
def test_remote_urls_are_stored_as_canonical_strings(target: str) -> None:
    component = _external_component()
    if target == "source":
        source = component["source"]
        assert isinstance(source, dict)
        source["url"] = "HTTPS://EXAMPLE.TEST/source.git"
    else:
        models = component["models"]
        assert isinstance(models, list)
        model = models[0]
        assert isinstance(model, dict)
        model["url"] = "HTTPS://EXAMPLE.TEST/example.gguf"

    manifest = ComponentManifest.model_validate(_manifest_data({"example": component}))
    if target == "source":
        assert manifest.components["example"].source.url == "https://example.test/source.git"
    else:
        assert manifest.components["example"].models[0].url == ("https://example.test/example.gguf")


@pytest.mark.parametrize("duplicate_field", ["id", "path"])
def test_component_rejects_duplicate_model_ids_and_paths(duplicate_field: str) -> None:
    component = _external_component()
    models = component["models"]
    assert isinstance(models, list)
    duplicate = deepcopy(models[0])
    duplicate["id"] = "second"
    duplicate["path"] = "models/second.gguf"
    duplicate[duplicate_field] = models[0][duplicate_field]
    models.append(duplicate)

    with pytest.raises(ValidationError, match=f"duplicate model {duplicate_field}"):
        ComponentManifest.model_validate(_manifest_data({"example": component}))


def test_manifest_rejects_model_ids_and_paths_shared_by_components() -> None:
    first = _external_component()
    second = _external_component()
    second_models = second["models"]
    assert isinstance(second_models, list)
    second_model = second_models[0]
    assert isinstance(second_model, dict)
    second_model["path"] = "models/second.gguf"

    with pytest.raises(ValidationError, match=r"model id example.*first.*second"):
        ComponentManifest.model_validate(_manifest_data({"first": first, "second": second}))

    second_model["id"] = "second"
    second_model["path"] = "models/example.gguf"
    second_runtime = second["runtime"]
    assert isinstance(second_runtime, dict)
    second_runtime["argv"] = ["{artifact}", "--model", "{model:second}"]
    with pytest.raises(ValidationError, match=r"model path models/example.gguf.*first.*second"):
        ComponentManifest.model_validate(_manifest_data({"first": first, "second": second}))


def test_manifest_rejects_unknown_and_self_dependencies() -> None:
    component = _external_component()
    component["dependencies"] = ["missing"]
    with pytest.raises(ValidationError, match="unknown dependency missing"):
        ComponentManifest.model_validate(_manifest_data({"example": component}))

    component["dependencies"] = ["example"]
    with pytest.raises(ValidationError, match="cannot depend on itself"):
        ComponentManifest.model_validate(_manifest_data({"example": component}))


def test_manifest_rejects_dependency_cycles() -> None:
    first = _workspace_component(dependencies=["second"])
    second = _workspace_component(dependencies=["first"])

    with pytest.raises(ValidationError, match=r"dependency cycle.*first.*second"):
        ComponentManifest.model_validate(_manifest_data({"first": first, "second": second}))


def test_enabled_component_cannot_depend_on_disabled_component() -> None:
    disabled = _external_component(enabled=False)
    enabled = _workspace_component(dependencies=["disabled"])

    with pytest.raises(ValidationError, match=r"enabled component enabled.*disabled component"):
        ComponentManifest.model_validate(_manifest_data({"disabled": disabled, "enabled": enabled}))


def test_manifest_rejects_unknown_and_duplicate_platforms() -> None:
    component = _external_component()
    component["platforms"] = ["windows-x86_64"]
    with pytest.raises(ValidationError, match="unsupported platform windows-x86_64"):
        ComponentManifest.model_validate(_manifest_data({"example": component}))

    component["platforms"] = ["darwin-arm64", "darwin-arm64"]
    with pytest.raises(ValidationError, match="duplicate platform darwin-arm64"):
        ComponentManifest.model_validate(_manifest_data({"example": component}))


def test_topological_start_order_is_deterministic_and_enabled_only() -> None:
    disabled = _external_component(enabled=False)
    alpha = _workspace_component()
    beta = _workspace_component()
    final = _workspace_component(dependencies=["alpha", "beta"])
    manifest = ComponentManifest.model_validate(
        _manifest_data(
            {
                "final": final,
                "beta": beta,
                "disabled": disabled,
                "alpha": alpha,
            }
        )
    )

    assert manifest.start_order() == ["alpha", "beta", "final"]


@pytest.mark.parametrize(
    ("system", "machine", "expected"),
    [
        ("Darwin", "arm64", "darwin-arm64"),
        ("Darwin", "x86_64", "darwin-x86_64"),
        ("Linux", "x86_64", "linux-x86_64"),
    ],
)
def test_current_platform_maps_supported_pairs(
    monkeypatch: pytest.MonkeyPatch,
    system: str,
    machine: str,
    expected: str,
) -> None:
    monkeypatch.setattr(components.platform, "system", lambda: system)
    monkeypatch.setattr(components.platform, "machine", lambda: machine)

    assert components.current_platform() == expected


def test_current_platform_rejects_unsupported_pair(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(components.platform, "system", lambda: "Linux")
    monkeypatch.setattr(components.platform, "machine", lambda: "aarch64")

    with pytest.raises(ValueError, match=r"unsupported platform: Linux/aarch64"):
        components.current_platform()


def test_load_manifest_reports_path_for_toml_and_validation_errors(tmp_path: Path) -> None:
    duplicate_path = tmp_path / "duplicate.toml"
    duplicate_path.write_text(
        """
schema_version = 1
vendor_dir = "desktop/vendor"
[components.example]
enabled = true
[components.example]
enabled = false
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=rf"{duplicate_path}.*TOML"):
        load_component_manifest(duplicate_path)

    invalid_path = tmp_path / "invalid.toml"
    invalid_path.write_text(
        'schema_version = 1\nvendor_dir = "desktop/vendor"\n[components.example]\n',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match=re.escape(str(invalid_path))) as error:
        load_component_manifest(invalid_path)
    assert "components.example.enabled" in str(error.value)


def test_resolve_component_paths_uses_root_and_vendor_bases(tmp_path: Path) -> None:
    external = _external_component()
    workspace = _workspace_component()
    manifest = ComponentManifest.model_validate(
        _manifest_data({"external": external, "workspace": workspace})
    )

    resolved_external = resolve_component_paths(tmp_path, manifest, "external")
    assert resolved_external.root == tmp_path.resolve()
    assert resolved_external.vendor == (tmp_path / "desktop/vendor").resolve()
    assert resolved_external.source_dir == (tmp_path / "desktop/vendor/source").resolve()
    assert resolved_external.build_dir == (tmp_path / "desktop/vendor/source/build").resolve()
    assert (
        resolved_external.artifact
        == (tmp_path / "desktop/vendor/source/build/example-server").resolve()
    )
    assert resolved_external.models == {
        "example": (tmp_path / "desktop/vendor/models/example.gguf").resolve()
    }

    resolved_workspace = resolve_component_paths(tmp_path, manifest, "workspace")
    assert resolved_workspace.source_dir == (tmp_path / "desktop/example").resolve()
    assert resolved_workspace.build_dir == (tmp_path / "desktop/example/target/release").resolve()
    assert (
        resolved_workspace.artifact
        == (tmp_path / "desktop/example/target/release/example").resolve()
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("vendor_dir", "../vendor"),
        ("source_dir", "../../outside"),
        ("build_dir", "../../outside"),
        ("artifact", "../../outside"),
        ("model", "../../outside.gguf"),
    ],
)
def test_resolve_component_paths_rejects_traversal(
    tmp_path: Path,
    field: str,
    value: str,
) -> None:
    manifest = ComponentManifest.model_validate(_manifest_data())
    if field == "vendor_dir":
        manifest = manifest.model_copy(update={"vendor_dir": value})
    else:
        component = manifest.components["example"]
        if field == "source_dir":
            source = component.source.model_copy(update={"source_dir": value})
            component = component.model_copy(update={"source": source})
        elif field in {"build_dir", "artifact"}:
            build = component.build.model_copy(update={field: value})
            component = component.model_copy(update={"build": build})
        else:
            model = component.models[0].model_copy(update={"path": value})
            component = component.model_copy(update={"models": [model]})
        manifest = manifest.model_copy(update={"components": {"example": component}})

    with pytest.raises(ValueError, match="escapes"):
        resolve_component_paths(tmp_path, manifest, "example")


@pytest.mark.parametrize(
    ("field", "error"),
    [
        ("vendor_dir", "vendor_dir"),
        ("source_dir", "source_dir"),
        ("build_dir", "build_dir"),
        ("artifact", "artifact"),
        ("model", "model example path"),
    ],
)
def test_resolve_component_paths_rejects_existing_symlink_escapes(
    tmp_path: Path,
    field: str,
    error: str,
) -> None:
    root = tmp_path / "root"
    outside = tmp_path / "outside"
    outside.mkdir()
    vendor = root / "desktop" / "vendor"

    if field == "vendor_dir":
        vendor.parent.mkdir(parents=True)
        vendor.symlink_to(outside, target_is_directory=True)
    else:
        vendor.mkdir(parents=True)
        if field == "source_dir":
            (vendor / "source").symlink_to(outside, target_is_directory=True)
        elif field == "build_dir":
            (vendor / "source").mkdir()
            (vendor / "source" / "build").symlink_to(outside, target_is_directory=True)
        elif field == "artifact":
            (vendor / "source" / "build").mkdir(parents=True)
            outside_artifact = outside / "example-server"
            outside_artifact.write_text("outside", encoding="utf-8")
            (vendor / "source" / "build" / "example-server").symlink_to(outside_artifact)
        else:
            (vendor / "models").mkdir()
            outside_model = outside / "example.gguf"
            outside_model.write_text("outside", encoding="utf-8")
            (vendor / "models" / "example.gguf").symlink_to(outside_model)

    manifest = ComponentManifest.model_validate(_manifest_data())
    with pytest.raises(ValueError, match=rf"{re.escape(error)} escapes"):
        resolve_component_paths(root, manifest, "example")


def test_resolve_component_paths_rejects_unknown_component(tmp_path: Path) -> None:
    manifest = ComponentManifest.model_validate(_manifest_data())

    with pytest.raises(ValueError, match="unknown component missing"):
        resolve_component_paths(tmp_path, manifest, "missing")


def test_expand_argv_expands_declared_tokens_without_reparsing_values() -> None:
    argv = [
        "{artifact}",
        "--model={model:qwen}",
        "--root",
        "{root}",
        "--prompt",
        "{prompt}",
        "--out",
        "{out}",
        "--width",
        "{width}",
        "--height",
        "{height}",
        "--steps",
        "{steps}",
        "--seconds",
        "{seconds}",
    ]
    tokens = {
        "artifact": "/repo/vendor/bin/tool",
        "model:qwen": "/repo/vendor/models/model with spaces;$(touch nope).gguf",
        "root": "/repo/{unknown}",
    }

    assert expand_argv(argv, tokens) == [
        "/repo/vendor/bin/tool",
        "--model=/repo/vendor/models/model with spaces;$(touch nope).gguf",
        "--root",
        "/repo/{unknown}",
        "--prompt",
        "{prompt}",
        "--out",
        "{out}",
        "--width",
        "{width}",
        "--height",
        "{height}",
        "--steps",
        "{steps}",
        "--seconds",
        "{seconds}",
    ]


@pytest.mark.parametrize(
    ("argv", "tokens", "error"),
    [
        (["{unknown}"], {}, "unknown argv token unknown"),
        (["{root}"], {}, "undeclared argv token root"),
        (["{model:qwen}"], {}, "undeclared argv token model:qwen"),
        (["{root!r}"], {"root": "/repo"}, "conversion"),
        (["{root:>20}"], {"root": "/repo"}, "format specifier"),
        (["{root}"], {"root": "/repo", "other": "value"}, "invalid token declaration other"),
    ],
)
def test_expand_argv_rejects_unknown_or_undeclared_tokens(
    argv: list[str],
    tokens: dict[str, str],
    error: str,
) -> None:
    with pytest.raises(ValueError, match=error):
        expand_argv(argv, tokens)


def test_manifest_rejects_unknown_or_undeclared_argv_tokens() -> None:
    component = _external_component()
    runtime = component["runtime"]
    assert isinstance(runtime, dict)
    runtime["argv"] = ["{artifact}", "{model:missing}"]

    with pytest.raises(ValidationError, match="undeclared model token model:missing"):
        ComponentManifest.model_validate(_manifest_data({"example": component}))

    runtime["argv"] = ["{artifact}", "{unknown}"]
    with pytest.raises(ValidationError, match="unknown argv token unknown"):
        ComponentManifest.model_validate(_manifest_data({"example": component}))


def test_manifest_allows_request_tokens_only_for_command_components() -> None:
    component = _external_component()
    runtime = component["runtime"]
    assert isinstance(runtime, dict)
    runtime["argv"] = ["{artifact}", "{prompt}"]

    with pytest.raises(ValidationError, match="request token prompt requires command runtime"):
        ComponentManifest.model_validate(_manifest_data({"example": component}))
