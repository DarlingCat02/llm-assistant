/**
 * Local AI Assistant - Frontend Application
 * 
 * Архитектура:
 * - API-first: все вызовы через REST API
 * - WebSocket для real-time событий
 * - Подготовка к голосовому вводу
 */

const API_BASE = '';
let currentChatId = null;
let ws = null;

// === Инициализация ===

document.addEventListener('DOMContentLoaded', () => {
    initEventListeners();
    loadChats();
    connectWebSocket();
    updateStatus();
});

function initEventListeners() {
    // Кнопки
    document.getElementById('new-chat-btn').addEventListener('click', createNewChat);
    document.getElementById('send-btn').addEventListener('click', sendMessage);
    document.getElementById('clear-chat-btn').addEventListener('click', clearChat);
    document.getElementById('delete-chat-btn').addEventListener('click', deleteChat);
    document.getElementById('memory-btn').addEventListener('click', toggleMemoryPanel);
    document.getElementById('status-btn').addEventListener('click', showStatus);
    document.getElementById('close-memory-btn').addEventListener('click', toggleMemoryPanel);
    document.getElementById('memory-search-btn').addEventListener('click', searchMemory);
    document.getElementById('memory-add-btn').addEventListener('click', addMemoryEntry);
    document.getElementById('close-status-btn').addEventListener('click', hideStatus);
    
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
        <div class="chat-item-title">${escapeHtml(chat.title)}</div>
        <div class="chat-item-date">${dateStr}</div>
    `;
    
    div.addEventListener('click', () => selectChat(chat.id));
    
    return div;
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

// Глобальная функция для удаления записей памяти
window.deleteMemoryEntry = deleteMemoryEntry;
