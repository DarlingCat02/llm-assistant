"""
Temporary mock backend: always returns tool actions, so the UI rendering of the
"actions" block can be verified without relying on the LLM's tool-calling.

Usage: python tests/mock_backend.py  (serves on 127.0.0.1:8000)
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatIn(BaseModel):
    message: str


@app.get("/api/status")
async def status():
    return {
        "status": "ok", "assistant_ready": True, "provider": "mock", "model": "mock",
        "supports_thinking": False, "loaded_context_length": 4096,
        "max_context_length": 4096, "chats_count": 1, "memory_entries": 0,
    }


@app.get("/api/config")
async def config():
    return {"provider": "ollama", "model": "mock", "ollama_host": "http://localhost:1234",
            "api_key": "", "num_ctx": 4096, "temperature": 0.7, "tts_steps": 64,
            "tts_temperature": 1.0, "memory_max_context": 20, "memory_search_results": 3,
            "memory_threshold": 0.3, "language": "ru", "show_backend_console": False,
            "personality_ru": "", "personality_en": "", "stt_model": "large-v3-turbo",
            "hotkey_voice": "Ctrl+Shift+V", "hotkey_voice_num": "Ctrl+Num0",
            "hotkey_live": "Ctrl+Shift+L"}


@app.get("/api/chats")
async def chats():
    return []


@app.post("/api/chats")
async def create_chat():
    return {"id": 1, "title": "Новый диалог", "created_at": "2026-01-01T00:00:00"}


@app.get("/api/chats/{chat_id}/messages")
async def chat_messages(chat_id: int):
    return []


@app.get("/api/avatars")
async def avatars():
    return {"avatars": []}


@app.get("/api/personas")
async def personas():
    return {"personas": [], "active": None, "exists": False, "error": None}


@app.post("/api/chat")
async def chat(body: ChatIn):
    return {
        "response": "Готово: открыл блокнот и создал файл.",
        "chat_id": 1, "message_id": 0,
        "used_context_tokens": 512, "max_context_tokens": 4096,
        "actions": [
            {"name": "app_open", "arguments": {"name": "notepad"},
             "result_preview": "Запущено: notepad", "ok": True},
            {"name": "file_create", "arguments": {"path": "demo.txt", "content": "hello" * 200},
             "result_preview": "Ошибка: [WinError 5] доступ запрещён", "ok": False},
        ],
    }