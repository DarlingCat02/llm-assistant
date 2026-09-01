"""
Local Assistant - Главный модуль запуска.

Консольный интерфейс для диалога с локальным AI-ассистентом.
Объединяет все компоненты:
- LLM Engine: генерация ответов через Ollama
- Memory Manager: поиск контекста в ChromaDB
- TTS Engine: озвучка ответов (опционально)

Архитектурные решения:
1. Класс Assistant инкапсулирует всю логику работы
2. Асинхронный цикл диалога не блокирует ввод/вывод
3. Graceful shutdown для корректного закрытия ресурсов

Пример использования:
    # Запуск через CLI
    python -m src.main
    
    # Или программно
    from src.main import Assistant
    
    async def main():
        assistant = Assistant()
        await assistant.run()
"""

import asyncio
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

from config import get_config, Config, setup_logging as config_setup_logging
from src.llm_engine import LLMEngine, Message, MessageRole, LLMResponse
from src.memory_manager import MemoryManager
from src.tts_engine import TTSEngine
try:
    from src.i18n import t
except ImportError:
    try:
        from i18n import t
    except ImportError:
        def t(key, lang=None, **kwargs):
            return key

# Логгер модуля
logger = logging.getLogger(__name__)


# === Настройка логирования ===
def setup_logging(config: Config) -> logging.Logger:
    """
    Настроить логирование приложения.

    Логи пишутся:
    - В консоль (stdout)
    - В файл logs/assistant.log

    Args:
        config: Конфигурация с уровнем логирования.

    Returns:
        logging.Logger: Настроенный логгер.
    """
    # Используем функцию из config модуля для базовой настройки
    config_setup_logging(config)
    
    # Создаём директорию для логов
    log_dir = config.get_logs_dir()
    
    # Добавляем файловый обработчик
    logger = logging.getLogger(__name__)
    file_handler = logging.FileHandler(
        log_dir / "assistant.log",
        encoding="utf-8",
    )
    file_handler.setFormatter(logging.Formatter(config.log.format if hasattr(config.log, 'format') else "%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
    logger.addHandler(file_handler)
    
    return logger


class Assistant:
    """
    Локальный AI-ассистент.
    
    Основной класс приложения, объединяющий все компоненты.
    Управляет жизненным циклом диалога и координирует работу модулей.
    
    Поток обработки запроса:
    1. Пользователь вводит сообщение
    2. Поиск релевантного контекста в памяти (RAG)
    3. Отправка запроса к LLM с контекстом
    4. Получение и отображение ответа
    5. Озвучка ответа (если включено)
    6. Сохранение диалога в память
    
    Пример использования:
        assistant = Assistant()
        await assistant.initialize()
        await assistant.run()
    """
    
    def __init__(self, config: Config | None = None):
        """
        Инициализировать ассистента.

        Args:
            config: Конфигурация приложения.
        """
        self._config = config or get_config()
        self._logger = logging.getLogger(__name__)

        # Компоненты (инициализируются позже)
        self._llm: LLMEngine | None = None
        self._memory: MemoryManager | None = None
        self._tts: TTSEngine | None = None

        # Флаг работы
        self._running = False
        self._closed = False

        # Статистика сессии
        self._message_count = 0
        self._start_time: datetime | None = None

        # Поиск в интернете
        self._search_tool = None
        self._ddg_tool_def = None
    
    async def initialize(self) -> None:
        """
        Инициализировать все компоненты ассистента.
        
        Вызывается один раз при старте.
        Последовательно инициализирует:
        1. LLM Engine (подключение к Ollama)
        2. Memory Manager (загрузка ChromaDB)
        3. TTS Engine (опционально)
        """
        self._logger.info("Initializing assistant...")
        self._start_time = datetime.now()
        
        # 1. LLM Engine
        self._llm = LLMEngine(config=self._config.llm)
        await self._llm.initialize()
        
        # 2. Memory Manager
        self._memory = MemoryManager(
            chroma_config=self._config.chroma,
            memory_config=self._config.memory,
        )
        await self._memory.initialize()
        
        # 3. TTS Engine
        self._tts = TTSEngine(config=self._config.tts)
        await self._tts.initialize()
        
        # Register tools (Function Calling stub)
        await self._register_tools()
        
        self._logger.info(
            f"Assistant ready. Model: {self._config.llm.model}, "
            f"Provider: {self._config.llm.provider.value}, "
            f"Memory: {self._config.chroma.persist_dir}"
        )
    
    def _should_search_memory(self, message: str) -> bool:
        """
        Определить, нужно ли искать в памяти (расширенная логика).
        
        RAG выполняется когда сообщение требует знаний/контекста.
        """
        msg = message.strip().lower()
        
        # === Категория 1: Явные запросы на воспоминание (100%) ===
        recall_keywords = [
            'помнишь', 'помни', 'remember', 'recall', 'ты знаешь', 'do you know',
            'было', 'was it', 'это было', 'is it was', 'как зовут', "what's my name",
            'моё имя', 'my name is', 'как меня зовут', 'what do you call me',
            'сохрани', 'запомни', 'keep in mind', 'не забудь',
        ]
        for kw in recall_keywords:
            if kw in msg:
                return True
        
        # === Категория 2: Вопросы требующие знаний (100%) ===
        question_keywords = [
            'что такое', 'what is', 'кто такой', 'who is',
            'как работает', 'how does', 'explain', 'объясни',
            'расскажи про', 'tell me about', 'describe',
            'почему', 'why', 'зачем', 'for what',
            'чем отличается', 'difference between',
        ]
        # Вопрос с вопросительным знаком
        if '?' in message:
            return True
        for kw in question_keywords:
            if kw in msg:
                return True
        
        # === Категория 3: Временные ссылки на прошлое ===
        temporal_keywords = [
            'в прошлый раз', 'last time', 'раньше', 'earlier', 'before',
            'недавно', 'recently', 'на прошлой неделе', 'last week',
            'вчера', 'yesterday', 'на прошлой встрече', 'at our last',
        ]
        for kw in temporal_keywords:
            if kw in msg:
                return True
        
        # === Категория 4: Контекстные ссылки (проект/код) ===
        context_keywords = [
            'мой проект', 'my project', 'наш код', 'our code',
            'этот файл', 'that file', 'тот проект', 'that project',
            'текущий проект', 'current project', 'данный проект',
            'модель', 'model', 'конфигурация', 'config',
        ]
        for kw in context_keywords:
            if kw in msg:
                return True
        
        # === Категория 5: Глаголы намерения/уточнения ===
        intent_keywords = [
            'проверь', 'check', 'посмотри', 'look',
            'какой', 'which', 'сколько', 'how many', 'how much',
            'найди', 'find', 'покажи', 'show me',
        ]
        for kw in intent_keywords:
            if kw in msg:
                return True
        
        # === ИСКЛЮЧЕНИЯ - когда RAG НЕ нужен ===
        
        # Очень короткие сообщения (кроме если есть явные маркеры)
        if len(message.strip()) < 15:
            # Всё равно проверяем на явные маркеры выше
            pass  # Continue to exclusions
        
        # Приветствия и простые фразы
        greetings = [
            'привет', 'здравствуй', 'здравствуйте', 'hello', 'hi', 'hey',
            'как дела', 'как ты', 'что делаешь', 'чем занимаешься',
            'пока', 'до свидания', 'спасибо', 'благодарю',
            'работает', 'есть кто', 'ты здесь',
        ]
        for greeting in greetings:
            if msg.startswith(greeting):
                return False
        
        # Простые вопросы о времени/погоде без личного контекста
        simple_questions = [
            'который час', 'сколько времени', 'какая дата',
            'как погода', 'какой день', 'today date', 'current time',
        ]
        for q in simple_questions:
            if q in msg:
                return False
        
        # Сообщение начинается с "я" new данные" без запроса
        if msg.startswith('я ') or msg.startswith('я:'):
            # Это новая информация от пользователя, а не вопрос
            return False
        
        # По умолчанию - ищем в памяти (лучше переусердствовать чем недополучить)
        return True
    
    def _looks_like_new_fact(self, message: str) -> bool:
        """
        Определить, содержит ли сообщение новый факт для извлечения.
        
        Факты обычно содержат:
        - Личную информацию (имя, возраст, город)
        - Предпочтения (любимый, нравится, не люблю)
        - О себе утверждения
        """
        msg = message.strip().lower()
        
        # Паттерны фактов
        fact_patterns = [
            'меня зовут', 'моё имя', ' меня ', 'по имени',
            'мне лет', 'мне ', 'года', 'возраст',
            'живу в', 'из ', 'город',
            'любимый', 'любит', 'нравится', 'не нравится',
            'работаю', 'работа', 'профессия', 'учусь',
            'у меня есть', 'у меня',
            'я ', 'моя', 'моё', 'мой',
            'предпочитаю', 'обычно', 'часто', 'я люблю',
        ]
        
        # Проверяем наличие фактовых паттернов
        for pattern in fact_patterns:
            if pattern in msg:
                return True
        
        # Также проверяем длину - очень длинные сообщения могут содержать факты
        if len(message.strip()) > 50:
            return True
        
        return False

    async def _register_tools(self) -> None:
        """
        Зарегистрировать доступные инструменты (Function Calling).
        """
        if not self._llm:
            return

        from src.web_search import DuckDuckGoSearchTool, DDG_TOOL_DEFINITION
        from src.agent_tools import (
            FILE_CREATE_DEFINITION, APP_OPEN_DEFINITION, FILE_OPEN_DEFINITION, BROWSER_OPEN_DEFINITION,
            SCREENSHOT_DEFINITION,
            file_create, app_open, file_open, browser_open, capture_screen,
        )

        # Language-aware tool definition
        try:
            _lang = get_config().general.language
        except Exception:
            _lang = "en"
        if _lang == "ru":
            self._ddg_tool_def = DDG_TOOL_DEFINITION
        else:
            try:
                from src.web_search import DDG_TOOL_DEFINITION_EN
                self._ddg_tool_def = DDG_TOOL_DEFINITION_EN
            except ImportError:
                self._ddg_tool_def = DDG_TOOL_DEFINITION
        self._llm.register_tool("web_search_ddg", self._execute_web_search_ddg)
        self._llm.register_tool("file_create", file_create)
        self._llm.register_tool("app_open", app_open)
        self._llm.register_tool("file_open", file_open)
        self._llm.register_tool("browser_open", browser_open)
        self._llm.register_tool("capture_screen", capture_screen)

        try:
            self._search_tool = DuckDuckGoSearchTool()
            await self._search_tool.initialize()
            self._logger.info("DuckDuckGo search ready")
        except Exception as e:
            self._logger.warning(f"Failed to initialize DuckDuckGo: {e}")

        self._logger.info("Agent tools registered: file_create, app_open, file_open, browser_open, capture_screen")
    
    def _get_api_headers(self) -> dict:
        """Получить заголовки для API-запросов."""
        headers = {}
        if self._config.llm.requires_api_key:
            headers["Authorization"] = f"Bearer {self._config.llm.api_key}"
        if self._config.llm.provider.value == "openrouter":
            headers["HTTP-Referer"] = "http://localhost:8000"
            headers["X-Title"] = "Local AI Assistant"
        return headers
    
    async def close(self) -> None:
        """Корректно закрыть все компоненты."""
        if self._closed:
            return
        self._closed = True
        
        self._logger.info("Shutting down assistant...")
        
        if self._tts:
            await self._tts.close()
        
        if self._memory:
            await self._memory.close()
        
        if self._llm:
            await self._llm.close()
        
        if self._start_time:
            duration = datetime.now() - self._start_time
            self._logger.info(
                f"Session completed. Messages: {self._message_count}, "
                f"Duration: {duration}"
            )
    
    async def process_message(self, user_message: str, thinking: bool = False, search: str = "", chat_history: list[dict] | None = None, images: list[str] | None = None) -> LLMResponse:
        """
        Обработать сообщение пользователя.

        Args:
            user_message: Сообщение пользователя.
            thinking: Включить режим рассуждения (для Qwen3).
            search: Включить поиск в интернете.
            chat_history: История сообщений чата (список dict'ов с role/content).
            images: Список base64-encoded изображений.

        Returns:
            LLMResponse: Ответ ассистента с контентом и метаданными.
        """
        if not self._llm or not self._memory:
            lang = get_config().general.language
            raise RuntimeError(t("api.assistant_not_init", lang=lang))

        self._message_count += 1

        # Auto-detection for screenshot trigger
        if images is None:
            images = []
        
        screen_config = self._config.screen
        if screen_config.enabled:
            screenshot_triggers = [tr.strip() for tr in screen_config.triggers.split(",") if tr.strip()]
            
            msg_lower = user_message.lower()
            needs_screenshot = any(trigger in msg_lower for trigger in screenshot_triggers)
            
            if needs_screenshot:
                self._logger.info(f"Screenshot trigger detected: '{user_message[:50]}...'")
                try:
                    from src.agent_tools import capture_screen
                    screenshot_b64 = await capture_screen(
                        monitor=screen_config.monitor,
                        save_path=screen_config.save_path
                    )
                    if screenshot_b64 and not screenshot_b64.startswith("Ошибка") and not screenshot_b64.startswith("Error"):
                        images.append(screenshot_b64)
                        self._logger.info("Auto screenshot added to request")
                    else:
                        self._logger.warning(f"Failed to capture screenshot: {screenshot_b64}")
                except Exception as e:
                    self._logger.error(f"Auto-screenshot error: {e}")

        # 1. Smart memory search (RAG)
        context = []
        if self._should_search_memory(user_message):
            self._logger.debug(f"Searching context for: {user_message[:50]}...")
            context = await self._memory.search_context(user_message)

            if context:
                self._logger.info(f"Found {len(context)} memory entries")
            else:
                self._logger.debug("No context found")
        else:
            self._logger.debug("RAG skipped (greeting/short message)")

        # 2. Prepare tools (language-aware)
        try:
            _tool_lang = get_config().general.language
        except Exception:
            _tool_lang = "en"
        if _tool_lang == "ru":
            from src.agent_tools import FILE_CREATE_DEFINITION, APP_OPEN_DEFINITION, FILE_OPEN_DEFINITION, BROWSER_OPEN_DEFINITION, SCREENSHOT_DEFINITION
            tools = [FILE_CREATE_DEFINITION, APP_OPEN_DEFINITION, FILE_OPEN_DEFINITION, BROWSER_OPEN_DEFINITION, SCREENSHOT_DEFINITION]
        else:
            try:
                from src.agent_tools import FILE_CREATE_DEFINITION_EN as FILE_CREATE_DEFINITION, APP_OPEN_DEFINITION_EN as APP_OPEN_DEFINITION, FILE_OPEN_DEFINITION_EN as FILE_OPEN_DEFINITION, BROWSER_OPEN_DEFINITION_EN as BROWSER_OPEN_DEFINITION, SCREENSHOT_DEFINITION_EN as SCREENSHOT_DEFINITION
                tools = [FILE_CREATE_DEFINITION, APP_OPEN_DEFINITION, FILE_OPEN_DEFINITION, BROWSER_OPEN_DEFINITION, SCREENSHOT_DEFINITION]
            except ImportError:
                from src.agent_tools import FILE_CREATE_DEFINITION, APP_OPEN_DEFINITION, FILE_OPEN_DEFINITION, BROWSER_OPEN_DEFINITION, SCREENSHOT_DEFINITION
                tools = [FILE_CREATE_DEFINITION, APP_OPEN_DEFINITION, FILE_OPEN_DEFINITION, BROWSER_OPEN_DEFINITION, SCREENSHOT_DEFINITION]
        
        if search and search == "ddg" and self._search_tool:
            # Language-aware DDG definition (fresh, not cached)
            try:
                from src.web_search import DDG_TOOL_DEFINITION as DDG_RU, DDG_TOOL_DEFINITION_EN as DDG_EN
                ddg_def = DDG_RU if _tool_lang == "ru" else DDG_EN
            except ImportError:
                ddg_def = self._ddg_tool_def
            tools.append(ddg_def)

        # 2.1. If search enabled — always search web
        if search and search == "ddg" and self._search_tool:
            web_results = await self._search_tool.search(user_message, max_results=7)

            if web_results and not web_results.startswith("["):
                if _tool_lang == "ru":
                    search_context = f"\n\n=== РЕЗУЛЬТАТЫ ПОИСКА В ИНТЕРНЕТЕ ===\n{web_results}\n=== КОНЕЦ РЕЗУЛЬТАТОВ ==="
                else:
                    search_context = f"\n\n=== WEB SEARCH RESULTS ===\n{web_results}\n=== END OF RESULTS ==="
                context.append(search_context)
                self._logger.info("Search results added to context")
            else:
                self._logger.warning(f"Search returned no results: {web_results}")

        # 3. Generate response via LLM
        self._logger.debug("Generating response...")
        response: LLMResponse = await self._llm.generate(
            user_message=user_message,
            additional_context=context,
            thinking=thinking,
            tools=tools,
            chat_history=chat_history,
            images=images,
        )

        answer = response.content

        # 4. Speak answer (if enabled)
        if self._tts and self._config.tts.enabled:
            self._logger.debug("Speaking answer...")
            await self._tts.speak(answer)

        # 5. Extract facts (only if message contains facts)
        if self._looks_like_new_fact(user_message):
            await self._extract_and_save_facts(user_message, answer)

        return response

    async def _execute_web_search_ddg(self, query: str) -> str:
        """Search via DuckDuckGo (callback for LLM)."""
        if not self._search_tool:
            try:
                lang = get_config().general.language
            except Exception:
                lang = "en"
            return "[DuckDuckGo search unavailable]" if lang == "en" else "[DuckDuckGo поиск недоступен]"
        return await self._search_tool.search(query, max_results=7)

    def process_message_sync(self, user_message: str, thinking: bool = False) -> str:
        """
        Обработать сообщение пользователя (синхронная версия для GUI).
        """
        import httpx
        
        if not self._llm or not self._memory:
            lang = get_config().general.language
            raise RuntimeError(t("api.assistant_not_init", lang=lang))

        self._message_count += 1

        # 1. Smart memory search (RAG)
        context = []
        if self._should_search_memory(user_message):
            context = asyncio.run(self._memory.search_context(user_message))
            
            if context:
                self._logger.info(f"Found {len(context)} memory entries")
            else:
                self._logger.debug("No context found")
        else:
            self._logger.debug("RAG skipped (greeting/short message)")

        # 2. Generate response via LLM
        self._logger.debug("Generating response...")
        
        answer = ""
        with httpx.Client(
            base_url=self._config.llm.api_base_url,
            timeout=60.0,
            headers=self._get_api_headers(),
        ) as sync_client:
            # Language-aware system prompt
            try:
                lang = get_config().general.language
            except Exception:
                lang = "en"
            if hasattr(self._llm, "_get_system_prompt"):
                system_prompt = self._llm._get_system_prompt()
            else:
                system_prompt = self._llm._system_prompt
            history = self._llm.get_history()
            
            messages = [
                {"role": "system", "content": system_prompt},
            ]
            
            if context:
                context_text = "\n\n".join(context)
                if lang == "ru":
                    ctx = f"=== КОНТЕКСТ ИЗ ПАМЯТИ ===\n{context_text}\n=== КОНЕЦ КОНТЕКСТА ==="
                else:
                    ctx = f"=== MEMORY CONTEXT ===\n{context_text}\n=== END OF CONTEXT ==="
                messages.append({
                    "role": "system",
                    "content": ctx
                })
            
            for msg in history:
                messages.append(msg.to_dict())
            
            messages.append({"role": "user", "content": user_message})
            
            payload = {
                "model": self._config.llm.model,
                "messages": messages,
                "stream": False,
                "temperature": self._config.llm.temperature,
            }
            
            if self._config.llm.provider.value == "ollama":
                thinking_type = "on" if thinking else "off"
                payload["options"] = {
                    "num_ctx": self._config.llm.num_ctx,
                    "temperature": self._config.llm.temperature,
                    "thinking": {"type": thinking_type},
                }
                del payload["temperature"]
            
            response = sync_client.post("/chat/completions", json=payload)
            response.raise_for_status()
            data = response.json()
            
            choice = data.get("choices", [{}])[0]
            answer = choice.get("message", {}).get("content", "")

        # 3. Извлечение фактов (только если сообщение содержит факты)
        if self._looks_like_new_fact(user_message):
            asyncio.run(self._extract_and_save_facts(user_message, answer))

        # 4. Добавляем в историю LLM
        self._llm.add_to_history(Message(role=MessageRole.USER, content=user_message))
        self._llm.add_to_history(Message(role=MessageRole.ASSISTANT, content=answer))

        return answer

    async def _extract_and_save_facts(self, user_message: str, assistant_response: str) -> None:
        """
        Извлечь важные факты из диалога и сохранить в память.
        
        Анализирует диалог и сохраняет только важную информацию:
        - Имя пользователя
        - Предпочтения (любимый цвет, еда, и т.д.)
        - Личные факты (возраст, город, работа)
        - Контекст для будущих разговоров
        
        Args:
            user_message: Сообщение пользователя.
            assistant_response: Ответ ассистента.
        """
        # Prompt for fact extraction (language-aware)
        try:
            _fact_lang = get_config().general.language
        except Exception:
            _fact_lang = "en"
        if _fact_lang == "ru":
            fact_extraction_prompt = f"""
Проанализируй диалог и извлеки ВАЖНЫЕ факты о пользователе.
Сохраняй только личную информацию и предпочтения.

Диалог:
User: {user_message}
Assistant: {assistant_response}

Если есть важные факты, верни их в формате JSON списка:
["Факт 1", "Факт 2"]

Если важных фактов нет, верни пустой список: []

ПРАВИЛА:
- Имена, ники, названия СОХРАНЯЙ в оригинале (не переводи и не транслитерируй)
- "Darling Cat" → "Darling Cat", а не "Дарлинг Кат"
- "Barcelona" → "Barcelona", а не "Барселона"
- "Python" → "Python", а не "Питон"

Примеры важных фактов:
- "Пользователя зовут Darling Cat"
- "Любимый цвет — red"
- "Пользователь живёт в Tokyo"
- "Пользователь работает с Python"

Не сохраняй обычные вопросы и ответы типа 'привет', 'как дела', 'спасибо'.
"""
        else:
            fact_extraction_prompt = f"""
Analyze the dialog and extract IMPORTANT facts about the user.
Save only personal information and preferences.

Dialog:
User: {user_message}
Assistant: {assistant_response}

If there are important facts, return them as JSON list:
["Fact 1", "Fact 2"]

If no important facts, return empty list: []

RULES:
- Keep names, nicknames, titles in original (do not translate or transliterate)
- "Darling Cat" → "Darling Cat", not translation
- "Barcelona" → "Barcelona", not translation
- "Python" → "Python", not translation

Examples of important facts:
- "User name is Darling Cat"
- "Favorite color is red"
- "User lives in Tokyo"
- "User works with Python"

Do not save ordinary questions and answers like 'hello', 'how are you', 'thanks'.
"""
        
        try:
            import httpx
            import json
            
            sync_client = httpx.Client(
                base_url=self._config.llm.api_base_url,
                timeout=30.0,
                headers=self._get_api_headers(),
            )
            
            try:
                sys_prompt = "Ты помощник для извлечения фактов. Возвращай ТОЛЬКО JSON список фактов или пустой список." if _fact_lang == "ru" else "You are a helper for fact extraction. Return ONLY JSON list of facts or empty list."
                messages = [
                    {"role": "system", "content": sys_prompt},
                    {"role": "user", "content": fact_extraction_prompt},
                ]
                
                payload = {
                    "model": self._config.llm.model,
                    "messages": messages,
                    "stream": False,
                    "temperature": 0.1,
                }
                
                response = sync_client.post("/chat/completions", json=payload)
                response.raise_for_status()
                data = response.json()
                
                choice = data.get("choices", [{}])[0]
                facts_text = choice.get("message", {}).get("content", "[]")
                
                # Парсим JSON
                facts = json.loads(facts_text.strip())
                
                if isinstance(facts, list) and facts:
                    # Save each fact
                    for fact in facts:
                        if fact and len(fact.strip()) > 5:
                            await self._memory.save_fact(fact.strip(), category="personal")
                            self._logger.info(f"Saved fact: {fact[:50]}...")
                
            finally:
                sync_client.close()
                
        except Exception as e:
            self._logger.debug(f"Failed to extract facts: {e}")

    async def run(self) -> None:
        """
        Запустить консольный цикл диалога.
        
        Бесконечный цикл:
        - Чтение ввода пользователя
        - Обработка команд (quit, clear, help, stats)
        - Обработка сообщений через process_message
        - Вывод ответа
        
        Завершается по команде 'quit' или Ctrl+C.
        """
        if not self._llm:
            lang = get_config().general.language
            raise RuntimeError(t("api.assistant_not_init", lang=lang))
        
        self._running = True
        self._print_welcome()
        
        try:
            while self._running:
                # Read user input
                try:
                    user_input = await self._get_input()
                except EOFError:
                    # Ctrl+D
                    break
                
                # Handle commands
                command_result = await self._handle_command(user_input)
                if command_result:
                    print(command_result)
                    lang = get_config().general.language
                    if command_result == "exit" or command_result == t("cli.exit", lang=lang):
                        break
                    continue
                
                # Skip empty messages
                if not user_input.strip():
                    continue
                
                # Handle message
                lang = get_config().general.language
                print(t("cli.thinking", lang=lang), end="\r")
                answer = await self.process_message(user_input.strip())
                print(" " * 50, end="\r")
                
                # Display answer
                print(f"\n🤖 {answer.content}\n")
        
        except KeyboardInterrupt:
            # Ctrl+C
            lang = get_config().general.language
            print(t("cli.interrupted", lang=lang))
        finally:
            await self.close()
    
    async def _get_input(self) -> str:
        """
        Получить ввод от пользователя.
        
        Асинхронная обёртка над input() для совместимости.
        
        Returns:
            str: Введённая строка.
        """
        # In Windows input() is blocking, use sync
        loop = asyncio.get_event_loop()
        lang = get_config().general.language
        prompt = t("cli.prompt", lang=lang)
        return await loop.run_in_executor(
            None,
            lambda: input(prompt),
        )
    
    async def _handle_command(self, text: str) -> Optional[str]:
        """
        Обработать команду пользователя.
        
        Поддерживаемые команды:
        - quit, exit, q: завершение работы
        - clear, c: очистка истории
        - help, h: справка
        - stats, s: статистика
        
        Args:
            text: Введённый текст.
        
        Returns:
            str | None: Результат команды или None если не команда.
        """
        text_lower = text.strip().lower()
        
        if text_lower in ("quit", "exit", "q", "выход"):
            self._running = False
            lang = get_config().general.language
            return t("cli.exit", lang=lang)
        
        elif text_lower in ("clear", "c", "очистить"):
            if self._llm:
                self._llm.clear_history()
            lang = get_config().general.language
            return t("cli.cleared", lang=lang)
        
        elif text_lower in ("help", "h", "помощь"):
            return self._get_help_text()
        
        elif text_lower in ("stats", "s", "статистика"):
            return await self._get_stats_text()
        
        return None
    
    def _print_welcome(self) -> None:
        """Вывести приветственное сообщение."""
        lang = get_config().general.language
        tts_state = t("cli.tts_state_on", lang=lang) if self._config.tts.enabled else t("cli.tts_state_off", lang=lang)
        print("\n" + "=" * 60)
        print(t("cli.welcome.title", lang=lang))
        print("=" * 60)
        print(t("cli.welcome.model", lang=lang, model=self._config.llm.model))
        print(t("cli.welcome.provider", lang=lang, provider=self._config.llm.provider.value))
        print(t("cli.welcome.memory", lang=lang, dir=self._config.chroma.persist_dir))
        print(t("cli.welcome.tts", lang=lang, state=tts_state))
        print("-" * 60)
        print(t("cli.welcome.commands", lang=lang))
        print("=" * 60 + "\n")
    
    def _get_help_text(self) -> str:
        """Получить текст справки."""
        lang = get_config().general.language
        lines = [
            "",
            t("cli.help.title", lang=lang),
            "",
            t("cli.help.commands", lang=lang),
            t("cli.help.quit", lang=lang),
            t("cli.help.clear", lang=lang),
            t("cli.help.stats", lang=lang),
            t("cli.help.help", lang=lang),
            "",
            t("cli.help.hint", lang=lang),
            "",
        ]
        return "\n".join(lines)
    
    async def _get_stats_text(self) -> str:
        """Получить текст статистики."""
        lang = get_config().general.language
        lines = ["" + t("cli.stats.title", lang=lang)]
        lines.append(t("cli.stats.messages", lang=lang, count=self._message_count))
        duration = str(datetime.now() - self._start_time) if self._start_time else "N/A"
        lines.append(t("cli.stats.uptime", lang=lang, duration=duration))
        
        if self._memory:
            memory_stats = await self._memory.get_stats()
            mem_count = memory_stats.get("total_entries", "N/A")
            lines.append(t("cli.stats.memory", lang=lang, count=mem_count))
        
        return "\n".join(lines)


async def main() -> None:
    """
    Точка входа приложения.

    Настраивает логирование, создаёт ассистента
    и запускает цикл диалога (консоль или GUI).
    """
    # Загружаем конфигурацию
    config = get_config()

    # Setup logging
    logger = setup_logging(config)
    logger.info("Starting Local AI Assistant...")

    # Create and initialize assistant
    assistant = Assistant(config)

    try:
        await assistant.initialize()

        # Choose mode: GUI or console
        if config.gui.enabled:
            logger.info(f"Starting GUI mode: {config.gui.title}")
            # Run GUI in separate thread
            _run_gui_mode(assistant)
        else:
            logger.info("Starting console mode")
            await assistant.run()

    except Exception as e:
        logger.error(f"Critical error: {e}", exc_info=True)
        raise
    finally:
        # Ensure resources are closed
        await assistant.close()

    logger.info("Application completed")


def _run_gui_mode(assistant: Assistant) -> None:
    """
    Запустить графический интерфейс.
    
    Выбирает фреймворк на основе конфигурации.
    
    Args:
        assistant: Инициализированный экземпляр Assistant.
    """
    framework = assistant._config.gui.framework.lower()
    
    if framework == "customtkinter":
        _run_customtkinter_gui(assistant)
    else:
        logger.warning(f"Unknown GUI framework: {framework}. Starting console mode.")
        asyncio.run(assistant.run())


def _run_customtkinter_gui(assistant: Assistant) -> None:
    """
    Запустить GUI на CustomTkinter.
    
    CustomTkinter работает в главном потоке, поэтому
    просто передаём управление и завершаем основной процесс.
    
    Args:
        assistant: Инициализированный экземпляр Assistant.
    """
    from src.gui_ctk import run_gui
    logger.info("Starting CustomTkinter GUI")
    run_gui(assistant)


if __name__ == "__main__":
    # Run async loop
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        lang = get_config().general.language
        print(t("cli.bye", lang=lang))
