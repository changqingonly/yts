"""云端 /api/image —— 与本地 infer-gateway /image 对称(薄入口)。

POST {prompt,width,height,steps} → {png_base64,model,width,height}。
业务在 yts_core.imagegen;真实云图模型替换 generate_png 即可。
"""

from __future__ import annotations

import base64
from uuid import uuid4

from fastapi import APIRouter, Cookie, Header
from pydantic import BaseModel
from yts_core.imagegen import generate_png

from .billing_guard import GenerationBillingGuard, billing_user_if_required
from .dependencies import DbSession

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
async def create_image(
    req: ImageRequest,
    session: DbSession,
    authorization: str | None = Header(default=None),
    device_id: str | None = Cookie(default=None, alias="yts-device"),
) -> ImageResult:
    user = await billing_user_if_required(session, authorization, device_id)
    async with GenerationBillingGuard(
        session=session,
        user=user,
        request_id=f"image:{uuid4().hex}",
        credit_scene="image",
        usage_scene=None,
    ):
        png = await generate_png(req.prompt, width=req.width, height=req.height, steps=req.steps)
        return ImageResult(
            png_base64=base64.b64encode(png).decode("ascii"), width=req.width, height=req.height
        )
