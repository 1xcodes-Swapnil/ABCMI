# ABCI-MI Observability, Logging & Telemetry Standard

**Document Version:** 2.0.0  
**Status:** Mandatory Engineering Standard

---

## 1. Observability Architecture

Observability in ABCI-MI provides end-to-end visibility into audio processing, ASR decoding latency, multi-agent blackboard consensus, vector search performance, and API transactions.

```
┌────────────────────────────────────────────────────────────┐
│                    FastAPI HTTP Request                    │
│           (X-Request-ID Header / UUID Injection)           │
└─────────────────────────────┬──────────────────────────────┘
                              │
┌─────────────────────────────▼──────────────────────────────┐
│                  Async Context Propagation                 │
│         (ContextVar tracks Request ID across tasks)        │
└─────────────────────────────┬──────────────────────────────┘
                              │
       ┌──────────────────────┼──────────────────────┐
       ▼                      ▼                      ▼
┌──────────────┐      ┌──────────────┐      ┌─────────────────┐
│  Structured  │      │ Health & Live│      │ Platform & ASR  │
│  JSON Logs   │      │ Diagnostics  │      │ Metric Counters │
└──────────────┘      └──────────────┘      └─────────────────┘
```

---

## 2. Structured JSON Logging Schema

All modules log via `app.core.logging.get_logger(__name__)`. Log records are emitted as structured JSON objects:

```json
{
  "timestamp": "2026-08-25T10:15:30.123456Z",
  "level": "INFO",
  "logger": "app.services.meeting_intelligence_service",
  "request_id": "c3f81e24-8a12-4c56-b789-0123456789ab",
  "module": "meeting_intelligence_service",
  "function": "synthesize_meeting_intelligence",
  "line": 142,
  "message": "ACE multi-agent intelligence synthesized successfully",
  "context": {
    "tenant_id": "enterprise-org-01",
    "meeting_id": "7b8e5c12-3a45-4e78-9012-3456789abcde",
    "decisions_count": 4,
    "action_items_count": 7,
    "synthesis_confidence": 0.94,
    "latency_ms": 320.5
  }
}
```

---

## 3. Key Performance & Telemetry Indicators

| Metric Category | Key Indicators | Target Threshold |
| :--- | :--- | :--- |
| **Acoustic & ASR** | Word Error Rate (WER), Timestamp Deviation, Overlap F1 | WER < 15%, Timestamp < 50ms, Overlap F1 > 0.65 |
| **Indic Normalization** | Mixed Code-Switching WER (Mix-WER), LID Accuracy | Mix-WER < 25%, LID Accuracy > 90% |
| **ACE Blackboard** | Hypothesis Consensus Score, Multi-Agent Resolution Latency | Confidence > 85%, Latency < 1.5s |
| **Vector Search (SKW)** | Qdrant HNSW Nearest-Neighbor Retrieval Latency | Latency < 10ms (p99) |
| **API & Database** | HTTP Status 5xx Count, Async DB Connection Pool Saturation | 5xx Rate < 0.01%, Pool Usage < 75% |
