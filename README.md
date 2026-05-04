# Local AI Assistant

Локальный AI-ассистент с голосовым вводом/выводом для Windows.

## Особенности

- 🎙️ **Голосовой ввод (STT)** - локальный Whisper без интернета
- 🔊 **Голосовой вывод (TTS)** - OmniVoice синтез и клонирование голоса
- 🖥️ **Desktop app** - Tauri (exe файл)
- 🧠 **Долговременная память** - ChromaDB
- ⚡ **Быстрый** - работает на локальных моделях через Ollama
- ⌨️ **Глобальные горячие клавиши** - работают вне окна приложения

## Требования

- Windows 10/11
- Python 3.11+
- Ollama (для LLM)
- GPU с 8GB+ VRAM (для OmniVoice + Whisper)

## Быстрый старт

### 1. Установка Ollama

Скачайте с https://ollama.com и установите. Затем:
```bash
ollama pull llama3.2:3b
```

### 2. Скачайте exe

- **Installer:** `llm-assistant-tauri/src-tauri/target/release/bundle/nsis/Local AI Assistant_1.0.0_x64-setup.exe`
- **Portable:** `llm-assistant-tauri/src-tauri/target/release/llm-assistant-tauri.exe`

### 3. Запуск

Запустите exe - приложение само запустит backend и откроет окно.

## Где скачать готовые модели и exe

### Вариант 1: GitHub Releases (скоро)

Скачайте готовые сборки из https://github.com/DarlingCat02/llm-assistant/releases

### Вариант 2: Сборка из исходников

#### 1. Скачайте модели

```bash
# Whisper (STT) - скачайте и распакуйте в:
# llm-assistant-tauri/src-tauri/target/release/openai_whisper-large-v3-turbo
# https://huggingface.co/openai/whisper-large-v3-turbo

# OmniVoice (TTS) - скачайте и распакуйте в:
# llm-assistant-tauri/src-tauri/target/release/OmniVoice
# https://huggingface.co/k2-fsa/OmniVoice
```

#### 2. Соберите Tauri app

```bash
cd llm-assistant-tauri
npm install
npm run tauri build
```

exe появится в: `llm-assistant-tauri/src-tauri/target/release/`

## Настройка модели LLM

Файл: `.env` (строка 5)
```
LLM_MODEL=llama3.2:3b
```

Доступные модели:
```bash
ollama list
ollama pull qwen2.5:1.5b
```

## Голосовой ввод (STT)

### Горячие клавиши

| Действие | Клавиша |
|----------|---------|
| Голосовой ввод | `Ctrl+Num0` |
| Остановка записи | `Ctrl+Num0` (повторно) |

После остановки - 1 секунда паузы, затем текст отправляется AI.

### Как изменить горячие клавиши

Файл: `llm-assistant-tauri/src-tauri/src/lib.rs`
```rust
let voice_shortcut = Shortcut::new(Some(Modifiers::CONTROL), Code::Numpad0);
```

После изменения: `cd llm-assistant-tauri && npm run tauri build`

## Голосовой вывод (TTS)

### OmniVoice

Используется [OmniVoice](https://github.com/k2-fsa/OmniVoice) для синтеза и клонирования голоса.

### Режимы

1. **Синтез (Synthesis)** - генерация голоса по текстовому описанию
2. **Клонирование (Clone)** - копирование голоса из референсного аудио

### Настройка голоса в UI

1. Включите TTS переключателем
2. Выберите режим: Synthesis или Clone
3. Для Clone - выберите аудио файл из папки `voices/`

### Параметры TTS

```python
num_step=32        # Шаги диффузии (меньше = быстрее)
guidance_scale=2.0  # Сила следования инструкции
seed=468556206     # Фиксированный сид для стабильности (режим синтеза)
```

### Голоса для клонирования

Добавьте аудио файлы в папку `voices/`:
- Формат: MP3, WAV
- Рекомендуемая длительность: 3-10 секунд
- Язык: тот же, что планируете использовать для синтеза

## Локальные модели

### Whisper (STT)

Модель должна быть скачана в:
```
llm-assistant-tauri/src-tauri/target/release/openai_whisper-large-v3-turbo
```

### OmniVoice (TTS)

Модель должна быть скачана в:
```
llm-assistant-tauri/src-tauri/target/release/OmniVoice
```

Скачать можно через HuggingFace:
- Whisper: https://huggingface.co/openai/whisper-large-v3-turbo
- OmniVoice: https://huggingface.co/k2-fsa/OmniVoice

## Конфигурация (.env)

```env
# LLM
LLM_PROVIDER=ollama
LLM_MODEL=llama3.2:3b
LLM_HOST=http://localhost:11434
LLM_NUM_CTX=4096
LLM_TEMPERATURE=0.7

# ChromaDB
CHROMA_PERSIST_DIR=./storage/chroma

# Память
MEMORY_MAX_CONTEXT=20
MEMORY_SEARCH_RESULTS=3

# TTS
TTS_ENABLED=false

# Прочее
LOG_LEVEL=INFO
```

## API Endpoints

| Метод | Эндпоинт | Описание |
|-------|----------|----------|
| GET | `/api/status` | Статус приложения |
| POST | `/api/chat` | Отправить сообщение |
| POST | `/api/stt` | Распознать голос |
| GET | `/api/chats` | Список чатов |
| POST | `/api/tts/toggle` | Включить/выключить TTS |
| POST | `/api/tts/config` | Настроить голос |
| POST | `/api/tts/speak` | Озвучить текст |

## Структура проекта

```
local_assistant/
├── .env                 # Конфигурация
├── config.py            # Python конфиг
├── README.md            # Этот файл
├── backend/
│   ├── main.py          # FastAPI backend
│   └── requirements.txt
├── src/
│   ├── main.py          # Assistant логика
│   ├── llm_engine.py    # Ollama/LM Studio/OpenRouter
│   ├── stt_engine.py    # Whisper STT
│   ├── tts_engine.py    # OmniVoice TTS
│   └── memory_manager.py # ChromaDB память
├── llm-assistant-tauri/ # Tauri desktop app
│   ├── src-tauri/
│   │   ├── src/lib.rs   # Глобальные горячие клавиши
│   │   └── target/release/
│   │       ├── OmniVoice/           # TTS модель
│   │       └── openai_whisper-*/    # STT модель
│   └── src/
│       ├── app.js        # Voice recording + VAD
│       ├── index.html    # UI
│       └── style.css
├── storage/             # ChromaDB данные
└── voices/              # Голоса для клонирования
```

## Оптимизация скорости

1. **LLM** - используйте легкие модели (1.5-3B параметров)
2. **TTS** - уменьшите `num_step` до 16-32
3. **Кеширование** - при первом клоне транскрипция кешируется

## Устранение проблем

### TTS не работает

1. Проверьте что FFmpeg доступен: `F:\ffmpeg\bin` в PATH
2. Проверьте наличие моделей в папках

### Модель не загружается

1. Проверьте Ollama: `ollama list`
2. Проверьте .env: `LLM_MODEL=llama3.2:3b`

### Голос не клонируется

Попробуйте режим Synthesis вместо Clone.

## Лицензия

MIT