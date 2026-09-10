"""
TTS Engine - Speech synthesis engine (Text-to-Speech).

The module provides an abstract interface for voicing assistant responses.
Current implementations: DummyTTSEngine (no-op stub) and OmniVoiceEngine
(local neural TTS), selected via the TTSEngine facade.

Architectural decisions:
1. Abstract base class ITTSEngine makes it easy to add
   any TTS library (Silero, Coqui, ElevenLabs API).
2. Async interface does not block the main thread.
3. Reference transcription caching for voice cloning (optimization).

Example usage:
    tts = TTSEngine()
    await tts.initialize()

    # Voice a text
    await tts.speak("Hello, I am your assistant!")

    # Save to a file
    await tts.save_to_file("Text", "output.wav")
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
    Speech synthesis result.

    Attributes:
        success: Operation success
        audio_data: Optionally, binary audio data (bytes)
        file_path: Optionally, path to the saved file
        duration_ms: Audio duration in milliseconds
        error: Error message if failed
    """
    success: bool
    audio_data: Optional[bytes] = None
    file_path: Optional[Path] = None
    duration_ms: int = 0
    error: Optional[str] = None


class ITTSEngine(ABC):
    """
    Abstract TTS engine interface.

    Allows replacing the implementation without changing assistant code.
    """

    @abstractmethod
    async def initialize(self) -> None:
        """Initialize the TTS engine."""
        pass
    
    @abstractmethod
    async def speak(self, text: str) -> AudioResult:
        """
        Voice a text (play via speakers).

        Args:
            text: Text to voice.

        Returns:
            AudioResult: Operation result.
        """
        pass
    
    @abstractmethod
    async def synthesize(self, text: str) -> AudioResult:
        """
        Synthesize audio without playback.

        Args:
            text: Text to voice.

        Returns:
            AudioResult: Result with audio_data.
        """
        pass
    
    @abstractmethod
    async def save_to_file(self, text: str, file_path: str | Path) -> AudioResult:
        """
        Save audio to a file.

        Args:
            text: Text to voice.
            file_path: Path to the file.

        Returns:
            AudioResult: Result with file_path.
        """
        pass
    
    @abstractmethod
    async def close(self) -> None:
        """Release resources."""
        pass


class DummyTTSEngine(ITTSEngine):
    """
    TTS engine stub.

    Used by default when TTS is disabled in config
    or as a placeholder for a future implementation.

    Logs all calls instead of real synthesis.
    """
    
    def __init__(self):
        self._initialized = False
        self._call_count = 0
    
    async def initialize(self) -> None:
        """Initialize the stub."""
        self._initialized = True
        logger.info("Dummy TTS Engine initialized (dummy)")
    
    async def speak(self, text: str) -> AudioResult:
        """
        Playback stub.

        Just logs the text instead of voicing.
        """
        if not self._initialized:
            return AudioResult(
                success=False,
                error="TTS Engine не инициализирован",
            )
        
        self._call_count += 1
        logger.info(f"[TTS Dummy] Text for synthesis #{self._call_count}: {text[:50]}...")
        
        # Simulate synthesis delay
        await asyncio.sleep(0.1)
        
        return AudioResult(
            success=True,
            duration_ms=100,
        )
    
    async def synthesize(self, text: str) -> AudioResult:
        """Synthesis stub."""
        if not self._initialized:
            return AudioResult(
                success=False,
                error="TTS Engine не инициализирован",
            )
        
        self._call_count += 1
        logger.debug(f"[TTS Dummy] Synthesis: {text[:50]}...")
        
        return AudioResult(
            success=True,
            audio_data=b"",  # Empty data
            duration_ms=100,
        )
    
    async def save_to_file(self, text: str, file_path: str | Path) -> AudioResult:
        """Stub for saving to a file."""
        if not self._initialized:
            return AudioResult(
                success=False,
                error="TTS Engine не инициализирован",
            )
        
        self._call_count += 1
        logger.info(f"[TTS Dummy] Saving to file: {file_path}")
        
        return AudioResult(
            success=True,
            file_path=Path(file_path),
            duration_ms=100,
        )
    
    async def close(self) -> None:
        """Close the stub."""
        self._initialized = False
        logger.info("Dummy TTS Engine closed")


class OmniVoiceEngine(ITTSEngine):
    """
    OmniVoice-based TTS engine.

    Local neural TTS with 600+ languages support.
    Requires: pip install omnivoice
    """
    
    def __init__(self, model_path: str = None, debug_save: bool = False):
        if model_path is None:
            from src.stt_engine import resolve_model_dir
            model_path = resolve_model_dir("omnivoice", "OmniVoice")
        self._model_path = model_path
        self._debug_save = debug_save
        self._model = None
        try:
            import torch
            self._device = "cuda" if torch.cuda.is_available() else "cpu"
        except Exception:
            self._device = "cpu"
        if self._device == "cpu":
            logger.warning("CUDA not available - OmniVoice will run on CPU (very slow)")
        self._initialized = False
        
        # Voice configuration
        self._mode = "instruct"  # "instruct" or "clone"
        self._instruct = "female"  # for instruct mode
        self._ref_audio_path = None  # for clone mode
        self._position_temperature = 0.0
        self._class_temperature = 0.0
        
        # Reference transcription cache (path -> transcription)
        self._ref_text_cache: dict[str, str] = {}
        
        # Folder with voices
        self._voices_dir = Path(__file__).parent.parent / "voices"
    
    def set_voice_config(self, mode: str = "instruct", 
                         instruct: str = "female",
                         ref_audio: str = None,
                         position_temperature: float = 0.0,
                         class_temperature: float = 0.0):
        """Configure voice parameters."""
        self._mode = mode
        self._instruct = instruct
        self._ref_audio_path = ref_audio
        self._position_temperature = position_temperature
        self._class_temperature = class_temperature
        
        # If clone mode - transcribe the reference and cache it
        if mode == "clone" and ref_audio:
            self._ensure_ref_text_cached(ref_audio)
        
        mode_str = f"instruct={instruct}" if mode == "instruct" else f"clone={ref_audio}"
        logger.info(f"TTS voice configured: mode={mode}, {mode_str}")
    
    def _ensure_ref_text_cached(self, ref_audio_path: str) -> None:
        """Transcribe the reference and save to cache (if not cached yet)."""
        if ref_audio_path in self._ref_text_cache:
            logger.info(f"Using transcription cache for: {ref_audio_path}")
            return
        
        if not self._whisper_model or not self._whisper_processor:
            logger.info("Local Whisper not loaded, skipping caching")
            return
        
        try:
            import librosa
            import torch
            
            logger.info(f"Transcribing reference (caching): {ref_audio_path}")
            
            # Load audio
            audio, sr = librosa.load(ref_audio_path, sr=16000)
            if audio.ndim > 1:
                audio = audio.mean(axis=1)
            audio = audio.astype('float32')
            
            # Transcribe
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
            
            # Save to cache
            self._ref_text_cache[ref_audio_path] = transcription
            logger.info(f"Reference cached: {transcription[:50]}...")
            
        except Exception as e:
            logger.warning(f"Failed to transcribe reference: {e}")
    
    def get_available_voices(self) -> list:
        """Get the list of available voices from the voices/ folder."""
        voices = []
        if not self._voices_dir.exists():
            logger.warning(f"Voices folder does not exist: {self._voices_dir}")
            return voices
        
        logger.info(f"Searching voices in: {self._voices_dir}")
        
        for f in self._voices_dir.iterdir():
            if f.suffix.lower() in ['.wav', '.mp3', '.ogg', '.flac']:
                logger.info(f"Found voice: {f.name}")
                voices.append({
                    "name": f.stem,
                    "file": f.name,
                    "path": str(f),
                })
        
        logger.info(f"Total voices found: {len(voices)}")
        return voices
    
    async def initialize(self) -> None:
        """Initialize the OmniVoice model."""
        if self._initialized:
            return
        
        logger.info(f"Loading OmniVoice model: {self._model_path}")
        
        try:
            import os
            
            # Make sure a working ffmpeg is on PATH (reference auto-transcription)
            from src.stt_engine import ensure_ffmpeg
            ensure_ffmpeg()
            
            # Resolve the Whisper model first (may trigger a one-time download,
            # so it must run before offline mode is enabled below)
            from src.stt_engine import resolve_whisper_model
            whisper_path = resolve_whisper_model(None)

            # Offline mode - use only local files
            os.environ["TRANSFORMERS_OFFLINE"] = "1"
            os.environ["HF_HUB_OFFLINE"] = "1"
            os.environ["HF_DATASETS_OFFLINE"] = "1"
            
            import torch
            from omnivoice import OmniVoice
            
            # Load OmniVoice
            dtype = torch.float16 if self._device == "cuda" else torch.float32
            
            self._model = OmniVoice.from_pretrained(
                self._model_path,
                device_map=self._device,
                dtype=dtype,
            )
            
            # Detect device
            if torch.cuda.is_available():
                self._device = "cuda"
            else:
                self._device = "cpu"
            
            # Load local Whisper for caching transcriptions (resolved above)
            try:
                from transformers import AutoModelForSpeechSeq2Seq, AutoProcessor
                logger.info(f"Loading local Whisper for caching: {whisper_path}")
                self._whisper_processor = AutoProcessor.from_pretrained(whisper_path, local_files_only=True)
                self._whisper_model = AutoModelForSpeechSeq2Seq.from_pretrained(
                    whisper_path, 
                    local_files_only=True,
                    torch_dtype=torch.float16 if self._device == "cuda" else torch.float32,
                )
                if self._device == "cuda":
                    self._whisper_model = self._whisper_model.to(self._device)
                logger.info("Local Whisper loaded for caching")
            except Exception as e:
                logger.warning(f"Failed to load local Whisper: {e}")
                self._whisper_model = None
                self._whisper_processor = None
            
            self._initialized = True
            logger.info(f"OmniVoice model loaded on {self._device}")
            
        except ImportError:
            logger.error("omnivoice not installed. Install: pip install omnivoice")
            raise
        except Exception as e:
            logger.error(f"OmniVoice loading error: {e}")
            raise
    
    async def _transcribe_reference(self, audio_path: str) -> str:
        """Transcribe the reference audio with local Whisper."""
        try:
            import torch
            import librosa
            import numpy as np
            
            logger.info(f"Loading audio: {audio_path}")
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
            logger.info(f"Transcription: {transcription}")
            return transcription
            
        except Exception as e:
            logger.error(f"Transcription error: {e}")
            return ""
    
    def _prepare_ref_audio(self, ref_path: str) -> str:
        """Convert the reference to an OmniVoice-compatible format (24kHz mono)."""
        import librosa
        import soundfile as sf
        import tempfile
        import numpy as np
        
        # Load and resample to 24 kHz mono
        audio, _ = librosa.load(ref_path, sr=24000, mono=True)
        audio = audio.astype(np.float32)
        audio = np.clip(audio, -1.0, 1.0)
        
        # Save to a temporary file
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp_path = tmp.name
            sf.write(tmp_path, audio, 24000, format="WAV", subtype="FLOAT")
        
        logger.info(f"Reference prepared: {tmp_path}")
        return tmp_path
    
    async def speak(self, text: str) -> AudioResult:
        """Voice a text."""
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
            
            logger.info(f"OmniVoice synthesis: {text[:50]}...")
            logger.info(f"Mode: mode={self._mode}, ref_audio={self._ref_audio_path}")
            
            loop = asyncio.get_event_loop()
            
            # Generation parameters
            gen_params = {
                "text": text,
                "speed": 1.0,
                "position_temperature": self._position_temperature,
                "class_temperature": self._class_temperature,
            }
            
            ref_prepared_path = None
            
            # Use reference audio or instruct
            if self._mode == "clone" and self._ref_audio_path:
                # Pass the reference directly (without librosa preprocessing)
                gen_params["ref_audio"] = self._ref_audio_path
                # Use the cached transcription or None for auto-transcription
                cached_ref_text = self._ref_text_cache.get(self._ref_audio_path)
                gen_params["ref_text"] = cached_ref_text
                
                if cached_ref_text:
                    logger.info(f"Using cached transcription for {self._ref_audio_path}")
                else:
                    logger.info(f"Using voice cloning: ref_audio (direct file) + ref_text=None (FFmpeg auto)")
                
                gen_params["num_step"] = 32
                gen_params["guidance_scale"] = 2.0
                gen_params["t_shift"] = 0.1
                gen_params["denoise"] = True
                gen_params["postprocess_output"] = True
                gen_params["language"] = "Russian"
                gen_params["seed"] = 12345
                logger.info(f"Using voice cloning: ref_audio (direct file) + ref_text=None (FFmpeg auto)")
            else:
                gen_params["instruct"] = "female, low pitch,"
                gen_params["num_step"] = 32
                gen_params["guidance_scale"] = 2.0
                gen_params["t_shift"] = 0.1
                gen_params["denoise"] = True
                gen_params["postprocess_output"] = True
                gen_params["language"] = "Russian"
                gen_params["seed"] = 468556206
                logger.info(f"Using voice design: female, low pitch, seed=468556206")
            
            # Generate audio (in executor, to avoid blocking)
            audio = await loop.run_in_executor(
                None,
                lambda: self._model.generate(**gen_params)
            )
            
            # Clean up the reference temp file
            if ref_prepared_path and os.path.exists(ref_prepared_path):
                try:
                    os.unlink(ref_prepared_path)
                except Exception:
                    pass
            
            # audio is a list tensor or numpy, take the first
            if isinstance(audio, list) and len(audio) > 0:
                audio_data = audio[0]
            else:
                audio_data = audio
            
            # Convert to numpy array if torch tensor
            if hasattr(audio_data, 'cpu'):
                audio_np = audio_data.cpu().numpy()
            else:
                audio_np = np.array(audio_data)
            
            logger.info(f"Audio shape: shape={audio_np.shape}, dtype={audio_np.dtype}, min={audio_np.min():.4f}, max={audio_np.max():.4f}")
            
            # Make sure it is a 1D array
            if audio_np.ndim > 1:
                audio_np = audio_np.flatten()
                logger.info(f"After flatten: shape={audio_np.shape}")
            
            # Normalize audio
            audio_np = audio_np.astype(np.float32)
            max_val = np.abs(audio_np).max()
            logger.info(f"Before normalization: max={max_val:.4f}")
            if max_val > 0:
                audio_np = audio_np / max_val
            
            logger.info(f"After normalization: min={audio_np.min():.4f}, max={audio_np.max():.4f}")
            
            # Save to a temp file for reading back
            import tempfile
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
                temp_path = f.name

            # Save 24kHz audio
            sf.write(temp_path, audio_np, 24000)
            logger.info(f"WAV saved: {temp_path}")

            # Optional permanent copy for inspection (TTS_DEBUG_SAVE=true)
            if self._debug_save:
                import datetime
                debug_dir = Path(__file__).parent.parent / "debug_tts"
                debug_dir.mkdir(parents=True, exist_ok=True)
                debug_path = str(debug_dir / f"tts_{datetime.datetime.now().strftime('%H%M%S')}.wav")
                sf.write(debug_path, audio_np, 24000)
                logger.info(f"DEBUG WAV saved: {debug_path}")
            
            # Read the file
            with open(temp_path, 'rb') as f:
                audio_bytes = f.read()
            
            # Remove the temp file
            import os
            os.remove(temp_path)
            
            # Free GPU memory after generation
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            
            # Force garbage collection
            import gc
            gc.collect()
            
            duration_ms = int(len(audio_bytes) / 2.4)  # Approximately for 24kHz 16bit
            
            logger.info(f"OmniVoice: audio generated, {len(audio_bytes)} bytes")
            
            return AudioResult(
                success=True,
                audio_data=audio_bytes,
                duration_ms=duration_ms,
            )
            
        except Exception as e:
            logger.error(f"OmniVoice TTS error: {e}")
            return AudioResult(
                success=False,
                error=str(e),
            )
    
    async def synthesize(self, text: str) -> bytes:
        """Synthesize audio and return bytes."""
        result = await self.speak(text)
        if result.success and result.audio_data:
            return result.audio_data
        raise RuntimeError(result.error or "Синтез не удался")
    
    async def save_to_file(self, text: str, file_path: str) -> AudioResult:
        """Save audio to a file."""
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
        """Close and release the model."""
        if self._model:
            del self._model
            self._model = None
        self._initialized = False
        logger.info("OmniVoice model unloaded from memory")


class TTSEngine:
    """
    Facade for the TTS engine.

    Automatically selects the implementation based on configuration
    and library availability.

    Example usage:
        tts = TTSEngine()
        await tts.initialize()

        if config.tts.enabled:
            await tts.speak("Hello!")
    """
    
    def __init__(self, config: TTSConfig | None = None):
        """
        Initialize the TTS facade.

        Args:
            config: TTS configuration.
        """
        self._config = config or get_config().tts
        self._engine: ITTSEngine | None = None
        self._initialized = False
        self._last_error: str | None = None

        # Saved voice config for applying when enabling
        self._voice_mode = "instruct"
        self._voice_instruct = "female"
        self._voice_ref_audio = None
    
    async def initialize(self) -> None:
        """
        Initialize the TTS engine.

        If TTS_ENABLED=false: DummyTTSEngine.
        Real TTS (OmniVoice) is loaded via enable_omnivoice() from the API.
        """
        if self._initialized:
            return
        
        if not self._config.enabled:
            self._engine = DummyTTSEngine()
            logger.info("TTS disabled in config, using dummy")
        else:
            logger.info("TTS enabled, will be loaded on first API request")
            self._engine = DummyTTSEngine()
        
        await self._engine.initialize()
        self._initialized = True
    
    async def close(self) -> None:
        """Close the TTS engine."""
        if self._engine:
            await self._engine.close()
        self._initialized = False
    
    async def speak(self, text: str) -> AudioResult:
        """
        Voice a text.

        Args:
            text: Text to voice.

        Returns:
            AudioResult: Operation result.
        """
        if not self._initialized or not self._engine:
            return AudioResult(
                success=False,
                error="TTS Engine не инициализирован",
            )
        
        return await self._engine.speak(text)
    
    async def synthesize(self, text: str) -> AudioResult:
        """Synthesize audio without playback."""
        if not self._initialized or not self._engine:
            return AudioResult(
                success=False,
                error="TTS Engine не инициализирован",
            )
        
        return await self._engine.synthesize(text)
    
    async def save_to_file(self, text: str, file_path: str | Path) -> AudioResult:
        """Save audio to a file."""
        if not self._initialized or not self._engine:
            return AudioResult(
                success=False,
                error="TTS Engine не инициализирован",
            )
        
        return await self._engine.save_to_file(text, file_path)
    
    @property
    def is_enabled(self) -> bool:
        """Check whether TTS is enabled."""
        return self._config.enabled and self._initialized
    
    @property
    def is_dummy(self) -> bool:
        """Check whether the stub is used."""
        return isinstance(self._engine, DummyTTSEngine)
    
    async def enable_omnivoice(self) -> bool:
        """
        Enable OmniVoice TTS.
        Loads the model into memory on first call.
        """
        if self._engine and not isinstance(self._engine, DummyTTSEngine):
            logger.info("OmniVoice already loaded")
            return True
        
        try:
            # Close the current engine
            if self._engine:
                await self._engine.close()
            
            # Create the OmniVoice engine
            self._engine = OmniVoiceEngine(debug_save=self._config.debug_save)
            await self._engine.initialize()
            self._initialized = True
            
            # Apply the saved voice config
            self._engine.set_voice_config(
                mode=self._voice_mode,
                instruct=self._voice_instruct,
                ref_audio=self._voice_ref_audio,
                position_temperature=0.0,
                class_temperature=0.0,
            )
            logger.info(f"Config applied: mode={self._voice_mode}, ref={self._voice_ref_audio}")
            
            logger.info("OmniVoice TTS enabled and loaded into memory")
            return True
            
        except Exception as e:
            self._last_error = f"{type(e).__name__}: {e}" if str(e) else repr(e)
            vram_info = ""
            try:
                import torch
                if torch.cuda.is_available():
                    free_b, total_b = torch.cuda.mem_get_info()
                    vram_info = f" (CUDA free/total: {free_b // 1024 // 1024} / {total_b // 1024 // 1024} MiB)"
            except Exception:
                pass
            logger.error(f"Failed to enable OmniVoice: {e}{vram_info}", exc_info=True)
            # Persist full diagnostics to disk (logs survive trimmed console pastes)
            try:
                import traceback
                from datetime import datetime
                logs_dir = Path(__file__).parent.parent / "logs"
                logs_dir.mkdir(parents=True, exist_ok=True)
                dump = logs_dir / f"tts_enable_fail_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
                dump.write_text(
                    f"error: {type(e).__name__}: {e}{vram_info}\n\n"
                    + traceback.format_exc(),
                    encoding="utf-8",
                )
                logger.info(f"Failure diagnostics written to {dump}")
            except Exception as dump_e:
                logger.debug(f"Failed to write diagnostics: {dump_e}")
            self._engine = DummyTTSEngine()
            await self._engine.initialize()
            return False

    @property
    def last_error(self) -> str | None:
        """Last OmniVoice loading error (if any)."""
        return self._last_error
    
    async def disable_omnivoice(self) -> bool:
        """
        Disable OmniVoice TTS.
        Unloads the model from memory.
        """
        if self._engine:
            await self._engine.close()
        
        self._engine = DummyTTSEngine()
        await self._engine.initialize()
        self._initialized = True
        
        logger.info("OmniVoice TTS disabled and unloaded from memory")
        return True
    
    def set_voice_config(self, mode: str = "instruct",
                         instruct: str = "female",
                         ref_audio: str = None,
                         position_temperature: float = 0.0,
                         class_temperature: float = 0.0):
        """Save the voice configuration."""
        self._voice_mode = mode
        self._voice_instruct = instruct
        self._voice_ref_audio = ref_audio
        
        # Apply to the current engine if it is OmniVoice
        if hasattr(self._engine, 'set_voice_config'):
            self._engine.set_voice_config(
                mode=mode,
                instruct=instruct,
                ref_audio=ref_audio,
                position_temperature=position_temperature,
                class_temperature=class_temperature,
            )
        
        logger.info(f"TTS config saved: mode={mode}, instruct={instruct}, ref_audio={ref_audio}")
    
    @property
    def is_omnivoice_loaded(self) -> bool:
        """Check whether OmniVoice is loaded."""
        return isinstance(self._engine, OmniVoiceEngine) and self._initialized
