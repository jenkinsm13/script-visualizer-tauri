use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;

use tauri::{Manager, RunEvent};

/// Holds the FastAPI sidecar child process. Killed on app exit.
struct ServerProcess(Mutex<Option<Child>>);

fn repo_root() -> PathBuf {
    // src-tauri lives at <repo>/ui/src-tauri/, so two `..` to get the repo root.
    let mut p = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    p.pop(); // ui/
    p.pop(); // <repo>/
    p
}

fn spawn_server() -> Result<Child, std::io::Error> {
    let root = repo_root();
    let python = std::env::var("SV_PYTHON").unwrap_or_else(|_| "python".to_string());
    Command::new(python)
        .args(["-m", "server"])
        .current_dir(&root)
        .stdout(Stdio::inherit())
        .stderr(Stdio::inherit())
        .spawn()
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let app = tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_opener::init())
        .manage(ServerProcess(Mutex::new(None)))
        .setup(|app| {
            // Don't auto-spawn if user already runs `python -m server` themselves.
            // Convention: set SV_NO_SIDECAR=1 to opt out.
            if std::env::var("SV_NO_SIDECAR").is_err() {
                match spawn_server() {
                    Ok(child) => {
                        let state = app.state::<ServerProcess>();
                        *state.0.lock().unwrap() = Some(child);
                        eprintln!("[tauri] spawned `python -m server`");
                    }
                    Err(e) => {
                        eprintln!(
                            "[tauri] failed to spawn server ({e}); the UI will retry HTTP \
                             until you start it manually with `python -m server`"
                        );
                    }
                }
            } else {
                eprintln!("[tauri] SV_NO_SIDECAR set; not spawning server");
            }
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building tauri application");

    app.run(|app_handle, event| {
        if let RunEvent::ExitRequested { .. } | RunEvent::Exit = event {
            if let Some(state) = app_handle.try_state::<ServerProcess>() {
                if let Some(mut child) = state.0.lock().unwrap().take() {
                    let _ = child.kill();
                    let _ = child.wait();
                    eprintln!("[tauri] reaped sidecar server");
                }
            }
        }
    });
}
