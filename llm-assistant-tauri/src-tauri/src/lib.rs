use log::{error, info};
use std::io::{BufRead, BufReader};
use std::process::{Command, Stdio};
use std::sync::{Arc, Mutex};
use tauri::{AppHandle, Emitter, Manager};

struct AppState {
    python_process: Option<std::process::Child>,
    logs: Arc<Mutex<Vec<String>>>,
}

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

fn project_dir() -> std::path::PathBuf {
    let exe_path = std::env::current_exe().unwrap();
    let binding = exe_path;
    binding
        .parent()
        .unwrap()
        .parent()
        .unwrap()
        .parent()
        .unwrap()
        .parent()
        .unwrap()
        .parent()
        .unwrap()
        .to_path_buf()
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
fn spawn_log_pump<R>(stream: R, logs: Arc<Mutex<Vec<String>>>, handle: AppHandle, to_stderr: bool)
where
    R: std::io::Read + Send + 'static,
{
    std::thread::spawn(move || {
        let mut reader = BufReader::new(stream);
        let mut buf: Vec<u8> = Vec::new();
        let mut read_errors = 0u32;
        loop {
            buf.clear();
            match reader.read_until(b'\n', &mut buf) {
                Ok(0) => break, // EOF
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
                    if l.len() > 2000 {
                        l.remove(0);
                    }
                }
                let _ = handle.emit("backend-log", line.clone());
                if to_stderr {
                    eprintln!("{}", line);
                } else {
                    println!("{}", line);
                }
            }
        }
    });
}

#[tauri::command]
fn get_backend_logs(state: tauri::State<Mutex<AppState>>) -> Vec<String> {
    state
        .lock()
        .map(|s| s.logs.lock().map(|l| l.clone()).unwrap_or_default())
        .unwrap_or_default()
}

#[tauri::command]
fn clear_backend_logs(state: tauri::State<Mutex<AppState>>) {
    if let Ok(s) = state.lock() {
        if let Ok(mut logs) = s.logs.lock() {
            logs.clear();
        }
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
    info!("Starting Python backend...");

    let exe_path = std::env::current_exe().unwrap();
    let binding = exe_path;
    let project_dir = binding
        .parent()
        .unwrap()
        .parent()
        .unwrap()
        .parent()
        .unwrap()
        .parent()
        .unwrap()
        .parent()
        .unwrap()
        .to_path_buf();

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
    let mut cmd = Command::new(&python);
    cmd.args([
        "-m",
        "uvicorn",
        "backend.main:app",
        "--host",
        "127.0.0.1",
        "--port",
        "8000",
    ])
    .current_dir(project_dir)
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

    // Reuse the existing log buffer when the backend is restarted, otherwise
    // create one. The pump threads must write into the very same Arc that
    // get_backend_logs reads - swapping it would leave the state pointing at an
    // orphaned buffer and the in-app terminal would go blank after the first
    // lines.
    let logs: Arc<Mutex<Vec<String>>> = match app_handle.try_state::<Mutex<AppState>>() {
        Some(state) => match state.lock() {
            Ok(s) => s.logs.clone(),
            Err(_) => Arc::new(Mutex::new(Vec::<String>::new())),
        },
        None => Arc::new(Mutex::new(Vec::<String>::new())),
    };

    // stdout thread
    if let Some(out) = stdout {
        let logs_clone = logs.clone();
        let handle_clone = app_handle.clone();
        spawn_log_pump(out, logs_clone, handle_clone, false);
    }
    // stderr thread
    if let Some(err) = stderr {
        let logs_clone = logs.clone();
        let handle_clone = app_handle.clone();
        spawn_log_pump(err, logs_clone, handle_clone, true);
    }
    info!(
        "Python backend started with PID: {} (show_console={})",
        pid, show_console
    );
    // Manage state (if already managed, just swap the child process)
    if let Some(state) = app_handle.try_state::<Mutex<AppState>>() {
        if let Ok(mut s) = state.lock() {
            s.python_process = Some(child);
            return;
        }
    }
    app_handle.manage(Mutex::new(AppState {
        python_process: Some(child),
        logs,
    }));
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
    env_logger::Builder::from_env(env_logger::Env::default().default_filter_or("info")).init();

    info!("Starting Local AI Assistant...");

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
            get_backend_logs,
            clear_backend_logs
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
