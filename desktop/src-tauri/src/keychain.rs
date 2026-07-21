//! macOS Keychain 存储桌面端刷新会话(refresh_token + device_id)。用户在浏览器域名
//! (tauri://localhost)与本地服务(127.0.0.1)之间是跨源关系,WebKit ITP 不会跨重启保留
//! cookie,登录状态必须靠这里显式持久化。本应用未签名,用 keyring 的 apple-native
//! Keychain 模块(而非需要签名授权的 protected/iCloud 存储,那个会在未签名构建上报
//! PlatformError -34018)。

use keyring::Entry;
use serde::{Deserialize, Serialize};

const SERVICE: &str = "com.yuetools.yts";
const ACCOUNT: &str = "refresh-session";

#[derive(Serialize, Deserialize, Clone)]
pub struct StoredCredentials {
    pub device_id: String,
    pub refresh_token: String,
}

fn entry() -> Result<Entry, String> {
    Entry::new(SERVICE, ACCOUNT).map_err(|e| e.to_string())
}

/// Ok(None) = Keychain 可访问但未存过任何东西(全新安装/已登出)。
/// Err = Keychain 本身不可用——调用方必须原样透出这个错误,不能当作"没存过"静默处理。
fn load(entry: &Entry) -> Result<Option<StoredCredentials>, String> {
    match entry.get_password() {
        Ok(json) => serde_json::from_str(&json).map(Some).map_err(|e| e.to_string()),
        Err(keyring::Error::NoEntry) => Ok(None),
        Err(e) => Err(e.to_string()),
    }
}

fn store(entry: &Entry, creds: &StoredCredentials) -> Result<(), String> {
    let json = serde_json::to_string(creds).map_err(|e| e.to_string())?;
    entry.set_password(&json).map_err(|e| e.to_string())
}

fn clear(entry: &Entry) -> Result<(), String> {
    match entry.delete_credential() {
        Ok(()) | Err(keyring::Error::NoEntry) => Ok(()),
        Err(e) => Err(e.to_string()),
    }
}

#[tauri::command]
pub async fn keychain_load() -> Result<Option<StoredCredentials>, String> {
    tauri::async_runtime::spawn_blocking(|| load(&entry()?))
        .await
        .map_err(|e| e.to_string())?
}

#[tauri::command]
pub async fn keychain_store(device_id: String, refresh_token: String) -> Result<(), String> {
    tauri::async_runtime::spawn_blocking(move || {
        store(&entry()?, &StoredCredentials { device_id, refresh_token })
    })
    .await
    .map_err(|e| e.to_string())?
}

#[tauri::command]
pub async fn keychain_clear() -> Result<(), String> {
    tauri::async_runtime::spawn_blocking(|| clear(&entry()?))
        .await
        .map_err(|e| e.to_string())?
}
