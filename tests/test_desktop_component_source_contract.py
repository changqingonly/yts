from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = ROOT / "scripts"
BUILD_SCRIPTS = [
    SCRIPT_DIR / "build_llamacpp.sh",
    SCRIPT_DIR / "build_sdcpp.sh",
    SCRIPT_DIR / "build_acestep.sh",
]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_legacy_scripts_do_not_read_or_write_vendor_env_files() -> None:
    forbidden = [
        "llamacpp.env",
        "imagegen.env",
        "YTS_LLAMA_CMD",
        "YTS_IMAGEGEN_CMD",
        "YTS_AUDIOGEN_CMD",
    ]
    offenders = [
        str(path.relative_to(ROOT))
        for path in [*BUILD_SCRIPTS, SCRIPT_DIR / "dev_gateway.sh"]
        if any(token in _read(path) for token in forbidden)
    ]

    assert offenders == []


def test_component_build_scripts_delegate_to_servctl_without_floating_clones() -> None:
    expected_components = {
        "build_llamacpp.sh": "llama",
        "build_sdcpp.sh": "stable-diffusion",
        "build_acestep.sh": "acestep",
    }
    for path in BUILD_SCRIPTS:
        source = _read(path)
        component = expected_components[path.name]
        assert f'exec "$ROOT/servctl" components install {component}' in source
        assert "git clone" not in source
        assert "resolve/main" not in source


def test_model_validity_checks_do_not_use_non_empty_file_size_only() -> None:
    offenders = [
        str(path.relative_to(ROOT))
        for path in BUILD_SCRIPTS
        if "[ -s " in _read(path) or " -s " in _read(path)
    ]

    assert offenders == []


def test_scripts_do_not_advertise_placeholder_or_synthetic_behavior() -> None:
    forbidden = ["placeholder", "synthetic", "stub", "TODO", "兜底", "占位"]
    script_paths = sorted(SCRIPT_DIR.glob("*.sh")) + [ROOT / "servctl"]
    offenders = [
        str(path.relative_to(ROOT))
        for path in script_paths
        if any(token.lower() in _read(path).lower() for token in forbidden)
    ]

    assert offenders == []


def test_cargo_application_lockfiles_are_trackable() -> None:
    lockfiles = [
        ROOT / "desktop" / "infer-gateway" / "Cargo.lock",
        ROOT / "desktop" / "src-tauri" / "Cargo.lock",
    ]
    for path in lockfiles:
        assert path.is_file()
        ignored = subprocess.run(
            ["git", "check-ignore", "-q", str(path.relative_to(ROOT))],
            cwd=ROOT,
            check=False,
        )
        assert ignored.returncode == 1, f"{path.relative_to(ROOT)} must not be ignored"


def test_readme_documents_the_supported_component_manager_flow() -> None:
    readme = _read(ROOT / "README.md")

    assert "./servctl components install" in readme
    assert "./servctl components verify" in readme
    assert "./servctl components status --profile local" in readme
    assert "./servctl start --profile local" in readme
    assert "scripts/build_llamacpp.sh" not in readme
    assert "scripts/build_sdcpp.sh" not in readme
    assert "scripts/dev_gateway.sh" not in readme
