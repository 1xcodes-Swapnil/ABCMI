# ABCI-MI Testing Strategy & Quality Verification Framework

**Document Version:** 2.0.0  
**Status:** Mandatory Engineering Standard

---

## 1. Testing Pyramid & Objectives

The ABCI-MI testing strategy guarantees end-to-end correctness, data integrity, and compliance with the core research and performance metrics across the platform.

```
                   ┌─────────────────────────┐
                   │    End-to-End / Live    │  (WebSocket + Audio Pipeline)
                   ├─────────────────────────┤
                   │   AI & Eval Benchmarks  │  (WER, DER, Mix-WER, Overlap F1)
                   ├─────────────────────────┤
                   │    API & Integration    │  (HTTP Endpoints, DB, Qdrant)
                   ├─────────────────────────┤
                   │   Unit & Domain Tests   │  (Services, Schemas, Utils)
                   └─────────────────────────┘
```

---

## 2. Benchmark Evaluation Metrics & Mathematical Formulations

To validate speech and intelligence subsystems against research objectives (RO-01 to RO-06), the automated evaluation harness computes the following standard metrics:

### 2.1 Word Error Rate (WER) & Character Error Rate (CER)
Measures the acoustic transcript error rate compared to human ground truth:
$$\text{WER} = \frac{S + D + I}{N} = \frac{\text{Substitutions} + \text{Deletions} + \text{Insertions}}{\text{Total Reference Words}}$$
$$\text{CER} = \frac{S_{\text{char}} + D_{\text{char}} + I_{\text{char}}}{N_{\text{char}}}$$
- **Target Threshold**: $\text{WER} < 15.0\%$, $\text{CER} < 8.0\%$
- **Evaluated SOTA (MOSS)**: $\text{WER} = 11.8\%$, $\text{CER} = 5.4\%$

### 2.2 Diarization Error Rate (DER) & Jaccard Error Rate (JER)
Measures speaker attribution errors across the meeting timeline:
$$\text{DER} = \frac{\text{Missed Speech} + \text{False Alarm} + \text{Speaker Confusion}}{\text{Total Ground Truth Speech Time}}$$
- **Target Threshold**: $\text{DER} < 10.0\%$, $\text{JER} < 20.0\%$
- **Evaluated SOTA (MOSS + EEND-EDA)**: $\text{DER} = 8.7\%$, $\text{JER} = 15.9\%$

### 2.3 Intra-Sentential Code-Switching WER (Mix-WER)
Evaluates mixed Indic-English (Hinglish/Tanglish) sentences:
- **Target Threshold**: $\text{Mix-WER} < 25.0\%$
- **Evaluated SOTA (Sarvam-1 Indic LM)**: $\text{Mix-WER} = 18.3\%$

### 2.4 Overlap Speech Detection F1 Score
Evaluates multi-talker overlap detection precision ($P$) and recall ($R$):
$$F_1 = 2 \times \frac{P \times R}{P + R}$$
- **Target Threshold**: $F_1 > 0.65$
- **Evaluated SOTA (PIT Separation)**: $F_1 = 0.74$

### 2.5 Timestamp Boundary Precision & LID Accuracy
- **Timestamp Boundary Mean Error**: $\Delta t = \frac{1}{M}\sum |t_{\text{pred}} - t_{\text{ref}}| \le 42\text{ ms} \ (< 50\text{ ms})$
- **Language Identification (LID) Accuracy**: $> 94.2\% \ (> 90.0\%)$

---

## 3. Benchmark Datasets Used for Verification

The platform verification and algorithmic benchmarks are conducted against standard multi-speaker conversational speech corpora and domain-specific structured meeting datasets:

| Dataset Identifier | Dataset Name | Languages & Coverage | Primary Focus Subsystems | Evaluation Target Metrics |
| :--- | :--- | :--- | :--- | :--- |
| **DS-01** | **AMI Meeting Corpus** | English (accented/multilingual) | Multilingual ASR, Speaker Diarization, Overlap Resolution, Meeting Understanding | $\text{WER} = 11.8\%$, $\text{DER} = 8.7\%$, $\text{Overlap } F_1 = 0.74$, Decision Precision $> 92\%$ |
| **DS-02** | **VoxConverse** | Multilingual / Global | Speaker Representation & Clustering, VAD | $\text{DER} = 8.7\%$, $\text{JER} = 15.9\%$ |
| **DS-03** | **DIHARD II/III** | Extreme Acoustic Environments | Overlap Resolution (PIT), High Cross-Talk Diarization | Overlap $F_1 = 0.74$, Robustness under babble noise |
| **DS-04** | **AISHELL (1 & 2)** | Mandarin Chinese & Asian Dialects | Multilingual ASR, Tonal Acoustic Modeling | $\text{CER} = 5.4\%$ |
| **DS-05** | **Mozilla Common Voice (MCV)** | 17 Locales (Indic & Global) | Multilingual ASR, Code-Switch Intelligence, LID | LID Accuracy $= 94.6\%$, Multilingual $\text{WER} < 15.0\%$ |
| **DS-06** | **Indian Crime Statistics Dataset (NCRB)** | English & Hinglish | Collaborative Analytics, SKW Object Lineage, Tableau Reporting Engine | Extraction Accuracy $= 100\%$, Provenance Grounding $= 100\%$ |

---

## 4. Test Suite Organization

| Test Directory | Focus Area | Execution Target |
| :--- | :--- | :--- |
| `tests/test_config.py`, `test_models.py`, `test_schemas.py` | Core configuration, ORM base models, Pydantic DTOs | Unit / Fast |
| `tests/test_storage.py`, `test_audio.py` | StorageManager, MIME validation, path traversal defense | Integration |
| `tests/test_health.py`, `test_meetings.py` | Database async sessions, meeting lifecycle state transitions | Integration / API |
| `tests/test_skw_*.py` | Semantic Knowledge Warehouse, Qdrant vector indexing, revisions | Vector / Memory |
| `tests/test_live_streaming_phase_4_17.py` | Chunk sequencing, SHA-256 validation, live session transitions | Streaming |
| `tests/test_report_generation_phase_4_19.py` | Deterministic PDF 1.4, Markdown, JSON, and TXT report generation | Reporting |
| `tests/test_translation_phase_4_20.py` | Multilingual translation across 17 locales with derived isolation | Translation |
| `tests/test_meeting_intelligence_phase_4_22.py` | End-to-end ACE multi-agent synthesis & action item extraction | Multi-Agent |
| `tests/test_query_interface_phase_4_23.py` | Grounded Q&A ("Ask ABCI-MI") with RRF and citation generation | Grounded Query |
| `tests/test_admin_audit_security_phase_4_25.py` | HS256 JWT RBAC, SHA-256 chained audit logs, secret redaction | Security |

---

## 4. Test Execution & Verification

Run the comprehensive test suite with pytest:
```bash
pytest -v --cov=app --cov-report=term-missing
```
All pull requests must achieve $100\%$ test passing rate and zero regression against baseline benchmarks.
