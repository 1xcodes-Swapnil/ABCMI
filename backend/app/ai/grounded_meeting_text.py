"""Gemini extraction with validated citations to actual transcript turns."""
from fastapi import HTTPException
from app.ai.gemini_text import GeminiTextProvider
import json

TYPES = ["summary", "decision", "action_item", "topic", "fact", "hypothesis"]
EXTRACTION_VERSION = "grounded-summary-v3-bounded"


def plan_text_batches(turns: list[dict], limit: int) -> list[list[dict]]:
    """Keep complete, ordered source turns within the provider's exact JSON budget."""
    if not turns or any(not t.get("segment_id") or not str(t.get("text", "")).strip() for t in turns):
        raise HTTPException(422, "Grounded extraction requires non-empty transcript turns with source identifiers")
    if len({str(t["segment_id"]) for t in turns}) != len(turns):
        raise HTTPException(422, "Grounded extraction requires unique source identifiers")
    batches, batch = [], []
    size = len(json.dumps({"turns": []}, ensure_ascii=False))
    empty_size = size
    for turn in turns:
        turn_size = len(json.dumps(turn, ensure_ascii=False))
        if empty_size + turn_size > limit:
            raise HTTPException(422, "A complete transcript turn exceeds the Gemini input limit; no text was truncated or sent")
        added = turn_size + (2 if batch else 0)
        if size + added > limit:
            batches.append(batch)
            batch, size = [], empty_size
            added = turn_size
        batch.append(turn)
        size += added
    if batch:
        batches.append(batch)
    return batches


async def extract_meeting_items(turns: list[dict]) -> tuple[list[dict], dict]:
    from app.core.config import get_settings
    batches = plan_text_batches(turns, get_settings().GEMINI_MAX_INPUT_CHARACTERS)
    if len(batches) == 1:
        return await _extract_batch(batches[0])
    items, calls = [], []
    for index, batch in enumerate(batches):
        extracted, call = await _extract_batch(batch)
        scope = {"batch_index": index, "batch_count": len(batches),
                 "source_segments": [str(t["segment_id"]) for t in batch],
                 "start_ms": batch[0]["start_ms"], "end_ms": batch[-1]["end_ms"],
                 "summary_scope": "transcript_window", "whole_meeting_summary": False}
        call = {**call, "text_window": scope}
        calls.append(call)
        for item in extracted:
            # These summaries describe only this input window, not the full meeting.
            if item["object_type"] == "summary":
                item["title"] = f"Window {index + 1}/{len(batches)}: {item['title']}"[:255]
            items.append({**item, "generation_metadata": call})
    return items, {"provider": "gemini", "model": calls[0]["model"],
                   "execution_mode": "REAL", "is_fixture": False,
                   "extraction_version": EXTRACTION_VERSION, "batch_count": len(batches),
                   "summary_scope": "transcript_windows", "whole_meeting_summary": False,
                   "elapsed_seconds": sum(c["elapsed_seconds"] for c in calls), "calls": calls}


async def _extract_batch(turns: list[dict]) -> tuple[list[dict], dict]:
    if not turns or any(not t.get("segment_id") or not str(t.get("text", "")).strip() for t in turns):
        raise HTTPException(422, "Grounded extraction requires non-empty transcript turns with source identifiers")
    sources = {str(t["segment_id"]): t for t in turns}
    schema = {"type": "OBJECT", "properties": {"items": {"type": "ARRAY", "items": {
        "type": "OBJECT", "properties": {
            "object_type": {"type": "STRING", "enum": TYPES},
            "title": {"type": "STRING"}, "content": {"type": "STRING"},
            "citations": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
                "segment_id": {"type": "STRING"}, "quote": {"type": "STRING"}},
                "required": ["segment_id", "quote"]}},
            "assignee": {"type": "STRING", "nullable": True},
            "due_date": {"type": "STRING", "nullable": True},
        }, "required": ["object_type", "title", "content", "citations"]}}}, "required": ["items"]}
    result, generation = await GeminiTextProvider().generate_json(
        "Extract meeting knowledge supported by the supplied transcript turns. Always include one concise summary of what is actually said, "
        "even if the transcript contains only greetings or an opening exchange. For such transcripts describe just that exchange. "
        "Only extract decisions actually agreed, actions explicitly assigned, and topics/facts/hypotheses actually stated. "
        "An empty category is valid; do not fill categories to meet a quota. Distinguish a hypothesis from fact. "
        "Each item must cite actual segment_id values with exact verbatim quotes. Never invent speakers, dates or confidence. "
        "Assignee and due_date must be verbatim source values or null; no inferred calendar dates. "
        "Use at most 40 concise items. All items are unverified interpretations for human review.",
        {"turns": turns}, schema)
    items = result.get("items")
    if not isinstance(items, list) or len(items) > 40:
        raise HTTPException(502, "Gemini returned an invalid meeting knowledge list")
    generation.update(extraction_version=EXTRACTION_VERSION, raw_items=items)
    if not any(isinstance(item, dict) and item.get("object_type") == "summary" for item in items):
        raise HTTPException(502, "Gemini did not generate the required grounded summary")
    normalized = []
    for item in items:
        if not isinstance(item, dict) or item.get("object_type") not in TYPES:
            raise HTTPException(502, "Gemini returned an unsupported knowledge type")
        if any(not isinstance(item.get(k), str) or not item[k].strip() for k in ("title", "content")) or len(item["title"]) > 255:
            raise HTTPException(502, "Gemini returned invalid knowledge content")
        citations = item.get("citations")
        if not isinstance(citations, list) or not citations:
            raise HTTPException(502, "Gemini knowledge has no source citations")
        cited = []
        for citation in citations:
            if not isinstance(citation, dict):
                raise HTTPException(502, "Gemini returned an invalid citation")
            source = sources.get(citation.get("segment_id"))
            quote = citation.get("quote")
            if source is None or not isinstance(quote, str) or not quote.strip() or quote not in source["text"]:
                raise HTTPException(502, "Gemini citation does not match the source transcript")
            if source not in cited:
                cited.append(source)
        cited_text = " ".join(t["text"] for t in cited)
        for field in ("assignee", "due_date"):
            value = item.get(field)
            if value is not None and (not isinstance(value, str) or not value.strip() or value not in cited_text):
                raise HTTPException(502, f"Gemini {field} is not stated in the cited source")
        normalized.append({**item, "source_segments": [str(t["segment_id"]) for t in cited],
                           "source_intervals": [{"start_ms": t["start_ms"], "end_ms": t["end_ms"]} for t in cited]})
    return normalized, generation
