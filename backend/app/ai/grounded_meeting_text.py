"""Gemini extraction with validated citations to actual transcript turns."""
from fastapi import HTTPException
from app.ai.gemini_text import GeminiTextProvider

TYPES = ["summary", "decision", "action_item", "topic", "fact", "hypothesis"]
EXTRACTION_VERSION = "grounded-summary-v2"


async def extract_meeting_items(turns: list[dict]) -> tuple[list[dict], dict]:
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
