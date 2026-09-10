"""
Transcript Intelligence Engine
Provides transcript cleaning, normalization, segment fusion, speaker identity preservation,
conversational turn identification, artifact removal, and provenance tracing.
"""

from datetime import datetime
import re
from typing import Any, Dict, List, Optional
import uuid
from pydantic import Field

from app.schemas.base import CoreBaseModel
from app.ai.multilingual_asr import ASRResult, ASRSegment, ASRWordTimestamp
from app.ai.code_switch_intelligence import NormalizedRepresentation, CodeSwitchBoundary


class CleanedTranscriptSegment(CoreBaseModel):
    """Cleaned and normalized transcript segment with preserved provenance."""
    segment_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    source_segment_ids: List[uuid.UUID] = Field(default_factory=list, description="IDs of source ASR segments")
    speaker_id: Optional[str] = Field(default=None)
    start_time: float = Field(..., ge=0.0)
    end_time: float = Field(..., ge=0.0)
    raw_transcript: str = Field(..., description="Unmodified original text")
    cleaned_transcript: str = Field(..., description="Normalized text with artifacts removed")
    detected_language: str = Field(default="en")
    code_switch_boundaries: List[CodeSwitchBoundary] = Field(default_factory=list)
    words: List[ASRWordTimestamp] = Field(default_factory=list)
    confidence: float = Field(default=0.90, ge=0.0, le=1.0)
    removed_artifacts: List[str] = Field(default_factory=list, description="Removed filler or stutter tokens")


class ConversationalTurn(CoreBaseModel):
    """Higher-level conversational turn grouped by speaker and continuous timing."""
    turn_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    speaker_id: str = Field(...)
    start_time: float = Field(..., ge=0.0)
    end_time: float = Field(..., ge=0.0)
    text: str = Field(...)
    detected_language: str = Field(default="en")
    segment_ids: List[uuid.UUID] = Field(default_factory=list)
    turn_confidence: float = Field(default=0.90, ge=0.0, le=1.0)


class TranscriptUnit(CoreBaseModel):
    """Meaningful semantic unit (e.g. sentence/utterance) derived from conversational turns."""
    unit_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    turn_id: uuid.UUID = Field(...)
    speaker_id: str = Field(...)
    start_time: float = Field(..., ge=0.0)
    end_time: float = Field(..., ge=0.0)
    sentence: str = Field(...)
    detected_language: str = Field(default="en")
    confidence: float = Field(default=0.90, ge=0.0, le=1.0)


class TranscriptIntelligenceResult(CoreBaseModel):
    """Output payload from Transcript Intelligence processing."""
    meeting_id: uuid.UUID
    cleaned_full_transcript: str
    cleaned_segments: List[CleanedTranscriptSegment] = Field(default_factory=list)
    conversational_turns: List[ConversationalTurn] = Field(default_factory=list)
    transcript_units: List[TranscriptUnit] = Field(default_factory=list)
    overall_confidence: float = Field(default=0.90, ge=0.0, le=1.0)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class TranscriptIntelligenceEngine:
    """
    Transcript Intelligence Engine for artifact cleaning, segment fusion,
    turn segmentation, and provenance preservation.
    """

    FILLER_WORDS = {"uh", "um", "er", "ah", "like", "you know"}

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        self.config = config or {
            "max_merge_gap_seconds": 1.5,
            "remove_fillers": True,
            "deduplicate_stutters": True,
        }

    def clean_text(self, text: str) -> tuple[str, List[str]]:
        """
        Cleans transcript text by removing obvious stutters and isolated filler noise tokens
        without altering factual meaning. Returns (cleaned_text, removed_artifacts).
        """
        if not text:
            return "", []

        removed = []
        tokens = text.split()
        cleaned_tokens = []

        i = 0
        while i < len(tokens):
            token = tokens[i]
            lower_token = re.sub(r"[^\w]", "", token.lower())

            # Check stutter repetition (e.g. "we we discuss")
            if i < len(tokens) - 1:
                next_lower = re.sub(r"[^\w]", "", tokens[i + 1].lower())
                if lower_token and lower_token == next_lower:
                    removed.append(f"stutter:{token}")
                    i += 1  # Skip repeated token
                    continue

            # Check isolated filler words if enabled
            if self.config.get("remove_fillers", True) and lower_token in self.FILLER_WORDS:
                removed.append(f"filler:{token}")
                i += 1
                continue

            cleaned_tokens.append(token)
            i += 1

        cleaned_text = " ".join(cleaned_tokens)
        return cleaned_text if cleaned_text else text, removed

    async def process_transcript(
        self,
        asr_result: ASRResult,
        code_switch_norm: Optional[NormalizedRepresentation] = None,
        diarization_result: Optional[Any] = None,
        overlap_result: Optional[Any] = None,
        correlation_id: Optional[str] = None,
    ) -> TranscriptIntelligenceResult:
        """
        Processes ASRResult into cleaned segments, conversational turns, and transcript units.
        """
        if not asr_result or not asr_result.segments:
            return TranscriptIntelligenceResult(
                meeting_id=asr_result.meeting_id if asr_result else uuid.uuid4(),
                cleaned_full_transcript="",
                cleaned_segments=[],
                conversational_turns=[],
                transcript_units=[],
                overall_confidence=1.0 if (asr_result and not asr_result.segments) else 0.0,
                metadata={"correlation_id": correlation_id, "empty_input": True},
            )

        cleaned_segments: List[CleanedTranscriptSegment] = []
        confidences: List[float] = []

        for seg in asr_result.segments:
            cleaned_txt, artifacts = self.clean_text(seg.transcript)
            boundaries = code_switch_norm.code_switch_boundaries if code_switch_norm else []

            cleaned_seg = CleanedTranscriptSegment(
                source_segment_ids=[seg.segment_id],
                speaker_id=seg.speaker_id or "speaker_unknown",
                start_time=seg.start_time,
                end_time=seg.end_time,
                raw_transcript=seg.transcript,
                cleaned_transcript=cleaned_txt,
                detected_language=seg.detected_language,
                code_switch_boundaries=boundaries,
                words=seg.words,
                confidence=seg.confidence,
                removed_artifacts=artifacts,
            )
            cleaned_segments.append(cleaned_seg)
            confidences.append(seg.confidence)

        # Fuse compatible adjacent segments belonging to same speaker within merge threshold
        turns = self._build_conversational_turns(cleaned_segments)

        # Extract semantic transcript units
        units = self._extract_transcript_units(turns)

        full_cleaned = " ".join([t.text for t in turns])
        overall_conf = (sum(confidences) / len(confidences)) if confidences else 0.90

        return TranscriptIntelligenceResult(
            meeting_id=asr_result.meeting_id,
            cleaned_full_transcript=full_cleaned,
            cleaned_segments=cleaned_segments,
            conversational_turns=turns,
            transcript_units=units,
            overall_confidence=overall_conf,
            metadata={
                "correlation_id": correlation_id,
                "model_name": asr_result.metadata.get("model_name", "openai/whisper-large-v3"),
                "model_version": asr_result.metadata.get("model_version", "v3-turbo"),
                "provenance": f"TranscriptIntelligence:{asr_result.metadata.get('provenance', 'ASR')}",
            },
        )

    def _build_conversational_turns(
        self,
        segments: List[CleanedTranscriptSegment],
    ) -> List[ConversationalTurn]:
        if not segments:
            return []

        turns: List[ConversationalTurn] = []
        max_gap = self.config.get("max_merge_gap_seconds", 1.5)

        curr_spk = segments[0].speaker_id or "speaker_unknown"
        curr_start = segments[0].start_time
        curr_end = segments[0].end_time
        curr_lang = segments[0].detected_language
        curr_texts = [segments[0].cleaned_transcript]
        curr_seg_ids = list(segments[0].source_segment_ids)
        curr_confs = [segments[0].confidence]

        for seg in segments[1:]:
            spk = seg.speaker_id or "speaker_unknown"
            gap = seg.start_time - curr_end

            if spk == curr_spk and gap <= max_gap:
                curr_end = max(curr_end, seg.end_time)
                curr_texts.append(seg.cleaned_transcript)
                curr_seg_ids.extend(seg.source_segment_ids)
                curr_confs.append(seg.confidence)
            else:
                avg_conf = sum(curr_confs) / len(curr_confs)
                turns.append(
                    ConversationalTurn(
                        speaker_id=curr_spk,
                        start_time=curr_start,
                        end_time=curr_end,
                        text=" ".join(curr_texts),
                        detected_language=curr_lang,
                        segment_ids=curr_seg_ids,
                        turn_confidence=avg_conf,
                    )
                )
                curr_spk = spk
                curr_start = seg.start_time
                curr_end = seg.end_time
                curr_lang = seg.detected_language
                curr_texts = [seg.cleaned_transcript]
                curr_seg_ids = list(seg.source_segment_ids)
                curr_confs = [seg.confidence]

        if curr_texts:
            turns.append(
                ConversationalTurn(
                    speaker_id=curr_spk,
                    start_time=curr_start,
                    end_time=curr_end,
                    text=" ".join(curr_texts),
                    detected_language=curr_lang,
                    segment_ids=curr_seg_ids,
                    turn_confidence=sum(curr_confs) / len(curr_confs),
                )
            )

        return turns

    def _extract_transcript_units(
        self,
        turns: List[ConversationalTurn],
    ) -> List[TranscriptUnit]:
        units: List[TranscriptUnit] = []
        for turn in turns:
            sentences = [s.strip() for s in turn.text.split(".") if s.strip()]
            if not sentences:
                sentences = [turn.text]

            num_s = len(sentences)
            dur = max(0.1, turn.end_time - turn.start_time)
            s_dur = dur / num_s

            for idx, sentence in enumerate(sentences):
                st = turn.start_time + (idx * s_dur)
                et = turn.start_time + ((idx + 1) * s_dur)
                units.append(
                    TranscriptUnit(
                        turn_id=turn.turn_id,
                        speaker_id=turn.speaker_id,
                        start_time=st,
                        end_time=et,
                        sentence=sentence,
                        detected_language=turn.detected_language,
                        confidence=turn.turn_confidence,
                    )
                )

        return units
