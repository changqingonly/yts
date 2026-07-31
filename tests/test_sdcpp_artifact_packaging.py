from __future__ import annotations

import hashlib
import json
import os
import stat
import subprocess
import zipfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_COMMIT = "e790073e1c311feb1ff423ba910f398df01bb60e"


def _write_executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def _fake_packaging_environment(tmp_path: Path) -> tuple[dict[str, str], Path]:
    source = tmp_path / "stable-diffusion.cpp"
    (source / "ggml").mkdir(parents=True)
    (source / "LICENSE").write_text("stable diffusion license\n", encoding="utf-8")
    (source / "ggml" / "LICENSE").write_text("ggml license\n", encoding="utf-8")

    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    _write_executable(
        fake_bin / "git",
        f"#!/bin/sh\nprintf '%s\\n' '{SOURCE_COMMIT}'\n",
    )
    _write_executable(
        fake_bin / "cmake",
        """#!/bin/sh
case " $* " in
  *" --build "*)
    mkdir -p "$YTS_SDC_SOURCE/build/bin"
    cat > "$YTS_SDC_SOURCE/build/bin/sd-cli" <<'EOF'
#!/bin/sh
case "${1:-}" in
  --help) printf '%s\n' 'stable-diffusion.cpp test cli' ;;
  *) exit 2 ;;
esac
EOF
    chmod +x "$YTS_SDC_SOURCE/build/bin/sd-cli"
    ;;
esac
""",
    )
    _write_executable(
        fake_bin / "file",
        "#!/bin/sh\nprintf '%s\\n' \"$1: Mach-O 64-bit executable arm64\"\n",
    )
    _write_executable(
        fake_bin / "vtool",
        "#!/bin/sh\nprintf '%s\\n' 'platform MACOS' 'minos 15.0' 'sdk 15.0'\n",
    )
    _write_executable(
        fake_bin / "otool",
        "#!/bin/sh\nprintf '%s\\n' \"$2:\" '/System/Library/Frameworks/Metal.framework/Versions/A/Metal' '/usr/lib/libSystem.B.dylib'\n",
    )

    output = tmp_path / "artifacts"
    env = dict(os.environ)
    env.update(
        {
            "PATH": f"{fake_bin}:{env['PATH']}",
            "YTS_SDC_SOURCE": str(source),
            "YTS_MODEL_ARTIFACT_ROOT": str(output),
        }
    )
    return env, output


def test_package_sdcpp_macos_builds_versioned_verified_archive(tmp_path: Path) -> None:
    env, output = _fake_packaging_environment(tmp_path)

    result = subprocess.run(
        ["bash", str(REPO_ROOT / "scripts" / "package_sdcpp_macos.sh")],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    release_dir = output / "sd" / "mac15-arm64"
    archive = release_dir / "e790073.zip"
    digest_file = archive.with_suffix(".zip.sha256")
    assert digest_file.read_text(encoding="ascii") == f"{hashlib.sha256(archive.read_bytes()).hexdigest()}\n"

    with zipfile.ZipFile(archive) as bundle:
        assert bundle.namelist() == [
            "stable-diffusion.cpp-macos-15-arm64/sd",
            "stable-diffusion.cpp-macos-15-arm64/LICENSE",
            "stable-diffusion.cpp-macos-15-arm64/ggml-LICENSE",
            "stable-diffusion.cpp-macos-15-arm64/manifest.json",
        ]
        manifest = json.loads(
            bundle.read("stable-diffusion.cpp-macos-15-arm64/manifest.json")
        )
        executable = bundle.read("stable-diffusion.cpp-macos-15-arm64/sd")

    assert manifest == {
        "architecture": "arm64",
        "executable": "sd",
        "executable_sha256": hashlib.sha256(executable).hexdigest(),
        "licenses": ["LICENSE", "ggml-LICENSE"],
        "minimum_macos": "15.0",
        "platform": "macos",
        "source_commit": SOURCE_COMMIT,
        "source_repository": "https://github.com/leejet/stable-diffusion.cpp",
    }


def test_package_sdcpp_macos_rejects_wrong_source_commit(tmp_path: Path) -> None:
    env, output = _fake_packaging_environment(tmp_path)
    fake_git = Path(env["PATH"].split(os.pathsep, 1)[0]) / "git"
    _write_executable(fake_git, "#!/bin/sh\nprintf '%s\\n' 'wrong-commit'\n")

    result = subprocess.run(
        ["bash", str(REPO_ROOT / "scripts" / "package_sdcpp_macos.sh")],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert f"expected source commit {SOURCE_COMMIT}" in result.stderr
    assert not output.exists()
