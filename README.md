# Local AI Assistant

Локальный AI-ассистент с голосовым вводом/выводом и поиском в интернете для Windows.

## Особенности

- 🎙️ **Голосовой ввод (STT)** - локальный Whisper без интернета
- 🔊 **Голосовой вывод (TTS)** - OmniVoice синтез и клонирование голоса
- 🌐 **Поиск в интернете** - DuckDuckGo (бесплатно, без API ключей)
- 🖥️ **Desktop app** - Tauri (exe файл)
- 🧠 **Долговременная память** - ChromaDB
- ⚡ **Быстрый** - работает на локальных моделях через Ollama/LM Studio
- ⌨️ **Глобальные горячие клавиши** - работают вне окна приложения
- 🎛️ **Настраиваемый UI** - изменяемая ширина боковой панели

## Требования

- Windows 10/11
- Python 3.11+
- Ollama или LM Studio (для LLM)
- GPU с 8GB+ VRAM (для OmniVoice + Whisper)

## Быстрый старт

### 1. Установка LLM провайдера

**Вариант A: Ollama**
```bash
# Скачайте с https://ollama.com и установите
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

Запустите exe - приложение само запустит backend и откроет окно.

## Где скачать готовые модели и exe

### Вариант 1: GitHub Releases

Скачайте готовые сборки из https://github.com/DarlingCat02/llm-assistant/releases

### Вариант 2: Сборка из исходников

#### 1. Скачайте модели

```bash
# Whisper (STT) - скачайте и распакуйте в:
# llm-assistant-tauri/src-tauri/target/release/openai_whisper-large-v3-turbo
python -c "from huggingface_hub import snapshot_download; snapshot_download('openai/whisper-large-v3-turbo', local_dir='llm-assistant-tauri/src-tauri/target/release/openai_whisper-large-v3-turbo')"

# OmniVoice (TTS) - скачайте и распакуйте в:
# llm-assistant-tauri/src-tauri/target/release/OmniVoice
python -c "from huggingface_hub import snapshot_download; snapshot_download('k2-fsa/OmniVoice', local_dir='llm-assistant-tauri/src-tauri/target/release/OmniVoice')"
```

#### 2. Установите зависимости

```bash
pip install -r requirements.txt
pip install ddgs  # Для поиска в интернете
```

#### 3. Соберите Tauri app

```bash
cd llm-assistant-tauri
npm install
npm run tauri build
```

exe появится в: `llm-assistant-tauri/src-tauri/target/release/`

## Поиск в интернете

### DuckDuckGo (бесплатно)

Поиск работает через [DuckDuckGo](https://duckduckgo.com) без API ключей.

**Как использовать:**
1. Включите переключатель "🌐 Поиск" в интерфейсе
2. Задайте вопрос - ассистент автоматически найдёт актуальную информацию
3. Результаты поиска используются для формирования ответа

**Примеры вопросов:**
- "Какая сейчас погода в Москве?"
- "Курс доллара к рублю"
- "Какие модели популярны на Hugging Face?"
- "Текущий президент США"

**Особенности:**
- Поиск выполняется автоматически при включённом переключателе
- 7 результатов поиска для каждого запроса
- Fallback на прямой HTTP-запрос к DuckDuckGo HTML

## Голосовой ввод (STT)

### Горячие клавиши

| Действие | Клавиша |
|----------|---------|
| Голосовой ввод | `Ctrl+Num0` |
| Остановка записи | `Ctrl+Num0` (повторно) или 2 сек тишины |

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
2. Выберите режим: Синтез или Клон
3. Для Clone - выберите аудио файл из папки `voices/`

### Голоса для клонирования

Добавьте аудио файлы в папку `voices/`:
- Формат: MP3, WAV
- Рекомендуемая длительность: 3-10 секунд
- Язык: тот же, что планируете использовать для синтеза

## Конфигурация (.env)

```env
# === LLM ===
LLM_PROVIDER=ollama          # ollama / lm_studio / openrouter
LLM_MODEL=llama3.2:3b        # Название модели
LLM_HOST=http://localhost:11434
LLM_NUM_CTX=4096
LLM_TEMPERATURE=0.7

# === Ollama (устаревшее) ===
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=llama3.2:3b

# === ChromaDB ===
CHROMA_PERSIST_DIR=./storage/chroma
CHROMA_COLLECTION_NAME=assistant_memory

# === Память ===
MEMORY_MAX_CONTEXT=20
MEMORY_SEARCH_RESULTS=3
MEMORY_SIMILARITY_THRESHOLD=0.3

# === TTS ===
TTS_ENABLED=false
TTS_MODEL=silero_v3

# === Web Interface ===
WEB_HOST=127.0.0.1
WEB_PORT=8000

# === Прочее ===
LOG_LEVEL=INFO
```

## API Endpoints

| Метод | Эндпоинт | Описание |
|-------|----------|----------|
| GET | `/api/status` | Статус приложения |
| POST | `/api/chat` | Отправить сообщение |
| POST | `/api/stt` | Распознать голос |
| GET | `/api/chats` | Список чатов |
| GET | `/api/chats/{id}/messages` | Сообщения чата |
| POST | `/api/tts/toggle` | Включить/выключить TTS |
| GET | `/api/tts/status` | Статус TTS |
| POST | `/api/tts/config` | Настроить голос |
| GET | `/api/tts/voices` | Список голосов |
| POST | `/api/tts/speak` | Озвучить текст |

## Структура проекта

```
local_assistant/
├── .env                 # Конфигурация
├── config.py            # Python конфиг
├── requirements.txt     # Зависимости Python
├── README.md            # Этот файл
├── backend/
│   ├── main.py          # FastAPI backend
│   ├── api.py           # API модели
│   └── database.py      # SQLite база чатов
├── src/
│   ├── main.py          # Assistant логика
│   ├── llm_engine.py    # Ollama/LM Studio/OpenRouter + Tool Calling
│   ├── stt_engine.py    # Whisper STT
│   ├── tts_engine.py    # OmniVoice TTS
│   ├── web_search.py    # DuckDuckGo поиск
│   └── memory_manager.py # ChromaDB память
├── llm-assistant-tauri/ # Tauri desktop app
│   ├── src-tauri/
│   │   ├── src/lib.rs   # Глобальные горячие клавиши
│   │   └── target/release/
│   │       ├── OmniVoice/           # TTS модель
│   │       └── openai_whisper-*/    # STT модель
│   └── src/
│       ├── app.js        # Voice recording + VAD + Search UI
│       ├── index.html    # UI
│       └── style.css
├── storage/             # ChromaDB данные
└── voices/              # Голоса для клонирования
```

## Оптимизация скорости

1. **LLM** - используйте легкие модели (1.5-4B параметров)
2. **TTS** - уменьшите `num_step` до 16-32
3. **Кеширование** - при первом клоне транскрипция кешируется
4. **Поиск** - выполняется автоматически при включённом переключателе

## Устранение проблем

### TTS не работает

1. Проверьте что FFmpeg доступен в PATH
2. Проверьте наличие моделей в папках

### Модель не загружается

1. Проверьте Ollama: `ollama list` или LM Studio
2. Проверьте .env: `LLM_MODEL=...`

### Поиск не работает

1. Проверьте подключение к интернету
2. Попробуйте другой запрос

### Горячие клавиши не работают

1. Проверьте что NumLock включён
2. Убедитесь что приложение в фокусе

## Лицензия

MIT
