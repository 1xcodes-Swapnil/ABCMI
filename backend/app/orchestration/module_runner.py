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
                try:
                    from pathlib import Path
                    import os
                    base_path = Path(settings.AUDIO_STORAGE_PATH).resolve()
                    raw_dir = base_path / "raw"
                    audio_payload = None
                    if raw_dir.exists():
                        prefix = f"{meeting_id}_"
                        for file in os.listdir(raw_dir):
                            if file.startswith(prefix):
                                audio_payload = (raw_dir / file).read_bytes()
                                break
                    
                    if not audio_payload:
                        if "audio_payload" in input_data:
                            audio_payload = input_data["audio_payload"]
                        elif "audio_bytes" in input_data:
                            audio_payload = input_data["audio_bytes"]

                    if cap == "audio_intelligence":
                        if not audio_payload:
                            raise FileNotFoundError(f"No audio file found for meeting {meeting_id} on disk.")
                        from app.ai.multilingual_asr import validate_audio
                        import tempfile
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
                            if os.path.exists(tmp_path):
                                os.remove(tmp_path)

                    elif cap == "multilingual_asr":
                        if not audio_payload:
                            raise FileNotFoundError(f"No audio file found for meeting {meeting_id} on disk.")
                        from app.ai.multilingual_asr import MultilingualASREngine
                        engine = MultilingualASREngine()
                        asr_res = await engine.transcribe_audio(
                            audio_payload=audio_payload,
                            meeting_id=uuid.UUID(meeting_id) if isinstance(meeting_id, str) else meeting_id,
                            target_languages=input_data.get("target_languages"),
                            correlation_id=correlation_id,
                            use_fixture=False
                        )
                        return {
                            "status": "SUCCESS",
                            "capability": cap,
                            "confidence_score": asr_res.overall_confidence,
                            "result_data": {
                                "transcript": asr_res.full_transcript,
                                "language": asr_res.detected_languages[0] if asr_res.detected_languages else "en",
                                "segments": [s.model_dump() for s in asr_res.segments],
                                "detected_languages": asr_res.detected_languages,
                                "language_distribution": asr_res.language_distribution,
                            },
                            "correlation_id": correlation_id,
                        }

                    elif cap == "speaker_representation":
                        if not audio_payload:
                            raise FileNotFoundError(f"No audio file found for meeting {meeting_id} on disk.")
                        from app.ai.speaker_diarization import SpeakerDiarizationEngine
                        engine = SpeakerDiarizationEngine()
                        sd_res = await engine.diarize_audio(
                            audio_payload=audio_payload,
                            meeting_id=uuid.UUID(meeting_id) if isinstance(meeting_id, str) else meeting_id,
                            expected_speakers=input_data.get("expected_speakers"),
                            correlation_id=correlation_id
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
