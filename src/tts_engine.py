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


class OmniVoiceEngine(ITTSEngine):
    """
    TTS движок на основе OmniVoice.
    
    Локальный нейросетевой TTS с поддержкой 600+ языков.
    Требует: pip install omnivoice
    """
    
    def __init__(self, model_path: str = None):
        if model_path is None:
            model_path = "E:\\My_Python_Projects\\OpenCode_test\\local_assistant\\llm-assistant-tauri\\src-tauri\\target\\release\\OmniVoice"
        self._model_path = model_path
        self._model = None
        self._device = "cuda"
        self._initialized = False
        
        # Конфигурация голоса
        self._mode = "instruct"  # "instruct" или "clone"
        self._instruct = "female"  # для instruct режима
        self._ref_audio_path = None  # для clone режима
        self._position_temperature = 0.0
        self._class_temperature = 0.0
        
        # Кеш транскрипций референсов (path -> transcription)
        self._ref_text_cache: dict[str, str] = {}
        
        # Папка с голосами
        self._voices_dir = Path("E:\\My_Python_Projects\\OpenCode_test\\local_assistant\\voices")
    
    def set_voice_config(self, mode: str = "instruct", 
                         instruct: str = "female",
                         ref_audio: str = None,
                         position_temperature: float = 0.0,
                         class_temperature: float = 0.0):
        """Настроить параметры голоса."""
        self._mode = mode
        self._instruct = instruct
        self._ref_audio_path = ref_audio
        self._position_temperature = position_temperature
        self._class_temperature = class_temperature
        
        # Если режим клона - транскрибируем референс и кешируем
        if mode == "clone" and ref_audio:
            self._ensure_ref_text_cached(ref_audio)
        
        mode_str = f"instruct={instruct}" if mode == "instruct" else f"clone={ref_audio}"
        logger.info(f"TTS голос настроен: mode={mode}, {mode_str}")
    
    def _ensure_ref_text_cached(self, ref_audio_path: str) -> None:
        """Транскрибировать референс и сохранить в кеш (если ещё не закеширован)."""
        if ref_audio_path in self._ref_text_cache:
            logger.info(f"Использую кеш транскрипции для: {ref_audio_path}")
            return
        
        if not self._whisper_model or not self._whisper_processor:
            logger.info("Локальная Whisper не загружена, пропускаю кеширование")
            return
        
        try:
            import librosa
            import torch
            
            logger.info(f"Транскрибирую референс (кеширование): {ref_audio_path}")
            
            # Загружаем аудио
            audio, sr = librosa.load(ref_audio_path, sr=16000)
            if audio.ndim > 1:
                audio = audio.mean(axis=1)
            audio = audio.astype('float32')
            
            # Транскрибируем
            input_features = self._whisper_processor(
                audio, 
                sampling_rate=16000, 
                return_tensors="pt"
            ).input_features
            
            if self._device == "cuda":
                input_features = input_features.half()
            input_features = input_features.to(self._device)
            
            forced_decoder_ids = self._whisper_processor.get_decoder_prompt_ids(language="russian", task="transcribe")
            predicted_ids = self._whisper_model.generate(input_features, forced_decoder_ids=forced_decoder_ids)
            transcription = self._whisper_processor.batch_decode(predicted_ids, skip_special_tokens=True)[0]
            
            # Сохраняем в кеш
            self._ref_text_cache[ref_audio_path] = transcription
            logger.info(f"Референс закеширован: {transcription[:50]}...")
            
        except Exception as e:
            logger.warning(f"Не удалось транскрибировать референс: {e}")
    
    def get_available_voices(self) -> list:
        """Получить список доступных голосов из папки voices/."""
        voices = []
        if not self._voices_dir.exists():
            logger.warning(f"Папка голосов не существует: {self._voices_dir}")
            return voices
        
        logger.info(f"Ищу голоса в: {self._voices_dir}")
        
        for f in self._voices_dir.iterdir():
            if f.suffix.lower() in ['.wav', '.mp3', '.ogg', '.flac']:
                logger.info(f"Найден голос: {f.name}")
                voices.append({
                    "name": f.stem,
                    "file": f.name,
                    "path": str(f),
                })
        
        logger.info(f"Всего найдено голосов: {len(voices)}")
        return voices
    
    async def initialize(self) -> None:
        """Инициализировать OmniVoice модель."""
        if self._initialized:
            return
        
        logger.info(f"Загрузка OmniVoice модели: {self._model_path}")
        
        try:
            import os
            
            # Добавляем FFmpeg в PATH для авто-транскрипции референса
            ffmpeg_bin = r"F:\ffmpeg\bin"
            if os.path.isdir(ffmpeg_bin) and ffmpeg_bin not in os.environ.get("PATH", ""):
                os.environ["PATH"] = ffmpeg_bin + ";" + os.environ.get("PATH", "")
                try:
                    os.add_dll_directory(ffmpeg_bin)
                except Exception:
                    pass
                logger.info(f"FFmpeg добавлен в PATH: {ffmpeg_bin}")
            
            # Офлайн режим - использовать только локальные файлы
            os.environ["TRANSFORMERS_OFFLINE"] = "1"
            os.environ["HF_HUB_OFFLINE"] = "1"
            os.environ["HF_DATASETS_OFFLINE"] = "1"
            
            import torch
            from omnivoice import OmniVoice
            
            # Загружаем OmniVoice
            dtype = torch.float16 if self._device == "cuda" else torch.float32
            
            self._model = OmniVoice.from_pretrained(
                self._model_path,
                device_map=self._device,
                dtype=dtype,
            )
            
            # Определяем устройство
            if torch.cuda.is_available():
                self._device = "cuda"
            else:
                self._device = "cpu"
            
            # Загружаем локальную Whisper для кеширования транскрипций
            whisper_path = "E:\\My_Python_Projects\\OpenCode_test\\local_assistant\\llm-assistant-tauri\\src-tauri\\target\\release\\openai_whisper-large-v3-turbo"
            try:
                from transformers import AutoModelForSpeechSeq2Seq, AutoProcessor
                logger.info(f"Загрузка локальной Whisper для кеширования: {whisper_path}")
                self._whisper_processor = AutoProcessor.from_pretrained(whisper_path, local_files_only=True)
                self._whisper_model = AutoModelForSpeechSeq2Seq.from_pretrained(
                    whisper_path, 
                    local_files_only=True,
                    torch_dtype=torch.float16 if self._device == "cuda" else torch.float32,
                )
                if self._device == "cuda":
                    self._whisper_model = self._whisper_model.to(self._device)
                logger.info("Локальная Whisper загружена для кеширования")
            except Exception as e:
                logger.warning(f"Не удалось загрузить локальную Whisper: {e}")
                self._whisper_model = None
                self._whisper_processor = None
            
            self._initialized = True
            logger.info(f"OmniVoice модель загружена на {self._device}")
            
        except ImportError:
            logger.error("omnivoice не установлен. Установите: pip install omnivoice")
            raise
        except Exception as e:
            logger.error(f"Ошибка загрузки OmniVoice: {e}")
            raise
    
    async def _transcribe_reference(self, audio_path: str) -> str:
        """Транскрибировать референсное аудио локальной Whisper."""
        try:
            import torch
            import librosa
            import numpy as np
            
            logger.info(f"Загрузка аудио: {audio_path}")
            audio, sr = librosa.load(audio_path, sr=16000)
            if audio.ndim > 1:
                audio = audio.mean(axis=1)
            audio = audio.astype(np.float32)
            
            input_features = self._whisper_processor(
                audio, 
                sampling_rate=16000, 
                return_tensors="pt"
            ).input_features
            
            if self._device == "cuda":
                input_features = input_features.half()
            input_features = input_features.to(self._device)
            
            forced_decoder_ids = self._whisper_processor.get_decoder_prompt_ids(language="russian", task="transcribe")
            
            predicted_ids = self._whisper_model.generate(
                input_features, 
                forced_decoder_ids=forced_decoder_ids
            )
            
            transcription = self._whisper_processor.batch_decode(predicted_ids, skip_special_tokens=True)[0]
            logger.info(f"Транскрипция: {transcription}")
            return transcription
            
        except Exception as e:
            logger.error(f"Ошибка транскрибации: {e}")
            return ""
    
    def _prepare_ref_audio(self, ref_path: str) -> str:
        """Конвертирует референс в формат, совместимый с OmniVoice (24kHz mono)."""
        import librosa
        import soundfile as sf
        import tempfile
        import numpy as np
        
        # Загружаем и ресемплим в 24 kHz mono
        audio, _ = librosa.load(ref_path, sr=24000, mono=True)
        audio = audio.astype(np.float32)
        audio = np.clip(audio, -1.0, 1.0)
        
        # Сохраняем во временный файл
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp_path = tmp.name
            sf.write(tmp_path, audio, 24000, format="WAV", subtype="FLOAT")
        
        logger.info(f"Референс подготовлен: {tmp_path}")
        return tmp_path
    
    async def speak(self, text: str) -> AudioResult:
        """Озвучить текст."""
        if not self._initialized or not self._model:
            return AudioResult(
                success=False,
                error="OmniVoice не инициализирован",
            )
        
        try:
            import torch
            import soundfile as sf
            import numpy as np
            import librosa
            import tempfile
            import os
            
            logger.info(f"OmniVoice синтез: {text[:50]}...")
            logger.info(f"Режим: mode={self._mode}, ref_audio={self._ref_audio_path}")
            
            loop = asyncio.get_event_loop()
            
            # Параметры генерации
            gen_params = {
                "text": text,
                "speed": 1.0,
                "position_temperature": self._position_temperature,
                "class_temperature": self._class_temperature,
            }
            
            ref_prepared_path = None
            
            # Используем референсное аудио или instruct
            if self._mode == "clone" and self._ref_audio_path:
                # Передаём референс напрямую (без librosa preprocessing)
                gen_params["ref_audio"] = self._ref_audio_path
                # Используем кешированную транскрипцию или None для авто-транскрипции
                cached_ref_text = self._ref_text_cache.get(self._ref_audio_path)
                gen_params["ref_text"] = cached_ref_text
                
                if cached_ref_text:
                    logger.info(f"Использую кешированную транскрипцию для {self._ref_audio_path}")
                else:
                    logger.info(f"Использую voice cloning: ref_audio (прямой файл) + ref_text=None (FFmpeg auto)")
                
                gen_params["num_step"] = 32
                gen_params["guidance_scale"] = 2.0
                gen_params["t_shift"] = 0.1
                gen_params["denoise"] = True
                gen_params["postprocess_output"] = True
                gen_params["language"] = "Russian"
                gen_params["seed"] = 12345
                logger.info(f"Использую voice cloning: ref_audio (прямой файл) + ref_text=None (FFmpeg auto)")
            else:
                gen_params["instruct"] = "female, low pitch,"
                gen_params["num_step"] = 32
                gen_params["guidance_scale"] = 2.0
                gen_params["t_shift"] = 0.1
                gen_params["denoise"] = True
                gen_params["postprocess_output"] = True
                gen_params["language"] = "Russian"
                gen_params["seed"] = 468556206
                logger.info(f"Использую voice design: female, low pitch, seed=468556206")
            
            # Генерируем аудио (в executor, чтобы не блокировать)
            audio = await loop.run_in_executor(
                None,
                lambda: self._model.generate(**gen_params)
            )
            
            # Очистка временного файла референса
            if ref_prepared_path and os.path.exists(ref_prepared_path):
                try:
                    os.unlink(ref_prepared_path)
                except Exception:
                    pass
            
            # audio - это list tensor или numpy, берём первый
            if isinstance(audio, list) and len(audio) > 0:
                audio_data = audio[0]
            else:
                audio_data = audio
            
            # Конвертируем в numpy array если torch tensor
            if hasattr(audio_data, 'cpu'):
                audio_np = audio_data.cpu().numpy()
            else:
                audio_np = np.array(audio_data)
            
            logger.info(f"Аудио форма: shape={audio_np.shape}, dtype={audio_np.dtype}, min={audio_np.min():.4f}, max={audio_np.max():.4f}")
            
            # Убедимся что 1D массив
            if audio_np.ndim > 1:
                audio_np = audio_np.flatten()
                logger.info(f"После flatten: shape={audio_np.shape}")
            
            # Нормализуем аудио
            audio_np = audio_np.astype(np.float32)
            max_val = np.abs(audio_np).max()
            logger.info(f"До нормализации: max={max_val:.4f}")
            if max_val > 0:
                audio_np = audio_np / max_val
            
            logger.info(f"После нормализации: min={audio_np.min():.4f}, max={audio_np.max():.4f}")
            
            # Сохраняем во временный файл и на диск для проверки
            import tempfile
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
                temp_path = f.name
            
            # Также сохраняем в постоянную папку для проверки
            import datetime
            debug_path = f"E:\\My_Python_Projects\\OpenCode_test\\local_assistant\\debug_tts\\tts_{datetime.datetime.now().strftime('%H%M%S')}.wav"
            import os
            os.makedirs(os.path.dirname(debug_path), exist_ok=True)
            
            # Сохраняем 24kHz аудио
            sf.write(temp_path, audio_np, 24000)
            sf.write(debug_path, audio_np, 24000)
            logger.info(f"WAV сохранён: {temp_path}")
            logger.info(f"DEBUG WAV сохранён: {debug_path}")
            
            # Читаем файл
            with open(temp_path, 'rb') as f:
                audio_bytes = f.read()
            
            # Удаляем временный файл
            import os
            os.remove(temp_path)
            
            # Очищаем память GPU после генерации
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            
            # Принудительная сборка мусора
            import gc
            gc.collect()
            
            duration_ms = int(len(audio_bytes) / 2.4)  # Приблизительно для 24kHz 16bit
            
            logger.info(f"OmniVoice: аудио сгенерировано, {len(audio_bytes)} байт")
            
            return AudioResult(
                success=True,
                audio_data=audio_bytes,
                duration_ms=duration_ms,
            )
            
        except Exception as e:
            logger.error(f"Ошибка OmniVoice TTS: {e}")
            return AudioResult(
                success=False,
                error=str(e),
            )
    
    async def synthesize(self, text: str) -> bytes:
        """Синтезировать аудио и вернуть bytes."""
        result = await self.speak(text)
        if result.success and result.audio_data:
            return result.audio_data
        raise RuntimeError(result.error or "Синтез не удался")
    
    async def save_to_file(self, text: str, file_path: str) -> AudioResult:
        """Сохранить аудио в файл."""
        result = await self.speak(text)
        if not result.success:
            return result
        
        try:
            with open(file_path, 'wb') as f:
                f.write(result.audio_data)
            
            return AudioResult(
                success=True,
                file_path=Path(file_path),
                duration_ms=result.duration_ms,
            )
        except Exception as e:
            return AudioResult(
                success=False,
                error=str(e),
            )
    
    async def close(self) -> None:
        """Закрыть и освободить модель."""
        if self._model:
            del self._model
            self._model = None
        self._initialized = False
        logger.info("OmniVoice модель выгружена из памяти")


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
        
        # Сохранённый конфиг голоса для применения при включении
        self._voice_mode = "instruct"
        self._voice_instruct = "female"
        self._voice_ref_audio = None
    
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
    
    async def enable_omnivoice(self) -> bool:
        """
        Включить OmniVoice TTS.
        Загружает модель в память при первом вызове.
        """
        if self._engine and not isinstance(self._engine, DummyTTSEngine):
            logger.info("OmniVoice уже загружен")
            return True
        
        try:
            # Закрываем текущий движок
            if self._engine:
                await self._engine.close()
            
            # Создаём OmniVoice движок
            self._engine = OmniVoiceEngine()
            await self._engine.initialize()
            self._initialized = True
            
            # Применяем сохранённый конфиг голоса
            self._engine.set_voice_config(
                mode=self._voice_mode,
                instruct=self._voice_instruct,
                ref_audio=self._voice_ref_audio,
                position_temperature=0.0,
                class_temperature=0.0,
            )
            logger.info(f"Применён конфиг: mode={self._voice_mode}, ref={self._voice_ref_audio}")
            
            logger.info("OmniVoice TTS включён и загружен в память")
            return True
            
        except Exception as e:
            logger.error(f"Не удалось включить OmniVoice: {e}")
            self._engine = DummyTTSEngine()
            await self._engine.initialize()
            return False
    
    async def disable_omnivoice(self) -> bool:
        """
        Выключить OmniVoice TTS.
        Выгружает модель из памяти.
        """
        if self._engine:
            await self._engine.close()
        
        self._engine = DummyTTSEngine()
        await self._engine.initialize()
        self._initialized = True
        
        logger.info("OmniVoice TTS выключён и выгружен из памяти")
        return True
    
    def set_voice_config(self, mode: str = "instruct",
                         instruct: str = "female",
                         ref_audio: str = None,
                         position_temperature: float = 0.0,
                         class_temperature: float = 0.0):
        """Сохранить конфигурацию голоса."""
        self._voice_mode = mode
        self._voice_instruct = instruct
        self._voice_ref_audio = ref_audio
        
        # Применяем к текущему движку если это OmniVoice
        if hasattr(self._engine, 'set_voice_config'):
            self._engine.set_voice_config(
                mode=mode,
                instruct=instruct,
                ref_audio=ref_audio,
                position_temperature=position_temperature,
                class_temperature=class_temperature,
            )
        
        logger.info(f"TTS конфиг сохранён: mode={mode}, instruct={instruct}, ref_audio={ref_audio}")
    
    @property
    def is_omnivoice_loaded(self) -> bool:
        """Проверить загружен ли OmniVoice."""
        return isinstance(self._engine, OmniVoiceEngine) and self._initialized
