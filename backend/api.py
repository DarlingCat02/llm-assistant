"""
API роуты для FastAPI приложения.

Модуль содержит все API эндпоинты, разделённые по категориям:
- Chat: управление чатами
- Memory: управление памятью (ChromaDB)
- Voice: голосовой ввод (будущее)

Архитектурные решения:
1. API-first: эндпоинты готовы к вызовам из любых клиентов
2. WebSocket для real-time событий
3. Подготовка к масштабированию (роуты разделены по тегам)
"""

import logging
from datetime import datetime
from typing import Optional, Annotated

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect, Depends
from pydantic import BaseModel, Field

from backend.database import ChatDatabase, Chat, Message

try:
    from src.i18n import t
except ImportError:
    try:
        from i18n import t
    except ImportError:
        def t(key, lang=None, **kwargs):
            return key
try:
    from config import get_config
except ImportError:
    def get_config():
        class _Cfg:
            class general:
                language = "en"
        return _Cfg()


# Global function to get DB (will be set from main.py)
_db_getter = None

def get_db():
    """Get DB via global getter."""
    if _db_getter is None:
        try:
            lang = get_config().general.language
        except Exception:
            lang = "en"
        raise HTTPException(status_code=503, detail=t("api.db_not_init", lang=lang))
    return _db_getter()

def set_db_getter(getter):
    """Установить getter для БД."""
    global _db_getter
    _db_getter = getter


logger = logging.getLogger(__name__)


# === Pydantic модели для API ===

class ChatCreate(BaseModel):
    """Модель создания чата."""
    title: str = Field(default="Новый чат", min_length=1, max_length=100)


class ChatResponse(BaseModel):
    """Модель ответа чата."""
    id: int
    title: str
    created_at: datetime
    updated_at: datetime
    
    model_config = {"from_attributes": True}


class MessageCreate(BaseModel):
    """Модель создания сообщения."""
    content: str = Field(..., min_length=1, max_length=10000)
    role: str = Field(..., pattern="^(user|assistant)$")


class MessageResponse(BaseModel):
    """Модель ответа сообщения."""
    id: int
    chat_id: int
    role: str
    content: str
    created_at: datetime
    
    model_config = {"from_attributes": True}


class ChatMessage(BaseModel):
    """Модель сообщения для чата (API запрос)."""
    message: str = Field(..., min_length=1, max_length=10000)
    chat_id: Optional[int] = None
    thinking: bool = Field(default=False, description="Включить режим рассуждения")
    search: str = Field(default="", description="Провайдер поиска: ddg / searxng")
    images: list[str] = Field(default_factory=list, description="Список base64-encoded изображений")


class ChatResponseMessage(BaseModel):
    """Модель ответа на сообщение чата."""
    response: str
    chat_id: int
    message_id: int
    used_context_tokens: int = 0
    max_context_tokens: int = 8192


class MemoryEntry(BaseModel):
    """Модель записи памяти."""
    id: str
    text: str
    score: float = 0.0
    metadata: dict = Field(default_factory=dict)


class MemorySearchRequest(BaseModel):
    """Модель запроса для поиска в памяти."""
    query: str = Field(..., min_length=1, max_length=10000)
    limit: int = Field(default=10, ge=1, le=100)


class MemoryAddRequest(BaseModel):
    """Модель запроса для добавления записи в память."""
    text: str = Field(..., min_length=1, max_length=10000)
    entry_type: str = Field(default="user_fact", pattern="^[a-z_]+$")


# === Роуты для памяти ===

memory_router = APIRouter(prefix="/api/memory", tags=["Memory"])


@memory_router.get("")
async def get_memory_entries(
    limit: int = 50,
):
    """
    Получить все записи из памяти.
    """
    from backend.main import get_assistant
    assistant = get_assistant()
    
    if not assistant or not assistant._memory:
        return {"entries": [], "total": 0}

    # Получаем все записи через поиск с пустым запросом
    entries = await assistant._memory.search("", limit=limit, min_similarity=0.0)

    return {
        "entries": [
            {
                "id": e.id,
                "text": e.text,
                "score": e.score,
                "metadata": e.metadata,
            }
            for e in entries
        ],
        "total": len(entries),
    }


@memory_router.post("")
async def add_memory_entry(
    request: MemoryAddRequest,
):
    """
    Добавить запись в память вручную.
    """
    from backend.main import get_assistant
    assistant = get_assistant()
    
    if not assistant or not assistant._memory:
        try:
            lang = get_config().general.language
        except Exception:
            lang = "en"
        raise HTTPException(status_code=503, detail=t("api.memory_not_available", lang=lang))

    saved = await assistant._memory.save(
        text=request.text,
        entry_type=request.entry_type,
    )

    if not saved:
        try:
            lang = get_config().general.language
        except Exception:
            lang = "en"
        return {"status": "skipped", "message": t("api.duplicate", lang=lang)}

    try:
        lang = get_config().general.language
    except Exception:
        lang = "en"
    return {"status": "ok", "message": t("api.added", lang=lang)}


@memory_router.post("/search")
async def search_memory(
    request: MemorySearchRequest,
):
    """
    Поиск в памяти по запросу.
    """
    from backend.main import get_assistant
    assistant = get_assistant()
    
    if not assistant or not assistant._memory:
        return {"query": request.query, "results": []}
    
    entries = await assistant._memory.search(
        request.query,
        limit=request.limit,
    )
    
    return {
        "query": request.query,
        "results": [
            {
                "id": e.id,
                "text": e.text,
                "score": e.score,
                "metadata": e.metadata,
            }
            for e in entries
        ],
    }


@memory_router.delete("/{entry_id}")
async def delete_memory_entry(
    entry_id: str,
):
    """
    Удалить запись из памяти.
    """
    from backend.main import get_assistant
    assistant = get_assistant()
    
    if not assistant or not assistant._memory:
        try:
            lang = get_config().general.language
        except Exception:
            lang = "en"
        raise HTTPException(status_code=503, detail=t("api.memory_not_available", lang=lang))

    deleted = await assistant._memory._storage.delete(entry_id)

    if not deleted:
        try:
            lang = get_config().general.language
        except Exception:
            lang = "en"
        raise HTTPException(status_code=404, detail=t("api.not_found", lang=lang))

    try:
        lang = get_config().general.language
    except Exception:
        lang = "en"
    return {"status": "ok", "message": t("api.deleted", lang=lang, id=entry_id)}


# === WebSocket для real-time событий ===

class ConnectionManager:
    """Менеджер WebSocket подключений."""

    def __init__(self):
        self._connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        """Accept connection."""
        # FastAPI checks origin, so accept with explicit allow
        try:
            # Check origin - allow all for local dev
            origin = websocket.headers.get("origin")
            logger.debug(f"WebSocket connection with origin: {origin}")
            await websocket.accept()
            self._connections.append(websocket)
            logger.info(f"WebSocket connected. Total connections: {len(self._connections)}")
        except Exception as e:
            logger.warning(f"Failed to accept WebSocket connection: {e}")
            raise

    def disconnect(self, websocket: WebSocket):
        """Disconnect client."""
        if websocket in self._connections:
            self._connections.remove(websocket)
        logger.info(f"WebSocket disconnected. Total connections: {len(self._connections)}")

    async def broadcast(self, message: dict):
        """
        Отправить сообщение всем подключённым клиентам.

        Args:
            message: Словарь для отправки (будет сериализован в JSON).
        """
        disconnected = []
        for connection in self._connections:
            try:
                await connection.send_json(message)
            except Exception:
                disconnected.append(connection)
        
        # Удаляем отключённых клиентов
        for conn in disconnected:
            self.disconnect(conn)

    async def send_personal(self, websocket: WebSocket, message: dict):
        """
        Send message to specific client.

        Args:
            websocket: Client connection.
            message: Dict to send.
        """
        try:
            await websocket.send_json(message)
        except Exception as e:
            logger.warning(f"Failed to send message: {e}")


manager = ConnectionManager()

# WebSocket роут перенесён в main.py для обхода проверки origin

