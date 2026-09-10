"""
Provider-Neutral Answer Provider Interface & Implementations (Phase 4.23)
Enables grounded answer synthesis without direct database or vector access.
Provides Mock, Deterministic, and Registry components for replaceable LLM backends.
"""

from abc import ABC, abstractmethod
import re
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from app.schemas.query import QueryAnswerStatus


class QuerySynthesisResult(BaseModel):
    """Result of answer synthesis from retrieved authoritative context."""
    answer: str = Field(..., description="Synthesized grounded answer")
    status: QueryAnswerStatus = Field(..., description="Answer status classification")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="Overall answer confidence")
    is_low_confidence: bool = Field(default=False, description="Whether answer confidence is below threshold (< 0.75)")
    requires_verification: bool = Field(default=False, description="Whether human verification is recommended")
    used_knowledge_ids: List[str] = Field(default_factory=list, description="IDs of knowledge objects referenced")
    provenance: Dict[str, Any] = Field(default_factory=dict, description="Synthesis provenance metadata")


class QueryAnswerProvider(ABC):
    """Abstract interface for grounded answer providers."""

    @abstractmethod
    async def synthesize_answer(
        self,
        query: str,
        retrieved_objects: List[Dict[str, Any]],
        context_metadata: Dict[str, Any],
    ) -> QuerySynthesisResult:
        """
        Synthesizes a grounded answer from pre-retrieved authorized knowledge objects.
        The provider receives only the authorized context and NEVER directly queries
        PostgreSQL, Qdrant, or Redis.
        """
        pass

    async def answer(
        self,
        query: str,
        retrieved_objects: List[Dict[str, Any]],
        context_metadata: Dict[str, Any],
    ) -> QuerySynthesisResult:
        """Alias for synthesize_answer."""
        return await self.synthesize_answer(query, retrieved_objects, context_metadata)


class DeterministicQueryAnswerProvider(QueryAnswerProvider):
    """
    Deterministic answer provider that extracts, formats, and groups retrieved knowledge
    into a structured, verified answer without requiring external LLM API calls.
    Ensures zero hallucination and strict adherence to available evidence.
    Includes prompt-injection defenses (treats all transcript/knowledge content as data).
    """

    CONFIDENCE_THRESHOLD = 0.75

    def _sanitize_untrusted_text(self, text: str) -> str:
        """
        Neutralizes potential prompt injection markers and sensitive leak tokens.
        Treats all retrieved text strictly as raw user data.
        """
        if not text:
            return ""
        # Neutralize common prompt injection patterns
        sanitized = re.sub(
            r"(?i)(ignore\s+previous\s+instructions|system\s+prompt|reveal\s+credentials|system\s+override)",
            r"[REDACTED_INJECTION_ATTEMPT: \1]",
            text,
        )
        return sanitized.strip()

    def _detect_query_intent(self, query: str) -> str:
        """Identify key intent based on question keywords."""
        q = query.lower()
        if any(k in q for k in ["action item", "action-item", "task", "assignee", "assigned", "todo", "to-do", "incomplete", "due"]):
            return "action_items"
        if any(k in q for k in ["decision", "decided", "agreed", "consensus", "choice", "concluded"]):
            return "decisions"
        if any(k in q for k in ["topic", "discussed", "theme", "agenda", "subject"]):
            return "topics"
        if any(k in q for k in ["summary", "summarize", "recap", "overview", "takeaway", "highlights"]):
            return "summary"
        if any(k in q for k in ["insight", "sentiment", "sentiment analysis", "risk", "alignment"]):
            return "insights"
        if any(k in q for k in ["fact", "metric", "measurement", "data point"]):
            return "facts"
        if any(k in q for k in ["hypothesis", "hypotheses", "assumption", "guess"]):
            return "hypotheses"
        return "general"

    async def synthesize_answer(
        self,
        query: str,
        retrieved_objects: List[Dict[str, Any]],
        context_metadata: Dict[str, Any],
    ) -> QuerySynthesisResult:
        """Synthesizes structured answer from retrieved knowledge."""
        if not retrieved_objects:
            return QuerySynthesisResult(
                answer="I could not find sufficient authoritative context in the accessible meetings or projects to answer your question.",
                status=QueryAnswerStatus.INSUFFICIENT_CONTEXT,
                confidence=0.0,
                is_low_confidence=True,
                requires_verification=True,
                used_knowledge_ids=[],
                provenance={
                    "provider": "DeterministicQueryAnswerProvider",
                    "retrieved_count": 0,
                    "reason": "no_matching_evidence",
                },
            )

        intent = self._detect_query_intent(query)
        used_ids = [str(obj.get("knowledge_id")) for obj in retrieved_objects if obj.get("knowledge_id")]

        # Calculate confidence
        confidences = [obj.get("confidence_score") or obj.get("confidence") or 0.8 for obj in retrieved_objects]
        avg_confidence = round(sum(confidences) / len(confidences), 3) if confidences else 0.8
        is_low = avg_confidence < self.CONFIDENCE_THRESHOLD

        # Check if any object explicitly requires verification
        any_req_verif = any(
            obj.get("payload", {}).get("requires_verification", False)
            or obj.get("is_low_confidence", False)
            for obj in retrieved_objects
        ) or is_low

        lines: List[str] = []
        scope_desc = context_metadata.get("scope_description", "authorized workspace context")

        # Group by object_type
        by_type: Dict[str, List[Dict[str, Any]]] = {}
        for obj in retrieved_objects:
            otype = str(obj.get("object_type", "knowledge")).lower()
            by_type.setdefault(otype, []).append(obj)

        if intent == "action_items" and "action_item" in by_type:
            items = by_type["action_item"]
            lines.append(f"Found **{len(items)}** relevant action item(s) across {scope_desc}:")
            for item in items:
                title = self._sanitize_untrusted_text(item.get("title") or item.get("content") or "Untitled action item")
                payload = item.get("payload") or {}
                status_str = str(payload.get("status", "open")).upper()
                assignee = payload.get("assignee") or "Unassigned"
                priority = payload.get("priority", "normal")
                due = f", Due: {payload.get('due_date')}" if payload.get("due_date") else ""
                lines.append(f"- **[{status_str}]** {title} (Assignee: {assignee}, Priority: {priority}{due})")

        elif intent == "decisions" and "decision" in by_type:
            decs = by_type["decision"]
            lines.append(f"Recorded **{len(decs)}** relevant decision(s) across {scope_desc}:")
            for dec in decs:
                title = self._sanitize_untrusted_text(dec.get("title") or "Decision")
                content = self._sanitize_untrusted_text(dec.get("content") or "")
                payload = dec.get("payload") or {}
                impact = f" Impact: {payload.get('impact')}." if payload.get("impact") else ""
                lines.append(f"- **{title}**: {content}{impact}")

        elif intent == "topics" and "topic" in by_type:
            topics = by_type["topic"]
            lines.append(f"Identified **{len(topics)}** discussion topic(s) across {scope_desc}:")
            for top in topics:
                title = self._sanitize_untrusted_text(top.get("title") or "Discussion Topic")
                content = self._sanitize_untrusted_text(top.get("content") or "")
                payload = top.get("payload") or {}
                kw = f" (Keywords: {', '.join(payload.get('keywords', []))})" if payload.get("keywords") else ""
                lines.append(f"- **{title}**: {content}{kw}")

        elif intent == "summary" and "summary" in by_type:
            summaries = by_type["summary"]
            lines.append(f"Executive summary context across {scope_desc}:")
            for sum_obj in summaries:
                title = self._sanitize_untrusted_text(sum_obj.get("title") or "Meeting Summary")
                content = self._sanitize_untrusted_text(sum_obj.get("content") or "")
                lines.append(f"### {title}\n{content}")

        elif intent == "insights" and "transcript_insight" in by_type:
            insights = by_type["transcript_insight"]
            lines.append(f"Found **{len(insights)}** key insight(s) across {scope_desc}:")
            for ins in insights:
                title = self._sanitize_untrusted_text(ins.get("title") or "Insight")
                content = self._sanitize_untrusted_text(ins.get("content") or "")
                payload = ins.get("payload") or {}
                sent = f" [Sentiment: {payload.get('sentiment')}]" if payload.get("sentiment") else ""
                lines.append(f"- **{title}**{sent}: {content}")

        else:
            # Multi-type / General answer synthesis
            lines.append(f"Based on {len(retrieved_objects)} authoritative record(s) across {scope_desc}:")
            for otype, items in by_type.items():
                label = otype.replace("_", " ").title()
                lines.append(f"\n**{label} ({len(items)})**:")
                for item in items[:5]:
                    title = self._sanitize_untrusted_text(item.get("title") or item.get("content", "")[:80])
                    content = self._sanitize_untrusted_text(item.get("content") or "")
                    m_title = item.get("meeting_title")
                    m_ref = f" *(from '{m_title}')*" if m_title else ""
                    lines.append(f"- **{title}**{m_ref}: {content}")

        answer_text = "\n".join(lines).strip()
        answer_status = QueryAnswerStatus.REQUIRES_VERIFICATION if any_req_verif else QueryAnswerStatus.ANSWERED

        return QuerySynthesisResult(
            answer=answer_text,
            status=answer_status,
            confidence=avg_confidence,
            is_low_confidence=is_low,
            requires_verification=any_req_verif,
            used_knowledge_ids=used_ids,
            provenance={
                "provider": "DeterministicQueryAnswerProvider",
                "detected_intent": intent,
                "total_considered": len(retrieved_objects),
                "knowledge_types_used": list(by_type.keys()),
            },
        )


class MockQueryAnswerProvider(QueryAnswerProvider):
    """
    Configurable mock answer provider for deterministic testing.
    Can be configured to return specific answers, trigger confidence levels,
    simulate errors, or test verification flags.
    """

    def __init__(
        self,
        custom_answer: Optional[str] = None,
        custom_status: Optional[QueryAnswerStatus] = None,
        custom_confidence: Optional[float] = None,
        force_verification: bool = False,
        should_fail: bool = False,
    ) -> None:
        self.custom_answer = custom_answer
        self.custom_status = custom_status
        self.custom_confidence = custom_confidence
        self.force_verification = force_verification
        self.should_fail = should_fail

    async def synthesize_answer(
        self,
        query: str,
        retrieved_objects: List[Dict[str, Any]],
        context_metadata: Dict[str, Any],
    ) -> QuerySynthesisResult:
        if self.should_fail:
            raise RuntimeError("Mock provider simulated synthesis failure.")

        if not retrieved_objects and not self.custom_answer:
            return QuerySynthesisResult(
                answer="No relevant meeting context was found.",
                status=QueryAnswerStatus.INSUFFICIENT_CONTEXT,
                confidence=0.0,
                is_low_confidence=True,
                requires_verification=True,
                used_knowledge_ids=[],
                provenance={"provider": "MockQueryAnswerProvider", "reason": "no_context"},
            )

        confidence = self.custom_confidence if self.custom_confidence is not None else 0.90
        is_low = confidence < 0.75
        requires_verification = self.force_verification or is_low

        answer = self.custom_answer or f"Mock grounded answer for query: '{query}' with {len(retrieved_objects)} source(s)."
        status = self.custom_status or (
            QueryAnswerStatus.REQUIRES_VERIFICATION if requires_verification else QueryAnswerStatus.ANSWERED
        )

        used_ids = [str(obj.get("knowledge_id")) for obj in retrieved_objects if obj.get("knowledge_id")]

        return QuerySynthesisResult(
            answer=answer,
            status=status,
            confidence=confidence,
            is_low_confidence=is_low,
            requires_verification=requires_verification,
            used_knowledge_ids=used_ids,
            provenance={
                "provider": "MockQueryAnswerProvider",
                "mock_total_objects": len(retrieved_objects),
            },
        )


class QueryProviderRegistry:
    """Registry for managing active QueryAnswerProvider instances."""

    _providers: Dict[str, QueryAnswerProvider] = {}
    _default_name: str = "deterministic"

    @classmethod
    def register(cls, name: str, provider: QueryAnswerProvider, set_as_default: bool = False) -> None:
        cls._providers[name] = provider
        if set_as_default:
            cls._default_name = name

    @classmethod
    def get(cls, name: Optional[str] = None) -> QueryAnswerProvider:
        target_name = name or cls._default_name
        if target_name not in cls._providers:
            # Fallback to deterministic
            if "deterministic" not in cls._providers:
                cls._providers["deterministic"] = DeterministicQueryAnswerProvider()
            return cls._providers["deterministic"]
        return cls._providers[target_name]

    @classmethod
    def reset(cls) -> None:
        cls._providers = {
            "deterministic": DeterministicQueryAnswerProvider(),
            "mock": MockQueryAnswerProvider(),
        }
        cls._default_name = "deterministic"


# Initialize default registry state
QueryProviderRegistry.reset()
