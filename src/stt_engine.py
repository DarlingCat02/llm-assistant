"""
STT Engine - Whisper для распознавания речи.

Использует модель Whisper Large V3 Turbo из локальной папки.
"""

import logging
from pathlib import Path
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)


class STTEngine:
    """
    STT движок на базе Whisper.
    """
    
    def __init__(self, model_path: Optional[str] = None):
        """
        Инициализировать STT движок.
        
        Args:
            model_path: Путь к папке с моделью Whisper. 
                        Если None - используется путь по умолчанию.
        """
        self._model_path = model_path
        self._model = None
        self._processor = None
        self._device = None
        self._initialized = False
    
    async def initialize(self) -> None:
        """Загрузить модель Whisper."""
        if self._initialized:
            return
        
        logger.info("Инициализация STT движка (Whisper)...")
        
        try:
            import torch
            from transformers import WhisperProcessor, WhisperForConditionalGeneration
            
            # Определяем устройство
            self._device = "cuda" if torch.cuda.is_available() else "cpu"
            logger.info(f"STT будет использовать: {self._device}")
            
            # Путь к модели
            if self._model_path is None:
                base_dir = Path(__file__).parent.parent
                self._model_path = base_dir / "llm-assistant-tauri" / "src-tauri" / "target" / "release" / "openai_whisper-large-v3-turbo"
            
            model_path = Path(self._model_path)
            if not model_path.exists():
                raise FileNotFoundError(f"Модель Whisper не найдена: {model_path}")
            
            logger.info(f"Загрузка модели из: {model_path}")
            
            # Загружаем процессор и модель
            self._processor = WhisperProcessor.from_pretrained(
                str(model_path),
                local_files_only=True
            )
            
            self._model = WhisperForConditionalGeneration.from_pretrained(
                str(model_path),
                local_files_only=True,
                torch_dtype=torch.float16 if self._device == "cuda" else torch.float32
            )
            
            self._model.to(self._device)
            self._model.eval()
            
            self._initialized = True
            logger.info("STT движок готов к работе")
            
        except Exception as e:
            logger.error(f"Ошибка инициализации STT: {e}")
            raise
    
    async def transcribe(self, audio_path: str) -> str:
        """
        Распознать речь из аудио файла.
        
        Args:
            audio_path: Путь к аудио файлу (wav, mp3, webm)
            
        Returns:
            str: Распознанный текст
        """
        if not self._initialized:
            await self.initialize()
        
        logger.info(f"Распознавание речи из: {audio_path}")
        
        try:
            import torch
            import librosa
            import os
            import shutil
            # Убедиться что ffmpeg доступен (как в tts_engine)
            if shutil.which("ffmpeg") is None:
                local_ffmpeg = Path(__file__).parent.parent / "ffmpeg"
                fallback_ffmpeg = Path(r"F:\ffmpeg\bin")
                for fb in [str(local_ffmpeg), str(fallback_ffmpeg)]:
                    if os.path.isdir(fb) and fb not in os.environ.get("PATH", ""):
                        os.environ["PATH"] = fb + ";" + os.environ.get("PATH", "")
                        break
            
            # Загружаем аудио
            audio, sr = librosa.load(audio_path, sr=16000)
            
            logger.debug(f"Аудио загружено: shape={audio.shape}, sr={sr}, duration={len(audio)/sr:.2f}s")
            if len(audio) == 0:
                raise ValueError("Аудио пустое (0 samples) — запись слишком короткая или повреждена")
            if len(audio) < 1600:  # <0.1 сек
                logger.warning(f"Очень короткое аудио: {len(audio)} samples ({len(audio)/sr:.2f}s), возможно тишина")
            
            # Если стерео - конвертируем в моно
            if len(audio.shape) > 1:
                audio = audio.mean(axis=1)
            
            # Конвертируем в float32 если нужно
            audio = audio.astype(np.float32)
            
            # Обрабатываем аудио
            input_features = self._processor(
                audio, 
                sampling_rate=16000, 
                return_tensors="pt"
            ).input_features
            
            # Приводим к типу модели
            if self._device == "cuda":
                input_features = input_features.half()
            
            # Переносим на устройство
            input_features = input_features.to(self._device)
            
            # Форсируем русский язык
            forced_decoder_ids = self._processor.get_decoder_prompt_ids(language="russian", task="transcribe")

            # Генерируем
            with torch.no_grad():
                predicted_ids = self._model.generate(
                    input_features,
                    forced_decoder_ids=forced_decoder_ids
                )
            
            # Декодируем
            transcription = self._processor.batch_decode(
                predicted_ids, 
                skip_special_tokens=True
            )[0]
            
            logger.info(f"Распознано: {transcription[:100]}...")
            return transcription.strip()
            
        except Exception as e:
            logger.error(f"Ошибка распознавания: {e}", exc_info=True)
            raise
    
    async def transcribe_bytes(self, audio_bytes: bytes, format: str = "webm") -> str:
        """
        Распознать речь из аудио байтов.
        
        Args:
            audio_bytes: Аудио данные
            format: Формат ('webm', 'wav', 'mp3')
            
        Returns:
            str: Распознанный текст
        """
        import tempfile
        import os
        
        # Создаём временный файл
        suffix = f".{format}"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name
        
        try:
            return await self.transcribe(tmp_path)
        finally:
            # Удаляем временный файл
            try:
                os.unlink(tmp_path)
            except:
                pass
    
    @property
    def is_initialized(self) -> bool:
        return self._initialized


# Глобальный экземпляр
_stt_engine: Optional[STTEngine] = None


def get_stt_engine() -> STTEngine:
    """Получить глобальный экземпляр STT движка."""
    global _stt_engine
    if _stt_engine is None:
        _stt_engine = STTEngine()
    return _stt_engine