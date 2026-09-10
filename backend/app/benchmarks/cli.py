"""
Command Line Interface for ABCI-MI Real Benchmark Evaluation.
Provides terminal-first execution, dataset inspection, multi-dataset suites, and report queries.
"""

import argparse
import json
import os
import sys
from typing import List, Optional

# Ensure paths
current_dir = os.path.dirname(os.path.abspath(__file__))
app_dir = os.path.dirname(current_dir)
backend_dir = os.path.dirname(app_dir)
workspace_dir = os.path.dirname(backend_dir)

for d in (current_dir, app_dir, backend_dir, workspace_dir):
    if d not in sys.path:
        sys.path.insert(0, d)

from app.benchmarks.config import get_benchmark_config
from app.benchmarks.dataset_registry import get_dataset_registry
from app.benchmarks.reporting import (
    COLOR_BOLD,
    COLOR_CYAN,
    COLOR_GREEN,
    COLOR_RED,
    COLOR_RESET,
    COLOR_YELLOW,
    BenchmarkReporter,
    format_num,
    format_pct,
)
from app.benchmarks.runner import BenchmarkRunner
from app.benchmarks.storage import BenchmarkStorage


def print_dataset_list():
    """Print tabular list of registered benchmark datasets and specifications."""
    registry = get_dataset_registry()
    datasets = registry.list_datasets()

    print(f"\n{COLOR_CYAN}{COLOR_BOLD}" + "=" * 90)
    print("  ABCI-MI REGISTERED REAL BENCHMARK DATASETS")
    print("=" * 90 + f"{COLOR_RESET}")

    print(f"{'Key':<15} | {'Dataset Name':<16} | {'Version':<12} | {'Tasks':<24} | {'Auth Required':<14}")
    print("-" * 90)

    for d in datasets:
        tasks_str = ", ".join(d["supported_tasks"])
        auth_str = f"{COLOR_YELLOW}YES{COLOR_RESET}" if d["requires_auth"] else f"{COLOR_GREEN}NO (Public){COLOR_RESET}"
        print(f"{d['key']:<15} | {d['name']:<16} | {d['version']:<12} | {tasks_str:<24} | {auth_str:<14}")

    print(f"{COLOR_CYAN}" + "=" * 90 + f"{COLOR_RESET}\n")


def run_single_dataset(args: argparse.Namespace) -> int:
    """Run evaluation on a single dataset."""
    runner = BenchmarkRunner()
    try:
        runner.run_benchmark(
            dataset_name=args.dataset,
            samples_count=args.samples,
            language=args.language,
            dataset_version=args.dataset_version,
            model_name=args.model,
            device=args.device,
            resume=args.resume,
            run_id=args.run_id,
        )
        return 0
    except Exception as ex:
        print(f"\n{COLOR_RED}[BENCHMARK ERROR] {ex}{COLOR_RESET}\n", file=sys.stderr)
        return 1


def run_all_datasets(args: argparse.Namespace) -> int:
    """Run evaluation sequentially across all registered datasets."""
    registry = get_dataset_registry()
    runner = BenchmarkRunner()
    datasets = registry.list_datasets()

    print(f"\n{COLOR_CYAN}{COLOR_BOLD}" + "=" * 80)
    print(f"  STARTING ABCI-MI MULTI-DATASET BENCHMARK SUITE ({len(datasets)} Datasets)")
    print("=" * 80 + f"{COLOR_RESET}\n")

    results = []
    for d in datasets:
        d_key = d["key"]
        print(f"\n{COLOR_YELLOW}>>> Processing Dataset: {d['name']} ({d['version']}) <<<{COLOR_RESET}")
        try:
            res = runner.run_benchmark(
                dataset_name=d_key,
                samples_count=args.samples,
                language="en" if d_key != "aishell" else "zh",
                model_name=args.model,
                device=args.device,
                resume=args.resume,
            )
            results.append(res)
        except Exception as ex:
            print(f"{COLOR_RED}[FAILED] Dataset {d['name']} evaluation failed: {ex}{COLOR_RESET}")
            results.append({
                "dataset_name": d["name"],
                "samples_requested": args.samples,
                "samples_completed": 0,
                "status": "FAILED",
                "mean_wer": None,
                "mean_cer": None,
                "mean_der": None,
            })

    # Consolidated Final Comparison Summary Table
    print(f"\n{COLOR_GREEN}{COLOR_BOLD}" + "=" * 80)
    print("  ABCI-MI MULTI-DATASET FINAL BENCHMARK SUMMARY")
    print("=" * 80 + f"{COLOR_RESET}")
    print(f"{'DATASET':<20} | {'SAMPLES':<10} | {'STATUS':<10} | {'WER':<10} | {'CER':<10} | {'DER':<10}")
    print("-" * 80)

    for r in results:
        d_name = r.get("dataset_name", "")
        samples_str = f"{r.get('samples_completed', 0)}/{r.get('samples_requested', 0)}"
        status_str = r.get("status", "UNKNOWN")
        wer_str = format_pct(r.get("mean_wer"))
        cer_str = format_pct(r.get("mean_cer"))
        der_str = format_pct(r.get("mean_der"))
        print(f"{d_name:<20} | {samples_str:<10} | {status_str:<10} | {wer_str:<10} | {cer_str:<10} | {der_str:<10}")

    print(f"{COLOR_GREEN}" + "=" * 80 + f"{COLOR_RESET}\n")
    return 0


def view_report(run_id: str) -> int:
    """Load and display saved report."""
    storage = BenchmarkStorage()
    config = get_benchmark_config()

    if run_id == "latest":
        latest_file = os.path.join(config.results_dir, "latest", "results.json")
        if not os.path.exists(latest_file):
            print(f"{COLOR_RED}[ERROR] No latest benchmark run found.{COLOR_RESET}")
            return 1
        with open(latest_file, "r", encoding="utf-8") as f:
            run_dict = json.load(f)
    else:
        run_dict = storage.get_run(run_id)
        if not run_dict:
            print(f"{COLOR_RED}[ERROR] Benchmark run '{run_id}' not found in database.{COLOR_RESET}")
            return 1

    BenchmarkReporter.print_summary_table(run_dict)
    summary_path = os.path.join(config.results_dir, "runs", run_dict["run_id"], "summary.md")
    if os.path.exists(summary_path):
        print(f"\n{COLOR_CYAN}--- Summary Document ({summary_path}) ---{COLOR_RESET}\n")
        with open(summary_path, "r", encoding="utf-8") as f:
            print(f.read())
    return 0


def compare_runs(run1_id: str, run2_id: str) -> int:
    """Compare two historical benchmark runs."""
    storage = BenchmarkStorage()
    run1 = storage.get_run(run1_id)
    run2 = storage.get_run(run2_id)

    if not run1:
        print(f"{COLOR_RED}[ERROR] Run '{run1_id}' not found.{COLOR_RESET}")
        return 1
    if not run2:
        print(f"{COLOR_RED}[ERROR] Run '{run2_id}' not found.{COLOR_RESET}")
        return 1

    BenchmarkReporter.compare_runs(run1, run2)
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Construct command-line argument parser."""
    parser = argparse.ArgumentParser(
        prog="python -m app.benchmarks.cli",
        description="ABCI-MI Real Benchmark & Evaluation Framework CLI",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", help="Benchmark action commands")

    # Command: list
    subparsers.add_parser("list", help="List registered benchmark datasets and specifications")

    # Command: run
    run_parser = subparsers.add_parser("run", help="Run benchmark on a specific dataset")
    run_parser.add_argument("dataset", type=str, help="Dataset name: ami, voxconverse, dihard, aishell, common_voice")
    run_parser.add_argument("--samples", "-s", type=int, default=5, help="Number of samples to evaluate (default: 5)")
    run_parser.add_argument("--language", "-l", type=str, default="en", help="Language code (default: en)")
    run_parser.add_argument("--dataset-version", type=str, default=None, help="Dataset version override")
    run_parser.add_argument("--model", "-m", type=str, default=None, help="ASR model name/identifier")
    run_parser.add_argument("--device", "-d", type=str, default="cpu", help="Device: cpu, cuda, cuda:0")
    run_parser.add_argument("--resume", "-r", action="store_true", help="Resume interrupted run, skipping completed samples")
    run_parser.add_argument("--run-id", type=str, default=None, help="Specific run ID to use or resume")
    run_parser.add_argument("--output", "-o", type=str, default=None, help="Custom output directory path")

    # Command: run-all
    run_all_parser = subparsers.add_parser("run-all", help="Run benchmarks across all registered datasets sequentially")
    run_all_parser.add_argument("--samples", "-s", type=int, default=5, help="Samples per dataset (default: 5)")
    run_all_parser.add_argument("--model", "-m", type=str, default=None, help="ASR model name/identifier")
    run_all_parser.add_argument("--device", "-d", type=str, default="cpu", help="Device: cpu, cuda")
    run_all_parser.add_argument("--resume", "-r", action="store_true", help="Resume completed samples")

    # Command: report
    report_parser = subparsers.add_parser("report", help="Display saved benchmark report")
    report_parser.add_argument("run_id", type=str, help="Run ID to display (or 'latest')")

    # Command: compare
    compare_parser = subparsers.add_parser("compare", help="Compare two benchmark runs side-by-side")
    compare_parser.add_argument("run1_id", type=str, help="First run ID")
    compare_parser.add_argument("run2_id", type=str, help="Second run ID")

    return parser


def main():
    """Main CLI entrypoint."""
    parser = build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    if args.command == "list":
        print_dataset_list()
        sys.exit(0)
    elif args.command == "run":
        sys.exit(run_single_dataset(args))
    elif args.command == "run-all":
        sys.exit(run_all_datasets(args))
    elif args.command == "report":
        sys.exit(view_report(args.run_id))
    elif args.command == "compare":
        sys.exit(compare_runs(args.run1_id, args.run2_id))
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
