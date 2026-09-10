# ABCI-MI (Adaptive Collaborative Intelligence for Multilingual Meeting Intelligence)
## Comprehensive Technical Documentation & Architectural Decision Record (ADR)
**Author / Development History**: End-to-End System Evolution (Phase 1 through Phase 4)  
**Target Environment**: Google Cloud Run / FastAPI Full-Stack / React 18 / Polyglot Persistence  

---

# 1. Executive Summary & System Vision

The **ABCI-MI** platform is an enterprise-grade, distributed AI meeting intelligence system engineered specifically for multi-speaker, multilingual, and code-switched meeting environments. Unlike traditional monolithic transcription tools, ABCI-MI utilizes an **Adaptive Collaboration Engine (ACE)** based on an **Adaptive Blackboard Multi-Agent Architecture**.

```
+-----------------------------------------------------------------------------------+
|                            PRESENTATION & UI TIER                                 |
|  React 18 + Tailwind CSS | D3 Telemetry | Dynamic Heatmaps | 13 Live Testbenches  |
+-----------------------------------------+-----------------------------------------+
                                          |
                                          v
+-----------------------------------------------------------------------------------+
|                              FASTAPI API GATEWAY                                  |
|   JWT/RBAC Auth | Real-time Streaming Ingestion | Meeting Session Orchestrator    |
+-----------------------------------------+-----------------------------------------+
                                          |
                                          v
+-----------------------------------------------------------------------------------+
|                        ADAPTIVE BLACKBOARD EVENT BUS (ACE)                        |
|   Asynchronous Event Bus | Multi-Agent Consensus | Priority Knowledge Dispatcher  |
+----+-------------------+--------------------+--------------------+----------------+
     |                   |                    |                    |
     v                   v                    v                    v
+-----------+    +---------------+    +---------------+    +------------------------+
|  Speech   |    |    Speaker    |    |  Code-Switch  |    |  Meeting Understanding |
| ASR Engine|    |  Diarization  |    | Intelligence  |    |     & Summarization    |
|  (Whisper |    |  (Pyannote /  |    |  (Sarvam-1    |    |   (Gemini 2.5 / 3.5    |
| Large-v3) |    |  ECAPA-TDNN)  |    |   2B Indic)   |    |       Blackboard)      |
+----+------+    +-------+-------+    +-------+-------+    +-----------+------------+
     |                   |                    |                        |
     +-------------------+--------------------+------------------------+
                                          |
                                          v
+-----------------------------------------------------------------------------------+
|                     SEMANTIC KNOWLEDGE WORKSPACE (SKW)                            |
| Immutable Knowledge Objects (KOs) | Versioned Provenance | Confidence Fusion Pass |
+-----------------------------------------+-----------------------------------------+
                                          |
                                          v
+-----------------------------------------------------------------------------------+
|                           POLYGLOT PERSISTENCE LAYER                              |
|  - PostgreSQL (Supabase): Relational Metadata, Accounts, Audit Trails             |
|  - Qdrant Vector DB: 1536-dim / 768-dim Semantic Knowledge Object Indexing        |
|  - Upstash Redis: Real-time Pub/Sub, Blackboard States, Stream Buffering          |
|  - Object Storage: Raw 16kHz WAV/Media Binary Blobs                               |
+-----------------------------------------------------------------------------------+
```

---

# 2. End-to-End Phase Evolution Log

```
+------------------+     +------------------+     +------------------+     +------------------+
|     PHASE 1      |     |     PHASE 2      |     |     PHASE 3      |     |     PHASE 4      |
|  Core Foundation | --> |  AI Subsystems   | --> | Knowledge & Data | --> | Adaptation, LoRA |
|  & Gateway Init  |     |   & Diarization  |     |  Persistence RAG |     |   & Benchmarks   |
+------------------+     +------------------+     +------------------+     +------------------+
```

### Phase 1: Core Foundation & Gateway Initialization
* **Architecture Setup**: Configured modular FastAPI Python service layer and Vite React frontend on Node 20.
* **Authentication & RBAC**: Established JWT authentication with multi-role access control (`admin`, `security_officer`, `host`, `member`).
* **Session Lifecycle**: Implemented live meeting room creation, binary audio streaming endpoints, and WebSocket push communication.

### Phase 2: AI Processing Subsystems & Multi-Agent Blackboard
* **Multilingual ASR Pipeline**: Integrated `openai/whisper-large-v3` supporting 17+ languages and dialect detection.
* **Speaker Diarization Engine**: Deployed multi-stage voice activity detection (Silero VAD), ECAPA-TDNN embeddings, and Agglomerative Hierarchical Clustering (AHC).
* **Code-Switch Intelligence**: Designed the **Sarvam-1 (2B Indic LM)** integration to resolve phonetic intra-sentential transitions (e.g., Hinglish, Tanglish, Telugish).
* **Adaptive Collaboration Engine (ACE)**: Built Blackboard coordination where specialized agents asynchronously score and publish transcript segments, topic bounds, action items, and risk tags.

### Phase 3: Semantic Knowledge Workspace (SKW) & Polyglot Persistence
* **Knowledge Object Schema**: Standardized atomic Knowledge Objects (KOs) containing SHA-256 integrity hashes, confidence scores ($[0.0, 1.0]$), and parent meeting lineage.
* **Polyglot Database Tier**:
  - Relational metadata in **PostgreSQL (Supabase)**.
  - Sub-millisecond vector indexing in **Qdrant Vector DB**.
  - High-throughput pub/sub event routing in **Upstash Redis**.
* **Citation-Backed RAG Q&A**: Constructed grounded question-answering with exact timestamp and speaker turn attribution.

### Phase 4: Model Adaptation, PEFT/LoRA Fine-Tuning & Evaluation
* **Evaluation Framework**: Built automated benchmarking suite calculating Word Error Rate (WER), Character Error Rate (CER), and Diarization Error Rate (DER).
* **Dataset Ingestion Pipeline**: Created automated processors for **AISHELL-1**, **VoxConverse**, **AMI Meeting Corpus**, and **YODAS2 - Sidon**.
* **Parameter-Efficient Fine-Tuning (PEFT)**: Developed LoRA training scripts for low-VRAM Whisper adaptation and causal language modeling for Sarvam-1.

---

# 3. Comprehensive Architectural Decision Records (ADRs)

---

### ADR-001: Sliding Window & Token Context Size Strategy

#### Context
Long meeting transcriptions often span 60 to 120+ minutes, generating between 15,000 and 50,000 tokens. Processing entire meetings in a single monolithic prompt context window degrades LLM attention, causes hallucinations in action item extraction, and incurs prohibitive latency and cost.

#### Decision
We implemented a **Hierarchical Dynamic Sliding Window with Overlap**:
1. **Acoustic Windowing (ASR Tier)**:
   - Chunk Duration: $30.0\text{ seconds}$ with a $1.5\text{ second}$ sliding overlap.
   - Purpose: Prevents word clipping at chunk boundaries and resolves cross-chunk phonetic ambiguity using Dynamic Time Warping (DTW).
2. **Textual Windowing (Understanding & Summarization Tier)**:
   - Window Size: **$1,024\text{ tokens}$** with a **$128\text{ token}$ ($12.5\%$) stride/overlap**.
   - Context Preservation: Each window retains speaker ID tags and global meeting metadata in a $128\text{ token}$ prepended context header.
3. **Blackboard Memory Compression**:
   - As chunks are processed, the *Knowledge Memory Agent* compresses resolved segments into rolling episodic summaries ($256\text{ tokens}$ max), discarding raw acoustic embeddings.

#### Mathematical Justification & Trade-off Analysis
$$\text{Stride Ratio} = \frac{\text{Window Size} - \text{Overlap}}{\text{Window Size}} = \frac{1024 - 128}{1024} = 87.5\%$$
- **Latency**: $O(N)$ linear complexity with respect to meeting length rather than quadratic $O(N^2)$ self-attention cost.
- **Accuracy**: Retaining a 128-token overlap ensures cross-turn semantic coherence (such as multi-speaker Q&A or unresolved action items) is never split across arbitrary boundaries.

---

### ADR-002: Polyglot Persistence Architecture

#### Context
A modern meeting intelligence platform processes structured tabular data, unstructured high-dimensional embeddings, high-throughput streaming events, and heavy binary media files.

#### Architectural Matrix

| Storage Layer | Technology | Primary Entity Stored | Key Justification |
|---|---|---|---|
| **Relational DB** | PostgreSQL 16 (Supabase) | Users, Meetings, Permissions, Audit Logs | ACID transactions, complex joins, role-based security policies. |
| **Vector DB** | Qdrant | Knowledge Object Embeddings (1536/768-dim) | HNSW indexing, filtered cosine similarity, sub-millisecond semantic search. |
| **In-Memory Cache** | Redis 7 (Upstash) | Live audio chunks, Blackboard Agent state | Sub-millisecond latency for live WebSocket streaming and pub/sub message passing. |
| **Binary Storage** | Object Storage / Local Blob | Raw 16kHz WAV, Video tracks | High bandwidth, cost-effective storage for multi-gigabyte media. |

#### Decision
Strict separation of concerns: The relational database stores references and metadata; Qdrant handles semantic search vectors; Redis manages ephemeral streaming buffers; and raw audio remains in object storage.

---

### ADR-003: Model Selection & Indic Code-Switching Strategy

#### Context
Meetings in multilingual environments (e.g., corporate Indian tech ecosystems) exhibit frequent **code-switching** (e.g., Hinglish, Tamil-English), shifting languages mid-sentence.

```
Utterance: "Mina, conchu no nichiyoubi hima? Birthday party eppadi cheddam?"
Pipeline:
  [Acoustic Audio] 
         |
         v
  [Whisper Large-v3 ASR] -> Generates phonetically grounded raw tokens
         |
         v
  [Sarvam-1 2B Indic LM] -> Resolves code-switched transitions & normalizes grammar
         |
         v
  [Gemini Agentic Blackboard] -> Extracts action items, decisions, and structured KOs
```

#### Decision & Rationale
1. **Primary ASR (`openai/whisper-large-v3`)**:
   - Selected for superior multilingual acoustic zero-shot generalization across 17+ languages.
2. **Code-Switching Normalizer (`sarvamai/sarvam-1`)**:
   - A 2B parameter Indic language model with native BPE tokenizers tailored for Indian languages. It corrects phonetic transliterations and English loanwords before text enters downstream summarizers.
3. **High-Level Intelligence (`gemini-2.5-flash` / `gemini-3.5-flash`)**:
   - Acts as the Blackboard Synthesis engine, providing structured extraction of decisions, key takeaways, and risks with low latency.

---

### ADR-004: Speaker Diarization Distance Metric & Clustering Thresholds

#### Context
Overlapping speech, ambient room reverberation, and varying microphone distances cause high Diarization Error Rates (DER) if clustering thresholds are static.

#### Decision
1. **Embedding Extraction**: Use **ECAPA-TDNN** (512-dimensional speaker embeddings) with sliding 1.5s sub-segments.
2. **Distance Metric**: **Cosine Distance** normalized over unit hyperspheres:
   $$D_{\text{cos}}(u, v) = 1 - \frac{u \cdot v}{\|u\|_2 \|v\|_2}$$
3. **Threshold Calibration**:
   - Agglomerative Hierarchical Clustering (AHC) threshold set to **$\tau = 0.72$** (calibrated on VoxConverse and AMI corpora).
   - Overlap detection trigger: When two active speaker probabilities exceed $P(\text{speech}) > 0.65$ simultaneously, the frame is marked as multi-talker overlap.

---

# 4. Dataset Benchmarking & Fine-Tuning Specification

The platform includes adapters and automated manifest generators for 4 benchmark corpora:

```
+-----------------------------------------------------------------------------------+
|                        4-CORPUS BENCHMARKING SUITE                                |
+-----------------------+-----------------------+------------------+----------------+
|  1. AISHELL-1         |  2. VoxConverse       |  3. AMI Corpus   |  4. YODAS2     |
|  - Mandarin ASR       |  - Multi-Talker DER   |  - Meeting ASR   |  - Indic LM    |
|  - 178 Hours, 400 Spk |  - YouTube Audio/RTTM |  - IHM/MDM XML   |  - Code-Switch |
+-----------------------+-----------------------+------------------+----------------+
```

### Dataset Specifications

1. **AISHELL-1 (Mandarin Speech Recognition)**
   - *Data Profile*: 178 hours, 400 native speakers, 16kHz WAV.
   - *Target Task*: Fine-tuning Whisper Large-v3 for Mandarin Character Error Rate (CER) reduction.
   - *Processor*: `AIShellProcessor` (`backend/scripts/dataset_processor.py`).

2. **VoxConverse (Conversational Diarization)**
   - *Data Profile*: 50+ hours of multi-speaker YouTube discussions with NIST `.rttm` annotations.
   - *Target Task*: Speaker turn segmentation and Diarization Error Rate (DER) validation.
   - *Processor*: `VoxConverseProcessor` (`backend/scripts/dataset_processor.py`).

3. **AMI Meeting Corpus (Multi-Speaker Meeting Intelligence)**
   - *Data Profile*: 100 hours of synchronous meeting recordings with Individual Headset Mics (IHM) and Multiple Distant Mics (MDM).
   - *Target Task*: Overlap resolution, acoustic alignment, and multi-channel meeting summarization.
   - *Processor*: `AMIProcessor` (`backend/scripts/dataset_processor.py`).

4. **YODAS2 - Sidon (Indic Speech & Code-Switching)**
   - *Data Profile*: Large-scale YouTube audio snippets across Indic languages (Hindi, Tamil, Telugu, Bengali).
   - *Target Task*: Fine-tuning **Sarvam-1** and **Whisper** for robust Indic/Hinglish speech recognition.
   - *Processor*: `YODAS2SidonProcessor` (`backend/scripts/dataset_processor.py`).

---

# 5. Security & Threat Modeling (5 Threat Zones)

| Threat Zone | Identified Risk | Architectural Countermeasure |
|---|---|---|
| **1. Input Surfaces** | Malicious audio payloads, prompt injection via uploaded transcripts | Strict file signature validation, sanitized text decoding, plain-data tagging before LLM prompts. |
| **2. Planning & Reasoning** | System prompt bypass in agentic Blackboard consensus | Hardened system instructions, schema-enforced output validation (JSON schema validation). |
| **3. Tool Execution** | SSRF or unauthorized database query execution | Parameterized ORM queries (SQLAlchemy), strict network egress boundaries. |
| **4. Memory & State** | Cross-tenant data leakage or session tampering | Multi-tenant tenant ID isolation, owner-bound path checking (`userId == auth.uid`). |
| **5. Inter-System Comm** | API key leakage across client browsers | Zero client-side secrets; all Gemini, Supabase, and Redis keys remain server-side in `.env`. |

---

# 6. Operational & Deployment Guide

### A. Environment Configuration (`backend/.env`)
```env
# AI Models & Keys
GEMINI_API_KEY="your_gemini_api_key"
HUGGINGFACE_HUB_TOKEN="your_hf_token"
WHISPER_MODEL_NAME="openai/whisper-large-v3"
SARVAM_MODEL_PATH="sarvamai/sarvam-1"

# Polyglot Database Credentials
DATABASE_URL_ASYNC="postgresql+asyncpg://postgres:password@your-supabase-url:5432/postgres"
REDIS_URL="rediss://default:password@your-upstash-redis:6379"
QDRANT_HOST="localhost"
QDRANT_PORT=6333
```

### B. Launching Full-Stack Services
```bash
# 1. Start Python FastAPI Backend Server
cd backend
alembic upgrade head
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# 2. Start Frontend React Vite Server (In project root)
npm install
npm run dev
```

### C. Model Fine-Tuning Execution
```bash
# Process dataset into standardized manifest
python -m scripts.dataset_processor --dataset yodas2 --language hi --max_samples 5000 --output ./manifests/yodas2_hindi.jsonl

# Fine-tune Whisper with PEFT/LoRA
python -m scripts.train_whisper_sarvam --model_type whisper --train_file ./manifests/yodas2_hindi.jsonl --output_dir ./models/whisper-indic-lora --language hi --batch_size 4
```
