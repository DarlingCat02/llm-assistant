<p align="center">
  <a href="#english">English</a> &nbsp;|&nbsp; <a href="#russian">Русский</a>
</p>

<a id="english"></a>
# Local AI Assistant

Local AI assistant with voice input/output, web search, **Vision-Language (VL) capabilities** and agent skills for Windows.

## Features

- 🎙️ **Voice input (STT)** — local Whisper, Russian only
- 🔊 **Voice output (TTS)** — OmniVoice synthesis and voice cloning
- 🌐 **Web search** — DuckDuckGo (free, no API keys)
- 📁 **Agent skills** — file creation, opening apps, websites and folders
- 📎 **File attachments** — TXT, PDF, DOCX, **images (PNG, JPG, WebP, GIF, BMP, TIFF)** supported
- 🖥️ **Desktop app** — Tauri (exe file)
- 🧠 **Long-term memory** — ChromaDB
- ⚡ **Fast** — runs on local models via Ollama / LM Studio
- ⌨️ **Global hotkeys** — work outside the app window
- 🎛️ **Customizable UI** — resizable sidebar, settings tabs
- 🧵 **Per-chat context** — each chat has isolated history
- 📊 **Context indicator** — shows used tokens / limit
- 🖼️ **Vision-Language (VL)** — image analysis, OCR, screenshot description
- 🖥️ **Auto screenshot** — triggered by phrases ("look at screen", "screenshot", etc.) with automatic analysis
- 🌐 **Language switch** — English / Russian interface (General → Language), default English on first launch

## Requirements

- Windows 10/11
- Python 3.11+
- Ollama or LM Studio (for LLM)
- GPU with 8GB+ VRAM (for OmniVoice + Whisper + VL)

**For VL capabilities (recommended models in LM Studio):**
- `qwen2.5-vl-3b-instruct` — optimal for 8-12GB VRAM
- `qwen2.5-vl-7b-instruct` — better quality, ~10GB VRAM
- `llava-v1.5-7b` / `llava-v1.6-mistral-7b` — alternatives
- `bakllava-7b` — lightweight alternative

**Important:** VL via API requires a model with vision encoder (qwen2.5-vl, llava, bakllava).
Plain text-only models will not work. For some models you need to download the matching mmproj and put it into the model's folder in LM Studio.

## From the author
The code was written almost entirely with an agent, while I acted only as architect, tester and prompt engineer.
I have long wanted to build my own assistant that could interact with the OS. An assistant that can maintain seamless (or almost seamless) dialogue, open folders and apps, have smart memory, and see the screen. The stack was designed in advance, and STT and TTS models were chosen as the best options I tested in Comfy UI.
Initially it was conceived as a background assistant, but in the end with all capabilities enabled (STT + TTS) VRAM usage can reach 7-10 GB, which already sounds quite substantial.
But it can still be used with full functionality for standard OS interactions, even while playing light VRAM games. So it works well as an assistant. Without TTS the situation looks even more favorable.
However I have no ideas yet how to reduce VRAM consumption. Since I want to use high-quality STT and TTS (especially TTS) models and I haven't found an OmniVoice analog with lower VRAM usage that matches its quality. It is not the most flexible model to configure, but it is good out of the box.
I personally use and recommend 2B-7B models with different quantization. Just browse Hugging Face and pick modern models (e.g. Qwen 3.5, Qwen 3.6, Gemma etc.).
The project is under active development. As new models, ideas and tools appear, the stack will evolve. The architecture will also be gradually improved and refactored.

## Quick start

### 1. Install LLM provider

**Option A: Ollama**
```bash
ollama pull llama3.2:3b
```

**Option B: LM Studio**
- Download from https://lmstudio.ai
- Load a model (e.g. Qwen 3.5 4B)
- Start the server

### 2. Configure .env

```env
# For Ollama:
LLM_PROVIDER=ollama
LLM_MODEL=llama3.2:3b
LLM_HOST=http://localhost:11434

# For LM Studio:
LLM_PROVIDER=lm_studio
LLM_MODEL=qwen3.5-4b:latest
LLM_HOST=http://localhost:1234

# Language (en/ru, default en):
GENERAL_LANGUAGE=en
```

### 3. Launch

Run the exe — the app will start the backend automatically and open the window.

## Where to get ready models and exe

### Option 1: GitHub Releases

Download ready builds from https://github.com/DarlingCat02/llm-assistant/releases

### Option 2: Build from source

#### 1. Download models

```bash
# Whisper (STT)
python -c "from huggingface_hub import snapshot_download; snapshot_download('openai/whisper-large-v3-turbo', local_dir='llm-assistant-tauri/src-tauri/target/release/openai_whisper-large-v3-turbo')"

# OmniVoice (TTS)
python -c "from huggingface_hub import snapshot_download; snapshot_download('k2-fsa/OmniVoice', local_dir='llm-assistant-tauri/src-tauri/target/release/OmniVoice')"
```

#### 2. Install dependencies

```bash
pip install -r requirements.txt
```

#### 3. Build Tauri app

```bash
cd llm-assistant-tauri
npm install
npm run tauri build
```

## Web search

Search works via DuckDuckGo without API keys.

**How to use:**
1. Enable the "🌐 Search" toggle in the UI
2. Ask a question — the assistant will automatically find up-to-date information

**Example questions:**
- "What's the weather in Moscow?"
- "USD to RUB rate"
- "Current US president"

## Chat context

Each chat has **isolated message history**. Switching chats does not mix contexts.

**Context indicator** in the chat header shows:
- How many tokens are used in the current dialog (`prompt_tokens`)
- Maximum limit (`LLM_NUM_CTX` / LM Studio `loaded_context_length`)
- Visual progress bar (green → yellow → red)

Updates after each model response.

## Agent skills

The assistant can work with files, apps and websites on your computer.

### Opening apps

Say "Open notepad", "Launch telegram" or any phrase with the app name.

**How it works:**
1. LLM recognizes the phrase and calls `app_open`
2. Searches `apps.json` by name/alias
3. If found — launches (supports .exe, .lnk, folders)
4. If not found — automatically opens as website in browser

**Example phrases:**
- "Open notepad"
- "Launch telegram"
- "Open discord"
- "Launch calculator"
- "Open replays" (opens folder in Explorer)

### Opening websites

Say "Open youtube", "Open github" — the site will open in the browser.

**How it works:**
- If app is not found in `apps.json`, `app_open` automatically opens as website
- Also available directly via `browser_open`
- Browser is taken from `default_browser` field in `apps.json`

**Example phrases:**
- "Open youtube"
- "Open vk.com"
- "Open github"
- "Open mail.ru website"

### Creating files

Say "Create file notes.txt with shopping list" — the assistant will create the file.

**Files are created in:** folder from `default_save_folder` in apps.json (default `~/Documents`)

### Opening files

Say "Open document.docx" — the file will be opened with the associated app.

### Configuring apps (apps.json)

`apps.json` in the project root contains the list of apps and their aliases.
**Not tracked by git** — local config, will not be pushed.

Use `apps.json.example` as a template.

**Format:**
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
            "path": "E:\\Folder\\with\\video"
        }
    ],
    "default_browser": "yandex",
    "default_save_folder": "C:\\Users\\%USERNAME%\\Documents",
    "blocked_apps": []
}
```

**Fields:**
| Field | Description |
|------|----------|
| `apps` | List of apps with name, aliases and path |
| `default_browser` | App name from `apps` to open websites |
| `default_save_folder` | Default folder for file creation |
| `blocked_apps` | List of blocked apps (will not open) |

**Supported path types:**
- `.exe` — executables
- `.lnk` — Windows shortcuts
- Folders — open in Explorer
- `%USERNAME%` — automatically substituted

**Aliases** — words by which LLM recognizes the request. The more aliases, the better the understanding.

## File and image attachments

Supports TXT, PDF, DOCX files and **images** for analysis.

1. Click 📎 next to the input field
2. Select a file (supported: TXT, PDF, DOCX, PNG, JPG, JPEG, WebP, GIF, BMP, TIFF)
3. Type a message (or leave empty)
4. File/image content will be sent with the message

**Limits:**
- Max 6000 characters from a file
- PDF: up to 20 pages
- DOCX: paragraph and table text
- Images: auto-resize to 1024px, JPEG quality=90 (token optimization)

### Vision-Language (VL) capabilities

The assistant can **analyze images** and **read text from screens/screenshots**:

- **OCR** — reading text from images, screenshots, document photos
- **Image description** — describing photo, screenshot, diagram content
- **Table/chart reading** — extracting data from tables and charts on screenshots
- **Code/UI analysis** — reading code from IDE screenshots, console errors
- **Multilingual** — Russian, English and other languages

**Model requirements:** VL via API needs a model with vision encoder (qwen2.5-vl, llava, bakllava).
When using qwen3.5-4b + mmproj via LM Studio API — works via correct `image_url` format in `content`.

### Auto screenshot by triggers

The assistant can **automatically take a screenshot** and analyze it:

**Triggers (configurable in `.env`):**
- "screen", "screenshot", "look at screen", "show screen"
- "what's on screen", "take screenshot", "capture screen"
- "screen", "screenshot", "look at screen"

**How it works:**
1. User writes: "Look at the screen"
2. Assistant automatically takes a screenshot (JPEG quality=90, max 1024px)
3. Screenshot is sent to the model with the request
4. Model analyzes and answers

**Configure via `.env`:**
```env
SCREENSHOT_ENABLED=true
SCREENSHOT_SAVE_PATH=./screenshots
SCREENSHOT_MONITOR=0
SCREENSHOT_TRIGGERS=screen,screenshot,look at screen,show screen,whats on screen,take screenshot,screen,screenshot,look at screen
```

**Optimization for 2K/4K screens:**
- Auto-resize to 1024px (keeps aspect ratio)
- JPEG quality=90 (quality/tokens balance)
- PNG → JPEG conversion (3-4x token saving)
- Result: ~1700 tokens instead of 5300+ (for 2K screen)

## Voice input (STT)

Whisper transcribes only in Russian.

### Hotkeys

| Action | Key |
|----------|---------|
| Voice input | `Ctrl+Num0` |
| Stop recording | `Ctrl+Num0` again or 2 sec silence |

After stopping — 1 second pause, then text is sent to AI.

### How to change hotkeys

File: `llm-assistant-tauri/src-tauri/src/lib.rs`
```rust
let voice_shortcut = Shortcut::new(Some(Modifiers::CONTROL), Code::Numpad0);
```

## Voice output (TTS)

### Modes

1. **Synthesis** — voice generation from text description
2. **Cloning** — copying voice from reference audio

### Voices for cloning

Add audio files to `voices/` folder:
- Format: MP3, WAV
- Recommended duration: 3-10 seconds

## Configuration (.env)

```env
# === LLM ===
LLM_PROVIDER=lm_studio        # ollama / lm_studio / openrouter
LLM_MODEL=qwen3.5-4b:latest
LLM_HOST=http://localhost:1234
LLM_NUM_CTX=8192
LLM_TEMPERATURE=0.7

# === General ===
GENERAL_LANGUAGE=en           # en / ru

# === ChromaDB ===
CHROMA_PERSIST_DIR=./storage/chroma

# === Memory ===
MEMORY_MAX_CONTEXT_MESSAGES=20
MEMORY_SEARCH_RESULTS=3
MEMORY_SIMILARITY_THRESHOLD=0.3

# === TTS ===
TTS_ENABLED=false
TTS_STEPS=64
TTS_TEMPERATURE=1.0

# === Other ===
LOG_LEVEL=INFO
```

## API Endpoints

| Method | Endpoint | Description |
|-------|----------|----------|
| GET | `/api/status` | App status |
| POST | `/api/chat` | Send message (returns `used_context_tokens`, `max_context_tokens`, supports `images` array) |
| POST | `/api/stt` | Voice recognition |
| POST | `/api/upload` | Upload file (document or image) |
| GET | `/api/chats` | List chats |
| GET | `/api/config` | Current config |
| PUT | `/api/config` | Update config |
| POST | `/api/tts/toggle` | Enable/disable TTS |
| POST | `/api/tts/config` | Configure voice |
| POST | `/api/tts/speak` | Synthesize speech |

## Project structure

```
local_assistant/
├── .env                    # Configuration
├── apps.json               # Apps config (git-ignored)
├── apps.json.example       # Template apps.json
├── config.py               # Python config
├── requirements.txt        # Python dependencies
├── README.md               # This file
├── backend/
│   ├── main.py             # FastAPI backend
│   ├── api.py              # API models
│   └── database.py         # SQLite chat DB
├── src/
│   ├── i18n.py             # Backend i18n
│   ├── main.py             # Assistant logic
│   ├── llm_engine.py       # LLM + Tool Calling
│   ├── stt_engine.py       # Whisper STT (Russian)
│   ├── tts_engine.py       # OmniVoice TTS
│   ├── web_search.py       # DuckDuckGo search
│   ├── agent_tools.py      # Agent tools
│   ├── file_processor.py   # File handling
│   └── memory_manager.py   # ChromaDB memory
├── llm-assistant-tauri/    # Tauri desktop app
│   ├── dist/               # Built frontend
│   ├── index.html           # Vite entry
│   ├── src/                 # Frontend sources
│   │   ├── app.js           # UI logic
│   │   ├── i18n.js          # Frontend i18n
│   │   ├── locales/en.json  # English translations
│   │   ├── locales/ru.json  # Russian translations
│   │   └── style.css        # Styles
│   ├── src-tauri/
│   │   ├── src/lib.rs      # Hotkeys
│   │   └── target/release/
│   │       ├── llm-assistant-tauri.exe  # Built app
│   │       ├── OmniVoice/              # TTS model
│   │       └── openai_whisper-*/       # STT model
│   ├── package.json
│   └── vite.config.ts
├── storage/                 # ChromaDB data
└── voices/                  # Voices for cloning
```

## Tools (Tool Calling)

The assistant uses the following tools:

| Tool | Description |
|------------|----------|
| `web_search_ddg` | Web search via DuckDuckGo |
| `file_create` | Create file with content |
| `app_open` | Open app/folder/website |
| `file_open` | Open file with associated app |
| `browser_open` | Open website in browser |
| `capture_screen` | Screenshot + VL analysis |

## Troubleshooting

### App does not open
1. Check Ollama/LM Studio
2. Check .env

### Search does not work
1. Check internet
2. Try another query

### Hotkeys do not work
1. Check NumLock
2. Make sure app is focused

### Apps do not open
1. Check `apps.json` — is the app there
2. Check exe paths
3. For `.lnk` and folders — uses `os.startfile` (implemented)

### Images not analyzed / 400 Bad Request
1. **Check model in LM Studio** — must be VL model
2. **Check `.env`** — `LLM_MODEL` must point to VL model
3. **Restart backend** after changing model in LM Studio
3. **Context overflow** — increase context in LM Studio (8192 or 16384)

### Auto screenshot not working
1. **Check triggers** in `.env` — `SCREENSHOT_TRIGGERS`
2. **Check logs** — `Screenshot captured: monitor=0, size=XXXXX bytes`
3. **400 Bad Request on screenshot** — model is not VL or context overflow (increase context)
4. **Model does not see screen** — ensure VL model with mmproj is selected in LM Studio

### Images not uploading
1. Check format — supported: PNG, JPG, JPEG, WebP, GIF, BMP, TIFF
2. File size should not exceed token limit (auto-resize to 1024px)

## License

MIT

---

<a id="russian"></a>
# Local AI Assistant

Локальный AI-ассистент с голосовым вводом/выводом, поиском в интернете, **Vision-Language (VL) возможностями** и агентными способностями для Windows.

## Особенности

- 🎙️ **Голосовой ввод (STT)** — локальный Whisper, только русский язык
- 🔊 **Голосовой вывод (TTS)** — OmniVoice синтез и клонирование голоса
- 🌐 **Поиск в интернете** — DuckDuckGo (бесплатно, без API ключей)
- 📁 **Агентные способности** — создание файлов, открытие приложений, сайтов и папок
- 📎 **Прикрепление файлов** — поддержка TXT, PDF, DOCX, **изображений (PNG, JPG, WebP, GIF, BMP, TIFF)**
- 🖥️ **Desktop app** — Tauri (exe файл)
- 🧠 **Долговременная память** — ChromaDB
- ⚡ **Быстрый** — работает на локальных моделях через Ollama/LM Studio
- ⌨️ **Глобальные горячие клавиши** — работают вне окна приложения
- 🎛️ **Настраиваемый UI** — изменяемая ширина боковой панели, вкладки настроек
- 🧵 **Контекст по чатам** — каждый чат имеет свою историю, не смешивается
- 📊 **Индикатор контекста** — показывает использованные токены / лимит
- 🖼️ **Vision-Language (VL) возможности** — анализ изображений, OCR, описание скриншотов
- 🖥️ **Авто-скриншот экрана** — по триггерам ("посмотри на экран", "скриншот" и др.) с автоматическим анализом
- 🌐 **Переключение языка** — английский / русский интерфейс (Общие → Язык), по умолчанию английский при первом запуске

## Требования

- Windows 10/11
- Python 3.11+
- Ollama или LM Studio (для LLM)
- GPU с 8GB+ VRAM (для OmniVoice + Whisper + VL)

**Для VL возможностей (рекомендуемые модели в LM Studio):**
- `qwen2.5-vl-3b-instruct` — оптимально для 8-12GB VRAM
- `qwen2.5-vl-7b-instruct` — лучше качество, ~10GB VRAM
- `llava-v1.5-7b` / `llava-v1.6-mistral-7b` — альтернативы
- `bakllava-7b` — лёгкая альтернатива

**Важно:** Для VL через API нужна модель с vision encoder (qwen2.5-vl, llava, bakllava). 
Обычные text only модели не подойдут. Для определенных моделей нужно скачать соответствующий mmproj и кинуть в папку к самой модели LM Studio. 

## От автора
Код был написан почти полностью с помощью агента, а я выступал лишь в роли архитектора, тестировщика, занимался промпт инженирингом. 
У меня давно было желание сделать своего ассистента который бы смог взаимодействовать с ОС. Ассистента, который может поддерживать бесшовный (или почти бесшовный) диалог, открывать папки, приложения, имел умную память, а также видел экран. Стек этого ассистента был продуман заранее, а STT и TTS модели были выбраны именно такие т.к я посчитал их лучшим вариантом (из всех которые тестировал в Comfy UI).
Вообще изначально он задумывался как фоновый ассистент, однако по итогу получилось так, что при включении всех возможностей (STT + TTS) вес в VRAM может достигать 7-10 ГБ, что уже звучит очень внушительно.
Но его всё ещё вполне можно использовать с полным функционалом при стандартных взаимодействиях с ОС, при игре в нетребовательные к VRAM игры. Т.е он вполне выступает в роли ассистента. Если не использовать TTS, то ситуация выглядит ещё более благоприятной.
Однако пока у меня нет идей как можно уменьшить потребление VRAM. Поскольку я хочу использовать качественные STT и TTS (Особенно TTS) модели и аналог OmniVoice по качеству с меньшим потрелением VRAM я не нашел. Это не самая гибкая в настройке модель, но она хороша изначально.
Лично я использую и советую модели на 2B-7B параметров разного квантования. Достаточно лазить в Hugging Face и брать современные модели (например Qwen 3.5, Qwen 3.6, Gemma и т.п).
Проект находится в активной разработке. По мере появления новых моделей, идей и инструментов стек будет эволюционировать. Архитектура также будет постепенно улучшаться и рефакториться. 

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

# Язык (en/ru, по умолчанию en):
GENERAL_LANGUAGE=en
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
- Максимальный лимит (`LLM_NUM_CTX` / LM Studio `loaded_context_length`)
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

## Прикрепление файлов и изображений

Поддерживается загрузка TXT, PDF, DOCX файлов и **изображений** для анализа.

1. Нажмите 📎 рядом с полем ввода
2. Выберите файл (поддерживаются: TXT, PDF, DOCX, PNG, JPG, JPEG, WebP, GIF, BMP, TIFF)
3. Напишите сообщение (или пустое)
4. Содержимое файла/изображение отправится вместе с сообщением

**Лимиты:**
- Максимум 6000 символов из файла
- PDF: до 20 страниц
- DOCX: текст абзацев и таблиц
- Изображения: автоматический ресайз до 1024px, JPEG quality=90 (оптимизация токенов)

### Vision-Language (VL) возможности

Ассистент может **анализировать изображения** и **читать текст с экранов/скриншотов**:

- **OCR** — чтение текста с изображений, скриншотов, фото документов
- **Описание изображений** — описание содержания фото, скриншотов, диаграмм
- **Чтение таблиц/графиков** — извлечение данных из таблиц и графиков на скриншотах
- **Анализ кода/интерфейсов** — чтение кода с скриншотов IDE, ошибок в консоли
- **Мультиязычность** — русский, английский и другие языки

**Требования к модели:** Для VL через API нужна модель с vision encoder (qwen2.5-vl, llava, bakllava). 
При использовании qwen3.5-4b + mmproj через LM Studio API — работает через правильный формат `image_url` в `content`.

### Авто-скриншот экрана по триггерам

Ассистент может **автоматически делать скриншот** и анализировать его:

**Триггеры (настраиваемые в `.env`):**
- "экран", "скриншот", "смотри на экран", "покажи экран"
- "что на экране", "сделай скриншот", "capture screen"
- "скрин", "screenshot", "посмотри на экран"

**Как работает:**
1. Пользователь пишет: "Посмотри на экран"
2. Ассистент автоматически делает скриншот (JPEG quality=90, max 1024px)
3. Скриншот передаётся модели вместе с запросом
4. Модель анализирует и отвечает

**Настройка через `.env`:**
```env
SCREENSHOT_ENABLED=true
SCREENSHOT_SAVE_PATH=./screenshots
SCREENSHOT_MONITOR=0
SCREENSHOT_TRIGGERS=экран,скриншот,смотри на экран,покажи экран,что на экране,сделай скриншот,скрин,screenshot,посмотри на экран
```

**Оптимизация для 2K/4K экранов:**
- Автоматический ресайз до 1024px (сохраняет пропорции)
- JPEG quality=90 (баланс качества/токенов)
- PNG → JPEG конвертация (экономия токенов в 3-4x)
- Результат: ~1700 токенов вместо 5300+ (для 2K экрана)

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

# === General ===
GENERAL_LANGUAGE=en           # en / ru

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
| POST | `/api/chat` | Отправить сообщение (возвращает `used_context_tokens`, `max_context_tokens`, поддерживает `images` массив) |
| POST | `/api/stt` | Распознать голос |
| POST | `/api/upload` | Загрузить файл (документ или изображение) |
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
│   ├── i18n.py             # Backend i18n
│   ├── main.py             # Assistant логика
│   ├── llm_engine.py       # LLM + Tool Calling
│   ├── stt_engine.py       # Whisper STT (русский)
│   ├── tts_engine.py       # OmniVoice TTS
│   ├── web_search.py       # DuckDuckGo поиск
│   ├── agent_tools.py      # Агентные инструменты
│   ├── file_processor.py   # Обработка файлов
│   └── memory_manager.py   # ChromaDB память
├── llm-assistant-tauri/    # Tauri desktop app
│   ├── dist/               # Собранный фронтенд
│   ├── index.html           # Точка входа Vite
│   ├── src/                 # Исходники фронтенда
│   │   ├── app.js           # UI логика
│   │   ├── i18n.js          # Frontend i18n
│   │   ├── locales/en.json  # English translations
│   │   ├── locales/ru.json  # Russian translations
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
| `capture_screen` | Скриншот экрана + анализ через VL |

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

### Изображения не анализируются / 400 Bad Request
1. **Проверьте модель в LM Studio** — должна быть VL-модель
2. **Проверьте `.env`** — `LLM_MODEL` должен указывать на VL-модель
3. **Перезапустите бэкенд** после смены модели в LM Studio
3. **Контекст переполнен** — увеличьте контекст в LM Studio (8192 или 16384)

### Авто-скриншот не работает
1. **Проверьте триггеры** в `.env` — `SCREENSHOT_TRIGGERS`
2. **Проверьте логи** — `Скриншот сделан: monitor=0, size=XXXXX bytes`
3. **400 Bad Request при скриншоте** — модель не VL или превышен контекст (увеличьте контекст)
4. **Модель не видит экран** — проверьте, что в LM Studio выбрана VL-модель с mmproj

### Изображения не загружаются
1. Проверьте формат — поддерживаются: PNG, JPG, JPEG, WebP, GIF, BMP, TIFF
2. Размер файла не должен превышать лимит токенов (авто-ресайз до 1024px)

## Лицензия

MIT
