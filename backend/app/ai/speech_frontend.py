"""Local-only, bounded Silero speech activity analysis before ASR.

No downloading, audio concatenation, timestamp compression or energy-only fallback.
Energy and spectral entropy are diagnostics, not calibrated speech classifiers.
"""
import hashlib
import math
import threading
import time
from pathlib import Path


def merge_speech_frames(frames, duration, collar):
    """Pad observed intervals without changing the source clock or joining audio."""
    if not math.isfinite(duration) or duration <= 0 or not math.isfinite(collar) or collar < 0:
        raise ValueError("Invalid speech interval duration/collar")
    intervals, previous = [], -1.0
    for start, end in frames:
        if not all(math.isfinite(x) for x in (start, end)) or not 0 <= start < end <= duration or start < previous:
            raise ValueError("Speech frames must be chronological and inside the actual input")
        previous = start
        start, end = max(0., start - collar), min(duration, end + collar)
        if intervals and start <= intervals[-1]["end"]:
            intervals[-1]["end"] = max(intervals[-1]["end"], end)
        else:
            intervals.append({"start": start, "end": end})
    return intervals


def speech_frontend_identity(settings):
    mode = settings.AUDIO_VAD_MODE
    identity = {"mode": mode, "policy": "silero_bounded_v1"}
    if mode == "off":
        return identity
    if mode not in {"observe", "filter"}:
        raise ValueError("Unknown VAD mode; no implicit fallback")
    path = Path(settings.AUDIO_VAD_MODEL_PATH or "")
    if not path.is_file():
        raise RuntimeError("Silero VAD enabled but local TorchScript model is missing; no download or fallback")
    identity.update(model_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                    threshold=settings.AUDIO_VAD_THRESHOLD,
                    collar_seconds=settings.AUDIO_VAD_COLLAR_SECONDS)
    return identity


class SpeechFrontend:
    _models = {}
    _lock = threading.Lock()  # Silero carries recurrent state; never share it concurrently.

    def __init__(self, settings):
        self.settings = settings
        self.identity = speech_frontend_identity(settings)

    def analyze(self, audio_path):
        if self.identity["mode"] == "off":
            return {**self.identity, "status": "DISABLED", "speech_detected": None}
        import numpy as np
        import torch
        from app.ai.audio_reader import AudioWindowReader

        started = time.perf_counter()
        # This frontend receives one existing bounded ASR chunk, never a long file.
        maximum = max(self.settings.AUDIO_CHUNK_DURATION_SECONDS,
                      self.settings.WHISPER_CHUNK_DURATION_SECONDS,
                      self.settings.LIVE_CHUNK_SECONDS) + self.settings.AUDIO_CHUNK_OVERLAP_SECONDS
        with AudioWindowReader(audio_path) as reader:
            duration = len(reader) / reader.samplerate
            if not math.isfinite(duration) or not 0 < duration <= maximum + 0.01:
                raise ValueError("VAD requires one bounded ASR window, not an entire long recording")
            waveform = reader.read(len(reader), always_2d=True).mean(axis=1)
            if len(waveform) != len(reader) or not np.isfinite(waveform).all():
                raise ValueError("VAD audio decode is incomplete or contains nonfinite samples")
            if reader.samplerate != 16000:
                import librosa
                waveform = librosa.resample(waveform, orig_sr=reader.samplerate, target_sr=16000)
        waveform = np.ascontiguousarray(waveform, dtype=np.float32)
        decode_seconds = time.perf_counter() - started
        speech_frames, probabilities, energies, entropies = [], [], [], []
        # Silero v5/v6 at 16 kHz requires 512 samples (32 ms), not arbitrary 20 ms.
        with self._lock, torch.inference_mode():
            model_started = time.perf_counter()
            key = self.identity["model_sha256"]
            model = self._models.get(key)
            if model is None:
                path = Path(self.settings.AUDIO_VAD_MODEL_PATH)
                if hashlib.sha256(path.read_bytes()).hexdigest() != key:
                    raise RuntimeError("VAD model changed after execution identity was captured")
                model = torch.jit.load(str(path), map_location="cpu").eval()
                if not hasattr(model, "reset_states"):
                    raise RuntimeError("Configured model does not expose the Silero recurrent-state API")
                self._models[key] = model
            model_load_seconds = time.perf_counter() - model_started
            model.reset_states()
            inference_started = time.perf_counter()
            try:
                for offset in range(0, len(waveform), 512):
                    actual = waveform[offset:offset + 512]
                    # Padding only satisfies neural frame shape; it never becomes ASR input.
                    frame = np.pad(actual, (0, 512 - len(actual)))
                    probability = float(model(torch.from_numpy(frame), 16000).item())
                    if not math.isfinite(probability) or not 0 <= probability <= 1:
                        raise RuntimeError("Silero returned an invalid speech probability")
                    probabilities.append(probability)
                    energies.append(float(np.mean(actual.astype(np.float64) ** 2)))
                    power = np.abs(np.fft.rfft(frame * np.hanning(512))) ** 2
                    total = float(power.sum())
                    distribution = power[power > 0] / total if total else np.array([])
                    entropies.append(float(-np.sum(distribution * np.log2(distribution))))
                    if probability >= self.settings.AUDIO_VAD_THRESHOLD:
                        speech_frames.append((offset / 16000, min(duration, (offset + len(actual)) / 16000)))
            finally:
                model.reset_states()
            inference_seconds = time.perf_counter() - inference_started
        intervals = merge_speech_frames(speech_frames, duration, self.settings.AUDIO_VAD_COLLAR_SECONDS)
        return {**self.identity, "status": "COMPLETED", "device": "cpu",
                "sample_rate": 16000, "frame_samples": 512, "input_duration": duration,
                "frame_count": len(probabilities), "speech_detected": bool(intervals),
                "speech_intervals": intervals, "speech_seconds": sum(x["end"] - x["start"] for x in intervals),
                "speech_probability_min": min(probabilities), "speech_probability_max": max(probabilities),
                "mean_short_time_energy": float(np.mean(energies)),
                "mean_spectral_entropy_bits": float(np.mean(entropies)),
                "analysis_seconds": time.perf_counter() - started,
                "decode_resample_seconds": decode_seconds, "model_load_seconds": model_load_seconds,
                "frame_analysis_seconds": inference_seconds,
                "energy_entropy_policy": "diagnostic_only_uncalibrated",
                "audio_modified": False, "timestamp_offset": 0,
                "accuracy": "NOT VERIFIED"}
