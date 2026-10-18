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
- 🗣️ **Wake word** — a spoken phrase starts voice input, no keyboard needed (off by default)
- 🎚️ **Input modes** — hotkey or an always-open background listener, one Whisper instance either way
- 📉 **VRAM readout** — who holds the video memory right now, and a button to hand it back
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
- Node.js 20+ and Rust (only to build the exe; easiest via `install.bat` option 8)
- FFmpeg (only for voice input — see below)

**PyTorch decides whether the GPU is used at all.** Left to PyPI it installs as
the CPU build — measured on a zero-start install: `torch 2.14.1+cpu`,
`cuda.is_available() = False`, and speech recognition of a 2.5-second clip took
**41 s** where the CUDA build takes **0.2 s**. `install.bat` therefore installs
PyTorch *first*, from an explicit index: CUDA if `nvidia-smi` is there, CPU
otherwise, falling back from cu128 to cu121 if the driver is too old. It
uninstalls any existing `torch`/`torchaudio` first — `pip` considers *any*
installed torch a satisfied requirement, CPU build included, and would
otherwise download nothing at all. Set `TORCH_BUILD=cpu` (or `=cuda`) in `.env`
to decide yourself. Both `torch` and `torchaudio` come from the same index on
purpose — mismatched versions break OmniVoice.

**Node.js 20, not 18.** The Tauri CLI refuses to run on older Node, and it
fails with an error that does not mention Node at all. `install.bat` checks the
version before downloading anything.

**Rust must be able to link.** `rustup` on its own installs the compiler but not
the C++ toolset, so a build on a fresh Windows dies after a while with
`link.exe not found`. Install
[Visual Studio Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/)
(the "Desktop development with C++" workload) alongside Rust. `install.bat`
option 1 proves it by compiling and linking a one-line program, and option 8
refuses to start a 60-minute build that would fail at the end.

**FFmpeg** is needed for voice input: the browser records webm/opus, and that
is what ffmpeg decodes. Either put it on PATH, or run `install.bat` option 7,
which drops `ffmpeg/ffmpeg.exe` next to the project where the app looks for it.
Without it, voice input fails with `422`.

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
Addendum: VRAM did become manageable later on, without giving up the models — one shared Whisper instead of two copies, unloading that actually returns the memory, and a readout that shows who holds what. See *VRAM: what is loaded, and how to give it back*.

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

**If the installer does not work on your machine**, there is a second route that
needs nothing but Git: clone the repository and run `install.bat` there. It
performs the same steps in the same order, and it is the route this project was
tested on — a clean folder, no `.env`, no `venv`, no models:

```bash
git clone https://github.com/DarlingCat02/llm-assistant.git
cd llm-assistant
install.bat     # choose [8] Full installation
run.bat
```

This route builds the exe itself, so it needs Python 3.11+, Node.js 20+ and Rust
on the machine — the installer bundles Python and ffmpeg instead. It also prints
each step and stops with an error, so if something fails you get told what,
which is worth having when the installer failed silently.

### Option 2: Build from source

Easiest on Windows: run `install.bat` and choose option [8] (full
installation). It does the steps below in the right order — dependencies, then
`.env`, then the models, then the build — and checks Node, Rust and the linker
first. Manual steps below, **all of them from the project root**: the paths are
relative to it, and a model downloaded from elsewhere ends up in a folder
nothing reads.

#### 1. Install dependencies

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

The app uses the `venv` Python automatically when it exists (both CLI and Tauri
backend), falling back to system Python.

#### 2. Create .env

```bash
copy .env.example .env
```

Then open `.env` and set at least `LLM_PROVIDER`, `LLM_MODEL` and `LLM_HOST` for
your LLM server. Everything else has a working default.

#### 3. Download models

Needs `huggingface_hub`, so it comes **after** step 1, not before:

```bash
# Whisper (STT)
venv\Scripts\python -c "from huggingface_hub import snapshot_download; snapshot_download('openai/whisper-large-v3-turbo', local_dir='models/whisper-large-v3-turbo')"

# OmniVoice (TTS)
venv\Scripts\python -c "from huggingface_hub import snapshot_download; snapshot_download('k2-fsa/OmniVoice', local_dir='models/omnivoice')"
```

Whisper for the wake word is not a separate download: the wake listener borrows
the same model as speech recognition.

There is one more model the app needs and you did not download: the **memory
embeddings** (`all-MiniLM-L6-v2`, ~90 MB). Without it there is no long-term
memory, and every request comes back 503 — so it is downloaded automatically on
first start into `models/all-MiniLM-L6-v2`, and from then on the app runs fully
offline. `install.bat` option 8 fetches it as well, if you would rather have it
before the first launch. To do it by hand:

```bash
venv\Scripts\python tests\fetch_whisper_model.py --embedding
```

Set `HF_HUB_OFFLINE=1` if you want a missing model to be an error instead of a
download — the app will then say which folder it expected.

#### 4. Build Tauri app

```bash
cd llm-assistant-tauri
npm install
npm run tauri build
```

### Where the app has to live

Run the exe **from inside the project folder**:

```
llm-assistant-tauri\src-tauri\target\release\llm-assistant-tauri.exe
```

This is not a formality. The backend is Python and it is *not* bundled: the
app looks for the project (the `backend` package, `.env`, `models/`, `storage/`)
by walking up from the exe until it finds it. Copy the exe somewhere else —
a desktop shortcut to `C:\Users\...\Desktop\app.exe` included — and there is
nothing to find, so the backend cannot start.

For the same reason **do not install the app from the generated installer**.
The build produces an NSIS package, but the installed copy lives under
`Program Files` or `%LOCALAPPDATA%`, outside the project, and cannot work.
The installer exists as an artefact, not as a supported way to run the app.

To put the app on the desktop, make a **shortcut to the exe inside the
project**, not a copy of the exe.

### What the app starts for itself

- **The backend port is chosen at launch**, not fixed at 8000 — if something
  else holds that port the app still starts. The frontend asks the launcher
  which port it got.
- **`logs/backend.log`** in the project folder holds the backend's output and
  the launcher's own messages. If the project folder cannot be written to
  (Program Files), the log goes to `%LOCALAPPDATA%\local_assistant\logs\`
  instead. It is truncated at every launch.

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

## Input modes: hotkey or background

The slider above the chat picks **how voice input is started**:

- **Hotkey** — nothing listens. Recognition loads when you press the key.
- **Background** — the microphone stays open and the first sound starts
  recognition by itself (this is the wake-word listener, at full strength).

The two are exclusive on purpose: only **one** Whisper instance is ever resident.
The wake word borrows the same model the STT uses rather than loading a second
copy — switching modes costs 0.0-0.1 s and no extra memory, and switching back
and forth does not accumulate anything. In the API this is
`GET/POST /api/input-mode`.

If the background listener cannot start (no model, no audio backend, a busy
microphone), the mode stays on hotkey and the reason is shown in Settings —
the UI never claims the microphone is open when it is not.

## Voice output (TTS)

### Modes

1. **Synthesis** — voice generation from text description
2. **Cloning** — copying voice from reference audio

### Voices for cloning

Add audio files to `voices/` folder:
- Format: MP3, WAV
- Recommended duration: 3-10 seconds

OmniVoice needs a transcript of the sample, which means recognising it — an
expensive step that used to run again on every clone. It is now computed **once
per file** and kept in `storage/tts_voices.json`, keyed by the sample's
name, size and modification time. Editing an entry by hand is respected and
never overwritten; replacing or re-recording the sample re-transcribes it. The
stored text is shown in **Settings → Voice**, next to the "unload models"
button.

## VRAM: what is loaded, and how to give it back

**Settings → Voice** shows a live readout of the video memory: total, used,
what the assistant itself holds, what other programs hold (LM Studio is usually
the biggest neighbour, and without it the assistant's own number looks like the
whole card), and what is free. Read through `nvidia-smi`, with torch as a
fallback.

**Unload models** frees the speech and recognition models on demand and reports
how much came back. It refuses rather than damages: background input mode holds
the very same recognition model, so releasing it while listening is refused with
an explanation instead of silently breaking the microphone.

Measured on a 12 GB card, TTS synthesis and cloning both settle at ~1.96 GB
(they used to hold ~3.5 GB, because each mode kept a second copy of Whisper).
Turning TTS off now hands nearly all of it back — 27 MB of ours left, ~70 MB
reserved by the CUDA context. That last part never comes back and is not a leak:
it is the context plus cuBLAS buffers.

The first load of a model is dominated by disk, not by code. Reading OmniVoice
(3.1 GB) cold at ~76 MB/s takes ~41 s; with the file cache warm it is ~2 s. If
the assistant seems to hang for 40 seconds the first time you enable voice
output, that is the disk — the log shows the load starting immediately.

There is no idle timer that unloads models behind your back on purpose: measured
on this machine, handing the cache back costs nothing but makes the next load
read from disk again, so it is done on request instead.

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
| GET | `/api/audio-inputs` | Available microphones |
| GET | `/api/wake-word` | Wake phrase + listener state |
| PUT | `/api/wake-word` | Set the wake phrase |
| GET | `/api/input-mode` | Current input mode (`hotkey` / `background`) + listener state |
| POST | `/api/input-mode` | Switch mode (`{"mode": "hotkey"\|"background"}`) |
| GET | `/api/gpu-memory` | VRAM breakdown, what is loaded, freed context |
| POST | `/api/gpu-memory/release` | Hand cached CUDA blocks back to the driver |
| POST | `/api/models/release` | Unload models (`{"what": "all"\|"stt"\|"tts"}`), refuses if in use |
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
| GET | `/api/tts/status` | TTS state |
| POST | `/api/tts/config` | Configure voice |
| GET | `/api/tts/voices` / `/api/tts/config` | Voice list / current voice |
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
├── logs/                   # Backend log written by the desktop app
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
│   ├── wake_word.py        # Wake-word listener (VAD + borrowed Whisper)
│   ├── tts_voice_cache.py  # Saved transcriptions of voice samples
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
├── models/                  # Local models (see models/README.txt)
│   ├── omnivoice/           # TTS model
│   ├── whisper-large-v3-turbo/  # STT model
│   └── all-MiniLM-L6-v2/    # memory embeddings
├── storage/                 # ChromaDB data + tts_voices.json (git-ignored)
└── voices/                  # Voices for cloning (git-ignored)
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

### Hardware checks (`tests/check_*.py`)

These are **not** part of pytest: each one needs a real backend on port 8000 and
touches hardware, so they are run by hand, one at a time, when the thing they
guard has been touched. Each states in its first lines what it asserts and which
defect it came from.

```bash
# start the app first, then:
python tests/check_input_modes.py        # one Whisper only, no drift across switches
python tests/check_memory_release.py     # unloading gives the memory back
python tests/check_vram_creep.py         # no growth across load/unload cycles
python tests/check_voice_transcript_cache.py voices\my_sample.mp3  # transcribed once, edits kept
python tests/check_stt_noise.py          # the terminal stays readable
python tests/check_wake_real.py          # wake phrase on a real recording
```

Groups: `check_wake_*` / `check_mic_levels` for the wake listener (some need a
microphone), `check_tts_*` / `check_mode_*` / `check_clone_after_drop` for
speech and mode switching, `check_input_modes` / `check_memory_release` /
`check_vram_creep` for memory, `check_ws_disconnect` / `check_tool_*` for the
backend. They are measurements first and tests second: several print numbers and
assert a threshold, so a failure is as often "the machine is different" as
"the code is wrong". None of them touch your data: where a check has to change
something to prove a point (`check_voice_transcript_cache` empties the store to
prove the first run really transcribes), it takes a copy first and puts
everything back, including if it is interrupted.

`python tests/fetch_whisper_model.py tiny` downloads the small model the wake
word needs, when it is missing.

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
2. **First load is disk-bound** — OmniVoice is 3.1 GB and reading it cold takes ~40 s at ~76 MB/s, do not click twice
3. **Check VRAM** — full stack (LLM + Whisper + OmniVoice) needs 7-10 GB

### Voice recognition fails (STT 422)
1. **Speak right after pressing the button**, louder and longer than a second
2. Empty/silent recordings are rejected — check the microphone
3. **Is ffmpeg there?** — the browser records webm/opus and only ffmpeg decodes it. `install.bat` option 7, or put it on PATH
4. Slow recognition on CPU means torch is the CPU build — check with `venv\Scripts\python -c "import torch; print(torch.cuda.is_available())"`, and reinstall with `venv\Scripts\python -m pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu128` (cu121 for older drivers)

### Build fails with `link.exe not found`
1. Rust is installed, the C++ toolset is not — install [Visual Studio Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/) with the "Desktop development with C++" workload
2. `install.bat` option 1 runs the same test in a second and says so before you spend an hour on a doomed build
3. Check the Node version too (needs 20+): `node --version`

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
- 🗣️ **Пробуждающая фраза** — голосом, без клавиатуры (по умолчанию выключено)
- 🎚️ **Режимы ввода** — по горячей клавише или постоянно открытый микрофон, модель распознавания в обоих случаях одна
- 📉 **Показатель видеопамяти** — кто сейчас занимает VRAM и кнопка «отдать обратно»
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
- Node.js 20+ и Rust (только для сборки exe; проще всего через `install.bat` пункт 8)
- FFmpeg (только для голосового ввода — см. ниже)

**От PyTorch зависит, используется ли видеокарта.** Если оставить его PyPI,
ставится CPU-сборка — проверено на чистой установке: `torch 2.14.1+cpu`,
`cuda.is_available() = False`, а распознавание клипа в 2,5 секунды заняло
**41 с**, тогда как с CUDA — **0,2 с**. Поэтому `install.bat` ставит PyTorch
**первым** и из явного индекса: CUDA, если есть `nvidia-smi`, иначе CPU, с
откатом с cu128 на cu121 для старых драйверов. Перед установкой имеющиеся
`torch` и `torchaudio` удаляются: `pip` считает *любой* установленный torch
подходящим (версия не указана), CPU-сборка не исключение — и без удаления он
не скачает вообще ничего. Решить самому можно строкой `TORCH_BUILD=cpu`
(или `=cuda`) в `.env`. И `torch`, и `torchaudio` берутся с одного индекса
намеренно — несовпадение версий ломает OmniVoice.

**Node.js 20, а не 18.** Tauri CLI отказывается работать на более старой версии,
и ошибка при этом не упоминает Node вообще. `install.bat` проверяет версию до того,
как что-либо скачает.

**Rust должен уметь линковать.** Один только `rustup` ставит компилятор, но не
набор инструментов C++, и сборка на чистой Windows падает через некоторое время
с `link.exe not found`. Поставьте вместе с Rust
[Visual Studio Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/)
(нагрузка «Разработка классических приложений на C++»). `install.bat` пункт 1
проверяет это, скомпилировав и слинковав однострочную программу, а пункт 8 не
начинает 60-минутную сборку, которая всё равно упала бы в конце.

**FFmpeg** нужен для голосового ввода: браузер пишет webm/opus, а декодирует это
ffmpeg. Либо он есть в PATH, либо выполните `install.bat` пункт 7 — он положит
`ffmpeg\ffmpeg.exe` рядом с проектом, где приложение его ищет. Без него голосовой
ввод отдаёт ошибку `422`.

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
Дополнение: позже VRAM всё же стал управляемым, без отказа от моделей — один общий Whisper вместо двух копий, выгрузка, которая действительно возвращает память, и показатель, видно кто что занимает. См. *Видеопамять: что загружено и как вернуть*. 

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

**Если установщик на вашей машине не пошёл**, есть второй путь, которому нужен
только Git: склонировать репозиторий и запустить `install.bat` прямо в нём. Он
делает те же шаги в том же порядке, и именно этот путь проверялся — чистая
папка, без `.env`, без `venv`, без моделей:

```bash
git clone https://github.com/DarlingCat02/llm-assistant.git
cd llm-assistant
install.bat     # выберите пункт [8] полная установка
run.bat
```

Этот путь собирает exe сам, поэтому на машине нужны Python 3.11+, Node.js 20+ и
Rust — установщик вместо этого несёт Python и ffmpeg с собой. И он печатает
каждый шаг и останавливается с ошибкой, то есть при неудаче вы узнаете что
именно сломалось. Это того стоит, когда установщик молча не сработал.

### Вариант 2: Сборка из исходников

Проще всего на Windows: запустите `install.bat` и выберите пункт [8] (полная
установка). Он выполняет шаги ниже в правильном порядке — зависимости, затем
`.env`, затем модели, затем сборка — и сначала проверяет Node, Rust и линкер.
Ручные шаги ниже, **все из корня проекта**: пути относительные, и модель,
скачанная откуда-то ещё, окажется в папке, которую никто не читает.

#### 1. Установите зависимости

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

Приложение автоматически использует Python из `venv`, если он есть (и CLI, и Tauri backend), иначе — системный Python.

#### 2. Создайте .env

```bash
copy .env.example .env
```

Откройте `.env` и задайте хотя бы `LLM_PROVIDER`, `LLM_MODEL` и `LLM_HOST` под
ваш LLM-сервер. Остальное работает на значениях по умолчанию.

#### 3. Скачайте модели

Нужен `huggingface_hub`, поэтому это идёт **после** шага 1, а не до него:

```bash
# Whisper (STT)
venv\Scripts\python -c "from huggingface_hub import snapshot_download; snapshot_download('openai/whisper-large-v3-turbo', local_dir='models/whisper-large-v3-turbo')"

# OmniVoice (TTS)
venv\Scripts\python -c "from huggingface_hub import snapshot_download; snapshot_download('k2-fsa/OmniVoice', local_dir='models/omnivoice')"
```

Whisper для фразы пробуждения отдельно не скачивается: слушатель берёт ту же
модель, что и распознавание речи.

Есть ещё одна модель, которая нужна приложению, но которую вы не скачивали:
**эмбеддинги для памяти** (`all-MiniLM-L6-v2`, ~90 МБ). Без них нет долговременной
памяти, и каждый запрос будет отдавать 503 — поэтому модель скачивается
автоматически при первом запуске в `models/all-MiniLM-L6-v2`, а дальше приложение
работает полностью офлайн. `install.bat` пункт 8 забирает её тоже, если хочется
иметь её до первого запуска. Вручную:

```bash
venv\Scripts\python tests\fetch_whisper_model.py --embedding
```

Переменная `HF_HUB_OFFLINE=1` превращает отсутствующую модель из загрузки в
ошибку — приложение тогда напишет, какую папку ожидало.

#### 4. Соберите Tauri app

```bash
cd llm-assistant-tauri
npm install
npm run tauri build
```

### Где должно лежать приложение

Запускайте exe **из папки проекта**:

```
llm-assistant-tauri\src-tauri\target\release\llm-assistant-tauri.exe
```

Это не формальность. Бэкенд — это Python, и он **не входит** в сборку:
приложение ищет проект (пакет `backend`, `.env`, `models/`, `storage/`),
поднимаясь вверх от exe, пока не найдёт. Скопируйте exe в другое место — даже
ярлык на рабочий стол, указывающий на `C:\Users\...\Desktop\app.exe`, — и
найти будет нечего, бэкенд не запустится.

По той же причине **не устанавливайте приложение из собранного установщика**.
Сборка делает NSIS-пакет, но установленная копия окажется в `Program Files`
или `%LOCALAPPDATA%`, вне проекта, и работать не сможет. Установщик —
артефакт сборки, а не поддерживаемый способ запуска.

Чтобы приложение было под рукой, сделайте **ярлык на exe внутри проекта**,
а не копию exe.

### Что приложение запускает само

- **Порт бэкенда выбирается при запуске**, а не жёстко равен 8000: если
  порт занят другим процессом, приложение всё равно стартует. Фронтенд
  спрашивает у лаунчера, какой порт тот получил.
- **`logs/backend.log`** в папке проекта содержит вывод бэкенда и сообщения
  самого лаунчера. Если папка проекта недоступна для записи (Program Files),
  лог пишется в `%LOCALAPPDATA%\local_assistant\logs\`. При каждом запуске
  файл очищается.

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

## Режимы ввода: горячая клавиша или фон

Ползунок над чатом выбирает, **как запускается голосовой ввод**:

- **Горячая клавиша** — микрофон не открыт, модель грузится по нажатию.
- **Фон** — микрофон остаётся открыт, первый же звук запускает
  распознавание сам (это и есть слушатель пробуждающей фразы, на полную).

Режимы исключают друг друга намеренно: одновременно в памяти живёт **один**
экземпляр Whisper. Пробуждающая фраза занимает ту же модель, что и обычное
распознавание, а не грузит вторую копию — переключение занимает 0.0-0.1 с и не
добавляет памяти, повторные переключения тоже ничего не накапливают. В API это
`GET/POST /api/input-mode`.

Если фоновый слушатель не смог запуститься (нет модели, нет аудио-бэкенда,
микрофон занят), режим остаётся на горячей клавише, а причина показывается в
настройках — интерфейс никогда не пишет, что микрофон открыт, если это не так.

## Голосовой вывод (TTS)

### Режимы

1. **Синтез** — генерация голоса по текстовому описанию
2. **Клонирование** — копирование голоса из референсного аудио

### Голоса для клонирования

Добавьте аудио файлы в папку `voices/`:
- Формат: MP3, WAV
- Рекомендуемая длительность: 3-10 секунд

OmniVoice нужен текст образца, то есть его распознавание — дорогая операция,
которая раньше повторялась при каждом клонировании. Теперь она считается
**один раз на файл** и хранится в `storage/tts_voices.json` под именем, размером
и временем изменения файла. Правка записи руками не перезаписывается, а
замена или перезапись образца приводит к новому распознаванию. Сохранённый
текст показывается в **Настройки → Голос** рядом с кнопкой выгрузки моделей.

## Видеопамять: что загружено и как вернуть

**Настройки → Голос** показывают текущее состояние видеопамяти: всего, занято,
сколько занимает сам ассистент, сколько — другие программы (обычно главный
сосед — LM Studio, без него цифра ассистента выглядит как вся карта) и сколько
свободно. Данные читаются через `nvidia-smi`, с запасным вариантом через torch.

**Кнопка «Выгрузить модели»** освобождает модели речи и распознавания и
показывает, сколько вернулось. Лучше отказать, чем навредить: фоновый режим
ввода держит ту же самую модель распознавания, поэтому выгрузка во время
слушания отклоняется с объяснением, а не ломает микрофон молча.

Замерено на карте 12 ГБ: синтез и клонирование голоса укладываются в ~1.96 ГБ
(раньше держали ~3.5 ГБ, потому что каждый режим держал вторую копию Whisper).
После выключения TTS почти вся память возвращается — остаётся 27 МБ наших и
~70 МБ, удерживаемых контекстом CUDA. Вот это последнее не возвращается и утечкой
не является: контекст плюс буферы cuBLAS.

Первую загрузку модели определяет диск, а не код. Чтение OmniVoice (3.1 ГБ) с
холодного кэша со скоростью ~76 МБ/с занимает ~41 с, с прогретым — ~2 с. Если
при первом включении голоса ассистент «висит» 40 секунд, это диск — по журналу
видно, что загрузка начинается сразу.

Таймера простоя, который выгружает модели за спиной у пользователя, здесь нет:
по замерам на этой машине возврат кэша ничего не стоит, но заставляет следующую
загрузку снова читать с диска, поэтому выгрузка делается по запросу.

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
| GET | `/api/audio-inputs` | Доступные микрофоны |
| GET | `/api/wake-word` | Фраза пробуждения и состояние слушателя |
| PUT | `/api/wake-word` | Задать фразу пробуждения |
| GET | `/api/input-mode` | Текущий режим ввода (`hotkey` / `background`) и состояние слушателя |
| POST | `/api/input-mode` | Сменить режим (`{"mode": "hotkey"\|"background"}`) |
| GET | `/api/gpu-memory` | Разбивка VRAM, что загружено, сколько освобождено |
| POST | `/api/gpu-memory/release` | Вернуть зарезервированные блоки CUDA драйверу |
| POST | `/api/models/release` | Выгрузить модели (`{"what": "all"\|"stt"\|"tts"}`), отказ при использовании |
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
| GET | `/api/tts/status` | Состояние TTS |
| POST | `/api/tts/config` | Настроить голос |
| GET | `/api/tts/voices` / `/api/tts/config` | Список голосов / текущий голос |
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
├── logs/                   # Лог бэкенда, который пишет приложение
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
│   ├── wake_word.py        # Пробуждающая фраза (VAD + общий Whisper)
│   ├── tts_voice_cache.py  # Сохранённые расшифровки образцов голоса
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
├── models/                  # Локальные модели (см. models/README.txt)
│   ├── omnivoice/           # Модель TTS
│   ├── whisper-large-v3-turbo/  # Модель STT
│   └── all-MiniLM-L6-v2/    # Эмбеддинги для памяти
├── storage/                 # ChromaDB данные + tts_voices.json (игнорируется git'ом)
└── voices/                  # Голоса для клонирования (игнорируется git'ом)
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

### Проверки на реальном железе (`tests/check_*.py`)

Они **не** входят в pytest: каждой нужен запущенный бэкенд на порту 8000 и
настоящее железо, поэтому их запускают вручную и по одной — когда затронуто то,
что они охраняют. В первых строках каждой написано, что именно она проверяет и
из какого дефекта выросла.

```bash
# сначала запустите приложение, затем:
python tests/check_input_modes.py        # модель распознавания одна, без накопления
python tests/check_memory_release.py     # выгрузка возвращает память
python tests/check_vram_creep.py         # нет роста по циклам загрузки/выгрузки
python tests/check_voice_transcript_cache.py voices\my_sample.mp3  # расшифровывается один раз, правки сохраняются
python tests/check_stt_noise.py          # терминал остаётся читаемым
python tests/check_wake_real.py          # фраза пробуждения на реальной записи
```

Группы: `check_wake_*` и `check_mic_levels` — слушатель пробуждения (части
требуют микрофон), `check_tts_*`, `check_mode_*`, `check_clone_after_drop` —
озвучка и переключение режимов, `check_input_modes`, `check_memory_release`,
`check_vram_creep` — память, `check_ws_disconnect`, `check_tool_*` — бэкенд.
Это сначала измерения, и только потом тесты: многие печатают числа и проверяют
порог, так что провал — это порой «машина другая», а не «код неверен». Ни одна из
них не трогает ваши данные: там, где проверке нужно что-то изменить, чтобы что-то
доказать (`check_voice_transcript_cache` очищает хранилище, чтобы убедиться, что
первый запуск действительно расшифровывает), она сначала делает копию и
возвращает всё на место — даже если её прервали.

`python tests/fetch_whisper_model.py tiny` скачает маленькую модель для фразы
пробуждения, если её нет.

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
2. **Первая загрузка упирается в диск** — OmniVoice это 3.1 ГБ, холодное чтение занимает ~40 с при ~76 МБ/с, не кликайте дважды
3. **Проверьте VRAM** — полный стек (LLM + Whisper + OmniVoice) требует 7-10 ГБ

### Не работает распознавание голоса (STT 422)
1. **Говорите сразу после нажатия кнопки**, громче и дольше секунды
2. Пустые/тихие записи отклоняются — проверьте микрофон
3. **Есть ли ffmpeg?** — браузер пишет webm/opus, а декодирует это только ffmpeg. `install.bat` пункт 7 или добавьте его в PATH
4. Медленное распознавание на CPU означает, что стоит CPU-сборка torch — проверьте `venv\Scripts\python -c "import torch; print(torch.cuda.is_available())"` и переустановите: `venv\Scripts\python -m pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu128` (для старых драйверов cu121)

### Сборка падает с `link.exe not found`
1. Rust установлен, а набор инструментов C++ — нет. Поставьте [Visual Studio Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/) с нагрузкой «Разработка классических приложений на C++»
2. `install.bat` пункт 1 выполняет ту же проверку за секунду и говорит об этом до часа бесполезной сборки
3. Заодно проверьте версию Node (нужен 20+): `node --version`

## Лицензия

MIT
