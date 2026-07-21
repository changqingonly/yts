//! 密码保护的本地登录信息保险库——Keychain 不可用时的用户主动选择项(非自动兜底)。
//! 加密核心(seal/open)是纯函数,不依赖 AppHandle/文件系统,便于 `cargo test` 直接跑;
//! 命令层只做路径解析和文件 I/O。

use argon2::{Algorithm, Argon2, Params, Version};
use base64::{engine::general_purpose::STANDARD as B64, Engine as _};
use chacha20poly1305::aead::{rand_core::RngCore, Aead, KeyInit, OsRng};
use chacha20poly1305::{ChaCha20Poly1305, Key, Nonce};
use serde::{Deserialize, Serialize};
use std::io::ErrorKind;
use std::path::PathBuf;
use tauri::{AppHandle, Manager};

use crate::keychain::StoredCredentials;

pub const VAULT_FILE_NAME: &str = "auth-vault.json";
const SALT_LEN: usize = 16;
const NONCE_LEN: usize = 12;
const KEY_LEN: usize = 32;
const M_COST_KIB: u32 = 19 * 1024; // ~19 MiB, OWASP Argon2id 基线
const T_COST: u32 = 2;
const P_COST: u32 = 1;

#[derive(Serialize, Deserialize, Clone)]
pub struct VaultFile {
    pub version: u32,
    pub kdf: String,
    pub m_cost_kib: u32,
    pub t_cost: u32,
    pub p_cost: u32,
    pub salt_b64: String,
    pub nonce_b64: String,
    pub ciphertext_b64: String,
}

#[derive(Debug, PartialEq, Eq)]
pub enum VaultError {
    WrongPassphrase,
    Corrupt(String),
}

fn derive_key(passphrase: &str, salt: &[u8], m: u32, t: u32, p: u32) -> Result<[u8; KEY_LEN], String> {
    let params = Params::new(m, t, p, Some(KEY_LEN)).map_err(|e| e.to_string())?;
    let argon2 = Argon2::new(Algorithm::Argon2id, Version::V0x13, params);
    let mut key = [0u8; KEY_LEN];
    argon2
        .hash_password_into(passphrase.as_bytes(), salt, &mut key)
        .map_err(|e| e.to_string())?;
    Ok(key)
}

/// 纯函数:不做任何文件 I/O。每次调用都用全新随机 salt/nonce。
pub fn seal(passphrase: &str, plaintext: &[u8]) -> Result<VaultFile, String> {
    let mut salt = [0u8; SALT_LEN];
    OsRng.fill_bytes(&mut salt);
    let key = derive_key(passphrase, &salt, M_COST_KIB, T_COST, P_COST)?;
    let cipher = ChaCha20Poly1305::new(Key::from_slice(&key));
    let mut nonce_bytes = [0u8; NONCE_LEN];
    OsRng.fill_bytes(&mut nonce_bytes);
    let nonce = Nonce::from_slice(&nonce_bytes);
    let ciphertext = cipher
        .encrypt(nonce, plaintext)
        .map_err(|e| e.to_string())?;
    Ok(VaultFile {
        version: 1,
        kdf: "argon2id".into(),
        m_cost_kib: M_COST_KIB,
        t_cost: T_COST,
        p_cost: P_COST,
        salt_b64: B64.encode(salt),
        nonce_b64: B64.encode(nonce_bytes),
        ciphertext_b64: B64.encode(&ciphertext),
    })
}

/// 纯函数:区分"密码错误"(AEAD 校验失败)与"文件损坏"(编码/参数错误)。
pub fn open(vault: &VaultFile, passphrase: &str) -> Result<Vec<u8>, VaultError> {
    let salt = B64
        .decode(&vault.salt_b64)
        .map_err(|e| VaultError::Corrupt(e.to_string()))?;
    let nonce_bytes = B64
        .decode(&vault.nonce_b64)
        .map_err(|e| VaultError::Corrupt(e.to_string()))?;
    let ciphertext = B64
        .decode(&vault.ciphertext_b64)
        .map_err(|e| VaultError::Corrupt(e.to_string()))?;
    let key = derive_key(passphrase, &salt, vault.m_cost_kib, vault.t_cost, vault.p_cost)
        .map_err(VaultError::Corrupt)?;
    let cipher = ChaCha20Poly1305::new(Key::from_slice(&key));
    let nonce = Nonce::from_slice(&nonce_bytes);
    cipher
        .decrypt(nonce, ciphertext.as_ref())
        .map_err(|_| VaultError::WrongPassphrase)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn seal_then_open_roundtrips() {
        let vault = seal("correct horse", b"{\"device_id\":\"d\",\"refresh_token\":\"t\"}").unwrap();
        let plaintext = open(&vault, "correct horse").unwrap();
        assert_eq!(plaintext, b"{\"device_id\":\"d\",\"refresh_token\":\"t\"}");
    }

    #[test]
    fn wrong_passphrase_is_distinct_error() {
        let vault = seal("correct horse", b"payload").unwrap();
        assert_eq!(open(&vault, "wrong horse"), Err(VaultError::WrongPassphrase));
    }

    #[test]
    fn each_seal_uses_fresh_salt_and_nonce() {
        let a = seal("p", b"x").unwrap();
        let b = seal("p", b"x").unwrap();
        assert_ne!(a.salt_b64, b.salt_b64);
        assert_ne!(a.nonce_b64, b.nonce_b64);
        assert_ne!(a.ciphertext_b64, b.ciphertext_b64);
    }

    #[test]
    fn corrupt_ciphertext_is_rejected() {
        let mut vault = seal("p", b"payload").unwrap();
        vault.ciphertext_b64 = B64.encode(b"not valid ciphertext at all");
        assert!(matches!(open(&vault, "p"), Err(VaultError::WrongPassphrase)));
    }
}

// ---- Tauri 命令层:只做路径解析 + 文件 I/O，加解密逻辑全在上面的纯函数里 ----

fn vault_path(app: &AppHandle) -> Result<PathBuf, String> {
    Ok(app
        .path()
        .app_data_dir()
        .map_err(|e| e.to_string())?
        .join(VAULT_FILE_NAME))
}

#[tauri::command]
pub async fn vault_exists(app: AppHandle) -> Result<bool, String> {
    Ok(vault_path(&app)?.exists())
}

#[tauri::command]
pub async fn vault_store(
    app: AppHandle,
    passphrase: String,
    device_id: String,
    refresh_token: String,
) -> Result<(), String> {
    let plaintext =
        serde_json::to_vec(&StoredCredentials { device_id, refresh_token }).map_err(|e| e.to_string())?;
    let path = vault_path(&app)?;
    tauri::async_runtime::spawn_blocking(move || {
        let vault = seal(&passphrase, &plaintext)?;
        if let Some(parent) = path.parent() {
            std::fs::create_dir_all(parent).map_err(|e| e.to_string())?;
        }
        std::fs::write(
            &path,
            serde_json::to_string_pretty(&vault).map_err(|e| e.to_string())?,
        )
        .map_err(|e| e.to_string())
    })
    .await
    .map_err(|e| e.to_string())?
}

#[tauri::command]
pub async fn vault_unlock(app: AppHandle, passphrase: String) -> Result<StoredCredentials, String> {
    let path = vault_path(&app)?;
    tauri::async_runtime::spawn_blocking(move || {
        let json = std::fs::read_to_string(&path).map_err(|e| e.to_string())?;
        let vault: VaultFile = serde_json::from_str(&json).map_err(|e| e.to_string())?;
        let plaintext = open(&vault, &passphrase).map_err(|e| match e {
            VaultError::WrongPassphrase => "wrong_passphrase".to_string(),
            VaultError::Corrupt(m) => format!("vault_corrupt: {m}"),
        })?;
        serde_json::from_slice(&plaintext).map_err(|e| e.to_string())
    })
    .await
    .map_err(|e| e.to_string())?
}

#[tauri::command]
pub async fn vault_clear(app: AppHandle) -> Result<(), String> {
    let path = vault_path(&app)?;
    match std::fs::remove_file(path) {
        Ok(()) => Ok(()),
        Err(e) if e.kind() == ErrorKind::NotFound => Ok(()),
        Err(e) => Err(e.to_string()),
    }
}
