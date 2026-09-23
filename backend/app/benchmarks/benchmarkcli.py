"""
ABCI-MI Benchmark CLI Alias Module
Enables invocation via `from app.benchmarks.benchmarkcli import main` or `python -m app.benchmarks.benchmarkcli`.
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
