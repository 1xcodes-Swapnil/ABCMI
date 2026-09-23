"""
ABCI-MI Benchmark CLI Alias Module
Enables invocation via `from app.benchmarks.benchmark_cli import main` or `python -m app.benchmarks.benchmark_cli`.
"""

from app.benchmarks.cli import (
    main,
    print_dataset_list,
    run_single_dataset,
    run_all_datasets,
    show_report,
    compare_reports,
)

if __name__ == "__main__":
    main()
