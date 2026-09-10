"""
ABCI-MI Artificial Intelligence & Audio Engine Layer
Houses Multilingual ASR, Code-Switch Intelligence, Speaker Diarization, Overlap Resolution, and LLM Intelligence.
"""

from app.ai.multilingual_asr import (
    ASRSegment,
    ASRWordTimestamp,
    ASRResult,
    MultilingualASREngine,
)
from app.ai.code_switch_intelligence import (
    CodeSwitchBoundary,
    NormalizedRepresentation,
    CodeSwitchIntelligenceEngine,
)
from app.ai.speaker_diarization import (
    SpeakerVoiceprint,
    SpeakerTurn,
    DiarizationResult,
    SpeakerDiarizationEngine,
)
from app.ai.overlap_resolution import (
    OverlappingSegment,
    OverlapCandidateHypothesis,
    OverlapResolutionResult,
    OverlapResolutionEngine,
)
from app.ai.transcript_intelligence import (
    CleanedTranscriptSegment,
    ConversationalTurn,
    TranscriptUnit,
    TranscriptIntelligenceResult,
    TranscriptIntelligenceEngine,
)
from app.ai.context_intelligence import (
    SpeakerRelationship,
    ContextualDependency,
    ContextIntelligenceResult,
    ContextIntelligenceEngine,
)
from app.ai.confidence_fusion import (
    ConfidenceSignalBreakdown,
    ConfidenceFusionResult,
    ConfidenceFusionEngine,
)
from app.ai.verification_engine import (
    VerificationResult,
    VerificationEngine,
)
from app.ai.meeting_understanding import (
    ExtractedKnowledgeObject,
    MeetingUnderstandingResult,
    MeetingUnderstandingEngine,
)
from app.ai.meeting_analytics import (
    SpeakerParticipationStats,
    CodeSwitchStats,
    ConfidenceStats,
    KnowledgeObjectStats,
    MeetingAnalyticsResult,
    MeetingAnalyticsEngine,
)
from app.ai.knowledge_memory import (
    KnowledgeMemoryQueryRequest,
    KnowledgeMemoryQueryResult,
    KnowledgeMemoryEngine,
)
from app.ai.model_verification import (
    ModelVerificationService,
)
from app.ai.translation_engine import (
    TranslationProvider,
    MockTranslationProvider,
    TranslationProviderRegistry,
    translation_provider_registry,
    TranslationEngine,
)

__all__ = [
    "ASRSegment",
    "ASRWordTimestamp",
    "ASRResult",
    "MultilingualASREngine",
    "CodeSwitchBoundary",
    "NormalizedRepresentation",
    "CodeSwitchIntelligenceEngine",
    "SpeakerVoiceprint",
    "SpeakerTurn",
    "DiarizationResult",
    "SpeakerDiarizationEngine",
    "OverlappingSegment",
    "OverlapCandidateHypothesis",
    "OverlapResolutionResult",
    "OverlapResolutionEngine",
    "CleanedTranscriptSegment",
    "ConversationalTurn",
    "TranscriptUnit",
    "TranscriptIntelligenceResult",
    "TranscriptIntelligenceEngine",
    "SpeakerRelationship",
    "ContextualDependency",
    "ContextIntelligenceResult",
    "ContextIntelligenceEngine",
    "ConfidenceSignalBreakdown",
    "ConfidenceFusionResult",
    "ConfidenceFusionEngine",
    "VerificationResult",
    "VerificationEngine",
    "ExtractedKnowledgeObject",
    "MeetingUnderstandingResult",
    "MeetingUnderstandingEngine",
    "SpeakerParticipationStats",
    "CodeSwitchStats",
    "ConfidenceStats",
    "KnowledgeObjectStats",
    "MeetingAnalyticsResult",
    "MeetingAnalyticsEngine",
    "KnowledgeMemoryQueryRequest",
    "KnowledgeMemoryQueryResult",
    "KnowledgeMemoryEngine",
    "ModelVerificationService",
    "TranslationProvider",
    "MockTranslationProvider",
    "TranslationProviderRegistry",
    "translation_provider_registry",
    "TranslationEngine",
]
