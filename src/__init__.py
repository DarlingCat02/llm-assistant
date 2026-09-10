"""
Local Assistant - Core of the local AI assistant.

Modular architecture for a scalable project:
- LLM Engine: Work with language models via Ollama API
- Memory Manager: Long-term memory based on ChromaDB
- TTS Engine: Speech synthesis (optional)
- Tools: Function system for extending capabilities

Example usage:
    from src import Assistant

    async def main():
        assistant = Assistant()
        await assistant.initialize()
        response = await assistant.process_message("Hello!")
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
