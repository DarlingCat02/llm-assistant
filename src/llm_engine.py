"""
LLM Engine - Универсальный движок для работы с языковыми моделями.

Поддерживаемые провайдеры:
- Ollama: http://localhost:11434/v1/chat/completions
- LM Studio: http://localhost:1234/v1/chat/completions
- OpenRouter: https://openrouter.ai/api/v1/chat/completions

Все провайдеры используют OpenAI-совместимый API, поэтому
код одинаковый для всех — меняется только URL и API-ключ.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Callable, Any
from enum import Enum

import httpx

from config import get_config, LLMConfig, LLMProvider


logger = logging.getLogger(__name__)


class MessageRole(str, Enum):
    """Роли сообщений в диалоге."""
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


@dataclass
class Message:
    """Сообщение в диалоге."""
    role: MessageRole
    content: str
    images: list[str] = field(default_factory=list)
    
    def to_dict(self) -> dict:
        result = {
            "role": self.role.value,
            "content": self.content,
        }
        if self.images:
            result["images"] = self.images
        return result


@dataclass
class ToolCall:
    """Вызов функции (инструмента) из LLM."""
    name: str
    arguments: dict[str, Any]


@dataclass
class LLMResponse:
    """Ответ от языковой модели."""
    content: str
    model: str
    done: bool = True
    total_duration: int = 0
    tool_calls: list[ToolCall] = field(default_factory=list)


class LLMEngine:
    """
    Асинхронный движок для работы с LLM через OpenAI-совместимый API.
    
    Автоматически определяет провайдер из конфигурации и использует
    правильный URL и API-ключ.
    
    Пример использования:
        engine = LLMEngine()
        await engine.initialize()
        response = await engine.generate("Привет!")
        print(response.content)
    """
    
    def __init__(self, config: LLMConfig | None = None):
        self._config = config or get_config().llm
        self._client: httpx.AsyncClient | None = None
        self._initialized = False
        
        self._conversation_history: list[Message] = []
        
        self._system_prompt = (
            "Ты — дружелюбный AI-ассистент. Веди естественный разговор с пользователем.\n\n"
            "ПРАВИЛА:\n"
            "1. Отвечай развёрнуто и по существу, показывай, что понимаешь смысл сообщения\n"
            "2. НЕ повторяй и не эхо-отражай сообщение пользователя — формулируй свой оригинальный ответ\n"
            "3. Если собираешься просто повторить то, что сказал пользователь — переформулируй по-другому\n"
            "4. Задавай уточняющие вопросы, если нужно\n"
            "5. Если не знаешь ответа — скажи честно\n"
            "6. Помни информацию о пользователе из контекста"
        )
        
        self._tools: dict[str, Callable] = {}
    
    async def initialize(self) -> None:
        """Инициализировать HTTP клиент и проверить доступность провайдера."""
        if self._initialized:
            return
        
        headers = {}
        if self._config.requires_api_key:
            if not self._config.api_key:
                raise RuntimeError(
                    f"API-ключ не указан для провайдера {self._config.provider.value}. "
                    f"Установите LLM_API_KEY в .env"
                )
            headers["Authorization"] = f"Bearer {self._config.api_key}"
        
        # OpenRouter требует дополнительный заголовок
        if self._config.provider == LLMProvider.OPENROUTER:
            headers["HTTP-Referer"] = "http://localhost:8000"
            headers["X-Title"] = "Local AI Assistant"
        
        self._client = httpx.AsyncClient(
            base_url=self._config.api_base_url,
            timeout=120.0,
            headers=headers,
            limits=httpx.Limits(
                max_keepalive_connections=5,
                max_connections=10,
            ),
        )
        
        # Проверяем доступность
        try:
            if self._config.is_local:
                # Для локальных провайдеров проверяем базовый URL
                await self._check_local_availability()
            else:
                # Для OpenRouter делаем тестовый запрос
                await self._check_openrouter_availability()
        except Exception as e:
            logger.warning(f"Проверка провайдера: {e}")
            # Не блокируем запуск — может быть временная проблема
        
        self._initialized = True
        logger.info(
            f"LLM Engine инициализирован: "
            f"провайдер={self._config.provider.value}, "
            f"модель={self._config.model}"
        )
    
    async def _check_local_availability(self) -> None:
        """Проверить доступность локального сервера."""
        try:
            # Ollama имеет /api/tags, LM Studio имеет /v1/models
            if self._config.provider == LLMProvider.OLLAMA:
                # Проверяем базовый хост (без /v1)
                base_client = httpx.AsyncClient(
                    base_url=self._config.host,
                    timeout=10.0,
                )
                try:
                    resp = await base_client.get("/api/tags")
                    resp.raise_for_status()
                finally:
                    await base_client.aclose()
            else:
                # LM Studio: /v1/models
                resp = await self._client.get("/models")
                resp.raise_for_status()
            
            logger.info(f"Провайдер {self._config.provider.value} доступен: {self._config.host}")
        except httpx.ConnectError:
            raise
    
    async def _check_openrouter_availability(self) -> None:
        """Проверить доступность OpenRouter."""
        try:
            resp = await self._client.get("/models")
            resp.raise_for_status()
            logger.info("OpenRouter доступен")
        except httpx.HTTPError as e:
            logger.warning(f"OpenRouter проверка: {e}")
    
    async def close(self) -> None:
        """Закрыть HTTP клиент."""
        if self._client:
            await self._client.aclose()
            self._client = None
            self._initialized = False
            logger.info("LLM Engine закрыт")
    
    def set_system_prompt(self, prompt: str) -> None:
        """Установить системный промпт."""
        self._system_prompt = prompt
        logger.debug(f"Системный промпт обновлён: {len(prompt)} символов")
    
    def register_tool(self, name: str, func: Callable) -> None:
        """Зарегистрировать функцию для Function Calling."""
        self._tools[name] = func
        logger.info(f"Зарегистрирован инструмент: {name}")
    
    def add_to_history(self, message: Message) -> None:
        """Добавить сообщение в историю диалога."""
        self._conversation_history.append(message)
        
        max_messages = get_config().memory.max_context_messages
        if len(self._conversation_history) > max_messages:
            self._conversation_history = self._conversation_history[-max_messages:]
            logger.debug(f"История обрезана до {max_messages} сообщений")
    
    def clear_history(self) -> None:
        """Очистить историю диалога."""
        self._conversation_history.clear()
        logger.info("История диалога очищена")
    
    def get_history(self) -> list[Message]:
        """Получить копию истории диалога."""
        return self._conversation_history.copy()
    
    async def _build_messages(
        self,
        user_message: str,
        additional_context: list[str] | None = None,
    ) -> list[dict]:
        """Построить список сообщений для отправки."""
        messages = []
        
        messages.append(
            Message(role=MessageRole.SYSTEM, content=self._system_prompt).to_dict()
        )
        
        if additional_context:
            context_text = "\n\n".join(additional_context)
            context_message = (
                f"=== КОНТЕКСТ ИЗ ПАМЯТИ ===\n"
                f"Следующая информация может быть полезна для ответа:\n\n"
                f"{context_text}\n"
                f"=== КОНЕЦ КОНТЕКСТА ==="
            )
            messages.append(
                Message(role=MessageRole.SYSTEM, content=context_message).to_dict()
            )
        
        for msg in self._conversation_history:
            messages.append(msg.to_dict())
        
        messages.append(
            Message(role=MessageRole.USER, content=user_message).to_dict()
        )
        
        return messages
    
    async def generate(
        self,
        user_message: str,
        additional_context: list[str] | None = None,
        stream: bool = False,
    ) -> LLMResponse:
        """
        Сгенерировать ответ на сообщение пользователя.
        
        Args:
            user_message: Сообщение пользователя
            additional_context: Контекст из Memory Manager
            stream: Если True, возвращать токены по мере генерации
        
        Returns:
            LLMResponse: Ответ от модели.
        """
        if not self._initialized:
            raise RuntimeError("LLM Engine не инициализирован. Вызовите initialize().")
        
        messages = await self._build_messages(user_message, additional_context)
        
        payload = {
            "model": self._config.model,
            "messages": messages,
            "stream": stream,
            "temperature": self._config.temperature,
        }
        
        # num_ctx — специфичен для Ollama, другие провайдеры его игнорируют
        if self._config.provider == LLMProvider.OLLAMA:
            payload["options"] = {
                "num_ctx": self._config.num_ctx,
                "temperature": self._config.temperature,
            }
            # Убираем temperature из корня для Ollama (он в options)
            del payload["temperature"]
        
        logger.debug(
            f"Запрос к LLM: {len(messages)} сообщений, "
            f"провайдер={self._config.provider.value}, "
            f"модель={self._config.model}"
        )
        
        try:
            if stream:
                return await self._generate_stream(payload)
            else:
                return await self._generate_single(payload)
        except httpx.HTTPError as e:
            logger.error(f"Ошибка запроса к {self._config.provider.value}: {e}")
            raise
    
    async def _generate_single(self, payload: dict) -> LLMResponse:
        """Обычный режим (ждём полный ответ)."""
        response = await self._client.post("/chat/completions", json=payload)
        response.raise_for_status()
        data = response.json()
        
        # OpenAI-совместимый формат ответа
        choice = data.get("choices", [{}])[0]
        message_data = choice.get("message", {})
        content = message_data.get("content", "")
        model = data.get("model", self._config.model)
        
        # Парсим tool calls если есть
        tool_calls = []
        if message_data.get("tool_calls"):
            for tc in message_data["tool_calls"]:
                import json
                tool_call = ToolCall(
                    name=tc.get("function", {}).get("name", "unknown"),
                    arguments=json.loads(tc.get("function", {}).get("arguments", "{}")),
                )
                tool_calls.append(tool_call)
            
            if tool_calls:
                logger.info(
                    f"LLM запросила вызов инструментов: "
                    f"{[tc.name for tc in tool_calls]}"
                )
        
        # Получаем usage информацию
        usage = data.get("usage", {})
        total_duration = 0
        if usage:
            # Примерная оценка: ~50ms на токен
            total_tokens = usage.get("total_tokens", 0)
            total_duration = total_tokens * 50_000_000  # наносекунды
        
        llm_response = LLMResponse(
            content=content,
            model=model,
            done=True,
            total_duration=total_duration,
            tool_calls=tool_calls,
        )
        
        logger.debug(
            f"Ответ LLM: {len(llm_response.content)} символов, "
            f"модель={model}"
        )
        
        return llm_response
    
    async def _generate_stream(self, payload: dict) -> LLMResponse:
        """Streaming режим (токены по мере генерации)."""
        full_content = []
        model_name = self._config.model
        
        async with self._client.stream("POST", "/chat/completions", json=payload) as response:
            response.raise_for_status()
            
            async for line in response.aiter_lines():
                if not line:
                    continue
                
                # SSE формат: "data: {...}"
                if line.startswith("data: "):
                    line = line[6:]
                
                if line.strip() == "[DONE]":
                    break
                
                import json
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue
                
                choice = data.get("choices", [{}])[0]
                delta = choice.get("delta", {})
                content = delta.get("content", "")
                if content:
                    full_content.append(content)
                
                if data.get("model"):
                    model_name = data["model"]
        
        llm_response = LLMResponse(
            content="".join(full_content),
            model=model_name,
            done=True,
        )
        
        logger.debug(f"Streaming ответ LLM: {len(llm_response.content)} символов")
        return llm_response
    
    async def generate_with_context(
        self,
        messages: list[Message],
    ) -> LLMResponse:
        """Сгенерировать ответ с произвольным контекстом."""
        if not self._initialized:
            raise RuntimeError("LLM Engine не инициализирован.")
        
        payload = {
            "model": self._config.model,
            "messages": [msg.to_dict() for msg in messages],
            "stream": False,
            "temperature": self._config.temperature,
        }
        
        if self._config.provider == LLMProvider.OLLAMA:
            payload["options"] = {
                "num_ctx": self._config.num_ctx,
                "temperature": self._config.temperature,
            }
            del payload["temperature"]
        
        return await self._generate_single(payload)
