from __future__ import annotations

import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.sync_env_examples import (  # noqa: E402
    ExampleSyncError,
    render_example,
    sync_examples,
)


def test_render_example_preserves_structure_and_sanitizes_values() -> None:
    source = (
        "# profile\n"
        "YTS_PROFILE=local\n"
        "\n"
        "YTS_OPENAI_API_KEY=secret\n"
        "YTS_AUTH_ACCESS_TOKEN_TTL_SECONDS=1800\n"
        "YTS_GATEWAY_TEXT_MAX_TOKENS=512\n"
        "YTS_DATABASE_URL=postgresql+asyncpg://user:pass@db.internal/yts\n"
        "YTS_LANGGRAPH_CHECKPOINT_POSTGRES_DSN=postgresql://user:pass@db.internal/yts\n"
        "YTS_LLAMA_MODEL=/Users/test/model.gguf\n"
        "YTS_AVATAR_STORAGE_DIR=/Users/test/avatars\n"
    )

    assert render_example(source) == (
        "# profile\n"
        "YTS_PROFILE=local\n"
        "\n"
        "YTS_OPENAI_API_KEY=\n"
        "YTS_AUTH_ACCESS_TOKEN_TTL_SECONDS=1800\n"
        "YTS_GATEWAY_TEXT_MAX_TOKENS=512\n"
        "YTS_DATABASE_URL=postgresql+asyncpg://USER:PASSWORD@HOST:5432/DBNAME\n"
        "YTS_LANGGRAPH_CHECKPOINT_POSTGRES_DSN=postgresql://USER:PASSWORD@HOST:5432/DBNAME\n"
        "YTS_LLAMA_MODEL=desktop/vendor/llm-models/Qwen2.5-7B-Instruct-Q4_K_M.gguf\n"
        "YTS_AVATAR_STORAGE_DIR=/path/to/value\n"
    )


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("YTS_LLAMA_SERVER_BIN", "desktop/vendor/llama.cpp/build/bin/llama-server"),
        ("YTS_LLAMA_MODEL", "desktop/vendor/llm-models/Qwen2.5-7B-Instruct-Q4_K_M.gguf"),
        ("YTS_IMAGEGEN_BIN", "desktop/vendor/stable-diffusion.cpp/build/bin/sd"),
        (
            "YTS_IMAGEGEN_DIFFUSION_MODEL",
            "desktop/vendor/sd-models/flux1-schnell-q4_k.gguf",
        ),
        ("YTS_IMAGEGEN_VAE", "desktop/vendor/sd-models/ae-f16.gguf"),
        ("YTS_IMAGEGEN_CLIP_L", "desktop/vendor/sd-models/clip_l-q8_0.gguf"),
        ("YTS_IMAGEGEN_T5XXL", "desktop/vendor/sd-models/t5xxl_q4_k.gguf"),
    ],
)
def test_render_example_uses_portable_model_paths(name: str, expected: str) -> None:
    assert render_example(f"{name}=/machine/specific/value\n") == f"{name}={expected}\n"


@pytest.mark.parametrize("name", ["YTS_AUTH_JWT_SECRET", "YTS_PASSWORD", "YTS_REFRESH_TOKEN"])
def test_render_example_empties_sensitive_values(name: str) -> None:
    assert render_example(f"{name}=do-not-publish\n") == f"{name}=\n"


def test_render_example_rejects_credential_bearing_non_database_url() -> None:
    with pytest.raises(ExampleSyncError, match="credential-bearing URL"):
        render_example("YTS_OPENAI_BASE_URL=https://user:pass@example.test/v1\n")


def test_render_example_rejects_invalid_env_lines() -> None:
    with pytest.raises(ExampleSyncError, match="invalid env line 2"):
        render_example("YTS_PROFILE=cloud\nnot-an-assignment\n")


def test_sync_examples_does_not_replace_either_target_when_rendering_fails(
    tmp_path: Path,
) -> None:
    conf_dir = tmp_path / "conf"
    conf_dir.mkdir()
    (conf_dir / "cloud.env").write_text("YTS_PROFILE=cloud\n", encoding="utf-8")
    (conf_dir / "local.env").write_text(
        "YTS_OPENAI_BASE_URL=https://user:pass@example.test/v1\n",
        encoding="utf-8",
    )
    cloud_example = conf_dir / "cloud.example.env"
    local_example = conf_dir / "local.example.env"
    cloud_example.write_text("cloud sentinel\n", encoding="utf-8")
    local_example.write_text("local sentinel\n", encoding="utf-8")

    with pytest.raises(ExampleSyncError, match="local.env"):
        sync_examples(tmp_path)

    assert cloud_example.read_text(encoding="utf-8") == "cloud sentinel\n"
    assert local_example.read_text(encoding="utf-8") == "local sentinel\n"
