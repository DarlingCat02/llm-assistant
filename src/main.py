"""
Local Assistant - Main entry module.

Console interface for dialog with the local AI assistant.
Combines all components:
- LLM Engine: answer generation via Ollama
- Memory Manager: context search in ChromaDB
- TTS Engine: answer voicing (optional)

Architectural decisions:
1. The Assistant class encapsulates all working logic
2. The async dialog loop does not block input/output
3. Graceful shutdown for correct resource closing

Example usage:
    # Run via CLI
    python -m src.main

    # Or programmatically
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
    from src.i18n import t, assistant_not_init_detail
except ImportError:
    try:
        from i18n import t, assistant_not_init_detail
    except ImportError:
        def t(key, lang=None, **kwargs):
            return key
        def assistant_not_init_detail(lang=None):
            return "Assistant not initialized"

# Module logger
logger = logging.getLogger(__name__)

# Sentinel: "argument not passed" (so we can tell it from an explicit None)
_UNSET = object()


# === Logging setup ===
def setup_logging(config: Config) -> logging.Logger:
    """
    Configure application logging.

    Logs are written to:
    - Console (stdout)
    - File logs/assistant.log

    Args:
        config: Configuration with the logging level.

    Returns:
        logging.Logger: Configured logger.
    """
    # Use the function from the config module for base setup
    config_setup_logging(config)
    
    # Create the logs directory
    log_dir = config.get_logs_dir()
    
    # Add a file handler
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
    Local AI assistant.

    The main application class combining all components.
    Manages the dialog lifecycle and coordinates module work.

    Request processing flow:
    1. User enters a message
    2. Search for relevant context in memory (RAG)
    3. Send request to LLM with context
    4. Receive and display the answer
    5. Voice the answer (if enabled)
    6. Save the dialog to memory

    Example usage:
        assistant = Assistant()
        await assistant.initialize()
        await assistant.run()
    """
    
    def __init__(self, config: Config | None = None):
        """
        Initialize the assistant.

        Args:
            config: Application configuration.
        """
        self._config = config or get_config()
        self._logger = logging.getLogger(__name__)

        # Components (initialized later)
        self._llm: LLMEngine | None = None
        self._memory: MemoryManager | None = None
        self._tts: TTSEngine | None = None

        # Running flag
        self._running = False
        self._closed = False

        # Session statistics
        self._message_count = 0
        self._start_time: datetime | None = None

        # Web search
        self._search_tool = None
        self._ddg_tool_def = None

        # Active persona (None -> standard system prompt)
        self._persona = None
    
    async def initialize(self) -> None:
        """
        Initialize all assistant components.

        Called once at startup.
        Sequentially initializes:
        1. LLM Engine (connection to Ollama)
        2. Memory Manager (ChromaDB loading)
        3. TTS Engine (optional)
        """
        self._logger.info("Initializing assistant...")
        self._start_time = datetime.now()

        # What is missing in models/, said before a feature needs it. The
        # resolvers only check that a folder exists, so a wrong or half-copied
        # one used to fail much later, inside transformers.
        from src.model_check import warn_about_models
        warn_about_models(self._config)
        
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

        # Apply the saved persona (if any)
        self.apply_persona()

        self._logger.info(
            f"Assistant ready. Model: {self._config.llm.model}, "
            f"Provider: {self._config.llm.provider.value}, "
            f"Memory: {self._config.chroma.persist_dir}"
        )

    @property
    def persona(self):
        """Currently active persona (None = standard prompt)."""
        return self._persona

    def memory_scopes(self) -> list[str] | None:
        """
        Memory scopes visible to the current conversation.

        Facts about the user live in the "user" scope and are shared by all
        personas; persona notes are isolated. No persona -> everything.
        """
        if not self._persona:
            return None
        return ["user", self._persona.id]

    def apply_persona(self, persona=_UNSET) -> None:
        """
        Activate a persona, or go back to the standard prompt.

        Args:
            persona: Persona object; None clears the persona. When the argument
                     is omitted, the persona is loaded from personas.json.
        """
        if persona is _UNSET:
            try:
                from src.personas import load, resolve_active
                persona = resolve_active(load())
            except Exception as e:
                self._logger.warning(f"Cannot load personas: {e}")
                persona = None

        self._persona = persona
        if persona is not None:
            self._llm.set_persona_prompt(persona.prompt_ru, persona.prompt_en)
            if persona.temperature is not None:
                try:
                    self._llm._config.temperature = persona.temperature
                except Exception:
                    pass
            self._logger.info(f"Persona applied: {persona.name} ({persona.id})")
        else:
            self._llm.set_persona_prompt("", "")
            self._logger.info("Persona cleared - standard system prompt")
    
    def _should_search_memory(self, message: str) -> bool:
        """
        Decide whether memory search is needed (extended logic).

        RAG runs when the message requires knowledge/context.
        """
        msg = message.strip().lower()
        
        # === Category 1: Explicit recall requests (100%) ===
        recall_keywords = [
            'помнишь', 'помни', 'remember', 'recall', 'ты знаешь', 'do you know',
            'было', 'was it', 'это было', 'is it was', 'как зовут', "what's my name",
            'моё имя', 'my name is', 'как меня зовут', 'what do you call me',
            'сохрани', 'запомни', 'keep in mind', 'не забудь',
        ]
        for kw in recall_keywords:
            if kw in msg:
                return True
        
        # === Category 2: Knowledge-seeking questions (100%) ===
        question_keywords = [
            'что такое', 'what is', 'кто такой', 'who is',
            'как работает', 'how does', 'explain', 'объясни',
            'расскажи про', 'tell me about', 'describe',
            'почему', 'why', 'зачем', 'for what',
            'чем отличается', 'difference between',
        ]
        # Question with a question mark
        if '?' in message:
            return True
        for kw in question_keywords:
            if kw in msg:
                return True
        
        # === Category 3: Temporal references to the past ===
        temporal_keywords = [
            'в прошлый раз', 'last time', 'раньше', 'earlier', 'before',
            'недавно', 'recently', 'на прошлой неделе', 'last week',
            'вчера', 'yesterday', 'на прошлой встрече', 'at our last',
        ]
        for kw in temporal_keywords:
            if kw in msg:
                return True
        
        # === Category 4: Contextual references (project/code) ===
        context_keywords = [
            'мой проект', 'my project', 'наш код', 'our code',
            'этот файл', 'that file', 'тот проект', 'that project',
            'текущий проект', 'current project', 'данный проект',
            'модель', 'model', 'конфигурация', 'config',
        ]
        for kw in context_keywords:
            if kw in msg:
                return True
        
        # === Category 5: Intent/clarification verbs ===
        intent_keywords = [
            'проверь', 'check', 'посмотри', 'look',
            'какой', 'which', 'сколько', 'how many', 'how much',
            'найди', 'find', 'покажи', 'show me',
        ]
        for kw in intent_keywords:
            if kw in msg:
                return True
        
        # === EXCLUSIONS - when RAG is NOT needed ===

        # Very short messages (except if there are explicit markers)
        if len(message.strip()) < 15:
            # Still check for explicit markers above
            pass  # Continue to exclusions
        
        # Greetings and simple phrases
        greetings = [
            'привет', 'здравствуй', 'здравствуйте', 'hello', 'hi', 'hey',
            'как дела', 'как ты', 'что делаешь', 'чем занимаешься',
            'пока', 'до свидания', 'спасибо', 'благодарю',
            'работает', 'есть кто', 'ты здесь',
        ]
        for greeting in greetings:
            if msg.startswith(greeting):
                return False
        
        # Simple time/weather questions without personal context
        simple_questions = [
            'который час', 'сколько времени', 'какая дата',
            'как погода', 'какой день', 'today date', 'current time',
        ]
        for q in simple_questions:
            if q in msg:
                return False
        
        # Message starting with "I ..." as new data without a request
        if msg.startswith('я ') or msg.startswith('я:'):
            # This is new information from the user, not a question
            return False
        
        # By default - search memory (better to overdo than to miss)
        return True
    
    def _looks_like_new_fact(self, message: str) -> bool:
        """
        Decide whether the message contains a new fact for extraction.

        Facts usually contain:
        - Personal information (name, age, city)
        - Preferences (favorite, likes, dislikes)
        - Self statements
        """
        msg = message.strip().lower()
        
        # Fact patterns
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
        
        # Check for fact patterns
        for pattern in fact_patterns:
            if pattern in msg:
                return True
        
        # Also check length - very long messages may contain facts
        if len(message.strip()) > 50:
            return True
        
        return False

    async def _register_tools(self) -> None:
        """
        Register available tools (Function Calling).
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
        """Get headers for API requests."""
        headers = {}
        if self._config.llm.requires_api_key:
            headers["Authorization"] = f"Bearer {self._config.llm.api_key}"
        if self._config.llm.provider.value == "openrouter":
            headers["HTTP-Referer"] = "http://localhost:8000"
            headers["X-Title"] = "Local AI Assistant"
        return headers
    
    async def close(self) -> None:
        """Close all components correctly."""
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
        Process a user message.

        Args:
            user_message: User message.
            thinking: Enable reasoning mode (for Qwen3).
            search: Enable web search.
            chat_history: Chat message history (list of dicts with role/content).
            images: List of base64-encoded images.

        Returns:
            LLMResponse: Assistant response with content and metadata.
        """
        if not self._llm or not self._memory:
            lang = get_config().general.language
            raise RuntimeError(assistant_not_init_detail(lang))

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
            context = await self._memory.search_context(user_message, scopes=self.memory_scopes())

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
        Process a user message (sync version for GUI).
        """
        import httpx
        
        if not self._llm or not self._memory:
            lang = get_config().general.language
            raise RuntimeError(assistant_not_init_detail(lang))

        self._message_count += 1

        # 1. Smart memory search (RAG)
        context = []
        if self._should_search_memory(user_message):
            context = asyncio.run(self._memory.search_context(user_message, scopes=self.memory_scopes()))
            
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
            
            # NOTE: memory context is merged into the single system message
            # because chat templates (e.g. Qwen3 via LM Studio) reject more
            # than one system message ("System message must be at the beginning").
            if context:
                context_text = "\n\n".join(context)
                if lang == "ru":
                    system_prompt += f"\n\n=== КОНТЕКСТ ИЗ ПАМЯТИ ===\n{context_text}\n=== КОНЕЦ КОНТЕКСТА ==="
                else:
                    system_prompt += f"\n\n=== MEMORY CONTEXT ===\n{context_text}\n=== END OF CONTEXT ==="

            messages = [
                {"role": "system", "content": system_prompt},
            ]
            
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

        # 3. Fact extraction (only if the message contains facts)
        if self._looks_like_new_fact(user_message):
            asyncio.run(self._extract_and_save_facts(user_message, answer))

        # 4. Add to LLM history
        self._llm.add_to_history(Message(role=MessageRole.USER, content=user_message))
        self._llm.add_to_history(Message(role=MessageRole.ASSISTANT, content=answer))

        return answer

    async def _extract_and_save_facts(self, user_message: str, assistant_response: str) -> None:
        """
        Extract important facts from the dialog and save to memory.

        Analyzes the dialog and saves only important information:
        - User name
        - Preferences (favorite color, food, etc.)
        - Personal facts (age, city, job)
        - Context for future conversations

        Args:
            user_message: User message.
            assistant_response: Assistant response.
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
                
                # Parse JSON
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
        Run the console dialog loop.

        Endless loop:
        - Read user input
        - Handle commands (quit, clear, help, stats)
        - Process messages via process_message
        - Print the answer

        Ends on 'quit' command or Ctrl+C.
        """
        if not self._llm:
            lang = get_config().general.language
            raise RuntimeError(assistant_not_init_detail(lang))
        
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
        Get input from the user.

        Async wrapper over input() for compatibility.

        Returns:
            str: Entered string.
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
        Handle a user command.

        Supported commands:
        - quit, exit, q: shutdown
        - clear, c: clear history
        - help, h: help
        - stats, s: statistics

        Args:
            text: Entered text.

        Returns:
            str | None: Command result or None if not a command.
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
        """Print the welcome message."""
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
        """Get the help text."""
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
        """Get the statistics text."""
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
    Application entry point.

    Configures logging, creates the assistant
    and runs the dialog loop (console or GUI).
    """
    # Load the configuration
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
    Run the graphical interface.

    Selects the framework based on the configuration.

    Args:
        assistant: Initialized Assistant instance.
    """
    framework = assistant._config.gui.framework.lower()
    
    if framework == "customtkinter":
        _run_customtkinter_gui(assistant)
    else:
        logger.warning(f"Unknown GUI framework: {framework}. Starting console mode.")
        asyncio.run(assistant.run())


def _run_customtkinter_gui(assistant: Assistant) -> None:
    """
    Run the CustomTkinter GUI.

    CustomTkinter runs in the main thread, so
    we just hand over control and finish the main process.

    Args:
        assistant: Initialized Assistant instance.
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
