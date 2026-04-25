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


# Глобальная функция для получения БД (будет установлена из main.py)
_db_getter = None

def get_db():
    """Получить БД через глобальный getter."""
    if _db_getter is None:
        raise HTTPException(status_code=503, detail="База данных не инициализирована")
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


class ChatResponseMessage(BaseModel):
    """Модель ответа на сообщение чата."""
    response: str
    chat_id: int
    message_id: int


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


class VoiceRequest(BaseModel):
    """Модель запроса для голосового ввода."""
    text: str = Field(default="", max_length=10000)
    chat_id: Optional[int] = None


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
        raise HTTPException(status_code=503, detail="Память не доступна")

    saved = await assistant._memory.save(
        text=request.text,
        entry_type=request.entry_type,
    )

    if not saved:
        return {"status": "skipped", "message": "Дубликат записи"}

    return {"status": "ok", "message": "Запись добавлена"}


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
        raise HTTPException(status_code=503, detail="Память не доступна")

    deleted = await assistant._memory._storage.delete(entry_id)

    if not deleted:
        raise HTTPException(status_code=404, detail="Запись не найдена")

    return {"status": "ok", "message": f"Запись {entry_id} удалена"}


# === Роуты для голоса (будущее) ===

voice_router = APIRouter(prefix="/api/voice", tags=["Voice"])


@voice_router.post("")
async def voice_input(
    request: VoiceRequest,
    assistant=None,  # Будет injected
):
    """
    Обработать голосовой ввод.
    
    TODO: Реализовать когда будет voice_service.py
    """
    raise HTTPException(
        status_code=501,
        detail="Голосовой ввод пока не реализован",
    )


# === WebSocket для real-time событий ===

class ConnectionManager:
    """Менеджер WebSocket подключений."""

    def __init__(self):
        self._connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        """Принять подключение."""
        # FastAPI проверяет origin, поэтому принимаем с явным разрешением
        try:
            # Проверяем origin - разрешаем все для локальной разработки
            origin = websocket.headers.get("origin")
            logger.debug(f"WebSocket подключение с origin: {origin}")
            await websocket.accept()
            self._connections.append(websocket)
            logger.info(f"WebSocket подключён. Всего подключений: {len(self._connections)}")
        except Exception as e:
            logger.warning(f"Не удалось принять WebSocket подключение: {e}")
            raise

    def disconnect(self, websocket: WebSocket):
        """Отключить клиента."""
        if websocket in self._connections:
            self._connections.remove(websocket)
        logger.info(f"WebSocket отключён. Всего подключений: {len(self._connections)}")

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
        Отправить сообщение конкретному клиенту.

        Args:
            websocket: Подключение клиента.
            message: Словарь для отправки.
        """
        try:
            await websocket.send_json(message)
        except Exception as e:
            logger.warning(f"Не удалось отправить сообщение: {e}")


manager = ConnectionManager()

# WebSocket роут перенесён в main.py для обхода проверки origin
# @voice_router.websocket("/ws/events") - удалено
