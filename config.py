"""
Local AI assistant configuration.

This module uses pydantic-settings to validate and load settings
from environment variables (.env file).

Supported LLM providers:
- ollama: local Ollama server
- lm_studio: local LM Studio server
- openrouter: OpenRouter API (cloud)

Usage example:
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


# === Base configuration classes ===

class BaseConfig(BaseSettings):
    """
    Base class for all configurations.
    """
    
    model_config = SettingsConfigDict(
        extra="ignore",
        env_file=".env",
        env_file_encoding="utf-8",
    )


class LLMProvider(str, Enum):
    """
    Supported LLM providers.

    All providers use an OpenAI-compatible API:
    - ollama: http://localhost:11434/v1/chat/completions
    - lm_studio: http://localhost:1234/v1/chat/completions
    - openrouter: https://openrouter.ai/api/v1/chat/completions
    """
    OLLAMA = "ollama"
    LM_STUDIO = "lm_studio"
    OPENROUTER = "openrouter"


class LLMConfig(BaseConfig):
    """
    Universal LLM provider configuration.

    Attributes:
        provider: Provider (ollama / lm_studio / openrouter)
        host: Server URL (for local providers)
        api_key: API key (for OpenRouter)
        model: Model name
        num_ctx: Maximum number of context tokens
        temperature: Generation temperature (0.0-2.0)
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
        default="",
        description="Модель для генерации ответов",
    )
    num_ctx: int = Field(
        default=8192,
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
        Get the base API URL for the current provider.
        """
        if self.provider == LLMProvider.OPENROUTER:
            return "https://openrouter.ai/api/v1"
        elif self.provider == LLMProvider.LM_STUDIO:
            if "localhost" in self.host and ":" not in self.host:
                return "http://localhost:1234/v1"
            return f"{self.host}/v1"
        else:
            # Ollama - without /v1
            return self.host
    
    @property
    def requires_api_key(self) -> bool:
        """Check whether the provider requires an API key."""
        return self.provider == LLMProvider.OPENROUTER
    
    @property
    def is_local(self) -> bool:
        """Check whether the provider is local."""
        return self.provider in (LLMProvider.OLLAMA, LLMProvider.LM_STUDIO)
    
    async def check_thinking_support(self) -> bool:
        """
        Dynamically check whether the model supports reasoning mode.

        Queries the Ollama API for model information.
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
        """Sync stub - use check_thinking_support() for async."""
        return False


class OllamaConfig(BaseConfig):
    """
    Legacy Ollama configuration (for backward compatibility).
    """
    
    host: str = Field(default="http://localhost:11434")
    model: str = Field(default="qwen2.5:7b")
    num_ctx: int = Field(default=8192, ge=512, le=32768)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    
    model_config = SettingsConfigDict(env_prefix="OLLAMA_")


class ChromaConfig(BaseConfig):
    """ChromaDB configuration."""
    
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
    """Memory system configuration."""
    
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
    """Text-to-Speech configuration."""
    
    enabled: bool = Field(default=False, description="Включить озвучку")
    model: str = Field(default="silero_v3", description="TTS модель")
    steps: int = Field(default=64, ge=16, le=128, description="Шаги генерации")
    temperature: float = Field(default=1.0, ge=0.0, le=2.0, description="Temperature TTS")
    debug_save: bool = Field(default=False, description="Сохранять отладочные WAV в debug_tts/")

    model_config = SettingsConfigDict(env_prefix="TTS_")


class STTConfig(BaseConfig):
    """Speech-to-Text configuration."""

    model: str = Field(default="large-v3-turbo", description="Модель Whisper: алиас, 'owner/repo' или путь к папке")

    model_config = SettingsConfigDict(env_prefix="STT_")


class LogConfig(BaseConfig):
    """Logging configuration."""
    
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
    """GUI configuration."""
    
    enabled: bool = Field(default=True, description="Включить GUI")
    framework: str = Field(default="customtkinter", description="GUI фреймворк")
    theme: str = Field(default="dark", description="Тема оформления")
    title: str = Field(default="Local AI Assistant", description="Заголовок окна")
    width: int = Field(default=900, ge=400, le=2560, description="Ширина окна")
    height: int = Field(default=600, ge=300, le=1440, description="Высота окна")
    
    model_config = SettingsConfigDict(env_prefix="GUI_")


class ScreenConfig(BaseConfig):
    """Screenshot configuration."""
    
    enabled: bool = Field(default=True, description="Включить авто-скриншоты по триггерам")
    save_path: str = Field(default="./screenshots", description="Папка для сохранения скриншотов")
    monitor: int = Field(default=0, description="Монитор (0=все, 1,2...=конкретный)")
    triggers: str = Field(default="экран,скриншот,смотри на экран,покажи экран,что на экране,сделай скриншот", description="Триггеры через запятую")
    
    model_config = SettingsConfigDict(env_prefix="SCREENSHOT_")


class PersonalityConfig(BaseConfig):
    """Custom personality layer appended to the base system prompt."""

    ru: str = Field(default="", description="Дополнительные инструкции для русского промпта")
    en: str = Field(default="", description="Additional instructions for the English prompt")

    @field_validator("ru", "en", mode="before")
    @classmethod
    def unescape_newlines(cls, v):
        """.env is line-based, so newlines are stored escaped as \\n."""
        if isinstance(v, str) and "\\n" in v:
            return v.replace("\\n", "\n")
        return v

    model_config = SettingsConfigDict(env_prefix="PERSONALITY_")


class HotkeyConfig(BaseConfig):
    """Global hotkeys (read by the Tauri shell on startup)."""

    voice: str = Field(default="Ctrl+Shift+V", description="Голосовой ввод (Ctrl+Shift+V)")
    voice_num: str = Field(default="Ctrl+Num0", description="Голосовой ввод, доп. клавиша (Ctrl+Num0)")
    live: str = Field(default="Ctrl+Shift+L", description="Live-режим (Ctrl+Shift+L)")

    model_config = SettingsConfigDict(env_prefix="HOTKEY_", extra="ignore")


class WakeWordConfig(BaseConfig):
    """Wake-word settings for the background input mode.

    There is no `enabled` and no model of its own any more:

    * Whether the wake word runs is the input mode chosen on the slider, and
      that is session state - not persisted, so a launch never holds the
      microphone open or a model in VRAM behind the user's back.
    * The model comes from STTConfig. Both modes run the same weights, so the
      detector can borrow the instance speech recognition already loaded
      instead of holding a second copy of the same 1.5 GB.
    """

    phrase: str = Field(default="", description="Пробуждающая фраза, например «ассистент»")
    input_device: str = Field(
        default="",
        description="Микрофон для прослушивания: пусто = системный по умолчанию",
    )
    action: str = Field(
        # chat   - show the transcript, then run it (default: with a small
        #         detector, a wrong trigger is only explainable if visible)
        # execute - run it silently and show only the answer
        default="chat",
        description="Что делать при срабатывании: chat или execute",
    )
    cooldown: float = Field(default=5.0, description="Пауза после срабатывания, сек")
    match_threshold: float = Field(
        # 0.70, not the 0.82 this used to default to. Measured on this machine
        # (tests/check_wake_threshold.py): 25 ordinary utterances scored at most
        # 0.38 against 'ассистент', while a real microphone rendering of the same
        # word as 'Систент' scored 0.80. The old threshold rejected genuine
        # detections with more than a 2x margin to spare.
        default=0.70,
        description="Порог совпадения фразы (0-1)",
    )

    @field_validator("phrase")
    @classmethod
    def _check_phrase(cls, v: str) -> str:
        v = (v or "").strip()
        if len(v) > 64:
            raise ValueError("Пробуждающая фраза длиннее 64 символов")
        return v

    @field_validator("cooldown")
    @classmethod
    def _check_cooldown(cls, v: float) -> float:
        return max(0.0, min(300.0, float(v)))

    @field_validator("match_threshold")
    @classmethod
    def _check_threshold(cls, v: float) -> float:
        return max(0.1, min(1.0, float(v)))

    @field_validator("action")
    @classmethod
    def _check_action(cls, v: str) -> str:
        v = (v or "chat").strip().lower()
        if v not in ("chat", "execute"):
            raise ValueError("Действие wake-word: chat или execute")
        return v

    model_config = SettingsConfigDict(env_prefix="WAKE_", extra="ignore")


class GeneralConfig(BaseConfig):
    """General settings (interface language)."""
    
    language: str = Field(default="en", description="Язык интерфейса: en / ru")
    show_backend_console: bool = Field(default=False, description="Show external backend console window")
    
    @field_validator("language")
    @classmethod
    def validate_language(cls, v: str) -> str:
        v = v.lower().strip()
        if v not in {"en", "ru"}:
            raise ValueError(f"Invalid language: {v}. Allowed: en, ru")
        return v
    
    model_config = SettingsConfigDict(env_prefix="GENERAL_")


# === Main configuration ===

class Config(BaseSettings):
    """
    Main application configuration.
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
    stt: STTConfig = Field(
        default_factory=STTConfig,
        description="Настройки STT",
    )
    log: LogConfig = Field(
        default_factory=LogConfig,
        description="Настройки логирования",
    )
    gui: GUIConfig = Field(
        default_factory=GUIConfig,
        description="Настройки GUI",
    )
    screen: ScreenConfig = Field(
        default_factory=ScreenConfig,
        description="Настройки скриншотов",
    )
    general: GeneralConfig = Field(
        default_factory=GeneralConfig,
        description="Общие настройки",
    )
    personality: PersonalityConfig = Field(
        default_factory=PersonalityConfig,
        description="Настройки личности (дополнительный слой к системному промпту)",
    )
    hotkey: HotkeyConfig = Field(
        default_factory=HotkeyConfig,
        description="Глобальные горячие клавиши",
    )
    wake: WakeWordConfig = Field(
        default_factory=WakeWordConfig,
        description="Пробуждающая фраза (wake-word)",
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


# === Global configuration getter ===

@lru_cache()
def get_config() -> Config:
    """
    Get the global configuration object (cached).
    """
    return Config()


def reload_config() -> Config:
    """Reload the configuration (clear the cache)."""
    get_config.cache_clear()
    return get_config()


# === Logging setup utility ===

def setup_logging(config: Config | None = None) -> None:
    """Configure logging based on the configuration."""
    if config is None:
        config = get_config()
    
    numeric_level = getattr(logging, config.log.level.upper(), logging.INFO)
    
    logging.basicConfig(
        level=numeric_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    
    logger = logging.getLogger(__name__)
    logger.info(f"Logging configured: level {config.log.level}")


def save_config(
    provider: str = None,
    model: str = None,
    ollama_host: str = None,
    api_key: str = None,
    num_ctx: int = None,
    temperature: float = None,
    tts_steps: int = None,
    tts_temperature: float = None,
    memory_max_context: int = None,
    memory_search_results: int = None,
    memory_threshold: float = None,
    language: str = None,
    show_backend_console: bool | None = None,
    personality_ru: str | None = None,
    personality_en: str | None = None,
    stt_model: str | None = None,
    hotkey_voice: str | None = None,
    hotkey_voice_num: str | None = None,
    hotkey_live: str | None = None,
    wake_phrase: str | None = None,
    wake_input_device: str | None = None,
    wake_action: str | None = None,
    wake_cooldown: float | None = None,
    wake_threshold: float | None = None,
) -> None:
    """
    Save the configuration to the .env file.

    The written values are also mirrored into os.environ: the backend calls
    load_dotenv() at import time, and OS environment variables take priority
    over the .env file in pydantic-settings. Without the mirror, a settings
    change saved at runtime would never be picked up by reload_config().
    """
    import os
    from pathlib import Path

    env_path = Path(__file__).parent / ".env"
    
    # Read the current .env
    env_vars = {}
    if env_path.exists():
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and "=" in line:
                    key, value = line.split("=", 1)
                    env_vars[key] = value
    
    # Update the values
    if provider is not None:
        env_vars["LLM_PROVIDER"] = provider
    
    # Save the model only if it is not empty
    if model is not None and model != "":
        if provider == "ollama":
            env_vars["OLLAMA_MODEL"] = model
            env_vars["LLM_MODEL"] = model
        else:
            env_vars["LLM_MODEL"] = model
    
    if ollama_host is not None:
        env_vars["LLM_HOST"] = ollama_host
        if provider == "ollama":
            env_vars["OLLAMA_HOST"] = ollama_host
    
    if api_key is not None:
        env_vars["LLM_API_KEY"] = api_key
    
    if num_ctx is not None:
        env_vars["LLM_NUM_CTX"] = str(num_ctx)
        if provider == "ollama":
            env_vars["OLLAMA_NUM_CTX"] = str(num_ctx)
    
    if temperature is not None:
        env_vars["LLM_TEMPERATURE"] = str(temperature)
        if provider == "ollama":
            env_vars["OLLAMA_TEMPERATURE"] = str(temperature)
    
    if tts_steps is not None:
        env_vars["TTS_STEPS"] = str(tts_steps)
    
    if tts_temperature is not None:
        env_vars["TTS_TEMPERATURE"] = str(tts_temperature)
    
    if memory_max_context is not None:
        env_vars["MEMORY_MAX_CONTEXT_MESSAGES"] = str(memory_max_context)
    
    if memory_search_results is not None:
        env_vars["MEMORY_SEARCH_RESULTS"] = str(memory_search_results)
    
    if memory_threshold is not None:
        env_vars["MEMORY_SIMILARITY_THRESHOLD"] = str(memory_threshold)
    
    if language is not None:
        env_vars["GENERAL_LANGUAGE"] = language.lower().strip()

    if show_backend_console is not None:
        env_vars["GENERAL_SHOW_BACKEND_CONSOLE"] = "true" if show_backend_console else "false"

    if personality_ru is not None:
        env_vars["PERSONALITY_RU"] = personality_ru.replace("\r\n", "\n").replace("\n", "\\n")

    if personality_en is not None:
        env_vars["PERSONALITY_EN"] = personality_en

    if stt_model is not None and stt_model != "":
        env_vars["STT_MODEL"] = stt_model.strip()

    for key, val in (("HOTKEY_VOICE", hotkey_voice),
                     ("HOTKEY_VOICE_NUM", hotkey_voice_num),
                     ("HOTKEY_LIVE", hotkey_live)):
        if val is not None and val != "":
            env_vars[key] = val.strip().replace("\r\n", "\n").replace("\n", "\\n")

    if wake_phrase is not None:
        env_vars["WAKE_PHRASE"] = wake_phrase.strip()
    if wake_input_device is not None:
        # Empty is meaningful: it means "follow the system default".
        env_vars["WAKE_INPUT_DEVICE"] = wake_input_device.strip()
    if wake_action is not None:
        env_vars["WAKE_ACTION"] = wake_action.strip().lower()
    if wake_cooldown is not None:
        env_vars["WAKE_COOLDOWN"] = str(wake_cooldown)
    if wake_threshold is not None:
        env_vars["WAKE_MATCH_THRESHOLD"] = str(wake_threshold)
    
    # Write back
    with open(env_path, "w", encoding="utf-8") as f:
        for key, value in env_vars.items():
            f.write(f"{key}={value}\n")

    # Keep the process environment in sync with the file (see docstring)
    os.environ.update(env_vars)
