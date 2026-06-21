//! 统一出口代理:所有出站调用(Python sidecar / 前端 / 授权后的 llama.cpp)经此,
//! 由 Rust 做认证 / 拦截 / 签名 / 审计。本轮 stub。
//!
//! 设计见 wiki Platform-Split / Transport-Agnostic-Core:出站收敛到单一 Rust chokepoint。

#[allow(dead_code)]
pub async fn proxy_request(_upstream_url: &str, _body: &[u8]) -> Result<Vec<u8>, String> {
    // TODO: 注入鉴权头 + 拦截策略 + 审计;reqwest 转发上游;返回响应字节
    Err("egress proxy: TODO".into())
}
