use log::{info, error};
use std::io::{BufRead, BufReader};
use std::process::{Command, Stdio};
use std::sync::{Arc, Mutex};
use tauri::{Manager, AppHandle, Emitter};

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

#[tauri::command]
fn get_backend_logs(state: tauri::State<Mutex<AppState>>) -> Vec<String> {
    state.lock().map(|s| s.logs.lock().map(|l| l.clone()).unwrap_or_default()).unwrap_or_default()
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
    
    // На Windows пробуем разные варианты python
    let python_cmds = if cfg!(windows) {
        vec!["python", "python3", "py"]
    } else {
        vec!["python3", "python"]
    };
    
    let exe_path = std::env::current_exe().unwrap();
    let binding = exe_path;
    let project_dir = binding
        .parent().unwrap()
        .parent().unwrap()
        .parent().unwrap()
        .parent().unwrap()
        .parent().unwrap();
    
    info!("Project dir: {:?}", project_dir);
    
    // Пробуем найти рабочую команду python
    let mut python_cmd = None;
    for cmd in &python_cmds {
        let test = Command::new(cmd)
            .arg("--version")
            .output();
        
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
    
    let show_console = get_show_console(project_dir);
    let mut cmd = Command::new(&python);
    cmd.args(["-m", "uvicorn", "backend.main:app", "--host", "127.0.0.1", "--port", "8000"])
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
    let logs = Arc::new(Mutex::new(Vec::<String>::new()));
    let logs_clone = logs.clone();
    let handle_clone = app_handle.clone();
    // stdout thread
    if let Some(out) = stdout {
        std::thread::spawn(move || {
            let reader = BufReader::new(out);
            for line in reader.lines().map_while(Result::ok) {
                {
                    let mut l = logs_clone.lock().unwrap();
                    l.push(line.clone());
                    if l.len() > 2000 { l.remove(0); }
                }
                let _ = handle_clone.emit("backend-log", line.clone());
                println!("{}", line);
            }
        });
    }
    let logs_clone2 = logs.clone();
    let handle_clone2 = app_handle.clone();
    if let Some(err) = stderr {
        std::thread::spawn(move || {
            let reader = BufReader::new(err);
            for line in reader.lines().map_while(Result::ok) {
                {
                    let mut l = logs_clone2.lock().unwrap();
                    l.push(line.clone());
                    if l.len() > 2000 { l.remove(0); }
                }
                let _ = handle_clone2.emit("backend-log", line.clone());
                eprintln!("{}", line);
            }
        });
    }
    info!("Python backend started with PID: {} (show_console={})", pid, show_console);
    // Manage state (if already managed, replace)
    if app_handle.try_state::<Mutex<AppState>>().is_some() {
        if let Some(state) = app_handle.try_state::<Mutex<AppState>>() {
            if let Ok(mut s) = state.lock() {
                s.python_process = Some(child);
                s.logs = logs;
                return;
            }
        }
    }
    app_handle.manage(Mutex::new(AppState {
        python_process: Some(child),
        logs,
    }));
}

fn setup_global_shortcuts(app: &AppHandle) {
    use tauri_plugin_global_shortcut::{Code, GlobalShortcutExt, Modifiers, Shortcut};
    
    let voice_shortcut = Shortcut::new(Some(Modifiers::CONTROL | Modifiers::SHIFT), Code::KeyV);
    let live_shortcut = Shortcut::new(Some(Modifiers::CONTROL | Modifiers::SHIFT), Code::KeyL);
    let voice_num0_shortcut = Shortcut::new(Some(Modifiers::CONTROL), Code::Numpad0);
    
    let app_handle = app.clone();
    if let Err(e) = app.global_shortcut().on_shortcut(voice_shortcut, move |_app, _shortcut, _event| {
        info!("Hotkey: Voice Input (Ctrl+Shift+V)");
        if let Some(window) = app_handle.get_webview_window("main") {
            let _ = window.emit("hotkey-voice", ());
        }
    }) {
        error!("Failed to register Ctrl+Shift+V: {:?}", e);
    }
    
    let app_handle2 = app.clone();
    if let Err(e) = app.global_shortcut().on_shortcut(live_shortcut, move |_app, _shortcut, _event| {
        info!("Hotkey: Live Mode (Ctrl+Shift+L)");
        if let Some(window) = app_handle2.get_webview_window("main") {
            let _ = window.emit("hotkey-live", ());
        }
    }) {
        error!("Failed to register Ctrl+Shift+L: {:?}", e);
    }
    
    // Ctrl+Num0 для голосового ввода
    let app_handle3 = app.clone();
    if let Err(e) = app.global_shortcut().on_shortcut(voice_num0_shortcut, move |_app, _shortcut, _event| {
        info!("Hotkey: Voice Input (Ctrl+Num0)");
        if let Some(window) = app_handle3.get_webview_window("main") {
            let _ = window.emit("hotkey-voice", ());
        }
    }) {
        error!("Failed to register Ctrl+Num0: {:?}", e);
    }
    
    info!("Global shortcuts registered: Ctrl+Shift+V, Ctrl+Num0 (voice), Ctrl+Shift+L (live)");
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    env_logger::Builder::from_env(env_logger::Env::default().default_filter_or("info"))
        .init();
    
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
        .invoke_handler(tauri::generate_handler![greet, get_backend_logs, clear_backend_logs])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}