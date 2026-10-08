"""Cheap renderer/ORM checks using saved REAL evidence; no network or inference."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
os.environ.update(EXECUTION_MODE="REAL", DEBUG="false", LOG_LEVEL="CRITICAL", HF_HUB_OFFLINE="1")


def main():
    from html import escape
    from sqlalchemy import MetaData
    from app.models.knowledge_object import KnowledgeObject
    from app.services.report_generation_service import ReportGenerationService
    from app.core.exceptions import BadRequestException
    from app.main import app

    folder = ROOT / "e2e_validation/runs" / ("offline_priority_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    folder.mkdir(parents=True, exist_ok=False)
    source = ROOT / "e2e_validation/runs/translation_priority_20261005T180447Z/result.json"
    saved = json.loads(source.read_text(encoding="utf-8"))
    translations = saved["fresh_readback"]
    metadata = {"source_artifact": str(source.relative_to(ROOT)), "sha256": hashlib.sha256(source.read_bytes()).hexdigest()}
    obj = KnowledgeObject(provenance={"execution_mode": "REAL"}, knowledge_metadata=metadata)
    restored = KnowledgeObject(provenance=json.loads(json.dumps(obj.provenance)))
    checks = {"orm_metadata_serialization": restored.knowledge_metadata == metadata,
              "sqlalchemy_metadata_unshadowed": isinstance(KnowledgeObject.metadata, MetaData),
              "api_import": bool(app.routes)}
    payload = {"meeting_id": saved["meeting_id"], "report_id": "NOT AVAILABLE", "report_type": "renderer validation preview",
        "generated_at": datetime.now(timezone.utc).isoformat(), "version": 1,
        "sections": [{"title": "Saved REAL Hindi translations", "content": "\n".join(t["text"] for t in translations),
                      "verification_status": "Translation accuracy requires human review"}]}
    renderer = ReportGenerationService(None)
    html, _ = renderer._export_to_format(payload, "html")
    (folder / "saved_translation_preview.html").write_bytes(html)
    checks["unicode_text_preserved"] = all(escape(t["text"]) in html.decode("utf-8") for t in translations)
    try:
        renderer._export_to_format(payload, "pdf")
        checks["unsupported_pdf_fails_explicitly"] = False
    except BadRequestException:
        checks["unsupported_pdf_fails_explicitly"] = True
    evidence = {"run_id": folder.name, "timestamp": datetime.now(timezone.utc).isoformat(), "checks": checks,
        "status": "VERIFIED" if all(checks.values()) else "NOT VERIFIED", "source": metadata,
        "translation_ids": [t["id"] for t in translations], "database_persistence": "NOT VERIFIED",
        "report_id": "NOT AVAILABLE", "inference_executed": False, "network_calls": False,
        "limitations": "Offline renderer preview only; not an API-created or persisted report. Browser printing not verified."}
    (folder / "result.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(json.dumps({"run_id": folder.name, "status": evidence["status"], "checks": checks}, indent=2))
    if not all(checks.values()):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
