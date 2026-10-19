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
    Supported formats: .wav, .mp3, .m4a, .flac, .ogg, .webm
    """
    if not audio_path:
        raise ValueError("Audio path cannot be empty.")
    if not os.path.exists(audio_path):
        raise FileNotFoundError(f"Audio file not found: {audio_path}")
    if not os.access(audio_path, os.R_OK):
        raise PermissionError(f"Audio file not readable: {audio_path}")
    
    ext = os.path.splitext(audio_path)[1].lower()
    if ext not in [".wav", ".mp3", ".m4a", ".flac", ".ogg", ".webm"]:
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
        # Inspect compressed container metadata without decoding the full recording.
        try:
            import av
            with av.open(audio_path) as container:
                streams = list(container.streams.audio)
                if not streams:
                    raise ValueError("No audio stream found")
                stream = streams[0]
                sample_rate = stream.codec_context.sample_rate
                channels = stream.codec_context.channels
                if stream.duration is not None and stream.time_base is not None:
                    duration = float(stream.duration * stream.time_base)
                elif container.duration is not None:
                    duration = float(container.duration / av.time_base)
                else:
                    raise ValueError("Audio container has no duration metadata; full-file decoding is disabled")
        except Exception as ex:
            raise ValueError(f"Could not read audio file metadata: {ex}")
            
    import math
    if not math.isfinite(duration) or duration <= 0 or not sample_rate or not channels:
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
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0, description="ASR model confidence if actually supplied")
    language_code: Optional[str] = Field(default=None, description="Detected language if actually supplied")


class ASRSegment(CoreBaseModel):
    """Contiguous speech segment attributed to a single speaker turn."""
    segment_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    speaker_id: Optional[str] = Field(default=None, description="Speaker identifier if available")
    start_time: float = Field(..., ge=0.0)
    end_time: float = Field(..., ge=0.0)
    transcript: str = Field(..., description="Transcribed text segment")
    detected_language: Optional[str] = Field(default=None, description="Primary detected language code, if supplied")
    words: List[ASRWordTimestamp] = Field(default_factory=list)
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ASRResult(CoreBaseModel):
    """Complete ASR processing output for a meeting audio payload."""
    meeting_id: uuid.UUID
    full_transcript: str
    detected_languages: List[str] = Field(default_factory=list)
    language_distribution: Dict[str, float] = Field(default_factory=dict)
    segments: List[ASRSegment] = Field(default_factory=list)
    overall_confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
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
        self.precision = self.config.get("precision", get_settings().OPENMOSS_PRECISION)
        self.model = None
        self.processor = None
        self.last_raw_output = None
        self.last_inference = {}

    def _load_model(self):
        """Loads MOSS weights and processor once per provider instance / process."""
        import time
        started_load = time.perf_counter()
        self.last_load_seconds = 0.0
        if self.model is not None and self.processor is not None:
            return

        cache_key = f"{self.model_id}:{self.device}:{self.precision}:{self.cache_dir}"
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

            if (is_cuda and self.precision not in {"nf4", "bf16"}) or (not is_cuda and self.precision not in {"dynamic_int8", "fp32"}):
                raise RuntimeError("Selected MOSS precision is incompatible with the requested device")

            if is_cuda and self.precision == "bf16":
                if not torch.cuda.is_bf16_supported():
                    raise RuntimeError("Configured BF16 CUDA execution is unsupported; no precision fallback")
                self.model = AutoModelForCausalLM.from_pretrained(
                    self.model_id, trust_remote_code=True, cache_dir=self.cache_dir,
                    token=self.token, device_map={"": str(requested_device)},
                    dtype=torch.bfloat16, local_files_only=True)
                logger.info("REAL MODEL LOADED: Open-MOSS with explicitly configured BF16 CUDA precision.")
            elif is_cuda:
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
                    logger.info("Selected Open-MOSS CPU precision: %s", self.precision)
                    self.model = torch.ao.quantization.quantize_dynamic(
                        raw_model,
                        {torch.nn.Linear},
                        dtype=torch.qint8,
                    ) if self.precision == "dynamic_int8" else raw_model
                    logger.info("REAL MODEL LOADED: Open-MOSS on CPU with precision %s.", self.precision)
                except Exception as q_ex:
                    raise RuntimeError("Selected CPU MOSS precision could not load; no precision fallback is permitted") from q_ex

            OpenMOSSProvider._cached_model = self.model
            OpenMOSSProvider._cached_processor = self.processor
            OpenMOSSProvider._cached_model_key = cache_key
            self.last_load_seconds = time.perf_counter() - started_load
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
            from moss_transcribe_diarize.inference_utils import build_transcription_messages, generate_transcription, DEFAULT_PROMPT
            base_prompt = DEFAULT_PROMPT + (
                "\nTranscribe the speech verbatim in its original spoken languages. "
                "Preserve language switches, names, repetitions and audible words. "
                "Do not translate, summarize, paraphrase, answer questions or add words "
                "that are not audible. Retain the required timestamp and speaker format."
            )
            # A declared input language is metadata, never a reference transcript.
            # Do not default Bengali/Tamil/etc. speech to a Hindi writing system.
            language_hint = (options or {}).get("language_hint", self.config.get("language_hint"))
            language_hints = (options or {}).get("language_hints", self.config.get("language_hints")) or []
            if language_hint:
                language_hints = [language_hint]
            if not isinstance(language_hints, (list, tuple)):
                raise ValueError("Declared languages must be a list")
            hint_map = {
                "en": ("English", "Latin"), "hi": ("Hindi", "Devanagari"),
                "bn": ("Bengali", "Bengali"), "gu": ("Gujarati", "Gujarati"),
                "kn": ("Kannada", "Kannada"), "ml": ("Malayalam", "Malayalam"),
                "mr": ("Marathi", "Devanagari"), "pa": ("Punjabi", "Gurmukhi"),
                "ta": ("Tamil", "Tamil"), "te": ("Telugu", "Telugu"),
                "ur": ("Urdu", "Perso-Arabic"), "zh": ("Chinese", "Chinese"),
                "ja": ("Japanese", "Japanese"), "fr": ("French", "Latin"),
                "es": ("Spanish", "Latin"), "de": ("German", "Latin"),
                "ru": ("Russian", "Cyrillic"), "ar": ("Arabic", "Arabic"),
                "hinglish": ("Hindi-English code-switching", "Devanagari for Hindi and Latin for English"),
                "tanglish": ("Tamil-English code-switching", "Tamil for Tamil and Latin for English"),
                "spanglish": ("Spanish-English code-switching", "Latin"),
                "franglais": ("French-English code-switching", "Latin"),
                "arabiya-english": ("Arabic-English code-switching", "Arabic for Arabic and Latin for English"),
            }
            declared_hints = []
            for hint in language_hints:
                hint = str(hint).strip().lower()
                hint = hint if hint in hint_map else hint.replace("-", "_").split("_")[0]
                if hint not in hint_map:
                    raise ValueError("Unsupported explicit MOSS language hint")
                if hint not in declared_hints:
                    declared_hints.append(hint)
            for hint in declared_hints:
                language_name, script = hint_map[hint]
                base_prompt += (f"\nInput language metadata: {language_name}. "
                    f"Write {language_name} speech using the {script} writing system. "
                    "Preserve any actually spoken language switches. Do not translate.")
            language_hint = declared_hints[0] if len(declared_hints) == 1 else None
            messages = build_transcription_messages(audio_path, prompt=base_prompt)
            recover_format = bool((options or {}).get("recover_format"))
            recover_loop = bool((options or {}).get("recover_token_loop"))
            recover_final = bool((options or {}).get("recover_final_bounds"))
            if recover_format or recover_loop or recover_final:
                from moss_transcribe_diarize.inference_utils import DEFAULT_PROMPT
                messages = build_transcription_messages(audio_path, prompt=base_prompt +
                    "\nReturn the timestamped diarized transcription only. Every spoken turn must begin "
                    "with its start time in seconds in brackets and a bracketed S01/S02 speaker ID, "
                    "then the spoken words, then its end time in seconds in brackets. "
                    "Use times actually inferred from this audio. Do not return untagged text or commentary.")
                if recover_loop or recover_final:
                    messages = build_transcription_messages(audio_path, prompt=base_prompt +
                        f"\nThis input is {audio_metadata['duration']:.3f} seconds long. "
                        "Transcribe only speech actually audible in this input, using the required "
                        "timestamp and speaker format. Finish after this input ends. "
                        "Do not continue an empty timestamp/speaker sequence or invent speech.")
            device = next(self.model.parameters()).device
            started = time.perf_counter()
            token_budget = int((options or {}).get("max_new_tokens", get_settings().OPENMOSS_MAX_NEW_TOKENS))
            recovery = bool((options or {}).get("recover_repetition"))
            recover_bounds = bool((options or {}).get("recover_bounds"))
            recovery = recovery or recover_bounds or recover_format or recover_loop or recover_final
            original_generation_config = self.model.generation_config
            if recovery:
                import copy
                guarded = copy.deepcopy(original_generation_config)
                guarded.no_repeat_ngram_size = 0 if (recover_bounds or recover_format or recover_loop) else 12
                guarded.repetition_penalty = 1.15 if recover_loop else (1.0 if recover_format else (1.15 if recover_bounds else 1.05))
                self.model.generation_config = guarded
                if recover_final:
                    guarded.num_beams = 2
                    guarded.no_repeat_ngram_size = 0
                    guarded.repetition_penalty = 1.15
            try:
                result = generate_transcription(self.model, self.processor, messages,
                    max_new_tokens=token_budget, do_sample=False,
                    device=torch.device(device), dtype=self.model.dtype)
            finally:
                self.model.generation_config = original_generation_config
            self.last_raw_output = result["text"]
            self.last_inference = {"raw_output_type": type(result).__name__, "raw_output_keys": list(result),
                                   "generated_tokens": result["generated_tokens"], "prompt_tokens": result["prompt_len"],
                                   "generation_seconds": time.perf_counter() - started, "device": str(device),
                                   "precision": self.precision,
                                   "transcription_policy": "verbatim_declared_languages_v2",
                                   "language_hint": language_hint,
                                   "declared_language_hints": declared_hints,
                                   "language_hint_source": "declared_input_metadata" if declared_hints else "NOT AVAILABLE",
                                   "model_load_seconds": self.last_load_seconds,
                                   "max_new_tokens": token_budget,
                                   "timestamp_boundary_policy": "processor_token_v1"}
            if (options or {}).get("boundary_context"):
                self.last_inference["boundary_context"] = options["boundary_context"]
            if recovery:
                self.last_inference.update(recovery_attempt=("bounded_bounds_beam_v5" if recover_final else "bounded_token_loop_prompt_v4" if recover_loop else "bounded_format_prompt_v3" if recover_format else
                                               "bounded_timestamp_guard_v2" if recover_bounds else "bounded_repetition_guard_v1"),
                                           no_repeat_ngram_size=guarded.no_repeat_ngram_size,
                                           repetition_penalty=guarded.repetition_penalty)
                if recover_final:
                    self.last_inference["num_beams"] = guarded.num_beams
            generation_journal = (options or {}).get("generation_journal")
            if generation_journal is not None:
                generation_journal({"raw_moss_output": self.last_raw_output, **self.last_inference})
            if result["generated_tokens"] >= token_budget:
                raise ValueError("MOSS reached its generation token limit; truncated output cannot be accepted as complete transcription")
            decoded_text = result["text"]
            
            # Parse decoded_text into ASRSegment formats
            chunk_meta = options.get("chunk_meta") if options else None
            segments = self._normalize_moss_output(decoded_text, audio_metadata["duration"], chunk_meta)
            
            logger.info(
                "REAL INFERENCE SUCCEEDED: Extracted %d segments from %s",
                len(segments), audio_path
            )
            return segments
            
        except Exception as ex:
            logger.error("REAL INFERENCE FAILED: Open-MOSS inference error on %s: %s", audio_path, ex)
            raise RuntimeError(f"Open-MOSS inference failed: {ex}") from ex

    def _normalize_moss_output(self, text, duration, chunk_meta=None):
        self.last_inference.pop("nonlexical_turns", None)
        self.last_inference.pop("right_context_only_turns", None)
        context = self.last_inference.get("boundary_context")
        if context:
            if (chunk_meta is None or context["owned_duration"] != chunk_meta.duration
                    or not 0 < context["input_duration"] - chunk_meta.duration <= get_settings().AUDIO_CHUNK_OVERLAP_SECONDS + 0.001):
                raise ValueError("Invalid bounded audio context")
            duration = context["input_duration"]
        try:
            segments = self._parse_moss_output(text, chunk_meta=chunk_meta)
        except ValueError as exc:
            # A trailing turn beginning wholly in following context belongs to
            # the next chunk. Keep its incomplete evidence, never invent its
            # end time or publish it as a transcript segment.
            import re
            import math
            trailing = re.fullmatch(r"\s*\[(\d+(?:\.\d+)?)\]\[(S\d+)\]\s*([^\[\]]+)\s*", text or "")
            if (context and trailing
                    and str(exc) == "MOSS output has no timestamped segments; timestamps cannot be fabricated"
                    and self.last_inference.get("generated_tokens", 0) < self.last_inference.get("max_new_tokens", 0)):
                start = float(trailing.group(1))
                if math.isfinite(start) and context["owned_duration"] <= start < duration:
                    self.last_inference["parsed_segments_before_audio_bounds"] = 0
                    self.last_inference["right_context_only_turns"] = [{
                        "start_time": start, "end_time": None, "speaker_id": trailing.group(2),
                        "transcript": trailing.group(3).strip(),
                        "reason": "incomplete_turn_entirely_in_following_context"}]
                    return []
            raise
        self.last_inference["parsed_segments_before_audio_bounds"] = len(segments)
        # Model times are estimates at the actual processor's audio-token
        # resolution. Bound an edge estimate only within one such token;
        # retain both original and normalized times for audit.
        if not hasattr(self, "_audio_time_resolution"):
            import json
            from pathlib import Path
            from huggingface_hub import try_to_load_from_cache
            config_path = Path(self.model_id) / "processor_config.json"
            if not config_path.is_file():
                config_path = try_to_load_from_cache(self.model_id, "processor_config.json",
                    cache_dir=self.cache_dir or get_settings().OPENMOSS_CACHE_DIR)
            cfg = json.loads(Path(config_path).read_text()) if isinstance(config_path, (str, Path)) else {}
            rate = float(cfg.get("audio_tokens_per_second", 0))
            self._audio_time_resolution = 1.0 / rate if rate > 0 else 0.0
        resolution = self._audio_time_resolution if self.last_inference.get("timestamp_boundary_policy") == "processor_token_v1" else 0.0
        segments, rejected = self._validate_audio_bounds(segments, duration, resolution)
        self.last_inference["timestamp_boundary_adjustments"] = [
            s.metadata["timestamp_boundary_normalization"] for s in segments
            if "timestamp_boundary_normalization" in s.metadata]
        self.last_inference["rejected_audio_bounds"] = rejected
        if not segments:
            turns = self.last_inference.get("nonlexical_turns")
            valid_turns = [t for t in (turns or []) if t["start"] < duration and t["end"] <= duration]
            self.last_inference["rejected_nonlexical_audio_bounds"] = [
                {**t, "reason": "outside_input_audio"} for t in (turns or [])
                if t["start"] >= duration or t["end"] > duration]
            if not valid_turns:
                raise ValueError("MOSS generated no structured transcript segments.")
            # Match lexical-turn bounds handling: retain actual in-range
            # nonlexical evidence, never clip a model timestamp or add words.
            self.last_inference["nonlexical_turns"] = valid_turns
        if context:
            # Actual following audio is context, owned by subsequent chunks.
            # Retain its evidence without publishing its words twice.
            excluded = [s for s in segments if s.start_time >= context["owned_duration"]]
            segments = [s for s in segments if s.start_time < context["owned_duration"]]
            self.last_inference["right_context_only_turns"] = [s.model_dump(mode="json") for s in excluded]
        return segments

    @staticmethod
    def _validate_audio_bounds(segments, duration, boundary_resolution=0.0):
        """Bound sub-token edge estimates with provenance; reject larger errors."""
        valid, rejected = [], []
        for segment in segments:
            if segment.start_time < duration and segment.end_time <= duration:
                valid.append(segment)
            elif (0 <= segment.start_time < duration < segment.end_time
                    and segment.end_time - duration <= boundary_resolution):
                adjustment = {"original_start": segment.start_time, "original_end": segment.end_time,
                    "normalized_end": duration, "audio_token_resolution_seconds": boundary_resolution,
                    "reason": "sub_token_estimate_at_input_boundary"}
                valid.append(segment.model_copy(update={"end_time": duration,
                    "metadata": {**segment.metadata, "timestamp_boundary_normalization": adjustment}}))
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
        parsed = parse_transcript(text, skip_empty=False)
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
            if chunk_meta is not None and parsed and all(not turn.text.strip() for turn in parsed):
                # Actual timestamped nonlexical turns are valid chunk evidence,
                # but must never become fabricated words or silence labels.
                self.last_inference["nonlexical_turns"] = [
                    {"start": turn.start, "end": turn.end, "speaker": turn.speaker} for turn in parsed]
                return []
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
        "zh", "ja", "fr", "es", "de", "ru", "ar", "ur",
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
        "ur": "Urdu",
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

    @classmethod
    def _declared_languages(cls, languages):
        """Canonicalize explicit metadata, without treating it as detection."""
        if languages is None:
            return []
        if not isinstance(languages, (list, tuple)):
            raise ValueError("Declared ASR languages must be a list")
        result = []
        for value in languages:
            if not isinstance(value, str):
                raise ValueError("Declared ASR language must be a string")
            code = value.strip().lower()
            if code in {"auto", "und", "unknown"}:
                continue
            code = code if code in cls.SUPPORTED_LANGUAGES else code.replace("-", "_").split("_")[0]
            if code not in cls.SUPPORTED_LANGUAGES:
                raise ValueError(f"Unsupported requested ASR language: {code}")
            if code not in result:
                result.append(code)
        return result

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
        cancel_check=None,
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

        declared_languages = self._declared_languages(target_languages)
        langs = declared_languages or ["hi", "en", "hinglish"]

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
            if exec_mode == "REAL" and not is_fixture_mode and settings.BATCH_ASR_PROVIDER == "whisper":
                return await self._transcribe_whisper(tmp_path, meeting_id, declared_languages,
                    correlation_id, force_chunked, cancel_check)

            # Check if chunked processing is triggered
            if (duration > threshold and duration > 0.0) or force_chunked:
                return await self.transcribe_long_audio(
                    audio_file_path=tmp_path,
                    meeting_id=meeting_id,
                    target_languages=declared_languages or None,
                    correlation_id=correlation_id,
                    use_fixture=is_fixture_mode,
                    chunk_duration=chunk_duration,
                    overlap_duration=overlap_duration,
                    cancel_check=cancel_check,
                )

            if exec_mode == "REAL" and not is_fixture_mode:
                # Run the actual Open-MOSS transcription in a single pass
                provider = OpenMOSSProvider({
                    "model_id": settings.OPENMOSS_MODEL_ID,
                    "device": settings.OPENMOSS_DEVICE,
                    "cache_dir": settings.OPENMOSS_CACHE_DIR,
                    "token": settings.HF_TOKEN,
                    "language_hints": declared_languages,
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

    async def _transcribe_whisper(self, path, meeting_id, languages, correlation_id,
                                  force_chunked=False, cancel_check=None):
        """Use the existing bounded reconstruction/persistence path explicitly."""
        import hashlib
        import json
        from pathlib import Path
        from app.ai.whisper_provider import WhisperHFProvider
        from app.ai.long_audio_processor import LongAudioProcessor
        from app.ai.asr_selection import batch_asr_identity
        settings = get_settings()
        identity = batch_asr_identity(settings)
        duration = validate_audio(path)["duration"]
        chunk_seconds = settings.WHISPER_CHUNK_DURATION_SECONDS
        overlap = settings.WHISPER_CHUNK_OVERLAP_SECONDS
        if not 0 < overlap < chunk_seconds:
            raise ValueError("Whisper requires 0 < overlap < bounded chunk duration")
        provider = WhisperHFProvider(languages)
        inference = []
        history = Path(settings.AUDIO_CHUNK_STATE_DIR)/str(meeting_id) if settings.AUDIO_CHUNK_STATE_DIR else None
        if history:
            history.mkdir(parents=True, exist_ok=True)
        async def transcribe_chunk(chunk_path, meta):
            digest = hashlib.sha256(Path(chunk_path).read_bytes()).hexdigest()
            journal = history/f"whisper_inference_{meta.chunk_id}.json" if history else None
            if journal and journal.exists():
                saved = json.loads(journal.read_text(encoding="utf-8"))
                if (saved.get("audio_sha256") != digest or saved.get("provider_identity") != identity
                        or saved.get("declared_languages") != languages or saved.get("execution_mode") != "REAL"):
                    raise RuntimeError("Whisper chunk journal identity mismatch")
                inference.append({**saved["inference"], "restored": True})
                return [ASRSegment.model_validate(x) for x in saved["segments"]]
            def save_raw(value):
                if history:
                    target = history/f"whisper_generation_{meta.chunk_id}.json"
                    temporary = target.with_suffix(".tmp")
                    temporary.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
                    temporary.replace(target)
            segments = await provider.transcribe(chunk_path, {"generation_journal": save_raw})
            inference.append({**provider.last_inference, "chunk_id": str(meta.chunk_id)})
            if journal:
                temporary = journal.with_suffix(".tmp")
                temporary.write_text(json.dumps({"execution_mode": "REAL", "audio_sha256": digest,
                    "provider_identity": identity, "declared_languages": languages,
                    "inference": provider.last_inference, "raw_provider_output": provider.last_raw_output,
                    "segments": [x.model_dump(mode="json") for x in segments]}, ensure_ascii=False), encoding="utf-8")
                temporary.replace(journal)
            return segments
        if duration > chunk_seconds or force_chunked:
            processor = LongAudioProcessor(chunk_duration=chunk_seconds, overlap_duration=overlap)
            reconstructed = await processor.process_long_audio(path, meeting_id, transcribe_chunk,
                correlation_id=correlation_id, cancel_check=cancel_check,
                transcription_context={"declared_languages": languages, "provider": "whisper"})
            result = reconstructed.asr_result
        else:
            def save_short_raw(value):
                if history:
                    target = history / "whisper_short_generation.json"
                    temporary = target.with_suffix(".tmp")
                    temporary.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
                    temporary.replace(target)
            segments = await provider.transcribe(path, {"generation_journal": save_short_raw})
            inference.append(provider.last_inference)
            result = ASRResult(meeting_id=meeting_id, full_transcript=" ".join(x.transcript for x in segments),
                segments=segments, overall_confidence=None, metadata={"chunk_count": 1,
                    "raw_provider_output": provider.last_raw_output})
        if not result.segments or not result.full_transcript.strip():
            raise RuntimeError("REAL Whisper produced no nonempty meeting transcript")
        result.metadata.update(provider="whisper", model_name=settings.WHISPER_MODEL_ID,
            is_fixture=False, inference=inference, correlation_id=correlation_id,
            chunk_count=result.metadata.get("total_chunks", 1),
            chunk_duration_seconds=chunk_seconds, overlap_duration_seconds=overlap,
            task="transcribe", translation=False, declared_languages=languages,
            transcription_accuracy="NOT VERIFIED", speaker_identity_source="PyAnnote reconciliation required")
        return result

    async def transcribe_long_audio(
        self,
        audio_file_path: str,
        meeting_id: uuid.UUID,
        target_languages: Optional[List[str]] = None,
        correlation_id: Optional[str] = None,
        use_fixture: bool = False,
        chunk_duration: Optional[float] = None,
        overlap_duration: Optional[float] = None,
        cancel_check=None,
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
        if exec_mode == "REAL" and settings.BATCH_ASR_PROVIDER == "whisper":
            return await self._transcribe_whisper(audio_file_path, meeting_id,
                self._declared_languages(target_languages), correlation_id, True, cancel_check)

        processor = LongAudioProcessor(
            chunk_duration=chunk_duration,
            overlap_duration=overlap_duration,
        )

        # Initialize OpenMOSSProvider once per long-audio run in REAL mode
        real_provider: Optional[OpenMOSSProvider] = None
        declared_languages = self._declared_languages(target_languages)
        if exec_mode == "REAL" and not use_fixture:
            real_provider = OpenMOSSProvider({
                "model_id": settings.OPENMOSS_MODEL_ID,
                "device": settings.OPENMOSS_DEVICE,
                "cache_dir": settings.OPENMOSS_CACHE_DIR,
                "token": settings.HF_TOKEN,
                "language_hints": declared_languages,
            })

        inference_trace = []
        async def _transcribe_chunk(chunk_path: str, chunk_meta: ChunkMetadata) -> List[ASRSegment]:
            if exec_mode == "REAL" and not use_fixture:
                if real_provider is None:
                    raise RuntimeError("REAL mode requested but OpenMOSSProvider was not initialized.")
                import json
                from pathlib import Path
                history = Path(settings.AUDIO_CHUNK_STATE_DIR) / str(meeting_id) if settings.AUDIO_CHUNK_STATE_DIR else None
                if history is not None:
                    history.mkdir(parents=True, exist_ok=True)
                evidence_path = history / f"inference_{chunk_meta.chunk_id}.json" if history is not None else None
                generation_path = history / f"generation_{chunk_meta.chunk_id}.json" if history is not None else None
                if evidence_path is not None and evidence_path.exists():
                    saved = json.loads(evidence_path.read_text(encoding="utf-8"))
                    if (saved.get("chunk_id") != str(chunk_meta.chunk_id) or saved.get("execution_mode") != "REAL"
                            or saved.get("start_time") != chunk_meta.start_time or saved.get("end_time") != chunk_meta.end_time):
                        raise RuntimeError("Invalid actual chunk inference journal")
                    restored = [ASRSegment.model_validate(row) for row in saved.pop("segment_payloads")]
                    if not saved.get("raw_moss_output"):
                        raise RuntimeError("Actual chunk inference journal is empty")
                    if not restored:
                        real_provider.last_inference = dict(saved)
                        normalized = real_provider._normalize_moss_output(saved["raw_moss_output"], chunk_meta.duration, chunk_meta)
                        if normalized or not (real_provider.last_inference.get("nonlexical_turns") or real_provider.last_inference.get("right_context_only_turns")):
                            raise RuntimeError("Empty chunk journal lacks actual nonlexical model evidence")
                    inference_trace.append({**saved, "recovered_from_inference_journal": True})
                    return restored
                import hashlib
                chunk_digest = hashlib.sha256(Path(chunk_path).read_bytes()).hexdigest()
                def journal_generation(generated):
                    if generation_path is not None:
                        temporary = generation_path.with_name(f"{generation_path.stem}_{uuid.uuid4().hex}.tmp")
                        with temporary.open("x", encoding="utf-8") as output:
                            json.dump({**generated, "chunk_id": str(chunk_meta.chunk_id), "execution_mode": "REAL",
                                       "start_time": chunk_meta.start_time, "end_time": chunk_meta.end_time,
                                       "chunk_audio_sha256": chunk_digest}, output)
                        temporary.replace(generation_path)
                async def recover_with_context(generated):
                    format_retry = bool(generated.get("boundary_context"))
                    if format_retry and generated.get("recovery_attempt") == "bounded_format_prompt_v3":
                        raise RuntimeError("Bounded audio-context recovery failed")
                    metadata = validate_audio(audio_file_path)
                    extra = min(settings.AUDIO_CHUNK_OVERLAP_SECONDS, metadata["duration"] - chunk_meta.end_time)
                    if extra <= 0:
                        raise RuntimeError("No real following audio exists for boundary recovery")
                    archive = history / f"generation_failed_{'context_format' if format_retry else 'before_context'}_{chunk_meta.chunk_id}.json"
                    if not archive.exists():
                        archive.write_text(json.dumps(generated), encoding="utf-8")
                    extended = chunk_meta.model_copy(update={"end_time": chunk_meta.end_time + extra,
                                                              "duration": chunk_meta.duration + extra})
                    context_path = processor.slice_audio_file(audio_file_path, extended)
                    try:
                        context = {"owned_duration": chunk_meta.duration, "input_duration": extended.duration,
                                   "input_end_time": extended.end_time,
                                   "input_audio_sha256": hashlib.sha256(Path(context_path).read_bytes()).hexdigest()}
                        if format_retry and context != generated["boundary_context"]:
                            raise RuntimeError("Saved boundary context differs from actual recovery audio")
                        return await real_provider.transcribe(context_path, options={
                            "chunk_meta": chunk_meta, "generation_journal": journal_generation,
                            "recover_token_loop": not format_retry, "recover_format": format_retry,
                            "boundary_context": context})
                    finally:
                        Path(context_path).unlink(missing_ok=True)
                async def transcribe_recovery(options):
                    before = generation_path.read_bytes() if generation_path and generation_path.exists() else None
                    try:
                        return await real_provider.transcribe(chunk_path, options=options)
                    except RuntimeError:
                        if not generation_path or not generation_path.exists() or generation_path.read_bytes() == before:
                            raise
                        latest = json.loads(generation_path.read_text(encoding="utf-8"))
                        if latest["generated_tokens"] >= latest["max_new_tokens"]:
                            return await recover_token_limited_chunk(latest)
                        return await normalize_saved_generation(latest)
                async def recover_token_limited_chunk(generated):
                    previous_attempt = generated.get("recovery_attempt")
                    if generated.get("boundary_context"):
                        if previous_attempt != "bounded_format_prompt_v3":
                            return await recover_with_context(generated)
                        raise RuntimeError("Bounded audio-context generation reached its token limit")
                    if previous_attempt in {"bounded_token_loop_prompt_v4", "bounded_bounds_beam_v5"}:
                        return await recover_with_context(generated)
                    # Keep the failed output before a single guarded retry.
                    failed_path = history / f"generation_failed_token_limit_{previous_attempt or 'initial'}_{chunk_meta.chunk_id}.json"
                    if not failed_path.exists():
                        with failed_path.open("x", encoding="utf-8") as output:
                            json.dump(generated, output)
                    try:
                        return await transcribe_recovery({
                            "chunk_meta": chunk_meta, "generation_journal": journal_generation,
                            "recover_repetition": not previous_attempt, "recover_token_loop": bool(previous_attempt)})
                    except RuntimeError:
                        # A chunk's second bounded recovery must not consume a
                        # retry of the entire meeting before it can run.
                        if previous_attempt or generation_path is None or not generation_path.exists():
                            raise
                        retry = json.loads(generation_path.read_text(encoding="utf-8"))
                        if (retry.get("recovery_attempt") != "bounded_repetition_guard_v1"
                                or retry["generated_tokens"] < retry["max_new_tokens"]):
                            raise
                        return await recover_token_limited_chunk(retry)
                async def normalize_saved_generation(generated):
                    real_provider.last_raw_output = generated["raw_moss_output"]
                    real_provider.last_inference = dict(generated)
                    try:
                        return real_provider._normalize_moss_output(generated["raw_moss_output"], chunk_meta.duration, chunk_meta)
                    except ValueError as exc:
                        if generated.get("boundary_context"):
                            return await recover_with_context(generated)
                        if (str(exc) == "MOSS generated no structured transcript segments."
                                and not generated.get("timestamp_boundary_policy")):
                            real_provider.last_inference["timestamp_boundary_policy"] = "processor_token_v1"
                            try:
                                return real_provider._normalize_moss_output(generated["raw_moss_output"], chunk_meta.duration, chunk_meta)
                            except ValueError:
                                real_provider.last_inference = dict(generated)
                        if (str(exc) == "MOSS output has no timestamped segments; timestamps cannot be fabricated"
                                and generated.get("recovery_attempt") not in {"bounded_format_prompt_v3", "bounded_token_loop_prompt_v4", "bounded_bounds_beam_v5"}):
                            failed_path = history / f"generation_failed_format_{chunk_meta.chunk_id}.json"
                            if not failed_path.exists():
                                with failed_path.open("x", encoding="utf-8") as output:
                                    json.dump(generated, output)
                            return await transcribe_recovery({
                                "chunk_meta": chunk_meta, "generation_journal": journal_generation,
                                "recover_format": True})
                        recoverable = {"MOSS returned invalid segment bounds",
                                       "MOSS generated no structured transcript segments.",
                                       "MOSS output has no timestamped segments; timestamps cannot be fabricated"}
                        if str(exc) in recoverable and generated.get("recovery_attempt") == "bounded_timestamp_guard_v2":
                            failed_path = history / f"generation_failed_bounds_v2_{chunk_meta.chunk_id}.json"
                            if not failed_path.exists():
                                with failed_path.open("x", encoding="utf-8") as output:
                                    json.dump(generated, output)
                            return await transcribe_recovery({
                                "chunk_meta": chunk_meta, "generation_journal": journal_generation,
                                "recover_token_loop": True})
                        if str(exc) in recoverable and generated.get("recovery_attempt") == "bounded_token_loop_prompt_v4":
                            failed_path = history / f"generation_failed_bounds_v4_{chunk_meta.chunk_id}.json"
                            if not failed_path.exists():
                                with failed_path.open("x", encoding="utf-8") as output:
                                    json.dump(generated, output)
                            return await transcribe_recovery({
                                "chunk_meta": chunk_meta, "generation_journal": journal_generation,
                                "recover_final_bounds": True})
                        if str(exc) in recoverable and generated.get("recovery_attempt") == "bounded_bounds_beam_v5":
                            return await recover_with_context(generated)
                        if (str(exc) not in recoverable
                                or generated.get("recovery_attempt") in {"bounded_timestamp_guard_v2", "bounded_format_prompt_v3", "bounded_token_loop_prompt_v4", "bounded_bounds_beam_v5"}):
                            raise
                        # N-gram suppression can break repeated timestamp grammar.
                        # Preserve the failed generation and retry once without
                        # banning token sequences; strict parsing still applies.
                        failed_path = history / f"generation_failed_bounds_{chunk_meta.chunk_id}.json"
                        if not failed_path.exists():
                            with failed_path.open("x", encoding="utf-8") as output:
                                json.dump(generated, output)
                        return await transcribe_recovery({
                            "chunk_meta": chunk_meta, "generation_journal": journal_generation,
                            "recover_bounds": True})
                recovered_generation = generation_path is not None and generation_path.exists()
                if recovered_generation:
                    generated = json.loads(generation_path.read_text(encoding="utf-8"))
                    if (generated.get("chunk_id") != str(chunk_meta.chunk_id) or generated.get("execution_mode") != "REAL"
                            or generated.get("chunk_audio_sha256") != chunk_digest
                            or generated.get("start_time") != chunk_meta.start_time or generated.get("end_time") != chunk_meta.end_time):
                        raise RuntimeError("Saved raw generation differs from actual chunk")
                    if generated["generated_tokens"] >= generated["max_new_tokens"]:
                        segments = await recover_token_limited_chunk(generated)
                    else:
                        segments = await normalize_saved_generation(generated)
                else:
                    try:
                        segments = await real_provider.transcribe(chunk_path, options={
                            "chunk_meta": chunk_meta, "generation_journal": journal_generation})
                    except RuntimeError:
                        # Handle a newly observed token-limit failure in this
                        # chunk, rather than restarting the entire ACE stage.
                        if generation_path is None or not generation_path.exists():
                            raise
                        failed = json.loads(generation_path.read_text(encoding="utf-8"))
                        if failed["generated_tokens"] < failed["max_new_tokens"]:
                            segments = await normalize_saved_generation(failed)
                        else:
                            segments = await recover_token_limited_chunk(failed)
                trace = {"chunk_id": str(chunk_meta.chunk_id), "execution_mode": "REAL",
                    "chunk_index": chunk_meta.chunk_index, "start_time": chunk_meta.start_time,
                    "end_time": chunk_meta.end_time, "segments": len(segments),
                    "raw_moss_output": real_provider.last_raw_output, **real_provider.last_inference,
                    "recovered_from_generation_journal": recovered_generation}
                if evidence_path is not None:
                    temporary = evidence_path.with_name(f"{evidence_path.stem}_{uuid.uuid4().hex}.tmp")
                    temporary.write_text(json.dumps({**trace,
                        "segment_payloads": [segment.model_dump(mode="json") for segment in segments]}), encoding="utf-8")
                    temporary.replace(evidence_path)
                inference_trace.append(trace)
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
            cancel_check=cancel_check,
            transcription_context={"declared_languages": declared_languages,
                                   "policy": "verbatim_declared_languages_v2"},
        )

        recon_result.asr_result.metadata.update(is_fixture=exec_mode != "REAL" or use_fixture,
            model_name=settings.OPENMOSS_MODEL_ID if exec_mode == "REAL" else self.PRETRAINED_MODEL_NAME,
            chunk_count=recon_result.total_chunks, inference=inference_trace)
        if exec_mode == "REAL" and settings.AUDIO_CHUNK_STATE_DIR:
            import json
            from collections import Counter
            from pathlib import Path
            precision_counts = Counter()
            for journal in (Path(settings.AUDIO_CHUNK_STATE_DIR) / str(meeting_id)).glob("inference_*.json"):
                actual = json.loads(journal.read_text(encoding="utf-8"))
                precision_counts[actual.get("precision", "NOT AVAILABLE")] += 1
            recon_result.asr_result.metadata.update(
                chunk_precision_counts=dict(precision_counts), mixed_precision_run=len(precision_counts) > 1)
        if exec_mode == "REAL" and not recon_result.asr_result.segments:
            raise RuntimeError("REAL meeting produced no transcript segments; nonlexical chunks alone are not success")
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
