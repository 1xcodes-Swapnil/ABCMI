#!/usr/bin/env bash
# ==============================================================================
# ABCI-MI Benchmark Runner Script
# Usage:
#   ./run_benchmarks.sh list
#   ./run_benchmarks.sh ami --samples 3
#   ./run_benchmarks.sh voxconverse
#   ./run_benchmarks.sh run-all
# ==============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_EXEC="${PYTHON_EXEC:-python3}"

if [ "$#" -eq 0 ]; then
    echo "Usage: $0 [command/dataset] [options]"
    echo ""
    echo "Examples:"
    echo "  $0 list                                   # List registered benchmark datasets"
    echo "  $0 ami --samples 3                        # Benchmark AMI with 3 samples"
    echo "  $0 voxconverse                            # Benchmark VoxConverse diarization"
    echo "  $0 aishell                                # Benchmark AISHELL-1 Mandarin"
    echo "  $0 common_voice --language hi             # Benchmark Common Voice Hindi"
    echo "  $0 dihard                                 # Benchmark DIHARD-III"
    echo "  $0 run-all                                # Run full benchmark suite"
    echo "  $0 report latest                          # View latest benchmark summary report"
    exit 1
fi

CMD="$1"
shift

case "$CMD" in
    list|report|compare|run-all)
        "$PYTHON_EXEC" "$SCRIPT_DIR/backend/cli.py" benchmark "$CMD" "$@"
        ;;
    ami|voxconverse|aishell|common_voice|dihard)
        "$PYTHON_EXEC" "$SCRIPT_DIR/backend/cli.py" benchmark run "$CMD" "$@"
        ;;
    *)
        "$PYTHON_EXEC" "$SCRIPT_DIR/backend/cli.py" benchmark "$CMD" "$@"
        ;;
esac
