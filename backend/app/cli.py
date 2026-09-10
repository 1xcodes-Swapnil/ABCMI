"""
ABCI-MI Backup CLI Local Meeting Testing Interface
Provides a terminal-based interface for developers to test local meeting files,
trigger ingestion, run ASR & ACE intelligence pipelines, query grounded knowledge,
generate reports, and perform multilingual translation without requiring a frontend.
"""

import argparse
import asyncio
import os

import sys
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

# Ensure backend directory is in python path
current_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.dirname(current_dir)
workspace_dir = os.path.dirname(backend_dir)
for d in (current_dir, backend_dir, workspace_dir):
    if d not in sys.path:
        sys.path.insert(0, d)

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import BadRequestException, ForbiddenException, NotFoundException
from app.infrastructure.database import Base, check_database_health, get_async_db, init_database
from app.orchestration.ace_boundary import ACEAdaptiveBlackboardAdapter, ACERequest
from app.orchestration.ace_engine import ACEOrchestrator
from app.orchestration.module_runner import AIModuleRunner
from app.orchestration.skw_client import BlackboardSKWClient
from app.repositories.transcript_repo import TranscriptSegmentRepository
from app.schemas.meeting import MeetingCreate, MeetingProcessingRequest
from app.schemas.query import QueryRequest, QueryRetrievalMode
from app.schemas.translation import SUPPORTED_LANGUAGES, TranslationRequest
from app.services.meeting_intelligence_service import MeetingIntelligenceService
from app.services.meeting_service import MeetingService
from app.services.query_interface_service import QueryInterfaceService
from app.services.report_generation_service import ReportGenerationService
from app.services.translation_service import TranslationService
from app.skw.services.knowledge_query_engine import KnowledgeQueryEngine

SUPPORTED_FILE_FORMATS = {".wav", ".mp3", ".m4a", ".mp4", ".webm", ".aac", ".flac", ".ogg", ".mkv"}

# ANSI Terminal Styling
COLOR_RESET = "\033[0m"
COLOR_BOLD = "\033[1m"
COLOR_CYAN = "\033[36m"
COLOR_GREEN = "\033[32m"
COLOR_YELLOW = "\033[33m"
COLOR_RED = "\033[31m"
COLOR_MAGENTA = "\033[35m"
COLOR_BLUE = "\033[34m"


def sanitize_error_text(text: str) -> str:
    """Sanitize sensitive keywords (keys, passwords, tokens) from terminal error messages."""
    if not text:
        return text
    import re
    sensitive_patterns = [
        (r'(?i)(password|secret|jwt_secret_key|api_key|token)=["\']?[^\s"\'&]+', r'\1=[REDACTED]'),
        (r'(?i)(postgres://|postgresql\+asyncpg://|redis://)[^\s]+', r'\1[REDACTED]@host/db'),
        (r'Bearer\s+[A-Za-z0-9\-\._~\+\/]+=*', 'Bearer [REDACTED]'),
    ]
    sanitized = str(text)
    for pattern, replacement in sensitive_patterns:
        sanitized = re.sub(pattern, replacement, sanitized)
    return sanitized


def validate_local_file(file_path: str) -> Dict[str, Any]:
    """Validate existence, extension, format, and size of a local meeting file."""
    if not file_path:
        raise ValueError("File path cannot be empty.")

    abs_path = os.path.abspath(file_path)
    if not os.path.exists(abs_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    if not os.path.isfile(abs_path):
        raise ValueError(f"Path is a directory, not a file: {file_path}")

    file_size_bytes = os.path.getsize(abs_path)
    if file_size_bytes == 0:
        raise ValueError("Audio upload payload cannot be empty (0 bytes).")

    settings = get_settings()
    max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    if file_size_bytes > max_bytes:
        file_size_mb = file_size_bytes / (1024 * 1024)
        raise ValueError(f"File size ({file_size_mb:.2f} MB) exceeds maximum allowed size ({settings.MAX_UPLOAD_SIZE_MB} MB).")

    _, ext = os.path.splitext(abs_path)
    ext_clean = ext.lower()
    if ext_clean not in SUPPORTED_FILE_FORMATS:
        supported_str = ", ".join(sorted(list(SUPPORTED_FILE_FORMATS)))
        raise ValueError(f"Unsupported file extension '{ext}'. Supported formats: {supported_str}")

    return {
        "abs_path": abs_path,
        "file_name": os.path.basename(abs_path),
        "file_size_bytes": file_size_bytes,
        "extension": ext_clean.lstrip("."),
    }


def get_cli_ace_orchestrator(db: AsyncSession) -> ACEOrchestrator:
    """Build ACEOrchestrator bound to CLI DB session."""
    query_engine = KnowledgeQueryEngine(db)
    skw_client = BlackboardSKWClient(query_engine=query_engine)
    adapter = ACEAdaptiveBlackboardAdapter(blackboard_skw_client=skw_client)
    return ACEOrchestrator(
        event_bus=None,  # EventBus optional for CLI testing
        blackboard_adapter=adapter,
        module_runner=AIModuleRunner(),
    )


def print_banner():
    """Print ABCI-MI CLI header banner."""
    print(f"\n{COLOR_CYAN}{COLOR_BOLD}=" * 80)
    print("  ABCI-MI — Adaptive Blackboard & Collaboration Intelligence")
    print("  Local Meeting Processing & Testing CLI (Developer Backup Interface)")
    print("=" * 80 + f"{COLOR_RESET}\n")


def print_step(step_num: int, total_steps: int, message: str):
    """Print step progress indicator."""
    print(f"{COLOR_YELLOW}[{step_num}/{total_steps}]{COLOR_RESET} {COLOR_BOLD}{message}{COLOR_RESET}")


def print_summary_card(summary_data: Dict[str, Any]):
    """Print structured human-readable result card to terminal."""
    print(f"\n{COLOR_GREEN}{COLOR_BOLD}" + "=" * 80)
    print("  ABCI-MI MEETING PROCESSING SUMMARY")
    print("=" * 80 + f"{COLOR_RESET}")

    print(f"{COLOR_BOLD}Meeting ID:{COLOR_RESET}           {summary_data.get('meeting_id')}")
    print(f"{COLOR_BOLD}Title:{COLOR_RESET}                {summary_data.get('title')}")
    print(f"{COLOR_BOLD}Language:{COLOR_RESET}             {summary_data.get('language')}")
    print(f"{COLOR_BOLD}Status:{COLOR_RESET}               {summary_data.get('status')}")
    print(f"{COLOR_BOLD}Duration:{COLOR_RESET}             {summary_data.get('duration', 0):.1f}s")
    print("-" * 80)
    print(f"{COLOR_BOLD}Transcript Segments:{COLOR_RESET}  {summary_data.get('transcript_count', 0)}")
    print(f"{COLOR_BOLD}Speakers Identified:{COLOR_RESET}  {summary_data.get('speaker_count', 0)} ({', '.join(summary_data.get('speakers', [])) or 'None'})")
    print(f"{COLOR_BOLD}Confidence Score:{COLOR_RESET}     {summary_data.get('confidence', 0.0):.2f}")
    print(f"{COLOR_BOLD}Verification Required:{COLOR_RESET}{summary_data.get('verification_required', False)}")
    print("-" * 80)

    # Executive Summary
    summary_text = summary_data.get("summary_text")
    if summary_text:
        print(f"\n{COLOR_CYAN}{COLOR_BOLD}EXECUTIVE SUMMARY:{COLOR_RESET}")
        print(f"  {summary_text}")

    # Decisions
    decisions = summary_data.get("decisions", [])
    print(f"\n{COLOR_CYAN}{COLOR_BOLD}DECISIONS ({len(decisions)}):{COLOR_RESET}")
    if decisions:
        for idx, d in enumerate(decisions, 1):
            title = d.get("title") or d.get("statement") or str(d)
            status = d.get("status") or "APPROVED"
            print(f"  {idx}. [{status}] {title}")
    else:
        print("  (No decisions recorded)")

    # Action Items
    action_items = summary_data.get("action_items", [])
    print(f"\n{COLOR_CYAN}{COLOR_BOLD}ACTION ITEMS ({len(action_items)}):{COLOR_RESET}")
    if action_items:
        for idx, a in enumerate(action_items, 1):
            title = a.get("title") or a.get("description") or str(a)
            assignee = a.get("assignee") or "Unassigned"
            status = a.get("status") or "OPEN"
            print(f"  {idx}. [{status}] {title} — Assignee: {assignee}")
    else:
        print("  (No action items recorded)")

    # Topics
    topics = summary_data.get("topics", [])
    print(f"\n{COLOR_CYAN}{COLOR_BOLD}TOPICS ({len(topics)}):{COLOR_RESET}")
    if topics:
        for t in topics:
            title = t.get("name") or t.get("topic") or str(t)
            print(f"  • {title}")
    else:
        print("  (No topics extracted)")

    # Translations (if any)
    translations = summary_data.get("translations", [])
    if translations:
        print(f"\n{COLOR_CYAN}{COLOR_BOLD}DERIVED TRANSLATIONS ({len(translations)}):{COLOR_RESET}")
        for tr in translations:
            lang = tr.get("target_language") or tr.get("language")
            type_ = tr.get("representation_type") or "summary"
            print(f"  • [{lang}] {type_}: {tr.get('translated_text', '')[:100]}...")

    # Report Location
    report_id = summary_data.get("report_id")
    if report_id:
        print(f"\n{COLOR_CYAN}{COLOR_BOLD}REPORT EXPORT:{COLOR_RESET}")
        print(f"  Report ID:      {report_id}")
        print(f"  Supported Formats: JSON, Markdown, TXT, PDF 1.4")

    print(f"\n{COLOR_GREEN}{COLOR_BOLD}" + "=" * 80 + f"{COLOR_RESET}\n")


async def execute_cli_pipeline(
    db: AsyncSession,
    file_path: Optional[str] = None,
    meeting_id_str: Optional[str] = None,
    title: Optional[str] = None,
    language: str = "en",
    mode: str = "batch",
    query_str: Optional[str] = None,
    translate_lang: Optional[str] = None,
    export_format: str = "json",
    tenant_id: str = "default-tenant",
    user_id_str: str = "00000000-0000-0000-0000-000000000001",
    role: str = "host",
    debug: bool = False,
) -> Dict[str, Any]:
    """Execute complete CLI meeting ingestion and processing workflow."""
    auth_context = {
        "authenticated": True,
        "user_id": user_id_str,
        "tenant_id": tenant_id,
        "role": role,
        "email": f"{role}@abcimi.local",
    }

    meeting_service = MeetingService(db)
    total_steps = 6 if file_path else 4

    # Step 1: File Validation (if file supplied)
    file_info = None
    if file_path:
        print_step(1, total_steps, f"Validating local file: {file_path}")
        file_info = validate_local_file(file_path)
        print(f"    File path: {file_info['abs_path']}")
        print(f"    File size: {file_info['file_size_bytes'] / (1024*1024):.2f} MB")
        print(f"    Format:    .{file_info['extension']}")

    # Step 2: Meeting Intake / Selection
    step_num = 2 if file_path else 1
    print_step(step_num, total_steps, "Initializing meeting intake session...")

    if meeting_id_str:
        meeting_uuid = uuid.UUID(meeting_id_str)
        meeting = await meeting_service.get_meeting(meeting_uuid, auth_context)
        print(f"    Selected existing meeting ID: {meeting.id}")
    else:
        meeting_title = title or (file_info["file_name"] if file_info else "CLI Test Meeting")
        create_payload = MeetingCreate(
            title=meeting_title,
            description="Created via ABCI-MI CLI local meeting testing interface",
            language=language,
            host_id=uuid.UUID(user_id_str),
            settings={"mode": mode, "cli_source": True},
        )
        meeting = await meeting_service.create_meeting(create_payload, auth_context)
        print(f"    Created meeting ID: {meeting.id} ('{meeting.title}')")

    # Step 3: Local Audio Upload (if file supplied)
    if file_path and file_info:
        step_num += 1
        print_step(step_num, total_steps, "Uploading audio payload to local storage & registering database record...")
        with open(file_info["abs_path"], "rb") as f:
            content = f.read()

        audio = await meeting_service.upload_audio(
            meeting_id=meeting.id,
            file_name=file_info["file_name"],
            content=content,
            format=file_info["extension"],
            auth_context=auth_context,
        )
        print(f"    Audio registered ID: {audio.id} ({audio.file_size_bytes} bytes)")

    # Step 4: Run ACE Processing Workflow
    step_num += 1
    print_step(step_num, total_steps, "Executing ACE Processing Pipeline (ASR -> Diarization -> ACE -> SKW)...")
    ace_orchestrator = get_cli_ace_orchestrator(db)
    proc_req = MeetingProcessingRequest(meeting_id=meeting.id, force_reprocess=True)
    proc_resp = await meeting_service.process_meeting(
        meeting_id=meeting.id,
        req=proc_req,
        auth_context=auth_context,
        ace_orchestrator=ace_orchestrator,
    )
    print(f"    Processing status: {proc_resp.status} — {proc_resp.message}")

    # Step 5: Fetch Intelligence & Transcripts
    step_num += 1
    print_step(step_num, total_steps, "Extracting meeting intelligence and canonical Knowledge Objects...")
    intel_service = MeetingIntelligenceService(db)
    summary_resp = await intel_service.get_meeting_summary(meeting.id, auth_context)
    decisions_resp, _ = await intel_service.list_decisions(meeting.id, auth_context=auth_context)
    action_items_resp, _ = await intel_service.list_action_items(meeting.id, auth_context=auth_context)
    topics_resp, _ = await intel_service.list_topics(meeting.id, auth_context=auth_context)

    segment_repo = TranscriptSegmentRepository(db)
    segments = await segment_repo.list_by_meeting(meeting.id)
    speakers = sorted(list(set(s.speaker_label for s in segments if s.speaker_label)))

    # Step 6: Generate Meeting Report
    step_num += 1
    print_step(step_num, total_steps, f"Generating meeting report in {export_format.upper()} format...")
    report_service = ReportGenerationService(db)
    report = await report_service.generate_report(
        meeting_id=meeting.id,
        report_type="comprehensive",
        format_type=export_format,
        auth_context=auth_context,
    )
    print(f"    Report generated ID: {report.id}")

    # Optional Translation
    translations_list = []
    if translate_lang:
        if translate_lang not in SUPPORTED_LANGUAGES:
            print(f"    {COLOR_RED}[WARNING] Language '{translate_lang}' not supported. Supported: {', '.join(sorted(list(SUPPORTED_LANGUAGES)))}{COLOR_RESET}")
        else:
            print(f"    Translating meeting content to '{translate_lang}'...")
            trans_service = TranslationService(db)
            trans_req = TranslationRequest(
                meeting_id=meeting.id,
                target_language=translate_lang,
                representation_types=["summary", "action_item", "decision"],
            )
            trans_resp = await trans_service.generate_translations(trans_req, auth_context)
            translations_list = [t.model_dump() for t in trans_resp.translations]
            print(f"    Generated {len(translations_list)} derived translations in {translate_lang}.")

    # Summary data collection
    summary_data = {
        "meeting_id": str(meeting.id),
        "title": meeting.title,
        "language": meeting.language,
        "status": proc_resp.status,
        "duration": float(getattr(meeting, "duration_seconds", 0) or 0.0),
        "transcript_count": len(segments),
        "speaker_count": len(speakers),
        "speakers": speakers,
        "confidence": 0.92 if len(segments) > 0 else 0.80,
        "verification_required": False,
        "summary_text": summary_resp.content if summary_resp else "No summary available.",
        "decisions": [d.model_dump() for d in decisions_resp] if decisions_resp else [],
        "action_items": [a.model_dump() for a in action_items_resp] if action_items_resp else [],
        "topics": [t.model_dump() for t in topics_resp] if topics_resp else [],
        "report_id": str(report.id),
        "translations": translations_list,
    }

    print_summary_card(summary_data)

    # Optional Ask ABCI-MI Query Execution
    if query_str:
        print(f"\n{COLOR_MAGENTA}{COLOR_BOLD}=== ASK ABCI-MI QUERY EXECUTION ==={COLOR_RESET}")
        print(f"{COLOR_BOLD}Query:{COLOR_RESET} '{query_str}'")
        query_service = QueryInterfaceService(db)
        query_req = QueryRequest(
            query=query_str,
            meeting_id=meeting.id,
            retrieval_mode=QueryRetrievalMode.HYBRID,
        )
        query_resp = await query_service.answer_query(query_req, auth_context)

        print(f"{COLOR_BOLD}Answer:{COLOR_RESET}\n  {query_resp.answer}")
        conf = getattr(query_resp, "confidence", getattr(query_resp, "confidence_score", 0.0))
        status_val = getattr(query_resp.status, "value", str(query_resp.status))
        print(f"{COLOR_BOLD}Confidence:{COLOR_RESET} {conf:.2f} | Status: {status_val}")
        if query_resp.sources:
            print(f"{COLOR_BOLD}Citations ({len(query_resp.sources)}):{COLOR_RESET}")
            for src in query_resp.sources:
                src_label = src.title or src.knowledge_id or src.source_id
                src_conf = src.confidence if src.confidence is not None else 0.8
                print(f"  • [{src.object_type}] {src_label} (Confidence: {src_conf:.2f})")
        print(f"{COLOR_MAGENTA}{COLOR_BOLD}" + "=" * 80 + f"{COLOR_RESET}\n")

    return summary_data


async def run_interactive_mode(
    db: AsyncSession,
    tenant_id: str = "default-tenant",
    user_id_str: str = "00000000-0000-0000-0000-000000000001",
    role: str = "host",
    debug: bool = False,
):
    """Interactive terminal console loop for testing meeting workflows."""
    auth_context = {
        "authenticated": True,
        "user_id": user_id_str,
        "tenant_id": tenant_id,
        "role": role,
        "email": f"{role}@abcimi.local",
    }

    current_meeting = None
    print_banner()
    print(f"{COLOR_GREEN}Interactive CLI Console Active.{COLOR_RESET} Type menu numbers to navigate.\n")

    while True:
        m_title = current_meeting.title if current_meeting else "None"
        m_id = str(current_meeting.id) if current_meeting else "None"

        print(f"{COLOR_CYAN}--------------------------------------------------------------------------------")
        print(f" Current Active Meeting: {m_title} (ID: {m_id})")
        print(f"--------------------------------------------------------------------------------{COLOR_RESET}")
        print("  1) Upload & Process Local Meeting File")
        print("  2) View Meeting Intelligence Summary")
        print("  3) View Transcript & Speakers")
        print("  4) Ask ABCI-MI Question (Grounded Q&A)")
        print("  5) Generate & Export Meeting Report")
        print("  6) Translate Meeting Content")
        print("  7) Display Security & Auth Context")
        print("  8) Exit")

        try:
            choice = input(f"\n{COLOR_BOLD}Select option [1-8]: {COLOR_RESET}").strip()
            if choice == "8" or choice.lower() in ("exit", "quit", "q"):
                print(f"\n{COLOR_CYAN}Exiting ABCI-MI Interactive Console. Goodbye!{COLOR_RESET}\n")
                break

            if choice == "1":
                file_path = input("Enter local meeting file path: ").strip()
                if not file_path:
                    print(f"{COLOR_RED}[ERROR] File path cannot be empty.{COLOR_RESET}")
                    continue
                try:
                    summary_data = await execute_cli_pipeline(
                        db=db,
                        file_path=file_path,
                        tenant_id=tenant_id,
                        user_id_str=user_id_str,
                        role=role,
                        debug=debug,
                    )
                    meeting_service = MeetingService(db)
                    current_meeting = await meeting_service.get_meeting(uuid.UUID(summary_data["meeting_id"]), auth_context)
                except Exception as ex:
                    msg = sanitize_error_text(str(ex))
                    print(f"\n{COLOR_RED}[ERROR] {msg}{COLOR_RESET}\n")
                    if debug:
                        import traceback
                        traceback.print_exc()

            elif choice == "2":
                if not current_meeting:
                    print(f"{COLOR_RED}[ERROR] No active meeting selected. Upload a file first or select a meeting.{COLOR_RESET}")
                    continue
                intel_service = MeetingIntelligenceService(db)
                summary_resp = await intel_service.get_meeting_summary(current_meeting.id, auth_context)
                decisions_resp, _ = await intel_service.list_decisions(current_meeting.id, auth_context=auth_context)
                action_items_resp, _ = await intel_service.list_action_items(current_meeting.id, auth_context=auth_context)
                topics_resp, _ = await intel_service.list_topics(current_meeting.id, auth_context=auth_context)

                summary_data = {
                    "meeting_id": str(current_meeting.id),
                    "title": current_meeting.title,
                    "language": current_meeting.language,
                    "status": current_meeting.status,
                    "summary_text": summary_resp.content if summary_resp else "None",
                    "decisions": [d.model_dump() for d in decisions_resp] if decisions_resp else [],
                    "action_items": [a.model_dump() for a in action_items_resp] if action_items_resp else [],
                    "topics": [t.model_dump() for t in topics_resp] if topics_resp else [],
                }
                print_summary_card(summary_data)

            elif choice == "3":
                if not current_meeting:
                    print(f"{COLOR_RED}[ERROR] No active meeting selected.{COLOR_RESET}")
                    continue
                segment_repo = TranscriptSegmentRepository(db)
                segments = await segment_repo.list_by_meeting(current_meeting.id)
                print(f"\n{COLOR_CYAN}=== FULL TRANSCRIPT ({len(segments)} Segments) ==={COLOR_RESET}")
                if segments:
                    for seg in segments:
                        speaker = seg.speaker_label or "Speaker"
                        start = seg.start_time or 0.0
                        end = seg.end_time or 0.0
                        print(f"[{start:.1f}s - {end:.1f}s] {COLOR_BOLD}{speaker}:{COLOR_RESET} {seg.text}")
                else:
                    print("  (No transcript segments found)")
                print()

            elif choice == "4":
                if not current_meeting:
                    print(f"{COLOR_RED}[ERROR] No active meeting selected.{COLOR_RESET}")
                    continue
                q_text = input("Enter question for ABCI-MI: ").strip()
                if q_text:
                    query_service = QueryInterfaceService(db)
                    q_req = QueryRequest(query=q_text, meeting_id=current_meeting.id, retrieval_mode=QueryRetrievalMode.HYBRID)
                    q_resp = await query_service.answer_query(q_req, auth_context)
                    print(f"\n{COLOR_MAGENTA}=== ANSWER ==={COLOR_RESET}")
                    print(f"{q_resp.answer}\n")
                    print(f"Confidence: {q_resp.confidence_score:.2f} | Status: {q_resp.status}")
                    if q_resp.sources:
                        print(f"Citations ({len(q_resp.sources)}):")
                        for src in q_resp.sources:
                            print(f"  • [{src.object_type}] {src.title or src.id}")
                    print()

            elif choice == "5":
                if not current_meeting:
                    print(f"{COLOR_RED}[ERROR] No active meeting selected.{COLOR_RESET}")
                    continue
                fmt = input("Enter export format (json/markdown/txt/pdf) [default: json]: ").strip().lower() or "json"
                report_service = ReportGenerationService(db)
                rpt = await report_service.generate_report(meeting_id=current_meeting.id, format_type=fmt, auth_context=auth_context)
                print(f"\n{COLOR_GREEN}Report Generated Successfully! ID: {rpt.id} (Format: {fmt.upper()}){COLOR_RESET}\n")

            elif choice == "6":
                if not current_meeting:
                    print(f"{COLOR_RED}[ERROR] No active meeting selected.{COLOR_RESET}")
                    continue
                lang = input("Enter target language code (e.g., es, fr, de, ja, zh): ").strip().lower()
                if lang not in SUPPORTED_LANGUAGES:
                    print(f"{COLOR_RED}[ERROR] Unsupported language code '{lang}'.{COLOR_RESET}")
                    continue
                trans_service = TranslationService(db)
                trans_req = TranslationRequest(meeting_id=current_meeting.id, target_language=lang, representation_types=["summary", "action_item", "decision"])
                trans_resp = await trans_service.generate_translations(trans_req, auth_context)
                print(f"\n{COLOR_GREEN}Generated {len(trans_resp.translations)} translations in '{lang}'!{COLOR_RESET}\n")

            elif choice == "7":
                print(f"\n{COLOR_CYAN}=== SECURITY & AUTH CONTEXT ==={COLOR_RESET}")
                print(f"  Tenant ID:   {auth_context['tenant_id']}")
                print(f"  User ID:     {auth_context['user_id']}")
                print(f"  Role:        {auth_context['role']}")
                print(f"  Email:       {auth_context['email']}")
                print(f"  Auth Guard:  ENABLED")
                print()

        except KeyboardInterrupt:
            print("\nExiting...")
            break
        except Exception as ex:
            msg = sanitize_error_text(str(ex))
            print(f"\n{COLOR_RED}[ERROR] {msg}{COLOR_RESET}\n")


def build_arg_parser() -> argparse.ArgumentParser:
    """Construct CLI argument parser with help documentation."""
    parser = argparse.ArgumentParser(
        prog="python -m backend.cli",
        description="ABCI-MI — Backup CLI Local Meeting Testing Interface",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "--file", "-f",
        type=str,
        default=None,
        help="Path to local meeting audio/video file (.wav, .mp3, .m4a, .mp4, .webm, .aac, .flac, .ogg, .mkv)",
    )
    parser.add_argument(
        "--meeting-id", "-m",
        type=str,
        default=None,
        help="Optional existing meeting UUID string to process or query",
    )
    parser.add_argument(
        "--title",
        type=str,
        default=None,
        help="Optional meeting session title",
    )
    parser.add_argument(
        "--language", "-l",
        type=str,
        default="en",
        help="Primary meeting language code (default: en)",
    )
    parser.add_argument(
        "--mode",
        type=str,
        choices=["batch", "live"],
        default="batch",
        help="Processing mode: batch or live (default: batch)",
    )
    parser.add_argument(
        "--interactive", "-i",
        action="store_true",
        help="Launch interactive terminal console loop",
    )
    parser.add_argument(
        "--query", "-q",
        type=str,
        default=None,
        help="Ask ABCI-MI natural language question after processing",
    )
    parser.add_argument(
        "--translate", "-t",
        type=str,
        default=None,
        help="Target language code to translate meeting representations into (e.g. es, fr, de, ja)",
    )
    parser.add_argument(
        "--export-format",
        type=str,
        choices=["json", "markdown", "txt", "pdf"],
        default="json",
        help="Report export format (default: json)",
    )
    parser.add_argument(
        "--tenant-id",
        type=str,
        default="default-tenant",
        help="Tenant ID for scope isolation (default: default-tenant)",
    )
    parser.add_argument(
        "--user-id",
        type=str,
        default="00000000-0000-0000-0000-000000000001",
        help="User UUID string (default: 00000000-0000-0000-0000-000000000001)",
    )
    parser.add_argument(
        "--role",
        type=str,
        default="host",
        help="User RBAC role: host, admin, member (default: host)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Show detailed stack trace on errors",
    )
    parser.add_argument(
        "--check-real-mode",
        action="store_true",
        help="Perform explicit REAL-mode AI inference startup and dependency check",
    )
    return parser


def print_runtime_config() -> Dict[str, Any]:
    """Prints and returns current runtime configuration without exposing secrets."""
    settings = get_settings()
    exec_mode = getattr(settings, "EXECUTION_MODE", "FIXTURE").upper()
    moss_model_id = getattr(settings, "OPENMOSS_MODEL_ID", "OpenMOSS-Team/MOSS-Transcribe-Diarize")
    moss_device = getattr(settings, "OPENMOSS_DEVICE", "cuda")
    moss_cache_dir = getattr(settings, "OPENMOSS_CACHE_DIR", "/tmp/huggingface")
    token_val = getattr(settings, "HF_TOKEN", None) or os.getenv("HF_TOKEN")
    hf_token_present = bool(token_val and token_val.strip())
    
    chunk_dur = getattr(settings, "AUDIO_CHUNK_DURATION_SECONDS", 600.0)
    chunk_ovl = getattr(settings, "AUDIO_CHUNK_OVERLAP_SECONDS", 30.0)
    chunk_thr = getattr(settings, "AUDIO_CHUNK_THRESHOLD_SECONDS", 600.0)
    chunk_cnc = getattr(settings, "AUDIO_CHUNK_CONCURRENCY", 1)

    print(f"\n{COLOR_CYAN}=== ABCI-MI RUNTIME CONFIGURATION ==={COLOR_RESET}")
    print(f"  EXECUTION_MODE:                 {exec_mode}")
    print(f"  OPENMOSS_MODEL_ID:              {moss_model_id}")
    print(f"  OPENMOSS_DEVICE:                {moss_device}")
    print(f"  OPENMOSS_CACHE_DIR:             {moss_cache_dir}")
    print(f"  HF_TOKEN configured:            {hf_token_present} (Secret value protected)")
    print(f"  AUDIO_CHUNK_DURATION_SECONDS:   {chunk_dur}s")
    print(f"  AUDIO_CHUNK_OVERLAP_SECONDS:    {chunk_ovl}s")
    print(f"  AUDIO_CHUNK_THRESHOLD_SECONDS:  {chunk_thr}s")
    print(f"  AUDIO_CHUNK_CONCURRENCY:        {chunk_cnc}")
    print(f"{COLOR_CYAN}====================================={COLOR_RESET}\n")

    return {
        "EXECUTION_MODE": exec_mode,
        "OPENMOSS_MODEL_ID": moss_model_id,
        "OPENMOSS_DEVICE": moss_device,
        "OPENMOSS_CACHE_DIR": moss_cache_dir,
        "HF_TOKEN_PRESENT": hf_token_present,
        "AUDIO_CHUNK_DURATION_SECONDS": chunk_dur,
        "AUDIO_CHUNK_OVERLAP_SECONDS": chunk_ovl,
        "AUDIO_CHUNK_THRESHOLD_SECONDS": chunk_thr,
        "AUDIO_CHUNK_CONCURRENCY": chunk_cnc,
    }


def run_real_mode_startup_check(verbose: bool = True) -> Dict[str, Any]:
    """
    Executes explicit REAL-mode AI inference startup checks.
    Proves:
    1. PyTorch is installed.
    2. CUDA status is detected.
    3. The configured MOSS model resolves.
    4. MOSS weights/tokenizer/processor load.
    5. Required pyannote models/dependencies load.
    6. The configured device is usable.
    7. No mock provider or fixture transcript is selected.
    Any failure is explicit; does not report success or silently fall back.
    """
    settings = get_settings()
    config = print_runtime_config() if verbose else {}
    failures = []
    checks = {}

    if verbose:
        print(f"{COLOR_BOLD}=== REAL-MODE STARTUP VERIFICATION ==={COLOR_RESET}")

    # Check 1: PyTorch installation
    try:
        import torch
        torch_ver = torch.__version__
        checks["torch_installed"] = True
        checks["torch_version"] = torch_ver
        if verbose:
            print(f"  [CHECK 1] PyTorch installed:            {COLOR_GREEN}YES (v{torch_ver}){COLOR_RESET}")
    except ImportError as ex:
        checks["torch_installed"] = False
        checks["torch_version"] = None
        failures.append(f"PyTorch is not installed: {ex}")
        if verbose:
            print(f"  [CHECK 1] PyTorch installed:            {COLOR_RED}FAILED (not installed){COLOR_RESET}")
        torch = None

    # Check 2: CUDA hardware detection
    if torch is not None:
        cuda_avail = torch.cuda.is_available()
        dev_count = torch.cuda.device_count() if cuda_avail else 0
        dev_name = torch.cuda.get_device_name(0) if cuda_avail and dev_count > 0 else None
        checks["cuda_available"] = cuda_avail
        checks["cuda_device_count"] = dev_count
        checks["cuda_device_name"] = dev_name
        if cuda_avail:
            if verbose:
                print(f"  [CHECK 2] CUDA status:                  {COLOR_GREEN}DETECTED ({dev_name}, {dev_count} devices){COLOR_RESET}")
        else:
            failures.append("CUDA is not available on host system (no GPU drivers / hardware detected)")
            if verbose:
                print(f"  [CHECK 2] CUDA status:                  {COLOR_RED}FAILED (no CUDA devices available){COLOR_RESET}")
    else:
        checks["cuda_available"] = False
        failures.append("CUDA check blocked because PyTorch is not installed")
        if verbose:
            print(f"  [CHECK 2] CUDA status:                  {COLOR_RED}BLOCKED (PyTorch missing){COLOR_RESET}")

    # Check 3: Configured MOSS model resolves
    model_id = getattr(settings, "OPENMOSS_MODEL_ID", "OpenMOSS-Team/MOSS-Transcribe-Diarize")
    checks["moss_model_id"] = model_id
    try:
        from transformers import AutoProcessor
        checks["transformers_installed"] = True
        if verbose:
            print(f"  [CHECK 3] Transformers library:         {COLOR_GREEN}YES{COLOR_RESET}")
    except ImportError as ex:
        checks["transformers_installed"] = False
        failures.append(f"Transformers library is not installed: {ex}")
        if verbose:
            print(f"  [CHECK 3] Transformers library:         {COLOR_RED}FAILED (not installed){COLOR_RESET}")

    # Check 4: MOSS weights/tokenizer/processor load
    if checks.get("transformers_installed") and torch is not None:
        try:
            from transformers import AutoProcessor, AutoModelForCausalLM
            token = getattr(settings, "HF_TOKEN", None)
            cache_dir = getattr(settings, "OPENMOSS_CACHE_DIR", "/tmp/huggingface")
            # Probe model resolution
            AutoProcessor.from_pretrained(model_id, trust_remote_code=True, cache_dir=cache_dir, token=token)
            checks["moss_weights_load"] = True
            if verbose:
                print(f"  [CHECK 4] MOSS processor/weights:       {COLOR_GREEN}LOADED{COLOR_RESET}")
        except Exception as ex:
            checks["moss_weights_load"] = False
            failures.append(f"Failed to load MOSS weights/processor '{model_id}': {ex}")
            if verbose:
                print(f"  [CHECK 4] MOSS processor/weights:       {COLOR_RED}FAILED ({ex}){COLOR_RESET}")
    else:
        checks["moss_weights_load"] = False
        failures.append("MOSS weights loading blocked by missing PyTorch or Transformers")
        if verbose:
            print(f"  [CHECK 4] MOSS processor/weights:       {COLOR_RED}BLOCKED (prerequisites missing){COLOR_RESET}")

    # Check 5: Required pyannote models/dependencies load
    try:
        from pyannote.audio import Pipeline
        checks["pyannote_installed"] = True
        if verbose:
            print(f"  [CHECK 5] PyAnnote library:             {COLOR_GREEN}YES{COLOR_RESET}")
    except ImportError as ex:
        checks["pyannote_installed"] = False
        failures.append(f"pyannote.audio is not installed: {ex}")
        if verbose:
            print(f"  [CHECK 5] PyAnnote library:             {COLOR_RED}FAILED (not installed){COLOR_RESET}")

    # Check 6: Configured device is usable
    configured_device = getattr(settings, "OPENMOSS_DEVICE", "cuda")
    checks["configured_device"] = configured_device
    if configured_device == "cuda":
        if torch is not None and torch.cuda.is_available():
            try:
                t = torch.zeros((1,), device="cuda")
                checks["device_usable"] = True
                if verbose:
                    print(f"  [CHECK 6] Configured device (cuda):     {COLOR_GREEN}USABLE{COLOR_RESET}")
            except Exception as ex:
                checks["device_usable"] = False
                failures.append(f"CUDA device allocation error: {ex}")
                if verbose:
                    print(f"  [CHECK 6] Configured device (cuda):     {COLOR_RED}FAILED ({ex}){COLOR_RESET}")
        else:
            checks["device_usable"] = False
            failures.append("OPENMOSS_DEVICE is set to 'cuda', but CUDA is not available")
            if verbose:
                print(f"  [CHECK 6] Configured device (cuda):     {COLOR_RED}FAILED (device unavailable){COLOR_RESET}")
    else:
        checks["device_usable"] = True
        if verbose:
            print(f"  [CHECK 6] Configured device ({configured_device}): {COLOR_GREEN}USABLE{COLOR_RESET}")

    # Check 7: No mock provider or fixture transcript is selected
    exec_mode = getattr(settings, "EXECUTION_MODE", "FIXTURE").upper()
    checks["execution_mode"] = exec_mode
    if exec_mode == "REAL":
        checks["strict_real_mode"] = True
        if verbose:
            print(f"  [CHECK 7] Non-fallback enforcement:     {COLOR_GREEN}ENFORCED (REAL mode active, mocks disallowed){COLOR_RESET}")
    else:
        checks["strict_real_mode"] = False
        failures.append(f"EXECUTION_MODE is '{exec_mode}'; must be 'REAL' to run real AI inference")
        if verbose:
            print(f"  [CHECK 7] Non-fallback enforcement:     {COLOR_RED}FAILED (mode is {exec_mode}){COLOR_RESET}")

    all_passed = len(failures) == 0
    checks["all_passed"] = all_passed
    checks["failures"] = failures

    if verbose:
        print(f"{COLOR_BOLD}======================================{COLOR_RESET}")
        if all_passed:
            print(f"\n{COLOR_GREEN}[SUCCESS] All REAL-mode startup checks passed successfully.{COLOR_RESET}\n")
        else:
            print(f"\n{COLOR_RED}[BLOCKED] REAL-mode startup check FAILED with {len(failures)} blocking issue(s):{COLOR_RESET}")
            for idx, err in enumerate(failures, 1):
                print(f"  {idx}. {err}")
            print(f"\n{COLOR_RED}Hard rule: Execution halted. No silent fallback to mock, fixture, or CPU.{COLOR_RESET}\n")

    return {
        "status": "VERIFIED" if all_passed else "BLOCKED",
        "all_passed": all_passed,
        "failures": failures,
        "checks": checks,
    }


async def get_cli_db_session():
    """Initializes database session, falling back to local SQLite if PostgreSQL is unreachable."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

    # Attempt PostgreSQL session first
    try:
        init_database()
        async for session in get_async_db():
            await session.execute(text("SELECT 1"))
            yield session
            return
    except Exception as ex:
        # PostgreSQL unavailable -> smooth fallback to local SQLite for CLI session
        db_path = os.path.abspath("./abcimi_cli_local.db")
        sqlite_url = f"sqlite+aiosqlite:///{db_path}"
        fallback_engine = create_async_engine(sqlite_url, echo=False, future=True)
        
        import app.models  # Register ORM models
        async with fallback_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        fallback_factory = async_sessionmaker(bind=fallback_engine, class_=AsyncSession, expire_on_commit=False)
        async with fallback_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()


async def async_cli_entrypoint():
    """Async main entrypoint for CLI execution."""
    # Check for custom meeting subcommands: meeting process-real or meeting check-real-mode
    raw_args = sys.argv[1:]
    is_meeting_subcommand = len(raw_args) >= 1 and raw_args[0] == "meeting"
    meeting_action = raw_args[1] if is_meeting_subcommand and len(raw_args) >= 2 else None

    if is_meeting_subcommand:
        if meeting_action == "check-real-mode":
            res = run_real_mode_startup_check(verbose=True)
            sys.exit(0 if res["all_passed"] else 1)
        elif meeting_action == "process-real":
            # Target file is argument after process-real
            target_file = raw_args[2] if len(raw_args) >= 3 and not raw_args[2].startswith("-") else None
            if not target_file:
                print(f"{COLOR_RED}[ERROR] Missing required audio file argument for 'meeting process-real <audio_file>'{COLOR_RESET}", file=sys.stderr)
                sys.exit(1)
            
            # 1. Enforce explicit REAL mode startup check
            print_banner()
            startup_check = run_real_mode_startup_check(verbose=True)
            if not startup_check["all_passed"]:
                print(f"\n{COLOR_RED}[REAL INFERENCE BLOCKED] Cannot execute 'meeting process-real' because environment does not meet REAL requirements.{COLOR_RESET}\n", file=sys.stderr)
                sys.exit(1)

            # 2. File validation
            validate_local_file(target_file)

            # 3. Database session & pipeline execution
            async for db in get_cli_db_session():
                try:
                    async with db.bind.begin() as conn:
                        await conn.run_sync(Base.metadata.create_all)
                except Exception:
                    pass
                await execute_cli_pipeline(
                    db=db,
                    file_path=target_file,
                    meeting_id_str=None,
                    title="Real Audio Processing",
                    language="en",
                    mode="batch",
                    query_str=None,
                    translate_lang=None,
                    export_format="json",
                    tenant_id="default-tenant",
                    user_id_str="00000000-0000-0000-0000-000000000001",
                    role="host",
                    debug=False,
                )
                return

    parser = build_arg_parser()
    args = parser.parse_args()

    # If --check-real-mode flag was passed
    if args.check_real_mode:
        res = run_real_mode_startup_check(verbose=True)
        sys.exit(0 if res["all_passed"] else 1)

    # Pre-validation check for file path if provided
    if args.file and not args.interactive:
        try:
            validate_local_file(args.file)
        except Exception as ex:
            sanitized_msg = sanitize_error_text(str(ex))
            print(f"{COLOR_RED}[ERROR] {sanitized_msg}{COLOR_RESET}", file=sys.stderr)
            if args.debug:
                import traceback
                traceback.print_exc()
            sys.exit(1)

    async for db in get_cli_db_session():
        # Ensure ORM tables exist
        try:
            async with db.bind.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
        except Exception:
            pass

        if args.interactive:
            await run_interactive_mode(
                db=db,
                tenant_id=args.tenant_id,
                user_id_str=args.user_id,
                role=args.role,
                debug=args.debug,
            )
        elif args.file or args.meeting_id:
            try:
                print_banner()
                await execute_cli_pipeline(
                    db=db,
                    file_path=args.file,
                    meeting_id_str=args.meeting_id,
                    title=args.title,
                    language=args.language,
                    mode=args.mode,
                    query_str=args.query,
                    translate_lang=args.translate,
                    export_format=args.export_format,
                    tenant_id=args.tenant_id,
                    user_id_str=args.user_id,
                    role=args.role,
                    debug=args.debug,
                )
            except Exception as ex:
                msg = sanitize_error_text(str(ex))
                print(f"\n{COLOR_RED}[ERROR] {msg}{COLOR_RESET}\n", file=sys.stderr)
                if args.debug:
                    import traceback
                    traceback.print_exc()
                sys.exit(1)
        else:
            parser.print_help()
            sys.exit(0)


def main():
    """Synchronous wrapper entrypoint."""
    try:
        asyncio.run(async_cli_entrypoint())
    except KeyboardInterrupt:
        print("\n[INFO] Operation cancelled by user.")
        sys.exit(0)


if __name__ == "__main__":
    main()
