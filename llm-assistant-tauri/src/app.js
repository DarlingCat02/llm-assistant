/**
 * Local AI Assistant - Frontend Application
 * 
 * Architecture:
 * - API-first: primary backend calls go through the REST API
 * - WebSocket for real-time events
 * - Voice input via Web Audio API + STT
 */

import { initI18n, t, setLanguage, getLang } from './i18n.js';
import { initAvatars, avatarHtml } from './avatars.js';
import { initPersonas, renderPersonaSettings, loadPersonas, renderPersonaSelector } from './personas.js';

const API_BASE = 'http://127.0.0.1:8000';
let currentChatId = null;
let ws = null;
let initialSettings = null;

// === Tauri Hotkeys ===
let isTauri = false;
try {
    isTauri = typeof window !== 'undefined' && window.__TAURI__ !== undefined;
    if (isTauri) {
        console.log('Запуск в Tauri режиме');
        import('@tauri-apps/api/event').then(({ listen }) => {
            listen('hotkey-voice', () => {
                console.log('Горячая клавиша: Голосовой ввод');
                toggleVoiceRecording();
            });
            listen('hotkey-live', () => {
                console.log('Горячая клавиша: Live режим');
                toggleLiveMode();
            });
        }).catch(e => console.error('Tauri events error:', e));
    }
} catch (e) {
    console.log('Запуск в браузере (не Tauri)');
}

// === Initialization ===

async function waitForApi(retries = 90, delay = 1000) {
    for (let i = 0; i < retries; i++) {
        try {
            const response = await fetch(`${API_BASE}/api/status`, { method: 'GET' });
            if (response.ok) {
                const data = await response.json().catch(() => null);
                // Older backends have no assistant_ready flag - treat as ready
                if (!data || data.assistant_ready !== false) return true;
                console.log(`Backend is up, waiting for assistant... (${i + 1}/${retries})`);
            }
        } catch (e) {
            console.log(`Ожидание API... (${i + 1}/${retries})`);
        }
        await new Promise(r => setTimeout(r, delay));
    }
    console.error('API не доступно');
    return false;
}

document.addEventListener('DOMContentLoaded', async () => {
    try { await initI18n(); } catch {}
    console.log('Ожидание готовности Python бэкенда...');
    const ready = await waitForApi();
    if (ready) {
        console.log('API готово, загрузка...');
        initAvatars();
        initPersonas();
        window.addEventListener('lai:avatar-changed', () => {
            if (currentChatId) loadChatMessages(currentChatId);
        });
        initEventListeners();
        loadChats();
        connectWebSocket();
        updateStatus();
    } else {
        document.getElementById('messages-container').innerHTML = 
            `<div class="error">${t('chat.error.backend')}</div>`;
    }
});

function initEventListeners() {
    // Resize sidebar
    const resizeHandle = document.getElementById('resize-handle');
    const sidebar = document.querySelector('.sidebar');
    if (resizeHandle && sidebar) {
        let isResizing = false;
        resizeHandle.addEventListener('mousedown', (e) => {
            isResizing = true;
            document.body.style.cursor = 'col-resize';
            document.body.style.userSelect = 'none';
        });
        document.addEventListener('mousemove', (e) => {
            if (!isResizing) return;
            const newWidth = Math.min(Math.max(e.clientX, 200), 500);
            sidebar.style.width = newWidth + 'px';
        });
        document.addEventListener('mouseup', () => {
            isResizing = false;
            document.body.style.cursor = '';
            document.body.style.userSelect = '';
        });
    }

    // Buttons
    document.getElementById('new-chat-btn').addEventListener('click', createNewChat);
    document.getElementById('send-btn').addEventListener('click', sendMessage);
    
    // Files
    document.getElementById('file-input').addEventListener('change', handleFileSelect);
    document.getElementById('file-remove').addEventListener('click', clearFile);
    
    // Remove individual files from previews (event delegation)
    document.getElementById('file-previews').addEventListener('click', (e) => {
        if (e.target.classList.contains('file-remove')) {
            const index = parseInt(e.target.dataset.index);
            if (!isNaN(index)) {
                attachedFiles.splice(index, 1);
                // Re-render the previews
                const previewsContainer = document.getElementById('file-previews');
                previewsContainer.innerHTML = '';
                attachedFiles.forEach((f, i) => {
                    const item = document.createElement('div');
                    item.className = 'file-preview-item';
                    if (f.type === 'image') {
                        item.innerHTML = `
                            <img src="data:${f.mime};base64,${f.base64}" alt="${f.name}">
                            <span class="file-name">${f.name}</span>
                            <button class="file-remove" data-index="${i}">✕</button>
                        `;
                    } else {
                        item.innerHTML = `
                            <span class="file-name">📄 ${f.name} (${f.charCount} ${getLang()==='ru'?'симв.':'chars'})</span>
                            <button class="file-remove" data-index="${i}">✕</button>
                        `;
                    }
                    document.getElementById('file-previews').appendChild(item);
                });
                if (!attachedFiles.length) {
                    document.getElementById('file-preview').classList.add('hidden');
                }
            }
        }
    });
    document.getElementById('search-ddg-toggle').addEventListener('change', (e) => {
        if (e.target.checked) {
            document.getElementById('search-searxng-toggle').checked = false;
        }
    });

    document.getElementById('voice-btn').addEventListener('click', toggleVoiceRecording);
    document.getElementById('tts-toggle').addEventListener('change', async (e) => {
        const enabled = e.target.checked;
        console.log('TTS переключено:', enabled);

        // Show/hide the TTS options
        const ttsOptions = document.getElementById('tts-options');
        if (ttsOptions) {
            ttsOptions.style.display = enabled ? 'flex' : 'none';
        }

        // Block double-clicks: model (un)loading takes tens of seconds
        e.target.disabled = true;
        try {
            const response = await fetch(`${API_BASE}/api/tts/toggle`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(enabled),
            });
            const data = await response.json();
            console.log('TTS статус:', data);

            // Backend reports the real state - do not leave the switch ON if load failed
            if (enabled && !data.omnivoice_loaded) {
                e.target.checked = false;
                if (ttsOptions) ttsOptions.style.display = 'none';
                alert(t('alert.ttsLoadFailed') + (data.error ? ': ' + data.error : ''));
                return;
            }

            // Load voices for cloning
            if (enabled) await loadTTSVoices();

        } catch (err) {
            console.error('Ошибка переключения TTS:', err);
            e.target.checked = !enabled;
        } finally {
            e.target.disabled = false;
        }
    });
    
    // Load voices on startup
    loadTTSVoices();
    
    // TTS mode switching (synthesis/cloning)
    document.querySelectorAll('input[name="tts-mode"]').forEach(radio => {
        radio.addEventListener('change', async (e) => {
            const mode = e.target.value;
            const voiceSelect = document.getElementById('tts-voice-select');
            const cloneSelect = document.getElementById('tts-clone-select');
            
            if (mode === 'clone') {
                voiceSelect.style.display = 'none';
                cloneSelect.style.display = 'block';
                
                // Load voices if not loaded yet
                if (cloneSelect.options.length === 1 && cloneSelect.options[0].value === '') {
                    await loadTTSVoices();
                }
            } else {
                voiceSelect.style.display = 'block';
                cloneSelect.style.display = 'none';
            }
            
            await updateTTSConfig();
        });
    });
    
    // Voice selection in synthesis mode
    document.getElementById('tts-voice-select').addEventListener('change', async (e) => {
        await updateTTSConfig();
    });
    
    // Voice selection in cloning mode
    document.getElementById('tts-clone-select').addEventListener('change', async (e) => {
        await updateTTSConfig();
    });
    
    document.getElementById('clear-chat-btn').addEventListener('click', clearChat);
    document.getElementById('delete-chat-btn').addEventListener('click', deleteChat);
    document.getElementById('memory-btn').addEventListener('click', toggleMemoryPanel);
    document.getElementById('status-btn').addEventListener('click', showStatus);
    document.getElementById('settings-btn').addEventListener('click', openSettings);
    document.getElementById('close-memory-btn').addEventListener('click', toggleMemoryPanel);
    document.getElementById('memory-search-btn').addEventListener('click', searchMemory);
    document.getElementById('memory-add-btn').addEventListener('click', addMemoryEntry);
    document.getElementById('close-status-btn').addEventListener('click', hideStatus);
    document.getElementById('close-settings-btn').addEventListener('click', closeSettings);
    document.getElementById('save-settings-btn').addEventListener('click', saveSettings);
    document.getElementById('provider-select').addEventListener('change', onProviderChange);
    const termBtn = document.getElementById('terminal-btn');
    if (termBtn) termBtn.addEventListener('click', toggleTerminalPanel);
    const termClose = document.getElementById('terminal-close-btn');
    if (termClose) termClose.addEventListener('click', () => document.getElementById('terminal-panel').classList.add('hidden'));
    const termClear = document.getElementById('terminal-clear-btn');
    if (termClear) termClear.addEventListener('click', clearTerminal);
    const termCopy = document.getElementById('terminal-copy-btn');
    if (termCopy) termCopy.addEventListener('click', copyTerminal);
    // Listen for backend logs from Rust
    if (isTauri) {
        import('@tauri-apps/api/event').then(({ listen }) => {
            listen('backend-log', (e) => appendTerminal(e.payload));
        }).catch(()=>{});
        // Load existing logs
        import('@tauri-apps/api/core').then(({ invoke }) => {
            invoke('get_backend_logs').then(lines => lines.forEach(appendTerminal)).catch(()=>{});
        }).catch(()=>{});
    }
    const langSel = document.getElementById('lang-select');
    if (langSel) {
        langSel.value = getLang();
        langSel.addEventListener('change', async (e) => {
            await setLanguage(e.target.value);
        });
    }
    
    // Enter to send
    document.getElementById('message-input').addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });
    
    // Memory search on Enter
    document.getElementById('memory-search-input').addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            searchMemory();
        }
    });
    
    // Add entry on Enter
    document.getElementById('memory-add-input').addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            addMemoryEntry();
        }
    });
}

// === WebSocket ===

function connectWebSocket() {
    // Use the same host as the page
    const wsUrl = `ws://${window.location.host}/ws/events`;
    console.log('Подключение к WebSocket:', wsUrl);
    
    ws = new WebSocket(wsUrl);
    
    ws.onopen = () => {
        console.log('WebSocket подключён');
        updateConnectionStatus(true);
    };
    
    ws.onclose = () => {
        console.log('WebSocket отключён');
        updateConnectionStatus(false);
        // Reconnect in 5 seconds
        setTimeout(connectWebSocket, 5000);
    };
    
    ws.onerror = (error) => {
        console.error('WebSocket ошибка:', error);
    };
    
    ws.onmessage = (event) => {
        console.log('Получено WebSocket сообщение:', event.data);
        const data = JSON.parse(event.data);
        handleWebSocketMessage(data);
    };
}

function handleWebSocketMessage(data) {
    console.log('WebSocket сообщение:', data);
    
    // Responses are rendered via the HTTP response in sendMessage().
    // WebSocket is reserved here for future real-time notifications.
}

function updateConnectionStatus(connected) {
    const statusBtn = document.getElementById('status-btn');
    if (connected) {
        statusBtn.textContent = t('status.connected');
    } else {
        statusBtn.textContent = t('status.disconnected');
    }
}

// === Chats ===

async function loadChats() {
    try {
        const response = await fetch(`${API_BASE}/api/chats`);
        const chats = await response.json();
        
        const chatsList = document.getElementById('chats-list');
        chatsList.innerHTML = '';
        
        chats.forEach(chat => {
            const chatEl = createChatElement(chat);
            chatsList.appendChild(chatEl);
        });
    } catch (error) {
        console.error('Ошибка загрузки чатов:', error);
    }
}

function createChatElement(chat) {
    const div = document.createElement('div');
    div.className = 'chat-item';
    if (chat.id === currentChatId) {
        div.classList.add('active');
    }
    
    const date = new Date(chat.updated_at);
    const dateStr = date.toLocaleDateString(getLang()==='ru'?'ru-RU':'en-US', {
        day: 'numeric',
        month: 'short',
        hour: '2-digit',
        minute: '2-digit',
    });
    
    div.innerHTML = `
        <div class="chat-item-title" data-chat-id="${chat.id}">${escapeHtml(chat.title)}</div>
        <div class="chat-item-date">${dateStr}</div>
    `;
    
    // Click selects the chat
    div.addEventListener('click', (e) => {
        if (!e.target.classList.contains('chat-item-title') || !e.target.contentEditable) {
            selectChat(chat.id);
        }
    });
    
    // Double-click renames the chat
    const titleEl = div.querySelector('.chat-item-title');
    titleEl.addEventListener('dblclick', (e) => {
        e.stopPropagation();
        const chatId = parseInt(e.target.dataset.chatId);
        startRenameChat(chatId, e.target);
    });
    
    return div;
}

async function startRenameChat(chatId, element) {
    element.contentEditable = true;
    element.focus();
    
    // Select all text
    const range = document.createRange();
    range.selectNodeContents(element);
    const sel = window.getSelection();
    sel.removeAllRanges();
    sel.addRange(range);
    
    const finishRename = async () => {
        element.contentEditable = false;
        const newTitle = element.textContent.trim();
        
        if (newTitle && newTitle !== element.dataset.originalTitle) {
            try {
                await fetch(`${API_BASE}/api/chats/${chatId}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ title: newTitle }),
                });
                await loadChats();
            } catch (error) {
                console.error('Ошибка переименования:', error);
            }
        } else {
            element.textContent = element.dataset.originalTitle;
        }
    };
    
    element.dataset.originalTitle = element.textContent;
    
    element.addEventListener('blur', finishRename, { once: true });
    element.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            element.blur();
        }
        if (e.key === 'Escape') {
            element.textContent = element.dataset.originalTitle;
            element.blur();
        }
    });
}

async function createNewChat() {
    try {
        const response = await fetch(`${API_BASE}/api/chats`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ title: t('sidebar.newChat') }),
        });
        
        const chat = await response.json();
        await loadChats();
        selectChat(chat.id);
    } catch (error) {
        console.error('Ошибка создания чата:', error);
    }
}

async function selectChat(chatId) {
    currentChatId = chatId;
    
    // Show the context indicator
    const ctxIndicator = document.getElementById('context-indicator');
    if (ctxIndicator) ctxIndicator.style.display = 'flex';
    
    // Update the selection highlight
    document.querySelectorAll('.chat-item').forEach(el => {
        el.classList.remove('active');
    });
    
    // Load messages
    await loadChatMessages(chatId);
    
    // Update the title
    document.getElementById('chat-title').textContent = `${getLang()==='ru'?'Чат':'Chat'} #${chatId}`;
    
    // Reset the context indicator (it updates after the next response)
    updateContextIndicator(0, 8192);
}

async function loadChatMessages(chatId) {
    try {
        const response = await fetch(`${API_BASE}/api/chats/${chatId}/messages`);
        const messages = await response.json();
        
        const container = document.getElementById('messages-container');
        container.innerHTML = '';
        
        messages.forEach(msg => {
            appendMessage(msg.role, msg.content, msg.created_at);
        });
        
        scrollToBottom();
    } catch (error) {
        console.error('Ошибка загрузки сообщений:', error);
    }
}

async function deleteChat() {
    if (!currentChatId) return;
    
    if (!confirm(t('confirm.deleteChat'))) return;
    
    try {
        await fetch(`${API_BASE}/api/chats/${currentChatId}`, {
            method: 'DELETE',
        });
        
        currentChatId = null;
        document.getElementById('chat-title').textContent = t('chat.select');
        // Hide the context indicator
        const ctxIndicator = document.getElementById('context-indicator');
        if (ctxIndicator) ctxIndicator.style.display = 'none';
        document.getElementById('messages-container').innerHTML = `
            <div class="welcome-message">
                <h2>${t('chat.welcome.title')}</h2>
                <p>${t('chat.welcome.subtitle')}</p>
            </div>
        `;
        
        await loadChats();
    } catch (error) {
        console.error('Ошибка удаления чата:', error);
    }
}

async function clearChat() {
    if (!currentChatId) return;
    
    if (!confirm(t('confirm.clearChat'))) return;
    
    try {
        await fetch(`${API_BASE}/api/chats/${currentChatId}/messages`, {
            method: 'DELETE',
        });
        
        document.getElementById('messages-container').innerHTML = '';
        updateContextIndicator(0, 8192);
    } catch (error) {
        console.error('Ошибка очистки чата:', error);
    }
}

// === Messages ===

let attachedFiles = []; // {type: 'document'|'image', name, text?, base64?, mime, width, height}

async function handleFileSelect(e) {
    const files = Array.from(e.target.files);
    if (!files.length) return;
    
    const previewsContainer = document.getElementById('file-previews');
    const filePreview = document.getElementById('file-preview');
    
    for (const file of files) {
        try {
            const formData = new FormData();
            formData.append('file', file);
            
            const response = await fetch(`${API_BASE}/api/upload`, { method: 'POST', body: formData });
            
            if (!response.ok) {
                const err = await response.json();
                throw new Error(err.detail || t('alert.fileUpload'));
            }
            
            const data = await response.json();
            
            if (data.type === 'image') {
                attachedFiles.push({
                    type: 'image',
                    name: file.name,
                    base64: data.base64,
                    mime: data.mime_type,
                    width: data.width,
                    height: data.height
                });
                
                // Create a preview
                const item = document.createElement('div');
                item.className = 'file-preview-item';
                item.innerHTML = `
                    <img src="data:${data.mime};base64,${data.base64}" alt="${file.name}">
                    <span class="file-name">${file.name}</span>
                    <button class="file-remove" data-index="${attachedFiles.length - 1}">✕</button>
                `;
                previewsContainer.appendChild(item);
            } else {
                attachedFiles.push({
                    type: 'document',
                    name: file.name,
                    text: data.text,
                    charCount: data.char_count
                });
                
                // Create a preview for the document
                const item = document.createElement('div');
                item.className = 'file-preview-item';
                item.innerHTML = `
                    <span class="file-name">📄 ${file.name} (${data.char_count} ${getLang()==='ru'?'симв.':'chars'})</span>
                    <button class="file-remove" data-index="${attachedFiles.length - 1}">✕</button>
                `;
                previewsContainer.appendChild(item);
            }
            
            filePreview.classList.remove('hidden');
            
        } catch (error) {
            console.error('Ошибка загрузки файла:', error);
            alert(t('alert.error', {msg: error.message}));
        }
    }
    
    e.target.value = '';
}

function clearFile() {
    attachedFiles = [];
    document.getElementById('file-input').value = '';
    document.getElementById('file-previews').innerHTML = '';
    document.getElementById('file-preview').classList.add('hidden');
}

async function sendMessage() {
    const input = document.getElementById('message-input');
    const message = input.value.trim();
    
    if (!message && !attachedFiles.length) return;
    
    // Build the final message with files
    let fullMessage = message;
    const docTexts = attachedFiles
        .filter(f => f.type === 'document')
        .map(f => `[${getLang()==='ru'?'ФАЙЛ':'FILE'}: ${f.name}]\n${f.text}\n[${getLang()==='ru'?'КОНЕЦ ФАЙЛА':'END OF FILE'}]`)
        .join('\n\n');
    
    if (docTexts) {
        fullMessage = message 
            ? `${message}\n\n${docTexts}`
            : docTexts;
    }
    
    // Collect image base64 payloads for sending
    const imageBases = attachedFiles
        .filter(f => f.type === 'image')
        .map(f => f.base64);
    
    // Save file info for the UI before clearing
    const filesCount = attachedFiles.length;
    const hasImages = imageBases.length > 0;
    const hasDocs = docTexts.length > 0;
    
    // Clear the input field and files
    input.value = '';
    input.style.height = 'auto';
    
    // Keep the current files for sending
    const imagesToSend = [...imageBases];
    const docsToSend = attachedFiles.filter(f => f.type === 'document');
    clearFile();
    
    // Append the user message (using the saved counts)
    appendMessage('user', message || (filesCount > 0 ? `📎 ${t('chat.file.count', {count: filesCount})}` : '')
        ? `${message}\n\n${hasDocs ? `📄 ${t('chat.file.docs', {names: docsToSend.map(f => f.name).join(', ')})}` : ''}${hasImages ? (hasDocs ? ', ' : '') + `🖼️ ${t('chat.file.images', {count: imageBases.length})}` : ''}`
        : (filesCount > 0 ? `📎 ${t('chat.file.count', {count: filesCount})}` : ''));
    showTypingIndicator();
    
    // Send to the server
    try {
        const thinkingToggle = document.getElementById('thinking-toggle');
        const thinkingEnabled = thinkingToggle ? thinkingToggle.checked : false;
        const searchDdg = document.getElementById('search-ddg-toggle');
        let searchProvider = '';
        if (searchDdg && searchDdg.checked) searchProvider = 'ddg';

        const response = await fetch(`${API_BASE}/api/chat`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                message: fullMessage,
                chat_id: currentChatId,
                thinking: thinkingEnabled,
                search: searchProvider,
                images: imagesToSend,
            }),
        });
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || t('alert.sendError'));
        }
        
        const data = await response.json();
        
        // If this is the first message in a new chat, update currentChatId
        if (!currentChatId) {
            currentChatId = data.chat_id;
            document.getElementById('chat-title').textContent = `${getLang()==='ru'?'Чат':'Chat'} #${currentChatId}`;
            await loadChats();
        }
        
        // Render the response from the HTTP response
        appendMessage('assistant', data.response, null, data.actions || null);
        hideTypingIndicator();
        
        // Update the context indicator
        updateContextIndicator(data.used_context_tokens, data.max_context_tokens);
        
        // TTS - speak the response if enabled
        const ttsToggle = document.getElementById('tts-toggle');
        if (ttsToggle && ttsToggle.checked) {
            playTTS(data.response);
        }
        
    } catch (error) {
        console.error('Ошибка отправки:', error);
        hideTypingIndicator();
        appendMessage('assistant', `❌ ${t('alert.error', {msg: error.message})}`);
    }
}

function renderActions(actions) {
    // Minimal collapsible list of tool calls executed during this turn
    if (!Array.isArray(actions) || actions.length === 0) return '';
    const rows = actions.map((a) => {
        const args = a.arguments || {};
        const argText = Object.entries(args)
            .map(([k, v]) => `${k}=${typeof v === 'string' ? v : JSON.stringify(v)}`)
            .join(', ');
        const short = argText.length > 120 ? argText.slice(0, 120) + '…' : argText;
        const ok = a.ok !== false;
        const preview = escapeHtml(a.result_preview || '');
        return `<div class="action-row${ok ? '' : ' action-error'}">
            <span class="action-icon">${ok ? '🔧' : '⚠️'}</span>
            <span class="action-name">${escapeHtml(a.name || 'tool')}</span>
            ${short ? `<span class="action-args">${escapeHtml(short)}</span>` : ''}
            ${preview ? `<span class="action-result">→ ${preview}</span>` : ''}
        </div>`;
    }).join('');
    return `<details class="actions-block">
        <summary class="actions-summary">${t('chat.actions.title')} (${actions.length})</summary>
        <div class="actions-list">${rows}</div>
    </details>`;
}

function appendMessage(role, content, timestamp = null, actions = null) {
    const container = document.getElementById('messages-container');
    
    // Remove the welcome message if present
    const welcome = container.querySelector('.welcome-message');
    if (welcome) {
        welcome.remove();
    }
    
    const div = document.createElement('div');
    div.className = `message ${role}`;
    
    const avatar = avatarHtml(role === 'user' ? 'user' : 'bot');
    const time = timestamp 
        ? new Date(timestamp).toLocaleTimeString(getLang()==='ru'?'ru-RU':'en-US', { hour: '2-digit', minute: '2-digit' })
        : new Date().toLocaleTimeString(getLang()==='ru'?'ru-RU':'en-US', { hour: '2-digit', minute: '2-digit' });
    
    div.innerHTML = `
        <div class="message-avatar">${avatar}</div>
        <div class="message-content">
            ${role === 'assistant' ? renderActions(actions) : ''}
            <div class="message-text">${escapeHtml(content)}</div>
            <div class="message-time">${time}</div>
        </div>
    `;
    
    container.appendChild(div);
    scrollToBottom();
}

function showTypingIndicator() {
    document.getElementById('typing-indicator').classList.remove('hidden');
    scrollToBottom();
}

function hideTypingIndicator() {
    document.getElementById('typing-indicator').classList.add('hidden');
}

function updateContextIndicator(usedTokens, maxTokens) {
    const indicator = document.getElementById('context-indicator');
    const fill = document.getElementById('context-bar-fill');
    const label = document.getElementById('context-label');
    if (!indicator || !fill || !label) return;

    const pct = maxTokens > 0 ? Math.min(usedTokens / maxTokens * 100, 100) : 0;
    fill.style.width = pct + '%';
    label.textContent = `${usedTokens} / ${maxTokens}`;
    indicator.style.display = 'flex';
}

function scrollToBottom() {
    const container = document.getElementById('messages-container');
    container.scrollTop = container.scrollHeight;
}

// === Memory ===

function toggleMemoryPanel() {
    const panel = document.getElementById('memory-panel');
    const isHidden = panel.classList.toggle('hidden');
    
    // If the panel was opened, load all entries
    if (!isHidden) {
        loadAllMemoryEntries();
    }
}

async function loadAllMemoryEntries() {
    const resultsDiv = document.getElementById('memory-results');
    resultsDiv.innerHTML = `<p>${t('memory.loading')}</p>`;
    
    try {
        const response = await fetch(`${API_BASE}/api/memory`);
        const data = await response.json();
        
        resultsDiv.innerHTML = '';
        
        if (!data.entries || data.entries.length === 0) {
            resultsDiv.innerHTML = `<p>${t('memory.empty')}</p>`;
            return;
        }
        
        resultsDiv.innerHTML = `<p style="color: gray; margin-bottom: 10px;">${t('memory.count', {count: data.total})}</p>`;
        
        data.entries.forEach(entry => {
            const div = document.createElement('div');
            div.className = 'memory-entry';
            div.innerHTML = `
                <div class="memory-entry-text">${escapeHtml(entry.text)}</div>
                <div class="memory-entry-meta">
                    <span>${t('memory.type', {type: entry.metadata?.type || 'general'})}</span>
                    <button class="btn-icon" onclick="deleteMemoryEntry('${entry.id}')" title="${t('memory.delete')}">🗑️</button>
                </div>
            `;
            resultsDiv.appendChild(div);
        });
        
    } catch (error) {
        console.error('Ошибка загрузки:', error);
        resultsDiv.innerHTML = `<p>${t('alert.error', {msg: error.message})}</p>`;
    }
}

async function searchMemory() {
    const input = document.getElementById('memory-search-input');
    const query = input.value.trim();
    
    if (!query) return;
    
    const resultsDiv = document.getElementById('memory-results');
    resultsDiv.innerHTML = `<p>${t('memory.searching')}</p>`;
    
    try {
        const response = await fetch(`${API_BASE}/api/memory/search`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ query: query, limit: 20 }),
        });
        
        const data = await response.json();
        
        resultsDiv.innerHTML = '';
        
        if (!data.results || data.results.length === 0) {
            resultsDiv.innerHTML = `<p>${t('memory.notFound')}</p>`;
            return;
        }
        
        data.results.forEach(entry => {
            const div = document.createElement('div');
            div.className = 'memory-entry';
            div.innerHTML = `
                <div class="memory-entry-text">${escapeHtml(entry.text)}</div>
                <div class="memory-entry-meta">
                    <span>${t('memory.similarity', {score: (entry.score * 100).toFixed(1)})}</span>
                    <button class="btn-icon" onclick="deleteMemoryEntry('${entry.id}')" title="${t('memory.delete')}">🗑️</button>
                </div>
            `;
            resultsDiv.appendChild(div);
        });
        
    } catch (error) {
        console.error('Ошибка поиска:', error);
        resultsDiv.innerHTML = `<p>${t('alert.error', {msg: error.message})}</p>`;
    }
}

async function deleteMemoryEntry(entryId) {
    if (!confirm(t('memory.confirmDelete'))) return;
    
    try {
        const response = await fetch(`${API_BASE}/api/memory/${entryId}`, {
            method: 'DELETE',
        });
        
        if (!response.ok) {
            const error = await response.json();
            alert(t('alert.error', {msg: error.detail || t('memory.errorDelete')}));
            return;
        }
        
        // Reload the entry list
        loadAllMemoryEntries();
    } catch (error) {
        console.error('Ошибка удаления:', error);
        alert(t('alert.error', {msg: error.message}));
    }
}

async function addMemoryEntry() {
    const input = document.getElementById('memory-add-input');
    const text = input.value.trim();
    
    if (!text) return;
    
    try {
        const response = await fetch(`${API_BASE}/api/memory`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text: text }),
        });
        
        if (!response.ok) {
            const error = await response.json();
            alert(t('alert.error', {msg: error.detail || t('memory.errorAdd')}));
            return;
        }
        
        input.value = '';
        loadAllMemoryEntries();
    } catch (error) {
        console.error('Ошибка добавления:', error);
        alert(t('alert.error', {msg: error.message}));
    }
}

// === Status ===

async function showStatus() {
    const modal = document.getElementById('status-modal');
    const content = document.getElementById('status-content');
    
    // Attach the close-button handler immediately, before fetch
    const closeBtn = document.getElementById('close-status-btn');
    if (closeBtn) {
        closeBtn.onclick = hideStatus;
    }
    
    content.innerHTML = `<p>${t('status.loading')}</p>`;
    modal.classList.remove('hidden');
    
    try {
        const response = await fetch(`${API_BASE}/api/status`);
        const data = await response.json();
        
        content.innerHTML = `
            <p><strong>${t('status.status')}</strong> ${data.status}</p>
            <p><strong>${t('status.provider')}</strong> ${data.provider}</p>
            <p><strong>${t('status.model')}</strong> ${data.model}</p>
            <p><strong>${t('status.chats')}</strong> ${data.chats_count || 0}</p>
            <p><strong>${t('status.memory')}</strong> ${data.memory_entries || 0}</p>
        `;
    } catch (error) {
        content.innerHTML = `<p>${t('alert.error', {msg: error.message})}</p>`;
    }
}

function hideStatus() {
    const modal = document.getElementById('status-modal');
    if (modal) {
        modal.classList.add('hidden');
    }
}

function showToast(message, type = 'success', duration = 3000) {
    const container = document.getElementById('toast-container');
    if (!container) { alert(message); return; }
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.innerHTML = `<span>${escapeHtml(message)}</span><button class="toast-close">✕</button>`;
    const closeBtn = toast.querySelector('.toast-close');
    let timer = setTimeout(() => {
        toast.style.animation = 'toastOut 0.3s forwards';
        setTimeout(() => toast.remove(), 300);
    }, duration);
    closeBtn.addEventListener('click', () => {
        clearTimeout(timer);
        toast.remove();
    });
    container.appendChild(toast);
}

// === Terminal ===
function toggleTerminalPanel() {
    const panel = document.getElementById('terminal-panel');
    if (panel) panel.classList.toggle('hidden');
}
function appendTerminal(line) {
    const pre = document.getElementById('terminal-log');
    if (!pre) return;
    pre.textContent += line + '\n';
    const lines = pre.textContent.split('\n');
    if (lines.length > 2000) pre.textContent = lines.slice(-2000).join('\n');
    pre.scrollTop = pre.scrollHeight;
}
async function clearTerminal() {
    const pre = document.getElementById('terminal-log');
    if (pre) pre.textContent = '';
    try {
        const { invoke } = await import('@tauri-apps/api/core');
        await invoke('clear_backend_logs');
    } catch {}
}
async function copyTerminal() {
    const pre = document.getElementById('terminal-log');
    if (pre) {
        try { await navigator.clipboard.writeText(pre.textContent); } catch {}
    }
}

// === Settings ===
async function openSettings() {
    const modal = document.getElementById('settings-modal');
    modal.classList.remove('hidden');
    
    // Load the current settings
    try {
        const response = await fetch(`${API_BASE}/api/config`);
        const config = await response.json();
        
        const langSel = document.getElementById('lang-select');
        if (langSel) {
            langSel.value = getLang();
        }
        const consoleToggle = document.getElementById('show-console-toggle');
        if (consoleToggle) consoleToggle.checked = !!config.show_backend_console;

        // Personality layer
        const pRu = document.getElementById('personality-ru-input');
        const pEn = document.getElementById('personality-en-input');
        if (pRu) pRu.value = config.personality_ru || '';
        if (pEn) pEn.value = config.personality_en || '';
        updatePersonalityCounters();
        
        document.getElementById('provider-select').value = config.provider || 'ollama';
        document.getElementById('ollama-host-input').value = config.ollama_host || 'http://localhost:11434';
        document.getElementById('api-key-input').value = config.api_key || '';
        
        // Context (log2 for the slider)
        const numCtx = config.num_ctx || 8192;
        const logVal = Math.round(Math.log2(numCtx));
        document.getElementById('num-ctx-slider').value = logVal;
        document.getElementById('num-ctx-value').textContent = numCtx;
        
        // Temperature
        const temp = config.temperature || 0.7;
        document.getElementById('temperature-slider').value = Math.round(temp * 10);
        document.getElementById('temperature-value').textContent = temp;
        
        // TTS
        document.getElementById('tts-steps-slider').value = config.tts_steps || 64;
        document.getElementById('tts-steps-value').textContent = config.tts_steps || 64;
        document.getElementById('tts-temp-slider').value = Math.round((config.tts_temperature || 1.0) * 10);
        document.getElementById('tts-temp-value').textContent = (config.tts_temperature || 1.0).toFixed(1);
        
        // Memory
        document.getElementById('memory-search-slider').value = config.memory_search_results || 3;
        document.getElementById('memory-search-value').textContent = config.memory_search_results || 3;
        document.getElementById('memory-threshold-slider').value = Math.round((config.memory_threshold || 0.3) * 10);
        document.getElementById('memory-threshold-value').textContent = (config.memory_threshold || 0.3).toFixed(1);

        // Save initial for restart check
        initialSettings = { ...config };
        
        await onProviderChange();
        
        // Select the current model (after loading the list)
        const modelSelect = document.getElementById('model-select');
        if (config.model) {
            // If the model is missing from the list, add it as (current)
            const exists = Array.from(modelSelect.options).some(o => o.value === config.model);
            if (!exists) {
                const opt = document.createElement('option');
                opt.value = config.model;
                opt.textContent = config.model + t('settings.current');
                modelSelect.prepend(opt);
            }
            modelSelect.value = config.model;
        }
    } catch (error) {
        console.error('Ошибка загрузки настроек:', error);
    }
    
    // Initialize the tabs
    initSettingsTabs();
    initSliders();
    initPersonalityInputs();
    loadPersonas().then(() => {
        renderPersonaSelector();
        renderPersonaSettings();
    });
}

function closeSettings() {
    const modal = document.getElementById('settings-modal');
    modal.classList.add('hidden');
}

function initSettingsTabs() {
    document.querySelectorAll('.settings-tab').forEach(tab => {
        tab.addEventListener('click', () => {
            document.querySelectorAll('.settings-tab').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.settings-tab-content').forEach(c => c.classList.remove('active'));
            tab.classList.add('active');
            document.getElementById('tab-' + tab.dataset.tab).classList.add('active');
        });
    });
}

function initSliders() {
    // Context: log2 slider
    const ctxSlider = document.getElementById('num-ctx-slider');
    const ctxValue = document.getElementById('num-ctx-value');
    if (ctxSlider) {
        ctxSlider.addEventListener('input', () => {
            ctxValue.textContent = Math.pow(2, parseInt(ctxSlider.value));
        });
    }
    
    // Temperature LLM
    const tempSlider = document.getElementById('temperature-slider');
    const tempValue = document.getElementById('temperature-value');
    if (tempSlider) {
        tempSlider.addEventListener('input', () => {
            tempValue.textContent = (parseInt(tempSlider.value) / 10).toFixed(1);
        });
    }
    
    // TTS Steps
    const ttsStepsSlider = document.getElementById('tts-steps-slider');
    const ttsStepsValue = document.getElementById('tts-steps-value');
    if (ttsStepsSlider) {
        ttsStepsSlider.addEventListener('input', () => {
            ttsStepsValue.textContent = ttsStepsSlider.value;
        });
    }
    
    // TTS Temperature
    const ttsTempSlider = document.getElementById('tts-temp-slider');
    const ttsTempValue = document.getElementById('tts-temp-value');
    if (ttsTempSlider) {
        ttsTempSlider.addEventListener('input', () => {
            ttsTempValue.textContent = (parseInt(ttsTempSlider.value) / 10).toFixed(1);
        });
    }
    
    // Memory Search
    const memSearchSlider = document.getElementById('memory-search-slider');
    const memSearchValue = document.getElementById('memory-search-value');
    if (memSearchSlider) {
        memSearchSlider.addEventListener('input', () => {
            memSearchValue.textContent = memSearchSlider.value;
        });
    }
    
    // Memory Threshold
    const memThreshSlider = document.getElementById('memory-threshold-slider');
    const memThreshValue = document.getElementById('memory-threshold-value');
    if (memThreshSlider) {
        memThreshSlider.addEventListener('input', () => {
            memThreshValue.textContent = (parseInt(memThreshSlider.value) / 10).toFixed(1);
        });
    }
}

async function onProviderChange() {
    const provider = document.getElementById('provider-select').value;
    const apiKeySection = document.getElementById('api-key-section');
    const ollamaHostSection = document.getElementById('ollama-host-input').parentElement;
    const hostInput = document.getElementById('ollama-host-input');
    const ctxSlider = document.getElementById('num-ctx-slider');
    const ctxHint = document.getElementById('num-ctx-hint');
    
    if (provider === 'openrouter') {
        apiKeySection.classList.remove('hidden');
        ollamaHostSection.classList.add('hidden');
    } else if (provider === 'lm_studio') {
        apiKeySection.classList.add('hidden');
        ollamaHostSection.classList.remove('hidden');
        // LM Studio defaults to port 1234
        if (hostInput.value.includes('11434')) {
            hostInput.value = 'http://localhost:1234';
        }
    } else {
        // Ollama
        apiKeySection.classList.add('hidden');
        ollamaHostSection.classList.remove('hidden');
        if (hostInput.value.includes('1234')) {
            hostInput.value = 'http://localhost:11434';
        }
    }

    // For LM Studio, context and model are read-only (managed in LM Studio)
    const isLmStudio = provider === 'lm_studio';
    const modelSelect = document.getElementById('model-select');
    if (ctxSlider) ctxSlider.disabled = isLmStudio;
    if (modelSelect) modelSelect.disabled = isLmStudio;
    if (ctxHint) {
        ctxHint.textContent = isLmStudio
            ? t('settings.context.hint.lmstudio')
            : t('settings.context.hint.ollama');
        ctxHint.classList.remove('hidden');
        if (!isLmStudio) ctxHint.classList.add('hidden');
    }
    
    await loadModelsForProvider(provider);
}

async function loadModelsForProvider(provider) {
    const modelSelect = document.getElementById('model-select');
    modelSelect.innerHTML = `<option value="">${t('settings.loading')}</option>`;
    
    // Get the host from the settings
    const hostInput = document.getElementById('ollama-host-input');
    const host = hostInput.value || 'http://localhost:11434';
    
    try {
        const response = await fetch(`${API_BASE}/api/models?provider=${provider}&host=${encodeURIComponent(host)}`);
        const data = await response.json();
        
        modelSelect.innerHTML = '';
        if (data.models && data.models.length > 0) {
            data.models.forEach(model => {
                const option = document.createElement('option');
                option.value = model;
                option.textContent = model;
                modelSelect.appendChild(option);
            });
        } else {
            modelSelect.innerHTML = `<option value="">${t('settings.noModels')}</option>`;
        }
    } catch (error) {
        console.error('Ошибка загрузки моделей:', error);
        modelSelect.innerHTML = `<option value="">${t('settings.error')}</option>`;
    }
}

// === Personality layer ===

function updatePersonalityCounters() {
    ['ru', 'en'].forEach(lang => {
        const input = document.getElementById(`personality-${lang}-input`);
        const counter = document.getElementById(`personality-${lang}-count`);
        if (input && counter) {
            counter.textContent = input.value.length;
            counter.style.color = input.value.length > 8000 ? 'var(--danger, #e06c75)' : '';
        }
    });
}

function initPersonalityInputs() {
    ['ru', 'en'].forEach(lang => {
        const input = document.getElementById(`personality-${lang}-input`);
        if (input) input.addEventListener('input', updatePersonalityCounters);
    });
    const resetBtn = document.getElementById('personality-reset-btn');
    if (resetBtn) {
        resetBtn.addEventListener('click', () => {
            ['ru', 'en'].forEach(lang => {
                const input = document.getElementById(`personality-${lang}-input`);
                if (input) input.value = '';
            });
            updatePersonalityCounters();
        });
    }
    updatePersonalityCounters();
}

async function saveSettings() {
    const provider = document.getElementById('provider-select').value;
    const modelSelect = document.getElementById('model-select');
    const model = modelSelect.disabled ? null : modelSelect.value;
    const ollamaHost = document.getElementById('ollama-host-input').value;
    const apiKey = document.getElementById('api-key-input').value;
    const ctxSlider = document.getElementById('num-ctx-slider');
    const numCtx = ctxSlider.disabled ? null : Math.pow(2, parseInt(ctxSlider.value));
    const temperature = parseInt(document.getElementById('temperature-slider').value) / 10;
    const ttsSteps = parseInt(document.getElementById('tts-steps-slider').value);
    const ttsTemperature = parseInt(document.getElementById('tts-temp-slider').value) / 10;
    const memorySearchResults = parseInt(document.getElementById('memory-search-slider').value);
    const memoryThreshold = parseInt(document.getElementById('memory-threshold-slider').value) / 10;
    const language = document.getElementById('lang-select') ? document.getElementById('lang-select').value : getLang();
    const showConsole = document.getElementById('show-console-toggle') ? document.getElementById('show-console-toggle').checked : false;
    const personalityRu = document.getElementById('personality-ru-input') ? document.getElementById('personality-ru-input').value : null;
    const personalityEn = document.getElementById('personality-en-input') ? document.getElementById('personality-en-input').value : null;

    // Apply language immediately so alert is in chosen language
    if (language !== getLang()) {
        await setLanguage(language);
    }

    // Determine if restart is actually needed
    let needsRestart = false;
    if (initialSettings) {
        if (provider !== initialSettings.provider) needsRestart = true;
        if (ollamaHost !== initialSettings.ollama_host) needsRestart = true;
        if (model !== null && model !== initialSettings.model) needsRestart = true;
        if (numCtx !== null && numCtx !== initialSettings.num_ctx) needsRestart = true;
        if (showConsole !== !!initialSettings.show_backend_console) needsRestart = true;
        // apiKey change also needs restart for some providers, but is hot-swapped, so not required
    } else {
        // Fallback: if we have no initial, assume restart only for provider/host/model/numCtx/showConsole
        needsRestart = false;
    }
    
    try {
        const response = await fetch(`${API_BASE}/api/config`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                provider,
                model,
                ollama_host: ollamaHost,
                api_key: apiKey,
                num_ctx: numCtx,
                temperature: temperature,
                tts_steps: ttsSteps,
                tts_temperature: ttsTemperature,
                memory_search_results: memorySearchResults,
                memory_threshold: memoryThreshold,
                language: language,
                show_backend_console: showConsole,
                personality_ru: personalityRu,
                personality_en: personalityEn,
            }),
        });
        
        if (response.ok) {
            showToast(t(needsRestart ? 'settings.saved' : 'settings.savedNoRestart'), needsRestart ? 'warning' : 'success', 3000);
            closeSettings();
        } else {
            showToast(t('settings.saveError'), 'error', 3000);
        }
    } catch (error) {
        console.error('Ошибка сохранения:', error);
        showToast(t('settings.saveError'), 'error', 3000);
    }
}

// Close the modal when clicking outside the content
document.addEventListener('click', (e) => {
    const modal = document.getElementById('status-modal');
    if (modal && e.target === modal) {
        hideStatus();
    }
});

async function updateStatus() {
    // Periodic status refresh
    const response = await fetch(`${API_BASE}/api/status`);
    const data = await response.json();
    console.log('Статус:', data);
    
    // Update the reasoning toggle state
    const thinkingToggle = document.getElementById('thinking-toggle');
    if (thinkingToggle) {
        const supportsThinking = data.supports_thinking === true;
        thinkingToggle.disabled = !supportsThinking;
        if (!supportsThinking) {
            thinkingToggle.checked = false;
        }
    }
    
    setInterval(async () => {
        try {
            const resp = await fetch(`${API_BASE}/api/status`);
            const st = await resp.json();
            console.log('Статус:', st);
            
            const tg = document.getElementById('thinking-toggle');
            if (tg) {
                const supports = st.supports_thinking === true;
                tg.disabled = !supports;
                if (!supports) {
                    tg.checked = false;
                }
            }
        } catch (error) {
            console.error('Ошибка обновления статуса:', error);
        }
    }, 30000);
}

// === Utilities ===

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// === Voice input ===
function startVoiceInput() {
    if (!('webkitSpeechRecognition' in window) && !('SpeechRecognition' in window)) {
        alert(t('alert.voiceNotSupported'));
        return;
    }
    
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    const recognition = new SpeechRecognition();
    
    recognition.lang = getLang()==='ru'?'ru-RU':'en-US';
    recognition.interimResults = false;
    recognition.maxAlternatives = 1;
    
    recognition.start();
    
    recognition.onresult = (event) => {
        const transcript = event.results[0][0].transcript;
        console.log('Распознано:', transcript);
        
        const input = document.getElementById('message-input');
        input.value = transcript;
        input.focus();
    };
    
    recognition.onerror = (event) => {
        console.error('Ошибка распознавания:', event.error);
    };
    
    recognition.onend = () => {
        console.log('Голосовой ввод завершён');
    };
}

// === Live mode ===
let liveModeActive = false;

function toggleLiveMode() {
    liveModeActive = !liveModeActive;
    console.log('Live режим:', liveModeActive ? 'ВКЛ' : 'ВЫКЛ');
    
    if (liveModeActive) {
        startLiveMode();
    } else {
        stopLiveMode();
    }
}

function startLiveMode() {
    const input = document.getElementById('message-input');
    input.placeholder = t('voice.liveActive');
    input.focus();
}

function stopLiveMode() {
    const input = document.getElementById('message-input');
    input.placeholder = t('voice.placeholder');
}

// === Voice Recording (Web Audio API + VAD) ===
let mediaRecorder = null;
let audioChunks = [];
let isRecording = false;
let isProcessingVoice = false;
let voiceActivityTimeout = null;
const SILENCE_THRESHOLD = 0.01;
const SILENCE_DURATION = 2000; // 2 seconds of silence to stop

async function toggleVoiceRecording() {
    if (isProcessingVoice) return; // Block while processing
    if (isRecording) {
        stopVoiceRecording();
    } else {
        await startVoiceRecording();
    }
}

async function startVoiceRecording() {
    if (isProcessingVoice) return; // Block while processing
    
    try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        
        audioChunks = [];
        mediaRecorder = new MediaRecorder(stream, {
            mimeType: 'audio/webm;codecs=opus'
        });
        
        mediaRecorder.ondataavailable = (event) => {
            if (event.data.size > 0) {
                audioChunks.push(event.data);
            }
        };
        
        mediaRecorder.onstop = async () => {
            isProcessingVoice = true; // Block re-recording while processing
            stream.getTracks().forEach(track => track.stop());
            
            // Wait 1 second before sending
            await new Promise(resolve => setTimeout(resolve, 1000));
            
            await processVoiceRecording();
            isProcessingVoice = false;
        };
        
        // Start recording
        mediaRecorder.start(100);
        isRecording = true;
        
        // UI - show the recording state
        const voiceBtn = document.getElementById('voice-btn');
        voiceBtn.classList.add('recording');
        voiceBtn.disabled = true;
        
        // Start voice activity monitoring
        monitorVoiceActivity(stream);
        
        console.log('Запись голоса начата...');
        
    } catch (error) {
        console.error('Ошибка доступа к микрофону:', error);
        alert(t('alert.micFailed'));
    }
}

function monitorVoiceActivity(stream) {
    const audioContext = new AudioContext();
    const analyser = audioContext.createAnalyser();
    const source = audioContext.createMediaStreamSource(stream);
    
    source.connect(analyser);
    analyser.fftSize = 256;
    
    const dataArray = new Uint8Array(analyser.frequencyBinCount);
    
    const checkLevel = () => {
        if (!isRecording) return;
        
        analyser.getByteFrequencyData(dataArray);
        
        // Compute the average level
        let sum = 0;
        for (let i = 0; i < dataArray.length; i++) {
            sum += dataArray[i];
        }
        const average = sum / dataArray.length / 255;
        
        if (average > SILENCE_THRESHOLD) {
            // Sound detected - reset the timer
            if (voiceActivityTimeout) {
                clearTimeout(voiceActivityTimeout);
            }
            // Start a new timer to stop after silence
            voiceActivityTimeout = setTimeout(() => {
                console.log('Тишина detected - останавливаем запись');
                stopVoiceRecording();
            }, SILENCE_DURATION);
        }
        
        if (isRecording) {
            requestAnimationFrame(checkLevel);
        }
    };
    
    checkLevel();
}

function stopVoiceRecording() {
    if (mediaRecorder && isRecording) {
        mediaRecorder.stop();
        isRecording = false;
        
        if (voiceActivityTimeout) {
            clearTimeout(voiceActivityTimeout);
            voiceActivityTimeout = null;
        }
        
        const voiceBtn = document.getElementById('voice-btn');
        voiceBtn.classList.remove('recording');
        voiceBtn.disabled = false;
        
        console.log('Запись голоса остановлена');
    }
}

async function processVoiceRecording() {
    if (audioChunks.length === 0) {
        console.log(t('voice.noAudio'));
        return;
    }
    
    console.log(t('voice.processing'));
    
    // Collect the audio into a blob
    const audioBlob = new Blob(audioChunks, { type: 'audio/webm' });

    // Skip obviously empty recordings locally (backend would answer 422)
    if (audioBlob.size < 4096) {
        console.log(t('voice.tooShort'));
        alert(t('voice.tooShort'));
        return;
    }

    // Show the processing indicator
    const voiceBtn = document.getElementById('voice-btn');
    voiceBtn.textContent = '⏳';
    voiceBtn.disabled = true;
    
    try {
        // Send to the server
        const formData = new FormData();
        formData.append('file', audioBlob, 'recording.webm');
        
        const response = await fetch(`${API_BASE}/api/stt`, {
            method: 'POST',
            body: formData
        });
        
        if (!response.ok) {
            const errBody = await response.json().catch(() => null);
            throw new Error(errBody && errBody.detail ? errBody.detail : `STT error: ${response.status}`);
        }
        
        const data = await response.json();
        
        if (data.success && data.text) {
            // Insert the text into the input field
            const input = document.getElementById('message-input');
            input.value = data.text;
            input.focus();
            console.log('Распознано:', data.text);
            
            // Send the message automatically
            sendMessage();
        } else {
            console.log(t('voice.emptyResult'));
        }
        
    } catch (error) {
        console.error(t('voice.sttError'), error);
        alert(t('alert.sttFailed', {msg: error.message}));
    } finally {
        // Restore the button to its normal state
        voiceBtn.textContent = '🎤';
        voiceBtn.disabled = false;
        audioChunks = [];
    }
}

// === TTS (Text-to-Speech) ===
async function playTTS(text) {
    if (!text) return;
    
    console.log(t('voice.tts.synthesis'), text.substring(0, 50) + '...');
    
    try {
        const response = await fetch(`${API_BASE}/api/tts/speak`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text: text }),
        });
        
        if (!response.ok) {
            throw new Error(`TTS error: ${response.status}`);
        }
        
        const blob = await response.blob();
        const audioUrl = URL.createObjectURL(blob);
        const audio = new Audio(audioUrl);
        
        audio.onended = () => {
            URL.revokeObjectURL(audioUrl);
            console.log(t('voice.tts.done'));
        };
        
        audio.onerror = (e) => {
            console.error(t('voice.tts.playError'), e);
            URL.revokeObjectURL(audioUrl);
        };
        
        await audio.play();
        console.log(t('voice.tts.start'));
        
    } catch (error) {
        console.error(t('voice.tts.error'), error);
    }
}

// Load the voice list for cloning
async function loadTTSVoices() {
    try {
        const response = await fetch(`${API_BASE}/api/tts/voices`);
        const data = await response.json();
        
        const cloneSelect = document.getElementById('tts-clone-select');
        cloneSelect.innerHTML = '';
        
        if (data.voices && data.voices.length > 0) {
            data.voices.forEach(voice => {
                const option = document.createElement('option');
                option.value = voice.path;
                option.textContent = `🎤 ${voice.name}`;
                cloneSelect.appendChild(option);
            });
        } else {
            const option = document.createElement('option');
            option.value = '';
            option.textContent = t('alert.noVoices');
            cloneSelect.appendChild(option);
        }
        
        console.log(t('voice.loaded'), data.voices?.length || 0);
    } catch (err) {
        console.error(t('voice.loadError'), err);
    }
}

// Update the TTS configuration
async function updateTTSConfig() {
    const mode = document.querySelector('input[name="tts-mode"]:checked').value;
    let instruct = 'female';
    let ref_audio = null;
    
    if (mode === 'instruct') {
        instruct = document.getElementById('tts-voice-select').value;
    } else {
        ref_audio = document.getElementById('tts-clone-select').value;
    }
    
    console.log('TTS конфиг:', { mode, instruct, ref_audio });
    
    try {
        const response = await fetch(`${API_BASE}/api/tts/config`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                mode: mode,
                instruct: instruct,
                ref_audio: ref_audio,
                position_temperature: 0.0,
                class_temperature: 0.0,
            }),
        });
        const data = await response.json();
        console.log('TTS конфиг сохранён:', data);
    } catch (err) {
        console.error('Ошибка сохранения TTS конфига:', err);
    }
}

// Global function for deleting memory entries
window.deleteMemoryEntry = deleteMemoryEntry;
