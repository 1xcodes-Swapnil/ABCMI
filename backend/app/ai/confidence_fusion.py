"""
Confidence Fusion Engine (Phase 4.12C)
Combines available confidence signals across ASR, language detection, speaker diarization,
word timestamps, code-switching, context, and extraction.
Outputs a normalized score (0.0 <= confidence <= 1.0) with deterministic signal weighting,
low-confidence flagging, and full correlation/provenance preservation.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
import uuid
from pydantic import Field

from app.schemas.base import CoreBaseModel
from app.schemas.knowledge_object import ProvenanceMetadataSchema


class ConfidenceSignalBreakdown(CoreBaseModel):
    """Breakdown of individual confidence input signals."""

    asr_confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    language_confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    diarization_confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    timestamp_confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    code_switch_confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    context_confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    extraction_confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)


class ConfidenceFusionResult(CoreBaseModel):
    """Fused confidence processing result payload."""

    meeting_id: uuid.UUID
    fused_confidence: float = Field(..., ge=0.0, le=1.0, description="Normalized score [0.0, 1.0]")
    is_low_confidence: bool = Field(default=False, description="True if fused confidence < threshold")
    confidence_threshold: float = Field(default=0.70)
    signal_breakdown: Dict[str, float] = Field(default_factory=dict)
    weights_applied: Dict[str, float] = Field(default_factory=dict)
    penalties_applied: Dict[str, float] = Field(default_factory=dict)
    correlation_id: Optional[str] = None
    provenance: ProvenanceMetadataSchema
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ConfidenceFusionEngine:
    """
    Deterministic Confidence Fusion Engine.
    Fuses multiple independent AI confidence signals into a single normalized confidence score.
    Supports signal weighting, missing signal re-normalization, and low-confidence flagging.
    """

    DEFAULT_SIGNAL_WEIGHTS = {
        "asr_confidence": 0.25,
        "language_confidence": 0.10,
        "diarization_confidence": 0.20,
        "timestamp_confidence": 0.15,
        "code_switch_confidence": 0.10,
        "context_confidence": 0.10,
        "extraction_confidence": 0.10,
    }

    CONFIDENCE_THRESHOLD = 0.70

    def __init__(self, custom_weights: Optional[Dict[str, float]] = None, confidence_threshold: float = 0.70) -> None:
        self.weights = custom_weights or dict(self.DEFAULT_SIGNAL_WEIGHTS)
        self.confidence_threshold = confidence_threshold

    def fuse_signals(
        self,
        meeting_id: uuid.UUID,
        signals: Dict[str, Optional[float]],
        correlation_id: Optional[str] = None,
        source_module: str = "confidence_fusion",
        model_name: str = "confidence_fusion_v1",
        model_version: str = "1.0.0",
    ) -> ConfidenceFusionResult:
        """
        Fuses a dictionary of confidence signals into a normalized composite confidence score.
        Calculates normalized weights for available signals and applies penalties for critical low signals.
        """
        valid_signals: Dict[str, float] = {}
        applied_weights: Dict[str, float] = {}
        penalties: Dict[str, float] = {}

        for sig_name, sig_val in signals.items():
            if sig_val is not None:
                # Clamp bounded signal [0.0, 1.0]
                clamped_val = max(0.0, min(1.0, float(sig_val)))
                valid_signals[sig_name] = clamped_val

        if not valid_signals:
            # Fallback neutral score if no signals provided
            fused_score = 0.75
            weights_used = {"fallback_neutral": 1.0}
        else:
            # Calculate total weight of available signals
            total_available_weight = sum(
                self.weights.get(k, 0.10) for k in valid_signals.keys()
            )

            if total_available_weight <= 0:
                total_available_weight = len(valid_signals) * 0.10

            weighted_sum = 0.0
            for k, val in valid_signals.items():
                w = self.weights.get(k, 0.10) / total_available_weight
                applied_weights[k] = round(w, 4)
                weighted_sum += val * w

            # Apply low-signal penalties (e.g. if ASR or Diarization < 0.5, apply penalty)
            penalty_factor = 0.0
            if valid_signals.get("asr_confidence", 1.0) < 0.50:
                penalties["low_asr_penalty"] = 0.10
                penalty_factor += 0.10

            if valid_signals.get("diarization_confidence", 1.0) < 0.50:
                penalties["low_diarization_penalty"] = 0.05
                penalty_factor += 0.05

            fused_score = max(0.0, min(1.0, weighted_sum - penalty_factor))
            weights_used = applied_weights

        fused_score = round(fused_score, 4)
        is_low = fused_score < self.confidence_threshold

        prov = ProvenanceMetadataSchema(
            producing_module=source_module,
            model_name=model_name,
            model_version=model_version,
            source_segments=[],
            source_intervals=[],
            lineage={"parent_signals": list(valid_signals.keys())},
            processing_metadata={
                "correlation_id": correlation_id,
                "confidence_threshold": self.confidence_threshold,
                "is_low_confidence": is_low,
            },
        )

        return ConfidenceFusionResult(
            meeting_id=meeting_id,
            fused_confidence=fused_score,
            is_low_confidence=is_low,
            confidence_threshold=self.confidence_threshold,
            signal_breakdown=valid_signals,
            weights_applied=weights_used,
            penalties_applied=penalties,
            correlation_id=correlation_id,
            provenance=prov,
        )
