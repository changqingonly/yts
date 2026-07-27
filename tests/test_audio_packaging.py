from pathlib import Path


def test_sidecar_packages_canonical_audio_ffmpeg_binary() -> None:
    spec = Path("desktop/sidecar/build_macos.spec").read_text(encoding="utf-8")
    build_script = Path("scripts/build_sidecar_macos.sh").read_text(encoding="utf-8")

    assert "collect_data_files('imageio_ffmpeg')" in spec
    assert "imageio_ffmpeg_datas" in spec
    assert "datas=imageio_ffmpeg_datas" in spec
    assert 'test -x "dist/yts-sidecar"' in build_script
    assert 'cp "dist/yts-sidecar" "${OUT}/yts-sidecar-${TRIPLE}"' in build_script
    assert "TODO: 调整 dist 路径" not in build_script


def test_rendition_worker_never_falls_back_to_system_ffmpeg() -> None:
    source = Path("server/yts_server/domains/audio_renditions.py").read_text(encoding="utf-8")

    assert "get_ffmpeg_exe" not in source
    assert 'resources.files("imageio_ffmpeg.binaries")' in source
    assert "FNAME_PER_PLATFORM[get_platform()]" in source
    assert "os.access(executable, os.X_OK)" in source
