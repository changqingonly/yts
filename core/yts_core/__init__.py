"""yts-core — 传输无关核心(架构红线)。

业务/编排逻辑只在此包。server(FastAPI HTTP)、desktop sidecar、未来 Windows PyO3
都只是薄入口,调用本包,严禁内联业务逻辑。
"""

__all__ = ["__version__"]
__version__ = "0.1.0"
