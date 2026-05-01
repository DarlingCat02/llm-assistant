use log::{info, error};
use std::process::Command;
use std::sync::Mutex;
use tauri::{Manager, AppHandle, Emitter};

struct AppState {
    python_process: Option<std::process::Child>,
}

#[tauri::command]
fn greet(name: &str) -> String {
    format!("Hello, {}! You've been greeted from Rust!", name)
}

fn start_python_backend(app_handle: AppHandle) {
    info!("Запуск Python бэкенда...");
    
    let python_cmd = if cfg!(windows) { "python" } else { "python3" };
    
    let exe_path = std::env::current_exe().unwrap();
    let binding = exe_path;
    // exe: .../llm-assistant-tauri/src-tauri/target/release/llm-assistant-tauri.exe
    // parent: release -> target -> src-tauri -> llm-assistant-tauri -> llm-assistant
    let project_dir = binding
        .parent().unwrap()
        .parent().unwrap()
        .parent().unwrap()
        .parent().unwrap()
        .parent().unwrap();
    
    info!("Project dir: {:?}", project_dir);
    
    let child = Command::new(python_cmd)
        .args(["-m", "uvicorn", "backend.main:app", "--host", "127.0.0.1", "--port", "8000"])
        .current_dir(project_dir)
        .spawn();
    
    match child {
        Ok(process) => {
            info!("Python бэкенд запущен с PID: {}", process.id());
            app_handle.manage(Mutex::new(AppState {
                python_process: Some(process),
            }));
        }
        Err(e) => {
            error!("Ошибка запуска Python: {}", e);
        }
    }
}

fn setup_global_shortcuts(app: &AppHandle) {
    use tauri_plugin_global_shortcut::{Code, GlobalShortcutExt, Modifiers, Shortcut};
    
    let voice_shortcut = Shortcut::new(Some(Modifiers::CONTROL | Modifiers::SHIFT), Code::KeyV);
    let live_shortcut = Shortcut::new(Some(Modifiers::CONTROL | Modifiers::SHIFT), Code::KeyL);
    
    let app_handle = app.clone();
    app.global_shortcut().on_shortcut(voice_shortcut, move |_app, _shortcut, _event| {
        info!("Горячая клавиша: Voice Input (Ctrl+Shift+V)");
        if let Some(window) = app_handle.get_webview_window("main") {
            let _ = window.emit("hotkey-voice", ());
        }
    }).ok();
    
    let app_handle2 = app.clone();
    app.global_shortcut().on_shortcut(live_shortcut, move |_app, _shortcut, _event| {
        info!("Горячая клавиша: Live Mode (Ctrl+Shift+L)");
        if let Some(window) = app_handle2.get_webview_window("main") {
            let _ = window.emit("hotkey-live", ());
        }
    }).ok();
    
    info!("Горячие клавиши зарегистрированы: Ctrl+Shift+V (голос), Ctrl+Shift+L (live)");
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    env_logger::Builder::from_env(env_logger::Env::default().default_filter_or("info"))
        .init();
    
    info!("Запуск Local AI Assistant...");
    
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_global_shortcut::Builder::new().build())
        .plugin(tauri_plugin_shell::init())
        .setup(|app| {
            info!("Настройка приложения...");
            
            start_python_backend(app.handle().clone());
            setup_global_shortcuts(app.handle());
            
            info!("Приложение готово!");
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![greet])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}