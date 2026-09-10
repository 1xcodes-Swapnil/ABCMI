"""
Translations & Derived Representations API Endpoints (Phase 4.20)
Provides REST endpoints for generating, listing, viewing, and regenerating multilingual translations.
"""

from typing import Any, Dict, List, Optional
import uuid
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_async_db, verify_authentication
from app.core.exceptions import BadRequestException, ForbiddenException, NotFoundException
from app.schemas.translation import (
    DerivedTranslationResponse,
    TranslationListResponse,
    TranslationRegenerateRequest,
    TranslationRequest,
)
from app.services.translation_service import TranslationService

router = APIRouter(tags=["Translations"])


@router.post(
    "/meetings/{meeting_id}/translations",
    response_model=List[DerivedTranslationResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Generate translated and derived representations for a meeting",
)
async def generate_translations(
    meeting_id: uuid.UUID,
    request: TranslationRequest,
    auth_context: Dict[str, Any] = Depends(verify_authentication),
    db: AsyncSession = Depends(get_async_db),
) -> List[DerivedTranslationResponse]:
    """
    Generates requested translated/derived representations for meeting transcripts and knowledge objects.
    Idempotent: Identical requests return cached derived objects rather than creating duplicates.
    """
    service = TranslationService(db)
    translations = await service.generate_translations(
        meeting_id=meeting_id,
        request=request,
        auth_context=auth_context,
    )
    return [DerivedTranslationResponse.model_validate(t) for t in translations]


@router.get(
    "/meetings/{meeting_id}/translations",
    response_model=TranslationListResponse,
    status_code=status.HTTP_200_OK,
    summary="List available translated/derived representations for a meeting",
)
async def list_translations(
    meeting_id: uuid.UUID,
    target_language: Optional[str] = Query(default=None, description="Filter by target language code"),
    representation_type: Optional[str] = Query(default=None, description="Filter by representation type"),
    requires_verification: Optional[bool] = Query(default=None, description="Filter by verification requirement"),
    limit: int = Query(default=50, ge=1, le=200, description="Items per page"),
    offset: int = Query(default=0, ge=0, description="Pagination offset"),
    auth_context: Dict[str, Any] = Depends(verify_authentication),
    db: AsyncSession = Depends(get_async_db),
) -> TranslationListResponse:
    """
    Lists generated translations and derived representations for a meeting with filtering and pagination.
    """
    service = TranslationService(db)
    items, total = await service.list_translations(
        meeting_id=meeting_id,
        target_language=target_language,
        representation_type=representation_type,
        requires_verification=requires_verification,
        limit=limit,
        offset=offset,
        auth_context=auth_context,
    )
    return TranslationListResponse(
        items=[DerivedTranslationResponse.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/translations/{translation_id}",
    response_model=DerivedTranslationResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve translation metadata and derived content",
)
async def get_translation(
    translation_id: uuid.UUID,
    auth_context: Dict[str, Any] = Depends(verify_authentication),
    db: AsyncSession = Depends(get_async_db),
) -> DerivedTranslationResponse:
    """
    Retrieves translation metadata, translated content, confidence score, and provenance lineage.
    """
    service = TranslationService(db)
    dt = await service.get_translation(
        translation_id=translation_id,
        auth_context=auth_context,
    )
    return DerivedTranslationResponse.model_validate(dt)


@router.post(
    "/translations/{translation_id}/regenerate",
    response_model=DerivedTranslationResponse,
    status_code=status.HTTP_200_OK,
    summary="Regenerate a derived translation representation idempotently",
)
async def regenerate_translation(
    translation_id: uuid.UUID,
    request: TranslationRegenerateRequest,
    auth_context: Dict[str, Any] = Depends(verify_authentication),
    db: AsyncSession = Depends(get_async_db),
) -> DerivedTranslationResponse:
    """
    Regenerates a derived translation, updating confidence and provenance lineage while maintaining version history.
    """
    service = TranslationService(db)
    dt = await service.regenerate_translation(
        translation_id=translation_id,
        request=request,
        auth_context=auth_context,
    )
    return DerivedTranslationResponse.model_validate(dt)
