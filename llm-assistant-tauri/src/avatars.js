// === Avatars ===
// Custom user/bot avatars: preset emoji or an uploaded image (avatars/ folder).

import { t, getLang } from './i18n.js';
import { apiBase } from './api-base.js';

const AVATAR_STORE_KEY = 'lai_avatars';

// Local escaper (avatars.js is a separate module and cannot use app.js helpers)
function esc(str) {
    const d = document.createElement('div');
    d.textContent = String(str == null ? '' : str);
    return d.innerHTML;
}
const AVATAR_PRESETS = {
    user: ['👤', '🧑', '👩', '🧔', '🤖', '🐱', '🦊', '🐼', '😎', '🧠'],
    bot: ['🤖', '👾', '🧠', '🐱', '🦊', '🐼', '👽', '🔮', '🧙', '😎'],
};
const AVATAR_DEFAULT = { user: '👤', bot: '🤖' };

let avatarCurrentRole = null;
let avatarUploaded = [];

function avatarLoadStore() {
    try {
        return JSON.parse(localStorage.getItem(AVATAR_STORE_KEY)) || {};
    } catch (e) {
        return {};
    }
}

function avatarSaveStore(store) {
    try {
        localStorage.setItem(AVATAR_STORE_KEY, JSON.stringify(store));
    } catch (e) {
        console.warn('Не удалось сохранить аватары:', e);
    }
}

// Returns the stored value for a role: emoji char or {file: name}
export function getAvatar(role) {
    const store = avatarLoadStore();
    const val = store[role];
    if (val && typeof val === 'object' && val.file) return val;
    if (typeof val === 'string' && val) return val;
    return AVATAR_DEFAULT[role];
}

function setAvatar(role, value) {
    const store = avatarLoadStore();
    store[role] = value;
    avatarSaveStore(store);
    avatarRefreshHeader();
    // Ask the app to re-render messages so avatars update in the chat
    window.dispatchEvent(new CustomEvent('lai:avatar-changed', { detail: { role } }));
}

export function avatarHtml(role) {
    const val = getAvatar(role);
    if (typeof val === 'object' && val.file) {
        // The file may have been deleted outside the app -> fall back to the emoji
        return `<img src="${apiBase()}/api/avatars/${encodeURIComponent(val.file)}"
                     alt="" class="avatar-img"
                     onerror="this.onerror=null;this.outerHTML='${AVATAR_DEFAULT[role]}'">`;
    }
    return esc(val);
}

// Drop references to avatars that no longer exist on disk
function avatarPruneMissing(list) {
    const store = avatarLoadStore();
    let changed = false;
    ['user', 'bot'].forEach(role => {
        const val = store[role];
        if (val && typeof val === 'object' && val.file
            && !list.some(a => a.name === val.file)) {
            store[role] = AVATAR_DEFAULT[role];
            changed = true;
        }
    });
    if (changed) avatarSaveStore(store);
}

function avatarRefreshHeader() {
    ['user', 'bot'].forEach(role => {
        const btn = document.getElementById(`${role}-avatar-btn`);
        if (btn) btn.innerHTML = avatarHtml(role);
    });
}

async function avatarFetchUploaded() {
    try {
        const resp = await fetch(`${apiBase()}/api/avatars`);
        if (!resp.ok) return [];
        const data = await resp.json();
        return Array.isArray(data.avatars) ? data.avatars : [];
    } catch (e) {
        console.warn('Не удалось получить список аватаров:', e);
        return [];
    }
}

function openAvatarMenu(role) {
    avatarCurrentRole = role;
    const menu = document.getElementById('avatar-menu');
    if (!menu) return;

    const isRu = getLang() === 'ru';
    document.getElementById('avatar-menu-title').textContent =
        role === 'user' ? (isRu ? 'Аватар пользователя' : 'User avatar')
                        : (isRu ? 'Аватар ассистента' : 'Assistant avatar');

    const presets = document.getElementById('avatar-menu-presets');
    presets.innerHTML = AVATAR_PRESETS[role].map(e =>
        `<button class="avatar-preset" data-emoji="${e}">${e}</button>`
    ).join('');

    menu.classList.remove('hidden');
    avatarFetchUploaded().then(list => {
        avatarUploaded = list;
        renderAvatarUploaded();
        positionAvatarMenu();
    });
}

function renderAvatarUploaded() {
    const box = document.getElementById('avatar-menu-uploaded');
    if (!box) return;
    if (!avatarUploaded.length) {
        box.innerHTML = `<div class="avatar-empty">${getLang() === 'ru' ? 'Загруженных нет' : 'No uploads yet'}</div>`;
        return;
    }
    const current = getAvatar(avatarCurrentRole);
    const currentFile = (typeof current === 'object' && current.file) ? current.file : null;
    box.innerHTML = avatarUploaded.map(a =>
        `<button class="avatar-uploaded-item${a.name === currentFile ? ' active' : ''}"
                 data-file="${esc(a.name)}" title="${esc(a.name)}">
            <img src="${apiBase()}/api/avatars/${encodeURIComponent(a.name)}" alt="">
         </button>`
    ).join('');
}

function positionAvatarMenu() {
    const menu = document.getElementById('avatar-menu');
    const btn = document.getElementById(`${avatarCurrentRole}-avatar-btn`);
    if (!menu || !btn) return;
    const r = btn.getBoundingClientRect();
    menu.style.left = `${Math.max(8, Math.min(r.left, window.innerWidth - 258))}px`;
    const h = menu.offsetHeight || 240;
    // Prefer above the button; fall back to below when there is no room
    if (r.top - h - 8 >= 0) {
        menu.style.top = 'auto';
        menu.style.bottom = `${window.innerHeight - r.top + 6}px`;
    } else {
        menu.style.bottom = 'auto';
        menu.style.top = `${Math.min(r.bottom + 6, window.innerHeight - h - 8)}px`;
    }
}

function closeAvatarMenu() {
    const menu = document.getElementById('avatar-menu');
    if (menu) menu.classList.add('hidden');
    avatarCurrentRole = null;
}

async function avatarUpload(file) {
    const isRu = getLang() === 'ru';
    if (!file) return;
    const form = new FormData();
    form.append('file', file);
    try {
        const resp = await fetch(`${apiBase()}/api/avatars`, { method: 'POST', body: form });
        const data = await resp.json().catch(() => null);
        if (!resp.ok) {
            alert(isRu ? `Ошибка загрузки: ${(data && data.detail) || resp.status}`
                       : `Upload failed: ${(data && data.detail) || resp.status}`);
            return;
        }
        setAvatar(avatarCurrentRole, { file: data.name });
        avatarUploaded = await avatarFetchUploaded();
        renderAvatarUploaded();
    } catch (e) {
        alert(isRu ? `Ошибка загрузки: ${e}` : `Upload failed: ${e}`);
    }
}

async function avatarDeleteSelected() {
    const isRu = getLang() === 'ru';
    const cur = getAvatar(avatarCurrentRole);
    if (typeof cur !== 'object' || !cur.file) {
        alert(isRu ? 'Выбран эмодзи — удалять нечего' : 'Emoji selected — nothing to delete');
        return;
    }
    try {
        const resp = await fetch(`${apiBase()}/api/avatars/${encodeURIComponent(cur.file)}`,
                                 { method: 'DELETE' });
        if (!resp.ok) throw new Error(resp.status);
        setAvatar(avatarCurrentRole, AVATAR_DEFAULT[avatarCurrentRole]);
        avatarUploaded = await avatarFetchUploaded();
        renderAvatarUploaded();
    } catch (e) {
        alert(isRu ? `Не удалось удалить: ${e}` : `Delete failed: ${e}`);
    }
}

export function initAvatars() {
    avatarRefreshHeader();

    // Drop references to files that are gone, then repaint
    avatarFetchUploaded().then(list => {
        avatarUploaded = list;
        avatarPruneMissing(list);
        avatarRefreshHeader();
    });

    ['user', 'bot'].forEach(role => {
        const btn = document.getElementById(`${role}-avatar-btn`);
        if (btn) btn.addEventListener('click', (e) => {
            e.stopPropagation();
            openAvatarMenu(role);
        });
    });

    const presets = document.getElementById('avatar-menu-presets');
    if (presets) {
        presets.addEventListener('click', (e) => {
            const btn = e.target.closest('.avatar-preset');
            if (!btn) return;
            setAvatar(avatarCurrentRole, btn.dataset.emoji);
        });
    }

    const uploaded = document.getElementById('avatar-menu-uploaded');
    if (uploaded) {
        uploaded.addEventListener('click', (e) => {
            const btn = e.target.closest('.avatar-uploaded-item');
            if (!btn) return;
            setAvatar(avatarCurrentRole, { file: btn.dataset.file });
            renderAvatarUploaded();
        });
    }

    const fileInput = document.getElementById('avatar-file-input');
    if (fileInput) {
        fileInput.addEventListener('change', (e) => {
            const f = e.target.files && e.target.files[0];
            e.target.value = '';
            avatarUpload(f);
        });
    }

    const resetBtn = document.getElementById('avatar-reset-btn');
    if (resetBtn) {
        resetBtn.addEventListener('click', () => {
            setAvatar(avatarCurrentRole, AVATAR_DEFAULT[avatarCurrentRole]);
            renderAvatarUploaded();
        });
    }

    const delBtn = document.getElementById('avatar-delete-btn');
    if (delBtn) delBtn.addEventListener('click', avatarDeleteSelected);

    document.addEventListener('click', (e) => {
        const menu = document.getElementById('avatar-menu');
        if (!menu || menu.classList.contains('hidden')) return;
        if (menu.contains(e.target)) return;
        if (e.target.closest('.avatar-btn')) return;
        closeAvatarMenu();
    });
}