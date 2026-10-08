"""
Translation Engine & Provider Interface (Phase 4.20)
Provides provider-neutral multilingual translation interface, deterministic mock adapter,
and provenance-preserving translation synthesis for ABCI-MI derived representations.
"""

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set
import uuid

from app.core.exceptions import BadRequestException
from app.core.logging import get_logger
from app.schemas.knowledge_object import ProvenanceMetadataSchema
from app.schemas.translation import SUPPORTED_LANGUAGES

logger = get_logger("ai.translation_engine")


class TranslationProvider(ABC):
    """Abstract base interface for translation providers."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Unique identifier for the translation provider."""
        pass

    @property
    @abstractmethod
    def supported_languages(self) -> Set[str]:
        """Set of supported ISO 639-1 language codes."""
        pass

    @abstractmethod
    async def translate_text(
        self,
        text: str,
        source_lang: str,
        target_lang: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Translates input text from source_lang to target_lang."""
        pass

    @abstractmethod
    async def detect_language(self, text: str) -> str:
        """Detects language of input text or returns default."""
        pass


class MockTranslationProvider(TranslationProvider):
    """
    Deterministic mock translation provider for testing and offline execution.
    Produces deterministic translated representations for all 17 supported languages.
    """

    MOCK_GLOSSARY: Dict[str, Dict[str, str]] = {
        "hi": {"Decision": "निर्णय", "Action": "कार्य", "Summary": "सारांश", "Topic": "विषय", "Fact": "तथ्य"},
        "ta": {"Decision": "முடிவு", "Action": "செயல்", "Summary": "சுருக்கம்", "Topic": "தலைப்பு", "Fact": "உண்மை"},
        "te": {"Decision": "నిర్ణయం", "Action": "చర్య", "Summary": "సారాంశం", "Topic": "అంశం", "Fact": "వాస్తవం"},
        "kn": {"Decision": "ನಿರ್ಧಾರ", "Action": "ಕ್ರಿಯೆ", "Summary": "ಸಾರಾಂಶ", "Topic": "ವಿಷಯ", "Fact": "ವಾಸ್ತವ"},
        "ml": {"Decision": "തീരുമാനം", "Action": "നടപടി", "Summary": "സംഗ്രഹം", "Topic": "വിഷയം", "Fact": "വസ്തുത"},
        "bn": {"Decision": "সিদ্ধান্ত", "Action": "কর্ম", "Summary": "সারসংক্ষেপ", "Topic": "বিষয়", "Fact": "তথ্য"},
        "mr": {"Decision": "निर्णय", "Action": "कृती", "Summary": "सारांश", "Topic": "विषय", "Fact": "तथ्य"},
        "gu": {"Decision": "નિર્ણય", "Action": "કાર્ય", "Summary": "સારાંશ", "Topic": "વિષય", "Fact": "હકીકત"},
        "pa": {"Decision": "ਫੈਸਲਾ", "Action": "ਕਾਰਵਾਈ", "Summary": "ਸੰਖੇਪ", "Topic": "ਵਿਸ਼ਾ", "Fact": "ਤੱਥ"},
        "es": {"Decision": "Decisión", "Action": "Acción", "Summary": "Resumen", "Topic": "Tema", "Fact": "Hecho"},
        "fr": {"Decision": "Décision", "Action": "Action", "Summary": "Résumé", "Topic": "Sujet", "Fact": "Fait"},
        "de": {"Decision": "Entscheidung", "Action": "Aktion", "Summary": "Zusammenfassung", "Topic": "Thema", "Fact": "Tatsache"},
        "zh": {"Decision": "决定", "Action": "行动项", "Summary": "摘要", "Topic": "主题", "Fact": "事实"},
        "ja": {"Decision": "決定事項", "Action": "アクション", "Summary": "要約", "Topic": "トピック", "Fact": "事実"},
        "ru": {"Decision": "Решение", "Action": "Действие", "Summary": "Резюме", "Topic": "Тема", "Fact": "Факт"},
        "ar": {"Decision": "قرار", "Action": "إجراء", "Summary": "ملخص", "Topic": "موضوع", "Fact": "حقيقة"},
    }

    def __init__(self, name: str = "mock_translation_provider"):
        self._name = name

    @property
    def provider_name(self) -> str:
        return self._name

    @property
    def supported_languages(self) -> Set[str]:
        return SUPPORTED_LANGUAGES

    async def detect_language(self, text: str) -> str:
        if not text or not text.strip():
            return "en"
        # Check simple script heuristics or return default
        return "en"

    async def translate_text(
        self,
        text: str,
        source_lang: str,
        target_lang: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        meta = metadata or {}
        confidence = meta.get("confidence_override", 0.94)

        if not text or not text.strip():
            return {
                "translated_text": "",
                "confidence": confidence,
                "source_language": source_lang,
                "target_language": target_lang,
                "is_fixture": True,
                "provider": self.provider_name,
            }

        # Deterministic mock translated representation
        prefix = f"[{target_lang.upper()}]"
        glossary = self.MOCK_GLOSSARY.get(target_lang, {})
        translated_body = text
        for term, translated_term in glossary.items():
            if term in text:
                translated_body = translated_body.replace(term, translated_term)

        translated_text = f"{prefix} {translated_body}"

        return {
            "translated_text": translated_text,
            "confidence": float(confidence),
            "source_language": source_lang,
            "target_language": target_lang,
            "is_fixture": True,
            "provider": self.provider_name,
        }


class GeminiTranslationProvider(TranslationProvider):
    @property
    def provider_name(self):
        return "gemini"

    @property
    def supported_languages(self):
        return set(SUPPORTED_LANGUAGES)

    async def detect_language(self, text):
        # Unknown remains explicit; Gemini detects it in the translation request.
        return "und"

    async def translate_text(self, text, source_lang, target_lang, metadata=None):
        from app.ai.gemini_text import GeminiTextProvider
        from fastapi import HTTPException
        result, generation = await GeminiTextProvider().generate_json(
            "Translate all source text faithfully into the target language. Preserve names, uncertainty and meaning. "
            "Do not add facts or explanations. Detect the source language if it is und. Return ISO language codes.",
            {"text": text, "source_language": source_lang, "target_language": target_lang},
            {"type": "OBJECT", "properties": {"translated_text": {"type": "STRING"},
             "source_language": {"type": "STRING"}, "target_language": {"type": "STRING"}},
             "required": ["translated_text", "source_language", "target_language"]})
        if not isinstance(result.get("translated_text"), str) or not result["translated_text"].strip() or result.get("target_language") != target_lang:
            raise HTTPException(502, "Gemini translation is empty or has an incorrect target language")
        return {**result, "confidence": None, "is_fixture": False, "generation": generation}


class TranslationProviderRegistry:
    """Registry managing translation engine providers."""

    def __init__(self):
        self._providers: Dict[str, TranslationProvider] = {}
        default_mock = MockTranslationProvider("mock_translation_provider")
        self.register(default_mock)
        self.register(GeminiTranslationProvider())

    def register(self, provider: TranslationProvider) -> None:
        self._providers[provider.provider_name] = provider

    def get(self, provider_name: Optional[str] = None) -> TranslationProvider:
        from app.core.config import get_settings
        from fastapi import HTTPException
        if get_settings().EXECUTION_MODE.upper() == "REAL":
            provider_name = provider_name or get_settings().TEXT_AI_PROVIDER.lower()
            if provider_name != "gemini":
                raise HTTPException(503, "REAL translation requires the configured Gemini provider")
        name = provider_name or "mock_translation_provider"
        provider = self._providers.get(name)
        if not provider:
            raise BadRequestException(
                message=f"Unsupported translation provider '{name}'",
                code="UNSUPPORTED_TRANSLATION_PROVIDER",
            )
        return provider

    def list_providers(self) -> List[str]:
        return list(self._providers.keys())


# Singleton registry instance
translation_provider_registry = TranslationProviderRegistry()


class TranslationEngine:
    """
    Core Translation Engine coordinating language validation, translation generation,
    confidence thresholding, and provenance metadata construction.
    """

    def __init__(self, registry: Optional[TranslationProviderRegistry] = None):
        self.registry = registry or translation_provider_registry

    async def translate(
        self,
        text: str,
        target_language: str,
        source_language: Optional[str] = None,
        confidence_threshold: float = 0.75,
        metadata: Optional[Dict[str, Any]] = None,
        provider_name: Optional[str] = None,
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Translates text to target language, performs confidence scoring,
        determines verification requirement, and attaches provenance.
        """
        provider = self.registry.get(provider_name)
        norm_target = target_language.strip().lower()
        if norm_target not in provider.supported_languages:
            raise BadRequestException(
                message=f"Language '{norm_target}' is not supported by translation provider '{provider.provider_name}'",
                code="UNSUPPORTED_LANGUAGE",
            )

        norm_source = (source_language or await provider.detect_language(text)).strip().lower()

        # Execute provider translation
        result = await provider.translate_text(
            text=text,
            source_lang=norm_source,
            target_lang=norm_target,
            metadata=metadata,
        )

        translated = result.get("translated_text")
        if not isinstance(translated, str) or not translated.strip():
            raise ValueError("Translation provider returned no translated text")
        from app.core.config import get_settings
        if get_settings().EXECUTION_MODE.upper() == "REAL" and result.get("is_fixture") is not False:
            raise ValueError("REAL translation requires explicit non-fixture provider provenance")
        confidence = float(result["confidence"]) if result.get("confidence") is not None else None
        is_low_confidence = confidence is None or confidence < confidence_threshold
        requires_verification = is_low_confidence or (metadata.get("requires_verification", False) if metadata else False)

        provenance = ProvenanceMetadataSchema(
            producing_module="TranslationEngine",
            model_name=provider.provider_name,
            model_version=result.get("generation", {}).get("model_version"),
            source_segments=metadata.get("source_segments", []) if metadata else [],
            source_intervals=metadata.get("source_intervals", []) if metadata else [],
            lineage={
                "source_language": norm_source,
                "target_language": norm_target,
                "source_object_id": metadata.get("source_object_id") if metadata else None,
                "source_segment_id": metadata.get("source_segment_id") if metadata else None,
                "is_fixture": result.get("is_fixture", True),
            },
            processing_metadata={
                "confidence_threshold": confidence_threshold,
                "is_low_confidence": is_low_confidence,
                "requires_verification": requires_verification,
                "correlation_id": correlation_id,
                "generation": result.get("generation"),
            },
        )

        return {
            "translated_text": translated,
            "source_language": norm_source,
            "target_language": norm_target,
            "confidence": confidence,
            "is_low_confidence": is_low_confidence,
            "requires_verification": requires_verification,
            "provenance": provenance.model_dump(),
            "provider": provider.provider_name,
        }
