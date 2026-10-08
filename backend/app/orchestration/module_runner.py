"""
ACE AI Processing Module Runner & Capability Registry (Phase 4.11B)
Provides module dispatching across the 13 required AI processing capabilities.
Includes configurable mock/simulated runners for testing confidence evaluation,
verification flows, retry logic, and recovery mechanisms. Supports REAL execution mode.
"""

from typing import Any, Callable, Coroutine, Dict, Optional
import uuid

from app.core.logging import get_logger
from app.core.config import get_settings

logger = get_logger("orchestration.module_runner")

ModuleHandler = Callable[[Dict[str, Any]], Coroutine[Any, Any, Dict[str, Any]]]


class AIModuleRunner:
    """
    Capability execution runner and registry for AI processing modules.
    Provides async dispatching to modules, handling parameters, correlation, and response format.
    Supports both REAL production mode and mock/fixture simulation modes.
    """

    SUPPORTED_CAPABILITIES = [
        "audio_intelligence",
        "multilingual_asr",
        "overlap_resolution",
        "speaker_representation",
        "code_switch_intelligence",
        "timestamp_intelligence",
        "transcript_intelligence",
        "confidence_fusion",
        "context_intelligence",
        "verification_engine",
        "meeting_understanding",
        "meeting_analytics",
        "knowledge_memory",
    ]

    def __init__(self) -> None:
        self._handlers: Dict[str, ModuleHandler] = {}
        self._injected_confidences: Dict[uuid.UUID, float] = {}
        self._injected_errors: Dict[uuid.UUID, str] = {}
        self._register_default_simulators()

    def register_capability_handler(self, capability: str, handler: ModuleHandler) -> None:
        """Register a custom module execution handler for a capability."""
        if capability not in self.SUPPORTED_CAPABILITIES:
            logger.warning(f"Registering non-standard capability identifier '{capability}'")
        self._handlers[capability] = handler

    def inject_task_confidence(self, task_id: uuid.UUID, confidence_score: float) -> None:
        """Inject a specific confidence score output for a task (used in testing)."""
        self._injected_confidences[task_id] = confidence_score

    def inject_task_error(self, task_id: uuid.UUID, error_message: str) -> None:
        """Inject a failure for a specific task (used in testing retry/recovery)."""
        self._injected_errors[task_id] = error_message

    async def execute_task(
        self,
        capability: str,
        task_id: uuid.UUID,
        meeting_id: uuid.UUID,
        request_id: uuid.UUID,
        input_data: Dict[str, Any],
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Dispatch task execution to the module handler for the given capability.
        Returns execution result dict containing status, confidence, and output payload.
        """
        # Check injected error test override
        if task_id in self._injected_errors:
            err_msg = self._injected_errors.pop(task_id)
            logger.info(f"Executing injected task error for task {task_id}: {err_msg}")
            raise RuntimeError(err_msg)

        handler = self._handlers.get(capability)
        if not handler:
            raise ValueError(f"No execution handler registered for capability '{capability}'")

        payload = {
            "task_id": str(task_id),
            "meeting_id": str(meeting_id),
            "request_id": str(request_id),
            "capability": capability,
            "correlation_id": correlation_id,
            "input": input_data,
        }

        try:
            result = await handler(payload)
            # Apply confidence override if injected
            if task_id in self._injected_confidences:
                result["confidence_score"] = self._injected_confidences.pop(task_id)
            return result
        except Exception as ex:
            logger.error(f"Error during module execution for capability '{capability}': {ex}")
            raise

    def _register_default_simulators(self) -> None:
        """Register realistic default simulators for all 13 core capabilities."""
        for cap in self.SUPPORTED_CAPABILITIES:
            self._handlers[cap] = self._make_simulated_handler(cap)

    def _make_simulated_handler(self, capability: str) -> ModuleHandler:
        """Create a default simulation or real handler depending on execution mode."""

        async def _simulated_handler(payload: Dict[str, Any]) -> Dict[str, Any]:
            cap = payload.get("capability", capability)
            meeting_id = payload.get("meeting_id")
            correlation_id = payload.get("correlation_id")
            input_data = payload.get("input") or {}

            logger.debug(f"AI module '{cap}' executing for meeting {meeting_id}")

            settings = get_settings()
            exec_mode = getattr(settings, "EXECUTION_MODE", "FIXTURE").upper()

            # Handle REAL production execution flow for core acoustic modules
            if exec_mode == "REAL":
                if cap == "knowledge_memory":
                    upstream = input_data.get("upstream_results", {})
                    objects = upstream.get("meeting_understanding", {}).get("knowledge_objects", [])
                    if not objects or any(not obj.get("content") for obj in objects):
                        raise ValueError("REAL knowledge memory requires grounded non-empty knowledge objects")
                    return {"status": "SUCCESS", "capability": cap, "confidence_score": None,
                            "result_data": {"knowledge_objects": objects, "persistence_status": "PENDING",
                                            "canonical_stored": False}, "correlation_id": correlation_id}
                if cap == "meeting_analytics":
                    from app.ai.meeting_analytics import MeetingAnalyticsEngine
                    upstream = input_data.get("upstream_results", {})
                    result = MeetingAnalyticsEngine().compute_analytics(uuid.UUID(str(meeting_id)),
                        speaker_turns=upstream.get("speaker_representation", {}).get("speaker_turns"),
                        meeting_duration_seconds=upstream.get("audio_intelligence", {}).get("duration_seconds", 0),
                        confidence_scores=[], knowledge_objects=upstream.get("meeting_understanding", {}).get("knowledge_objects", []),
                        correlation_id=correlation_id)
                    return {"status": "SUCCESS", "capability": cap, "confidence_score": None,
                            "result_data": result.model_dump(mode="json"), "correlation_id": correlation_id}
                if cap == "meeting_understanding":
                    from app.ai.meeting_understanding import MeetingUnderstandingEngine
                    upstream = input_data.get("upstream_results", {})
                    transcript = upstream.get("multilingual_asr", {}).get("transcript")
                    if not transcript:
                        raise ValueError("REAL meeting understanding requires the actual transcript")
                    context = upstream.get("context_intelligence", {}).get("metadata", {})
                    context = {**context, "turns": [{"segment_id": str(s["segment_id"]),
                        "text": s["transcript"], "start_ms": s["start_time"] * 1000,
                        "end_ms": s["end_time"] * 1000, "speaker": s.get("speaker_id")}
                        for s in upstream.get("multilingual_asr", {}).get("segments", [])]}
                    result = await MeetingUnderstandingEngine().analyze_meeting(uuid.UUID(str(meeting_id)),
                        transcript, context_data=context, correlation_id=correlation_id, use_fixture=False)
                    return {"status": "SUCCESS", "capability": cap, "confidence_score": result.overall_confidence,
                            "result_data": result.model_dump(mode="json"), "correlation_id": correlation_id}
                if cap == "verification_engine":
                    from app.ai.verification_engine import VerificationEngine
                    upstream = input_data.get("upstream_results", {})
                    transcript = upstream.get("multilingual_asr", {}).get("transcript")
                    if not transcript:
                        raise ValueError("REAL verification requires actual transcript data")
                    _, result = VerificationEngine().evaluate_output(uuid.UUID(str(meeting_id)),
                        "transcript_insight", transcript,
                        upstream.get("confidence_fusion", {}).get("fused_confidence"),
                        correlation_id=correlation_id, payload={"execution_mode": "REAL"})
                    return {"status": "SUCCESS", "capability": cap, "confidence_score": result.confidence_score,
                            "result_data": result.model_dump(mode="json"), "correlation_id": correlation_id}
                if cap == "context_intelligence":
                    from app.ai.context_intelligence import ContextIntelligenceEngine
                    from app.ai.transcript_intelligence import TranscriptIntelligenceResult
                    transcript = TranscriptIntelligenceResult.model_validate(
                        input_data.get("upstream_results", {}).get("transcript_intelligence", {}))
                    result = await ContextIntelligenceEngine().extract_context(transcript,
                        meeting_id=uuid.UUID(str(meeting_id)), correlation_id=correlation_id)
                    return {"status": "SUCCESS", "capability": cap, "confidence_score": result.overall_confidence,
                            "result_data": result.model_dump(mode="json"), "correlation_id": correlation_id}
                if cap == "confidence_fusion":
                    from app.ai.confidence_fusion import ConfidenceFusionEngine
                    upstream = input_data.get("upstream_results", {})
                    measured_asr = [s["confidence"] for s in upstream.get("multilingual_asr", {}).get("segments", [])
                                    if s.get("confidence") is not None]
                    result = ConfidenceFusionEngine().fuse_signals(uuid.UUID(str(meeting_id)), {
                        "asr_confidence": sum(measured_asr)/len(measured_asr) if measured_asr else None,
                        "diarization_confidence": upstream.get("speaker_representation", {}).get("diarization_confidence"),
                    }, correlation_id=correlation_id)
                    return {"status": "SUCCESS", "capability": cap, "confidence_score": result.fused_confidence,
                            "result_data": result.model_dump(mode="json"), "correlation_id": correlation_id}
                if cap == "transcript_intelligence":
                    from app.ai.multilingual_asr import ASRResult, ASRSegment
                    from app.ai.transcript_intelligence import TranscriptIntelligenceEngine
                    upstream = input_data.get("upstream_results", {})
                    asr = upstream.get("multilingual_asr", {})
                    segments = [ASRSegment.model_validate(s) for s in asr.get("segments", [])]
                    if not segments:
                        raise ValueError("REAL transcript intelligence requires actual ASR segments")
                    asr_result = ASRResult(meeting_id=uuid.UUID(str(meeting_id)),
                        full_transcript=asr["transcript"], segments=segments, overall_confidence=None,
                        metadata={**asr.get("metadata", {}), "model_name": settings.OPENMOSS_MODEL_ID,
                                  "provenance": "REAL MOSS"})
                    result = await TranscriptIntelligenceEngine().process_transcript(asr_result, correlation_id=correlation_id)
                    if not result.cleaned_segments:
                        raise ValueError("REAL transcript intelligence produced no segments")
                    return {"status": "SUCCESS", "capability": cap, "confidence_score": result.overall_confidence,
                            "result_data": result.model_dump(mode="json"), "correlation_id": correlation_id}
                if cap == "timestamp_intelligence":
                    import math
                    upstream = input_data.get("upstream_results", {})
                    segments = upstream.get("multilingual_asr", {}).get("segments", [])
                    duration = upstream.get("audio_intelligence", {}).get("duration_seconds")
                    if not segments or duration is None:
                        raise ValueError("REAL timestamp validation requires ASR segments and audio duration")
                    previous_start = -1.0
                    for segment in segments:
                        start, end = segment["start_time"], segment["end_time"]
                        if not (math.isfinite(start) and math.isfinite(end) and
                                0 <= start < end <= duration and start >= previous_start):
                            raise ValueError("REAL ASR timestamps are invalid or out of order")
                        previous_start = start
                    return {"status": "SUCCESS", "capability": cap, "confidence_score": None,
                            "result_data": {"segments": segments, "timestamps_valid": True,
                                            "validated_segment_count": len(segments)},
                            "correlation_id": correlation_id}
                if cap == "code_switch_intelligence":
                    from app.ai.code_switch_intelligence import CodeSwitchIntelligenceEngine
                    upstream = input_data.get("upstream_results", {})
                    transcript = upstream.get("multilingual_asr", {}).get("transcript")
                    if not transcript:
                        raise ValueError("REAL code-switch normalization requires the ASR transcript")
                    observed_segments = upstream.get("multilingual_asr", {}).get("segments", [])
                    if not observed_segments:
                        raise ValueError("REAL normalization requires actual ASR turns")
                    engine = CodeSwitchIntelligenceEngine()
                    normalized_turns = []
                    for segment in observed_segments:
                        original = segment.get("transcript", "")
                        if not original.strip():
                            continue
                        normalized_turns.append({"segment_id": segment.get("segment_id"),
                            "original_text": original, "canonical_text": await engine.map_to_canonical(original),
                            "inference": dict(getattr(engine, "last_inference", {}))})
                    if not normalized_turns:
                        raise ValueError("REAL normalization returned no actual turns")
                    canonical = " ".join(turn["canonical_text"] for turn in normalized_turns)
                    return {"status": "SUCCESS", "capability": cap, "confidence_score": None,
                            "result_data": {"original_text": transcript, "canonical_text": canonical,
                                            "normalized_turns": normalized_turns,
                                            "model": "sarvamai/sarvam-1", "language_detection": "NOT_VERIFIED"},
                            "correlation_id": correlation_id}
                if cap == "overlap_resolution":
                    from app.ai.overlap_resolution import OverlapResolutionEngine
                    upstream = input_data.get("upstream_results", {})
                    result = await OverlapResolutionEngine().resolve_overlaps(
                        meeting_id=uuid.UUID(str(meeting_id)),
                        diarization_turns=upstream.get("speaker_representation", {}).get("speaker_turns"))
                    return {"status": "SUCCESS", "capability": cap, "confidence_score": None,
                            "result_data": result.model_dump(mode="json"), "correlation_id": correlation_id}
                if cap not in {"audio_intelligence", "multilingual_asr", "speaker_representation"}:
                    raise RuntimeError(f"REAL handler is not implemented for capability '{cap}'.")
                try:
                    from pathlib import Path
                    import os
                    base_path = Path(settings.AUDIO_STORAGE_PATH).resolve()
                    raw_dir = base_path / "raw"
                    audio_payload = input_data.get("audio_payload") or input_data.get("audio_bytes")
                    audio_file_path = input_data.get("audio_file_path")
                    if audio_file_path:
                        source = Path(audio_file_path).resolve()
                        if not source.is_relative_to(base_path) or not source.is_file():
                            raise ValueError("Stored audio path is outside configured storage or unavailable")
                        audio_file_path = str(source)
                    if not audio_payload and not audio_file_path and raw_dir.exists():
                        prefix = f"{meeting_id}_"
                        for file in os.listdir(raw_dir):
                            if file.startswith(prefix):
                                audio_file_path = str(raw_dir / file)
                                break
                    
                    if not audio_payload:
                        if "audio_payload" in input_data:
                            audio_payload = input_data["audio_payload"]
                        elif "audio_bytes" in input_data:
                            audio_payload = input_data["audio_bytes"]

                    if cap == "audio_intelligence":
                        if not audio_payload and not audio_file_path:
                            raise FileNotFoundError(f"No audio file found for meeting {meeting_id} on disk.")
                        from app.ai.multilingual_asr import validate_audio
                        import tempfile
                        tmp_path = audio_file_path
                        if not tmp_path:
                            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                                tmp.write(audio_payload)
                                tmp_path = tmp.name
                        try:
                            meta = validate_audio(tmp_path)
                            return {
                                "status": "SUCCESS",
                                "capability": cap,
                                "confidence_score": 1.0,
                                "result_data": {
                                    "raw_audio_processed": True,
                                    "duration_seconds": meta["duration"],
                                    "sample_rate": meta["sample_rate"],
                                    "channels": meta["channels"]
                                },
                                "correlation_id": correlation_id,
                            }
                        finally:
                            if not audio_file_path and os.path.exists(tmp_path):
                                os.remove(tmp_path)

                    elif cap == "multilingual_asr":
                        if not audio_payload and not audio_file_path:
                            raise FileNotFoundError(f"No audio file found for meeting {meeting_id} on disk.")
                        from app.ai.multilingual_asr import MultilingualASREngine
                        engine = MultilingualASREngine()
                        asr_res = await engine.transcribe_audio(
                            audio_payload=audio_payload,
                            meeting_id=uuid.UUID(meeting_id) if isinstance(meeting_id, str) else meeting_id,
                            target_languages=input_data.get("target_languages"),
                            correlation_id=correlation_id,
                            use_fixture=False,
                            audio_file_path=audio_file_path,
                        )
                        return {
                            "status": "SUCCESS",
                            "capability": cap,
                            "confidence_score": asr_res.overall_confidence,
                            "result_data": {
                                "transcript": asr_res.full_transcript,
                                "language": asr_res.detected_languages[0] if asr_res.detected_languages else None,
                                "segments": [s.model_dump() for s in asr_res.segments],
                                "detected_languages": asr_res.detected_languages,
                                "language_distribution": asr_res.language_distribution,
                                "metadata": asr_res.metadata,
                            },
                            "correlation_id": correlation_id,
                        }

                    elif cap == "speaker_representation":
                        if not audio_payload and not audio_file_path:
                            raise FileNotFoundError(f"No audio file found for meeting {meeting_id} on disk.")
                        from app.ai.speaker_diarization import SpeakerDiarizationEngine
                        engine = SpeakerDiarizationEngine()
                        sd_res = await engine.diarize_audio(
                            audio_payload=audio_payload,
                            meeting_id=uuid.UUID(meeting_id) if isinstance(meeting_id, str) else meeting_id,
                            expected_speakers=input_data.get("expected_speakers"),
                            correlation_id=correlation_id,
                            audio_file_path=audio_file_path,
                        )
                        return {
                            "status": "SUCCESS",
                            "capability": cap,
                            "confidence_score": sd_res.overall_confidence,
                            "result_data": {
                                "speakers": list(set(t.speaker_id for t in sd_res.speaker_turns)),
                                "diarization_confidence": sd_res.overall_confidence,
                                "speaker_turns": [t.model_dump() for t in sd_res.speaker_turns],
                                "voiceprints": [v.model_dump() for v in sd_res.voiceprints],
                                "metadata": sd_res.metadata,
                            },
                            "correlation_id": correlation_id,
                        }

                except Exception as ex:
                    logger.error(f"REAL execution failed for capability '{cap}': {ex}")
                    raise RuntimeError(f"REAL mode execution failed for capability '{cap}': {ex}") from ex

            # Default fixture/mock simulation modes
            default_outputs: Dict[str, Any] = {
                "audio_intelligence": {"raw_audio_processed": True, "duration_seconds": 120.0, "sample_rate": 16000},
                "multilingual_asr": {"transcript": "Welcome to the ABCI-MI collaborative intelligence sync.", "language": "en"},
                "overlap_resolution": {"overlaps_detected": 1, "resolved_segments": 1},
                "speaker_representation": {"speakers": ["Speaker_1", "Speaker_2"], "diarization_confidence": 0.92},
                "code_switch_intelligence": {"code_switch_points": [], "primary_lang": "en", "secondary_lang": "es"},
                "timestamp_intelligence": {"aligned_tokens": 12, "time_precision_ms": 10},
                "transcript_intelligence": {"cleaned_transcript": "Welcome to the ABCI-MI collaborative intelligence sync.", "word_count": 8},
                "confidence_fusion": {"fused_confidence": 0.88, "signals": {"asr": 0.90, "diarization": 0.86}},
                "context_intelligence": {"context_matches": 3, "topic": "ABCI-MI ACE Architecture"},
                "verification_engine": {"verification_passed": True, "verification_notes": "Structural validation passed"},
                "meeting_understanding": {"key_decisions": ["Proceed with Phase 4.11B integration"], "summary": "Sync on ACE integration."},
                "meeting_analytics": {"speaker_talk_time": {"Speaker_1": 60, "Speaker_2": 60}},
                "knowledge_memory": {"canonical_stored": True, "object_type": "summary", "knowledge_id": str(uuid.uuid4())},
            }

            output = default_outputs.get(cap, {"processed": True})

            return {
                "status": "SUCCESS",
                "capability": cap,
                "confidence_score": 0.90,
                "result_data": output,
                "correlation_id": correlation_id,
            }

        return _simulated_handler
