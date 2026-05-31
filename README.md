# Local AI Assistant

Локальный AI-ассистент с голосовым вводом/выводом, поиском в интернете и агентными способностями для Windows.

## Особенности

- 🎙️ **Голосовой ввод (STT)** — локальный Whisper, только русский язык
- 🔊 **Голосовой вывод (TTS)** — OmniVoice синтез и клонирование голоса
- 🌐 **Поиск в интернете** — DuckDuckGo (бесплатно, без API ключей)
- 📁 **Агентные способности** — создание файлов, открытие приложений, сайтов и папок
- 📎 **Прикрепление файлов** — поддержка TXT, PDF, DOCX
- 🖥️ **Desktop app** — Tauri (exe файл)
- 🧠 **Долговременная память** — ChromaDB
- ⚡ **Быстрый** — работает на локальных моделях через Ollama/LM Studio
- ⌨️ **Глобальные горячие клавиши** — работают вне окна приложения
- 🎛️ **Настраиваемый UI** — изменяемая ширина боковой панели, вкладки настроек
- 🧵 **Контекст по чатам** — каждый чат имеет свою историю, не смешивается
- 📊 **Индикатор контекста** — показывает использованные токены / лимит

## Требования

- Windows 10/11
- Python 3.11+
- Ollama или LM Studio (для LLM)
- GPU с 8GB+ VRAM (для OmniVoice + Whisper)

## Быстрый старт

### 1. Установка LLM провайдера

**Вариант A: Ollama**
```bash
ollama pull llama3.2:3b
```

**Вариант B: LM Studio**
- Скачайте с https://lmstudio.ai
- Загрузите модель (например, Qwen 3.5 4B)
- Запустите сервер

### 2. Настройка .env

```env
# Для Ollama:
LLM_PROVIDER=ollama
LLM_MODEL=llama3.2:3b
LLM_HOST=http://localhost:11434

# Для LM Studio:
LLM_PROVIDER=lm_studio
LLM_MODEL=qwen3.5-4b:latest
LLM_HOST=http://localhost:1234
```

### 3. Запуск

Запустите exe — приложение само запустит backend и откроет окно.

## Где скачать готовые модели и exe

### Вариант 1: GitHub Releases

Скачайте готовые сборки из https://github.com/DarlingCat02/llm-assistant/releases

### Вариант 2: Сборка из исходников

#### 1. Скачайте модели

```bash
# Whisper (STT)
python -c "from huggingface_hub import snapshot_download; snapshot_download('openai/whisper-large-v3-turbo', local_dir='llm-assistant-tauri/src-tauri/target/release/openai_whisper-large-v3-turbo')"

# OmniVoice (TTS)
python -c "from huggingface_hub import snapshot_download; snapshot_download('k2-fsa/OmniVoice', local_dir='llm-assistant-tauri/src-tauri/target/release/OmniVoice')"
```

#### 2. Установите зависимости

```bash
pip install -r requirements.txt
```

#### 3. Соберите Tauri app

```bash
cd llm-assistant-tauri
npm install
npm run tauri build
```

## Поиск в интернете

Поиск работает через DuckDuckGo без API ключей.

**Как использовать:**
1. Включите переключатель "🌐 Поиск" в интерфейсе
2. Задайте вопрос — ассистент автоматически найдёт актуальную информацию

**Примеры вопросов:**
- "Какая сейчас погода в Москве?"
- "Курс доллара к рублю"
- "Текущий президент США"

## Контекст чата

Каждый чат имеет **отдельную историю сообщений**. При переключении между чатами контекст не смешивается.

**Индикатор контекста** в шапке чата показывает:
- Сколько токенов использовано в текущем диалоге (`prompt_tokens`)
- Максимальный лимит (`LLM_NUM_CTX`)
- Визуальный progress bar (зелёный → жёлтый → красный по мере заполнения)

Обновляется после каждого ответа модели.

## Агентные способности

Ассистент умеет работать с файлами, приложениями и сайтами на компьютере.

### Открытие приложений

Скажите "Открой блокнот", "Запусти телеграм" или любую другую фразу с названием приложения.

**Как работает:**
1. LLM распознаёт фразу и вызывает инструмент `app_open`
2. Ищет приложение в `apps.json` по имени/алиасу
3. Если нашёл — запускает (поддерживаются .exe, .lnk, папки)
4. Если не нашёл — автоматически открывает как сайт в браузере

**Примеры фраз:**
- "Открой блокнот"
- "Запусти телеграм"
- "Открой дискорд"
- "Запустите калькулятор"
- "Открой повторы" (откроет папку в проводнике)

### Открытие сайтов

Скажите "Открой ютуб", "Открой github" — сайт откроется в браузере.

**Как работает:**
- Если приложение не найдено в `apps.json`, `app_open` автоматически открывает как сайт
- Можно также напрямую через `browser_open`
- Браузер берётся из поля `default_browser` в `apps.json`

**Примеры фраз:**
- "Открой ютуб"
- "Открой vk.com"
- "Открой github"
- "Открой сайт mail.ru"

### Создание файлов

Скажите "Создай файл notes.txt со списком покупок" — ассистент создаст файл.

**Файлы создаются в:** папка из `default_save_folder` в apps.json (по умолчанию `~/Documents`)

### Открытие файлов

Скажите "Открой document.docx" — файл откроется в ассоциированном приложении.

### Настройка приложений (apps.json)

Файл `apps.json` в корне проекта содержит список приложений и их алиасов.
**Не отслеживается git'ом** — локальный конфиг, не попадёт в репозиторий.

Используйте `apps.json.example` как шаблон.

**Формат:**
```json
{
    "apps": [
        {
            "name": "telegram",
            "aliases": ["телеграм", "telegram", "tg", "телега"],
            "path": "C:\\Users\\%USERNAME%\\AppData\\Roaming\\Telegram Desktop\\Telegram.exe"
        },
        {
            "name": "replays",
            "aliases": ["реплеи", "повторы"],
            "path": "E:\\Папка\\с\\видео"
        }
    ],
    "default_browser": "yandex",
    "default_save_folder": "C:\\Users\\%USERNAME%\\Documents",
    "blocked_apps": []
}
```

**Поля:**
| Поле | Описание |
|------|----------|
| `apps` | Список приложений с именем, алиасами и путём |
| `default_browser` | Имя приложения из `apps` для открытия сайтов |
| `default_save_folder` | Папка по умолчанию для создания файлов |
| `blocked_apps` | Список заблокированных приложений (не откроются) |

**Поддерживаемые типы путей:**
- `.exe` — исполняемые файлы
- `.lnk` — ярлыки Windows
- Папки — открываются в проводнике
- `%USERNAME%` — автоматически подставляется имя пользователя

**Алиасы** — это слова, по которым LLM распознаёт запрос. Чем больше алиасов — тем лучше понимание.

## Прикрепление файлов

Поддерживается загрузка TXT, PDF и DOCX файлов для анализа.

1. Нажмите 📎 рядом с полем ввода
2. Выберите файл
3. Напишите сообщение (или пустое)
4. Содержимое файла отправится вместе с сообщением

**Лимиты:**
- Максимум 6000 символов из файла
- PDF: до 20 страниц
- DOCX: текст абзацев и таблиц

## Голосовой ввод (STT)

Whisper транскрибирует только на русском языке.

### Горячие клавиши

| Действие | Клавиша |
|----------|---------|
| Голосовой ввод | `Ctrl+Num0` |
| Остановка записи | `Ctrl+Num0` (повторно) или 2 сек тишины |

После остановки — 1 секунда паузы, затем текст отправляется AI.

### Как изменить горячие клавиши

Файл: `llm-assistant-tauri/src-tauri/src/lib.rs`
```rust
let voice_shortcut = Shortcut::new(Some(Modifiers::CONTROL), Code::Numpad0);
```

## Голосовой вывод (TTS)

### Режимы

1. **Синтез** — генерация голоса по текстовому описанию
2. **Клонирование** — копирование голоса из референсного аудио

### Голоса для клонирования

Добавьте аудио файлы в папку `voices/`:
- Формат: MP3, WAV
- Рекомендуемая длительность: 3-10 секунд

## Конфигурация (.env)

```env
# === LLM ===
LLM_PROVIDER=lm_studio        # ollama / lm_studio / openrouter
LLM_MODEL=qwen3.5-4b:latest
LLM_HOST=http://localhost:1234
LLM_NUM_CTX=8192
LLM_TEMPERATURE=0.7

# === ChromaDB ===
CHROMA_PERSIST_DIR=./storage/chroma

# === Память ===
MEMORY_MAX_CONTEXT_MESSAGES=20
MEMORY_SEARCH_RESULTS=3
MEMORY_SIMILARITY_THRESHOLD=0.3

# === TTS ===
TTS_ENABLED=false
TTS_STEPS=64
TTS_TEMPERATURE=1.0

# === Прочее ===
LOG_LEVEL=INFO
```

## API Endpoints

| Метод | Эндпоинт | Описание |
|-------|----------|----------|
| GET | `/api/status` | Статус приложения |
| POST | `/api/chat` | Отправить сообщение (возвращает `used_context_tokens`, `max_context_tokens`) |
| POST | `/api/stt` | Распознать голос |
| POST | `/api/upload` | Загрузить файл |
| GET | `/api/chats` | Список чатов |
| GET | `/api/config` | Текущая конфигурация |
| PUT | `/api/config` | Обновить конфигурацию |
| POST | `/api/tts/toggle` | Включить/выключить TTS |
| POST | `/api/tts/config` | Настроить голос |
| POST | `/api/tts/speak` | Озвучить текст |

## Структура проекта

```
local_assistant/
├── .env                    # Конфигурация
├── apps.json               # Конфиг приложений (игнорируется git'ом)
├── apps.json.example       # Шаблон apps.json
├── config.py               # Python конфиг
├── requirements.txt        # Зависимости Python
├── README.md               # Этот файл
├── backend/
│   ├── main.py             # FastAPI backend
│   ├── api.py              # API модели
│   └── database.py         # SQLite база чатов
├── src/
│   ├── main.py             # Assistant логика
│   ├── llm_engine.py       # LLM + Tool Calling
│   ├── stt_engine.py       # Whisper STT (русский)
│   ├── tts_engine.py       # OmniVoice TTS
│   ├── web_search.py       # DuckDuckGo поиск
│   ├── agent_tools.py      # Агентные инструменты
│   ├── file_processor.py   # Обработка файлов
│   └── memory_manager.py   # ChromaDB память
├── frontend/                # Веб-фронтенд (для браузера)
│   ├── index.html
│   ├── app.js
│   └── style.css
├── llm-assistant-tauri/    # Tauri desktop app
│   ├── dist/               # Собранный фронтенд
│   ├── index.html           # Точка входа Vite
│   ├── src/                 # Исходники фронтенда
│   │   ├── app.js           # UI логика
│   │   ├── index.html       # Интерфейс (для Vite)
│   │   └── style.css        # Стили
│   ├── src-tauri/
│   │   ├── src/lib.rs      # Горячие клавиши
│   │   └── target/release/
│   │       ├── llm-assistant-tauri.exe  # Собранное приложение
│   │       ├── OmniVoice/              # TTS модель
│   │       └── openai_whisper-*/       # STT модель
│   ├── package.json
│   └── vite.config.ts
├── storage/                 # ChromaDB данные
└── voices/                  # Голоса для клонирования
```

## Инструменты (Tool Calling)

Ассистент использует следующие инструменты:

| Инструмент | Описание |
|------------|----------|
| `web_search_ddg` | Поиск в интернете через DuckDuckGo |
| `file_create` | Создание файла с содержимым |
| `app_open` | Открытие приложения/папки/сайта |
| `file_open` | Открытие файла в ассоциированной программе |
| `browser_open` | Открытие сайта в браузере |

## Устранение проблем

### Приложение не открывается
1. Проверьте Ollama/LM Studio
2. Проверьте .env

### Поиск не работает
1. Проверьте интернет
2. Попробуйте другой запрос

### Горячие клавиши не работают
1. Проверьте NumLock
2. Убедитесь что приложение в фокусе

### Приложения не открываются
1. Проверьте `apps.json` — есть ли нужное приложение
2. Проверьте пути к exe файлам
3. Для `.lnk` и папок — используйте `os.startfile` (реализовано)

## Лицензия

MIT
