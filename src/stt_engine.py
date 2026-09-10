"""
STT Engine - Whisper for speech recognition.

Uses a local Whisper model folder. The model is selected via STT_MODEL
(alias, 'owner/repo' id or explicit path) and downloaded on demand.
"""

import logging
from pathlib import Path
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)


def ensure_ffmpeg() -> str | None:
    """
    Make sure a working ffmpeg binary is on PATH.

    Checks candidates in order (system PATH, then the local ./ffmpeg folder)
    by actually running `ffmpeg -version`. The first working one wins and its
    folder is prepended to PATH (once). Returns the ffmpeg path or None.

    Returns:
        str | None: Resolved ffmpeg executable path, or None if none works.
    """
    import os
    import subprocess

    base_dir = Path(__file__).parent.parent
    candidates = []
    # Scan every PATH directory (shutil.which stops at the first match,
    # which may be broken while a working binary sits later in PATH)
    for directory in os.environ.get("PATH", "").split(os.pathsep):
        directory = directory.strip().strip('"')
        if not directory:
            continue
        for exe_name in ("ffmpeg.exe", "ffmpeg"):
            candidate = os.path.join(directory, exe_name)
            if os.path.isfile(candidate) and candidate not in candidates:
                candidates.append(candidate)
    local_exe = base_dir / "ffmpeg" / "ffmpeg.exe"
    if local_exe.is_file() and str(local_exe) not in candidates:
        candidates.append(str(local_exe))

    for exe in candidates:
        try:
            proc = subprocess.run(
                [exe, "-version"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=10,
            )
            if proc.returncode != 0:
                logger.warning(f"ffmpeg candidate failed: {exe} (exit {proc.returncode})")
                continue
        except Exception as e:
            logger.warning(f"ffmpeg candidate unusable: {exe} ({e})")
            continue
        ffmpeg_dir = str(Path(exe).parent)
        if ffmpeg_dir not in os.environ.get("PATH", ""):
            os.environ["PATH"] = ffmpeg_dir + ";" + os.environ.get("PATH", "")
            try:
                os.add_dll_directory(ffmpeg_dir)
            except Exception:
                pass
            logger.info(f"FFmpeg ready: {exe}")
        return exe

    logger.warning("No working ffmpeg found (system PATH nor ./ffmpeg). WebM/ogg decode may fail.")
    return None


def resolve_model_dir(name: str, legacy_subpath: str) -> str:
    """
    Resolve a model directory.

    Preferred location is ./models/<name>. If it does not exist, fall back
    to the legacy location under the Tauri build output (with a warning).

    Args:
        name: Directory name under ./models/.
        legacy_subpath: Directory name under .../target/release/.

    Returns:
        str: Resolved directory path (may not exist; the caller validates).
    """
    base_dir = Path(__file__).parent.parent
    preferred = base_dir / "models" / name
    if preferred.is_dir():
        return str(preferred)
    legacy = base_dir / "llm-assistant-tauri" / "src-tauri" / "target" / "release" / legacy_subpath
    if legacy.is_dir():
        logger.warning(f"Using legacy model path: {legacy}. Move it to {preferred}")
        return str(legacy)
    return str(preferred)


WHISPER_ALIASES = {
    "tiny": "openai/whisper-tiny",
    "base": "openai/whisper-base",
    "small": "openai/whisper-small",
    "medium": "openai/whisper-medium",
    "large": "openai/whisper-large-v3",
    "large-v3-turbo": "openai/whisper-large-v3-turbo",
}

DEFAULT_WHISPER_ALIAS = "large-v3-turbo"


def resolve_whisper_model(spec: Optional[str]) -> str:
    """
    Resolve the Whisper model to a local folder.

    Args:
        spec: Explicit value (local folder path, 'owner/repo' id or alias),
            or None to use STT_MODEL from the configuration.

    Returns:
        str: Path to the local model folder (downloaded on demand).
    """
    if not spec:
        from config import get_config
        spec = get_config().stt.model
    spec = str(spec).strip()

    # Explicit local folder?
    if Path(spec).is_dir():
        return str(Path(spec))

    # Alias or full repo id?
    alias = spec.lower()
    if alias in WHISPER_ALIASES:
        repo_id = WHISPER_ALIASES[alias]
    elif "/" in alias:
        repo_id = spec
    else:
        raise ValueError(
            f"Unknown Whisper model '{spec}'. "
            f"Valid aliases: {', '.join(sorted(WHISPER_ALIASES))}, "
            f"a 'owner/repo' id, or a local folder path."
        )

    model_name = repo_id.split("/")[-1]
    resolved = resolve_model_dir(model_name, f"openai_{model_name}")
    if Path(resolved).is_dir():
        return resolved

    # One-time download (must run before callers enable offline mode)
    from huggingface_hub import snapshot_download
    target = Path(__file__).parent.parent / "models" / model_name
    logger.info(f"Downloading Whisper model {repo_id} to {target} ...")
    snapshot_download(repo_id, local_dir=str(target))
    return str(target)


class STTEngine:
    """
    Whisper-based STT engine.
    """
    
    def __init__(self, model_path: Optional[str] = None):
        """
        Initialize the STT engine.

        Args:
            model_path: Path to the folder with the Whisper model.
                        If None - the default path is used.
        """
        self._model_path = model_path
        self._model = None
        self._processor = None
        self._device = None
        self._initialized = False
    
    async def initialize(self) -> None:
        """Load the Whisper model."""
        if self._initialized:
            return
        
        logger.info("Initializing STT engine (Whisper)...")
        
        try:
            import torch
            from transformers import WhisperProcessor, WhisperForConditionalGeneration
            
            # Detect device
            self._device = "cuda" if torch.cuda.is_available() else "cpu"
            logger.info(f"STT will use: {self._device}")
            
            # Model path: explicit path, STT_MODEL alias, or default (downloaded on demand)
            self._model_path = resolve_whisper_model(self._model_path)
            
            model_path = Path(self._model_path)
            if not model_path.exists():
                raise FileNotFoundError(f"Модель Whisper не найдена: {model_path}")
            
            logger.info(f"Loading model from: {model_path}")
            
            # Load processor and model
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
            logger.info("STT engine ready")
            
        except Exception as e:
            logger.error(f"STT initialization error: {e}")
            raise
    
    async def transcribe(self, audio_path: str) -> str:
        """
        Recognize speech from an audio file.

        Args:
            audio_path: Path to the audio file (wav, mp3, webm)

        Returns:
            str: Recognized text
        """
        if not self._initialized:
            await self.initialize()
        
        logger.info(f"Speech recognition from: {audio_path}")
        
        try:
            import torch
            import librosa
            import os
            import shutil
            # Make sure a working ffmpeg is on PATH (needed for webm/ogg decode)
            ensure_ffmpeg()
            
            # Load audio (any decode failure -> ValueError so callers return 422, not 500)
            try:
                audio, sr = librosa.load(audio_path, sr=16000)
            except ValueError:
                raise
            except Exception as e:
                raise ValueError(f"Не удалось декодировать аудио ({type(e).__name__}: {e})")

            logger.debug(f"Audio loaded: shape={audio.shape}, sr={sr}, duration={len(audio)/sr:.2f}s")
            if len(audio) == 0:
                raise ValueError("Аудио пустое (0 samples) — запись слишком короткая или повреждена")
            if len(audio) < 1600:  # <0.1 sec
                logger.warning(f"Very short audio: {len(audio)} samples ({len(audio)/sr:.2f}s), possibly silence")
            
            # If stereo - convert to mono
            if len(audio.shape) > 1:
                audio = audio.mean(axis=1)
            
            # Convert to float32 if needed
            audio = audio.astype(np.float32)
            
            # Process audio
            input_features = self._processor(
                audio, 
                sampling_rate=16000, 
                return_tensors="pt"
            ).input_features
            
            # Cast to the model dtype
            if self._device == "cuda":
                input_features = input_features.half()
            
            # Move to device
            input_features = input_features.to(self._device)
            
            # Force Russian language
            forced_decoder_ids = self._processor.get_decoder_prompt_ids(language="russian", task="transcribe")

            # Generate
            with torch.no_grad():
                predicted_ids = self._model.generate(
                    input_features,
                    forced_decoder_ids=forced_decoder_ids
                )
            
            # Decode
            transcription = self._processor.batch_decode(
                predicted_ids, 
                skip_special_tokens=True
            )[0]
            
            logger.info(f"Recognized: {transcription[:100]}...")
            return transcription.strip()
            
        except Exception as e:
            logger.error(f"Recognition error: {e}", exc_info=True)
            raise
    
    async def transcribe_bytes(self, audio_bytes: bytes, format: str = "webm") -> str:
        """
        Recognize speech from audio bytes.

        Args:
            audio_bytes: Audio data
            format: Format ('webm', 'wav', 'mp3')

        Returns:
            str: Recognized text
        """
        import tempfile
        import os
        
        # Create a temporary file
        suffix = f".{format}"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name
        
        try:
            return await self.transcribe(tmp_path)
        finally:
            # Remove the temporary file
            try:
                os.unlink(tmp_path)
            except:
                pass
    
    @property
    def is_initialized(self) -> bool:
        return self._initialized


# Global instance
_stt_engine: Optional[STTEngine] = None


def get_stt_engine() -> STTEngine:
    """Get the global STT engine instance."""
    global _stt_engine
    if _stt_engine is None:
        _stt_engine = STTEngine()
    return _stt_engine