"""
FastAPI бэкенд для Local AI Assistant.

Основное приложение, которое:
1. Предоставляет REST API для всех функций ассистента
2. Поддерживает WebSocket для real-time событий

Архитектурные решения:
1. API-first: бэкенд работает независимо от фронтенда
2. CORS настроен для будущих внешних клиентов
3. Подготовка к голосовому сервису (отдельный клиент API)

Запуск:
    uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
"""

import logging
import sys
import os
import tempfile
import base64
import io
from pathlib import Path
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from dotenv import load_dotenv

try:
    from PIL import Image
except ImportError:
    Image = None

# Загружаем .env в переменные окружения для поисковых инструментов
load_dotenv()

from fastapi import FastAPI, Request, HTTPException, Depends, WebSocket, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware

# Добавляем родительскую директорию в path для импортов
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import get_config, Config
from backend.database import ChatDatabase
from backend.api import (
    memory_router,
    manager,
    ChatMessage,
    ChatResponseMessage,
    set_db_getter,
)


# === Настройка логирования ===
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


# === Глобальные объекты ===
_config: Config | None = None
_assistant = None
_db: ChatDatabase | None = None


def get_assistant():
    """Получить глобальный экземпляр ассистента."""
    return _assistant


def get_db() -> ChatDatabase:
    """Получить глобальный экземпляр БД."""
    if _db is None:
        raise HTTPException(status_code=503, detail="База данных не инициализирована")
    return _db


# Dependency для injection БД
async def get_db_dependency() -> ChatDatabase:
    """Dependency для получения БД в роутах."""
    return get_db()


# === Lifecycle события ===

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    """
    Управление жизненным циклом приложения.
    
    Инициализирует и закрывает ресурсы при старте/остановке.
    """
    global _config, _assistant, _db
    
    logger.info("Запуск Local AI Assistant Backend...")
    
    # Загружаем конфигурацию
    _config = get_config()
    logger.info(f"Конфигурация загружена: провайдер={_config.llm.provider.value}, модель={_config.llm.model}")
    
    # Инициализируем базу данных чатов
    _db = ChatDatabase(str(Path(__file__).parent.parent / "storage" / "chats.db"))
    await _db.initialize()
    
    # Устанавливаем getter для БД (для api.py)
    set_db_getter(lambda: _db)
    
    # Инициализируем ассистента (опционально, для API чата)
    try:
        from src.main import Assistant
        _assistant = Assistant(_config)
        await _assistant.initialize()
        logger.info("Ассистент инициализирован для API")
        # Для LM Studio — синхронизируем модель с реально загруженной в LM Studio (один раз при старте)
        if _config.llm.provider.value == "lm_studio":
            try:
                import httpx
                async with httpx.AsyncClient(timeout=3.0) as client:
                    resp = await client.get(f"{_config.llm.host}/api/v0/models")
                    if resp.status_code == 200:
                        for m in resp.json().get("data", []):
                            if m.get("state") == "loaded":
                                loaded_id = m.get("id")
                                if loaded_id and loaded_id != _config.llm.model:
                                    logger.info(f"Синхронизация модели LM Studio: {_config.llm.model} -> {loaded_id} (загружена в LM Studio)")
                                    _config.llm.model = loaded_id
                                    if _assistant and _assistant._llm:
                                        _assistant._llm._config.model = loaded_id
                                break
            except Exception as e:
                logger.debug(f"Не удалось синхронизировать модель LM Studio: {e}")
    except Exception as e:
        logger.warning(f"Не удалось инициализировать ассистента: {e}")
        logger.warning("API чата будет недоступно, но веб-интерфейс работает")
        _assistant = None
    
    # Запускаем keep-alive для Ollama
    try:
        from backend.background_tasks import start_ollama_keep_alive
        await start_ollama_keep_alive(interval=60)
    except Exception as e:
        logger.warning(f"Не удалось запустить keep-alive: {e}")
    
    logger.info("Backend готов к работе")
    
    yield  # Приложение работает
    
    # Завершение работы
    logger.info("Остановка Backend...")
    
    # Останавливаем keep-alive
    try:
        from backend.background_tasks import stop_ollama_keep_alive
        await stop_ollama_keep_alive()
    except Exception:
        pass
    
    if _assistant:
        await _assistant.close()
    
    if _db:
        await _db.close()
    
    logger.info("Backend остановлен")


# === Создание приложения ===

app = FastAPI(
    title="Local AI Assistant API",
    description="API для локального AI-ассистента с поддержкой чатов, памяти и голосового ввода",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS для будущих внешних клиентов
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # В продакшене ограничить
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Middleware для обработки OPTIONS запросов (нужно для WebSocket)
@app.middleware("http")
async def handle_options(request: Request, call_next):
    """Обрабатывает OPTIONS запросы для CORS."""
    if request.method == "OPTIONS":
        from starlette.responses import Response
        response = Response(status_code=200)
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "*"
        return response
    
    return await call_next(request)


# === Монтирование роутов ===

app.include_router(memory_router)

# Добавляем WebSocket роут напрямую к app
# Это помогает обойти проверку origin
@app.websocket("/ws/events")
async def global_websocket_endpoint(websocket: WebSocket):
    """Глобальный WebSocket эндпоинт."""
    from backend.api import manager
    from fastapi import WebSocketDisconnect
    
    logger.info(f"WebSocket запрос (global): origin={websocket.headers.get('origin')}")
    
    try:
        await manager.connect(websocket)
        logger.info("WebSocket подключён (global)")
        
        # Просто держим подключение открытым
        while True:
            try:
                data = await websocket.receive_json()
                await manager.send_personal(websocket, {"type": "echo", "data": data})
            except Exception:
                continue
                
    except WebSocketDisconnect:
        manager.disconnect(websocket)
        logger.info("WebSocket отключён (global)")
    except Exception as e:
        logger.error(f"WebSocket ошибка: {e}")
        manager.disconnect(websocket)


# === API эндпоинты ===


@app.get("/api/chats")
async def get_all_chats():
    """Получить список всех чатов."""
    chats = await _db.get_all_chats()
    return [
        {
            "id": c.id,
            "title": c.title,
            "created_at": c.created_at,
            "updated_at": c.updated_at,
        }
        for c in chats
    ]


@app.post("/api/chats")
async def create_chat(request: dict):
    """Создать новый чат."""
    title = request.get("title", "Новый чат")
    chat_id = await _db.create_chat(title)
    chat = await _db.get_chat(chat_id)
    return {
        "id": chat.id,
        "title": chat.title,
        "created_at": chat.created_at,
        "updated_at": chat.updated_at,
    }


@app.put("/api/chats/{chat_id}")
async def update_chat(chat_id: int, request: dict):
    """Обновить чат (переименовать)."""
    title = request.get("title")
    if title:
        await _db.update_chat_title(chat_id, title)
    chat = await _db.get_chat(chat_id)
    if not chat:
        raise HTTPException(status_code=404, detail="Чат не найден")
    return {
        "id": chat.id,
        "title": chat.title,
        "created_at": chat.created_at,
        "updated_at": chat.updated_at,
    }


@app.get("/api/chats/{chat_id}/messages")
async def get_chat_messages(chat_id: int):
    """Получить сообщения чата."""
    messages = await _db.get_chat_history(chat_id)
    return [
        {
            "id": m.id,
            "chat_id": m.chat_id,
            "role": m.role,
            "content": m.content,
            "created_at": m.created_at,
        }
        for m in messages
    ]


@app.delete("/api/chats/{chat_id}")
async def delete_chat(chat_id: int):
    """Удалить чат."""
    deleted = await _db.delete_chat(chat_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Чат не найден")
    return {"status": "ok"}


@app.delete("/api/chats/{chat_id}/messages")
async def clear_chat_messages(chat_id: int):
    """Очистить сообщения чата."""
    await _db.clear_chat_history(chat_id)
    return {"status": "ok"}


@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    """Загрузить файл (документ или изображение) и извлечь данные."""
    document_types = [
        "text/plain",
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/msword",
    ]
    image_types = [
        "image/png",
        "image/jpeg",
        "image/jpg",
        "image/webp",
        "image/gif",
        "image/bmp",
        "image/tiff",
    ]
    allowed_types = document_types + image_types
    
    if file.content_type not in allowed_types:
        raise HTTPException(status_code=400, detail=f"Формат {file.content_type} не поддерживается. Используйте: txt, pdf, docx, png, jpg, webp, gif, bmp, tiff")
    
    try:
        content = await file.read()
        
        # Обработка изображений — кодируем в base64
        if file.content_type in image_types:
            import base64
            import io
            from PIL import Image
            
            # Открываем изображение для получения размеров
            img = Image.open(io.BytesIO(content))
            width, height = img.size
            
            # Опционально: ресайз больших изображений (макс 1024px по большей стороне)
            max_dim = 1024
            if max(width, height) > max_dim:
                ratio = max_dim / max(width, height)
                new_size = (int(width * ratio), int(height * ratio))
                img = img.resize(new_size, Image.Resampling.LANCZOS)
                # Сохраняем обратно в bytes
                buf = io.BytesIO()
                img.save(buf, format=img.format or "PNG")
                content = buf.getvalue()
            
            image_base64 = base64.b64encode(content).decode('utf-8')
            
            return {
                "filename": file.filename,
                "type": "image",
                "base64": image_base64,
                "mime_type": file.content_type,
                "width": img.width,
                "height": img.height,
            }
        
        # Документы — сохраняем во временный файл и извлекаем текст
        ext = file.filename.split(".")[-1] if "." in file.filename else "txt"
        with tempfile.NamedTemporaryFile(delete=False, suffix=f".{ext}") as tmp:
            tmp.write(content)
            tmp_path = tmp.name
        
        from src.file_processor import extract_text
        text = await extract_text(tmp_path, file.content_type)
        
        os.unlink(tmp_path)
        
        return {
            "filename": file.filename,
            "type": "document",
            "text": text,
            "char_count": len(text),
        }
        
    except Exception as e:
        logger.error(f"Ошибка загрузки файла: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/chat", response_model=ChatResponseMessage)
async def chat(request: ChatMessage):
    """
    Отправить сообщение и получить ответ от AI.

    Основной эндпоинт для чата с ассистентом.

    Args:
        request: Сообщение и опционально ID чата.

    Returns:
        ChatResponseMessage: Ответ ассистента и ID чата.
    """
    if not _assistant:
        raise HTTPException(
            status_code=503,
            detail="Ассистент не инициализирован. Убедитесь, что Ollama запущена (ollama serve).",
        )

    # Создаём новый чат если не указан
    chat_id = request.chat_id
    if not chat_id:
        chat_id = await _db.create_chat("Новый диалог")

    # Сохраняем сообщение пользователя
    await _db.add_message(chat_id, "user", request.message)

    # Загружаем историю чата для контекста (последние 30 сообщений, без дубля текущего)
    history_messages = await _db.get_chat_history(chat_id)
    # Исключаем последнее сообщение (текущее user), т.к. оно уже передаётся как user_message отдельно
    if history_messages and history_messages[-1].role == "user" and history_messages[-1].content == request.message:
        history_messages = history_messages[:-1]
    # Ограничиваем историю чтобы не раздувать промпт (57 сообщений → 1968 токенов, было медленно)
    MAX_HISTORY = 30
    if len(history_messages) > MAX_HISTORY:
        history_messages = history_messages[-MAX_HISTORY:]
    chat_history = [
        {"role": msg.role, "content": msg.content}
        for msg in history_messages
        if msg.role in ("user", "assistant")
    ]

    # Для LM Studio — подменяем модель на реально загруженную (1 запрос в 30с, чтобы не грузить вторую)
    if _config and _config.llm.provider.value == "lm_studio":
        loaded = await get_lmstudio_loaded_model()
        if loaded and _assistant and _assistant._llm and loaded != _assistant._llm._config.model:
            logger.info(f"Подмена модели {_assistant._llm._config.model} -> {loaded} (загружена в LM Studio)")
            _assistant._llm._config.model = loaded

    # Получаем ответ от ассистента
    try:
        llm_response = await _assistant.process_message(
            request.message,
            thinking=request.thinking,
            search=request.search,
            chat_history=chat_history,
            images=request.images,
        )
        response_text = llm_response.content
        used_tokens = llm_response.prompt_tokens
    except Exception as e:
        logger.error(f"Ошибка при генерации ответа: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    # Сохраняем ответ ассистента
    await _db.add_message(chat_id, "assistant", response_text)

    # Отправляем событие через WebSocket
    logger.info(f"Отправка WebSocket события: chat_id={chat_id}, content={response_text[:50]}...")
    await manager.broadcast({
        "type": "new_message",
        "chat_id": chat_id,
        "role": "assistant",
        "content": response_text,
    })

    max_ctx = await get_effective_context_length()

    return ChatResponseMessage(
        response=response_text,
        chat_id=chat_id,
        message_id=0,
        used_context_tokens=used_tokens,
        max_context_tokens=max_ctx,
    )


_cached_lm_model: str | None = None
_cached_lm_model_time: float = 0.0

async def get_lmstudio_loaded_model() -> str | None:
    """Вернуть id загруженной модели в LM Studio (кеш 30с), чтобы не грузить вторую."""
    global _cached_lm_model, _cached_lm_model_time
    import time
    now = time.monotonic()
    if _cached_lm_model is not None and (now - _cached_lm_model_time) < 30.0:
        return _cached_lm_model
    try:
        cfg = get_config().llm
        if cfg.provider.value != "lm_studio":
            return None
        import httpx
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(f"{cfg.host}/api/v0/models")
            if resp.status_code == 200:
                for m in resp.json().get("data", []):
                    if m.get("state") == "loaded":
                        _cached_lm_model = m.get("id")
                        _cached_lm_model_time = now
                        return _cached_lm_model
    except:
        pass
    return None

async def get_effective_context_length() -> int:
    """Вернуть лимит контекста из конфига (для LM Studio — тоже из .env, без лишних запросов)."""
    cfg = get_config().llm
    return int(getattr(cfg, 'num_ctx', 8192))


@app.get("/api/status")
async def get_status():
    """
    Получить статус сервиса.
    """
    stats = {}
    
    if _db:
        chats = await _db.get_all_chats()
        stats["chats_count"] = len(chats)
    
    if _assistant and _assistant._memory:
        memory_stats = await _assistant._memory.get_stats()
        stats["memory_entries"] = memory_stats.get("total_entries", 0)
    
    thinking_supported = await _config.llm.check_thinking_support() if _config else False
    effective_ctx = await get_effective_context_length() if _config else 8192
    
    return {
        "status": "ok",
        "provider": _config.llm.provider.value if _config else "unknown",
        "model": _config.llm.model if _config else "unknown",
        "supports_thinking": thinking_supported,
        "loaded_context_length": effective_ctx,
        "max_context_length": effective_ctx,
        **stats,
    }


@app.get("/api/config")
async def get_current_config():
    """Получить текущую конфигурацию. Для LM Studio — возвращает реально загруженную модель."""
    if not _config:
        return {
            "provider": "ollama", "model": "", "ollama_host": "http://localhost:11434",
            "api_key": "", "num_ctx": 8192, "temperature": 0.7,
            "tts_steps": 64, "tts_temperature": 1.0,
            "memory_max_context": 20, "memory_search_results": 3, "memory_threshold": 0.3,
        }
    
    return {
        "provider": _config.llm.provider.value,
        "model": _config.llm.model,
        "ollama_host": _config.llm.host,
        "api_key": _config.llm.api_key or "",
        "num_ctx": _config.llm.num_ctx,
        "temperature": _config.llm.temperature,
        "tts_steps": _config.tts.steps,
        "tts_temperature": _config.tts.temperature,
        "memory_max_context": _config.memory.max_context_messages,
        "memory_search_results": _config.memory.search_results,
        "memory_threshold": _config.memory.similarity_threshold,
    }


@app.put("/api/config")
async def update_config(request: dict):
    """Обновить конфигурацию (сохраняется в .env файл). При смене модели/контекста для LM Studio — автозагрузка."""
    from config import get_config, save_config, reload_config
    
    provider = request.get("provider", "ollama")
    model = request.get("model", "")
    ollama_host = request.get("ollama_host", "http://localhost:11434")
    api_key = request.get("api_key", "")
    num_ctx = request.get("num_ctx")
    temperature = request.get("temperature")
    tts_steps = request.get("tts_steps")
    tts_temperature = request.get("tts_temperature")
    memory_max_context = request.get("memory_max_context")
    memory_search_results = request.get("memory_search_results")
    memory_threshold = request.get("memory_threshold")

    # Запомним предыдущую модель/контекст для определения смены
    try:
        prev_cfg = get_config()
        prev_model = prev_cfg.llm.model
        prev_provider = prev_cfg.llm.provider.value
        prev_ctx = prev_cfg.llm.num_ctx
    except:
        prev_model = ""
        prev_provider = ""
        prev_ctx = None
    
    save_config(
        provider=provider,
        model=model,
        ollama_host=ollama_host,
        api_key=api_key,
        num_ctx=num_ctx,
        temperature=temperature,
        tts_steps=tts_steps,
        tts_temperature=tts_temperature,
        memory_max_context=memory_max_context,
        memory_search_results=memory_search_results,
        memory_threshold=memory_threshold,
    )
    # Hot-swap без рестарта
    try:
        new_cfg = reload_config()
        global _config
        _config = new_cfg
        if _assistant:
            _assistant._config = new_cfg
            if _assistant._llm:
                _assistant._llm._config = new_cfg.llm
                # Пересоздать http клиент с новым host/api_key если сменился
                try:
                    await _assistant._llm.close()
                except:
                    pass
                _assistant._llm._initialized = False
                await _assistant._llm.initialize()
    except Exception as e:
        logger.warning(f"Hot-swap config failed: {e}")

    # Для LM Studio — только сохранение, без автозагрузки (меняется в самом LM Studio, read-only в UI)
    load_result = None
    if False and provider == "lm_studio" and model and (model != prev_model or (num_ctx and num_ctx != prev_ctx)):
        try:
            import httpx
            base = ollama_host.rstrip("/") if ollama_host else "http://localhost:1234"
            if not base.startswith("http"):
                base = "http://" + base
            # Выгрузить старые загруженные модели перед загрузкой новой (чтобы не копились :2, :3)
            # Если та же модель с тем же контекстом уже загружена — пропускаем выгрузку
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    r = await client.get(f"{base}/api/v0/models")
                    if r.status_code == 200:
                        data = r.json()
                        target_ctx = None
                        try:
                            target_ctx = int(num_ctx) if num_ctx else None
                        except:
                            pass
                        already_ok = False
                        for m in data.get("data", []):
                            if m.get("state") == "loaded" and m.get("id") == model:
                                if target_ctx is None or m.get("loaded_context_length") == target_ctx:
                                    already_ok = True
                                    break
                        if not already_ok:
                            for m in data.get("data", []):
                                if m.get("state") == "loaded":
                                    try:
                                        await client.post(f"{base}/api/v1/models/unload", json={"instance_id": m.get("id")}, timeout=10.0)
                                        logger.info(f"Выгружена старая модель: {m.get('id')}")
                                    except Exception as ue:
                                        logger.debug(f"Не удалось выгрузить {m.get('id')}: {ue}")
            except Exception as e:
                logger.debug(f"Ошибка при выгрузке старых моделей: {e}")
            payload = {"model": model}
            if num_ctx:
                try:
                    payload["context_length"] = int(num_ctx)
                except:
                    pass
            async with httpx.AsyncClient(timeout=90.0) as client:
                resp = await client.post(f"{base}/api/v1/models/load", json=payload)
                if resp.status_code in (200, 204):
                    load_result = {"ok": True}
                else:
                    try:
                        data = resp.json()
                    except:
                        data = {"raw": resp.text[:500]}
                    if resp.status_code == 400 and "already loaded" in str(data).lower():
                        load_result = {"ok": True, "already_loaded": True}
                    else:
                        load_result = {"ok": False, "status": resp.status_code, "detail": data}
        except Exception as e:
            load_result = {"ok": False, "error": str(e)}

    if load_result is not None:
        if load_result.get("ok"):
            return {"status": "ok", "message": "Конфигурация сохранена и модель загружена в LM Studio", "load": load_result}
        else:
            return {"status": "ok", "message": "Конфигурация сохранена, но автозагрузка в LM Studio не удалась — загрузите вручную", "load": load_result, "warning": True}
    
    return {"status": "ok", "message": "Конфигурация сохранена (hot-swap без рестарта)"}


@app.post("/api/tts/toggle")
async def toggle_tts(request: Request):
    """
    Переключить TTS (OmniVoice) вкл/выкл.
    
    Принимает raw JSON bool (true/false) или объект {"enabled": true}.
    При enabled=True - загружает OmniVoice в память.
    При enabled=False - выгружает OmniVoice из памяти.
    """
    if not _assistant:
        raise HTTPException(status_code=503, detail="Ассистент не инициализирован")
    
    try:
        body = await request.json()
    except:
        body = False
    if isinstance(body, bool):
        enabled = body
    elif isinstance(body, dict):
        enabled = bool(body.get("enabled", body.get("value", False)))
    else:
        enabled = bool(body)
    
    if enabled:
        success = await _assistant._tts.enable_omnivoice()
    else:
        success = await _assistant._tts.disable_omnivoice()
    
    return {
        "status": "ok",
        "enabled": enabled,
        "omnivoice_loaded": _assistant._tts.is_omnivoice_loaded if enabled else False,
    }


@app.get("/api/tts/status")
async def get_tts_status():
    """Получить статус TTS."""
    if not _assistant or not _assistant._tts:
        return {"enabled": False, "omnivoice_loaded": False}
    
    return {
        "enabled": True,
        "omnivoice_loaded": _assistant._tts.is_omnivoice_loaded,
    }


@app.post("/api/tts/config")
async def tts_config(request: dict):
    """
    Настроить параметры TTS голоса.
    
    Параметры:
    - instruct: описание голоса (female, male, female russian, и т.д.)
    - position_temperature: 0 = стабильный, выше = случайный
    - class_temperature: 0 = стабильный, выше = случайный
    """
    if not _assistant or not _assistant._tts:
        raise HTTPException(status_code=503, detail="TTS не инициализирован")
    
    mode = request.get("mode", "instruct")  # "instruct" или "clone"
    instruct = request.get("instruct", "female")
    ref_audio = request.get("ref_audio", None)  # путь к файлу референса
    position_temp = request.get("position_temperature", 0.0)
    class_temp = request.get("class_temperature", 0.0)
    
    # Сохраняем конфиг в TTSEngine (фасад)
    _assistant._tts.set_voice_config(
        mode=mode,
        instruct=instruct,
        ref_audio=ref_audio,
        position_temperature=position_temp,
        class_temperature=class_temp,
    )
    
    # Если OmniVoice уже загружен - применяем конфиг сразу
    if _assistant._tts.is_omnivoice_loaded and hasattr(_assistant._tts._engine, 'set_voice_config'):
        _assistant._tts._engine.set_voice_config(
            mode=mode,
            instruct=instruct,
            ref_audio=ref_audio,
            position_temperature=position_temp,
            class_temperature=class_temp,
        )
        logger.info(f"Конфиг применён к уже загруженному OmniVoice: mode={mode}, ref={ref_audio}")
    
    return {
        "status": "ok",
        "mode": mode,
        "instruct": instruct,
        "ref_audio": ref_audio,
        "position_temperature": position_temp,
        "class_temperature": class_temp,
    }


@app.get("/api/tts/voices")
async def get_voices():
    """Получить список доступных голосов для клонирования."""
    from pathlib import Path
    
    voices_dir = Path(__file__).parent.parent / "voices"
    voices = []
    
    if voices_dir.exists():
        for f in voices_dir.iterdir():
            if f.suffix.lower() in ['.wav', '.mp3', '.ogg', '.flac']:
                voices.append({
                    "name": f.stem,
                    "file": f.name,
                    "path": str(f),
                })
    
    return {"voices": voices}


@app.get("/api/tts/config")
async def get_tts_config():
    """Получить текущую конфигурацию TTS."""
    if not _assistant or not _assistant._tts:
        return {"instruct": "female", "position_temperature": 0.0, "class_temperature": 0.0}
    
    engine = _assistant._tts._engine
    if hasattr(engine, '_instruct'):
        return {
            "instruct": engine._instruct,
            "position_temperature": engine._position_temperature,
            "class_temperature": engine._class_temperature,
        }
    
    return {"instruct": "female", "position_temperature": 0.0, "class_temperature": 0.0}


@app.post("/api/tts/speak")
async def tts_speak(request: dict):
    """
    Синтезировать речь из текста и вернуть аудио.
    """
    if not _assistant or not _assistant._tts:
        raise HTTPException(status_code=503, detail="TTS не инициализирован")
    
    text = request.get("text", "")
    if not text:
        raise HTTPException(status_code=400, detail="Текст не предоставлен")
    
    # Проверяем что OmniVoice загружен
    if not _assistant._tts.is_omnivoice_loaded:
        # Пробуем загрузить
        await _assistant._tts.enable_omnivoice()
    
    # Синтезируем
    result = await _assistant._tts.speak(text)
    
    if not result.success:
        raise HTTPException(status_code=500, detail=result.error or "Ошибка синтеза")
    
    # Возвращаем аудио
    from fastapi.responses import Response
    return Response(
        content=result.audio_data,
        media_type="audio/wav",
        headers={"Content-Disposition": "inline"},
    )


@app.get("/api/models")
async def get_models(provider: str = "ollama", host: str = "http://localhost:11434"):
    """Получить список моделей для провайдера."""
    import httpx
    
    if provider == "ollama":
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(f"{host}/api/tags")
                if resp.status_code == 200:
                    data = resp.json()
                    models = [m["name"] for m in data.get("models", [])]
                    return {"models": models}
        except Exception as e:
            return {"models": [], "error": str(e)}
    
    elif provider == "lm_studio":
        try:
            # Уважать host параметр (как для ollama)
            base = host.rstrip("/") if host else "http://localhost:1234"
            if not base.startswith("http"):
                base = "http://" + base
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(f"{base}/v1/models")
                if resp.status_code == 200:
                    data = resp.json()
                    models = [m["id"] for m in data.get("data", [])]
                    return {"models": models}
        except Exception as e:
            return {"models": [], "error": str(e)}
    
    elif provider == "openrouter":
        # OpenRouter не имеет простого API для списка моделей
        # Используем популярные модели по умолчанию
        return {
            "models": [
                "qwen/qwen2.5-7b-instruct",
                "qwen/qwen2.5-32b-instruct",
                "meta-llama/llama-3.1-8b-instruct",
                "google/gemma-2-9b-it",
                "anthropic/claude-3.5-sonnet",
            ]
        }
    
    return {"models": []}


@app.post("/api/models/load")
async def load_model(request: dict):
    """Загрузить модель в провайдере (LM Studio: POST /api/v1/models/load). Выгружает предыдущую если нужно."""
    provider = request.get("provider", "lm_studio")
    model = request.get("model", "")
    host = request.get("host", "http://localhost:1234")
    context_length = request.get("context_length") or request.get("num_ctx")

    if not model:
        raise HTTPException(status_code=400, detail="model не указан")

    if provider == "lm_studio":
        base = host.rstrip("/") if host else "http://localhost:1234"
        if not base.startswith("http"):
            base = "http://" + base
        # Выгрузить предыдущие загруженные модели (чтобы не копились :2, :3 инстансы)
        # Логика: если уже загружена та же модель с тем же контекстом — ничего не делаем,
        # иначе выгружаем все загруженные (особенно ту же модель с другим контекстом)
        try:
            import httpx
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(f"{base}/api/v0/models")
                if resp.status_code == 200:
                    data = resp.json()
                    target_ctx = None
                    try:
                        target_ctx = int(context_length) if context_length else None
                    except:
                        pass
                    # Проверить already loaded с тем же контекстом
                    already_ok = False
                    for m in data.get("data", []):
                        if m.get("state") == "loaded" and m.get("id") == model:
                            loaded_ctx = m.get("loaded_context_length")
                            if target_ctx is None or loaded_ctx == target_ctx:
                                already_ok = True
                                break
                    if already_ok:
                        logger.info(f"Модель {model} уже загружена с контекстом {target_ctx}, пропускаем выгрузку")
                    else:
                        # Выгружаем все загруженные (и ту же модель с другим контекстом, и другие модели)
                        for m in data.get("data", []):
                            if m.get("state") == "loaded":
                                inst_id = m.get("id")
                                # Не выгружаем саму цель если она уже загружена с правильным контекстом (выше уже проверили)
                                # Иначе выгружаем всё
                                try:
                                    await client.post(f"{base}/api/v1/models/unload", json={"instance_id": inst_id}, timeout=10.0)
                                    logger.info(f"Выгружена предыдущая модель: {inst_id}")
                                except Exception as ue:
                                    logger.debug(f"Не удалось выгрузить {inst_id}: {ue}")
        except Exception as e:
            logger.debug(f"Ошибка при выгрузке старых моделей: {e}")

        payload = {"model": model}
        if context_length:
            try:
                payload["context_length"] = int(context_length)
            except:
                pass
        # Попытка загрузить
        try:
            import httpx
            async with httpx.AsyncClient(timeout=90.0) as client:
                resp = await client.post(f"{base}/api/v1/models/load", json=payload)
                if resp.status_code in (200, 204):
                    return {"ok": True, "provider": provider, "model": model, "context_length": context_length}
                # LM Studio может вернуть 400 если уже загружена — считаем ok
                try:
                    data = resp.json()
                except:
                    data = {"raw": resp.text[:500]}
                if resp.status_code == 400 and "already loaded" in str(data).lower():
                    return {"ok": True, "provider": provider, "model": model, "already_loaded": True}
                return {"ok": False, "status": resp.status_code, "detail": data}
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"LM Studio load failed: {e}")
    elif provider == "ollama":
        # Ollama грузит лениво, отдельная команда не нужна — hot-swap через payload.model
        return {"ok": True, "provider": provider, "model": model, "jit": True}
    else:
        return {"ok": True, "provider": provider, "model": model}


# === STT (Speech-to-Text) ===

_stt_engine = None

async def get_stt_engine():
    """Получить или создать STT движок."""
    global _stt_engine
    if _stt_engine is None:
        from src.stt_engine import get_stt_engine
        _stt_engine = get_stt_engine()
        await _stt_engine.initialize()
    return _stt_engine


@app.post("/api/stt")
async def stt_transcribe(file: UploadFile = File(...)):
    """
    Распознать речь из аудио файла.
    
    Принимает аудио файл (webm, wav, mp3) и возвращает распознанный текст.
    """
    logger.info(f"Получен аудио файл: {file.filename}, тип: {file.content_type}")
    
    # Проверяем формат
    allowed_types = ["audio/webm", "audio/wav", "audio/wave", "audio/x-wav", "audio/mp3", "audio/mpeg", "audio/ogg", "audioopus"]
    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=400, 
            detail=f"Неподдерживаемый формат: {file.content_type}. Используйте webm, wav или mp3"
        )
    
    try:
        # Инициализируем STT если нужно
        stt = await get_stt_engine()
        
        # Читаем аудио
        audio_data = await file.read()
        
        # Определяем формат
        ext = file.filename.split(".")[-1] if "." in file.filename else "webm"
        
        # Распознаём
        logger.info("Начало распознавания...")
        text = await stt.transcribe_bytes(audio_data, format=ext)
        
        logger.info(f"Распознано: {text[:100]}...")
        
        return {"text": text, "success": True}
        
    except Exception as e:
        logger.error(f"Ошибка STT: {e}", exc_info=True)
        # Если ошибка пустая — показать repr и traceback для диагностики
        detail = str(e) or repr(e) or e.__class__.__name__
        if not detail.strip():
            import traceback
            detail = traceback.format_exc()[-500:]
        raise HTTPException(status_code=500, detail=f"Ошибка распознавания: {detail}")


# === Запуск ===

if __name__ == "__main__":
    import uvicorn
    
    # Запускаем с отключенной проверкой host для WebSocket
    uvicorn.run(
        app,
        host="0.0.0.0",  # Слушаем все интерфейсы
        port=8000,
        reload=False,
        ws_ping_interval=None,  # Отключаем ping для стабильности
        ws_ping_timeout=None,
    )
