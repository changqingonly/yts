from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from yts_core.config import get_settings
from yts_server.main import create_app


@pytest.fixture
def artifact_client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> tuple[TestClient, bytes]:
    artifact_root = tmp_path / "model-artifacts"
    artifact = artifact_root / "sd" / "mac15-arm64" / "e790073.zip"
    artifact.parent.mkdir(parents=True)
    content = b"0123456789abcdef"
    artifact.write_bytes(content)
    monkeypatch.setenv("YTS_PROFILE", "cloud")
    monkeypatch.setenv("YTS_MODEL_ARTIFACT_STORAGE_DIR", str(artifact_root))
    get_settings.cache_clear()
    return TestClient(create_app()), content


def test_model_artifact_origin_serves_complete_file(
    artifact_client: tuple[TestClient, bytes],
) -> None:
    client, content = artifact_client

    response = client.get("/download/sd/mac15-arm64/e790073.zip")

    assert response.status_code == 200
    assert response.content == content
    assert response.headers["content-type"] == "application/zip"
    assert response.headers["accept-ranges"] == "bytes"


def test_model_artifact_origin_supports_head(
    artifact_client: tuple[TestClient, bytes],
) -> None:
    client, content = artifact_client

    response = client.head("/download/sd/mac15-arm64/e790073.zip")

    assert response.status_code == 200
    assert response.content == b""
    assert response.headers["content-length"] == str(len(content))
    assert response.headers["accept-ranges"] == "bytes"


def test_model_artifact_origin_supports_byte_ranges(
    artifact_client: tuple[TestClient, bytes],
) -> None:
    client, content = artifact_client

    response = client.get(
        "/download/sd/mac15-arm64/e790073.zip",
        headers={"Range": "bytes=3-7"},
    )

    assert response.status_code == 206
    assert response.content == content[3:8]
    assert response.headers["content-range"] == f"bytes 3-7/{len(content)}"


def test_model_artifact_origin_returns_not_found_for_missing_file(
    artifact_client: tuple[TestClient, bytes],
) -> None:
    client, _ = artifact_client

    response = client.get("/download/sd/mac15-arm64/missing.zip")

    assert response.status_code == 404


def test_model_artifact_origin_rejects_directory_traversal(
    artifact_client: tuple[TestClient, bytes], tmp_path: Path
) -> None:
    client, _ = artifact_client
    outside = tmp_path / "outside.zip"
    outside.write_bytes(b"secret")

    response = client.get("/download/%2e%2e/outside.zip")

    assert response.status_code == 404
    assert response.content != b"secret"


def test_model_artifact_origin_does_not_keep_the_old_public_uri(
    artifact_client: tuple[TestClient, bytes],
) -> None:
    client, _ = artifact_client

    response = client.get("/artifacts/local-models/stable-diffusion.cpp/revision/sd.zip")

    assert response.status_code == 404
