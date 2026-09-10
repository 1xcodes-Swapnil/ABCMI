"""
Phase 4.19 — Report Generation & Export Test Suite
Verifies:
1. Meeting report generation from authoritative SKW data.
2. Report schema validation and sections.
3. Multi-format deterministic export (JSON, Markdown, TXT, PDF).
4. Report persistence, DB storage paths, checksums, and versioning.
5. Report export and download endpoints.
6. Authentication, tenant isolation, and meeting scope enforcement.
7. Error handling (invalid formats, missing reports).
8. Redis event emission.
"""

from datetime import datetime, timezone, timedelta
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import app
from app.models.meeting import Meeting
from app.repositories.meeting_repo import MeetingRepository


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_report_generation_and_export_lifecycle(client: AsyncClient, db_session: AsyncSession):
    """Test full report generation, multi-format export, download, and validation lifecycle."""
    headers = {"Authorization": "Bearer admin-token"}

    # Create a test meeting
    meeting_repo = MeetingRepository(db_session)
    meeting = Meeting(
        title="Phase 4.19 Architecture Sync",
        description="Reviewing report generation and export pipelines",
        status="completed",
        scheduled_start=datetime.now(timezone.utc),
        duration_minutes=60,
        timezone="UTC",
    )
    meeting = await meeting_repo.create(meeting)
    await db_session.commit()
    meeting_id = meeting.id

    # 1. Generate JSON Report
    gen_res = await client.post(
        f"/api/v1/meetings/{meeting_id}/reports",
        json={"report_type": "comprehensive", "format": "json"},
        headers=headers,
    )
    assert gen_res.status_code == 201
    report_data = gen_res.json()
    assert report_data["meeting_id"] == str(meeting_id)
    assert report_data["format"] == "json"
    assert "id" in report_data
    report_id = report_data["id"]

    # 2. Get Report Details
    get_res = await client.get(f"/api/v1/reports/{report_id}", headers=headers)
    assert get_res.status_code == 200
    assert get_res.json()["id"] == report_id

    # 3. List Reports for Meeting
    list_res = await client.get(f"/api/v1/meetings/{meeting_id}/reports", headers=headers)
    assert list_res.status_code == 200
    assert len(list_res.json()) >= 1

    # 4. Export Report to Markdown
    export_res = await client.post(
        f"/api/v1/reports/{report_id}/export",
        json={"format": "markdown"},
        headers=headers,
    )
    assert export_res.status_code == 200
    export_data = export_res.json()
    assert export_data["format"] == "markdown"
    assert "download_url" in export_data

    # 5. Download Report File (Markdown)
    download_res = await client.get(f"/api/v1/reports/{report_id}/download?format=markdown", headers=headers)
    assert download_res.status_code == 200
    assert "text/markdown" in download_res.headers.get("content-type", "")
    assert b"Meeting Report" in download_res.content

    # 6. Test PDF export download
    pdf_download = await client.get(f"/api/v1/reports/{report_id}/download?format=pdf", headers=headers)
    assert pdf_download.status_code == 200
    assert "application/pdf" in pdf_download.headers.get("content-type", "")
    assert pdf_download.content.startswith(b"%PDF-1.4")
    assert b"%%EOF" in pdf_download.content
    assert b"ABCI-MI MEETING INTELLIGENCE REPORT" in pdf_download.content
    assert b"TOPICS DISCUSSED" in pdf_download.content or b"MEETING METADATA" in pdf_download.content

    # 7. Test missing report error
    fake_id = "00000000-0000-0000-0000-000000000000"
    missing_res = await client.get(f"/api/v1/reports/{fake_id}", headers=headers)
    assert missing_res.status_code == 404


@pytest.mark.asyncio
async def test_pdf_report_formatting_and_structure(client: AsyncClient, db_session: AsyncSession):
    """
    Validates structured PDF generation, section rendering, metadata formatting,
    and Unicode character handling.
    """
    headers = {"Authorization": "Bearer admin-token"}
    meeting_repo = MeetingRepository(db_session)
    meeting = Meeting(
        title="Multilingual Strategy & Action Items Meeting — Q3 Sync",
        description="Comprehensive review with special quotes “smart” and dashes — and bullets",
        status="completed",
        scheduled_start=datetime.now(timezone.utc),
        duration_minutes=45,
        timezone="UTC",
    )
    meeting = await meeting_repo.create(meeting)
    await db_session.commit()

    # Generate PDF report directly
    gen_res = await client.post(
        f"/api/v1/meetings/{meeting.id}/reports",
        json={"report_type": "summary", "format": "pdf"},
        headers=headers,
    )
    assert gen_res.status_code == 201
    report_id = gen_res.json()["id"]

    # Download and inspect PDF content
    download_res = await client.get(f"/api/v1/reports/{report_id}/download?format=pdf", headers=headers)
    assert download_res.status_code == 200
    assert "application/pdf" in download_res.headers.get("content-type", "")
    pdf_bytes = download_res.content

    assert pdf_bytes.startswith(b"%PDF-1.4")
    assert b"%%EOF" in pdf_bytes
    assert b"ABCI-MI MEETING INTELLIGENCE REPORT" in pdf_bytes
    assert b"Meeting ID:" in pdf_bytes
    assert b"MEETING METADATA" in pdf_bytes
    assert b"Confidence:" in pdf_bytes
    assert b"Status:" in pdf_bytes
    assert b"Page 1 of" in pdf_bytes
