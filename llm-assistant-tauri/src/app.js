/**
 * Local AI Assistant - Frontend Application
 * 
 * Архитектура:
 * - API-first: все вызовы через REST API
 * - WebSocket для real-time событий
 * - Подготовка к голосовому вводу
 */

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
            '<div class="error">Ошибка: Python бэкенд не запущен</div>';
    }
});

function initEventListeners() {
    // Кнопки
    document.getElementById('new-chat-btn').addEventListener('click', createNewChat);
    document.getElementById('send-btn').addEventListener('click', sendMessage);
    document.getElementById('voice-btn').addEventListener('click', toggleVoiceRecording);
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
        statusBtn.textContent = '🟢 Статус';
    } else {
        statusBtn.textContent = '🔴 Статус';
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
    const dateStr = date.toLocaleDateString('ru-RU', {
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
            body: JSON.stringify({ title: 'Новый чат' }),
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
    
    // Обновляем выделение
    document.querySelectorAll('.chat-item').forEach(el => {
        el.classList.remove('active');
    });
    
    // Загружаем сообщения
    await loadChatMessages(chatId);
    
    // Обновляем заголовок
    document.getElementById('chat-title').textContent = `Чат #${chatId}`;
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
    
    if (!confirm('Удалить этот чат?')) return;
    
    try {
        await fetch(`${API_BASE}/api/chats/${currentChatId}`, {
            method: 'DELETE',
        });
        
        currentChatId = null;
        document.getElementById('chat-title').textContent = 'Выберите чат';
        document.getElementById('messages-container').innerHTML = `
            <div class="welcome-message">
                <h2>🤖 Добро пожаловать в Local AI Assistant!</h2>
                <p>Выберите существующий чат или создайте новый</p>
            </div>
        `;
        
        await loadChats();
    } catch (error) {
        console.error('Ошибка удаления чата:', error);
    }
}

async function clearChat() {
    if (!currentChatId) return;
    
    if (!confirm('Очистить историю сообщений?')) return;
    
    try {
        await fetch(`${API_BASE}/api/chats/${currentChatId}/messages`, {
            method: 'DELETE',
        });
        
        document.getElementById('messages-container').innerHTML = '';
    } catch (error) {
        console.error('Ошибка очистки чата:', error);
    }
}

// === Сообщения ===

async function sendMessage() {
    const input = document.getElementById('message-input');
    const message = input.value.trim();
    
    if (!message) return;
    
    // Очищаем поле
    input.value = '';
    input.style.height = 'auto';
    
    // Добавляем сообщение пользователя
    appendMessage('user', message);
    showTypingIndicator();
    
    // Отправляем на сервер
    try {
        const thinkingToggle = document.getElementById('thinking-toggle');
        const thinkingEnabled = thinkingToggle ? thinkingToggle.checked : false;
        
        const response = await fetch(`${API_BASE}/api/chat`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                message: message,
                chat_id: currentChatId,
                thinking: thinkingEnabled,
            }),
        });
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Ошибка отправки');
        }
        
        const data = await response.json();
        
        // Если это первое сообщение в новом чате, обновляем currentChatId
        if (!currentChatId) {
            currentChatId = data.chat_id;
            document.getElementById('chat-title').textContent = `Чат #${currentChatId}`;
            await loadChats();
        }
        
        // Показываем ответ из HTTP-ответа
        appendMessage('assistant', data.response);
        hideTypingIndicator();
        
    } catch (error) {
        console.error('Ошибка отправки:', error);
        hideTypingIndicator();
        appendMessage('assistant', `❌ Ошибка: ${error.message}`);
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
        ? new Date(timestamp).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })
        : new Date().toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' });
    
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
    resultsDiv.innerHTML = '<p>Загрузка...</p>';
    
    try {
        const response = await fetch(`${API_BASE}/api/memory`);
        const data = await response.json();
        
        resultsDiv.innerHTML = '';
        
        if (!data.entries || data.entries.length === 0) {
            resultsDiv.innerHTML = '<p>Память пуста. Ассистент ещё не сохранил важные факты.</p>';
            return;
        }
        
        resultsDiv.innerHTML = `<p style="color: gray; margin-bottom: 10px;">Записей: ${data.total}</p>`;
        
        data.entries.forEach(entry => {
            const div = document.createElement('div');
            div.className = 'memory-entry';
            div.innerHTML = `
                <div class="memory-entry-text">${escapeHtml(entry.text)}</div>
                <div class="memory-entry-meta">
                    <span>Тип: ${entry.metadata?.type || 'general'}</span>
                    <button class="btn-icon" onclick="deleteMemoryEntry('${entry.id}')" title="Удалить">🗑️</button>
                </div>
            `;
            resultsDiv.appendChild(div);
        });
        
    } catch (error) {
        console.error('Ошибка загрузки:', error);
        resultsDiv.innerHTML = `<p>Ошибка: ${error.message}</p>`;
    }
}

async function searchMemory() {
    const input = document.getElementById('memory-search-input');
    const query = input.value.trim();
    
    if (!query) return;
    
    const resultsDiv = document.getElementById('memory-results');
    resultsDiv.innerHTML = '<p>Поиск...</p>';
    
    try {
        const response = await fetch(`${API_BASE}/api/memory/search`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ query: query, limit: 20 }),
        });
        
        const data = await response.json();
        
        resultsDiv.innerHTML = '';
        
        if (!data.results || data.results.length === 0) {
            resultsDiv.innerHTML = '<p>Ничего не найдено</p>';
            return;
        }
        
        data.results.forEach(entry => {
            const div = document.createElement('div');
            div.className = 'memory-entry';
            div.innerHTML = `
                <div class="memory-entry-text">${escapeHtml(entry.text)}</div>
                <div class="memory-entry-meta">
                    <span>Схожесть: ${(entry.score * 100).toFixed(1)}%</span>
                    <button class="btn-icon" onclick="deleteMemoryEntry('${entry.id}')" title="Удалить">🗑️</button>
                </div>
            `;
            resultsDiv.appendChild(div);
        });
        
    } catch (error) {
        console.error('Ошибка поиска:', error);
        resultsDiv.innerHTML = `<p>Ошибка: ${error.message}</p>`;
    }
}

async function deleteMemoryEntry(entryId) {
    if (!confirm('Удалить эту запись из памяти?')) return;
    
    try {
        const response = await fetch(`${API_BASE}/api/memory/${entryId}`, {
            method: 'DELETE',
        });
        
        if (!response.ok) {
            const error = await response.json();
            alert(`Ошибка: ${error.detail || 'Не удалось удалить'}`);
            return;
        }
        
        // Перезагружаем список записей
        loadAllMemoryEntries();
    } catch (error) {
        console.error('Ошибка удаления:', error);
        alert(`Ошибка: ${error.message}`);
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
            alert(`Ошибка: ${error.detail || 'Не удалось добавить'}`);
            return;
        }
        
        input.value = '';
        loadAllMemoryEntries();
    } catch (error) {
        console.error('Ошибка добавления:', error);
        alert(`Ошибка: ${error.message}`);
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
    
    content.innerHTML = '<p>Загрузка...</p>';
    modal.classList.remove('hidden');
    
    try {
        const response = await fetch(`${API_BASE}/api/status`);
        const data = await response.json();
        
        content.innerHTML = `
            <p><strong>Статус:</strong> ${data.status}</p>
            <p><strong>Провайдер:</strong> ${data.provider}</p>
            <p><strong>Модель:</strong> ${data.model}</p>
            <p><strong>Чатов:</strong> ${data.chats_count || 0}</p>
            <p><strong>Записей в памяти:</strong> ${data.memory_entries || 0}</p>
        `;
    } catch (error) {
        content.innerHTML = `<p>Ошибка: ${error.message}</p>`;
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
        
        document.getElementById('provider-select').value = config.provider || 'ollama';
        document.getElementById('ollama-host-input').value = config.ollama_host || 'http://localhost:11434';
        document.getElementById('api-key-input').value = config.api_key || '';
        
        onProviderChange();
        await loadModelsForProvider(config.provider || 'ollama');
        
        // Выбрать текущую модель
        const modelSelect = document.getElementById('model-select');
        if (config.model) {
            modelSelect.value = config.model;
        }
    } catch (error) {
        console.error('Ошибка загрузки настроек:', error);
    }
}

function closeSettings() {
    const modal = document.getElementById('settings-modal');
    modal.classList.add('hidden');
}

function onProviderChange() {
    const provider = document.getElementById('provider-select').value;
    const apiKeySection = document.getElementById('api-key-section');
    const ollamaHostSection = document.getElementById('ollama-host-input').parentElement;
    const hostInput = document.getElementById('ollama-host-input');
    
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
    
    loadModelsForProvider(provider);
}

async function loadModelsForProvider(provider) {
    const modelSelect = document.getElementById('model-select');
    modelSelect.innerHTML = '<option value="">Загрузка...</option>';
    
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
            modelSelect.innerHTML = '<option value="">Нет моделей</option>';
        }
    } catch (error) {
        console.error('Ошибка загрузки моделей:', error);
        modelSelect.innerHTML = '<option value="">Ошибка</option>';
    }
}

async function saveSettings() {
    const provider = document.getElementById('provider-select').value;
    const model = document.getElementById('model-select').value;
    const ollamaHost = document.getElementById('ollama-host-input').value;
    const apiKey = document.getElementById('api-key-input').value;
    
    try {
        const response = await fetch(`${API_BASE}/api/config`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                provider,
                model,
                ollama_host: ollamaHost,
                api_key: apiKey,
            }),
        });
        
        if (response.ok) {
            alert('Настройки сохранены! Перезапустите приложение для применения.');
            closeSettings();
        } else {
            alert('Ошибка сохранения настроек');
        }
    } catch (error) {
        console.error('Ошибка сохранения:', error);
        alert('Ошибка сохранения настроек');
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
        alert('Голосовой ввод не поддерживается в этом браузере');
        return;
    }
    
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    const recognition = new SpeechRecognition();
    
    recognition.lang = 'ru-RU';
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
    input.placeholder = 'Live режим активирован - говорите...';
    input.focus();
}

function stopLiveMode() {
    const input = document.getElementById('message-input');
    input.placeholder = 'Введите сообщение...';
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
        alert('Не удалось получить доступ к микрофону');
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
        console.log('Нет аудио данных');
        return;
    }
    
    console.log('Обработка записи...');
    
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
            console.log('Пустой результат распознавания');
        }
        
    } catch (error) {
        console.error('Ошибка STT:', error);
        alert('Ошибка распознавания голоса: ' + error.message);
    } finally {
        // Возвращаем кнопку в_NORMALное состояние
        voiceBtn.textContent = '🎤';
        voiceBtn.disabled = false;
        audioChunks = [];
    }
}

// Глобальная функция для удаления записей памяти
window.deleteMemoryEntry = deleteMemoryEntry;
