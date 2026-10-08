"""Recover metadata only from the matching real Qdrant record; never regenerate content."""
import asyncio
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
os.environ.update(EXECUTION_MODE="REAL", DEBUG="false", LOG_LEVEL="CRITICAL", HF_HUB_OFFLINE="1")


async def main():
    from sqlalchemy import select, func
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from app.infrastructure.database import init_database, close_database_connections
    from app.models.knowledge_object import KnowledgeObject
    from app.models.inference_job import InferenceJob
    from app.skw.indexing.semantic_indexer import SemanticIndexer
    folder = ROOT / "e2e_validation/runs" / ("metadata_repair_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    folder.mkdir(parents=True, exist_ok=False)
    evidence = {"run_id": folder.name, "timestamp": datetime.now(timezone.utc).isoformat(),
                "status": "NOT VERIFIED", "inference_executed": False, "records": []}
    sessions = async_sessionmaker(init_database(), expire_on_commit=False)
    try:
        indexer = SemanticIndexer()
        client = await indexer._get_client()
        async with sessions() as db:
            evidence["active_jobs"] = (await db.execute(select(func.count()).select_from(InferenceJob)
                .where(InferenceJob.status.in_(["queued", "running"])))).scalar_one()
            objects = (await db.execute(select(KnowledgeObject).where(KnowledgeObject.meeting_id ==
                uuid.UUID("2126caea-4e13-4902-a02f-12a8260db0bd"), KnowledgeObject.qdrant_point_id.is_not(None)))).scalars().all()
            for obj in objects:
                points = await client.retrieve(collection_name=indexer.collection_name, ids=[obj.qdrant_point_id], with_payload=True)
                entry = {"knowledge_id": str(obj.id), "qdrant_point_id": obj.qdrant_point_id, "status": "NOT VERIFIED"}
                evidence["records"].append(entry)
                if len(points) != 1:
                    raise RuntimeError("Saved vector record missing")
                payload = points[0].payload
                if payload.get("content") != obj.content or payload.get("version") != obj.version or payload.get("meeting_id") != str(obj.meeting_id):
                    raise RuntimeError("Vector content/version/scope differs from PostgreSQL")
                metadata = payload.get("metadata")
                if not isinstance(metadata, dict):
                    raise RuntimeError("Vector metadata is not available")
                entry["metadata"] = metadata
                entry["changed"] = obj.knowledge_metadata != metadata
                if entry["changed"]:
                    obj.knowledge_metadata = metadata
                entry["status"] = "SOURCE MATCHED"
            await db.commit()
        async with sessions() as db:
            for entry in evidence["records"]:
                row = await db.get(KnowledgeObject, uuid.UUID(entry["knowledge_id"]))
                entry["fresh_session_matches"] = row.knowledge_metadata == entry["metadata"]
                entry["status"] = "VERIFIED" if entry["fresh_session_matches"] else "NOT VERIFIED"
        if evidence["records"] and all(e["fresh_session_matches"] for e in evidence["records"]):
            evidence["status"] = "VERIFIED"
    except Exception as exc:
        evidence.update(status="BLOCKED", error_type=type(exc).__name__)
    finally:
        with (folder / "result.json").open("x", encoding="utf-8") as handle:
            json.dump(evidence, handle, indent=2, default=str)
        await close_database_connections()
    print(json.dumps({k:evidence.get(k) for k in ("run_id", "status", "active_jobs", "error_type")}, indent=2))
    if evidence["status"] != "VERIFIED":
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
