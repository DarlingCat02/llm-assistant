"""
FastAPI backend for Local AI Assistant.

Main application that:
1. Provides REST API for all assistant features
2. Supports WebSocket for real-time events

Architecture decisions:
1. API-first: backend works independently of the frontend
2. CORS configured for future external clients
3. Voice (STT/TTS) served as built-in endpoints of the same app

Run:
    uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
"""

import logging
import re
import sys
import os
import asyncio
import tempfile
import base64
import io
from pathlib import Path
from contextlib import asynccontextmanager
from typing import AsyncGenerator


def pick_lmstudio_model(configured: str, loaded: list[str]) -> str | None:
    """
    Decide which LM Studio model the assistant should talk to at startup.

    Rules:
    - if the configured model is loaded, keep it - the user chose it;
    - otherwise fall back to the first loaded model, so a stale .env does not
      make the backend request a second model and waste VRAM;
    - nothing loaded -> keep the configuration and let the request fail loudly.

    Returns the model to use, or None when the configuration should be kept.
    """
    if not loaded:
        return None
    if configured in loaded:
        return None
    return loaded[0]


class _CrashProofStderr:
    """sys.stderr wrapper that never raises on write/flush.

    The backend is spawned by Tauri with a piped stderr. Progress bars
    (tqdm used by transformers model loading) flush that stream directly,
    and the flush can fail with OSError(22) once the pipe is in a bad
    state - killing model loading AFTER a previous engine already loaded.
    Guarding the stream makes such failures impossible; normal logging
    keeps working because it holds its own handler references.
    """

    def __init__(self, stream):
        object.__setattr__(self, "_stream", stream)

    def write(self, data):
        try:
            return self._stream.write(data)
        except Exception:
            return 0

    def flush(self):
        try:
            return self._stream.flush()
        except Exception:
            return None

    def __getattr__(self, name):
        return getattr(object.__getattribute__(self, "_stream"), name)

    def __setattr__(self, name, value):
        setattr(object.__getattribute__(self, "_stream"), name, value)


if not isinstance(getattr(sys, "stderr", None), _CrashProofStderr):
    sys.stderr = _CrashProofStderr(sys.stderr)

# No transformers/hub progress bars in production logs (they write/flush
# stderr directly and are useless when piped). Respected by huggingface_hub.
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")

from dotenv import load_dotenv

try:
    from PIL import Image
except ImportError:
    Image = None

# Load .env into environment variables for search tools
load_dotenv()

from fastapi import FastAPI, Request, HTTPException, Depends, WebSocket, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware

# Add the parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import get_config, Config
try:
    from src.i18n import t, assistant_not_init_detail
except ImportError:
    try:
        from i18n import t, assistant_not_init_detail  # type: ignore
    except ImportError:
        def t(key, lang=None, **kwargs):
            return key
        def assistant_not_init_detail(lang=None):
            return "Assistant not initialized"
from dataclasses import asdict

from backend.database import ChatDatabase
from src.personas import Persona
from backend.api import (
    memory_router,
    manager,
    ChatMessage,
    ChatResponseMessage,
    set_db_getter,
)


# === Logging setup ===
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


# === Global objects ===
_config: Config | None = None
_assistant = None
_db: ChatDatabase | None = None


def get_assistant():
    """Get the global assistant instance."""
    return _assistant


def get_db() -> ChatDatabase:
    """Get global DB instance."""
    if _db is None:
        try:
            lang = get_config().general.language
        except Exception:
            lang = "en"
        raise HTTPException(status_code=503, detail=t("api.db_not_init", lang=lang))
    return _db


# Dependency for DB injection
async def get_db_dependency() -> ChatDatabase:
    """Dependency for getting the DB in routes."""
    return get_db()


# === Lifecycle events ===

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    """
    Manage the application lifecycle.

    Initializes and closes resources on startup/shutdown.
    """
    global _config, _assistant, _db
    
    logger.info("Starting Local AI Assistant Backend...")

    # Disable transformers progress bars (they flush stderr directly;
    # see _CrashProofStderr above for why that is fatal here)
    try:
        from transformers.utils import logging as hf_logging
        hf_logging.disable_progress_bar()
    except Exception:
        pass

    # Load configuration
    _config = get_config()
    logger.info(f"Configuration loaded: provider={_config.llm.provider.value}, model={_config.llm.model}")
    
    # Initialize chat database
    _db = ChatDatabase(str(Path(__file__).parent.parent / "storage" / "chats.db"))
    await _db.initialize()
    
    # Set getter for DB (for api.py)
    set_db_getter(lambda: _db)
    
    # Initialize assistant (optional, for chat API)
    try:
        from src.main import Assistant
        _assistant = Assistant(_config)
        await _assistant.initialize()
        logger.info("Assistant initialized for API")
        # For LM Studio — align the model with what is actually loaded, but
        # never override a model the user configured that IS loaded. Taking the
        # first loaded model unconditionally used to swap qwen-3.5-4b for a 2B
        # that happened to be loaded too, silently breaking tool calling.
        if _config.llm.provider.value == "lm_studio":
            try:
                import httpx
                async with httpx.AsyncClient(timeout=3.0) as client:
                    resp = await client.get(f"{_config.llm.host}/api/v0/models")
                    if resp.status_code == 200:
                        loaded = [
                            m.get("id")
                            for m in resp.json().get("data", [])
                            if m.get("state") == "loaded" and m.get("id")
                        ]
                        chosen = pick_lmstudio_model(_config.llm.model, loaded)
                        if chosen and chosen != _config.llm.model:
                            logger.info(
                                f"Syncing LM Studio model: {_config.llm.model} -> {chosen} "
                                f"(loaded in LM Studio)"
                            )
                            _config.llm.model = chosen
                            if _assistant and _assistant._llm:
                                _assistant._llm._config.model = chosen
                        elif _config.llm.model in loaded:
                            logger.info(f"LM Studio model in use: {_config.llm.model}")
            except Exception as e:
                logger.debug(f"Failed to sync LM Studio model: {e}")
    except Exception as e:
        logger.warning(f"Failed to initialize assistant: {e}")
        logger.warning("Chat API will be unavailable, but web interface works")
        _assistant = None
    
    # Start keep-alive for Ollama
    try:
        from backend.background_tasks import start_ollama_keep_alive
        await start_ollama_keep_alive(interval=60)
    except Exception as e:
        logger.warning(f"Failed to start keep-alive: {e}")

    # Start wake-word (off by default; never fatal)
    try:
        _ok, _err = _wake_start()
        if _ok:
            logger.info("Wake word: listening")
    except Exception as e:
        logger.warning(f"Wake word did not start: {e}")

    logger.info("Backend ready")

    yield  # App running

    # Shutdown
    logger.info("Stopping Backend...")

    # Stop wake-word (releases the microphone)
    try:
        _wake_stop()
    except Exception:
        pass

    # Stop keep-alive
    try:
        from backend.background_tasks import stop_ollama_keep_alive
        await stop_ollama_keep_alive()
    except Exception:
        pass
    
    if _assistant:
        await _assistant.close()
    
    if _db:
        await _db.close()
    
    logger.info("Backend stopped")


# === Application setup ===

app = FastAPI(
    title="Local AI Assistant API",
    description="API для локального AI-ассистента с поддержкой чатов, памяти и голосового ввода",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS for future external clients
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Middleware for handling OPTIONS requests (needed for WebSocket)
@app.middleware("http")
async def handle_options(request: Request, call_next):
    """Handle OPTIONS requests for CORS."""
    if request.method == "OPTIONS":
        from starlette.responses import Response
        response = Response(status_code=200)
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "*"
        return response
    
    return await call_next(request)


# === Mounting routes ===

app.include_router(memory_router)

# Add the WebSocket route directly to app
# This helps bypass the origin check
@app.websocket("/ws/events")
async def global_websocket_endpoint(websocket: WebSocket):
    """Global WebSocket endpoint."""
    from backend.api import manager
    from fastapi import WebSocketDisconnect
    
    logger.info(f"WebSocket request (global): origin={websocket.headers.get('origin')}")
    
    try:
        await manager.connect(websocket)
        logger.info("WebSocket connected (global)")
        
        # Just keep connection open
        while True:
            try:
                data = await websocket.receive_json()
                await manager.send_personal(websocket, {"type": "echo", "data": data})
            except Exception:
                continue
                
    except WebSocketDisconnect:
        manager.disconnect(websocket)
        logger.info("WebSocket disconnected (global)")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        manager.disconnect(websocket)


# === Wake word ===

_wake_detector = None
_wake_error: str | None = None


def _wake_model_path() -> str:
    """Where the small Whisper used for wake detection lives."""
    from src.stt_engine import resolve_model_dir

    return resolve_model_dir("whisper-tiny", "whisper-tiny")


@app.get("/api/audio-inputs")
async def list_audio_inputs():
    """
    Microphones the wake-word listener can open.

    Returns the system default first, then everything else that can record.
    """
    try:
        import sounddevice as sd
    except Exception as e:
        return {"devices": [], "error": f"{type(e).__name__}: {e}"}

    try:
        default_index = sd.default.device[0]
    except Exception:
        default_index = None

    devices = []
    try:
        for idx, dev in enumerate(sd.query_devices()):
            if dev.get("max_input_channels", 0) < 1:
                continue
            devices.append({
                "index": idx,
                "name": dev.get("name", f"device {idx}"),
                "channels": int(dev.get("max_input_channels", 0)),
                "samplerate": float(dev.get("default_samplerate", 16000.0)),
                "default": idx == default_index,
            })
    except Exception as e:
        return {"devices": [], "error": f"{type(e).__name__}: {e}"}

    # Windows exposes one physical microphone several times (per sample rate,
    # per API). Listing all of them made the dropdown unusable, so keep the
    # first entry per name and note how many were folded away.
    unique: dict[str, dict] = {}
    for dev in devices:
        key = dev["name"].strip().lower()
        if key not in unique:
            dev["aliases"] = 0
            unique[key] = dev
        else:
            unique[key]["aliases"] += 1

    result = list(unique.values())
    # Default first so the common case needs no scrolling
    result.sort(key=lambda d: (not d["default"], d["name"].lower()))
    return {"devices": result, "error": None}


def _wake_start() -> tuple[bool, str | None]:
    """
    Start (or restart) always-listening wake-word detection.

    Degrades instead of raising: a missing model, a missing audio backend or a
    busy microphone must never stop the app from starting.
    """
    global _wake_detector, _wake_error

    _wake_stop()

    try:
        cfg = get_config().wake
    except Exception as e:
        logger.warning(f"Wake word: cannot read config: {e}")
        return False, str(e)

    if not cfg.enabled:
        _wake_error = None
        return False, None
    if not cfg.phrase.strip():
        _wake_error = "Пробуждающая фраза не задана"
        logger.warning("Wake word is enabled but no phrase is set - staying off")
        return False, _wake_error

    path = _wake_model_path()
    if not Path(path).is_dir():
        _wake_error = f"Модель не найдена: {path}"
        logger.warning(
            f"Wake word model not found at {path} - staying off. "
            f"Run: python tests/fetch_whisper_model.py {cfg.model}"
        )
        return False, _wake_error

    from src.wake_word import WakeWordDetector

    async def notify(text: str) -> None:
        # Called from the detector's own thread - schedule on the loop
        from backend.api import manager as ws_manager

        try:
            await ws_manager.broadcast({
                "type": "wake-word-detected",
                "transcript": text,
            })
        except Exception as e:
            logger.warning(f"Wake word notify failed: {e}")

    loop = asyncio.get_running_loop()

    def on_detect(text: str) -> None:
        asyncio.run_coroutine_threadsafe(notify(text), loop)

    detector = WakeWordDetector(
        phrase=cfg.phrase,
        model_path=path,
        on_detect=on_detect,
        cooldown=cfg.cooldown,
        threshold=cfg.match_threshold,
        input_device=cfg.input_device,
    )
    if not detector.start():
        err = detector.error or "неизвестная ошибка"
        logger.warning(f"Wake word did not start: {err}")
        _wake_detector = None
        _wake_error = err
        return False, err

    _wake_detector = detector
    _wake_error = None
    return True, None


def _wake_stop() -> None:
    global _wake_detector
    if _wake_detector is not None:
        try:
            _wake_detector.stop()
        except Exception as e:
            logger.warning(f"Wake word stop failed: {e}")
        _wake_detector = None


@app.get("/api/wake-word")
async def get_wake_word():
    """Current wake-word settings and live state."""
    from src.wake_word import phrase_score

    try:
        cfg = get_config().wake
    except Exception:
        cfg = None

    detector = _wake_detector
    return {
        "enabled": bool(cfg.enabled) if cfg else False,
        "phrase": cfg.phrase if cfg else "",
        "model": cfg.model if cfg else "tiny",
        "input_device": cfg.input_device if cfg else "",
        "cooldown": cfg.cooldown if cfg else 5.0,
        "match_threshold": cfg.match_threshold if cfg else 0.82,
        "listening": bool(detector and detector.is_running),
        "error": (detector.error if detector else None) or _wake_error,
        "active_device": (detector.device_name if detector else None),
        "device_problem": (detector.device_problem if detector else None),
        # Level meter: proves whether the microphone hears anything at all,
        # which is otherwise impossible to tell from the outside.
        "input_level": round(detector.input_level, 5) if detector else 0.0,
        "peak_level": round(detector.peak_level, 5) if detector else 0.0,
        "mic_open": bool(detector and detector.opened),
        "blocks_read": detector.blocks_read if detector else 0,
        "last_transcript": detector.last_transcript if detector else "",
        "phrase_score": (
            phrase_score(detector.last_transcript, cfg.phrase)
            if detector and cfg and detector.last_transcript else 0.0
        ),
    }


@app.put("/api/wake-word")
async def update_wake_word(request: dict):
    """Save wake-word settings and (re)start detection when enabled."""
    # reload_config must be imported here: it is what clears the lru_cache on
    # get_config(), and without it every save of the wake-word settings died
    # with a NameError (HTTP 500) - the settings silently never applied.
    from config import save_config, reload_config

    enabled = request.get("enabled")
    phrase = request.get("phrase")
    model = request.get("model")
    device = request.get("input_device")
    cooldown = request.get("cooldown")
    threshold = request.get("match_threshold")

    for name, value, kind in (
        ("phrase", phrase, str), ("model", model, str),
        ("input_device", device, str),
    ):
        if value is not None and not isinstance(value, kind):
            raise HTTPException(status_code=400, detail=f"{name} должен быть строкой")
    if device is not None and len(device) > 200:
        raise HTTPException(status_code=400, detail="Слишком длинное имя устройства")
    if phrase is not None and len(phrase) > 64:
        raise HTTPException(status_code=400, detail="Фраза длиннее 64 символов")
    if model is not None and model not in ("tiny", "base"):
        raise HTTPException(status_code=400, detail="Модель: только tiny или base")
    if cooldown is not None and not (0 <= float(cooldown) <= 300):
        raise HTTPException(status_code=400, detail="Кулдаун: от 0 до 300 секунд")
    if threshold is not None and not (0.1 <= float(threshold) <= 1.0):
        raise HTTPException(status_code=400, detail="Порог: от 0.1 до 1.0")
    if enabled is True and not (phrase or "").strip():
        raise HTTPException(
            status_code=400,
            detail="Укажите пробуждающую фразу, чтобы включить её",
        )

    save_config(
        wake_enabled=enabled, wake_phrase=phrase, wake_model=model,
        wake_input_device=device, wake_cooldown=cooldown, wake_threshold=threshold,
    )
    # The file is not enough: get_config() is cached, and OS env vars take
    # priority over the file - save_config mirrors both, so just re-read.
    reload_config()

    ok, err = _wake_start()
    return {"status": "ok", "listening": ok, "error": err}


# === API endpoints ===

@app.get("/api/chats")
async def get_all_chats():
    """Get the list of all chats."""
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
    """Create new chat."""
    try:
        lang = get_config().general.language
    except Exception:
        lang = "en"
    default_title = "Новый чат" if lang == "ru" else "New chat"
    title = request.get("title", default_title)
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
    """Update chat (rename)."""
    title = request.get("title")
    if title:
        await _db.update_chat_title(chat_id, title)
    chat = await _db.get_chat(chat_id)
    if not chat:
        try:
            lang = get_config().general.language
        except Exception:
            lang = "en"
        raise HTTPException(status_code=404, detail=t("api.chat_not_found", lang=lang))
    return {
        "id": chat.id,
        "title": chat.title,
        "created_at": chat.created_at,
        "updated_at": chat.updated_at,
    }


@app.get("/api/chats/{chat_id}/messages")
async def get_chat_messages(chat_id: int):
    """Get chat messages."""
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
    """Delete chat."""
    deleted = await _db.delete_chat(chat_id)
    if not deleted:
        try:
            lang = get_config().general.language
        except Exception:
            lang = "en"
        raise HTTPException(status_code=404, detail=t("api.chat_not_found", lang=lang))
    return {"status": "ok"}


@app.delete("/api/chats/{chat_id}/messages")
async def clear_chat_messages(chat_id: int):
    """Clear chat messages."""
    await _db.clear_chat_history(chat_id)
    return {"status": "ok"}


@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    """Upload a file (document or image) and extract data."""
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
        try:
            lang = get_config().general.language
        except Exception:
            lang = "en"
        raise HTTPException(status_code=400, detail=t("api.unsupported_format", lang=lang, type=file.content_type))
    
    try:
        content = await file.read()
        
        # Handle images — encode to base64
        if file.content_type in image_types:
            import base64
            import io
            from PIL import Image
            
            # Open the image to get its dimensions
            img = Image.open(io.BytesIO(content))
            width, height = img.size
            
            # Optionally: resize large images (max 1024px on the longer side)
            max_dim = 1024
            if max(width, height) > max_dim:
                ratio = max_dim / max(width, height)
                new_size = (int(width * ratio), int(height * ratio))
                img = img.resize(new_size, Image.Resampling.LANCZOS)
                # Save back to bytes
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
        
        # Documents — save to a temp file and extract text
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
        logger.error(f"File upload error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/chat", response_model=ChatResponseMessage)
async def chat(request: ChatMessage):
    """
    Send message and get AI response.

    Main endpoint for chat with assistant.

    Args:
        request: Message and optional chat ID.

    Returns:
        ChatResponseMessage: Assistant response and chat ID.
    """
    if not _assistant:
        try:
            lang = get_config().general.language
        except Exception:
            lang = "en"
        raise HTTPException(
            status_code=503,
            detail=assistant_not_init_detail(lang),
        )

    # Create new chat if not specified
    chat_id = request.chat_id
    if not chat_id:
        try:
            lang = get_config().general.language
        except Exception:
            lang = "en"
        default_title = "Новый диалог" if lang == "ru" else "New chat"
        chat_id = await _db.create_chat(default_title)

    # Save user message
    await _db.add_message(chat_id, "user", request.message)

    # Load chat history for context (last 30 messages, without duplicate current)
    history_messages = await _db.get_chat_history(chat_id)
    # Exclude last message (current user), as it's already passed as user_message separately
    if history_messages and history_messages[-1].role == "user" and history_messages[-1].content == request.message:
        history_messages = history_messages[:-1]
    # Limit history to not bloat prompt (57 messages -> 1968 tokens, was slow)
    MAX_HISTORY = 30
    if len(history_messages) > MAX_HISTORY:
        history_messages = history_messages[-MAX_HISTORY:]
    chat_history = [
        {"role": msg.role, "content": msg.content}
        for msg in history_messages
        if msg.role in ("user", "assistant")
    ]

    # For LM Studio — follow the loaded model, but never swap away from a model
    # the user configured that IS loaded (see pick_lmstudio_model). Cached 30s.
    if _config and _config.llm.provider.value == "lm_studio" and _assistant and _assistant._llm:
        current = _assistant._llm._config.model
        loaded = await get_lmstudio_loaded_models()
        target = pick_lmstudio_model(current, loaded)
        if target and target != current:
            logger.info(f"Replacing model {current} -> {target} (loaded in LM Studio)")
            _assistant._llm._config.model = target

    # Get response from assistant
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
        import dataclasses as _dataclasses
        actions = [
            _dataclasses.asdict(a) for a in getattr(llm_response, "actions", []) or []
        ]
    except Exception as e:
        logger.error(f"Error generating response: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    # Save assistant response
    await _db.add_message(chat_id, "assistant", response_text)

    # Send event via WebSocket
    logger.info(f"Sending WebSocket event: chat_id={chat_id}, content={response_text[:50]}...")
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
        actions=actions,
    )


_cached_lm_models: list[str] | None = None
_cached_lm_model_time: float = 0.0

async def get_lmstudio_loaded_models() -> list[str]:
    """IDs of every model currently loaded in LM Studio (30s cache)."""
    global _cached_lm_models, _cached_lm_model_time
    import time
    now = time.monotonic()
    if _cached_lm_models is not None and (now - _cached_lm_model_time) < 30.0:
        return _cached_lm_models
    try:
        cfg = get_config().llm
        if cfg.provider.value != "lm_studio":
            return []
        import httpx
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(f"{cfg.host}/api/v0/models")
            if resp.status_code == 200:
                loaded = [
                    m.get("id")
                    for m in resp.json().get("data", [])
                    if m.get("state") == "loaded" and m.get("id")
                ]
                _cached_lm_models = loaded
                _cached_lm_model_time = now
                return loaded
    except Exception:
        pass
    return []

async def get_lmstudio_loaded_model() -> str | None:
    """First model loaded in LM Studio, or None. Used for status display."""
    loaded = await get_lmstudio_loaded_models()
    return loaded[0] if loaded else None

async def get_effective_context_length() -> int:
    """Return the context limit from the config (for LM Studio — also from .env, no extra requests)."""
    cfg = get_config().llm
    return int(getattr(cfg, 'num_ctx', 8192))


@app.get("/api/status")
async def get_status():
    """
    Get the service status.
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
        "assistant_ready": _assistant is not None,
        "provider": _config.llm.provider.value if _config else "unknown",
        "model": _config.llm.model if _config else "unknown",
        "supports_thinking": thinking_supported,
        "loaded_context_length": effective_ctx,
        "max_context_length": effective_ctx,
        **stats,
    }


@app.get("/api/config")
async def get_current_config():
    """Get the current configuration. For LM Studio — returns the actually loaded model."""
    if not _config:
        return {
            "provider": "ollama", "model": "", "ollama_host": "http://localhost:11434",
            "api_key": "", "num_ctx": 8192, "temperature": 0.7,
            "tts_steps": 64, "tts_temperature": 1.0,
            "memory_max_context": 20, "memory_search_results": 3, "memory_threshold": 0.3,
            "language": "en",
            "show_backend_console": False,
            "personality_ru": "", "personality_en": "",
            "stt_model": "large-v3-turbo",
            "hotkey_voice": "Ctrl+Shift+V", "hotkey_voice_num": "Ctrl+Num0",
            "hotkey_live": "Ctrl+Shift+L",
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
        "language": _config.general.language,
        "show_backend_console": _config.general.show_backend_console,
        "personality_ru": _config.personality.ru,
        "personality_en": _config.personality.en,
        "stt_model": _config.stt.model,
        "hotkey_voice": _config.hotkey.voice,
        "hotkey_voice_num": _config.hotkey.voice_num,
        "hotkey_live": _config.hotkey.live,
    }


@app.put("/api/config")
async def update_config(request: dict):
    """Update the configuration (saved to the .env file). Applies without restart (hot-swap); the LM Studio model itself is switched in LM Studio."""
    from config import get_config, save_config, reload_config
    
    # Use None as default for partial updates (e.g. language-only from i18n.js)
    provider = request.get("provider")
    model = request.get("model")
    ollama_host = request.get("ollama_host")
    api_key = request.get("api_key")
    num_ctx = request.get("num_ctx")
    temperature = request.get("temperature")
    tts_steps = request.get("tts_steps")
    tts_temperature = request.get("tts_temperature")
    memory_max_context = request.get("memory_max_context")
    memory_search_results = request.get("memory_search_results")
    memory_threshold = request.get("memory_threshold")
    language = request.get("language")
    show_backend_console = request.get("show_backend_console")
    if show_backend_console is not None:
        show_backend_console = bool(show_backend_console)
        if isinstance(request.get("show_backend_console"), str):
            show_backend_console = request.get("show_backend_console").lower() == "true"

    personality_ru = request.get("personality_ru")
    personality_en = request.get("personality_en")
    stt_model = request.get("stt_model")
    hotkey_voice = request.get("hotkey_voice")
    hotkey_voice_num = request.get("hotkey_voice_num")
    hotkey_live = request.get("hotkey_live")
    for name, val in (("personality_ru", personality_ru), ("personality_en", personality_en)):
        if val is not None and not isinstance(val, str):
            raise HTTPException(status_code=400, detail=f"{name} must be a string")
        if isinstance(val, str) and len(val) > 8000:
            raise HTTPException(status_code=400, detail=f"{name} is too long (max 8000 chars)")

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
        language=language,
        show_backend_console=show_backend_console,
        personality_ru=personality_ru,
        personality_en=personality_en,
        stt_model=stt_model,
        hotkey_voice=hotkey_voice,
        hotkey_voice_num=hotkey_voice_num,
        hotkey_live=hotkey_live,
    )
    # Hot-swap without restart
    try:
        new_cfg = reload_config()
        global _config
        _config = new_cfg
        if _assistant:
            _assistant._config = new_cfg
            if _assistant._llm:
                _assistant._llm._config = new_cfg.llm
                # Recreate http client with new host/api_key if changed
                try:
                    await _assistant._llm.close()
                except:
                    pass
                _assistant._llm._initialized = False
                await _assistant._llm.initialize()
                # Refresh language-aware system prompt and tool definitions
                try:
                    if hasattr(_assistant._llm, "refresh_system_prompt"):
                        _assistant._llm.refresh_system_prompt()
                    # Refresh DDG tool def for new language
                    _lang = new_cfg.general.language
                    try:
                        from src.web_search import DDG_TOOL_DEFINITION, DDG_TOOL_DEFINITION_EN
                        _assistant._ddg_tool_def = DDG_TOOL_DEFINITION if _lang == "ru" else DDG_TOOL_DEFINITION_EN
                    except ImportError:
                        pass
                except Exception:
                    pass
    except Exception as e:
        logger.warning(f"Hot-swap config failed: {e}")

    try:
        lang = get_config().general.language
    except Exception:
        lang = "en"
    return {"status": "ok", "message": t("api.config_saved", lang=lang)}


@app.post("/api/tts/toggle")
async def toggle_tts(request: Request):
    """
    Toggle TTS (OmniVoice) on/off.
    
    Accepts raw JSON bool (true/false) or object {"enabled": true}.
    When enabled=True - loads OmniVoice into memory.
    When enabled=False - unloads OmniVoice from memory.
    """
    if not _assistant:
        try:
            lang = get_config().general.language
        except Exception:
            lang = "en"
        raise HTTPException(status_code=503, detail=assistant_not_init_detail(lang))
    
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
    
    loaded = _assistant._tts.is_omnivoice_loaded if enabled else False
    return {
        "status": "ok",
        "enabled": enabled,
        "omnivoice_loaded": loaded,
        "error": _assistant._tts.last_error if enabled and not loaded else None,
    }


@app.get("/api/tts/status")
async def get_tts_status():
    """Get the TTS status."""
    if not _assistant or not _assistant._tts:
        return {"enabled": False, "omnivoice_loaded": False}
    
    return {
        "enabled": True,
        "omnivoice_loaded": _assistant._tts.is_omnivoice_loaded,
    }


@app.post("/api/tts/config")
async def tts_config(request: dict):
    """
    Configure TTS voice parameters.

    Parameters:
    - instruct: voice description (female, male, female russian, etc.)
    - position_temperature: 0 = stable, higher = more random
    - class_temperature: 0 = stable, higher = more random
    """
    if not _assistant or not _assistant._tts:
        try:
            lang = get_config().general.language
        except Exception:
            lang = "en"
        raise HTTPException(status_code=503, detail=t("api.tts_not_init", lang=lang))
    
    mode = request.get("mode", "instruct")  # "instruct" or "clone"
    instruct = request.get("instruct", "female")
    ref_audio = request.get("ref_audio", None)  # path to reference file
    position_temp = request.get("position_temperature", 0.0)
    class_temp = request.get("class_temperature", 0.0)
    
    # Save config in TTSEngine (facade)
    _assistant._tts.set_voice_config(
        mode=mode,
        instruct=instruct,
        ref_audio=ref_audio,
        position_temperature=position_temp,
        class_temperature=class_temp,
    )
    
    # If OmniVoice already loaded - apply config immediately
    if _assistant._tts.is_omnivoice_loaded and hasattr(_assistant._tts._engine, 'set_voice_config'):
        _assistant._tts._engine.set_voice_config(
            mode=mode,
            instruct=instruct,
            ref_audio=ref_audio,
            position_temperature=position_temp,
            class_temperature=class_temp,
        )
        logger.info(f"Config applied to already loaded OmniVoice: mode={mode}, ref={ref_audio}")
    
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
    """Get the list of available voices for cloning."""
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
    """Get the current TTS configuration."""
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
    Synthesize speech from text and return audio.
    """
    if not _assistant or not _assistant._tts:
        try:
            lang = get_config().general.language
        except Exception:
            lang = "en"
        raise HTTPException(status_code=503, detail=t("api.tts_not_init", lang=lang))
    
    text = request.get("text", "")
    if not text:
        try:
            lang = get_config().general.language
        except Exception:
            lang = "en"
        raise HTTPException(status_code=400, detail=t("api.text_not_provided", lang=lang))
    
    # Check OmniVoice loaded
    if not _assistant._tts.is_omnivoice_loaded:
        # Try to load (honor the result - a failed load must not fall through to the dummy)
        if not await _assistant._tts.enable_omnivoice() or not _assistant._tts.is_omnivoice_loaded:
            try:
                lang = get_config().general.language
            except Exception:
                lang = "en"
            raise HTTPException(status_code=500, detail=t("api.tts_not_init", lang=lang))

    # Synthesize
    result = await _assistant._tts.speak(text)
    
    if not result.success:
        try:
            lang = get_config().general.language
        except Exception:
            lang = "en"
        raise HTTPException(status_code=500, detail=result.error or t("api.synthesis_error", lang=lang))
    
    # Return the audio
    from fastapi.responses import Response
    return Response(
        content=result.audio_data,
        media_type="audio/wav",
        headers={"Content-Disposition": "inline"},
    )


# === Personas ===

@app.get("/api/personas")
async def get_personas():
    """List the persona catalog and the active selection."""
    from src import personas as P
    data = P.load()
    return {
        "personas": [asdict(p) for p in data.personas],
        "active": data.active_id,
        "exists": data.exists,
        "error": data.parse_error,
    }


@app.put("/api/personas")
async def update_personas(request: dict):
    """Replace the persona catalog and the active selection."""
    from src import personas as P
    from dataclasses import asdict

    items = request.get("personas")
    if not isinstance(items, list):
        raise HTTPException(status_code=400, detail="personas must be a list")

    try:
        raw = [Persona(**i) if isinstance(i, dict) and "id" in i else i for i in items]
    except TypeError as e:
        raise HTTPException(status_code=400, detail=f"Malformed persona entry: {e}")

    clean, active, errors = P.validate(raw, request.get("active"))
    saved = P.save(P.PersonasFile(personas=clean, active_id=active))
    if not saved:
        raise HTTPException(status_code=500, detail="Cannot write personas.json")

    if _assistant is not None:
        _reapply_active_persona()
    return {"status": "ok", "personas": [asdict(p) for p in clean],
            "active": active, "warnings": errors}


@app.post("/api/personas/activate")
async def activate_persona(request: dict):
    """Switch the active persona at runtime (id or null for the default prompt)."""
    from src import personas as P

    pid = request.get("id")
    pid = str(pid).strip().lower() if isinstance(pid, str) and pid.strip() else None

    data = P.load()
    persona = None
    if pid is not None:
        persona = next((p for p in data.personas if p.id == pid), None)
        if persona is None:
            raise HTTPException(status_code=404, detail=f"Persona '{pid}' not found")

    data.active_id = persona.id if persona else None
    P.save(data)

    if _assistant is not None:
        _assistant.apply_persona(persona)

    return {"status": "ok", "active": data.active_id,
            "persona": asdict(persona) if persona else None}


def _reapply_active_persona() -> None:
    """Re-apply the saved persona after the catalog changed."""
    from src import personas as P
    try:
        persona = P.resolve_active(P.load())
        if _assistant is not None:
            _assistant.apply_persona(persona)
    except Exception as e:
        logger.warning(f"Cannot apply persona: {e}")


# === Avatars ===

AVATARS_DIR = Path(__file__).parent.parent / "avatars"
AVATAR_MAX_SIZE = 5 * 1024 * 1024
AVATAR_MAX_DIM = 128
AVATAR_ALLOWED_TYPES = ["image/png", "image/jpeg", "image/jpg", "image/webp", "image/gif"]
_AVATAR_NAME_RE = re.compile(r"^[A-Za-z0-9_.\-]+$")


def _validate_avatar_name(name: str) -> str:
    """Reject anything that could escape the avatars folder."""
    if not name or not _AVATAR_NAME_RE.match(name) or ".." in name:
        raise HTTPException(status_code=400, detail="Invalid avatar name")
    return name


def _avatar_path(name: str) -> Path:
    return AVATARS_DIR / _validate_avatar_name(name)


@app.get("/api/avatars")
async def list_avatars():
    """List uploaded avatars."""
    if not AVATARS_DIR.exists():
        return {"avatars": []}
    items = []
    for f in sorted(AVATARS_DIR.iterdir()):
        if f.is_file() and _AVATAR_NAME_RE.match(f.name):
            items.append({"name": f.name, "url": f"/api/avatars/{f.name}"})
    return {"avatars": items}


@app.post("/api/avatars")
async def upload_avatar(file: UploadFile = File(...)):
    """Upload an avatar image (resized to a small square)."""
    if file.content_type not in AVATAR_ALLOWED_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported image type: {file.content_type}. Use PNG, JPG, WEBP or GIF",
        )

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty file")
    if len(data) > AVATAR_MAX_SIZE:
        raise HTTPException(status_code=400, detail="Image is too large (max 5 MB)")

    if Image is None:
        raise HTTPException(status_code=500, detail="Pillow is not installed")

    import io
    import uuid

    try:
        img = Image.open(io.BytesIO(data))
        img = img.convert("RGBA")
        # Center-crop to a square, then downscale
        w, h = img.size
        side = min(w, h)
        img = img.crop(((w - side) // 2, (h - side) // 2,
                        (w - side) // 2 + side, (h - side) // 2 + side))
        img = img.resize((AVATAR_MAX_DIM, AVATAR_MAX_DIM), Image.Resampling.LANCZOS)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Cannot read image: {e}")

    AVATARS_DIR.mkdir(parents=True, exist_ok=True)
    name = f"avatar_{uuid.uuid4().hex[:12]}.png"
    img.save(AVATARS_DIR / name, format="PNG")
    logger.info(f"Avatar saved: {name}")
    return {"status": "ok", "name": name, "url": f"/api/avatars/{name}"}


@app.get("/api/avatars/{name}")
async def get_avatar(name: str):
    """Serve an avatar image file."""
    from fastapi.responses import FileResponse
    path = _avatar_path(name)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Avatar not found")
    return FileResponse(path)


@app.delete("/api/avatars/{name}")
async def delete_avatar(name: str):
    """Delete an uploaded avatar."""
    path = _avatar_path(name)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Avatar not found")
    try:
        path.unlink()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Cannot delete avatar: {e}")
    return {"status": "ok"}


@app.get("/api/models")
async def get_models(provider: str = "ollama", host: str = "http://localhost:11434"):
    """Get the model list for a provider."""
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
            # Respect the host parameter (same as for Ollama)
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
        # OpenRouter has no simple API for listing models
        # Use popular default models
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
    """Load a model in the provider (LM Studio: POST /api/v1/models/load). Unloads the previous one if needed."""
    provider = request.get("provider", "lm_studio")
    model = request.get("model", "")
    host = request.get("host", "http://localhost:1234")
    context_length = request.get("context_length") or request.get("num_ctx")

    if not model:
        try:
            lang = get_config().general.language
        except Exception:
            lang = "en"
        raise HTTPException(status_code=400, detail=t("api.model_not_specified", lang=lang))

    if provider == "lm_studio":
        base = host.rstrip("/") if host else "http://localhost:1234"
        if not base.startswith("http"):
            base = "http://" + base
        # Unload previously loaded models (to avoid accumulating :2, :3 instances)
        # Logic: if same model with same context already loaded — do nothing,
        # otherwise unload all loaded (especially same model with different context)
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
                    # Check if already loaded with the same context
                    already_ok = False
                    for m in data.get("data", []):
                        if m.get("state") == "loaded" and m.get("id") == model:
                            loaded_ctx = m.get("loaded_context_length")
                            if target_ctx is None or loaded_ctx == target_ctx:
                                already_ok = True
                                break
                    if already_ok:
                        logger.info(f"Model {model} already loaded with context {target_ctx}, skipping unload")
                    else:
                        # Unload all loaded (both same model with different context and other models)
                        for m in data.get("data", []):
                            if m.get("state") == "loaded":
                                inst_id = m.get("id")
                                # Do not unload target if already loaded with correct context (checked above)
                                # Otherwise unload all
                                try:
                                    await client.post(f"{base}/api/v1/models/unload", json={"instance_id": inst_id}, timeout=10.0)
                                    logger.info(f"Unloaded previous model: {inst_id}")
                                except Exception as ue:
                                    logger.debug(f"Failed to unload {inst_id}: {ue}")
        except Exception as e:
            logger.debug(f"Error unloading old models: {e}")

        payload = {"model": model}
        if context_length:
            try:
                payload["context_length"] = int(context_length)
            except:
                pass
        # Try to load
        try:
            import httpx
            async with httpx.AsyncClient(timeout=90.0) as client:
                resp = await client.post(f"{base}/api/v1/models/load", json=payload)
                if resp.status_code in (200, 204):
                    return {"ok": True, "provider": provider, "model": model, "context_length": context_length}
                # LM Studio may return 400 if already loaded — treat as ok
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
        # Ollama loads lazily, no separate command needed — hot-swap via payload.model
        return {"ok": True, "provider": provider, "model": model, "jit": True}
    else:
        return {"ok": True, "provider": provider, "model": model}


# === STT (Speech-to-Text) ===

def _dump_failed_audio(audio_data: bytes | None, reason: str) -> None:
    """Best-effort dump of audio that failed STT (for diagnostics)."""
    try:
        if not audio_data:
            return
        from datetime import datetime
        debug_dir = Path(__file__).parent.parent / "debug_tts"
        debug_dir.mkdir(parents=True, exist_ok=True)
        name = f"stt_fail_{reason}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.webm"
        (debug_dir / name).write_bytes(audio_data)
        logger.info(f"Failed STT audio dumped: {name} ({len(audio_data)} bytes)")
    except Exception as e:
        logger.debug(f"Failed to dump audio: {e}")


_stt_engine = None

async def get_stt_engine():
    """Get or create the STT engine."""
    global _stt_engine
    if _stt_engine is None:
        from src.stt_engine import get_stt_engine
        _stt_engine = get_stt_engine()
        await _stt_engine.initialize()
    return _stt_engine


@app.post("/api/stt")
async def stt_transcribe(file: UploadFile = File(...)):
    """
    Recognize speech from an audio file.

    Accepts an audio file (webm, wav, mp3) and returns the recognized text.
    """
    logger.info(f"Received audio file: {file.filename}, type: {file.content_type}")
    
    # Check format
    allowed_types = ["audio/webm", "audio/wav", "audio/wave", "audio/x-wav", "audio/mp3", "audio/mpeg", "audio/ogg", "audioopus"]
    if file.content_type not in allowed_types:
        try:
            lang = get_config().general.language
        except Exception:
            lang = "en"
        raise HTTPException(
            status_code=400,
            detail=t("api.unsupported_format", lang=lang, type=file.content_type)
        )

    # Read audio first so empty recordings fail fast with 422 (not 500)
    audio_data = await file.read()
    if not audio_data or len(audio_data) < 1024:
        try:
            lang = get_config().general.language
        except Exception:
            lang = "en"
        raise HTTPException(
            status_code=422,
            detail=t("api.empty_audio", lang=lang),
        )

    try:
        # Initialize STT if needed
        stt = await get_stt_engine()

        # Determine format
        ext = file.filename.split(".")[-1] if "." in file.filename else "webm"

        # Recognize
        logger.info("Starting recognition...")
        text = await stt.transcribe_bytes(audio_data, format=ext)

        logger.info(f"Recognized: {text[:100]}...")

        return {"text": text, "success": True}

    except ValueError as e:
        # Bad audio data (empty/silence after decoding) - client-side problem
        logger.warning(f"STT rejected audio: {e}")
        _dump_failed_audio(audio_data, "rejected")
        try:
            lang = get_config().general.language
        except Exception:
            lang = "en"
        raise HTTPException(status_code=422, detail=t("api.recognition_error", lang=lang, detail=str(e) or "invalid audio"))
    except Exception as e:
        logger.error(f"STT error: {e}", exc_info=True)
        _dump_failed_audio(audio_data, "error")
        # If error empty — show repr and traceback for diagnostics
        # (type name first so OSError vs RuntimeError vs OOM are distinguishable in UI)
        detail = f"{type(e).__name__}: {e}" if str(e) else (repr(e) or e.__class__.__name__)
        if not detail.strip():
            import traceback
            detail = traceback.format_exc()[-500:]
        try:
            lang = get_config().general.language
        except Exception:
            lang = "en"
        raise HTTPException(status_code=500, detail=t("api.recognition_error", lang=lang, detail=detail))


# === Entrypoint ===

if __name__ == "__main__":
    import uvicorn
    
    # Run with host check disabled for WebSocket
    uvicorn.run(
        app,
        host="0.0.0.0",  # Listen on all interfaces
        port=8000,
        reload=False,
        ws_ping_interval=None,  # Disable ping for stability
        ws_ping_timeout=None,
    )
