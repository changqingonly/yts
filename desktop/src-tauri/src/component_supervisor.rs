use fs2::FileExt;
use serde::Deserialize;
use std::collections::{BTreeMap, BTreeSet};
use std::fmt::{Display, Formatter};
use std::fs::{self, File, OpenOptions};
use std::io::{Read, Write};
use std::net::{TcpStream, ToSocketAddrs};
use std::path::{Path, PathBuf};
use std::time::{Duration, Instant};
use tauri::async_runtime::Receiver;
use tauri::AppHandle;
use tauri_plugin_shell::process::{CommandChild, CommandEvent};
use tauri_plugin_shell::ShellExt;

const LOCK_SCHEMA_VERSION: u32 = 1;
const LOCK_OWNER_TAURI: &str = "tauri";
const INFER_GATEWAY: &str = "infer-gateway";
const SIDECAR_NAME: &str = "yts-sidecar";

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct SupervisorError {
    message: String,
}

impl SupervisorError {
    pub fn new(message: impl Into<String>) -> Self {
        Self {
            message: message.into(),
        }
    }
}

impl Display for SupervisorError {
    fn fmt(&self, formatter: &mut Formatter<'_>) -> std::fmt::Result {
        formatter.write_str(&self.message)
    }
}

impl std::error::Error for SupervisorError {}

impl From<std::io::Error> for SupervisorError {
    fn from(value: std::io::Error) -> Self {
        Self::new(value.to_string())
    }
}

impl From<toml::de::Error> for SupervisorError {
    fn from(value: toml::de::Error) -> Self {
        Self::new(value.to_string())
    }
}

#[derive(Debug, Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ComponentManifest {
    pub schema_version: u32,
    pub vendor_dir: String,
    pub components: BTreeMap<String, ComponentSpec>,
}

#[derive(Debug, Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ComponentSpec {
    pub enabled: bool,
    pub platforms: Vec<String>,
    pub dependencies: Vec<String>,
    pub source: SourceSpec,
    pub build: BuildSpec,
    #[serde(default)]
    pub models: Vec<ModelAsset>,
    pub runtime: RuntimeSpec,
}

#[derive(Debug, Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct SourceSpec {
    pub kind: String,
    pub source_dir: String,
    pub url: Option<String>,
    pub commit: Option<String>,
    pub submodules: Option<bool>,
}

#[derive(Debug, Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct BuildSpec {
    pub target: String,
    pub configure_argv: Vec<String>,
    pub build_argv: Vec<String>,
    pub build_dir: String,
    pub artifact: String,
}

#[derive(Debug, Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ModelAsset {
    pub id: String,
    pub url: String,
    pub size: u64,
    pub sha256: String,
    pub path: String,
}

#[derive(Debug, Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct RuntimeSpec {
    pub kind: String,
    pub argv: Vec<String>,
    pub host: Option<String>,
    pub port: Option<u16>,
    pub health: Option<ProbeSpec>,
    pub readiness: Option<ProbeSpec>,
    pub startup_timeout_seconds: Option<u64>,
    pub shutdown_timeout_seconds: Option<u64>,
    pub execution_timeout_seconds: Option<u64>,
    pub request_timeout_seconds: Option<u64>,
    pub limits: Option<CommandLimits>,
}

#[derive(Debug, Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ProbeSpec {
    pub path: String,
    pub timeout_seconds: u64,
}

#[derive(Debug, Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct CommandLimits {
    pub max_output_bytes: u64,
    pub max_concurrency: u32,
    pub max_width: Option<u32>,
    pub max_height: Option<u32>,
    pub max_steps: Option<u32>,
    pub max_seconds: Option<f32>,
}

impl ComponentManifest {
    pub fn from_path(path: impl AsRef<Path>) -> Result<Self, SupervisorError> {
        let path = path.as_ref();
        let source = fs::read_to_string(path)
            .map_err(|error| SupervisorError::new(format!("cannot read {path:?}: {error}")))?;
        let manifest: Self = toml::from_str(&source)
            .map_err(|error| SupervisorError::new(format!("invalid manifest {path:?}: {error}")))?;
        if manifest.schema_version != 1 {
            return Err(SupervisorError::new(format!(
                "unsupported component manifest schema_version {}",
                manifest.schema_version
            )));
        }
        Ok(manifest)
    }

    pub fn start_order(&self) -> Result<Vec<String>, SupervisorError> {
        let enabled: BTreeSet<&str> = self
            .components
            .iter()
            .filter_map(|(name, component)| component.enabled.then_some(name.as_str()))
            .collect();
        let mut indegree: BTreeMap<&str, usize> = BTreeMap::new();
        let mut dependents: BTreeMap<&str, Vec<&str>> = BTreeMap::new();
        for name in &enabled {
            indegree.insert(name, 0);
            dependents.insert(name, Vec::new());
        }
        for name in &enabled {
            let component = &self.components[*name];
            for dependency in &component.dependencies {
                if !self.components.contains_key(dependency) {
                    return Err(SupervisorError::new(format!(
                        "component {name} has unknown dependency {dependency}"
                    )));
                }
                if enabled.contains(dependency.as_str()) {
                    *indegree.get_mut(name).expect("enabled component") += 1;
                    dependents
                        .get_mut(dependency.as_str())
                        .expect("enabled dependency")
                        .push(name);
                }
            }
        }

        let mut ready: BTreeSet<&str> = indegree
            .iter()
            .filter_map(|(name, count)| (*count == 0).then_some(*name))
            .collect();
        let mut ordered = Vec::new();
        while let Some(name) = ready.pop_first() {
            ordered.push(name.to_string());
            for dependent in dependents.get(name).into_iter().flatten() {
                let count = indegree.get_mut(dependent).expect("dependent");
                *count -= 1;
                if *count == 0 {
                    ready.insert(dependent);
                }
            }
        }
        if ordered.len() != enabled.len() {
            return Err(SupervisorError::new(
                "enabled component dependency graph contains a cycle",
            ));
        }
        Ok(ordered)
    }
}

pub fn current_platform() -> Result<String, SupervisorError> {
    #[cfg(all(target_os = "macos", target_arch = "aarch64"))]
    {
        return Ok("darwin-arm64".to_string());
    }
    #[cfg(all(target_os = "macos", target_arch = "x86_64"))]
    {
        return Ok("darwin-x86_64".to_string());
    }
    #[cfg(all(target_os = "linux", target_arch = "x86_64"))]
    {
        return Ok("linux-x86_64".to_string());
    }
    #[allow(unreachable_code)]
    Err(SupervisorError::new(format!(
        "unsupported platform: {}/{}",
        std::env::consts::OS,
        std::env::consts::ARCH
    )))
}

#[derive(Debug, Clone)]
pub struct LaunchSpec {
    pub name: String,
    pub argv: Vec<String>,
    pub env: BTreeMap<String, String>,
    pub cwd: PathBuf,
}

pub trait RuntimeLauncher {
    fn spawn(&mut self, spec: LaunchSpec) -> Result<Box<dyn RuntimeChild>, SupervisorError>;
    fn wait_ready(&mut self, name: &str, runtime: &RuntimeSpec) -> Result<(), SupervisorError>;
}

pub trait RuntimeChild: Send {
    fn name(&self) -> &str;
    fn pid(&self) -> u32;
    fn kill(&mut self) -> Result<(), SupervisorError>;
}

pub struct ComponentSupervisor {
    lock_path: PathBuf,
    lock: Option<SupervisorLock>,
    children: Vec<Box<dyn RuntimeChild>>,
}

impl ComponentSupervisor {
    pub fn new(lock_path: PathBuf) -> Self {
        Self {
            lock_path,
            lock: None,
            children: Vec::new(),
        }
    }

    pub fn for_development() -> Self {
        let root = development_repo_root();
        Self::new(root.join("run").join("yts-local-supervisor.lock"))
    }

    pub fn child_count(&self) -> usize {
        self.children.len()
    }

    pub fn start(
        &mut self,
        root: &Path,
        config_dir: &Path,
        runtime_dir: &Path,
        launcher: &mut dyn RuntimeLauncher,
    ) -> Result<(), SupervisorError> {
        if self.lock.is_some() || !self.children.is_empty() {
            return Err(SupervisorError::new(
                "component supervisor is already running",
            ));
        }
        let manifest = ComponentManifest::from_path(root.join("desktop/components.toml"))?;
        let platform = current_platform()?;
        for (name, component) in &manifest.components {
            if component.enabled && !component.platforms.contains(&platform) {
                return Err(SupervisorError::new(format!(
                    "component {name} does not support current platform {platform}"
                )));
            }
        }

        let lock = SupervisorLock::acquire_with(
            &self.lock_path,
            LOCK_OWNER_TAURI,
            std::process::id(),
            process_exists,
        )?;
        self.lock = Some(lock);

        match self.start_ordered_children(root, config_dir, runtime_dir, &manifest, launcher) {
            Ok(()) => Ok(()),
            Err(error) => {
                let rollback = self.rollback();
                self.release_lock();
                if rollback.is_empty() {
                    Err(error)
                } else {
                    Err(SupervisorError::new(format!(
                        "{error}; rollback errors: {}",
                        rollback.join("; ")
                    )))
                }
            }
        }
    }

    pub fn stop(&mut self) -> Result<Vec<String>, SupervisorError> {
        let mut killed = Vec::new();
        let mut errors = Vec::new();
        while let Some(mut child) = self.children.pop() {
            let name = child.name().to_string();
            match child.kill() {
                Ok(()) => killed.push(name),
                Err(error) => errors.push(format!("{name}: {error}")),
            }
        }
        if let Some(mut lock) = self.lock.take() {
            if let Err(error) = lock.release() {
                errors.push(format!("lock: {error}"));
            }
        }
        if errors.is_empty() {
            Ok(killed)
        } else {
            Err(SupervisorError::new(errors.join("; ")))
        }
    }

    fn start_ordered_children(
        &mut self,
        root: &Path,
        config_dir: &Path,
        runtime_dir: &Path,
        manifest: &ComponentManifest,
        launcher: &mut dyn RuntimeLauncher,
    ) -> Result<(), SupervisorError> {
        let start_order = manifest.start_order()?;
        for name in start_order
            .iter()
            .filter(|name| name.as_str() != INFER_GATEWAY)
        {
            let component = &manifest.components[name];
            if component.runtime.kind == "service" {
                self.spawn_component(root, manifest, name, component, launcher)?;
            }
        }
        let gateway = manifest
            .components
            .get(INFER_GATEWAY)
            .ok_or_else(|| SupervisorError::new("missing infer-gateway component"))?;
        self.spawn_component(root, manifest, INFER_GATEWAY, gateway, launcher)?;
        self.spawn_sidecar(root, config_dir, runtime_dir, launcher)?;
        Ok(())
    }

    fn spawn_component(
        &mut self,
        root: &Path,
        manifest: &ComponentManifest,
        name: &str,
        component: &ComponentSpec,
        launcher: &mut dyn RuntimeLauncher,
    ) -> Result<(), SupervisorError> {
        if component.runtime.kind != "service" {
            return Err(SupervisorError::new(format!(
                "component {name} runtime must be service"
            )));
        }
        let argv = expand_component_argv(root, manifest, name)?;
        let child = launcher.spawn(LaunchSpec {
            name: name.to_string(),
            argv,
            env: BTreeMap::new(),
            cwd: root.to_path_buf(),
        })?;
        self.children.push(child);
        launcher.wait_ready(name, &component.runtime)
    }

    fn spawn_sidecar(
        &mut self,
        root: &Path,
        config_dir: &Path,
        runtime_dir: &Path,
        launcher: &mut dyn RuntimeLauncher,
    ) -> Result<(), SupervisorError> {
        let env = BTreeMap::from([
            ("YTS_PROFILE".to_string(), "local".to_string()),
            (
                "YTS_CONFIG_DIR".to_string(),
                config_dir.to_string_lossy().to_string(),
            ),
            (
                "YTS_RUNTIME_DIR".to_string(),
                runtime_dir.to_string_lossy().to_string(),
            ),
        ]);
        let child = launcher.spawn(LaunchSpec {
            name: SIDECAR_NAME.to_string(),
            argv: vec![SIDECAR_NAME.to_string()],
            env,
            cwd: root.to_path_buf(),
        })?;
        self.children.push(child);
        Ok(())
    }

    fn rollback(&mut self) -> Vec<String> {
        let mut errors = Vec::new();
        while let Some(mut child) = self.children.pop() {
            let name = child.name().to_string();
            if let Err(error) = child.kill() {
                errors.push(format!("{name}: {error}"));
            }
        }
        errors
    }

    fn release_lock(&mut self) {
        if let Some(mut lock) = self.lock.take() {
            let _ = lock.release();
        }
    }
}

#[derive(Debug)]
pub struct SupervisorLock {
    path: PathBuf,
    file: File,
}

impl SupervisorLock {
    pub fn acquire_with(
        path: &Path,
        owner: &str,
        pid: u32,
        process_exists: impl Fn(u32) -> bool,
    ) -> Result<Self, SupervisorError> {
        if owner != "servctl" && owner != LOCK_OWNER_TAURI {
            return Err(SupervisorError::new(format!(
                "unsupported lock owner {owner}"
            )));
        }
        if let Some(parent) = path.parent() {
            fs::create_dir_all(parent)?;
        }
        if path.exists() {
            let record = LockRecord::from_path(path)?;
            if process_exists(record.pid) {
                return Err(SupervisorError::new(format!(
                    "local runtime is owned by {}: pid {}",
                    record.owner, record.pid
                )));
            }
            fs::remove_file(path)?;
        }
        let mut file = OpenOptions::new()
            .create_new(true)
            .read(true)
            .write(true)
            .open(path)?;
        file.try_lock_exclusive()?;
        let record = LockRecord {
            schema_version: LOCK_SCHEMA_VERSION,
            owner: owner.to_string(),
            pid,
            started_at: "tauri-runtime".to_string(),
        };
        file.write_all(serde_json::to_string(&record)?.as_bytes())?;
        file.write_all(b"\n")?;
        Ok(Self {
            path: path.to_path_buf(),
            file,
        })
    }

    pub fn release(&mut self) -> Result<(), SupervisorError> {
        self.file.unlock()?;
        match fs::remove_file(&self.path) {
            Ok(()) => Ok(()),
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(()),
            Err(error) => Err(error.into()),
        }
    }
}

#[derive(Debug, serde::Serialize, Deserialize)]
struct LockRecord {
    #[serde(rename = "schemaVersion")]
    schema_version: u32,
    owner: String,
    pid: u32,
    #[serde(rename = "startedAt")]
    started_at: String,
}

impl LockRecord {
    fn from_path(path: &Path) -> Result<Self, SupervisorError> {
        let source = fs::read_to_string(path)?;
        let record: Self = serde_json::from_str(&source)
            .map_err(|error| SupervisorError::new(format!("invalid lock {path:?}: {error}")))?;
        if record.schema_version != LOCK_SCHEMA_VERSION {
            return Err(SupervisorError::new(format!(
                "unsupported lock schema {}",
                record.schema_version
            )));
        }
        if record.pid == 0 {
            return Err(SupervisorError::new("lock pid must be positive"));
        }
        Ok(record)
    }
}

impl From<serde_json::Error> for SupervisorError {
    fn from(value: serde_json::Error) -> Self {
        Self::new(value.to_string())
    }
}

pub struct ShellLauncher<R: tauri::Runtime> {
    app: AppHandle<R>,
}

impl<R: tauri::Runtime> ShellLauncher<R> {
    pub fn new(app: AppHandle<R>) -> Self {
        Self { app }
    }
}

impl<R: tauri::Runtime> RuntimeLauncher for ShellLauncher<R> {
    fn spawn(&mut self, spec: LaunchSpec) -> Result<Box<dyn RuntimeChild>, SupervisorError> {
        if spec.argv.is_empty() {
            return Err(SupervisorError::new(format!("{} argv is empty", spec.name)));
        }
        let command = if spec.name == SIDECAR_NAME {
            self.app
                .shell()
                .sidecar(SIDECAR_NAME)
                .map_err(|error| SupervisorError::new(error.to_string()))?
                .args(spec.argv.iter().skip(1))
        } else {
            self.app
                .shell()
                .command(&spec.argv[0])
                .args(spec.argv.iter().skip(1))
        }
        .current_dir(&spec.cwd)
        .envs(spec.env.iter());
        let (receiver, child) = command
            .spawn()
            .map_err(|error| SupervisorError::new(error.to_string()))?;
        Ok(Box::new(ShellRuntimeChild {
            name: spec.name,
            child: Some(child),
            _receiver: receiver,
        }))
    }

    fn wait_ready(&mut self, name: &str, runtime: &RuntimeSpec) -> Result<(), SupervisorError> {
        wait_http_ready(name, runtime)
    }
}

struct ShellRuntimeChild {
    name: String,
    child: Option<CommandChild>,
    _receiver: Receiver<CommandEvent>,
}

impl RuntimeChild for ShellRuntimeChild {
    fn name(&self) -> &str {
        &self.name
    }

    fn pid(&self) -> u32 {
        self.child.as_ref().map(CommandChild::pid).unwrap_or(0)
    }

    fn kill(&mut self) -> Result<(), SupervisorError> {
        if let Some(child) = self.child.take() {
            child
                .kill()
                .map_err(|error| SupervisorError::new(error.to_string()))?;
        }
        Ok(())
    }
}

pub fn development_repo_root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .expect("src-tauri has desktop parent")
        .parent()
        .expect("desktop has repo parent")
        .to_path_buf()
}

fn process_exists(pid: u32) -> bool {
    #[cfg(unix)]
    {
        let status = std::process::Command::new("kill")
            .arg("-0")
            .arg(pid.to_string())
            .status();
        return status.map(|status| status.success()).unwrap_or(false);
    }
    #[cfg(not(unix))]
    {
        let _ = pid;
        false
    }
}

fn expand_component_argv(
    root: &Path,
    manifest: &ComponentManifest,
    name: &str,
) -> Result<Vec<String>, SupervisorError> {
    let component = manifest
        .components
        .get(name)
        .ok_or_else(|| SupervisorError::new(format!("unknown component {name}")))?;
    let vendor = root.join(&manifest.vendor_dir);
    let source_base = if component.source.kind == "external" {
        vendor.clone()
    } else {
        root.to_path_buf()
    };
    let build_base = source_base.clone();
    let source = source_base.join(&component.source.source_dir);
    let build = build_base.join(&component.build.build_dir);
    let artifact = build_base.join(&component.build.artifact);
    let mut tokens = BTreeMap::from([
        ("root".to_string(), root.to_string_lossy().to_string()),
        ("vendor".to_string(), vendor.to_string_lossy().to_string()),
        ("source".to_string(), source.to_string_lossy().to_string()),
        ("build".to_string(), build.to_string_lossy().to_string()),
        (
            "artifact".to_string(),
            artifact.to_string_lossy().to_string(),
        ),
    ]);
    for model in &component.models {
        tokens.insert(
            format!("model:{}", model.id),
            vendor.join(&model.path).to_string_lossy().to_string(),
        );
    }
    component
        .runtime
        .argv
        .iter()
        .map(|argument| expand_argument(argument, &tokens))
        .collect()
}

fn expand_argument(
    argument: &str,
    tokens: &BTreeMap<String, String>,
) -> Result<String, SupervisorError> {
    let mut output = String::new();
    let mut rest = argument;
    while let Some(start) = rest.find('{') {
        output.push_str(&rest[..start]);
        let after_start = &rest[start + 1..];
        let Some(end) = after_start.find('}') else {
            return Err(SupervisorError::new(format!(
                "unterminated argv token in {argument:?}"
            )));
        };
        let token = &after_start[..end];
        let normalized = token.replace(':', ":");
        let value = tokens
            .get(&normalized)
            .ok_or_else(|| SupervisorError::new(format!("undeclared argv token {normalized}")))?;
        output.push_str(value);
        rest = &after_start[end + 1..];
    }
    output.push_str(rest);
    Ok(output)
}

fn wait_http_ready(name: &str, runtime: &RuntimeSpec) -> Result<(), SupervisorError> {
    let host = runtime
        .host
        .as_ref()
        .ok_or_else(|| SupervisorError::new(format!("{name} runtime requires host")))?;
    let port = runtime
        .port
        .ok_or_else(|| SupervisorError::new(format!("{name} runtime requires port")))?;
    let readiness = runtime
        .readiness
        .as_ref()
        .ok_or_else(|| SupervisorError::new(format!("{name} runtime requires readiness")))?;
    let deadline = Instant::now() + Duration::from_secs(readiness.timeout_seconds);
    let address = format!("{host}:{port}");
    while Instant::now() < deadline {
        if probe_http(&address, host, &readiness.path).unwrap_or(false) {
            return Ok(());
        }
        std::thread::sleep(Duration::from_millis(250));
    }
    Err(SupervisorError::new(format!(
        "{name} readiness timed out at http://{address}{}",
        readiness.path
    )))
}

fn probe_http(address: &str, host: &str, path: &str) -> Result<bool, SupervisorError> {
    let socket = address
        .to_socket_addrs()?
        .next()
        .ok_or_else(|| SupervisorError::new(format!("cannot resolve {address}")))?;
    let mut stream = TcpStream::connect_timeout(&socket, Duration::from_secs(1))?;
    stream.set_read_timeout(Some(Duration::from_secs(1)))?;
    let request = format!("GET {path} HTTP/1.1\r\nHost: {host}\r\nConnection: close\r\n\r\n");
    stream.write_all(request.as_bytes())?;
    let mut response = String::new();
    stream.read_to_string(&mut response)?;
    Ok(response.starts_with("HTTP/1.1 2") || response.starts_with("HTTP/1.0 2"))
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;
    use std::path::{Path, PathBuf};
    use std::sync::atomic::{AtomicU64, Ordering};

    static TEST_COUNTER: AtomicU64 = AtomicU64::new(0);

    #[derive(Default)]
    struct FakeLauncher {
        events: Vec<String>,
        fail_on: Option<String>,
        next_pid: u32,
    }

    impl FakeLauncher {
        fn new() -> Self {
            Self {
                events: Vec::new(),
                fail_on: None,
                next_pid: 1000,
            }
        }

        fn fail_on(label: &str) -> Self {
            Self {
                events: Vec::new(),
                fail_on: Some(label.to_string()),
                next_pid: 1000,
            }
        }

        fn record(&mut self, label: String) -> Result<(), SupervisorError> {
            self.events.push(label.clone());
            if self.fail_on.as_deref() == Some(label.as_str()) {
                return Err(SupervisorError::new(format!("failed at {label}")));
            }
            Ok(())
        }
    }

    impl RuntimeLauncher for FakeLauncher {
        fn spawn(&mut self, spec: LaunchSpec) -> Result<Box<dyn RuntimeChild>, SupervisorError> {
            self.record(format!("spawn:{}", spec.name))?;
            if spec.name == "yts-sidecar" {
                assert_eq!(
                    spec.env.get("YTS_PROFILE").map(String::as_str),
                    Some("local")
                );
                assert!(spec.env.contains_key("YTS_CONFIG_DIR"));
                assert!(spec.env.contains_key("YTS_RUNTIME_DIR"));
            }
            self.next_pid += 1;
            Ok(Box::new(FakeChild {
                name: spec.name,
                pid: self.next_pid,
            }))
        }

        fn wait_ready(
            &mut self,
            name: &str,
            _runtime: &RuntimeSpec,
        ) -> Result<(), SupervisorError> {
            self.record(format!("ready:{name}"))
        }
    }

    struct FakeChild {
        name: String,
        pid: u32,
    }

    impl RuntimeChild for FakeChild {
        fn name(&self) -> &str {
            &self.name
        }

        fn pid(&self) -> u32 {
            self.pid
        }

        fn kill(&mut self) -> Result<(), SupervisorError> {
            Ok(())
        }
    }

    fn repo_root() -> PathBuf {
        PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .parent()
            .unwrap()
            .parent()
            .unwrap()
            .to_path_buf()
    }

    fn test_dir(name: &str) -> PathBuf {
        let id = TEST_COUNTER.fetch_add(1, Ordering::SeqCst);
        let path = std::env::temp_dir().join(format!(
            "yts-tauri-supervisor-{name}-{}-{id}",
            std::process::id()
        ));
        if path.exists() {
            fs::remove_dir_all(&path).unwrap();
        }
        fs::create_dir_all(&path).unwrap();
        path
    }

    fn supervisor(lock_dir: &Path) -> ComponentSupervisor {
        ComponentSupervisor::new(lock_dir.join("run").join("yts-local-supervisor.lock"))
    }

    #[test]
    fn manifest_deserializes_current_platform_and_topological_order() {
        let manifest = ComponentManifest::from_path(repo_root().join("desktop/components.toml"))
            .expect("manifest should parse");

        assert_eq!(manifest.schema_version, 1);
        assert_eq!(
            manifest.components["llama"].source.commit.as_deref(),
            Some("72874f559c598b8f89fbb24864868337cf5afb4c")
        );
        assert!(!manifest.components["acestep"].enabled);
        assert_eq!(
            manifest.start_order().expect("start order"),
            vec!["llama", "stable-diffusion", "infer-gateway"]
        );
        assert!(manifest.components["llama"]
            .platforms
            .contains(&current_platform().expect("supported platform")));
    }

    #[test]
    fn lock_refuses_when_live_servctl_pid_owns_it() {
        let dir = test_dir("lock-refusal");
        let lock_path = dir.join("run").join("yts-local-supervisor.lock");
        fs::create_dir_all(lock_path.parent().unwrap()).unwrap();
        fs::write(
            &lock_path,
            r#"{"schemaVersion":1,"owner":"servctl","pid":424242,"startedAt":"2026-07-15T00:00:00Z"}"#,
        )
        .unwrap();

        let error = SupervisorLock::acquire_with(&lock_path, "tauri", 123, |_| true)
            .expect_err("live servctl owner must block tauri");

        assert!(error.to_string().contains("owned by servctl"));
    }

    #[test]
    fn start_retains_children_and_starts_sidecar_last() {
        let root = repo_root();
        let dir = test_dir("start");
        let mut launcher = FakeLauncher::new();
        let mut supervisor = supervisor(&dir);

        supervisor
            .start(
                &root,
                &dir.join("conf"),
                &dir.join("runtime"),
                &mut launcher,
            )
            .expect("start");

        assert_eq!(
            launcher.events,
            vec![
                "spawn:llama",
                "ready:llama",
                "spawn:infer-gateway",
                "ready:infer-gateway",
                "spawn:yts-sidecar",
            ]
        );
        assert_eq!(supervisor.child_count(), 3);
    }

    #[test]
    fn start_rolls_back_started_children_on_failure() {
        let root = repo_root();
        let dir = test_dir("rollback");
        let mut launcher = FakeLauncher::fail_on("ready:infer-gateway");
        let mut supervisor = supervisor(&dir);

        let error = supervisor
            .start(
                &root,
                &dir.join("conf"),
                &dir.join("runtime"),
                &mut launcher,
            )
            .expect_err("readiness failure should rollback");

        assert!(error.to_string().contains("failed at ready:infer-gateway"));
        assert_eq!(supervisor.child_count(), 0);
        assert!(!dir.join("run").join("yts-local-supervisor.lock").exists());
    }

    #[test]
    fn stop_kills_children_in_reverse_order_and_releases_lock() {
        let root = repo_root();
        let dir = test_dir("stop");
        let mut launcher = FakeLauncher::new();
        let mut supervisor = supervisor(&dir);
        supervisor
            .start(
                &root,
                &dir.join("conf"),
                &dir.join("runtime"),
                &mut launcher,
            )
            .expect("start");

        let killed = supervisor.stop().expect("stop");

        assert_eq!(killed, vec!["yts-sidecar", "infer-gateway", "llama"]);
        assert_eq!(supervisor.child_count(), 0);
        assert!(!dir.join("run").join("yts-local-supervisor.lock").exists());
    }
}
