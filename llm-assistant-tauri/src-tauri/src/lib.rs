use log::{info, error};
use std::process::Command;
use std::sync::Mutex;
use tauri::{Manager, AppHandle, Emitter};

struct AppState {
    python_process: Option<std::process::Child>,
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
    
    let child = Command::new(&python)
        .args(["-m", "uvicorn", "backend.main:app", "--host", "127.0.0.1", "--port", "8000"])
        .current_dir(project_dir)
        .spawn();
    
    match child {
        Ok(process) => {
            info!("Python backend started with PID: {}", process.id());
            app_handle.manage(Mutex::new(AppState {
                python_process: Some(process),
            }));
        }
        Err(e) => {
            error!("Failed to start Python: {}", e);
        }
    }
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
        .invoke_handler(tauri::generate_handler![greet])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}