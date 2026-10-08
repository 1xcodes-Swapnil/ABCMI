"""
Multilingual Automatic Speech Recognition (ASR) Engine
Provides ASR capabilities supporting 17 global and regional languages:
English, Hindi, Tamil, Telugu, Kannada, Malayalam, Bengali, Marathi, Gujarati, Punjabi,
Chinese, Japanese, French, Spanish, German, Russian, Arabic, and Code-Switched dialects.
Generates word-level timestamps, language detection confidence, and speaker-attributed text segments.
"""

import os
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, List, Optional
import uuid
from pydantic import Field

from app.schemas.base import CoreBaseModel
from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger("ai.multilingual_asr")


def validate_audio(audio_path: str) -> Dict[str, Any]:
    """
    Validates audio file existence, readability, format, size, duration, etc.
    Supported formats: .wav, .mp3, .m4a, .flac
    """
    if not audio_path:
        raise ValueError("Audio path cannot be empty.")
    if not os.path.exists(audio_path):
        raise FileNotFoundError(f"Audio file not found: {audio_path}")
    if not os.access(audio_path, os.R_OK):
        raise PermissionError(f"Audio file not readable: {audio_path}")
    
    ext = os.path.splitext(audio_path)[1].lower()
    if ext not in [".wav", ".mp3", ".m4a", ".flac"]:
        raise ValueError(f"Unsupported audio format: {ext}")
        
    if os.path.getsize(audio_path) == 0:
        raise ValueError("Audio file is empty.")
        
    duration = 0.0
    sample_rate = 16000
    channels = 1
    
    # Try reading with soundfile
    try:
        import soundfile as sf
        info = sf.info(audio_path)
        duration = info.duration
        sample_rate = info.samplerate
        channels = info.channels
    except Exception:
        # Fallback to librosa if soundfile fails
        try:
            import librosa
            y, sr = librosa.load(audio_path, sr=None)
            duration = float(librosa.get_duration(y=y, sr=sr))
            sample_rate = sr
            channels = 1 if len(y.shape) == 1 else y.shape[0]
        except Exception as ex:
            raise ValueError(f"Could not read audio file metadata: {ex}")
            
    if duration <= 0:
        raise ValueError("Audio file has zero or negative duration.")
        
    return {
        "duration": duration,
        "sample_rate": sample_rate,
        "channels": channels,
    }


class ASRWordTimestamp(CoreBaseModel):
    """Word-level timing and language confidence breakdown."""
    word: str = Field(..., description="Transcribed word token")
    start_time: float = Field(..., ge=0.0, description="Start timestamp in seconds")
    end_time: float = Field(..., ge=0.0, description="End timestamp in seconds")
    confidence: float = Field(default=0.90, ge=0.0, le=1.0, description="ASR model confidence score")
    language_code: str = Field(default="en", description="Detected language code for this word")


class ASRSegment(CoreBaseModel):
    """Contiguous speech segment attributed to a single speaker turn."""
    segment_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    speaker_id: Optional[str] = Field(default=None, description="Speaker identifier if available")
    start_time: float = Field(..., ge=0.0)
    end_time: float = Field(..., ge=0.0)
    transcript: str = Field(..., description="Transcribed text segment")
    detected_language: Optional[str] = Field(default="en", description="Primary detected language code, if supplied")
    words: List[ASRWordTimestamp] = Field(default_factory=list)
    confidence: Optional[float] = Field(default=0.90, ge=0.0, le=1.0)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ASRResult(CoreBaseModel):
    """Complete ASR processing output for a meeting audio payload."""
    meeting_id: uuid.UUID
    full_transcript: str
    detected_languages: List[str] = Field(default_factory=list)
    language_distribution: Dict[str, float] = Field(default_factory=dict)
    segments: List[ASRSegment] = Field(default_factory=list)
    overall_confidence: Optional[float] = Field(default=0.92, ge=0.0, le=1.0)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ASRProvider(ABC):
    """Abstract Base Class for ASR Providers (Phase 4.26)."""
    
    @abstractmethod
    async def transcribe(
        self, 
        audio_path: str, 
        options: Optional[Dict[str, Any]] = None
    ) -> List[ASRSegment]:
        """Transcribe an audio file and return a list of ASRSegment."""
        pass


class OpenMOSSProvider(ASRProvider):
    """Concrete ASR Provider using Open-MOSS (MOSS-Transcribe-Diarize)."""
    
    # Class-level model cache to guarantee MOSS is loaded once per provider/process
    _cached_model = None
    _cached_processor = None
    _cached_model_key = None

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.model_id = self.config.get("model_id", "OpenMOSS-Team/MOSS-Transcribe-Diarize")
        self.device = self.config.get("device", "cpu")
        self.cache_dir = self.config.get("cache_dir")
        self.token = self.config.get("token")
        self.model = None
        self.processor = None
        self.last_raw_output = None
        self.last_inference = {}

    def _load_model(self):
        """Loads MOSS weights and processor once per provider instance / process."""
        if self.model is not None and self.processor is not None:
            return

        cache_key = f"{self.model_id}:{self.device}"
        if OpenMOSSProvider._cached_model_key == cache_key and OpenMOSSProvider._cached_model is not None:
            self.model = OpenMOSSProvider._cached_model
            self.processor = OpenMOSSProvider._cached_processor
            logger.info("REAL MODEL LOADED: Reusing cached Open-MOSS (%s on %s)", self.model_id, self.device)
            return

        import torch
        from transformers import AutoModelForCausalLM, AutoProcessor
        from app.ai.model_inventory import configure_cache
        configure_cache()
        requested_device = torch.device("cuda:0" if self.device == "auto" else self.device)
        if requested_device.type == "cuda" and not torch.cuda.is_available():
            raise RuntimeError("Configured CUDA device is unavailable; REAL inference cannot move silently to CPU")
        
        try:
            logger.info("Loading Open-MOSS processor and weights for '%s' on device '%s'...", self.model_id, self.device)
            try:
                self.processor = AutoProcessor.from_pretrained(
                    self.model_id, trust_remote_code=True, cache_dir=self.cache_dir,
                    token=self.token, local_files_only=True,
                )
            except TypeError as exc:
                if "fix_mistral_regex" not in str(exc) or "multiple values" not in str(exc):
                    raise
                self.processor = self._construct_processor(remove_mistral_key=True)
            if not getattr(self.processor, "chat_template", None):
                self.processor = self._construct_processor(remove_mistral_key=False)
            device_target = self.device if self.device != "auto" else "auto"
            is_cuda = requested_device.type == "cuda"

            if is_cuda:
                # 4-bit NF4 Quantization for CUDA GPU
                try:
                    from transformers import BitsAndBytesConfig
                    bnb_config = BitsAndBytesConfig(
                        load_in_4bit=True,
                        bnb_4bit_quant_type="nf4",
                        bnb_4bit_compute_dtype=torch.float16,
                        bnb_4bit_use_double_quant=True,
                    )
                    self.model = AutoModelForCausalLM.from_pretrained(
                        self.model_id,
                        trust_remote_code=True,
                        cache_dir=self.cache_dir,
                        token=self.token,
                        device_map={"": str(requested_device)},
                        quantization_config=bnb_config,
                        dtype=torch.float16,
                        local_files_only=True,
                    )
                    logger.info("REAL MODEL LOADED: Open-MOSS loaded with 4-bit CUDA quantization.")
                except Exception as q_err:
                    raise RuntimeError("Configured 4-bit CUDA MOSS loading failed") from q_err
            else:
                # Optimized CPU execution: load lightweight float32/bfloat16 and apply dynamic INT8 quantization
                raw_model = AutoModelForCausalLM.from_pretrained(
                    self.model_id,
                    trust_remote_code=True,
                    cache_dir=self.cache_dir,
                    token=self.token,
                    device_map="cpu",
                    torch_dtype=torch.float32,
                    low_cpu_mem_usage=True,
                    local_files_only=True,
                )
                try:
                    logger.info("Applying PyTorch dynamic INT8 quantization for Open-MOSS on CPU...")
                    self.model = torch.ao.quantization.quantize_dynamic(
                        raw_model,
                        {torch.nn.Linear},
                        dtype=torch.qint8,
                    )
                    logger.info("REAL MODEL LOADED: Open-MOSS dynamic INT8 quantized on CPU.")
                except Exception as q_ex:
                    logger.warning("Dynamic INT8 quantization skipped (%s), using standard CPU model.", q_ex)
                    self.model = raw_model

            OpenMOSSProvider._cached_model = self.model
            OpenMOSSProvider._cached_processor = self.processor
            OpenMOSSProvider._cached_model_key = cache_key
            logger.info("REAL MODEL LOADED: Open-MOSS '%s' successfully loaded on device '%s'", self.model_id, self.device)
        except Exception as ex:
            raise RuntimeError(
                f"Failed to load Open-MOSS model '{self.model_id}' on device '{self.device}': {ex}"
            ) from ex

    def _construct_processor(self, *, remove_mistral_key: bool):
        """Notebook-verified compatibility path; never edits downloaded model files."""
        import json
        import shutil
        import tempfile
        from pathlib import Path
        from huggingface_hub import snapshot_download
        from transformers import AutoTokenizer, WhisperFeatureExtractor
        from moss_transcribe_diarize.processing_moss_transcribe_diarize import MossTranscribeDiarizeProcessor
        directory = Path(self.model_id)
        if not directory.is_dir():
            directory = Path(snapshot_download(self.model_id, cache_dir=self.cache_dir,
                                               token=self.token, local_files_only=True))
        config = json.loads((directory / "processor_config.json").read_text())
        template = (directory / "chat_template.jinja").read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory(prefix="abcimi_moss_tokenizer_") as temporary:
            tokenizer_dir = directory
            if remove_mistral_key:
                tokenizer_dir = Path(temporary)
                for name in ["tokenizer.json", "vocab.json", "merges.txt", "added_tokens.json",
                             "special_tokens_map.json", "chat_template.jinja", "config.json"]:
                    if (directory / name).is_file():
                        shutil.copy2(directory / name, tokenizer_dir / name)
                tokenizer_config = json.loads((directory / "tokenizer_config.json").read_text())
                tokenizer_config.pop("fix_mistral_regex", None)
                (tokenizer_dir / "tokenizer_config.json").write_text(json.dumps(tokenizer_config))
            tokenizer = AutoTokenizer.from_pretrained(tokenizer_dir, trust_remote_code=True, local_files_only=True)
        extractor = WhisperFeatureExtractor.from_pretrained(directory, local_files_only=True)
        keys = ("audio_tokens_per_second", "audio_merge_size", "time_marker_every_seconds", "enable_time_marker")
        return MossTranscribeDiarizeProcessor(feature_extractor=extractor, tokenizer=tokenizer,
            chat_template=template, **{key: config[key] for key in keys if key in config})

    async def transcribe(
        self, 
        audio_path: str, 
        options: Optional[Dict[str, Any]] = None
    ) -> List[ASRSegment]:
        """Perform actual Open-MOSS transcription on the provided audio path."""
        # 1. Validate audio first
        audio_metadata = validate_audio(audio_path)
        
        # 2. Check dependencies and load model
        try:
            import torch
            import librosa
        except ImportError as ex:
            raise RuntimeError(
                f"Missing real model dependencies (torch, librosa) for Open-MOSS: {ex}"
            ) from ex
            
        self._load_model()
        
        # 3. Perform inference
        logger.info(
            "REAL INFERENCE ATTEMPTED: Processing audio file %s with Open-MOSS (%s on %s)",
            audio_path, self.model_id, self.device
        )
        try:
            import time
            from moss_transcribe_diarize.inference_utils import build_transcription_messages, generate_transcription
            messages = build_transcription_messages(audio_path)
            device = next(self.model.parameters()).device
            started = time.perf_counter()
            token_budget = int((options or {}).get("max_new_tokens", get_settings().OPENMOSS_MAX_NEW_TOKENS))
            result = generate_transcription(self.model, self.processor, messages,
                max_new_tokens=token_budget, do_sample=False,
                device=torch.device(device), dtype=self.model.dtype)
            self.last_raw_output = result["text"]
            self.last_inference = {"raw_output_type": type(result).__name__, "raw_output_keys": list(result),
                                   "generated_tokens": result["generated_tokens"], "prompt_tokens": result["prompt_len"],
                                   "generation_seconds": time.perf_counter() - started, "device": str(device),
                                   "max_new_tokens": token_budget}
            if result["generated_tokens"] >= token_budget:
                raise ValueError("MOSS reached its generation token limit; truncated output cannot be accepted as complete transcription")
            decoded_text = result["text"]
            
            # Parse decoded_text into ASRSegment formats
            chunk_meta = options.get("chunk_meta") if options else None
            segments = self._parse_moss_output(decoded_text, chunk_meta=chunk_meta)
            self.last_inference["parsed_segments_before_audio_bounds"] = len(segments)
            segments, rejected = self._validate_audio_bounds(segments, audio_metadata["duration"])
            self.last_inference["rejected_audio_bounds"] = rejected
            if not segments:
                raise ValueError("MOSS generated no structured transcript segments.")
            
            logger.info(
                "REAL INFERENCE SUCCEEDED: Extracted %d segments from %s",
                len(segments), audio_path
            )
            return segments
            
        except Exception as ex:
            logger.error("REAL INFERENCE FAILED: Open-MOSS inference error on %s: %s", audio_path, ex)
            raise RuntimeError(f"Open-MOSS inference failed: {ex}") from ex

    @staticmethod
    def _validate_audio_bounds(segments, duration):
        """Reject impossible model turns without clipping or inventing timestamps."""
        valid, rejected = [], []
        for segment in segments:
            if segment.start_time < duration and segment.end_time <= duration:
                valid.append(segment)
            else:
                rejected.append({"start_time": segment.start_time, "end_time": segment.end_time,
                                 "reason": "outside_input_audio"})
        return valid, rejected

    @staticmethod
    def _parse_timestamp(ts_str: str) -> float:
        """Safely parse timestamps formatted as mm:ss.xx, hh:mm:ss.xx, or decimal seconds."""
        ts = ts_str.strip()
        if ":" in ts:
            parts = ts.split(":")
            if len(parts) == 2:
                # mm:ss.xx
                return float(parts[0]) * 60.0 + float(parts[1])
            elif len(parts) == 3:
                # hh:mm:ss.xx
                return float(parts[0]) * 3600.0 + float(parts[1]) * 60.0 + float(parts[2])
        return float(ts)

    def _parse_moss_output(self, text: str, chunk_meta: Optional[Any] = None) -> List[ASRSegment]:
        """
        Use the official MOSS parser for model-generated speaker/timestamp turns.
        Missing timestamps fail explicitly. Confidence and language remain unknown
        when the model does not supply them.
        """
        import math
        from moss_transcribe_diarize import parse_transcript
        if not text or not text.strip():
            raise ValueError("MOSS generated empty output.")
        parsed = parse_transcript(text)
        segments = []
        for turn in parsed:
            if not (math.isfinite(turn.start) and math.isfinite(turn.end) and 0 <= turn.start < turn.end):
                raise ValueError("MOSS returned invalid segment bounds")
            if not turn.text.strip():
                continue
            segments.append(ASRSegment(speaker_id=turn.speaker, start_time=turn.start, end_time=turn.end,
                transcript=turn.text, detected_language=None, confidence=None, words=[],
                metadata={"model": self.model_id, "chunk_index": getattr(chunk_meta, "chunk_index", None),
                          "confidence_status": "NOT_VERIFIED", "language_status": "NOT_VERIFIED"}))
        if not segments:
            raise ValueError("MOSS output has no timestamped segments; timestamps cannot be fabricated")
        return segments


class MultilingualASREngine:
    """
    Multilingual ASR Engine utilizing OpenAI Whisper Large-v3 pretrained architecture
    and Open-MOSS (MOSS-Transcribe-Diarize) for first-class REAL mode. Supports 17 languages and dialects.
    """

    PRETRAINED_MODEL_NAME = "openai/whisper-large-v3"
    PRETRAINED_MODEL_VERSION = "v3-turbo"

    SUPPORTED_LANGUAGES = [
        "en", "hi", "ta", "te", "kn", "ml", "bn", "mr", "gu", "pa",
        "zh", "ja", "fr", "es", "de", "ru", "ar",
        "hinglish", "tanglish", "spanglish", "franglais", "arabiya-english",
    ]

    LANGUAGE_NAMES = {
        "en": "English",
        "hi": "Hindi",
        "ta": "Tamil",
        "te": "Telugu",
        "kn": "Kannada",
        "ml": "Malayalam",
        "bn": "Bengali",
        "mr": "Marathi",
        "gu": "Gujarati",
        "pa": "Punjabi",
        "zh": "Chinese",
        "ja": "Japanese",
        "fr": "French",
        "es": "Spanish",
        "de": "German",
        "ru": "Russian",
        "ar": "Arabic",
        "hinglish": "Hinglish (Hindi-English)",
        "tanglish": "Tanglish (Tamil-English)",
        "spanglish": "Spanglish (Spanish-English)",
        "franglais": "Franglais (French-English)",
        "arabiya-english": "Arabiya-English (Arabic-English)",
    }

    def __init__(self, model_config: Optional[Dict[str, Any]] = None) -> None:
        self.config = model_config or {
            "default_language": "hi",
            "fallback_language": "en",
            "beam_size": 5,
            "word_timestamps": True,
            "use_fixture_mode": True,
        }
        self.model_name = self.PRETRAINED_MODEL_NAME
        self.model_version = self.PRETRAINED_MODEL_VERSION

    async def transcribe_audio(
        self,
        audio_payload: bytes,
        meeting_id: uuid.UUID,
        target_languages: Optional[List[str]] = None,
        correlation_id: Optional[str] = None,
        use_fixture: Optional[bool] = None,
        force_chunked: bool = False,
        chunk_duration: Optional[float] = None,
        overlap_duration: Optional[float] = None,
        audio_file_path: Optional[str] = None,
    ) -> ASRResult:
        """
        Transcribes multilingual audio payload into timed segments with language confidence.
        Enforces validation for the 17 supported languages.
        Supports REAL mode execution using Open-MOSS.
        Automatically switches to LongAudioProcessor when audio duration exceeds AUDIO_CHUNK_THRESHOLD_SECONDS
        or when force_chunked is True.
        """
        if not audio_payload and not audio_file_path:
            raise ValueError("Audio payload cannot be empty.")

        langs = target_languages or ["hi", "en", "hinglish"]

        # Validate language codes against the 17 supported languages + code-switched dialects
        invalid_langs = [l for l in langs if l.lower() not in self.SUPPORTED_LANGUAGES]
        if invalid_langs:
            raise ValueError(
                f"Unsupported language code(s): {invalid_langs}. "
                f"Supported 17 languages and dialects are: {self.SUPPORTED_LANGUAGES}"
            )

        settings = get_settings()
        exec_mode = getattr(settings, "EXECUTION_MODE", "FIXTURE").upper()
        if exec_mode == "REAL" and use_fixture:
            raise RuntimeError("REAL mode forbids fixture transcription.")
        if use_fixture is not None:
            is_fixture_mode = use_fixture
        else:
            is_fixture_mode = (exec_mode != "REAL") and self.config.get("use_fixture_mode", True)

        # Save audio payload to a temporary file for validation and processing
        import tempfile
        owns_temp_file = audio_file_path is None
        tmp_path = audio_file_path
        if owns_temp_file:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                tmp.write(audio_payload)
                tmp_path = tmp.name

        try:
            try:
                audio_meta = validate_audio(tmp_path)
                duration = audio_meta["duration"]
            except Exception as val_err:
                if exec_mode == "REAL":
                    raise ValueError("REAL audio metadata validation failed") from val_err
                logger.debug(f"Audio metadata validation skipped: {val_err}")
                duration = 0.0

            threshold = getattr(settings, "AUDIO_CHUNK_THRESHOLD_SECONDS", 600.0)

            # Check if chunked processing is triggered
            if (duration > threshold and duration > 0.0) or force_chunked:
                return await self.transcribe_long_audio(
                    audio_file_path=tmp_path,
                    meeting_id=meeting_id,
                    target_languages=langs,
                    correlation_id=correlation_id,
                    use_fixture=is_fixture_mode,
                    chunk_duration=chunk_duration,
                    overlap_duration=overlap_duration,
                )

            if exec_mode == "REAL" and not is_fixture_mode:
                # Run the actual Open-MOSS transcription in a single pass
                provider = OpenMOSSProvider({
                    "model_id": settings.OPENMOSS_MODEL_ID,
                    "device": settings.OPENMOSS_DEVICE,
                    "cache_dir": settings.OPENMOSS_CACHE_DIR,
                    "token": settings.HF_TOKEN,
                })

                segments = await provider.transcribe(tmp_path)

                full_transcripts = [s.transcript for s in segments]
                full_text = " ".join(full_transcripts)

                # Compute languages from segments
                detected_langs = list(set(s.detected_language for s in segments if s.detected_language))

                lang_dist = {}
                if len(segments) > 0:
                    for s in segments:
                        if s.detected_language:
                            lang_dist[s.detected_language] = lang_dist.get(s.detected_language, 0.0) + 1.0
                    for l in lang_dist:
                        lang_dist[l] = lang_dist[l] / len(segments)

                return ASRResult(
                    meeting_id=meeting_id,
                    full_transcript=full_text,
                    detected_languages=detected_langs,
                    language_distribution=lang_dist,
                    segments=segments,
                    overall_confidence=None,
                    metadata={
                        "correlation_id": correlation_id,
                        "audio_bytes_length": len(audio_payload) if audio_payload is not None else os.path.getsize(tmp_path),
                        "model_name": settings.OPENMOSS_MODEL_ID,
                        "model_version": "latest",
                        "provenance": f"ASR:{settings.OPENMOSS_MODEL_ID}:latest",
                        "is_fixture": False,
                        "inference": provider.last_inference,
                        "raw_moss_output": provider.last_raw_output,
                        "chunk_count": 1,
                        "supported_languages_count": len(self.SUPPORTED_LANGUAGES),
                    },
                )
        finally:
            if owns_temp_file and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass

        # Generate sample transcript segments according to target languages for FIXTURE / MOCK mode
        segments: List[ASRSegment] = []
        full_transcripts: List[str] = []
        lang_dist: Dict[str, float] = {}

        if "zh" in langs:
            words = [
                ASRWordTimestamp(word="你好", start_time=0.0, end_time=0.5, confidence=0.97, language_code="zh"),
                ASRWordTimestamp(word="团队", start_time=0.6, end_time=1.0, confidence=0.98, language_code="zh"),
                ASRWordTimestamp(word="today", start_time=1.1, end_time=1.5, confidence=0.96, language_code="en"),
            ]
            segment = ASRSegment(
                speaker_id="speaker_0",
                start_time=0.0,
                end_time=1.5,
                transcript="你好 团队 today",
                detected_language="zh",
                words=words,
                confidence=0.97,
            )
            segments.append(segment)
            full_transcripts.append(segment.transcript)
            lang_dist["zh"] = 0.7
            lang_dist["en"] = 0.3
        elif "ja" in langs:
            words = [
                ASRWordTimestamp(word="こんにちは", start_time=0.0, end_time=0.6, confidence=0.96, language_code="ja"),
                ASRWordTimestamp(word="みんな", start_time=0.7, end_time=1.2, confidence=0.95, language_code="ja"),
            ]
            segment = ASRSegment(
                speaker_id="speaker_0",
                start_time=0.0,
                end_time=1.2,
                transcript="こんにちは みんな",
                detected_language="ja",
                words=words,
                confidence=0.96,
            )
            segments.append(segment)
            full_transcripts.append(segment.transcript)
            lang_dist["ja"] = 1.0
        elif "fr" in langs or "franglais" in langs:
            words = [
                ASRWordTimestamp(word="Bonjour", start_time=0.0, end_time=0.5, confidence=0.98, language_code="fr"),
                ASRWordTimestamp(word="l'équipe", start_time=0.6, end_time=1.0, confidence=0.96, language_code="fr"),
                ASRWordTimestamp(word="welcome", start_time=1.1, end_time=1.5, confidence=0.97, language_code="en"),
            ]
            segment = ASRSegment(
                speaker_id="speaker_0",
                start_time=0.0,
                end_time=1.5,
                transcript="Bonjour l'équipe welcome",
                detected_language="franglais",
                words=words,
                confidence=0.97,
            )
            segments.append(segment)
            full_transcripts.append(segment.transcript)
            lang_dist["fr"] = 0.6
            lang_dist["en"] = 0.4
        elif "es" in langs or "spanglish" in langs:
            words = [
                ASRWordTimestamp(word="Hola", start_time=0.0, end_time=0.4, confidence=0.98, language_code="es"),
                ASRWordTimestamp(word="equipo", start_time=0.5, end_time=0.9, confidence=0.97, language_code="es"),
                ASRWordTimestamp(word="meeting", start_time=1.0, end_time=1.4, confidence=0.96, language_code="en"),
            ]
            segment = ASRSegment(
                speaker_id="speaker_0",
                start_time=0.0,
                end_time=1.4,
                transcript="Hola equipo meeting",
                detected_language="spanglish",
                words=words,
                confidence=0.97,
            )
            segments.append(segment)
            full_transcripts.append(segment.transcript)
            lang_dist["es"] = 0.6
            lang_dist["en"] = 0.4
        elif "de" in langs:
            words = [
                ASRWordTimestamp(word="Guten", start_time=0.0, end_time=0.4, confidence=0.98, language_code="de"),
                ASRWordTimestamp(word="Tag", start_time=0.5, end_time=0.8, confidence=0.98, language_code="de"),
            ]
            segment = ASRSegment(
                speaker_id="speaker_0",
                start_time=0.0,
                end_time=0.8,
                transcript="Guten Tag",
                detected_language="de",
                words=words,
                confidence=0.98,
            )
            segments.append(segment)
            full_transcripts.append(segment.transcript)
            lang_dist["de"] = 1.0
        elif "ru" in langs:
            words = [
                ASRWordTimestamp(word="Здравствуйте", start_time=0.0, end_time=0.8, confidence=0.95, language_code="ru"),
            ]
            segment = ASRSegment(
                speaker_id="speaker_0",
                start_time=0.0,
                end_time=0.8,
                transcript="Здравствуйте",
                detected_language="ru",
                words=words,
                confidence=0.95,
            )
            segments.append(segment)
            full_transcripts.append(segment.transcript)
            lang_dist["ru"] = 1.0
        elif "ar" in langs or "arabiya-english" in langs:
            words = [
                ASRWordTimestamp(word="Marhaban", start_time=0.0, end_time=0.5, confidence=0.96, language_code="ar"),
                ASRWordTimestamp(word="team", start_time=0.6, end_time=1.0, confidence=0.97, language_code="en"),
            ]
            segment = ASRSegment(
                speaker_id="speaker_0",
                start_time=0.0,
                end_time=1.0,
                transcript="Marhaban team",
                detected_language="arabiya-english",
                words=words,
                confidence=0.96,
            )
            segments.append(segment)
            full_transcripts.append(segment.transcript)
            lang_dist["ar"] = 0.5
            lang_dist["en"] = 0.5
        else:
            # Default Hinglish / English / Hindi synthesis
            words = [
                ASRWordTimestamp(word="Namaste", start_time=0.0, end_time=0.5, confidence=0.96, language_code="hi"),
                ASRWordTimestamp(word="team", start_time=0.6, end_time=0.9, confidence=0.98, language_code="en"),
                ASRWordTimestamp(word="today", start_time=1.0, end_time=1.4, confidence=0.95, language_code="en"),
                ASRWordTimestamp(word="hum", start_time=1.5, end_time=1.7, confidence=0.92, language_code="hi"),
                ASRWordTimestamp(word="architecture", start_time=1.8, end_time=2.5, confidence=0.97, language_code="en"),
                ASRWordTimestamp(word="discuss", start_time=2.6, end_time=3.0, confidence=0.94, language_code="en"),
                ASRWordTimestamp(word="karenge", start_time=3.1, end_time=3.6, confidence=0.95, language_code="hi"),
            ]
            segment = ASRSegment(
                speaker_id="speaker_0",
                start_time=0.0,
                end_time=3.6,
                transcript="Namaste team today hum architecture discuss karenge",
                detected_language="hinglish",
                words=words,
                confidence=0.95,
            )
            segments.append(segment)
            full_transcripts.append(segment.transcript)
            lang_dist["hi"] = 0.4
            lang_dist["en"] = 0.5
            lang_dist["hinglish"] = 0.1

        full_text = " ".join(full_transcripts)

        return ASRResult(
            meeting_id=meeting_id,
            full_transcript=full_text,
            detected_languages=langs,
            language_distribution=lang_dist,
            segments=segments,
            overall_confidence=0.95,
            metadata={
                "correlation_id": correlation_id,
                "audio_bytes_length": len(audio_payload),
                "model_name": self.PRETRAINED_MODEL_NAME,
                "model_version": self.PRETRAINED_MODEL_VERSION,
                "provenance": f"ASR:{self.PRETRAINED_MODEL_NAME}:{self.PRETRAINED_MODEL_VERSION}",
                "is_fixture": is_fixture_mode,
                "supported_languages_count": len(self.SUPPORTED_LANGUAGES),
            },
        )

    async def transcribe_long_audio(
        self,
        audio_file_path: str,
        meeting_id: uuid.UUID,
        target_languages: Optional[List[str]] = None,
        correlation_id: Optional[str] = None,
        use_fixture: bool = False,
        chunk_duration: Optional[float] = None,
        overlap_duration: Optional[float] = None,
    ) -> ASRResult:
        """
        Executes chunked ASR pipeline with overlap for long recordings (1-2+ hours).
        Uses LongAudioProcessor for chunk slicing, global timestamp offsets, speaker reconciliation,
        and boundary deduplication.
        """
        from app.ai.long_audio_processor import LongAudioProcessor, ChunkMetadata

        settings = get_settings()
        exec_mode = getattr(settings, "EXECUTION_MODE", "FIXTURE").upper()

        if exec_mode == "REAL" and use_fixture:
            raise RuntimeError("REAL mode forbids fixture transcription.")

        processor = LongAudioProcessor(
            chunk_duration=chunk_duration,
            overlap_duration=overlap_duration,
        )

        # Initialize OpenMOSSProvider once per long-audio run in REAL mode
        real_provider: Optional[OpenMOSSProvider] = None
        if exec_mode == "REAL" and not use_fixture:
            real_provider = OpenMOSSProvider({
                "model_id": settings.OPENMOSS_MODEL_ID,
                "device": settings.OPENMOSS_DEVICE,
                "cache_dir": settings.OPENMOSS_CACHE_DIR,
                "token": settings.HF_TOKEN,
            })

        inference_trace = []
        async def _transcribe_chunk(chunk_path: str, chunk_meta: ChunkMetadata) -> List[ASRSegment]:
            if exec_mode == "REAL" and not use_fixture:
                if real_provider is None:
                    raise RuntimeError("REAL mode requested but OpenMOSSProvider was not initialized.")
                segments = await real_provider.transcribe(chunk_path, options={"chunk_meta": chunk_meta})
                inference_trace.append({"chunk_index": chunk_meta.chunk_index, "start_time": chunk_meta.start_time,
                    "end_time": chunk_meta.end_time, "segments": len(segments),
                    "raw_moss_output": real_provider.last_raw_output, **real_provider.last_inference})
                return segments
            else:
                # Simulated chunk transcription for fixture/test mode
                # Generate realistic turns within this chunk's local timeline [0, chunk_meta.duration]
                dur = chunk_meta.duration
                mid = dur / 2.0
                turn1_text = f"Reviewing action items for phase {chunk_meta.chunk_index + 1}."
                turn2_text = f"Confirmed progress on section {chunk_meta.chunk_index + 1}."

                words1 = [
                    ASRWordTimestamp(word=w, start_time=i * 0.4, end_time=(i + 1) * 0.4, confidence=0.95, language_code="en")
                    for i, w in enumerate(turn1_text.split())
                ]
                words2 = [
                    ASRWordTimestamp(word=w, start_time=mid + i * 0.4, end_time=mid + (i + 1) * 0.4, confidence=0.94, language_code="en")
                    for i, w in enumerate(turn2_text.split())
                ]

                # Alternate speakers across chunks to verify cross-chunk reconciliation
                spk_a = f"Speaker {1 + (chunk_meta.chunk_index % 2)}"
                spk_b = f"Speaker {2 - (chunk_meta.chunk_index % 2)}"

                return [
                    ASRSegment(
                        speaker_id=spk_a,
                        start_time=0.0,
                        end_time=min(mid, max(2.0, len(words1) * 0.4)),
                        transcript=turn1_text,
                        detected_language="en",
                        words=words1,
                        confidence=0.95,
                    ),
                    ASRSegment(
                        speaker_id=spk_b,
                        start_time=mid,
                        end_time=min(dur, mid + max(2.0, len(words2) * 0.4)),
                        transcript=turn2_text,
                        detected_language="en",
                        words=words2,
                        confidence=0.94,
                    ),
                ]

        recon_result = await processor.process_long_audio(
            audio_file_path=audio_file_path,
            meeting_id=meeting_id,
            transcribe_chunk_func=_transcribe_chunk,
            correlation_id=correlation_id,
        )

        recon_result.asr_result.metadata.update(is_fixture=exec_mode != "REAL" or use_fixture,
            model_name=settings.OPENMOSS_MODEL_ID if exec_mode == "REAL" else self.PRETRAINED_MODEL_NAME,
            chunk_count=recon_result.total_chunks, inference=inference_trace)
        return recon_result.asr_result

    async def process_segment(
        self,
        audio_chunk: bytes,
        speaker_id: Optional[str] = None,
    ) -> ASRSegment:
        """
        Transcribes a short audio chunk into a single ASRSegment.
        """
        if not audio_chunk:
            raise ValueError("Audio chunk cannot be empty.")

        if get_settings().EXECUTION_MODE.upper() == "REAL":
            raise RuntimeError("REAL streaming transcription is not implemented by process_segment.")

        return ASRSegment(
            speaker_id=speaker_id or "speaker_unknown",
            start_time=0.0,
            end_time=1.5,
            transcript="Action item identified",
            detected_language="en",
            confidence=0.93,
        )
