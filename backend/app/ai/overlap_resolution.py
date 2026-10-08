"""
Overlap Resolution Engine
Provides multi-speaker overlap detection, cross-talk separation, candidate hypotheses generation,
and confidence score recalibration.
"""

from typing import Any, Dict, List, Literal, Optional
import math
import uuid
from pydantic import Field

from app.schemas.base import CoreBaseModel


class OverlappingSegment(CoreBaseModel):
    """Interval with overlapping concurrent speech from multiple speakers."""
    segment_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    start_time: float = Field(..., ge=0.0)
    end_time: float = Field(..., ge=0.0)
    primary_speaker: str = Field(..., description="Dominant speaker ID")
    secondary_speaker: str = Field(..., description="Overlapping secondary speaker ID")
    overlap_ratio: float = Field(default=0.3, ge=0.0, le=1.0)


class OverlapCandidateHypothesis(CoreBaseModel):
    """Disambiguated candidate transcript hypothesis for a speaker during overlap."""
    candidate_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    speaker_id: str = Field(...)
    transcript: str = Field(...)
    confidence: float = Field(default=0.85, ge=0.0, le=1.0)


class OverlapResolutionResult(CoreBaseModel):
    """Output model for overlap resolution processing."""
    meeting_id: uuid.UUID
    overlapping_segments: List[OverlappingSegment] = Field(default_factory=list)
    resolved_candidates: List[OverlapCandidateHypothesis] = Field(default_factory=list)
    adjusted_confidence: Optional[float] = Field(default=0.88, ge=0.0, le=1.0)
    resolution_status: Literal["NOT_REQUIRED", "UNRESOLVED", "NOT_VERIFIED"] = "NOT_VERIFIED"
    separation_verified: bool = False
    warnings: List[str] = Field(default_factory=list)


class OverlapResolutionEngine:
    """
    Overlap Resolution Engine for separating and decoding concurrent speech streams.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        self.config = config or {
            "separation_threshold": 0.25,
            "max_concurrent_speakers": 3,
        }

    async def resolve_overlaps(
        self,
        audio_payload: Optional[bytes] = None,
        meeting_id: Optional[uuid.UUID] = None,
        diarization_turns: Optional[List[Any]] = None,
        diarization_result: Optional[Any] = None,
        asr_result: Optional[Any] = None,
        correlation_id: Optional[str] = None,
    ) -> OverlapResolutionResult:
        """
        Detects concurrent speech regions and generates separated candidate hypotheses.
        """
        m_id = meeting_id or getattr(diarization_result, "meeting_id", None) or getattr(asr_result, "meeting_id", None) or uuid.uuid4()
        from app.core.config import get_settings
        if get_settings().EXECUTION_MODE.upper() == "REAL":
            turns = diarization_turns if diarization_turns is not None else getattr(diarization_result, "speaker_turns", None)
            if not turns:
                raise ValueError("REAL overlap detection requires actual diarization turns")
            def value(turn, key):
                return turn[key] if isinstance(turn, dict) else getattr(turn, key)
            for turn in turns:
                start, end = value(turn, "start_time"), value(turn, "end_time")
                if not (math.isfinite(start) and math.isfinite(end) and 0 <= start < end
                        and value(turn, "speaker_id")):
                    raise ValueError("REAL overlap detection received invalid diarization turns")
            overlaps = []
            for i, first in enumerate(turns):
                for second in turns[i + 1:]:
                    if value(first, "speaker_id") == value(second, "speaker_id"):
                        continue
                    start = max(value(first, "start_time"), value(second, "start_time"))
                    end = min(value(first, "end_time"), value(second, "end_time"))
                    if end > start:
                        duration = min(value(first, "end_time") - value(first, "start_time"),
                                       value(second, "end_time") - value(second, "start_time"))
                        overlaps.append(OverlappingSegment(start_time=start, end_time=end,
                            primary_speaker=value(first, "speaker_id"), secondary_speaker=value(second, "speaker_id"),
                            overlap_ratio=(end - start) / duration))
            # SDD 12.6.15 permits publishing unresolved overlap. Retain observed
            # intervals; never invent separated audio, hypotheses or confidence.
            return OverlapResolutionResult(meeting_id=m_id, overlapping_segments=overlaps,
                resolved_candidates=[], adjusted_confidence=None,
                resolution_status="UNRESOLVED" if overlaps else "NOT_REQUIRED",
                separation_verified=False,
                warnings=["Overlapping speech remains unresolved: no separation provider is configured. "
                          "The original ASR transcript is preserved; overlapping words and speaker "
                          "attribution require review."] if overlaps else [])

        overlaps = [
            OverlappingSegment(
                start_time=3.2,
                end_time=3.6,
                primary_speaker="speaker_0",
                secondary_speaker="speaker_1",
                overlap_ratio=0.25,
            )
        ]

        candidates = [
            OverlapCandidateHypothesis(
                speaker_id="speaker_0",
                transcript="karenge",
                confidence=0.88,
            ),
            OverlapCandidateHypothesis(
                speaker_id="speaker_1",
                transcript="Yes agree",
                confidence=0.82,
            ),
        ]

        return OverlapResolutionResult(
            meeting_id=m_id,
            overlapping_segments=overlaps,
            resolved_candidates=candidates,
            adjusted_confidence=0.86,
        )
