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
    
    async def initialize(self) -> None:
        """
        Инициализировать все компоненты ассистента.
        
        Вызывается один раз при старте.
        Последовательно инициализирует:
        1. LLM Engine (подключение к Ollama)
        2. Memory Manager (загрузка ChromaDB)
        3. TTS Engine (опционально)
        """
        self._logger.info("Инициализация ассистента...")
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
        
        # Регистрируем инструменты (Function Calling заглушка)
        await self._register_tools()
        
        self._logger.info(
            f"Ассистент готов. Модель: {self._config.llm.model}, "
            f"Провайдер: {self._config.llm.provider.value}, "
            f"Память: {self._config.chroma.persist_dir}"
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
        
        Заглушка для будущей реализации.
        """
        if not self._llm:
            return
        
        self._logger.debug("Инструменты зарегистрированы (заглушка)")
    
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
        
        self._logger.info("Завершение работы ассистента...")
        
        if self._tts:
            await self._tts.close()
        
        if self._memory:
            await self._memory.close()
        
        if self._llm:
            await self._llm.close()
        
        if self._start_time:
            duration = datetime.now() - self._start_time
            self._logger.info(
                f"Сессия завершена. Сообщений: {self._message_count}, "
                f"Длительность: {duration}"
            )
    
    async def process_message(self, user_message: str, thinking: bool = False) -> str:
        """
        Обработать сообщение пользователя.

        Args:
            user_message: Сообщение пользователя.
            thinking: Включить режим рассуждения (для Qwen3).

        Returns:
            str: Ответ ассистента.
        """
        if not self._llm or not self._memory:
            raise RuntimeError("Ассистент не инициализирован")

        self._message_count += 1

        # 1. Умный поиск контекста в памяти (RAG)
        context = []
        if self._should_search_memory(user_message):
            self._logger.debug(f"Поиск контекста для: {user_message[:50]}...")
            context = await self._memory.search_context(user_message)
            
            if context:
                self._logger.info(f"Найдено {len(context)} записей в памяти")
            else:
                self._logger.debug("Контекст не найден")
        else:
            self._logger.debug("RAG пропущен (приветствие/короткое сообщение)")

        # 2. Генерация ответа через LLM
        self._logger.debug("Генерация ответа...")
        response: LLMResponse = await self._llm.generate(
            user_message=user_message,
            additional_context=context,
            thinking=thinking,
        )

        answer = response.content

        # 3. Озвучка ответа (если включено)
        if self._tts and self._config.tts.enabled:
            self._logger.debug("Озвучка ответа...")
            await self._tts.speak(answer)

        # 4. Извлечение фактов (только если сообщение содержит факты)
        if self._looks_like_new_fact(user_message):
            await self._extract_and_save_facts(user_message, answer)

        # 5. Добавляем в историю LLM
        self._llm.add_to_history(Message(role=MessageRole.USER, content=user_message))
        self._llm.add_to_history(Message(role=MessageRole.ASSISTANT, content=answer))

        return answer

    def process_message_sync(self, user_message: str, thinking: bool = False) -> str:
        """
        Обработать сообщение пользователя (синхронная версия для GUI).
        """
        import httpx
        
        if not self._llm or not self._memory:
            raise RuntimeError("Ассистент не инициализирован")

        self._message_count += 1

        # 1. Умный поиск контекста в памяти (RAG)
        context = []
        if self._should_search_memory(user_message):
            context = asyncio.run(self._memory.search_context(user_message))
            
            if context:
                self._logger.info(f"Найдено {len(context)} записей в памяти")
            else:
                self._logger.debug("Контекст не найден")
        else:
            self._logger.debug("RAG пропущен (приветствие/короткое сообщение)")

        # 2. Генерация ответа через LLM
        self._logger.debug("Генерация ответа...")
        
        answer = ""
        with httpx.Client(
            base_url=self._config.llm.api_base_url,
            timeout=60.0,
            headers=self._get_api_headers(),
        ) as sync_client:
            system_prompt = self._llm._system_prompt
            history = self._llm.get_history()
            
            messages = [
                {"role": "system", "content": system_prompt},
            ]
            
            if context:
                context_text = "\n\n".join(context)
                messages.append({
                    "role": "system",
                    "content": f"=== КОНТЕКСТ ИЗ ПАМЯТИ ===\n{context_text}\n=== КОНЕЦ КОНТЕКСТА ==="
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
        # Промпт для извлечения фактов
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
        
        try:
            import httpx
            import json
            
            sync_client = httpx.Client(
                base_url=self._config.llm.api_base_url,
                timeout=30.0,
                headers=self._get_api_headers(),
            )
            
            try:
                messages = [
                    {"role": "system", "content": "Ты помощник для извлечения фактов. Возвращай ТОЛЬКО JSON список фактов или пустой список."},
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
                    # Сохраняем каждый факт
                    for fact in facts:
                        if fact and len(fact.strip()) > 5:
                            await self._memory.save_fact(fact.strip(), category="personal")
                            self._logger.info(f"Сохранён факт: {fact[:50]}...")
                
            finally:
                sync_client.close()
                
        except Exception as e:
            self._logger.debug(f"Не удалось извлечь факты: {e}")

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
            raise RuntimeError("Ассистент не инициализирован. Вызовите initialize().")
        
        self._running = True
        self._print_welcome()
        
        try:
            while self._running:
                # Читаем ввод пользователя
                try:
                    user_input = await self._get_input()
                except EOFError:
                    # Ctrl+D
                    break
                
                # Обрабатываем команды
                command_result = await self._handle_command(user_input)
                if command_result:
                    print(command_result)
                    if command_result == "exit":
                        break
                    continue
                
                # Пропускаем пустые сообщения
                if not user_input.strip():
                    continue
                
                # Обрабатываем сообщение
                print("\n🤖 Ассистент печатает...", end="\r")
                answer = await self.process_message(user_input.strip())
                print(" " * 50, end="\r")  # Очищаем строку
                
                # Выводим ответ
                print(f"\n🤖 {answer}\n")
        
        except KeyboardInterrupt:
            # Ctrl+C
            print("\n\nПрервано пользователем")
        finally:
            await self.close()
    
    async def _get_input(self) -> str:
        """
        Получить ввод от пользователя.
        
        Асинхронная обёртка над input() для совместимости.
        
        Returns:
            str: Введённая строка.
        """
        # В Windows input() блокирующий, используем sync
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: input("👤 Вы: "),
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
            return "exit"
        
        elif text_lower in ("clear", "c", "очистить"):
            if self._llm:
                self._llm.clear_history()
            return "🧹 История диалога очищена"
        
        elif text_lower in ("help", "h", "помощь"):
            return self._get_help_text()
        
        elif text_lower in ("stats", "s", "статистика"):
            return await self._get_stats_text()
        
        return None
    
    def _print_welcome(self) -> None:
        """Вывести приветственное сообщение."""
        print("\n" + "=" * 60)
        print("🤖 LOCAL AI ASSISTANT")
        print("=" * 60)
        print(f"Модель: {self._config.llm.model}")
        print(f"Провайдер: {self._config.llm.provider.value}")
        print(f"Память: {self._config.chroma.persist_dir}")
        print(f"TTS: {'ВКЛ' if self._config.tts.enabled else 'ВЫКЛ'}")
        print("-" * 60)
        print("Команды: help (помощь), clear (очистить), stats (статистика), quit (выход)")
        print("=" * 60 + "\n")
    
    def _get_help_text(self) -> str:
        """Получить текст справки."""
        return """
📖 СПРАВКА

Команды:
  quit, exit, q     - Выход из ассистента
  clear, c          - Очистить историю диалога
  stats, s          - Показать статистику
  help, h           - Эта справка

Просто введите сообщение для начала диалога.
"""
    
    async def _get_stats_text(self) -> str:
        """Получить текст статистики."""
        stats = {
            "Сообщений в сессии": self._message_count,
            "Время работы": str(datetime.now() - self._start_time) if self._start_time else "N/A",
        }
        
        if self._memory:
            memory_stats = await self._memory.get_stats()
            stats["Записей в памяти"] = memory_stats.get("total_entries", "N/A")
        
        lines = ["\n📊 СТАТИСТИКА"]
        for key, value in stats.items():
            lines.append(f"  {key}: {value}")
        
        return "\n".join(lines)


async def main() -> None:
    """
    Точка входа приложения.

    Настраивает логирование, создаёт ассистента
    и запускает цикл диалога (консоль или GUI).
    """
    # Загружаем конфигурацию
    config = get_config()

    # Настраиваем логирование
    logger = setup_logging(config)
    logger.info("Запуск Local AI Assistant...")

    # Создаём и инициализируем ассистента
    assistant = Assistant(config)

    try:
        await assistant.initialize()

        # Выбираем режим: GUI или консоль
        if config.gui.enabled:
            logger.info(f"Запуск GUI режима: {config.gui.title}")
            # Запускаем GUI в отдельном потоке
            _run_gui_mode(assistant)
        else:
            logger.info("Запуск консольного режима")
            await assistant.run()

    except Exception as e:
        logger.error(f"Критическая ошибка: {e}", exc_info=True)
        raise
    finally:
        # Гарантируем закрытие ресурсов
        await assistant.close()

    logger.info("Приложение завершено")


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
    elif framework == "flet":
        _run_flet_gui(assistant)
    else:
        logger.warning(f"Неизвестный GUI фреймворк: {framework}. Запуск консольного режима.")
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
    logger.info("Запуск CustomTkinter GUI")
    run_gui(assistant)


def _run_flet_gui(assistant: Assistant) -> None:
    """
    Запустить GUI на Flet в отдельном процессе.
    
    Args:
        assistant: Инициализированный экземпляр Assistant.
    """
    import multiprocessing as mp
    
    # Сериализуем данные для передачи в процесс
    config_dict = {
        'llm_provider': assistant._config.llm.provider.value,
        'llm_host': assistant._config.llm.host,
        'llm_api_key': assistant._config.llm.api_key,
        'llm_model': assistant._config.llm.model,
        'llm_num_ctx': assistant._config.llm.num_ctx,
        'llm_temperature': assistant._config.llm.temperature,
        'chroma_persist_dir': assistant._config.chroma.persist_dir,
        'chroma_collection': assistant._config.chroma.collection_name,
        'memory_max_context': assistant._config.memory.max_context_messages,
        'memory_search_results': assistant._config.memory.search_results,
        'memory_similarity_threshold': assistant._config.memory.similarity_threshold,
        'tts_enabled': assistant._config.tts.enabled,
        'gui_title': assistant._config.gui.title,
        'gui_theme': assistant._config.gui.theme,
        'gui_width': assistant._config.gui.width,
        'gui_height': assistant._config.gui.height,
    }

    # Запускаем GUI в отдельном процессе
    gui_process = mp.Process(target=_flet_gui_process_entry, args=(config_dict,))
    gui_process.start()
    gui_process.join()


def _flet_gui_process_entry(config_dict: dict) -> None:
    """
    Точка входа для GUI процесса Flet.

    Создаёт новый Assistant и запускает GUI.

    Args:
        config_dict: Словарь конфигурации.
    """
    import flet as ft
    from config import Config, LLMConfig, LLMProvider, ChromaConfig, MemoryConfig, TTSConfig, GUIConfig
    from src.main import Assistant
    from src.gui import create_gui_page

    provider = LLMProvider(config_dict['llm_provider'])
    
    config = Config(
        llm=LLMConfig(
            provider=provider,
            host=config_dict['llm_host'],
            api_key=config_dict['llm_api_key'],
            model=config_dict['llm_model'],
            num_ctx=config_dict['llm_num_ctx'],
            temperature=config_dict['llm_temperature'],
        ),
        chroma=ChromaConfig(
            persist_dir=config_dict['chroma_persist_dir'],
            collection_name=config_dict['chroma_collection'],
        ),
        memory=MemoryConfig(
            max_context_messages=config_dict['memory_max_context'],
            search_results=config_dict['memory_search_results'],
            similarity_threshold=config_dict['memory_similarity_threshold'],
        ),
        tts=TTSConfig(
            enabled=config_dict['tts_enabled'],
        ),
        gui=GUIConfig(
            title=config_dict['gui_title'],
            theme=config_dict['gui_theme'],
            width=config_dict['gui_width'],
            height=config_dict['gui_height'],
        ),
    )

    # Создаём и инициализируем ассистента в новом event loop
    async def create_assistant():
        assistant = Assistant(config)
        await assistant.initialize()
        return assistant

    import asyncio
    assistant = asyncio.run(create_assistant())

    # Создаём и запускаем GUI
    page_handler = create_gui_page(assistant)
    ft.run(page_handler)


if __name__ == "__main__":
    # Запускаем асинхронный цикл
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nДо свидания!")
