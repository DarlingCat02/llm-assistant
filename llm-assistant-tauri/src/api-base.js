// Where the backend lives, in one place.
//
// The address used to be written out four times - app.js, i18n.js, avatars.js
// and personas.js - so changing it meant editing four files and the ones you
// forgot failed on their own: i18n.js swallowed the error and quietly fell back
// to English, avatars.js only warned in the console.
//
// Inside the desktop app the port is not a constant anyway: the Rust side picks
// a free one (something else on another machine may already hold 8000) and
// answers backend_port. Outside the app - the browser against a manually
// started uvicorn - the default is what a plain `python -m uvicorn
// backend.main:app` listens on.

let base = 'http://127.0.0.1:8000';
let resolved = false;

export function apiBase() {
    return base;
}

export function wsBase() {
    return base.replace(/^http/, 'ws');
}

// Resolves the address once. Call it before the first request; later callers
// get the same answer, so nothing races over which port is in use.
export async function ensureApiBase() {
    if (resolved) return base;
    resolved = true;

    try {
        if (window.__TAURI__) {
            const { invoke } = await import('@tauri-apps/api/core');
            const port = await invoke('backend_port');
            if (typeof port === 'number' && port > 0 && port < 65536) {
                base = `http://127.0.0.1:${port}`;
            }
        }
    } catch (error) {
        // No answer from the app: keep the default rather than leaving the UI
        // pointing nowhere.
        console.warn('Could not read the backend port, using 8000:', error);
    }
    return base;
}