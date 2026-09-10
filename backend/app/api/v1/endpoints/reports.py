"""
Report API Router
Implements backend endpoints for generating, listing, viewing, exporting, and downloading meeting reports.
"""

from typing import Any, Dict, List, Optional
import uuid
from fastapi import APIRouter, Depends, Response, status
from fastapi.responses import Response as FastAPIResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_async_db, verify_authentication
from app.core.logging import get_logger
from app.schemas.report import (
    ExportRequest,
    ExportResponse,
    ReportRequest,
    ReportResponse,
)
from app.services.report_generation_service import ReportGenerationService
from app.infrastructure.storage import get_storage_manager

logger = get_logger(__name__)

router = APIRouter(tags=["Meeting Reports"])


@router.post("/meetings/{meeting_id}/reports", response_model=ReportResponse, status_code=status.HTTP_201_CREATED)
async def generate_meeting_report(
    meeting_id: uuid.UUID,
    payload: Optional[ReportRequest] = None,
    auth_context: Dict[str, Any] = Depends(verify_authentication),
    db: AsyncSession = Depends(get_async_db),
) -> ReportResponse:
    """Generate a structured meeting report from authoritative SKW data."""
    service = ReportGenerationService(db)
    req = payload or ReportRequest()
    report = await service.generate_report(
        meeting_id=meeting_id,
        report_type=req.report_type or "comprehensive",
        format_type=req.format or "json",
        include_analytics=req.include_analytics if req.include_analytics is not None else True,
        auth_context=auth_context,
    )
    
    # Transform ORM model to response DTO with sections
    sections = []
    if report.provenance and "sections" in report.provenance:
        # If stored in provenance or build sections from report
        pass
    
    # Build default sections representation
    sections = [
        {"title": "Report Summary", "content": f"Meeting Report generated for {meeting_id}", "confidence": 1.0, "verification_status": "verified"}
    ]
    if report.provenance and isinstance(report.provenance, dict) and "sections" in report.provenance:
        sections = report.provenance["sections"]

    return ReportResponse(
        id=report.id,
        meeting_id=report.meeting_id,
        tenant_id=report.tenant_id,
        report_type=report.report_type,
        status=report.status,
        format=report.format,
        storage_path=report.storage_path,
        file_size=report.file_size,
        checksum=report.checksum,
        version=report.version,
        provenance=report.provenance,
        sections=sections,
        created_at=report.created_at,
        updated_at=report.updated_at,
    )


@router.get("/meetings/{meeting_id}/reports", response_model=List[ReportResponse], status_code=status.HTTP_200_OK)
async def list_meeting_reports(
    meeting_id: uuid.UUID,
    auth_context: Dict[str, Any] = Depends(verify_authentication),
    db: AsyncSession = Depends(get_async_db),
) -> List[ReportResponse]:
    """List all reports generated for a specific meeting."""
    service = ReportGenerationService(db)
    reports = await service.list_reports_for_meeting(meeting_id, auth_context)
    
    response_list = []
    for report in reports:
        sections = [{"title": "Report Summary", "content": f"Meeting Report for {meeting_id}", "confidence": 1.0, "verification_status": "verified"}]
        if report.provenance and isinstance(report.provenance, dict) and "sections" in report.provenance:
            sections = report.provenance["sections"]

        response_list.append(
            ReportResponse(
                id=report.id,
                meeting_id=report.meeting_id,
                tenant_id=report.tenant_id,
                report_type=report.report_type,
                status=report.status,
                format=report.format,
                storage_path=report.storage_path,
                file_size=report.file_size,
                checksum=report.checksum,
                version=report.version,
                provenance=report.provenance,
                sections=sections,
                created_at=report.created_at,
                updated_at=report.updated_at,
            )
        )
    return response_list


@router.get("/reports/{report_id}", response_model=ReportResponse, status_code=status.HTTP_200_OK)
async def get_report_details(
    report_id: uuid.UUID,
    auth_context: Dict[str, Any] = Depends(verify_authentication),
    db: AsyncSession = Depends(get_async_db),
) -> ReportResponse:
    """Retrieve detailed metadata and sections for a specific report."""
    service = ReportGenerationService(db)
    report = await service.get_report(report_id, auth_context)

    sections = [{"title": "Report Summary", "content": f"Meeting Report for {report.meeting_id}", "confidence": 1.0, "verification_status": "verified"}]
    if report.provenance and isinstance(report.provenance, dict) and "sections" in report.provenance:
        sections = report.provenance["sections"]

    return ReportResponse(
        id=report.id,
        meeting_id=report.meeting_id,
        tenant_id=report.tenant_id,
        report_type=report.report_type,
        status=report.status,
        format=report.format,
        storage_path=report.storage_path,
        file_size=report.file_size,
        checksum=report.checksum,
        version=report.version,
        provenance=report.provenance,
        sections=sections,
        created_at=report.created_at,
        updated_at=report.updated_at,
    )


@router.post("/reports/{report_id}/export", response_model=ExportResponse, status_code=status.HTTP_200_OK)
async def export_report_endpoint(
    report_id: uuid.UUID,
    payload: ExportRequest,
    auth_context: Dict[str, Any] = Depends(verify_authentication),
    db: AsyncSession = Depends(get_async_db),
) -> ExportResponse:
    """Export or re-export a report into a target format (json, markdown, txt, pdf)."""
    service = ReportGenerationService(db)
    _, filename, checksum = await service.export_report(report_id, payload.format, auth_context)
    report = await service.get_report(report_id, auth_context)

    return ExportResponse(
        report_id=report.id,
        format=payload.format,
        download_url=f"/api/v1/reports/{report.id}/download?format={payload.format}",
        file_size=report.file_size,
        checksum=checksum,
        filename=filename,
        created_at=report.created_at,
    )


@router.get("/reports/{report_id}/download", status_code=status.HTTP_200_OK)
async def download_report_file(
    report_id: uuid.UUID,
    format: Optional[str] = None,
    auth_context: Dict[str, Any] = Depends(verify_authentication),
    db: AsyncSession = Depends(get_async_db),
) -> FastAPIResponse:
    """Download the generated report file from storage."""
    service = ReportGenerationService(db)
    report = await service.get_report(report_id, auth_context)
    target_format = format or report.format

    storage = get_storage_manager()
    try:
        file_bytes = storage.get_report_file(report.storage_path) if report.storage_path else b""
    except Exception:
        # If file needs export
        file_bytes, _, _ = await service.export_report(report_id, target_format, auth_context)

    content_types = {
        "json": "application/json",
        "markdown": "text/markdown",
        "md": "text/markdown",
        "txt": "text/plain",
        "pdf": "application/pdf",
    }
    media_type = content_types.get(target_format.lower(), "application/octet-stream")
    filename = f"report_{report.meeting_id}_{report_id}.{target_format}"

    return FastAPIResponse(
        content=file_bytes,
        media_type=media_type,
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
