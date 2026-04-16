# Local AI Assistant

Локальный AI-ассистент с модульной архитектурой. Поддерживает **Ollama**, **LM Studio** и **OpenRouter**.

**Особенности:**
- 🖥️ Графический интерфейс (CustomTkinter) + Веб-интерфейс (FastAPI) + консольный режим
- 🧠 Долговременная память на ChromaDB
- 🔌 Function Calling (заглушка для расширения)
- 🎨 Тёмная/светлая тема GUI
- 🚀 One-click запуск (Windows)
- 🌐 Веб-интерфейс с API-first архитектурой
- 🎤 Подготовка к голосовому вводу (services/voice_service.py)
- 🔀 Переключение между провайдерами: Ollama / LM Studio / OpenRouter

## Структура проекта

```
local_assistant/
├── .env.example          # Шаблон конфигурации
├── config.py             # Конфигурация (pydantic-settings)
├── requirements.txt      # Зависимости
├── run.bat               # One-click запуск (консоль/GUI)
├── run_web.bat           # Запуск веб-сервера
├── run_voice.bat         # Запуск голосового сервиса (заглушка)
├── backend/
│   ├── main.py           # FastAPI приложение
│   ├── api.py            # API роуты
│   ├── database.py       # SQLite для чатов
│   └── requirements.txt  # Backend зависимости
├── frontend/
│   ├── index.html        # Веб-интерфейс
│   ├── style.css         # Стили
│   └── app.js            # Frontend логика
├── services/
│   └── voice_service.py  # ЗАГЛУШКА: будущий голосовой ввод
└── src/
    ├── llm_engine.py     # Ollama API
    ├── memory_manager.py # ChromaDB + RAG
    ├── tts_engine.py     # TTS (заглушка)
    ├── gui_ctk.py        # CustomTkinter GUI
    └── main.py           # Console/GUI точка входа
```

## info
Этот проект был частично написан агентно, в целях обучения. 
Лично я: 
Выбирал стек технологий и выдвигал требования к масштабируемости, полностью продумывал функционал (ещё далеко не все фичи реализованы которые задумывались изначально). 
Запускал, находил баги, проверял производительность, выйявлял узкие места, принимал решения по ускорению, тестировал на своём железе. Собирал всё в единую рабочую систему и проверял совместимость модулей.
А также писал инструкции.
## Быстрый старт

### 1. Создание виртуального окружения

```bash
cd local_assistant

# Создание venv
python -m venv venv

# Активация (Windows)
venv\Scripts\activate
```

### 2. Установка зависимостей

```bash
# Основные зависимости
pip install -r requirements.txt

# Зависимости для веб-интерфейса
pip install -r backend/requirements.txt
```

### 3. Настройка конфигурации

```bash
# Скопировать шаблон
copy .env.example .env
```

Отредактируйте `.env` при необходимости:
- `LLM_PROVIDER` — провайдер: `ollama` / `lm_studio` / `openrouter`
- `LLM_MODEL` — модель для генерации
- `LLM_API_KEY` — API-ключ (нужен только для OpenRouter)
- `GUI_ENABLED` — включить GUI (`true`/`false`)
- `WEB_PORT` — порт для веб-сервера (по умолчанию `8000`)

### 4. Выбор LLM-провайдера

Все три провайдера используют OpenAI-совместимый API. Переключение — через одну переменную `.env`.

#### Ollama (локальный)
```env
LLM_PROVIDER=ollama
LLM_HOST=http://localhost:11434
LLM_MODEL=qwen2.5:7b
LLM_API_KEY=
```
Установка: https://ollama.ai. Загрузка модели: `ollama pull qwen2.5:7b`

#### LM Studio (локальный)
```env
LLM_PROVIDER=lm_studio
LLM_HOST=http://localhost:1234
LLM_MODEL=qwen2.5-7b-instruct
LLM_API_KEY=
```
Установка: https://lmstudio.ai. Загрузите модель через GUI LM Studio и запустите локальный сервер.

#### OpenRouter (облачный)
```env
LLM_PROVIDER=openrouter
LLM_HOST=
LLM_MODEL=openai/gpt-4o
LLM_API_KEY=sk-or-v1-...
```
Получить ключ: https://openrouter.ai/keys. Популярные модели: `anthropic/claude-3.5-sonnet`, `google/gemini-pro-1.5`, `qwen/qwen-2.5-72b-instruct`.

### 5. Запуск ассистента

**Вариант A: Консольный режим**
```bash
# В .env: GUI_ENABLED=false
python -m src.main
```

**Вариант B: Графический интерфейс (CustomTkinter)**
```bash
# В .env: GUI_ENABLED=true
python -m src.main
```

**Вариант C: Веб-интерфейс (рекомендуется)**
```bash
# В .env: GUI_ENABLED=false (чтобы не дублировать)
# Запуск веб-сервера
run_web.bat

# Или вручную:
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000

# Открыть в браузере: http://localhost:8000
```

**Вариант D: One-click запуск (Windows)**
```bash
# Консоль/GUI
run.bat

# Веб-интерфейс
run_web.bat

# Голосовой сервис (заглушка)
run_voice.bat
```

## API документация

Веб-сервер предоставляет REST API:

| Метод | Эндпоинт | Описание |
|-------|----------|----------|
| GET | `/api/status` | Статус сервиса |
| POST | `/api/chat` | Отправить сообщение, получить ответ |
| GET | `/api/chats` | Список чатов |
| POST | `/api/chats` | Создать чат |
| GET | `/api/chats/{id}` | Получить чат |
| DELETE | `/api/chats/{id}` | Удалить чат |
| GET | `/api/chats/{id}/messages` | История сообщений |
| DELETE | `/api/chats/{id}/messages` | Очистить историю |
| GET | `/api/memory` | Записи памяти |
| POST | `/api/memory/search` | Поиск в памяти |
| DELETE | `/api/memory/{id}` | Удалить запись |
| WS | `/ws/events` | WebSocket для real-time событий |

**Пример запроса:**
```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Привет!", "chat_id": null}'
```

## План развития проекта

| Этап | Что делаем | Статус |
|------|-----------|--------|
| **1** | Консольный ассистент | ✅ Готово |
| **2** | CustomTkinter GUI | ✅ Готово |
| **3** | Веб-интерфейс + FastAPI API | ✅ Готово |
| **4** | Чаты, память, CRUD | ✅ Готово |
| **5** | `voice_service.py` (заглушка) | ✅ Готово |
| **6** | Глобальные горячие клавиши (pynput) | ⏳ Позже |
| **7** | Захват аудио (speech_recognition) | ⏳ Позже |
| **8** | Whisper локальный для транскрибации | ⏳ Позже |
| **9** | Системный трей (pystray) | ⏳ Позже |

## Технические детали для будущего

### Глобальные горячие клавиши:
```python
from pynput import keyboard

def on_press(key):
    if key == keyboard.KeyCode.from_char('`'):  # Клавиша ~
        start_recording()

with keyboard.Listener(on_press=on_press) as listener:
    listener.join()
```

### Захват аудио:
```python
import speech_recognition as sr

recognizer = sr.Recognizer()
with sr.Microphone() as source:
    audio = recognizer.listen(source)
    text = recognizer.recognize_whisper(audio)  # Локально!
```

### Отправка на бэкенд:
```python
import requests

response = requests.post(
    "http://localhost:8000/api/voice",
    files={"audio": audio_data}
)
```

## Настройка конфигурации

### Переменные окружения

| Переменная | По умолчанию | Описание |
|------------|--------------|----------|
| `LLM_PROVIDER` | `ollama` | Провайдер: ollama / lm_studio / openrouter |
| `LLM_HOST` | `http://localhost:11434` | URL сервера (для локальных провайдеров) |
| `LLM_API_KEY` | `` | API-ключ (нужен для OpenRouter) |
| `LLM_MODEL` | `qwen2.5:7b` | Модель для генерации |
| `LLM_NUM_CTX` | `4096` | Макс. токенов контекста (для Ollama) |
| `LLM_TEMPERATURE` | `0.7` | Температура (0.0-2.0) |
| `CHROMA_PERSIST_DIR` | `./storage/chroma` | Путь к ChromaDB |
| `MEMORY_MAX_CONTEXT` | `20` | Сообщений в истории |
| `MEMORY_SEARCH_RESULTS` | `3` | Результатов поиска |
| `MEMORY_SIMILARITY_THRESHOLD` | `0.3` | Порог схожести |
| `TTS_ENABLED` | `false` | Включить TTS |
| `LOG_LEVEL` | `INFO` | Уровень логов |
| `GUI_ENABLED` | `true` | Включить GUI |
| `GUI_THEME` | `dark` | Тема (dark/light) |
| `GUI_WIDTH` | `900` | Ширина окна |
| `GUI_HEIGHT` | `600` | Высота окна |

## Расширение функциональности

### Добавление нового инструмента (Function Calling)

```python
# В main.py, метод _register_tools
async def save_memory_tool(fact: str, category: str = "general"):
    await self._memory.save_fact(fact, category)
    return f"Факт сохранён: {fact}"

self._llm.register_tool("save_memory", save_memory_tool)
```

### Подключение Silero TTS

1. Установите: `pip install silero-tts`
2. Создайте класс `SileroTTSEngine(ITTSEngine)`
3. Замените `DummyTTSEngine` в `TTSEngine.initialize()`

## Логи

Логи сохраняются в `logs/assistant.log`. Уровень логирования настраивается в `.env`:
```
LOG_LEVEL=DEBUG  # Для отладки
LOG_LEVEL=INFO   # Для обычной работы
```

## Лицензия

MIT
