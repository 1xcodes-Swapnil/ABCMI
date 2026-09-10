"""
Reporting and comparison engine for ABCI-MI benchmark evaluation.
Generates human-readable terminal dashboards, Markdown summaries, JSON exports, and run diffs.
"""

import json
import os
from typing import Any, Dict, List, Optional

COLOR_RESET = "\033[0m"
COLOR_BOLD = "\033[1m"
COLOR_CYAN = "\033[36m"
COLOR_GREEN = "\033[32m"
COLOR_YELLOW = "\033[33m"
COLOR_RED = "\033[31m"
COLOR_MAGENTA = "\033[35m"
COLOR_BLUE = "\033[34m"


def format_pct(val: Optional[float]) -> str:
    """Format decimal fraction to percentage string or N/A."""
    if val is None:
        return "N/A"
    return f"{val * 100:.2f}%"


def format_num(val: Optional[float], decimals: int = 2) -> str:
    """Format float or return N/A."""
    if val is None:
        return "N/A"
    return f"{val:.{decimals}f}"


class BenchmarkReporter:
    """Generates formatted reports and visual dashboards."""

    @staticmethod
    def print_run_header(run_id: str, dataset_name: str, version: str, model_name: str, device: str) -> None:
        """Print benchmark execution header banner."""
        print(f"\n{COLOR_CYAN}{COLOR_BOLD}" + "=" * 80)
        print(f"  ABCI-MI REAL BENCHMARK EXECUTION — {dataset_name.upper()} ({version})")
        print("=" * 80 + f"{COLOR_RESET}")
        print(f"  {COLOR_BOLD}Run ID:{COLOR_RESET}     {run_id}")
        print(f"  {COLOR_BOLD}Model:{COLOR_RESET}      {model_name}")
        print(f"  {COLOR_BOLD}Device:{COLOR_RESET}     {device}")
        print(f"  {COLOR_BOLD}Standard:{COLOR_RESET}   NIST / LibriSpeech Protocol (Real Audio Only)")
        print(f"{COLOR_CYAN}" + "-" * 80 + f"{COLOR_RESET}\n")

    @staticmethod
    def print_sample_card(sample_dict: Dict[str, Any]) -> None:
        """Print individual sample evaluation results card."""
        s_id = sample_dict.get("sample_id")
        dur = sample_dict.get("duration_seconds", 0.0)
        status = sample_dict.get("status")
        status_color = COLOR_GREEN if status == "SUCCESS" else COLOR_RED

        print(f"{COLOR_BOLD}Sample:{COLOR_RESET} {s_id} | {COLOR_BOLD}Duration:{COLOR_RESET} {dur:.1f}s | {COLOR_BOLD}Status:{COLOR_RESET} {status_color}{status}{COLOR_RESET}")

        if status == "SUCCESS":
            if sample_dict.get("wer") is not None:
                print(f"  {COLOR_CYAN}ASR{COLOR_RESET}          WER: {COLOR_BOLD}{format_pct(sample_dict.get('wer'))}{COLOR_RESET}")
            if sample_dict.get("cer") is not None:
                print(f"  {COLOR_CYAN}ASR (CER){COLOR_RESET}    CER: {COLOR_BOLD}{format_pct(sample_dict.get('cer'))}{COLOR_RESET}")
            if sample_dict.get("der") is not None:
                print(
                    f"  {COLOR_CYAN}DIARIZATION{COLOR_RESET}  DER: {COLOR_BOLD}{format_pct(sample_dict.get('der'))}{COLOR_RESET} "
                    f"(Missed: {format_pct(sample_dict.get('missed_speech_rate'))}, "
                    f"FA: {format_pct(sample_dict.get('false_alarm_rate'))}, "
                    f"Confusion: {format_pct(sample_dict.get('speaker_confusion_rate'))})"
                )
            if sample_dict.get("mean_boundary_error_ms") is not None:
                print(f"  {COLOR_CYAN}ALIGNMENT{COLOR_RESET}    Mean Boundary Error: {format_num(sample_dict.get('mean_boundary_error_ms'))} ms")
            if sample_dict.get("real_time_factor") is not None:
                print(
                    f"  {COLOR_CYAN}PERFORMANCE{COLOR_RESET}  Time: {format_num(sample_dict.get('processing_time_seconds'))}s | "
                    f"RTF: {COLOR_BOLD}{format_num(sample_dict.get('real_time_factor'), 3)}{COLOR_RESET}"
                )
        else:
            err = sample_dict.get("error_message") or "Unknown error"
            print(f"  {COLOR_RED}Error:{COLOR_RESET} {err}")

        print()

    @staticmethod
    def print_summary_table(run_dict: Dict[str, Any]) -> None:
        """Print overall benchmark run summary table."""
        print(f"\n{COLOR_GREEN}{COLOR_BOLD}" + "=" * 80)
        print(f"  BENCHMARK RUN SUMMARY — {run_dict.get('dataset_name', '').upper()}")
        print("=" * 80 + f"{COLOR_RESET}")

        print(f"  {COLOR_BOLD}Run ID:{COLOR_RESET}             {run_dict.get('run_id')}")
        print(f"  {COLOR_BOLD}Status:{COLOR_RESET}             {run_dict.get('status')}")
        print(f"  {COLOR_BOLD}Samples Completed:{COLOR_RESET}  {run_dict.get('samples_completed', 0)} / {run_dict.get('samples_requested', 0)}")
        print(f"  {COLOR_BOLD}Samples Failed:{COLOR_RESET}     {run_dict.get('samples_failed', 0)}")
        print("-" * 80)
        print(f"  {COLOR_BOLD}Mean WER:{COLOR_RESET}           {format_pct(run_dict.get('mean_wer'))}")
        print(f"  {COLOR_BOLD}Mean CER:{COLOR_RESET}           {format_pct(run_dict.get('mean_cer'))}")
        print(f"  {COLOR_BOLD}Mean DER:{COLOR_RESET}           {format_pct(run_dict.get('mean_der'))}")
        print(f"  {COLOR_BOLD}Mean RTF:{COLOR_RESET}           {format_num(run_dict.get('mean_rtf'), 4)}")
        print(f"{COLOR_GREEN}" + "=" * 80 + f"{COLOR_RESET}\n")

    @staticmethod
    def save_run_reports(run_dict: Dict[str, Any], results_dir: str) -> None:
        """Persist markdown and JSON report files in run folder."""
        run_id = run_dict["run_id"]
        run_dir = os.path.join(results_dir, "runs", run_id)
        os.makedirs(run_dir, exist_ok=True)

        # 1. results.json
        with open(os.path.join(run_dir, "results.json"), "w", encoding="utf-8") as f:
            json.dump(run_dict, f, indent=2)

        # 2. metrics.json
        metrics_data = {
            "run_id": run_id,
            "dataset_name": run_dict.get("dataset_name"),
            "dataset_version": run_dict.get("dataset_version"),
            "mean_wer": run_dict.get("mean_wer"),
            "mean_cer": run_dict.get("mean_cer"),
            "mean_der": run_dict.get("mean_der"),
            "mean_rtf": run_dict.get("mean_rtf"),
            "samples_completed": run_dict.get("samples_completed"),
            "samples_failed": run_dict.get("samples_failed"),
        }
        with open(os.path.join(run_dir, "metrics.json"), "w", encoding="utf-8") as f:
            json.dump(metrics_data, f, indent=2)

        # 3. errors.json
        errors = [
            {"sample_id": s.get("sample_id"), "error": s.get("error_message")}
            for s in run_dict.get("samples", [])
            if s.get("status") == "FAILED"
        ]
        with open(os.path.join(run_dir, "errors.json"), "w", encoding="utf-8") as f:
            json.dump(errors, f, indent=2)

        # 4. summary.md
        md_lines = [
            f"# ABCI-MI Benchmark Report: {run_dict.get('dataset_name', '').upper()}",
            "",
            f"- **Run ID**: `{run_id}`",
            f"- **Dataset**: {run_dict.get('dataset_name')} ({run_dict.get('dataset_version')})",
            f"- **Model**: `{run_dict.get('model_name')}`",
            f"- **Provider**: `{run_dict.get('provider')}`",
            f"- **Device**: `{run_dict.get('device')}`",
            f"- **Status**: `{run_dict.get('status')}`",
            f"- **Completed At**: {run_dict.get('completed_at', 'N/A')}",
            "",
            "## Summary Metrics",
            "",
            "| Metric | Value |",
            "| :--- | :--- |",
            f"| **Mean WER** | {format_pct(run_dict.get('mean_wer'))} |",
            f"| **Mean CER** | {format_pct(run_dict.get('mean_cer'))} |",
            f"| **Mean DER** | {format_pct(run_dict.get('mean_der'))} |",
            f"| **Mean RTF** | {format_num(run_dict.get('mean_rtf'), 4)} |",
            f"| **Samples Evaluated** | {run_dict.get('samples_completed', 0)} / {run_dict.get('samples_requested', 0)} |",
            "",
            "## Sample Breakdown",
            "",
            "| Sample ID | Duration (s) | Status | WER | CER | DER | RTF | Error |",
            "| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |",
        ]

        for s in run_dict.get("samples", []):
            dur_str = f"{s.get('duration_seconds', 0.0):.1f}"
            status_str = s.get("status", "UNKNOWN")
            wer_str = format_pct(s.get("wer"))
            cer_str = format_pct(s.get("cer"))
            der_str = format_pct(s.get("der"))
            rtf_str = format_num(s.get("real_time_factor"), 3)
            err_str = (s.get("error_message") or "-").replace("|", "\\|")
            md_lines.append(
                f"| `{s.get('sample_id')}` | {dur_str} | {status_str} | {wer_str} | {cer_str} | {der_str} | {rtf_str} | {err_str} |"
            )

        with open(os.path.join(run_dir, "summary.md"), "w", encoding="utf-8") as f:
            f.write("\n".join(md_lines) + "\n")

    @staticmethod
    def compare_runs(run1: Dict[str, Any], run2: Dict[str, Any]) -> None:
        """Display side-by-side comparison between two benchmark runs."""
        print(f"\n{COLOR_CYAN}{COLOR_BOLD}" + "=" * 80)
        print(f"  ABCI-MI BENCHMARK COMPARISON MATRIX")
        print("=" * 80 + f"{COLOR_RESET}")

        print(f"{'Attribute / Metric':<30} | {'Run 1 (' + run1['run_id'][:8] + ')':<22} | {'Run 2 (' + run2['run_id'][:8] + ')':<22}")
        print("-" * 80)
        print(f"{'Dataset':<30} | {run1.get('dataset_name'):<22} | {run2.get('dataset_name'):<22}")
        print(f"{'Model / Provider':<30} | {run1.get('model_name'):<22} | {run2.get('model_name'):<22}")
        print(f"{'Status':<30} | {run1.get('status'):<22} | {run2.get('status'):<22}")
        print(f"{'Samples Completed':<30} | {str(run1.get('samples_completed')):<22} | {str(run2.get('samples_completed')):<22}")
        print("-" * 80)
        print(f"{'Mean WER':<30} | {format_pct(run1.get('mean_wer')):<22} | {format_pct(run2.get('mean_wer')):<22}")
        print(f"{'Mean CER':<30} | {format_pct(run1.get('mean_cer')):<22} | {format_pct(run2.get('mean_cer')):<22}")
        print(f"{'Mean DER':<30} | {format_pct(run1.get('mean_der')):<22} | {format_pct(run2.get('mean_der')):<22}")
        print(f"{'Mean RTF':<30} | {format_num(run1.get('mean_rtf')):<22} | {format_num(run2.get('mean_rtf')):<22}")
        print(f"{COLOR_CYAN}" + "=" * 80 + f"{COLOR_RESET}\n")
