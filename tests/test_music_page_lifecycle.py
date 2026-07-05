from __future__ import annotations

from pathlib import Path

FRONTEND = Path("desktop/frontend/src")


def read_source(relative_path: str) -> str:
    return (FRONTEND / relative_path).read_text(encoding="utf-8")


def test_music_page_clears_player_queue_before_revoking_blob_urls_on_unmount() -> None:
    source = read_source("pages/MusicPage.vue")
    unmount_block = source.split("onBeforeUnmount(() => {", 1)[1].split("});", 1)[0]

    assert "player.setQueue([]);" in unmount_block
    assert unmount_block.index("player.setQueue([]);") < unmount_block.index(
        "revokePlayableTrackUrls();"
    )
