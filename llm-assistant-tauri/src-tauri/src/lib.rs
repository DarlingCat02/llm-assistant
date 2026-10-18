use log::{error, info};
use std::io::{BufRead, BufReader};
use std::process::{Command, Stdio};
use std::sync::atomic::{AtomicU16, Ordering};
use std::sync::{Arc, Mutex};
use tauri::{AppHandle, Emitter, Manager};

/// The port the backend was given, readable before the app state exists.
///
/// The frontend asks for it as soon as the page loads, which can be before
/// start_python_backend has finished registering the state. Keeping it here
/// too means the answer is right in either order.
static BACKEND_PORT: AtomicU16 = AtomicU16::new(8000);

struct AppState {
    python_process: Option<std::process::Child>,
    logs: Arc<Mutex<Vec<String>>>,
    /// Monotonic count of every line ever captured. The buffer is capped, so
    /// the UI cannot use its length to tell how much it already showed - this
    /// counter is what makes a sliding buffer safe to follow.
    total_logs: Arc<std::sync::atomic::AtomicU64>,
    /// Port the backend was actually given, so the frontend can ask instead of
    /// assuming 8000 and failing silently when something else holds it.
    port: u16,
}

const LOG_BUFFER_MAX: usize = 2000;

fn get_show_console(project_dir: &std::path::Path) -> bool {
    let env_path = project_dir.join(".env");
    if let Ok(content) = std::fs::read_to_string(env_path) {
        for line in content.lines() {
            let line = line.trim();
            if line.starts_with("GENERAL_SHOW_BACKEND_CONSOLE") {
                if let Some(val) = line.split('=').nth(1) {
                    return val.trim().to_lowercase() == "true";
                }
            }
        }
    }
    false
}

/// Where the program keeps data that has to survive a reinstall: the user's
/// app-data folder, which is writable even when the app was installed under
/// Program Files.
fn data_dir() -> std::path::PathBuf {
    #[cfg(windows)]
    {
        if let Some(local) = std::env::var_os("LOCALAPPDATA") {
            return std::path::PathBuf::from(local).join("local_assistant");
        }
    }
    #[cfg(not(windows))]
    {
        if let Some(home) = std::env::var_os("HOME") {
            return std::path::PathBuf::from(home).join(".local_assistant");
        }
    }
    std::env::temp_dir().join("local_assistant")
}

/// Walk up from `start` looking for the file that only ever exists in the
/// project: the backend package.
fn find_project_dir(start: &std::path::Path) -> Option<std::path::PathBuf> {
    for dir in start.ancestors() {
        if dir.join("backend").join("main.py").is_file() {
            return Some(dir.to_path_buf());
        }
    }
    None
}

/// The project root.
///
/// This used to count five parent directories up from the exe, which only
/// holds for `<root>\llm-assistant-tauri\src-tauri\target\<profile>\app.exe`
/// and unwrapped at every step: installed under Program Files the fourth
/// `parent()` of `C:\` is `None`, so the app panicked before showing a window -
/// and with no console in a release build, nothing said why. A marker file
/// answers the same question without counting, and works wherever the project
/// was cloned or moved to.
fn project_dir() -> std::path::PathBuf {
    let exe_dir = std::env::current_exe()
        .ok()
        .and_then(|exe| exe.parent().map(|p| p.to_path_buf()));

    if let Some(dir) = exe_dir.as_deref().and_then(find_project_dir) {
        return dir.to_path_buf();
    }

    // The exe was copied or installed away from the project. Check the usual
    // place a source tree lives before giving up on it.
    let mut guesses: Vec<std::path::PathBuf> = Vec::new();
    if let Some(documents) = std::env::var_os("USERPROFILE").or_else(|| std::env::var_os("HOME")) {
        let base = std::path::PathBuf::from(documents);
        guesses.push(base.join("Documents").join("local_assistant"));
        guesses.push(base.join("Desktop").join("local_assistant"));
        guesses.push(base.join("local_assistant"));
        guesses.push(base.clone());
    }
    guesses.push(std::env::current_dir().unwrap_or_else(|_| data_dir()));
    for guess in &guesses {
        if let Some(found) = find_project_dir(guess) {
            return found;
        }
    }

    let fallback = exe_dir.unwrap_or_else(|| data_dir());
    error!(
        "Project folder not found next to the exe; falling back to {:?}. \
         The backend needs the project (backend/, .env, models/) - run the exe \
         from llm-assistant-tauri\\src-tauri\\target\\release\\ inside the project, \
         or see logs/backend.log",
        fallback
    );
    fallback
}

/// The log directory, preferring the project and falling back to app data.
///
/// A project under Program Files cannot be written to, and a wrong project root
/// means `logs/backend.log` is never created at all - which is exactly the file
/// the UI tells the user to go and look at when something fails.
fn logs_dir(project_dir: &std::path::Path) -> std::path::PathBuf {
    let in_project = project_dir.join("logs");
    if std::fs::create_dir_all(&in_project).is_ok() {
        return in_project;
    }
    let fallback = data_dir().join("logs");
    if std::fs::create_dir_all(&fallback).is_ok() {
        error!("Cannot write logs inside the project; using {:?}", fallback);
        return fallback;
    }
    in_project
}

/// Open the log file for appending, or None when even that fails.
fn open_log_file(dir: &std::path::Path) -> Option<Arc<Mutex<std::fs::File>>> {
    use std::fs::OpenOptions;
    std::fs::create_dir_all(dir).ok()?;
    let file = OpenOptions::new()
        .create(true)
        .append(true)
        .open(dir.join("backend.log"))
        .ok()?;
    Some(Arc::new(Mutex::new(file)))
}

/// A free TCP port on the loopback interface.
///
/// The backend port used to be hardcoded, so anything already listening on 8000
/// on another machine left the app with a dead UI and nothing to explain it.
fn free_port() -> u16 {
    std::net::TcpListener::bind(("127.0.0.1", 0))
        .and_then(|l| l.local_addr())
        .map(|addr| addr.port())
        .unwrap_or(8000)
}

fn get_env_value(project_dir: &std::path::Path, key: &str) -> Option<String> {
    let env_path = project_dir.join(".env");
    if let Ok(content) = std::fs::read_to_string(env_path) {
        for line in content.lines() {
            let line = line.trim();
            // Exact KEY= match (so HOTKEY_VOICE does not match HOTKEY_VOICE_NUM)
            if line.len() > key.len() && line.starts_with(key) && line[key.len()..].starts_with('=')
            {
                if let Some(val) = line.split('=').nth(1) {
                    return Some(val.trim().to_string());
                }
            }
        }
    }
    None
}

fn parse_code(p: &str) -> Option<tauri_plugin_global_shortcut::Code> {
    use tauri_plugin_global_shortcut::Code;
    // Single latin letter -> KeyA..KeyZ, single digit -> Digit0..Digit9
    if p.len() == 1 {
        let c = p.chars().next().unwrap();
        if c.is_ascii_alphabetic() {
            return match c {
                'A' => Some(Code::KeyA),
                'B' => Some(Code::KeyB),
                'C' => Some(Code::KeyC),
                'D' => Some(Code::KeyD),
                'E' => Some(Code::KeyE),
                'F' => Some(Code::KeyF),
                'G' => Some(Code::KeyG),
                'H' => Some(Code::KeyH),
                'I' => Some(Code::KeyI),
                'J' => Some(Code::KeyJ),
                'K' => Some(Code::KeyK),
                'L' => Some(Code::KeyL),
                'M' => Some(Code::KeyM),
                'N' => Some(Code::KeyN),
                'O' => Some(Code::KeyO),
                'P' => Some(Code::KeyP),
                'Q' => Some(Code::KeyQ),
                'R' => Some(Code::KeyR),
                'S' => Some(Code::KeyS),
                'T' => Some(Code::KeyT),
                'U' => Some(Code::KeyU),
                'V' => Some(Code::KeyV),
                'W' => Some(Code::KeyW),
                'X' => Some(Code::KeyX),
                'Y' => Some(Code::KeyY),
                'Z' => Some(Code::KeyZ),
                _ => None,
            };
        }
        if c.is_ascii_digit() {
            return match c {
                '0' => Some(Code::Digit0),
                '1' => Some(Code::Digit1),
                '2' => Some(Code::Digit2),
                '3' => Some(Code::Digit3),
                '4' => Some(Code::Digit4),
                '5' => Some(Code::Digit5),
                '6' => Some(Code::Digit6),
                '7' => Some(Code::Digit7),
                '8' => Some(Code::Digit8),
                '9' => Some(Code::Digit9),
                _ => None,
            };
        }
        return None;
    }
    match p {
        "NUM0" | "NUMPAD0" => Some(Code::Numpad0),
        "NUM1" | "NUMPAD1" => Some(Code::Numpad1),
        "NUM2" | "NUMPAD2" => Some(Code::Numpad2),
        "NUM3" | "NUMPAD3" => Some(Code::Numpad3),
        "NUM4" | "NUMPAD4" => Some(Code::Numpad4),
        "NUM5" | "NUMPAD5" => Some(Code::Numpad5),
        "NUM6" | "NUMPAD6" => Some(Code::Numpad6),
        "NUM7" | "NUMPAD7" => Some(Code::Numpad7),
        "NUM8" | "NUMPAD8" => Some(Code::Numpad8),
        "NUM9" | "NUMPAD9" => Some(Code::Numpad9),
        "F1" => Some(Code::F1),
        "F2" => Some(Code::F2),
        "F3" => Some(Code::F3),
        "F4" => Some(Code::F4),
        "F5" => Some(Code::F5),
        "F6" => Some(Code::F6),
        "F7" => Some(Code::F7),
        "F8" => Some(Code::F8),
        "F9" => Some(Code::F9),
        "F10" => Some(Code::F10),
        "F11" => Some(Code::F11),
        "F12" => Some(Code::F12),
        "SPACE" => Some(Code::Space),
        "ENTER" | "RETURN" => Some(Code::Enter),
        "TAB" => Some(Code::Tab),
        "ESC" | "ESCAPE" => Some(Code::Escape),
        "BACKSPACE" => Some(Code::Backspace),
        _ => None,
    }
}

fn parse_shortcut(spec: &str) -> Option<tauri_plugin_global_shortcut::Shortcut> {
    use tauri_plugin_global_shortcut::{Code, Modifiers, Shortcut};
    let mut modifiers = Modifiers::empty();
    let mut code: Option<Code> = None;
    for part in spec.split('+') {
        let p = part.trim().to_uppercase();
        if p.is_empty() {
            return None;
        }
        match p.as_str() {
            "CTRL" | "CONTROL" => modifiers |= Modifiers::CONTROL,
            "SHIFT" => modifiers |= Modifiers::SHIFT,
            "ALT" => modifiers |= Modifiers::ALT,
            "SUPER" | "WIN" | "WINDOWS" | "CMD" | "META" => modifiers |= Modifiers::SUPER,
            _ => {
                if code.is_some() {
                    return None; // two main keys -> invalid
                }
                code = parse_code(&p);
                if code.is_none() {
                    return None;
                }
            }
        }
    }
    let mods = if modifiers.is_empty() {
        None
    } else {
        Some(modifiers)
    };
    Some(Shortcut::new(mods, code?))
}

impl Drop for AppState {
    fn drop(&mut self) {
        if let Some(mut process) = self.python_process.take() {
            info!("Stopping Python process...");
            let _ = process.kill();
        }
    }
}

#[tauri::command]
fn greet(name: &str) -> String {
    format!("Hello, {}! You've been greeted from Rust!", name)
}

/// Read the child's output line by line and forward every line to the in-app
/// terminal.
///
/// Deliberately does NOT use `BufRead::lines()`: it fails with `InvalidData`
/// on the first non-UTF-8 chunk (Windows code pages, tqdm bars, emoji split
/// across reads) and `map_while(Result::ok)` would silently end the pump, so
/// the terminal would freeze after a couple of lines. Reading raw bytes and
/// decoding lossily keeps the stream alive no matter what the backend prints.
fn spawn_log_pump<R>(
    stream: R,
    logs: Arc<Mutex<Vec<String>>>,
    total: Arc<std::sync::atomic::AtomicU64>,
    handle: AppHandle,
    log_file: Option<Arc<Mutex<std::fs::File>>>,
) where
    R: std::io::Read + Send + 'static,
{
    std::thread::spawn(move || {
        let mut reader = BufReader::new(stream);
        let mut buf: Vec<u8> = Vec::new();
        let mut read_errors = 0u32;
        loop {
            buf.clear();
            match reader.read_until(b'\n', &mut buf) {
                Ok(0) => {
                    // EOF: the backend process is gone (crash, or another
                    // instance already holds the port). Say so, otherwise the
                    // terminal just stops mid-output with no explanation.
                    let note = format!(
                        "\n*** backend process exited - output above is final ***"
                    );
                    if let Ok(mut l) = logs.lock() {
                        l.push(note.clone());
                    }
                    total.fetch_add(1, std::sync::atomic::Ordering::Relaxed);
                    if let Some(file) = &log_file {
                        use std::io::Write;
                        if let Ok(mut f) = file.lock() {
                            let _ = writeln!(f, "{}", note);
                            let _ = f.flush();
                        }
                    }
                    let _ = handle.emit("backend-log", note);
                    break;
                }
                Ok(_) => read_errors = 0,
                Err(_) => {
                    // Transient read error: back off instead of dying, otherwise
                    // the terminal stays frozen forever. Give up only if the
                    // handle is really broken.
                    read_errors += 1;
                    if read_errors > 50 {
                        break;
                    }
                    std::thread::sleep(std::time::Duration::from_millis(100));
                    continue;
                }
            }
            // Progress bars (tqdm & co) redraw with '\r' instead of '\n'.
            // Emitting every '\r'-separated chunk keeps the terminal live;
            // waiting for a real newline would glue the whole bar into one
            // huge line that only appears once the download finishes.
            for raw in buf.split(|&b| b == b'\n' || b == b'\r') {
                let line = String::from_utf8_lossy(raw).to_string();
                if line.trim().is_empty() {
                    continue;
                }
                if let Ok(mut l) = logs.lock() {
                    l.push(line.clone());
                    while l.len() > LOG_BUFFER_MAX {
                        l.remove(0);
                    }
                }
                total.fetch_add(1, std::sync::atomic::Ordering::Relaxed);
                // Also on disk. The terminal is only visible once the window
                // opens, and the in-memory buffer is capped - so a backend that
                // dies before anyone looks left no trace of why. Failures here
                // are ignored on purpose: a full disk must not stop the pump
                // and freeze the terminal.
                if let Some(file) = &log_file {
                    use std::io::Write;
                    if let Ok(mut f) = file.lock() {
                        let _ = writeln!(f, "{}", line);
                        let _ = f.flush();
                    }
                }
                // No println!/eprintln! here on purpose: this is a GUI process
                // whose stdout/stderr are not attached to anything, and the
                // write blocks once the (undrained) pipe buffer fills - which
                // wedged this thread and froze the terminal. The line already
                // reaches the user through the event below.
                let _ = handle.emit("backend-log", line);
            }
        }
    });
}

/// Log lines plus the cumulative counter, so a client can follow the capped
/// buffer without missing or repeating lines.
#[tauri::command]
fn get_backend_logs(state: tauri::State<Mutex<AppState>>) -> serde_json::Value {
    use std::sync::atomic::Ordering;
    let payload = state.lock().map(|s| {
        let lines = s.logs.lock().map(|l| l.clone()).unwrap_or_default();
        let total = s.total_logs.load(Ordering::Relaxed);
        serde_json::json!({ "lines": lines, "total": total })
    });
    payload
        .unwrap_or_else(|_| serde_json::json!({ "lines": [], "total": 0 }))
}

#[tauri::command]
fn get_backend_log_total(state: tauri::State<Mutex<AppState>>) -> u64 {
    use std::sync::atomic::Ordering;
    state
        .lock()
        .map(|s| s.total_logs.load(Ordering::Relaxed))
        .unwrap_or(0)
}

#[tauri::command]
fn clear_backend_logs(state: tauri::State<Mutex<AppState>>) {
    if let Ok(s) = state.lock() {
        if let Ok(mut logs) = s.logs.lock() {
            logs.clear();
        }
        // Clear means "start over": reset the counter too, otherwise the UI
        // would think it already missed thousands of lines.
        s.total_logs.store(0, std::sync::atomic::Ordering::Relaxed);
    }
}

fn stop_python_backend(app_handle: &AppHandle) {
    if let Some(state) = app_handle.try_state::<Mutex<AppState>>() {
        if let Ok(mut state) = state.lock() {
            if let Some(mut process) = state.python_process.take() {
                info!("Stopping Python process...");
                let _ = process.kill();
            }
        }
    }
}

fn start_python_backend(app_handle: AppHandle) {
    let project_dir = project_dir();
    info!("Project dir: {:?}", project_dir);

    // Prefer the project's venv python (dependencies installed via install.bat),
    // fall back to system interpreters.
    let mut python_cmds: Vec<String> = Vec::new();
    #[cfg(windows)]
    {
        let venv_python = project_dir.join("venv").join("Scripts").join("python.exe");
        if venv_python.exists() {
            info!("Using venv python: {:?}", venv_python);
            python_cmds.push(venv_python.to_string_lossy().to_string());
        }
    }
    #[cfg(not(windows))]
    {
        let venv_python = project_dir.join("venv").join("bin").join("python3");
        if venv_python.exists() {
            info!("Using venv python: {:?}", venv_python);
            python_cmds.push(venv_python.to_string_lossy().to_string());
        }
    }
    if cfg!(windows) {
        python_cmds.extend([
            "python".to_string(),
            "python3".to_string(),
            "py".to_string(),
        ]);
    } else {
        python_cmds.extend(["python3".to_string(), "python".to_string()]);
    }

    // Try to find a working python command
    let mut python_cmd = None;
    for cmd in &python_cmds {
        let test = Command::new(cmd).arg("--version").output();

        if let Ok(output) = test {
            if output.status.success() {
                info!("Found python: {}", cmd);
                python_cmd = Some(cmd.to_string());
                break;
            }
        }
    }

    let python = match python_cmd {
        Some(cmd) => cmd,
        None => {
            error!("Python not found on system");
            return;
        }
    };

    let show_console = get_show_console(&project_dir);
    let port = free_port();
    BACKEND_PORT.store(port, Ordering::Relaxed);
    info!("Backend port: {}", port);
    let mut cmd = Command::new(&python);
    cmd.args([
        "-m",
        "uvicorn",
        "backend.main:app",
        "--host",
        "127.0.0.1",
        "--port",
        &port.to_string(),
    ])
    .current_dir(&project_dir)
    // `backend.main:app` used to resolve only because the working directory
    // happened to be the project root. Saying so explicitly means the backend
    // still imports if that ever stops being true.
    .env("PYTHONPATH", &project_dir)
    // Without this Python encodes stdout/stderr with the system ANSI code page
    // (cp1251 here), which the log pump then decodes as UTF-8 and turns every
    // Russian log line into unreadable garbage.
    .env("PYTHONUTF8", "1")
    .env("PYTHONIOENCODING", "utf-8")
    .stdout(Stdio::piped())
    .stderr(Stdio::piped());
    #[cfg(windows)]
    if !show_console {
        use std::os::windows::process::CommandExt;
        cmd.creation_flags(0x08000000); // CREATE_NO_WINDOW
    }
    let mut child = match cmd.spawn() {
        Ok(c) => c,
        Err(e) => {
            error!("Failed to start Python: {}", e);
            return;
        }
    };
    let stdout = child.stdout.take();
    let stderr = child.stderr.take();
    let pid = child.id();

    // Fresh log file per run, so the file always describes what is happening now
    // rather than a mixture of old failures. Append mode, not truncate: the
    // Rust-side logger already writes into this same file from startup, and
    // truncating on the backend's start would throw those lines away.
    let log_file = open_log_file(&logs_dir(&project_dir));
    if log_file.is_none() {
        error!("Cannot open logs/backend.log for writing");
    }

    // Reuse the existing log buffer when the backend is restarted, otherwise
    // create one. The pump threads must write into the very same Arc that
    // get_backend_logs reads - swapping it would leave the state pointing at an
    // orphaned buffer and the in-app terminal would go blank after the first
    // lines.
    let (logs, total_logs): (Arc<Mutex<Vec<String>>>, Arc<std::sync::atomic::AtomicU64>) =
        match app_handle.try_state::<Mutex<AppState>>() {
            Some(state) => match state.lock() {
                Ok(s) => (s.logs.clone(), s.total_logs.clone()),
                Err(_) => (
                    Arc::new(Mutex::new(Vec::<String>::new())),
                    Arc::new(std::sync::atomic::AtomicU64::new(0)),
                ),
            },
            None => (
                Arc::new(Mutex::new(Vec::<String>::new())),
                Arc::new(std::sync::atomic::AtomicU64::new(0)),
            ),
        };

    // stdout thread
    if let Some(out) = stdout {
        let logs_clone = logs.clone();
        let total_clone = total_logs.clone();
        let handle_clone = app_handle.clone();
        spawn_log_pump(out, logs_clone, total_clone, handle_clone, log_file.clone());
    }
    // stderr thread
    if let Some(err) = stderr {
        let logs_clone = logs.clone();
        let total_clone = total_logs.clone();
        let handle_clone = app_handle.clone();
        spawn_log_pump(err, logs_clone, total_clone, handle_clone, log_file);
    }
    info!(
        "Python backend started with PID: {} (show_console={})",
        pid, show_console
    );
    // Manage state (if already managed, just swap the child process)
    if let Some(state) = app_handle.try_state::<Mutex<AppState>>() {
        if let Ok(mut s) = state.lock() {
            s.python_process = Some(child);
            s.port = port;
            return;
        }
    }
    app_handle.manage(Mutex::new(AppState {
        python_process: Some(child),
        logs,
        total_logs,
        port,
    }));
}

/// The port the backend was actually given.
///
/// The frontend used to hardcode 8000 in four places. When anything else held
/// that port, the app showed an empty UI with no way to find out why; now the
/// backend picks a free port and the frontend asks for it.
#[tauri::command]
fn backend_port(state: tauri::State<'_, Mutex<AppState>>) -> u16 {
    match state.lock() {
        Ok(s) => s.port,
        // Not registered yet: the static already holds the port that was
        // handed to uvicorn, which is the answer either way.
        Err(_) => BACKEND_PORT.load(Ordering::Relaxed),
    }
}

fn setup_global_shortcuts(app: &AppHandle) {
    use tauri_plugin_global_shortcut::{Code, GlobalShortcutExt, Modifiers, Shortcut};

    // Hotkeys are configurable via .env (HOTKEY_VOICE / HOTKEY_VOICE_NUM / HOTKEY_LIVE),
    // e.g. "Ctrl+Shift+V", "Alt+F9", "F12". Invalid values fall back to defaults.
    let dir = project_dir();
    let voice_spec =
        get_env_value(&dir, "HOTKEY_VOICE").unwrap_or_else(|| "Ctrl+Shift+V".to_string());
    let voice_num0_spec =
        get_env_value(&dir, "HOTKEY_VOICE_NUM").unwrap_or_else(|| "Ctrl+Num0".to_string());
    let live_spec =
        get_env_value(&dir, "HOTKEY_LIVE").unwrap_or_else(|| "Ctrl+Shift+L".to_string());

    let voice_shortcut = parse_shortcut(&voice_spec).unwrap_or_else(|| {
        error!(
            "Invalid HOTKEY_VOICE='{}', falling back to Ctrl+Shift+V",
            voice_spec
        );
        Shortcut::new(Some(Modifiers::CONTROL | Modifiers::SHIFT), Code::KeyV)
    });
    let live_shortcut = parse_shortcut(&live_spec).unwrap_or_else(|| {
        error!(
            "Invalid HOTKEY_LIVE='{}', falling back to Ctrl+Shift+L",
            live_spec
        );
        Shortcut::new(Some(Modifiers::CONTROL | Modifiers::SHIFT), Code::KeyL)
    });
    let voice_num0_shortcut = parse_shortcut(&voice_num0_spec).unwrap_or_else(|| {
        error!(
            "Invalid HOTKEY_VOICE_NUM='{}', falling back to Ctrl+Num0",
            voice_num0_spec
        );
        Shortcut::new(Some(Modifiers::CONTROL), Code::Numpad0)
    });

    let app_handle = app.clone();
    let voice_spec_log = voice_spec.clone();
    if let Err(e) =
        app.global_shortcut()
            .on_shortcut(voice_shortcut, move |_app, _shortcut, _event| {
                info!("Hotkey: Voice Input ({})", voice_spec_log);
                if let Some(window) = app_handle.get_webview_window("main") {
                    let _ = window.emit("hotkey-voice", ());
                }
            })
    {
        error!("Failed to register {}: {:?}", voice_spec, e);
    }

    let app_handle2 = app.clone();
    let live_spec_log = live_spec.clone();
    if let Err(e) =
        app.global_shortcut()
            .on_shortcut(live_shortcut, move |_app, _shortcut, _event| {
                info!("Hotkey: Live Mode ({})", live_spec_log);
                if let Some(window) = app_handle2.get_webview_window("main") {
                    let _ = window.emit("hotkey-live", ());
                }
            })
    {
        error!("Failed to register {}: {:?}", live_spec, e);
    }

    // Second shortcut for voice input
    let app_handle3 = app.clone();
    let voice_num0_spec_log = voice_num0_spec.clone();
    if let Err(e) =
        app.global_shortcut()
            .on_shortcut(voice_num0_shortcut, move |_app, _shortcut, _event| {
                info!("Hotkey: Voice Input ({})", voice_num0_spec_log);
                if let Some(window) = app_handle3.get_webview_window("main") {
                    let _ = window.emit("hotkey-voice", ());
                }
            })
    {
        error!("Failed to register {}: {:?}", voice_num0_spec, e);
    }

    info!(
        "Global shortcuts registered: {}, {} (voice), {} (live)",
        voice_spec, voice_num0_spec, live_spec
    );
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    // Start from a clean log, then send this app's own messages to the same
    // file as the backend's. env_logger writes to stderr, and a release build
    // has no console (main.rs sets windows_subsystem), so "Python not found"
    // and "cannot open the log file" went nowhere at all - on another machine
    // every failure of the launcher was invisible.
    let log_dir = logs_dir(&project_dir());
    let _ = std::fs::OpenOptions::new()
        .create(true)
        .write(true)
        .truncate(true)
        .open(log_dir.join("backend.log"));

    let mut builder = env_logger::Builder::from_env(
        env_logger::Env::default().default_filter_or("info"),
    );
    // Its own handle, in append mode: env_logger keeps writing for the whole
    // run, while the backend's pump appends through a shared lock.
    match std::fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(log_dir.join("backend.log"))
    {
        Ok(file) => {
            // target() mutates in place and returns &mut Builder.
            builder.target(env_logger::Target::Pipe(Box::new(file)));
        }
        Err(e) => {
            eprintln!("cannot open {}: {}", log_dir.join("backend.log").display(), e);
        }
    }
    let _ = builder.try_init();

    info!("Starting Local AI Assistant...");
    info!("Log file: {}", log_dir.join("backend.log").display());

    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_global_shortcut::Builder::new().build())
        .plugin(tauri_plugin_shell::init())
        .setup(|app| {
            info!("Setting up application...");
            start_python_backend(app.handle().clone());
            setup_global_shortcuts(app.handle());
            info!("Application ready!");
            Ok(())
        })
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::CloseRequested { .. } = event {
                info!("Closing application...");
                stop_python_backend(window.app_handle());
            }
        })
        .invoke_handler(tauri::generate_handler![
            greet,
            backend_port,
            get_backend_logs,
            get_backend_log_total,
            clear_backend_logs
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
