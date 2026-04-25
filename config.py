"""
Конфигурация локального AI-ассистента.

Модуль использует pydantic-settings для валидации и загрузки настроек
из переменных окружения (.env файл).

Поддерживаемые LLM-провайдеры:
- ollama: Локальный Ollama сервер
- lm_studio: Локальный LM Studio сервер
- openrouter: OpenRouter API (облачный)

Пример использования:
    from config import get_config
    
    config = get_config()
    print(config.llm.provider)   # "ollama"
    print(config.llm.model)      # "qwen2.5:7b"
"""

import logging
from enum import Enum
from pathlib import Path
from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


# === Базовые классы конфигураций ===

class BaseConfig(BaseSettings):
    """
    Базовый класс для всех конфигураций.
    """
    
    model_config = SettingsConfigDict(
        extra="ignore",
        env_file=".env",
        env_file_encoding="utf-8",
    )


class LLMProvider(str, Enum):
    """
    Поддерживаемые LLM-провайдеры.
    
    Все провайдеры используют OpenAI-совместимый API:
    - ollama: http://localhost:11434/v1/chat/completions
    - lm_studio: http://localhost:1234/v1/chat/completions
    - openrouter: https://openrouter.ai/api/v1/chat/completions
    """
    OLLAMA = "ollama"
    LM_STUDIO = "lm_studio"
    OPENROUTER = "openrouter"


class LLMConfig(BaseConfig):
    """
    Универсальная конфигурация LLM-провайдера.
    
    Attributes:
        provider: Провайдер (ollama / lm_studio / openrouter)
        host: URL сервера (для локальных провайдеров)
        api_key: API-ключ (для OpenRouter)
        model: Название модели
        num_ctx: Максимальное количество токенов контекста
        temperature: Температура генерации (0.0-2.0)
    """
    
    provider: LLMProvider = Field(
        default=LLMProvider.OLLAMA,
        description="LLM провайдер: ollama / lm_studio / openrouter",
    )
    host: str = Field(
        default="http://localhost:11434",
        description="URL сервера (для локальных провайдеров)",
    )
    api_key: str = Field(
        default="",
        description="API-ключ (нужен для OpenRouter)",
    )
    model: str = Field(
        default="qwen2.5:7b",
        description="Модель для генерации ответов",
    )
    num_ctx: int = Field(
        default=4096,
        ge=512,
        le=32768,
        description="Максимальное количество токенов контекста",
    )
    temperature: float = Field(
        default=0.7,
        ge=0.0,
        le=2.0,
        description="Температура генерации (креативность)",
    )
    
    model_config = SettingsConfigDict(env_prefix="LLM_")
    
    @property
    def api_base_url(self) -> str:
        """
        Получить базовый URL API для текущего провайдера.
        
        Returns:
            str: URL для OpenAI-совместимого endpoint.
        """
        if self.provider == LLMProvider.OPENROUTER:
            return "https://openrouter.ai/api/v1"
        return f"{self.host}/v1"
    
    @property
    def requires_api_key(self) -> bool:
        """Проверить, нужен ли API-ключ для провайдера."""
        return self.provider == LLMProvider.OPENROUTER
    
    @property
    def is_local(self) -> bool:
        """Проверить, является ли провайдер локальным."""
        return self.provider in (LLMProvider.OLLAMA, LLMProvider.LM_STUDIO)
    
    async def check_thinking_support(self) -> bool:
        """
        Динамически проверить, поддерживает ли модель режим рассуждения.
        
        Делает запрос к Ollama API для получения информации о модели.
        """
        if self.provider != LLMProvider.OLLAMA:
            return False
        
        try:
            import httpx
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.post(
                    f"{self.host}/api/show",
                    json={"name": self.model}
                )
                if resp.status_code == 200:
                    data = resp.json()
                    capabilities = data.get("capabilities", {})
                    if "thinking" in capabilities:
                        return capabilities["thinking"] is True
                    details = data.get("details", {})
                    if "thinking" in details:
                        return details["thinking"] is True
                return False
        except Exception:
            return False
    
    @property
    def supports_thinking(self) -> bool:
        """Синхронная заглушка - используйте check_thinking_support() для async."""
        return False


class OllamaConfig(BaseConfig):
    """
    Устаревшая конфигурация Ollama (для обратной совместимости).
    """
    
    host: str = Field(default="http://localhost:11434")
    model: str = Field(default="qwen2.5:7b")
    num_ctx: int = Field(default=4096, ge=512, le=32768)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    
    model_config = SettingsConfigDict(env_prefix="OLLAMA_")


class ChromaConfig(BaseConfig):
    """Конфигурация ChromaDB."""
    
    persist_dir: str = Field(
        default="./storage/chroma",
        description="Директория для хранения ChromaDB",
    )
    collection_name: str = Field(
        default="assistant_memory",
        description="Название коллекции в ChromaDB",
    )
    
    model_config = SettingsConfigDict(env_prefix="CHROMA_")


class MemoryConfig(BaseConfig):
    """Конфигурация системы памяти."""
    
    max_context_messages: int = Field(
        default=20,
        ge=1,
        le=100,
        description="Максимум сообщений в контексте",
    )
    search_results: int = Field(
        default=3,
        ge=1,
        le=10,
        description="Количество результатов поиска в памяти",
    )
    similarity_threshold: float = Field(
        default=0.3,
        ge=0.0,
        le=1.0,
        description="Порог схожести для поиска в памяти",
    )
    
    model_config = SettingsConfigDict(env_prefix="MEMORY_")


class TTSConfig(BaseConfig):
    """Конфигурация Text-to-Speech."""
    
    enabled: bool = Field(default=False, description="Включить озвучку")
    model: str = Field(default="silero_v3", description="TTS модель")
    
    model_config = SettingsConfigDict(env_prefix="TTS_")


class LogConfig(BaseConfig):
    """Конфигурация логирования."""
    
    level: str = Field(default="INFO", description="Уровень логирования")
    
    @field_validator("level")
    @classmethod
    def validate_level(cls, v: str) -> str:
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        v_upper = v.upper()
        if v_upper not in valid_levels:
            raise ValueError(
                f"Неверный уровень логирования: {v}. "
                f"Допустимые: {valid_levels}"
            )
        return v_upper
    
    model_config = SettingsConfigDict(env_prefix="LOG_")


class GUIConfig(BaseConfig):
    """Конфигурация GUI."""
    
    enabled: bool = Field(default=True, description="Включить GUI")
    framework: str = Field(default="customtkinter", description="GUI фреймворк")
    theme: str = Field(default="dark", description="Тема оформления")
    title: str = Field(default="Local AI Assistant", description="Заголовок окна")
    width: int = Field(default=900, ge=400, le=2560, description="Ширина окна")
    height: int = Field(default=600, ge=300, le=1440, description="Высота окна")
    
    model_config = SettingsConfigDict(env_prefix="GUI_")


# === Основная конфигурация ===

class Config(BaseSettings):
    """
    Основная конфигурация приложения.
    """
    
    base_dir: Path = Field(
        default_factory=lambda: Path(__file__).parent,
        description="Корневая директория проекта",
    )
    
    llm: LLMConfig = Field(
        default_factory=LLMConfig,
        description="Настройки LLM провайдера",
    )
    ollama: OllamaConfig = Field(
        default_factory=OllamaConfig,
        description="Настройки Ollama (обратная совместимость)",
    )
    chroma: ChromaConfig = Field(
        default_factory=ChromaConfig,
        description="Настройки ChromaDB",
    )
    memory: MemoryConfig = Field(
        default_factory=MemoryConfig,
        description="Настройки системы памяти",
    )
    tts: TTSConfig = Field(
        default_factory=TTSConfig,
        description="Настройки TTS",
    )
    log: LogConfig = Field(
        default_factory=LogConfig,
        description="Настройки логирования",
    )
    gui: GUIConfig = Field(
        default_factory=GUIConfig,
        description="Настройки GUI",
    )
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )
    
    def get_storage_dir(self) -> Path:
        storage_path = Path(self.chroma.persist_dir)
        if not storage_path.is_absolute():
            storage_path = self.base_dir / storage_path
        storage_path.mkdir(parents=True, exist_ok=True)
        return storage_path
    
    def get_logs_dir(self) -> Path:
        logs_dir = self.base_dir / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        return logs_dir


# === Глобальная функция получения конфигурации ===

@lru_cache()
def get_config() -> Config:
    """
    Получить глобальный объект конфигурации (кэшируется).
    """
    return Config()


def reload_config() -> Config:
    """Перезагрузить конфигурацию (очистить кэш)."""
    get_config.cache_clear()
    return get_config()


# === Утилита для настройки логирования ===

def setup_logging(config: Config | None = None) -> None:
    """Настроить логирование на основе конфигурации."""
    if config is None:
        config = get_config()
    
    numeric_level = getattr(logging, config.log.level.upper(), logging.INFO)
    
    logging.basicConfig(
        level=numeric_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    
    logger = logging.getLogger(__name__)
    logger.info(f"Логирование настроено: уровень {config.log.level}")
