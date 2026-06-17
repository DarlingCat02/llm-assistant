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
    TOOL = "tool"


@dataclass
class Message:
    """Сообщение в диалоге."""
    role: MessageRole
    content: str
    images: list[str] = field(default_factory=list)
    tool_calls: list[dict] | None = None
    name: str | None = None
    tool_call_id: str | None = None

    def to_dict(self) -> dict:
        result = {
            "role": self.role.value,
            "content": self.content,
        }
        if self.images:
            result["images"] = self.images
        if self.tool_calls:
            result["tool_calls"] = self.tool_calls
        if self.name:
            result["name"] = self.name
        if self.tool_call_id:
            result["tool_call_id"] = self.tool_call_id
        return result


@dataclass
class ToolCall:
    """Вызов функции (инструмента) из LLM."""
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class LLMResponse:
    """Ответ от языковой модели."""
    content: str
    model: str
    done: bool = True
    total_duration: int = 0
    prompt_tokens: int = 0
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
            "Ты — AI-ассистент. Отвечай кратко и по делу.\n\n"
            "ПРАВИЛА:\n"
            "1. Отвечай ТОЛЬКО на русском языке, без вставок английских слов\n"
            "2. Отвечай прямо, без лишних слов и эмоций\n"
            "3. Не повторяй и не перефразируй сообщение пользователя\n"
            "4. Если не знаешь — скажи честно\n"
            "5. Используй контекст из памяти\n\n"
            "ПРАВИЛА РАБОТЫ С ПОИСКОМ:\n"
            "- ТЫ НЕ ЗНАЕШЬ ТЕКУЩУЮ ДАТУ, ВРЕМЯ, ПОГОДУ, КУРСЫ ВАЛЮТ — у тебя нет актуальных данных\n"
            "- ВСЕГДА используй web_search для: времени, даты, погоды, курсов, новостей, актуальных цен\n"
            "- Если тебе вернулись результаты поиска — ОБЯЗАТЕЛЬНО используй их для ответа\n"
            "- НЕ придумывай данные из головы — опирайся ТОЛЬКО на результаты поиска\n"
            "- Указывай конкретные цифры и факты из результатов\n"
            "- НЕ отвечай на вопросы о времени/дате/температуре без предварительного поиска\n\n"
            "АГЕНТНЫЕ ВОЗМОЖНОСТИ:\n"
            "- У тебя есть инструменты для работы с файлами, приложениями и экраном\n"
            "- file_create(path, content) — создать файл\n"
            "- app_open(name) — открыть приложение. Название бери ТОЧНО как сказал пользователь, НЕ ПЕРЕВОДИ на английский\n"
            "- browser_open(url) — открыть сайт в браузере (youtube.com, vk.com, github.com и т.д.)\n"
            "- file_open(path) — открыть файл ассоциированным приложением\n"
            "- capture_screen(monitor, save_path) — сделать скриншот экрана. Используй когда пользователь просит посмотреть на экран, показать что на экране, сделать скриншот\n"
            "- Используй эти инструменты когда пользователь просит создать файл, открыть приложение, сайт, файл или посмотреть на экран"
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
    
    def _format_user_content(self, text: str, images: list[str] | None = None) -> list[dict] | str:
        """Форматировать контент пользователя для OpenAI Vision API."""
        if not images:
            return text
        
        content = [{"type": "text", "text": text}]
        for img_b64 in images:
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}
            })
        return content

    async def _build_messages(
        self,
        user_message: str,
        additional_context: list[str] | None = None,
        thinking: bool = False,
        chat_history: list[dict] | None = None,
        images: list[str] | None = None,
    ) -> tuple[list[dict], bool]:
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
        
        history = chat_history if chat_history is not None else [msg.to_dict() for msg in self._conversation_history]
        for msg in history:
            messages.append(msg if isinstance(msg, dict) else msg.to_dict())
        
        # Форматируем user message с изображениями для OpenAI Vision API
        user_content = self._format_user_content(user_message, images)
        user_msg_dict = {
            "role": MessageRole.USER.value,
            "content": user_content
        }
        messages.append(user_msg_dict)
        
        return messages, thinking

    async def generate(
        self,
        user_message: str,
        additional_context: list[str] | None = None,
        stream: bool = False,
        thinking: bool = False,
        tools: list[dict] | None = None,
        chat_history: list[dict] | None = None,
        images: list[str] | None = None,
    ) -> LLMResponse:
        """
        Сгенерировать ответ на сообщение пользователя.

        Args:
            user_message: Сообщение пользователя
            additional_context: Контекст из Memory Manager
            stream: Если True, возвращать токены по мере генерации
            thinking: Включить режим рассуждения (для Qwen3)
            tools: Список определений инструментов (OpenAI tool format)
            images: Список base64-encoded изображений

        Returns:
            LLMResponse: Ответ от модели.
        """
        if not self._initialized:
            raise RuntimeError("LLM Engine не инициализирован. Вызовите initialize().")

        messages, thinking_enabled = await self._build_messages(
            user_message, additional_context, thinking, chat_history, images
        )

        payload = {
            "model": self._config.model,
            "messages": messages,
            "stream": stream,
            "temperature": self._config.temperature,
        }

        if tools:
            payload["tools"] = tools

        # num_ctx и thinking — специфичны для Ollama
        if self._config.provider == LLMProvider.OLLAMA:
            thinking_type = "on" if thinking_enabled else "off"
            payload["options"] = {
                "num_ctx": self._config.num_ctx,
                "temperature": self._config.temperature,
                "thinking": {"type": thinking_type},
            }
            del payload["temperature"]

        logger.debug(
            f"Запрос к LLM: {len(messages)} сообщений, "
            f"провайдер={self._config.provider.value}, "
            f"модель={self._config.model}"
        )
        if tools:
            logger.info(f"Инструменты: {[t['function']['name'] for t in tools]}")

        try:
            max_rounds = 5
            for round_idx in range(max_rounds):
                if stream and round_idx == 0:
                    response = await self._generate_stream(payload)
                else:
                    response = await self._generate_single(payload)

                if not response.tool_calls:
                    break

                logger.info(
                    f"Раунд {round_idx + 1}: LLM вызвала инструмент(ы): "
                    f"{[tc.name for tc in response.tool_calls]}"
                )

                import json
                assistant_msg = Message(
                    role=MessageRole.ASSISTANT,
                    content=response.content,
                    tool_calls=[
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.name,
                                "arguments": json.dumps(tc.arguments, ensure_ascii=False) if isinstance(tc.arguments, dict) else tc.arguments,
                            },
                        }
                        for tc in response.tool_calls
                    ],
                )
                payload["messages"].append(assistant_msg.to_dict())

                for tc in response.tool_calls:
                    tool_result = await self._execute_tool(tc)
                    tool_msg = Message(
                        role=MessageRole.TOOL,
                        content=tool_result,
                        tool_call_id=tc.id,
                    )
                    payload["messages"].append(tool_msg.to_dict())

                if stream:
                    payload["stream"] = False

            if response.tool_calls:
                logger.info(f"Инструменты выполнены за {round_idx + 1} раунд(ов)")

            return response

        except httpx.HTTPError as e:
            logger.error(f"Ошибка запроса к {self._config.provider.value}: {e}")
            raise

    async def _execute_tool(self, tool_call: ToolCall) -> str:
        """Выполнить вызов инструмента и вернуть результат."""
        if not hasattr(self, '_tools') or not self._tools:
            return f"[Ошибка: инструмент '{tool_call.name}' не зарегистрирован]"

        tool_fn = self._tools.get(tool_call.name)
        if not tool_fn:
            return f"[Ошибка: инструмент '{tool_call.name}' не найден]"

        try:
            result = await tool_fn(**tool_call.arguments)
            return str(result)
        except Exception as e:
            logger.error(f"Ошибка выполнения инструмента {tool_call.name}: {e}")
            return f"[Ошибка выполнения инструмента {tool_call.name}: {e}]"
    
    async def _generate_single(self, payload: dict) -> LLMResponse:
        """Обычный режим (ждём полный ответ)."""
        # Для Ollama используем /api/chat/completions
        endpoint = "/chat/completions"
        if self._config.provider == LLMProvider.OLLAMA:
            endpoint = "/api/chat"
        
        response = await self._client.post(endpoint, json=payload)
        response.raise_for_status()
        data = response.json()
        
        # Парсим ответ в зависимости от провайдера
        if self._config.provider == LLMProvider.OLLAMA:
            # Ollama format: {"message": {"role": "assistant", "content": "..."}}
            message_data = data.get("message", {})
            content = message_data.get("content", "")
            model = data.get("model", self._config.model)
        else:
            # OpenAI format: {"choices": [{"message": {...}}]}
            choice = data.get("choices", [{}])[0]
            message_data = choice.get("message", {})
            content = message_data.get("content", "")
            model = data.get("model", self._config.model)
        
        # Парсим tool calls если есть
        tool_calls = []
        if message_data.get("tool_calls"):
            for tc in message_data["tool_calls"]:
                import json
                raw_args = tc.get("function", {}).get("arguments", "{}")
                if isinstance(raw_args, dict):
                    arguments = raw_args
                else:
                    arguments = json.loads(raw_args)
                tool_call = ToolCall(
                    id=tc.get("id", ""),
                    name=tc.get("function", {}).get("name", "unknown"),
                    arguments=arguments,
                )
                tool_calls.append(tool_call)
            
            if tool_calls:
                logger.info(
                    f"LLM запросила вызов инструментов: "
                    f"{[tc.name for tc in tool_calls]}"
                )
        
        # Получаем duration информацию
        total_duration = 0
        prompt_tokens = 0
        if self._config.provider == LLMProvider.OLLAMA:
            total_duration = data.get("total_duration", 0)
            prompt_tokens = data.get("prompt_eval_count", 0)
        else:
            usage = data.get("usage", {})
            if usage:
                total_tokens = usage.get("total_tokens", 0)
                total_duration = total_tokens * 50_000_000
                prompt_tokens = usage.get("prompt_tokens", 0)
        
        llm_response = LLMResponse(
            content=content,
            model=model,
            done=True,
            total_duration=total_duration,
            prompt_tokens=prompt_tokens,
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
                "thinking": {"type": "off"},
            }
            del payload["temperature"]
        
        return await self._generate_single(payload)
