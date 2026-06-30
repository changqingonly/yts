from __future__ import annotations

from yts_core.config import get_settings
from yts_core.orchestration.checkpointing import setup_langgraph_checkpointer


def main() -> None:
    setup_langgraph_checkpointer(get_settings())


if __name__ == "__main__":
    main()
