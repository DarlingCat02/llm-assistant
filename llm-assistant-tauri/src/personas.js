// === Personas ===
// Catalog of behaviour presets with runtime switching.
// No persona selected -> the standard system prompt is used.

import { t, getLang } from './i18n.js';

const API = 'http://127.0.0.1:8000';

export const personasState = {
    personas: [],
    active: null,
    loaded: false,
};

function esc(str) {
    const d = document.createElement('div');
    d.textContent = String(str == null ? '' : str);
    return d.innerHTML;
}

function avatarImg(persona, size = 20) {
    if (persona && persona.avatar) {
        return `<img src="${API}/api/avatars/${encodeURIComponent(persona.avatar)}"
                     class="avatar-img" style="width:${size}px;height:${size}px" alt="">`;
    }
    return '<span class="persona-emoji">🎭</span>';
}

export async function loadPersonas() {
    try {
        const resp = await fetch(`${API}/api/personas`);
        if (!resp.ok) throw new Error(resp.status);
        const data = await resp.json();
        personasState.personas = Array.isArray(data.personas) ? data.personas : [];
        personasState.active = data.active || null;
        personasState.loaded = true;
        return personasState;
    } catch (e) {
        console.warn('Не удалось загрузить персон:', e);
        personasState.personas = [];
        personasState.active = null;
        personasState.loaded = true;
        return personasState;
    }
}

export async function savePersonas(personas, active) {
    const resp = await fetch(`${API}/api/personas`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ personas, active }),
    });
    const data = await resp.json().catch(() => null);
    if (!resp.ok) {
        throw new Error((data && data.detail) || resp.status);
    }
    await loadPersonas();
    renderPersonaSelector();
    renderPersonaSettings();
    return data;
}

export async function activatePersona(id) {
    const resp = await fetch(`${API}/api/personas/activate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id: id || null }),
    });
    const data = await resp.json().catch(() => null);
    if (!resp.ok) {
        throw new Error((data && data.detail) || resp.status);
    }
    personasState.active = data.active || null;
    renderPersonaSelector();
    renderPersonaSettings();
    return personasState.active;
}

// === Header selector ===

let menuOpen = false;

export function renderPersonaSelector() {
    const btn = document.getElementById('persona-btn');
    if (!btn) return;
    const persona = personasState.personas.find((p) => p.id === personasState.active);
    btn.innerHTML = `${avatarImg(persona, 18)}<span class="persona-btn-name">${
        persona ? esc(persona.name) : esc(t('persona.none'))
    }</span><span class="persona-caret">▾</span>`;
    btn.title = t('persona.switch');
}

function renderMenu() {
    const menu = document.getElementById('persona-menu');
    if (!menu) return;
    const isRu = getLang() === 'ru';
    const rows = personasState.personas.map((p) => {
        const active = p.id === personasState.active;
        return `<button class="persona-item${active ? ' active' : ''}" data-id="${esc(p.id)}">
            ${avatarImg(p, 20)}
            <span class="persona-item-name">${esc(p.name)}</span>
            ${active ? '<span class="persona-check">✓</span>' : ''}
        </button>`;
    }).join('');
    const noneActive = !personasState.active;
    menu.innerHTML = `
        <div class="persona-menu-header">${esc(t('persona.catalog'))}</div>
        <button class="persona-item${noneActive ? ' active' : ''}" data-id="">
            <span class="persona-emoji">🤖</span>
            <span class="persona-item-name">${esc(t('persona.none'))}</span>
            ${noneActive ? '<span class="persona-check">✓</span>' : ''}
        </button>
        <div class="persona-menu-list">${rows}</div>
        <div class="persona-menu-footer">
            <button class="persona-manage-btn" id="persona-manage-btn">${esc(t('persona.manage'))}</button>
        </div>`;
}

export function togglePersonaMenu() {
    const menu = document.getElementById('persona-menu');
    if (!menu) return;
    menuOpen = menu.classList.contains('hidden');
    if (menuOpen) {
        renderMenu();
        menu.classList.remove('hidden');
        positionMenu();
    } else {
        menu.classList.add('hidden');
    }
}

function positionMenu() {
    const menu = document.getElementById('persona-menu');
    const btn = document.getElementById('persona-btn');
    if (!menu || !btn) return;
    const r = btn.getBoundingClientRect();
    menu.style.left = `${Math.max(8, Math.min(r.left, window.innerWidth - 240))}px`;
    const h = menu.offsetHeight || 260;
    if (r.bottom + h + 8 <= window.innerHeight) {
        menu.style.top = `${r.bottom + 6}px`;
        menu.style.bottom = 'auto';
    } else {
        menu.style.bottom = `${window.innerHeight - r.top + 6}px`;
        menu.style.top = 'auto';
    }
}

export function closePersonaMenu() {
    const menu = document.getElementById('persona-menu');
    if (menu) menu.classList.add('hidden');
    menuOpen = false;
}

async function onMenuClick(e) {
    const item = e.target.closest('.persona-item');
    if (item) {
        const id = item.dataset.id || null;
        closePersonaMenu();
        try {
            await activatePersona(id);
        } catch (err) {
            console.error('Не удалось переключить персону:', err);
            alert(getLang() === 'ru' ? `Ошибка переключения: ${err.message}` : `Switch failed: ${err.message}`);
        }
        return;
    }
    if (e.target.closest('#persona-manage-btn')) {
        closePersonaMenu();
        const tabBtn = document.querySelector('.settings-tab[data-tab="personas"]');
        if (tabBtn) tabBtn.click();
        document.getElementById('settings-modal').classList.remove('hidden');
        renderPersonaSettings();
    }
}

// === Settings: catalog editor ===

let editingId = null;

export function renderPersonaSettings() {
    const list = document.getElementById('persona-list');
    if (!list) return;

    if (!personasState.personas.length) {
        list.innerHTML = `<div class="persona-empty">${esc(t('persona.empty'))}</div>`;
    } else {
        list.innerHTML = personasState.personas.map((p) => {
            const active = p.id === personasState.active;
            return `<div class="persona-card${active ? ' active' : ''}" data-id="${esc(p.id)}">
                <div class="persona-card-head">${avatarImg(p, 28)}<b>${esc(p.name)}</b>
                    <code>${esc(p.id)}</code>
                    ${active ? `<span class="badge">${esc(t('persona.active'))}</span>` : ''}
                </div>
                <div class="persona-card-actions">
                    <button class="btn-secondary" data-act="select" data-id="${esc(p.id)}">${
                        active ? esc(t('persona.selected')) : esc(t('persona.select'))}</button>
                    <button class="btn-secondary" data-act="edit" data-id="${esc(p.id)}">✎</button>
                    <button class="btn-secondary" data-act="copy" data-id="${esc(p.id)}">⧉</button>
                    <button class="btn-secondary" data-act="delete" data-id="${esc(p.id)}">🗑</button>
                </div>
            </div>`;
        }).join('');
    }
    renderPersonaEditor();
}

function renderPersonaEditor() {
    const editor = document.getElementById('persona-editor');
    if (!editor) return;
    if (!editingId) {
        editor.classList.add('hidden');
        return;
    }
    const p = personasState.personas.find((x) => x.id === editingId);
    if (!p) {
        editingId = null;
        editor.classList.add('hidden');
        return;
    }
    editor.classList.remove('hidden');
    document.getElementById('persona-form-name').value = p.name || '';
    document.getElementById('persona-form-id').value = p.id || '';
    document.getElementById('persona-form-id').disabled = true;
    document.getElementById('persona-form-ru').value = p.prompt_ru || '';
    document.getElementById('persona-form-en').value = p.prompt_en || '';
    document.getElementById('persona-form-temp').value =
        (p.temperature === null || p.temperature === undefined) ? '' : p.temperature;
}

function openEditor(id) {
    editingId = id;
    renderPersonaEditor();
}

async function handleSettingsClick(e) {
    const btn = e.target.closest('button[data-act]');
    if (!btn) return;
    const act = btn.dataset.act;
    const id = btn.dataset.id;
    const p = personasState.personas.find((x) => x.id === id);

    if (act === 'select') {
        try { await activatePersona(id); } catch (err) { console.error(err); alert(String(err.message || err)); }
    } else if (act === 'edit') {
        openEditor(id);
    } else if (act === 'copy') {
        if (!p) return;
        const copy = { ...p };
        copy.id = `${p.id}-copy`;
        let n = 2;
        while (personasState.personas.some((x) => x.id === copy.id)) {
            copy.id = `${p.id}-copy${n++}`;
        }
        try { await savePersonas([...personasState.personas, copy], personasState.active); openEditor(copy.id); }
        catch (err) { alert(String(err.message || err)); }
    } else if (act === 'delete') {
        if (!p) return;
        if (!confirm(getLang() === 'ru' ? `Удалить персону «${p.name}»?` : `Delete persona "${p.name}"?`)) return;
        const rest = personasState.personas.filter((x) => x.id !== id);
        const active = personasState.active === id ? null : personasState.active;
        try {
            await savePersonas(rest, active);
            if (editingId === id) editingId = null;
            renderPersonaEditor();
        } catch (err) { alert(String(err.message || err)); }
    }
}

async function handleEditorClick(e) {
    const btn = e.target.closest('button[data-editor-act]');
    if (!btn) return;
    const act = btn.dataset.editorAct;
    const name = document.getElementById('persona-form-name').value.trim();
    const ru = document.getElementById('persona-form-ru').value;
    const en = document.getElementById('persona-form-en').value;
    const tempRaw = document.getElementById('persona-form-temp').value.trim();
    const temperature = tempRaw === '' ? null : parseFloat(tempRaw);

    if (act === 'save') {
        if (!name) { alert(getLang() === 'ru' ? 'Укажите имя персоны' : 'Persona name is required'); return; }
        if (Number.isNaN(temperature)) { alert(getLang() === 'ru' ? 'Температура должна быть числом 0.0-2.0' : 'Temperature must be a number 0.0-2.0'); return; }
        const idx = personasState.personas.findIndex((x) => x.id === editingId);
        const updated = { id: editingId, name, prompt_ru: ru, prompt_en: en, temperature,
                          avatar: (personasState.personas[idx] || {}).avatar || null };
        const list = [...personasState.personas];
        if (idx >= 0) list[idx] = updated; else list.push(updated);
        try {
            await savePersonas(list, personasState.active);
            editingId = null;
            renderPersonaEditor();
        } catch (err) { alert(String(err.message || err)); }
    } else if (act === 'cancel') {
        editingId = null;
        renderPersonaEditor();
    }
}

function newPersona() {
    let id = 'persona';
    let n = 1;
    while (personasState.personas.some((x) => x.id === id)) id = `persona${++n}`;
    personasState.personas.push({
        id, name: t('persona.newName'), avatar: null,
        prompt_ru: '', prompt_en: '', temperature: null,
    });
    editingId = id;
    renderPersonaSettings();
}

export async function initPersonas() {
    await loadPersonas();
    renderPersonaSelector();

    const btn = document.getElementById('persona-btn');
    if (btn) btn.addEventListener('click', (e) => { e.stopPropagation(); togglePersonaMenu(); });

    const menu = document.getElementById('persona-menu');
    if (menu) menu.addEventListener('click', (e) => { e.stopPropagation(); onMenuClick(e); });

    document.addEventListener('click', () => { if (menuOpen) closePersonaMenu(); });

    const list = document.getElementById('persona-list');
    if (list) list.addEventListener('click', handleSettingsClick);

    const editor = document.getElementById('persona-editor');
    if (editor) editor.addEventListener('click', handleEditorClick);

    const addBtn = document.getElementById('persona-add-btn');
    if (addBtn) addBtn.addEventListener('click', newPersona);

    renderPersonaSettings();
}