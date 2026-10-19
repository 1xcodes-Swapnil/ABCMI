"""Local-cache-only Transformers Whisper adapter for explicit REAL batch ASR.

No mock, model download, CPU fallback, translation or invented speaker identity.
Uses the same bounded audio reader, ASR schema and reconstruction contracts.
"""
import math
import time
from app.ai.multilingual_asr import ASRProvider, ASRSegment, ASRWordTimestamp, validate_audio
from app.core.config import get_settings


class WhisperHFProvider(ASRProvider):
    _cache = None
    _cache_key = None

    def __init__(self, languages=None):
        self.languages = languages or []
        self.last_raw_output = None
        self.last_inference = {}
        self.pipe = None

    def _load_model(self):
        import torch
        from transformers import AutoModelForSpeechSeq2Seq, AutoProcessor, pipeline
        from app.ai.model_inventory import configure_cache, snapshot_for
        s = get_settings()
        device = torch.device("cuda:0" if s.OPENMOSS_DEVICE == "auto" else s.OPENMOSS_DEVICE)
        if device.type != "cuda" or not torch.cuda.is_available():
            raise RuntimeError("REAL Whisper requires configured CUDA; no CPU fallback")
        cache = configure_cache()
        snapshot = snapshot_for(s.WHISPER_MODEL_ID, cache)
        if snapshot is None:
            raise RuntimeError("Whisper snapshot missing locally; copy the existing cache, no automatic download")
        key = (str(snapshot), str(device), s.WHISPER_PRECISION)
        if self.__class__._cache_key == key and self.__class__._cache is not None:
            self.pipe = self.__class__._cache
            self.model_load_seconds = 0.0
            self.revision = snapshot.name
            return
        dtype = torch.float16 if s.WHISPER_PRECISION == "fp16" else torch.bfloat16
        if dtype == torch.bfloat16 and not torch.cuda.is_bf16_supported():
            raise RuntimeError("Configured Whisper BF16 unsupported; no precision fallback")
        started = time.perf_counter()
        model = AutoModelForSpeechSeq2Seq.from_pretrained(str(snapshot), local_files_only=True,
            dtype=dtype, use_safetensors=True, low_cpu_mem_usage=True)
        model.to(device).eval()
        processor = AutoProcessor.from_pretrained(str(snapshot), local_files_only=True)
        self.pipe = pipeline("automatic-speech-recognition", model=model,
            tokenizer=processor.tokenizer, feature_extractor=processor.feature_extractor,
            device=device, dtype=dtype)
        self.__class__._cache, self.__class__._cache_key = self.pipe, key
        self.model_load_seconds = time.perf_counter()-started
        self.revision = snapshot.name

    async def transcribe(self, audio_path, options=None):
        import torch
        import numpy as np
        import soxr
        from app.ai.audio_reader import AudioWindowReader
        s = get_settings()
        if s.EXECUTION_MODE.upper() != "REAL":
            raise RuntimeError("WhisperHFProvider is an explicit REAL provider")
        info = validate_audio(audio_path)
        if info["duration"] > 30.001:
            raise ValueError("Whisper input exceeds its bounded 30s contract; use LongAudioProcessor")
        self._load_model()
        with AudioWindowReader(audio_path) as reader:
            rate = reader.samplerate
            audio = reader.read(len(reader), dtype="float32", always_2d=True).mean(axis=1)
        if rate != 16000:
            audio = soxr.resample(audio, rate, 16000)
        if not np.isfinite(audio).all() or not len(audio):
            raise ValueError("Invalid actual Whisper waveform")
        kwargs = {"task": "transcribe", "do_sample": False, "num_beams": 1,
                  "max_new_tokens": 440, "condition_on_prev_tokens": False,
                  "temperature": 0.0}
        # A mixed-language meeting must not be coerced to a single language.
        if len(self.languages) == 1 and self.languages[0] not in {
                "hinglish", "tanglish", "spanglish", "franglais", "arabiya-english"}:
            kwargs["language"] = self.languages[0]
        started = time.perf_counter()
        with torch.inference_mode():
            raw = self.pipe({"array": audio, "sampling_rate": 16000},
                            return_timestamps="word", generate_kwargs=kwargs)
        self.last_raw_output = raw
        self.last_inference = {"provider": "whisper", "execution_mode": "REAL",
            "model_id": s.WHISPER_MODEL_ID, "model_revision": self.revision,
            "device": str(self.pipe.device), "precision": s.WHISPER_PRECISION,
            "model_load_seconds": self.model_load_seconds,
            "generation_seconds": time.perf_counter()-started,
            "task": "transcribe", "translation": False,
            "declared_languages": self.languages, "detected_language_status": "NOT VERIFIED",
            "confidence_status": "NOT VERIFIED", "raw_output_type": type(raw).__name__}
        callback = (options or {}).get("generation_journal")
        if callback:
            callback({"raw_provider_output": raw, **self.last_inference})
        if not isinstance(raw, dict) or not isinstance(raw.get("chunks"), list):
            raise RuntimeError("Whisper returned no timestamped output structure")
        if not str(raw.get("text", "")).strip():
            if raw["chunks"]:
                raise RuntimeError("Whisper text/chunks disagree")
            self.last_inference["empty_model_output"] = True
            return []  # Actual empty model output, not a claim of verified silence.
        if not raw["chunks"]:
            raise RuntimeError("Whisper text has no actual timestamped words")
        import unicodedata
        def text_identity(value):
            return "".join(unicodedata.normalize("NFC", value).split())
        if any(not isinstance(chunk, dict) or not isinstance(chunk.get("text"), str)
               for chunk in raw["chunks"]):
            raise RuntimeError("Whisper returned malformed word records")
        if text_identity(raw["text"]) != text_identity("".join(chunk["text"] for chunk in raw["chunks"])):
            raise RuntimeError("Whisper word records do not cover its actual text; no text silently discarded")
        segments, words = [], []
        previous_start = -1.0
        def flush():
            if not words:
                return
            text = " ".join(w.word.strip() for w in words).strip()
            segments.append(ASRSegment(speaker_id="UNRESOLVED", start_time=words[0].start_time,
                end_time=words[-1].end_time, transcript=text, detected_language=None,
                confidence=None, words=list(words), metadata={"provider": "whisper",
                    "timestamp_source": "model_word_alignment", "speaker_identity_status": "UNRESOLVED"}))
            words.clear()
        for chunk in raw["chunks"]:
            times = chunk.get("timestamp")
            if not times or len(times) != 2 or any(x is None for x in times):
                raise RuntimeError("Whisper word is missing timestamps; no endpoint fabricated")
            left, right = map(float, times)
            if not (math.isfinite(left+right) and 0 <= left <= right <= info["duration"]):
                raise RuntimeError("Whisper word timestamp outside actual audio bounds")
            text = chunk.get("text")
            if not isinstance(text, str) or not text.strip():
                raise RuntimeError("Whisper returned an empty timestamped word")
            if left < previous_start:
                raise RuntimeError("Whisper words are out of order")
            previous_start = left
            if words and (left-words[-1].end_time > .75 or right-words[0].start_time > 5):
                flush()
            words.append(ASRWordTimestamp(word=text.strip(), start_time=left, end_time=right,
                                         confidence=None, language_code=None))
            if text.rstrip().endswith((".", "?", "!", "।", "。", "？", "！")):
                flush()
        flush()
        self.last_inference["parsed_segments"] = len(segments)
        return segments
