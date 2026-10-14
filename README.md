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
- 🔧 **Visible agent actions** — every tool call the assistant made is shown above the answer (collapsible)
- 🎭 **Personas** — switchable behaviour presets, applied instantly without a restart
- ✍️ **Personality editor** — extra instructions layered on top of the system prompt (per language)
- 🧠 **Long-term memory** — ChromaDB, with shared user facts and per-persona notes
- 👤 **Avatars** — pick an emoji or upload your own picture for you and the assistant
- 📎 **File attachments** — TXT, PDF, DOCX, **images (PNG, JPG, WebP, GIF, BMP, TIFF)** supported
- 🖥️ **Desktop app** — Tauri (exe file)
- ⚡ **Fast** — runs on local models via Ollama / LM Studio
- ⌨️ **Global hotkeys** — work outside the app window, editable in Settings → General
- 🎛️ **Customizable UI** — resizable sidebar, settings tabs
- 🧵 **Per-chat context** — each chat has isolated history
- 📊 **Context indicator** — shows used tokens / limit
- 🖼️ **Vision-Language (VL)** — image analysis, OCR, screenshot description
- 🖥️ **Auto screenshot** — triggered by phrases ("look at screen", "screenshot", etc.) with automatic analysis
- 🌐 **Language switch** — English / Russian interface (General → Language), default English on first launch
- 🖥️ **Terminal** — built-in backend log viewer (bottom panel 40vh), external console hidden by default (toggle in General)

## Requirements

- Windows 10/11
- Python 3.11+
- Ollama or LM Studio (for LLM)
- GPU with 8GB+ VRAM (for OmniVoice + Whisper + VL)
- Node.js 18+ and Rust (only to build the exe; easiest via `install.bat` option 8)

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

Easiest on Windows: run `install.bat` and choose option [8] (full installation). Manual steps below:

#### 1. Download models

```bash
# Whisper (STT)
python -c "from huggingface_hub import snapshot_download; snapshot_download('openai/whisper-large-v3-turbo', local_dir='models/whisper-large-v3-turbo')"

# OmniVoice (TTS)
python -c "from huggingface_hub import snapshot_download; snapshot_download('k2-fsa/OmniVoice', local_dir='models/omnivoice')"
```

#### 2. Install dependencies

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

The app uses the `venv` Python automatically when it exists (both CLI and Tauri backend), falling back to system Python.

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

### Seeing what the assistant did

Every tool call made during a turn is reported back and rendered as a collapsible
**"Выполненные действия"** block above the answer:

```
▾ Выполненные действия (2)
  🔧 app_open      name=notepad        → Запущено: notepad
  ⚠️ file_create   path=demo.txt       → Ошибка: [WinError 5] доступ запрещён
```

- The block is collapsed by default so it does not clutter the chat.
- Failed calls are highlighted in red with a ⚠️ marker.
- Arguments and results are truncated (200 characters) — long tool output (for
  example a base64 screenshot) is never dumped into the chat.

> Small models sometimes answer with code instead of actually calling a tool.
> That is a model limitation, not a bug: no tool was executed, so nothing is shown.

### Personas

A persona is a **behaviour layer** on top of the system prompt — tone, style,
role. It never replaces the service rules (search policy, tool usage, language).

- Switch in the chat header (the 🎭 pill) or manage the catalog in
  **Settings → 🎭🎭 Персоны**.
- Switching is instant: the new prompt is used from the very next message, no
  restart.
- **"Без персоны"** = the standard system prompt.
- Each persona can carry its own `temperature`; empty = use the model setting.
- The catalog lives in `personas.json` next to `apps.json` (git-ignored).
  `personas.json.example` shows the format.

If `personas.json` is missing or corrupted the app logs a warning and falls back
to the standard prompt — it never overwrites a file it could not parse.

### Personality layer (extra instructions)

**Settings → 🎭 Личность** holds two text boxes (Russian / English) that are
appended to the system prompt. The service rules stay system-managed and are
read-only; here you only set style and character.

Priority: active persona → personality layer → standard prompt.

### The two prompt blocks (RU / EN)

A persona stores `prompt_ru` and `prompt_en`. These are **two different prompts
for two interface languages**, not translations of one another — fill in the one
that matches your language and leave the other empty.

**Why:** the base system prompt is bilingual too, and its content differs between
the two rather than just its wording. The Russian version teaches the model the
tool triggers "открой блокнот" / "посмотри на экран"; the English one teaches
"open notepad" / "look at screen". Pairing a Russian base with an English persona
hands the model a blend of two rule sets, which noticeably degrades small models.

**How the choice is made:** `_get_personality_layer()` in `src/llm_engine.py`
reads `GENERAL_LANGUAGE` (Settings → General → Language) and applies exactly one
block. The other is ignored until you switch the interface language.

The field in use is marked with a **"используется"** badge in both the Personas
and the Personality tabs.

### Avatars

Click the 👤 / 🤖 buttons in the chat header to change either avatar:

- pick one of the preset emoji,
- upload your own image (PNG / JPG / WebP / GIF, up to 5 MB),
- delete an uploaded avatar.

Uploaded images are centre-cropped to a square and stored at 128×128 in
`avatars/` (git-ignored). The selection is kept in the browser's local storage;
a reference to a file that no longer exists is replaced by the default emoji.

### Memory scopes

Memory uses one ChromaDB collection with a `scope` field in the metadata:

- `user` — facts about you, shared by every persona;
- `<persona_id>` — notes that belong to one persona only.

With a persona active the assistant searches `["user", <persona_id>]`; with no
persona it searches everything. Extracted facts about you are always stored in
`user`, so switching personas never loses them.

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

## Wake word

Say a phrase to wake the assistant without touching the keyboard. The phrase is
whatever you type in **Settings → General → Wake word** — for example just the
assistant's name. Case and punctuation do not matter.

**How it works**

```
microphone (open while enabled)
  -> Silero VAD          decides whether anyone is talking
  -> Whisper tiny        transcribes, only while speech is detected
  -> phrase match        fuzzy compare with your phrase
  -> the app starts the normal voice input
```

Cost measured on a mid-range CPU: **~4% of one core while idle**, **~19% while
someone is talking** (and nothing at all in silence, because the VAD gates the
transcription). The VAD is what makes an always-on listener affordable.

**Which model is used.** Its own small one (`whisper-tiny` or `base` in
`./models/`), not the `large-v3-turbo` used for real commands — recognition of
commands is completely unaffected. The decoding language follows the script of
your phrase, so a Russian phrase is not decoded in English mode.

**Privacy.** While enabled the microphone stays open, which Windows shows as a
recording indicator. Audio is recognised on the fly and discarded — nothing is
written to disk. It is **off by default** and has to be switched on explicitly.

**If it does not start** the reason is shown under the settings (usually the
model is missing). Fetch it once with:

```bash
python tests/fetch_whisper_model.py tiny
```

A missing model, a missing audio backend or a busy microphone leave the app
starting normally — wake word just stays off.

## Voice input (STT)

Whisper transcribes only in Russian.

### Model selection

Set `STT_MODEL` in `.env`: an alias, a Hugging Face `owner/repo` id, or a local folder path. Missing models are downloaded on first use into `models/`.

| Alias | Model | VRAM (approx) |
|---|---|---|
| `tiny` | `openai/whisper-tiny` | ~1 GB |
| `base` | `openai/whisper-base` | ~1 GB |
| `small` | `openai/whisper-small` | ~2 GB |
| `medium` | `openai/whisper-medium` | ~5 GB |
| `large` | `openai/whisper-large-v3` | ~10 GB |
| `large-v3-turbo` (default) | `openai/whisper-large-v3-turbo` | ~4 GB |

### Hotkeys

| Action | Key (default) |
|----------|---------|
| Voice input | `Ctrl+Shift+V` or `Ctrl+Num0` |
| Live mode | `Ctrl+Shift+L` |
| Stop recording | Same voice key again or 2 sec silence |

After stopping — 1 second pause, then text is sent to AI.

### How to change hotkeys

Set in `.env` (applied on app restart, format `Ctrl+Shift+V`, `Alt+F9`, `F12`, ...):

```env
HOTKEY_VOICE=Ctrl+Shift+V
HOTKEY_VOICE_NUM=Ctrl+Num0
HOTKEY_LIVE=Ctrl+Shift+L
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

# === Personality (extra instructions appended to the system prompt) ===
# Edited in Settings -> Personality; newlines are stored as \n
PERSONALITY_RU=
PERSONALITY_EN=

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
TTS_DEBUG_SAVE=false       # save debug WAV copies to debug_tts/

# === STT ===
STT_MODEL=large-v3-turbo   # tiny / base / small / medium / large / large-v3-turbo, 'owner/repo' or folder path

# === Hotkeys (global, applied on restart) ===
HOTKEY_VOICE=Ctrl+Shift+V
HOTKEY_VOICE_NUM=Ctrl+Num0
HOTKEY_LIVE=Ctrl+Shift+L

# === Other ===
LOG_LEVEL=INFO
```

> `STT_MODEL` and `HOTKEY_*` can be edited in the app (Settings → 🎙 Голос and
> Settings → Общие) and are applied after a restart. `PERSONALITY_*` apply
> immediately — no restart needed.

## API Endpoints

| Method | Endpoint | Description |
|-------|----------|----------|
| GET | `/api/status` | App status |
| POST | `/api/chat` | Send message (returns `used_context_tokens`, `max_context_tokens`, `actions`, supports `images` array) |
| POST | `/api/stt` | Voice recognition |
| POST | `/api/upload` | Upload file (document or image) |
| GET | `/api/chats` | List chats |
| GET | `/api/config` | Current config |
| PUT | `/api/config` | Update config |
| GET | `/api/personas` | Persona catalog + active selection |
| PUT | `/api/personas` | Replace the persona catalog |
| POST | `/api/personas/activate` | Switch persona at runtime (`{"id": "editor"}`, `{"id": null}` for none) |
| GET | `/api/avatars` | List uploaded avatars |
| POST | `/api/avatars` | Upload an avatar (multipart `file`, resized to 128×128 PNG) |
| GET | `/api/avatars/{name}` | Serve an avatar image |
| DELETE | `/api/avatars/{name}` | Delete an avatar |
| POST | `/api/tts/toggle` | Enable/disable TTS |
| POST | `/api/tts/config` | Configure voice |
| POST | `/api/tts/speak` | Synthesize speech |

## Project structure

```
local_assistant/
├── .env                    # Configuration
├── apps.json               # Apps config (git-ignored)
├── apps.json.example       # Template apps.json
├── personas.json           # Persona catalog (git-ignored)
├── personas.json.example   # Template personas.json
├── avatars/                # Uploaded avatars (git-ignored)
├── config.py               # Python config
├── requirements.txt        # Python dependencies
├── requirements-dev.txt    # Test dependencies (pytest)
├── pytest.ini              # Test config
├── tests/                  # Automated tests
├── README.md               # This file
├── backend/
│   ├── main.py             # FastAPI backend
│   ├── api.py              # API models
│   ├── database.py         # SQLite chat DB
│   └── background_tasks.py # Background tasks (Ollama keep-alive)
├── src/
│   ├── i18n.py             # Backend i18n
│   ├── main.py             # Assistant logic
│   ├── llm_engine.py       # LLM + Tool Calling
│   ├── personas.py         # Persona storage
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
│   │   ├── avatars.js       # User/bot avatars
│   │   ├── personas.js      # Persona switcher + catalog editor
│   │   ├── i18n.js          # Frontend i18n
│   │   ├── locales/en.json  # English translations
│   │   ├── locales/ru.json  # Russian translations
│   │   └── style.css        # Styles
│   ├── src-tauri/
│   │   ├── src/lib.rs      # Hotkeys
│   │   └── target/release/
│   │       └── llm-assistant-tauri.exe  # Built app
│   ├── package.json
│   └── vite.config.ts
├── models/                  # Local models
│   ├── omnivoice/           # TTS model
│   └── whisper-large-v3-turbo/  # STT model
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

## Tests

```bash
pip install -r requirements-dev.txt
python -m pytest -q
```

The suite never needs a GPU, an LLM server, STT or TTS — everything heavy is
mocked or replaced with `tmp_path`. It covers import smoke tests, prompt assembly
(base + personality + persona), the persona store (including broken/missing
files), avatar endpoints (including path traversal), memory scopes, config
round-trips and the tool-action payload.

Run it after changing config, prompts, personas or memory logic — it needs about
a second and catches the regressions that are hard to see in the UI.

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

### "Assistant not initialized" (503)
1. **Kill stale Python processes** — an old backend may still hold port 8000 (`taskkill /F /IM python.exe`), then restart the app
2. Wait for backend startup (~10-60 s on first run while the embedding model loads)

### TTS model fails to load
1. **Read the error text** — the app shows the backend reason in the alert
2. **First load takes ~1 minute** (OmniVoice + Whisper cache), do not click twice
3. **Check VRAM** — full stack (LLM + Whisper + OmniVoice) needs 7-10 GB

### Voice recognition fails (STT 422)
1. **Speak right after pressing the button**, louder and longer than a second
2. Empty/silent recordings are rejected — check the microphone
3. Slow recognition on CPU means torch without CUDA — reinstall: `venv\Scripts\python -m pip install torch --index-url https://download.pytorch.org/whl/cu121`

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
- 🔧 **Видимые действия ассистента** — каждый вызов инструмента показан над ответом (сворачиваемый блок)
- 🎭 **Персоны** — переключаемые пресеты поведения, применяются мгновенно без перезапуска
- ✍️ **Редактор личности** — дополнительные инструкции поверх системного промпта (для каждого языка)
- 🧠 **Долговременная память** — ChromaDB: общие факты о вас и заметки отдельных персон
- 👤 **Аватары** — эмодзи или своя картинка для вас и для ассистента
- 📎 **Прикрепление файлов** — поддержка TXT, PDF, DOCX, **изображений (PNG, JPG, WebP, GIF, BMP, TIFF)**
- 🖥️ **Desktop app** — Tauri (exe файл)
- ⚡ **Быстрый** — работает на локальных моделях через Ollama/LM Studio
- ⌨️ **Глобальные горячие клавиши** — работают вне окна приложения, меняются в Настройки → Общие
- 🎛️ **Настраиваемый UI** — изменяемая ширина боковой панели, вкладки настроек
- 🧵 **Контекст по чатам** — каждый чат имеет свою историю, не смешивается
- 📊 **Индикатор контекста** — показывает использованные токены / лимит
- 🖼️ **Vision-Language (VL) возможности** — анализ изображений, OCR, описание скриншотов
- 🖥️ **Авто-скриншот экрана** — по триггерам ("посмотри на экран", "скриншот" и др.) с автоматическим анализом
- 🌐 **Переключение языка** — английский / русский интерфейс (Общие → Язык), по умолчанию английский при первом запуске
- 🖥️ **Терминал** — встроенный просмотр логов бэкенда (панель снизу 40vh), внешняя консоль скрыта по умолчанию (переключатель в Общих)

## Требования

- Windows 10/11
- Python 3.11+
- Ollama или LM Studio (для LLM)
- GPU с 8GB+ VRAM (для OmniVoice + Whisper + VL)
- Node.js 18+ и Rust (только для сборки exe; проще всего через `install.bat` пункт 8)

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

Проще всего на Windows: запустите `install.bat` и выберите пункт [8] (полная установка). Ручные шаги ниже:

#### 1. Скачайте модели

```bash
# Whisper (STT)
python -c "from huggingface_hub import snapshot_download; snapshot_download('openai/whisper-large-v3-turbo', local_dir='models/whisper-large-v3-turbo')"

# OmniVoice (TTS)
python -c "from huggingface_hub import snapshot_download; snapshot_download('k2-fsa/OmniVoice', local_dir='models/omnivoice')"
```

#### 2. Установите зависимости

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

Приложение автоматически использует Python из `venv`, если он есть (и CLI, и Tauri backend), иначе — системный Python.

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

### Что ассистент делал

Каждый вызов инструмента за ход возвращается в интерфейс и показывается
сворачиваемым блоком **«Выполненные действия»** над ответом:

```
▾ Выполненные действия (2)
  🔧 app_open      name=notepad        → Запущено: notepad
  ⚠️ file_create   path=demo.txt       → Ошибка: [WinError 5] доступ запрещён
```

- Блок свёрнут по умолчанию, чтобы не засорять чат.
- Неудачные вызовы подсвечиваются красным с меткой ⚠️.
- Аргументы и результаты обрезаются до 200 символов — длинный вывод (например,
  base64 скриншота) в чат не попадает.

> Небольшие модели иногда отвечают кодом вместо реального вызова инструмента.
> Это ограничение модели, а не ошибка: инструмент не вызывался — блока нет.

### Персоны

Персона — это **слой поведения** поверх системного промпта: тон, стиль, роль.
Служебные правила (политика поиска, работа с инструментами, язык) она не заменяет.

- Переключение — в шапке чата (плашка 🎭) или каталог в
  **Настройки → 🎭🎭 Персоны**.
- Переключение мгновенное: новый промпт применяется уже со следующего сообщения,
  перезапуск не нужен.
- **«Без персоны»** = стандартный системный промпт.
- У каждой персоны может быть своя `temperature`; пусто = настройка модели.
- Каталог хранится в `personas.json` рядом с `apps.json` (в git не попадает),
  формат показан в `personas.json.example`.

Если `personas.json` отсутствует или повреждён, приложение пишет предупреждение
и возвращается к стандартному промпту — файл, который не удалось разобрать, не
перезаписывается.

### Слой личности (дополнительные инструкции)

**Настройки → 🎭 Личность** — два текстовых поля (русский / английский),
которые добавляются к системному промпту. Служебные правила остаются
нередактируемыми, здесь задаётся только стиль и характер.

Приоритет: активная персона → слой личности → стандартный промпт.

### Два блока промптов (RU / EN)

У персоны хранятся `prompt_ru` и `prompt_en`. Это **два разных промпта под два
языка интерфейса**, а не перевод одного на другой — заполняйте только тот
блок, который соответствует вашему языку, второй оставляйте пустым.

**Зачем:** базовый системный промпт тоже двуязычный, причём содержание в нём
различается, а не только формулировки. Русская версия учит модель триггерам
инструментов «открой блокнот» / «посмотри на экран», английская — «open notepad» /
«look at screen». Если смешать русскую базу с английской персоной, модель
получает смесь двух наборов правил, что заметно ухудшает качество на малых
моделях.

**Как выбирается:** функция `_get_personality_layer()` в `src/llm_engine.py`
читает `GENERAL_LANGUAGE` (Настройки → Общие → Язык) и применяет ровно один
блок. Второй игнорируется, пока вы не переключите язык интерфейса.

Используемый сейчас блок помечен плашкой **«используется»** — и во вкладке
«🎭🎭 Персоны», и во вкладке «✍️ Личность».

### Аватары

Нажмите кнопки 👤 / 🤖 в шапке чата, чтобы сменить свой аватар или аватар
ассистента:

- выбрать готовый эмодзи,
- загрузить свою картинку (PNG / JPG / WebP / GIF, до 5 МБ),
- удалить загруженную картинку.

Загруженные изображения кадрируются в квадрат и хранятся в 128×128 в папке
`avatars/` (в git не попадает). Выбор хранится в localStorage браузера; ссылка на
несуществующий файл автоматически заменяется эмодзи по умолчанию.

### Скоупы памяти

Память — одна коллекция ChromaDB, в метаданных есть поле `scope`:

- `user` — факты о вас, общие для всех персон;
- `<persona_id>` — заметки, относящиеся только к одной персоне.

При активной персоне ассистент ищет по `["user", <persona_id>]`, без персоны —
по всем записям. Извлечённые факты о вас всегда пишутся в `user`, поэтому смена
персоны их не теряет.

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

## Пробуждающая фраза (wake-word)

Произнесите фразу — и ассистент проснётся, без нажатия клавиш. Фраза любая,
какую вы напишете в **Настройки → Общие → Пробуждающая фраза**, например просто
имя ассистента. Регистр и знаки препинания не важны.

**Как работает**

```
микрофон (открыт, пока включено)
  -> Silero VAD          определяет, говорит ли кто-нибудь
  -> Whisper tiny        распознаёт, только пока идёт речь
  -> сверка с фразой     нечёткое сравнение с вашей фразой
  -> приложение запускает обычный голосовой ввод
```

Замеренная нагрузка на среднем CPU: **~4% одного ядра в простое**, **~19% пока
кто-то говорит** (и полный ноль в тишине — VAD не даёт запускать распознавание).
Именно VAD делает постоянное прослушивание affordable.

**Какая модель используется.** Собственная маленькая (`whisper-tiny` или `base`
в `./models/`), а не `large-v3-turbo` для команд — распознавание команд
полностью не затронуто. Язык декодирования определяется по письму вашей фразы,
поэтому русская фраза не распознаётся в английском режиме.

**Приватность.** Пока включено, микрофон остаётся открытым — Windows покажет
индикатор записи. Звук распознаётся на лету и отбрасывается, на диск ничего не
пишется. По умолчанию **выключено** и включается только вручную.

**Если не запустилось** — причина показана прямо в настройках (обычно нет
модели). Один раз скачать:

```bash
python tests/fetch_whisper_model.py tiny
```

Отсутствие модели, аудио-бэкенда или занятый микрофон не ломают запуск
приложения — пробуждающая фраза просто остаётся выключенной.

## Голосовой ввод (STT)

Whisper транскрибирует только на русском языке.

### Выбор модели

Задайте `STT_MODEL` в `.env`: алиас, Hugging Face `owner/repo` или путь к папке. Недостающие модели скачиваются при первом использовании в `models/`.

| Алиас | Модель | VRAM (примерно) |
|---|---|---|
| `tiny` | `openai/whisper-tiny` | ~1 ГБ |
| `base` | `openai/whisper-base` | ~1 ГБ |
| `small` | `openai/whisper-small` | ~2 ГБ |
| `medium` | `openai/whisper-medium` | ~5 ГБ |
| `large` | `openai/whisper-large-v3` | ~10 ГБ |
| `large-v3-turbo` (по умолчанию) | `openai/whisper-large-v3-turbo` | ~4 ГБ |

### Горячие клавиши

| Действие | Клавиша (по умолчанию) |
|----------|---------|
| Голосовой ввод | `Ctrl+Shift+V` или `Ctrl+Num0` |
| Live-режим | `Ctrl+Shift+L` |
| Остановка записи | Та же клавиша повторно или 2 сек тишины |

После остановки — 1 секунда паузы, затем текст отправляется AI.

### Как изменить горячие клавиши

Задайте в `.env` (применяется при перезапуске приложения, формат `Ctrl+Shift+V`, `Alt+F9`, `F12`, ...):

```env
HOTKEY_VOICE=Ctrl+Shift+V
HOTKEY_VOICE_NUM=Ctrl+Num0
HOTKEY_LIVE=Ctrl+Shift+L
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

# === Личность (доп. инструкции к системному промпту) ===
# Меняются в Настройки -> Личность; переносы строк сохраняются как \n
PERSONALITY_RU=
PERSONALITY_EN=

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
TTS_DEBUG_SAVE=false       # сохранять отладочные WAV в debug_tts/

# === STT ===
STT_MODEL=large-v3-turbo   # tiny / base / small / medium / large / large-v3-turbo, 'owner/repo' или путь к папке

# === Горячие клавиши (глобальные, применяются при перезапуске) ===
HOTKEY_VOICE=Ctrl+Shift+V
HOTKEY_VOICE_NUM=Ctrl+Num0
HOTKEY_LIVE=Ctrl+Shift+L

# === Прочее ===
LOG_LEVEL=INFO
```

> `STT_MODEL` и `HOTKEY_*` меняются прямо в приложении (Настройки → 🎙 Голос и
> Настройки → Общие) и применяются после перезапуска. `PERSONALITY_*` применяются
> сразу, перезапуск не нужен.

## API Endpoints

| Метод | Эндпоинт | Описание |
|-------|----------|----------|
| GET | `/api/status` | Статус приложения |
| POST | `/api/chat` | Отправить сообщение (возвращает `used_context_tokens`, `max_context_tokens`, `actions`, поддерживает `images` массив) |
| POST | `/api/stt` | Распознать голос |
| POST | `/api/upload` | Загрузить файл (документ или изображение) |
| GET | `/api/chats` | Список чатов |
| GET | `/api/config` | Текущая конфигурация |
| PUT | `/api/config` | Обновить конфигурацию |
| GET | `/api/personas` | Каталог персон + активная |
| PUT | `/api/personas` | Заменить каталог персон |
| POST | `/api/personas/activate` | Переключить персону на лету (`{"id": "editor"}`, `{"id": null}` — без персоны) |
| GET | `/api/avatars` | Список загруженных аватаров |
| POST | `/api/avatars` | Загрузить аватар (multipart `file`, ресайз до 128×128 PNG) |
| GET | `/api/avatars/{name}` | Отдать картинку аватара |
| DELETE | `/api/avatars/{name}` | Удалить аватар |
| POST | `/api/tts/toggle` | Включить/выключить TTS |
| POST | `/api/tts/config` | Настроить голос |
| POST | `/api/tts/speak` | Озвучить текст |

## Структура проекта

```
local_assistant/
├── .env                    # Конфигурация
├── apps.json               # Конфиг приложений (игнорируется git'ом)
├── apps.json.example       # Шаблон apps.json
├── personas.json           # Каталог персон (игнорируется git'ом)
├── personas.json.example   # Шаблон personas.json
├── avatars/                # Загруженные аватары (игнорируется git'ом)
├── config.py               # Python конфиг
├── requirements.txt        # Зависимости Python
├── requirements-dev.txt    # Зависимости для тестов (pytest)
├── pytest.ini              # Конфигурация тестов
├── tests/                  # Автотесты
├── README.md               # Этот файл
├── backend/
│   ├── main.py             # FastAPI backend
│   ├── api.py              # API модели
│   ├── database.py         # SQLite база чатов
│   └── background_tasks.py # Фоновые задачи (Ollama keep-alive)
├── src/
│   ├── i18n.py             # Backend i18n
│   ├── main.py             # Assistant логика
│   ├── llm_engine.py       # LLM + Tool Calling
│   ├── personas.py         # Хранилище персон
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
│   │   ├── avatars.js       # Аватары пользователя и ассистента
│   │   ├── personas.js      # Переключатель и редактор персон
│   │   ├── i18n.js          # Frontend i18n
│   │   ├── locales/en.json  # English translations
│   │   ├── locales/ru.json  # Russian translations
│   │   └── style.css        # Стили
│   ├── src-tauri/
│   │   ├── src/lib.rs      # Горячие клавиши
│   │   └── target/release/
│   │       └── llm-assistant-tauri.exe  # Собранное приложение
│   ├── package.json
│   └── vite.config.ts
├── models/                  # Локальные модели
│   ├── omnivoice/           # TTS модель
│   └── whisper-large-v3-turbo/  # STT модель
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

## Тесты

```bash
pip install -r requirements-dev.txt
python -m pytest -q
```

Тестам не нужны GPU, LLM-сервер, STT или TTS — всё тяжёлое мокается или
подменяется на `tmp_path`. Покрыты: проверка импортов, сборка промпта
(база + личность + персона), хранилище персон (включая битые и отсутствующие
файлы), эндпоинты аватаров (включая path traversal), скоупы памяти, round-trip
конфига и payload выполненных действий.

Запускайте после правок конфига, промптов, персон или логики памяти — тесты
работают около секунды и ловят регрессии, которые в UI не видны.

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

### «Ассистент не инициализирован» (503)
1. **Убейте зависшие процессы Python** — старый backend может держать порт 8000 (`taskkill /F /IM python.exe`), затем перезапустите приложение
2. Дождитесь старта backend (~10-60 сек при первом запуске, грузится embedding-модель)

### Модель TTS не загружается
1. **Прочитайте текст ошибки** — приложение показывает причину из backend в алерте
2. **Первая загрузка занимает ~минуту** (OmniVoice + кэш Whisper), не кликайте дважды
3. **Проверьте VRAM** — полный стек (LLM + Whisper + OmniVoice) требует 7-10 ГБ

### Не работает распознавание голоса (STT 422)
1. **Говорите сразу после нажатия кнопки**, громче и дольше секунды
2. Пустые/тихие записи отклоняются — проверьте микрофон
3. Медленное распознавание на CPU означает torch без CUDA — переустановите: `venv\Scripts\python -m pip install torch --index-url https://download.pytorch.org/whl/cu121`

## Лицензия

MIT
