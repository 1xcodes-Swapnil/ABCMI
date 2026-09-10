"""
Pydantic Schemas for Meeting Reports and Export Operations
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
import uuid
from pydantic import Field

from app.schemas.base import CoreBaseModel


class ReportRequest(CoreBaseModel):
    """Payload to trigger report generation for a meeting."""
    report_type: Optional[str] = Field(default="comprehensive", description="Report type e.g. comprehensive, executive, technical")
    format: Optional[str] = Field(default="json", description="Output format: json, markdown, txt, pdf")
    include_analytics: Optional[bool] = Field(default=True, description="Whether to include analytics and metrics")
    correlation_id: Optional[str] = Field(default=None, description="Correlation identifier")


class ReportSection(CoreBaseModel):
    """Structured report section representing a thematic block or item."""
    title: str = Field(..., description="Section title")
    content: str = Field(..., description="Section body content or serialized representation")
    confidence: Optional[float] = Field(default=None, description="Confidence score if applicable")
    verification_status: Optional[str] = Field(default=None, description="Verification status e.g. verified, pending")
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Additional section metadata")


class ReportMetadata(CoreBaseModel):
    """Metadata describing report generation provenance and context."""
    meeting_id: uuid.UUID
    tenant_id: Optional[str] = None
    generated_at: datetime
    version: int = 1
    checksum: Optional[str] = None
    file_size: int = 0
    provenance: Optional[Dict[str, Any]] = Field(default_factory=dict)


class ReportResponse(CoreBaseModel):
    """Frontend/API-safe response DTO for a meeting report."""
    id: uuid.UUID
    meeting_id: uuid.UUID
    tenant_id: Optional[str] = None
    report_type: str
    status: str
    format: str
    storage_path: Optional[str] = None
    file_size: int = 0
    checksum: Optional[str] = None
    version: int = 1
    provenance: Optional[Dict[str, Any]] = Field(default_factory=dict)
    sections: List[ReportSection] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ExportRequest(CoreBaseModel):
    """Payload to request report export in a specific format."""
    format: str = Field(..., description="Target export format: json, markdown, txt, pdf")
    correlation_id: Optional[str] = Field(default=None, description="Correlation identifier")


class ExportResponse(CoreBaseModel):
    """Response DTO for report export containing download URL and file metadata."""
    report_id: uuid.UUID
    format: str
    download_url: str
    file_size: int
    checksum: str
    filename: str
    created_at: datetime

    class Config:
        from_attributes = True
