# API 契约(共享)

前端与后端的**唯一契约来源** = `core/yts_core/schemas`(Pydantic)。

导出 OpenAPI / JSON Schema(供前端生成类型 / 校验):
```bash
# 从运行中的 server 导出 OpenAPI
curl http://127.0.0.1:8000/openapi.json -o shared/api-contract/openapi.json
```

> 切换实现(本地 sidecar / 云端)**不改契约**;这是「统一 API + 双实现」(wiki Arch-V3-1)的支点。
