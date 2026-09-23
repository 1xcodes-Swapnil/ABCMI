"""
Open-MOSS (MOSS-Transcribe-Diarize) Adapter Module
Phase 4.26 — Provides decoupled adapter interfaces and implementations for Open-MOSS
multilingual speech recognition, speaker diarization, and model verification.
"""

import os
from typing import Any, Dict, List, Optional
import uuid

from app.core.config import get_settings
from app.core.logging import get_logger
from app.ai.multilingual_asr import (
    ASRProvider,
    OpenMOSSProvider,
    ASRSegment,
    ASRWordTimestamp,
    ASRResult,
    validate_audio,
)

logger = get_logger("ai.moss_adapter")

# Canonical aliases for framework flexibility
MOSSAdapter = OpenMOSSProvider
OpenMOSSAdapter = OpenMOSSProvider


def get_moss_adapter(config: Optional[Dict[str, Any]] = None) -> OpenMOSSProvider:
    """
    Factory function returning an initialized OpenMOSSProvider / MOSSAdapter instance.
    """
    settings = get_settings()
    cfg = config or {}
    if "device" not in cfg:
        cfg["device"] = "cuda" if getattr(settings, "CUDA_AVAILABLE", False) else "cpu"
    return OpenMOSSProvider(config=cfg)


__all__ = [
    "ASRProvider",
    "OpenMOSSProvider",
    "MOSSAdapter",
    "OpenMOSSAdapter",
    "ASRSegment",
    "ASRWordTimestamp",
    "ASRResult",
    "validate_audio",
    "get_moss_adapter",
]
