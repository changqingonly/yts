"""云端 /api/image —— 与本地 candle-server /image 对称(薄入口)。

POST {prompt,width,height,steps} → {png_base64,model,width,height}。
业务在 yts_core.imagegen;真实云图模型替换 generate_png 即可。
"""

from __future__ import annotations

import base64

from fastapi import APIRouter
from pydantic import BaseModel
from yts_core.imagegen import generate_png

router = APIRouter(prefix="/image", tags=["image"])


class ImageRequest(BaseModel):
    prompt: str
    width: int = 512
    height: int = 512
    steps: int = 20


class ImageResult(BaseModel):
    png_base64: str
    model: str = "cloud-placeholder"
    width: int
    height: int


@router.post("", response_model=ImageResult)
async def create_image(req: ImageRequest) -> ImageResult:
    png = await generate_png(req.prompt, width=req.width, height=req.height, steps=req.steps)
    return ImageResult(
        png_base64=base64.b64encode(png).decode("ascii"),
        width=req.width,
        height=req.height,
    )
