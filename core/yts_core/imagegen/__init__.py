"""图像生成 —— 传输无关核心(云端 producer)。

与本地 candle-server /image(stable-diffusion.cpp)对称:同样输入 prompt/尺寸/步数,
输出 PNG 字节。FastAPI 路由是薄入口,调本模块。

本轮云端用占位 PNG(纯 Python,无依赖);真实云端图像模型(FLUX/SD3.5 服务或 API)
替换 generate_png() 即可,契约不变。
"""

from .generator import generate_png

__all__ = ["generate_png"]
