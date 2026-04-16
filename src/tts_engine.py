"""
TTS Engine - Движок синтеза речи (Text-to-Speech).

Модуль предоставляет абстрактный интерфейс для озвучки ответов ассистента.
В текущей реализации — заглушка, готовая к расширению.

Архитектурные решения:
1. Абстрактный базовый класс ITTSEngine позволяет легко добавить
   любую TTS библиотеку (pyttsx3, Silero, Coqui, ElevenLabs API).
2. Асинхронный интерфейс не блокирует основной поток.
3. Кэширование аудио для повторных фраз (оптимизация).

Планы расширения:
- Silero TTS: локальная нейросетевая модель (качественный русский язык)
- pyttsx3: оффлайн TTS через системные голоса
- ElevenLabs API: премиум качество через API

Пример использования:
    tts = TTSEngine()
    await tts.initialize()
    
    # Озвучить текст
    await tts.speak("Привет, я ваш ассистент!")
    
    # Сохранить в файл
    await tts.save_to_file("Текст", "output.wav")
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from config import get_config, TTSConfig


logger = logging.getLogger(__name__)


@dataclass
class AudioResult:
    """
    Результат синтеза речи.
    
    Attributes:
        success: Успешность операции
        audio_data: Опционально, бинарные данные аудио (bytes)
        file_path: Опционально, путь к сохранённому файлу
        duration_ms: Длительность аудио в миллисекундах
        error: Сообщение об ошибке если failed
    """
    success: bool
    audio_data: Optional[bytes] = None
    file_path: Optional[Path] = None
    duration_ms: int = 0
    error: Optional[str] = None


class ITTSEngine(ABC):
    """
    Абстрактный интерфейс TTS движка.
    
    Позволяет заменить реализацию без изменения кода ассистента.
    """
    
    @abstractmethod
    async def initialize(self) -> None:
        """Инициализировать TTS движок."""
        pass
    
    @abstractmethod
    async def speak(self, text: str) -> AudioResult:
        """
        Озвучить текст (воспроизвести через динамики).
        
        Args:
            text: Текст для озвучки.
        
        Returns:
            AudioResult: Результат операции.
        """
        pass
    
    @abstractmethod
    async def synthesize(self, text: str) -> AudioResult:
        """
        Синтезировать аудио без воспроизведения.
        
        Args:
            text: Текст для озвучки.
        
        Returns:
            AudioResult: Результат с audio_data.
        """
        pass
    
    @abstractmethod
    async def save_to_file(self, text: str, file_path: str | Path) -> AudioResult:
        """
        Сохранить аудио в файл.
        
        Args:
            text: Текст для озвучки.
            file_path: Путь к файлу.
        
        Returns:
            AudioResult: Результат с file_path.
        """
        pass
    
    @abstractmethod
    async def close(self) -> None:
        """Освободить ресурсы."""
        pass


class DummyTTSEngine(ITTSEngine):
    """
    Заглушка TTS движка.
    
    Используется по умолчанию когда TTS отключён в конфиге
    или как placeholder для будущей реализации.
    
    Логгирует все вызовы вместо реального синтеза.
    """
    
    def __init__(self):
        self._initialized = False
        self._call_count = 0
    
    async def initialize(self) -> None:
        """Инициализировать заглушку."""
        self._initialized = True
        logger.info("Dummy TTS Engine инициализирован (заглушка)")
    
    async def speak(self, text: str) -> AudioResult:
        """
        Заглушка воспроизведения.
        
        Просто логирует текст вместо озвучки.
        """
        if not self._initialized:
            return AudioResult(
                success=False,
                error="TTS Engine не инициализирован",
            )
        
        self._call_count += 1
        logger.info(f"[TTS Dummy] Текст для озвучки #{self._call_count}: {text[:50]}...")
        
        # Имитация задержки синтеза
        await asyncio.sleep(0.1)
        
        return AudioResult(
            success=True,
            duration_ms=100,
        )
    
    async def synthesize(self, text: str) -> AudioResult:
        """Заглушка синтеза."""
        if not self._initialized:
            return AudioResult(
                success=False,
                error="TTS Engine не инициализирован",
            )
        
        self._call_count += 1
        logger.debug(f"[TTS Dummy] Синтез: {text[:50]}...")
        
        return AudioResult(
            success=True,
            audio_data=b"",  # Пустые данные
            duration_ms=100,
        )
    
    async def save_to_file(self, text: str, file_path: str | Path) -> AudioResult:
        """Заглушка сохранения в файл."""
        if not self._initialized:
            return AudioResult(
                success=False,
                error="TTS Engine не инициализирован",
            )
        
        self._call_count += 1
        logger.info(f"[TTS Dummy] Сохранение в файл: {file_path}")
        
        return AudioResult(
            success=True,
            file_path=Path(file_path),
            duration_ms=100,
        )
    
    async def close(self) -> None:
        """Закрыть заглушку."""
        self._initialized = False
        logger.info("Dummy TTS Engine закрыт")


class Pyttsx3Engine(ITTSEngine):
    """
    TTS движок на основе pyttsx3.
    
    Оффлайн TTS с использованием системных голосов.
    Работает без интернета, но качество зависит от ОС.
    
    Для активации:
    1. Установить: pip install pyttsx3
    2. Раскомментировать использование в TTSEngine factory
    """
    
    def __init__(self, voice_name: str | None = None, rate: int = 150):
        """
        Инициализировать pyttsx3 движок.
        
        Args:
            voice_name: Имя голоса (None = голос по умолчанию)
            rate: Скорость речи (слова в минуту)
        """
        self._voice_name = voice_name
        self._rate = rate
        self._engine = None
        self._initialized = False
        
        # Кэш аудио (хеш текста -> audio data)
        self._cache: dict[str, bytes] = {}
    
    async def initialize(self) -> None:
        """Инициализировать pyttsx3."""
        import pyttsx3
        
        # pyttsx3 не асинхронный, запускаем в executor
        loop = asyncio.get_event_loop()
        self._engine = await loop.run_in_executor(
            None,
            lambda: pyttsx3.init(),
        )
        
        # Настраиваем голос
        if self._voice_name:
            self._engine.setProperty("voice", self._voice_name)
        self._engine.setProperty("rate", self._rate)
        
        self._initialized = True
        logger.info(f"Pyttsx3 TTS Engine инициализирован, голос: {self._voice_name or 'default'}")
    
    async def speak(self, text: str) -> AudioResult:
        """Озвучить текст через системные динамики."""
        if not self._initialized or not self._engine:
            return AudioResult(
                success=False,
                error="TTS Engine не инициализирован",
            )
        
        loop = asyncio.get_event_loop()
        
        try:
            # Блокирующий вызов в executor
            await loop.run_in_executor(None, lambda: self._engine.say(text))
            await loop.run_in_executor(None, lambda: self._engine.runAndWait())
            
            return AudioResult(
                success=True,
                duration_ms=len(text) * 50,  # Примерная длительность
            )
        except Exception as e:
            logger.error(f"Ошибка TTS: {e}")
            return AudioResult(
                success=False,
                error=str(e),
            )
    
    async def synthesize(self, text: str) -> AudioResult:
        """
        Синтезировать аудио.
        
        Примечание: pyttsx3 не поддерживает прямой экспорт в bytes,
        только воспроизведение или сохранение в файл.
        """
        logger.warning("Pyttsx3 не поддерживает synthesize(), используйте save_to_file()")
        return AudioResult(
            success=False,
            error="Pyttsx3 не поддерживает синтез в bytes",
        )
    
    async def save_to_file(self, text: str, file_path: str | Path) -> AudioResult:
        """Сохранить аудио в файл."""
        if not self._initialized or not self._engine:
            return AudioResult(
                success=False,
                error="TTS Engine не инициализирован",
            )
        
        loop = asyncio.get_event_loop()
        file_path = Path(file_path)
        
        try:
            # pyttsx3 не имеет прямого save, эмулируем через say
            # Для реального сохранения нужно использовать другие библиотеки
            logger.warning("Pyttsx3 требует доработки для save_to_file")
            
            return AudioResult(
                success=False,
                error="Pyttsx3 требует доработки для сохранения в файл",
            )
        except Exception as e:
            logger.error(f"Ошибка сохранения TTS: {e}")
            return AudioResult(
                success=False,
                error=str(e),
            )
    
    async def close(self) -> None:
        """Освободить ресурсы."""
        if self._engine:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, lambda: self._engine.stop())
        self._initialized = False
        logger.info("Pyttsx3 TTS Engine закрыт")


class TTSEngine:
    """
    Фасад для TTS движка.
    
    Автоматически выбирает реализацию на основе конфигурации
    и доступности библиотек.
    
    Пример использования:
        tts = TTSEngine()
        await tts.initialize()
        
        if config.tts.enabled:
            await tts.speak("Привет!")
    """
    
    def __init__(self, config: TTSConfig | None = None):
        """
        Инициализировать TTS фасад.
        
        Args:
            config: Конфигурация TTS.
        """
        self._config = config or get_config().tts
        self._engine: ITTSEngine | None = None
        self._initialized = False
    
    async def initialize(self) -> None:
        """
        Инициализировать TTS движок.
        
        Выбирает реализацию:
        - Если TTS_ENABLED=false: DummyTTSEngine
        - Если установлен pyttsx3: Pyttsx3Engine
        - Иначе: DummyTTSEngine
        """
        if self._initialized:
            return
        
        if not self._config.enabled:
            # TTS отключён — используем заглушку
            self._engine = DummyTTSEngine()
            logger.info("TTS отключён в конфигурации, используется заглушка")
        else:
            # Пытаемся использовать pyttsx3
            try:
                import pyttsx3
                self._engine = Pyttsx3Engine(voice_name=self._config.model)
                logger.info(f"Pyttsx3 доступен, используется для TTS (модель: {self._config.model})")
            except ImportError:
                logger.warning("pyttsx3 не установлен, используется заглушка")
                self._engine = DummyTTSEngine()
        
        await self._engine.initialize()
        self._initialized = True
    
    async def close(self) -> None:
        """Закрыть TTS движок."""
        if self._engine:
            await self._engine.close()
        self._initialized = False
    
    async def speak(self, text: str) -> AudioResult:
        """
        Озвучить текст.
        
        Args:
            text: Текст для озвучки.
        
        Returns:
            AudioResult: Результат операции.
        """
        if not self._initialized or not self._engine:
            return AudioResult(
                success=False,
                error="TTS Engine не инициализирован",
            )
        
        return await self._engine.speak(text)
    
    async def synthesize(self, text: str) -> AudioResult:
        """Синтезировать аудио без воспроизведения."""
        if not self._initialized or not self._engine:
            return AudioResult(
                success=False,
                error="TTS Engine не инициализирован",
            )
        
        return await self._engine.synthesize(text)
    
    async def save_to_file(self, text: str, file_path: str | Path) -> AudioResult:
        """Сохранить аудио в файл."""
        if not self._initialized or not self._engine:
            return AudioResult(
                success=False,
                error="TTS Engine не инициализирован",
            )
        
        return await self._engine.save_to_file(text, file_path)
    
    @property
    def is_enabled(self) -> bool:
        """Проверить включён ли TTS."""
        return self._config.enabled and self._initialized
    
    @property
    def is_dummy(self) -> bool:
        """Проверить используется ли заглушка."""
        return isinstance(self._engine, DummyTTSEngine)
