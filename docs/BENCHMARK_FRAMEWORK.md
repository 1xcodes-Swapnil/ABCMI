# ABCI-MI Real Benchmark & Evaluation Framework

## 1. Overview & Architecture

The **ABCI-MI Benchmark and Evaluation Subsystem** provides a rigorous, standardized, real-data evaluation framework for meeting speech transcription (ASR), multi-speaker diarization (DER), timestamp boundary alignment, and cross-lingual performance.

### Core Principles
1. **Strict Real Audio Evaluation**: Never uses mocks, synthetic audio generators, placeholder transcripts, or simulated metrics.
2. **NIST / LibriSpeech Protocol Compliance**: Standardized dynamic programming algorithms for Levenshtein edit distance (WER / CER), Hungarian bipartite maximum-weight matching for speaker permutation resolution (DER), and collar boundary evaluation.
3. **Failure Isolation & Explicit Error Codes**: If runtime acoustic models, audio recordings, or ground-truth annotations are missing, the framework records explicit failure codes (`DATASET_NOT_FOUND`, `INVALID_DATASET_STRUCTURE`, `MISSING_ANNOTATIONS`, `MISSING_AUDIO`, `ACCESS_REQUIRED`, `UNSUPPORTED_VERSION`) without silently fabricating scores.
4. **Reproducible Persistence**: Every run records full execution environment telemetry (CPU, GPU, RAM, OS, Python version, device) alongside per-sample metrics in SQLite database (`benchmark_results/benchmarks.db`) and structured JSON artifacts (`results.json`, `metrics.json`, `summary.md`).

---

## 2. Dataset Source-Verification Audit Matrix

Every dataset source in the ABCI-MI benchmark framework has been verified against official publishers and repositories:

| Dataset | Official Name | Official Publisher | Official Homepage / Download Source | Version | License / Access Terms | Ground Truth Format | Supported Tasks |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **AMI** | AMI Meeting Corpus | AMI Consortium / Univ. of Edinburgh / IDIAP | **Homepage**: `https://groups.inf.ed.ac.uk/ami/corpus/`<br>**Mirror**: `https://groups.inf.ed.ac.uk/ami/AMICorpusMirror/amicorpus/` | 1.6.2 | CC BY 4.0 (Public Research) | XML NXT, NIST RTTM, Word transcripts | ASR, Diarization, Alignment, Summarization |
| **VoxConverse** | VoxConverse Diarization Corpus | Visual Geometry Group (VGG), University of Oxford | **Homepage**: `https://www.robots.ox.ac.uk/~vgg/data/voxconverse/`<br>**RTTM Repo**: `https://github.com/joonson/voxconverse` | v0.0.3 | CC BY 4.0 (Public Open) | NIST RTTM format (`dev/`, `test/`) | Diarization, Alignment |
| **DIHARD** | DIHARD Speech Diarization Challenge | Linguistic Data Consortium (LDC) / ISCA SIG-ML | **Homepage**: `https://dihardchallenge.github.io/dihard3/`<br>**LDC**: LDC2020E12 (Dev), LDC2021E02 (Eval) | DIHARD-III | LDC Evaluation License Agreement (**Restricted**) | NIST RTTM + UEM maps | Diarization, Cross-talk / Overlap |
| **AISHELL** | AISHELL-1 Mandarin Speech Corpus | Beijing Shell Shell Technology Co. / OpenSLR | **Homepage**: `https://www.openslr.org/33/`<br>**Archive**: `https://www.openslr.org/resources/33/data_aishell.tgz` | AISHELL-1 (v0.8) | Apache 2.0 (Open Source) | Text transcripts (`transcript_v0.8.txt`) | Mandarin ASR, Character Alignment |
| **Common Voice** | Mozilla Common Voice | Mozilla Foundation | **Homepage**: `https://commonvoice.mozilla.org/`<br>**Portal**: `https://commonvoice.mozilla.org/datasets` | CV-Corpus-17.0 | CC0 1.0 Universal (Terms Acceptance Required) | TSV annotations (`validated.tsv`, `test.tsv`) | Multilingual ASR (17 Locales) |

---

## 3. Dataset Configuration & Environment Variables

To run benchmarks on local archives or custom disk volumes, set the following environment variables:

| Environment Variable | Description | Expected Directory Structure |
| :--- | :--- | :--- |
| `DATASET_ROOT` | Global root directory for all benchmark datasets | `$DATASET_ROOT/{ami,voxconverse,dihard,aishell,common_voice}/` |
| `AMI_DATASET_ROOT` | Override path to extracted AMI Meeting Corpus | `<root>/<meeting_id>.wav` and optional `<meeting_id>.rttm` |
| `VOXCONVERSE_DATASET_ROOT` | Override path to VoxConverse audio directory | `<root>/<sample_id>.wav` and `<sample_id>.rttm` |
| `DIHARD_DATASET_ROOT` | Path to extracted DIHARD III LDC dataset | `<root>/<sample_id>.wav` (or `data/wav/`) and `<sample_id>.rttm` (or `data/rttm/`) |
| `AISHELL_DATASET_ROOT` | Path to extracted AISHELL-1 directory | `<root>/data_aishell/transcript/aishell_transcript_v0.8.txt` and `<root>/wav/` |
| `COMMON_VOICE_DATASET_ROOT` | Path to extracted Common Voice locale archive | `<root>/<locale>/validated.tsv` and `<root>/<locale>/clips/<clip_id>.mp3` |

### Manual Ingestion & Access Guides

#### 1. DIHARD III (LDC)
1. Sign the evaluation license agreement at [DIHARD III Challenge](https://dihardchallenge.github.io/dihard3/).
2. Download LDC2020E12 (Dev) or LDC2021E02 (Eval).
3. Extract files and export:
   ```bash
   export DIHARD_DATASET_ROOT="/path/to/dihard3"
   ```

#### 2. AISHELL-1 (OpenSLR)
1. Download `data_aishell.tgz` (15 GB) from [OpenSLR Resource 33](https://www.openslr.org/33/).
2. Extract the archive: `tar -xvzf data_aishell.tgz`.
3. Set environment variable:
   ```bash
   export AISHELL_DATASET_ROOT="/path/to/data_aishell"
   ```

#### 3. Mozilla Common Voice
1. Visit [Mozilla Common Voice Datasets](https://commonvoice.mozilla.org/datasets) and accept community terms.
2. Download target language archives (e.g. `cv-corpus-17.0-2024-03-15-hi.tar.gz`).
3. Extract into `$COMMON_VOICE_DATASET_ROOT/<language_code>/`.

---

## 4. Mathematical Metric Formulations

### Word Error Rate (WER)
Calculated via Wagner-Fischer dynamic programming matrix:
$$\text{WER} = \frac{S + D + I}{N} = \frac{\text{Substitutions} + \text{Deletions} + \text{Insertions}}{\text{Reference Words}}$$

### Character Error Rate (CER)
For character-based and logographic scripts (e.g., Mandarin Chinese, Japanese):
$$\text{CER} = \frac{S_c + D_c + I_c}{N_c}$$

### Diarization Error Rate (DER)
Evaluated with optimal 1-to-1 speaker assignment via Hungarian Kuhn-Munkres bipartite matching:
$$\text{DER} = \frac{\text{Missed Speech Time} + \text{False Alarm Time} + \text{Speaker Confusion Time}}{\text{Total Reference Speech Time}}$$
Includes configurable **collar evaluation windows** (default: 250ms) around reference segment boundaries to eliminate acoustic transition artifacts.

### Real-Time Factor (RTF)
$$\text{RTF} = \frac{\text{Wall-Clock Processing Time (s)}}{\text{Audio Duration (s)}}$$
- $\text{RTF} < 1.0$: Faster than real-time (streaming capable)
- $\text{RTF} \ge 1.0$: Slower than real-time

---

## 5. CLI Usage & Commands

### 1. List Available Benchmark Datasets & Source Metadata
```bash
python3 backend/cli.py benchmark list
# or
python3 -m app.benchmarks.cli list
```

### 2. Run Benchmark on a Specific Dataset
```bash
python3 backend/cli.py benchmark run ami --samples 5 --device cpu
python3 backend/cli.py benchmark run voxconverse --samples 3
python3 backend/cli.py benchmark run aishell --samples 5 --language zh
python3 backend/cli.py benchmark run common_voice --samples 5 --language hi
```

### 3. Run Benchmark Suite across All 5 Datasets
```bash
python3 backend/cli.py benchmark run-all --samples 5
```

### 4. Resume an Interrupted Run
```bash
python3 backend/cli.py benchmark run ami --samples 20 --resume --run-id <run_id>
```

### 5. Inspect Run Reports and Summary
```bash
python3 backend/cli.py benchmark report latest
python3 backend/cli.py benchmark report <run_id>
```

### 6. Side-by-Side Run Comparison
```bash
python3 backend/cli.py benchmark compare <run_id_1> <run_id_2>
```

---

## 6. Storage Layout

All benchmark artifacts are stored in `benchmark_results/`:
```
benchmark_results/
├── benchmarks.db                # SQLite database of all historical runs & samples
├── latest/                      # Symlink or mirror of most recent run artifacts
│   ├── config.json
│   ├── results.json
│   ├── metrics.json
│   ├── summary.md
│   └── errors.json
└── runs/
    └── <run_id>/
        ├── config.json          # Hardware & execution configuration
        ├── results.json         # Complete run metadata and per-sample results
        ├── metrics.json         # Aggregated WER, CER, DER, RTF metrics
        ├── summary.md           # Markdown executive summary
        └── errors.json          # Isolated failure logs
```
