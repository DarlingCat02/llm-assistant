"""
Local Assistant - Ядро локального AI-ассистента.

Модульная архитектура для масштабируемого проекта:
- LLM Engine: Работа с языковыми моделями через Ollama API
- Memory Manager: Долговременная память на основе ChromaDB
- TTS Engine: Синтез речи (опционально)
- Tools: Система функций для расширения возможностей

Пример использования:
    from src import Assistant
    
    async def main():
        assistant = Assistant()
        await assistant.initialize()
        response = await assistant.chat("Привет!")
        print(response)
"""

from src.llm_engine import LLMEngine, Message, MessageRole, LLMResponse, ToolCall
from src.memory_manager import MemoryManager
from src.tts_engine import TTSEngine

__all__ = [
    "LLMEngine",
    "Message",
    "MessageRole",
    "LLMResponse",
    "ToolCall",
    "MemoryManager",
    "TTSEngine",
]

__version__ = "0.1.0"
