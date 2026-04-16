"""
FastAPI бэкенд для Local AI Assistant.

Основное приложение, которое:
1. Предоставляет REST API для всех функций ассистента
2. Раздаёт статический фронтенд
3. Поддерживает WebSocket для real-time событий

Архитектурные решения:
1. API-first: бэкенд работает независимо от фронтенда
2. CORS настроен для будущих внешних клиентов
3. Подготовка к голосовому сервису (отдельный клиент API)

Запуск:
    uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
"""

import logging
import sys
from pathlib import Path
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request, HTTPException, Depends, WebSocket
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware

# Добавляем родительскую директорию в path для импортов
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import get_config, Config
from backend.database import ChatDatabase
from backend.api import (
    memory_router,
    voice_router,
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
app.include_router(voice_router)

# Добавляем WebSocket роут напрямую к app (не через voice_router)
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

    # Получаем ответ от ассистента
    try:
        response_text = await _assistant.process_message(request.message)
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

    return ChatResponseMessage(
        response=response_text,
        chat_id=chat_id,
        message_id=0,  # Можно получить из БД
    )


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
    
    return {
        "status": "ok",
        "provider": _config.llm.provider.value if _config else "unknown",
        "model": _config.llm.model if _config else "unknown",
        **stats,
    }


# === Статический фронтенд ===

FRONTEND_DIR = Path(__file__).parent.parent / "frontend"


@app.get("/", response_class=HTMLResponse)
async def serve_frontend():
    """
    Отдать главную страницу фронтенда.
    """
    index_path = FRONTEND_DIR / "index.html"
    
    if not index_path.exists():
        raise HTTPException(
            status_code=404,
            detail="Фронтенд не найден. Создайте frontend/index.html",
        )
    
    return FileResponse(index_path)


@app.get("/{path:path}")
async def serve_static(path: str):
    """
    Отдать статические файлы фронтенда.
    """
    file_path = (FRONTEND_DIR / path).resolve()
    
    if not str(file_path).startswith(str(FRONTEND_DIR.resolve())):
        raise HTTPException(status_code=403, detail="Доступ запрещён")
    
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Файл не найден")
    
    return FileResponse(file_path)


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
