"""HTTP 路由 = 薄入口。每个 handler 只做:解码 → 调 yts_core → 编码。禁止内联业务逻辑。"""
