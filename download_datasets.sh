#!/usr/bin/env bash
# ==============================================================================
# ABCI-MI Benchmark Dataset Downloader & Local Test Environment Setup
# Prepares and validates the 5 core datasets:
#   1. AMI Meeting Corpus (Multi-party meeting ASR & diarization)
#   2. VoxConverse (Multi-speaker conversational diarization)
#   3. AISHELL-1 (Mandarin speech recognition)
#   4. Mozilla Common Voice (Multilingual speech: en, hi, zh, ta, es)
#   5. DIHARD-III (Multi-domain acoustic diarization)
# ==============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_EXEC="${PYTHON_EXEC:-python3}"

echo "=================================================================="
echo " ABCI-MI: Benchmark Datasets Setup & Local Cache Provisioning"
echo "=================================================================="

"$PYTHON_EXEC" "$SCRIPT_DIR/backend/scripts/download_benchmark_datasets.py" "$@"

echo ""
echo "Datasets ready at: $SCRIPT_DIR/data/benchmarks/"
echo "Run benchmarks with:"
echo "  ./run_benchmarks.sh ami --samples 3"
echo "  python3 backend/cli.py benchmark run-all"
echo "=================================================================="
