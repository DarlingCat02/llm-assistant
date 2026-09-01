/**
 * Local AI Assistant - Frontend Application
 * 
 * Архитектура:
 * - API-first: все вызовы через REST API
 * - WebSocket для real-time событий
 * - Подготовка к голосовому вводу
 */

import { initI18n, t, setLanguage, getLang } from './i18n.js';

const API_BASE = 'http://127.0.0.1:8000';
let currentChatId = null;
let ws = null;

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

// === Инициализация ===

async function waitForApi(retries = 20, delay = 500) {
    for (let i = 0; i < retries; i++) {
        try {
            const response = await fetch(`${API_BASE}/api/status`, { method: 'GET' });
            if (response.ok) return true;
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

    // Кнопки
    document.getElementById('new-chat-btn').addEventListener('click', createNewChat);
    document.getElementById('send-btn').addEventListener('click', sendMessage);
    
    // Файлы
    document.getElementById('file-input').addEventListener('change', handleFileSelect);
    document.getElementById('file-remove').addEventListener('click', clearFile);
    
    // Удаление отдельных файлов из превью (делегирование событий)
    document.getElementById('file-previews').addEventListener('click', (e) => {
        if (e.target.classList.contains('file-remove')) {
            const index = parseInt(e.target.dataset.index);
            if (!isNaN(index)) {
                attachedFiles.splice(index, 1);
                // Перерендерим превью
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
        
        // Показываем/скрываем TTS опции
        const ttsOptions = document.getElementById('tts-options');
        if (ttsOptions) {
            ttsOptions.style.display = enabled ? 'flex' : 'none';
        }
        
        try {
            const response = await fetch(`${API_BASE}/api/tts/toggle`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(enabled),
            });
            const data = await response.json();
            console.log('TTS статус:', data);
            
            // Загружаем голоса для клонирования
            if (enabled) await loadTTSVoices();
            
        } catch (err) {
            console.error('Ошибка переключения TTS:', err);
            e.target.checked = !enabled;
        }
    });
    
    // Загружаем голоса при старте
    loadTTSVoices();
    
    // Переключение режима TTS (синтез/клонирование)
    document.querySelectorAll('input[name="tts-mode"]').forEach(radio => {
        radio.addEventListener('change', async (e) => {
            const mode = e.target.value;
            const voiceSelect = document.getElementById('tts-voice-select');
            const cloneSelect = document.getElementById('tts-clone-select');
            
            if (mode === 'clone') {
                voiceSelect.style.display = 'none';
                cloneSelect.style.display = 'block';
                
                // Загрузить голоса если ещё не загружены
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
    
    // Выбор голоса в режиме синтеза
    document.getElementById('tts-voice-select').addEventListener('change', async (e) => {
        await updateTTSConfig();
    });
    
    // Выбор голоса в режиме клонирования
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
    const langSel = document.getElementById('lang-select');
    if (langSel) {
        langSel.value = getLang();
        langSel.addEventListener('change', async (e) => {
            await setLanguage(e.target.value);
        });
    }
    
    // Enter для отправки
    document.getElementById('message-input').addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });
    
    // Поиск в памяти по Enter
    document.getElementById('memory-search-input').addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            searchMemory();
        }
    });
    
    // Добавление записи по Enter
    document.getElementById('memory-add-input').addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            addMemoryEntry();
        }
    });
}

// === WebSocket ===

function connectWebSocket() {
    // Используем тот же host что и для страницы
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
        // Переподключение через 5 секунд
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
    
    // Ответы показываются через HTTP response в sendMessage().
    // WebSocket здесь для будущих real-time уведомлений.
}

function updateConnectionStatus(connected) {
    const statusBtn = document.getElementById('status-btn');
    if (connected) {
        statusBtn.textContent = t('status.connected');
    } else {
        statusBtn.textContent = t('status.disconnected');
    }
}

// === Чаты ===

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
    
    // Клик - выбор чата
    div.addEventListener('click', (e) => {
        if (!e.target.classList.contains('chat-item-title') || !e.target.contentEditable) {
            selectChat(chat.id);
        }
    });
    
    // Двойной клик - переименование
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
    
    // Выделить весь текст
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
    
    // Показываем индикатор контекста
    const ctxIndicator = document.getElementById('context-indicator');
    if (ctxIndicator) ctxIndicator.style.display = 'flex';
    
    // Обновляем выделение
    document.querySelectorAll('.chat-item').forEach(el => {
        el.classList.remove('active');
    });
    
    // Загружаем сообщения
    await loadChatMessages(chatId);
    
    // Обновляем заголовок
    document.getElementById('chat-title').textContent = `${getLang()==='ru'?'Чат':'Chat'} #${chatId}`;
    
    // Сбрасываем индикатор контекста (обновится после следующего ответа)
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
        // Прячем индикатор контекста
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

// === Сообщения ===

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
                
                // Создаем превью
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
                
                // Создаем превью для документа
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
    
    // Формируем финальное сообщение с файлами
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
    
    // Собираем base64 изображений для отправки
    const imageBases = attachedFiles
        .filter(f => f.type === 'image')
        .map(f => f.base64);
    
    // Сохраняем информацию о файлах для UI ДО очистки
    const filesCount = attachedFiles.length;
    const hasImages = imageBases.length > 0;
    const hasDocs = docTexts.length > 0;
    
    // Очищаем поле и файлы
    input.value = '';
    input.style.height = 'auto';
    
    // Сохраняем текущие файлы для отправки
    const imagesToSend = [...imageBases];
    const docsToSend = attachedFiles.filter(f => f.type === 'document');
    clearFile();
    
    // Добавляем сообщение пользователя (используем сохранённое количество)
    appendMessage('user', message || (filesCount > 0 ? `📎 ${t('chat.file.count', {count: filesCount})}` : '')
        ? `${message}\n\n${hasDocs ? `📄 ${t('chat.file.docs', {names: docsToSend.map(f => f.name).join(', ')})}` : ''}${hasImages ? (hasDocs ? ', ' : '') + `🖼️ ${t('chat.file.images', {count: imageBases.length})}` : ''}`
        : (filesCount > 0 ? `📎 ${t('chat.file.count', {count: filesCount})}` : ''));
    showTypingIndicator();
    
    // Отправляем на сервер
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
        
        // Если это первое сообщение в новом чате, обновляем currentChatId
        if (!currentChatId) {
            currentChatId = data.chat_id;
            document.getElementById('chat-title').textContent = `${getLang()==='ru'?'Чат':'Chat'} #${currentChatId}`;
            await loadChats();
        }
        
        // Показываем ответ из HTTP-ответа
        appendMessage('assistant', data.response);
        hideTypingIndicator();
        
        // Обновляем индикатор контекста
        updateContextIndicator(data.used_context_tokens, data.max_context_tokens);
        
        // TTS - озвучиваем ответ если включено
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

function appendMessage(role, content, timestamp = null) {
    const container = document.getElementById('messages-container');
    
    // Удаляем welcome сообщение если есть
    const welcome = container.querySelector('.welcome-message');
    if (welcome) {
        welcome.remove();
    }
    
    const div = document.createElement('div');
    div.className = `message ${role}`;
    
    const avatar = role === 'user' ? '👤' : '🤖';
    const time = timestamp 
        ? new Date(timestamp).toLocaleTimeString(getLang()==='ru'?'ru-RU':'en-US', { hour: '2-digit', minute: '2-digit' })
        : new Date().toLocaleTimeString(getLang()==='ru'?'ru-RU':'en-US', { hour: '2-digit', minute: '2-digit' });
    
    div.innerHTML = `
        <div class="message-avatar">${avatar}</div>
        <div class="message-content">
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

// === Память ===

function toggleMemoryPanel() {
    const panel = document.getElementById('memory-panel');
    const isHidden = panel.classList.toggle('hidden');
    
    // Если открыли панель - загружаем все записи
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
        
        // Перезагружаем список записей
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

// === Статус ===

async function showStatus() {
    const modal = document.getElementById('status-modal');
    const content = document.getElementById('status-content');
    
    // Привязываем обработчик кнопки закрытия СРАЗУ, до fetch
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

// === Настройки ===
async function openSettings() {
    const modal = document.getElementById('settings-modal');
    modal.classList.remove('hidden');
    
    // Загружаем текущие настройки
    try {
        const response = await fetch(`${API_BASE}/api/config`);
        const config = await response.json();
        
        const langSel = document.getElementById('lang-select');
        if (langSel && config.language) {
            langSel.value = config.language;
            if (config.language !== getLang()) {
                await setLanguage(config.language);
            }
        }
        
        document.getElementById('provider-select').value = config.provider || 'ollama';
        document.getElementById('ollama-host-input').value = config.ollama_host || 'http://localhost:11434';
        document.getElementById('api-key-input').value = config.api_key || '';
        
        // Контекст (log2 для слайдера)
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
        
        await onProviderChange();
        
        // Выбрать текущую модель (после загрузки списка)
        const modelSelect = document.getElementById('model-select');
        if (config.model) {
            // Если модели нет в списке — добавим её как (текущая)
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
    
    // Инициализация табов
    initSettingsTabs();
    initSliders();
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
    // Контекст: log2 слайдер
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
        // LM Studio по умолчанию на порту 1234
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

    // Для LM Studio контекст и модель — только чтение (меняются в LM Studio)
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
    
    // Получаем хост из настроек
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
            }),
        });
        
        if (response.ok) {
            alert(t('settings.saved'));
            closeSettings();
        } else {
            alert(t('settings.saveError'));
        }
    } catch (error) {
        console.error('Ошибка сохранения:', error);
        alert(t('settings.saveError'));
    }
}

// Закрытие модалки при клике вне контента
document.addEventListener('click', (e) => {
    const modal = document.getElementById('status-modal');
    if (modal && e.target === modal) {
        hideStatus();
    }
});

async function updateStatus() {
    // Периодическое обновление статуса
    const response = await fetch(`${API_BASE}/api/status`);
    const data = await response.json();
    console.log('Статус:', data);
    
    // Обновление состояния переключателя рассуждения
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

// === Утилиты ===

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// === Голосовой ввод ===
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

// === Live режим ===
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
    if (isProcessingVoice) return; // Блокируем во время обработки
    if (isRecording) {
        stopVoiceRecording();
    } else {
        await startVoiceRecording();
    }
}

async function startVoiceRecording() {
    if (isProcessingVoice) return; // Блокируем во время обработки
    
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
            isProcessingVoice = true; // Блокируем повторную запись пока обрабатываем
            stream.getTracks().forEach(track => track.stop());
            
            // Ждём 1 секунду перед отправкой
            await new Promise(resolve => setTimeout(resolve, 1000));
            
            await processVoiceRecording();
            isProcessingVoice = false;
        };
        
        // Начинаем запись
        mediaRecorder.start(100);
        isRecording = true;
        
        // UI - показываем что записываем
        const voiceBtn = document.getElementById('voice-btn');
        voiceBtn.classList.add('recording');
        voiceBtn.disabled = true;
        
        // Начинаем мониторинг голосовой активности
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
        
        // Вычисляем средний уровень
        let sum = 0;
        for (let i = 0; i < dataArray.length; i++) {
            sum += dataArray[i];
        }
        const average = sum / dataArray.length / 255;
        
        if (average > SILENCE_THRESHOLD) {
            // Есть звук - сбрасываем таймер
            if (voiceActivityTimeout) {
                clearTimeout(voiceActivityTimeout);
            }
            // Запускаем новый таймер на остановку после тишины
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
    
    // Собираем аудио в blob
    const audioBlob = new Blob(audioChunks, { type: 'audio/webm' });
    
    // Показываем индикатор обработки
    const voiceBtn = document.getElementById('voice-btn');
    voiceBtn.textContent = '⏳';
    voiceBtn.disabled = true;
    
    try {
        // Отправляем на сервер
        const formData = new FormData();
        formData.append('file', audioBlob, 'recording.webm');
        
        const response = await fetch(`${API_BASE}/api/stt`, {
            method: 'POST',
            body: formData
        });
        
        if (!response.ok) {
            throw new Error(`STT error: ${response.status}`);
        }
        
        const data = await response.json();
        
        if (data.success && data.text) {
            // Вставляем текст в поле ввода
            const input = document.getElementById('message-input');
            input.value = data.text;
            input.focus();
            console.log('Распознано:', data.text);
            
            // Автоматически отправляем сообщение
            sendMessage();
        } else {
            console.log(t('voice.emptyResult'));
        }
        
    } catch (error) {
        console.error(t('voice.sttError'), error);
        alert(t('alert.sttFailed', {msg: error.message}));
    } finally {
        // Возвращаем кнопку в_NORMALное состояние
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

// Загрузить список голосов для клонирования
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

// Обновить конфигурацию TTS
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

// Глобальная функция для удаления записей памяти
window.deleteMemoryEntry = deleteMemoryEntry;
