# Local AI Assistant

Локальный AI-ассистент с модульной архитектурой. Поддерживает **Ollama**, **LM Studio** и **OpenRouter**.

**Особенности:**
- 🖥️ Графический интерфейс (Tauri desktop app)
- 🧠 Долговременная память на ChromaDB
- 🎤 Голосовой ввод (STT) — Whisper локально
- 🔊 Голосовой вывод (TTS) — в разработке
- 🎨 Тёмная тема UI
- 🚀 Глобальные горячие клавиши (работают вне окна)

## Быстрый старт

### Запуск (Tauri Desktop)

```bash
# Запустите exe: llm-assistant-tauri\src-tauri\target\release\llm-assistant-tauri.exe
# или установите: llm-assistant-tauri\src-tauri\target\release\bundle\nsis\Local AI Assistant_1.0.0_x64-setup.exe
```

Приложение автоматически запускает Python backend и веб-интерфейс.

### Запуск из исходников

```bash
cd local_assistant

# Установка зависимостей Python
pip install -r requirements.txt
pip install -r backend/requirements.txt

# Создайте .env из .env.example и настройте модель

# Запуск веб-сервера
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

## Голосовой ввод (STT)

### Используемые модели

- **STT**: [Whisper Large V3 Turbo](https://huggingface.co/openai/whisper-large-v3-turbo)
- Модель должна быть в папке: `llm-assistant-tauri/src-tauri/target/release/openai_whisper-large-v3-turbo`

### Установка модели

```bash
# Скачайте модель с HuggingFace и распакуйте в нужную папку
# Или используйте скрипт загрузки (добавить позже)
```

### Горячие клавиши

| Действие | Клавиша |
|----------|---------|
| Голосовой ввод | `Ctrl+Num0` (цифровая клавиатура) |
| Голосовой ввод (альтернатива) | `Ctrl+Shift+V` |
| Live-режим (непрерывный чат) | `Ctrl+Shift+L` |

### Как изменить горячие клавиши

Файл: `llm-assistant-tauri/src-tauri/src/lib.rs`

```rust
fn setup_global_shortcuts(app: &AppHandle) {
    use tauri_plugin_global_shortcut::{Code, GlobalShortcutExt, Modifiers, Shortcut};
    
    // Измените здесь
    let voice_shortcut = Shortcut::new(Some(Modifiers::CONTROL), Code::Numpad0); // Ctrl+Num0
    
    // Добавьте новые:
    // Modifiers::CONTROL | Modifiers::SHIFT - Ctrl+Shift
    // Modifiers::ALT - Alt
    // Code::KeyA, Code::KeyB, и т.д. - буквы
    // Code::Numpad1..Code::Numpad0 - цифры на цифровой клавиатуре
}
```

После изменения пересоберите: `cd llm-assistant-tauri && npm run tauri build`

### Как это работает

1. Нажмите `Ctrl+Num0` → запись начнётся (кнопка микрофона анимируется)
2. Говорите → VAD автоматически остановит запись через 2 сек тишины
3. Нажмите `Ctrl+Num0` ещё раз → запись остановится
4. Через 1 секунду текст отправится AI и ответ придёт голосом (если TTS включён)

## Настройка LLM

### Ollama (рекомендуется)

```env
LLM_PROVIDER=ollama
LLM_MODEL=qwen2.5:7b
```
Установка: https://ollama.ai

### LM Studio

```env
LLM_PROVIDER=lm_studio
LLM_MODEL=qwen2.5-7b-instruct
```

### OpenRouter (облачный)

```env
LLM_PROVIDER=openrouter
LLM_MODEL=openai/gpt-4o
LLM_API_KEY=sk-or-v1-...
```

## Структура проекта

```
local_assistant/
├── .env.example
├── config.py
├── requirements.txt
├── backend/
│   ├── main.py           # FastAPI + STT endpoint
│   └── requirements.txt
├── src/
│   ├── llm_engine.py     # Ollama API
│   ├── stt_engine.py     # Whisper STT
│   └── memory_manager.py # ChromaDB
├── llm-assistant-tauri/  # Desktop app (Tauri)
│   ├── src-tauri/
│   │   ├── src/lib.rs    # Global shortcuts
│   │   └── tauri.conf.json
│   └── src/
│       ├── app.js        # Voice recording + VAD
│       └── index.html    # UI
└── storage/              # ChromaDB
```

## API Endpoints

| Метод | Эндпоинт | Описание |
|-------|----------|----------|
| GET | `/api/status` | Статус |
| POST | `/api/chat` | Чат с AI |
| POST | `/api/stt` | Распознавание голоса |
| GET | `/api/chats` | Список чатов |
| DELETE | `/api/chats/{id}` | Удалить чат |

## Зависимости Python

```bash
pip install transformers torch torchaudio librosa numpy
```

## Требования

- Python 3.11+
- 8GB RAM (рекомендуется 16GB)
- GPU с 6GB VRAM (для LLM + STT)
- Windows 10/11

## Лицензия

MIT