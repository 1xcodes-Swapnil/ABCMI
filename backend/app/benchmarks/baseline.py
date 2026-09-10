"""
Baseline comparison engine for evaluating standard models vs ABCI-MI enhanced pipelines.
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from app.benchmarks.datasets.base import BenchmarkSample
from app.benchmarks.metrics import calculate_wer, calculate_cer, calculate_der, calculate_rtf


@dataclass
class BaselineSystem:
    """Represents a baseline ASR / Diarization model configuration."""
    model_name: str
    provider: str
    version: str = "1.0.0"
    device: str = "cpu"

    def transcribe(self, sample: BenchmarkSample) -> Dict[str, Any]:
        """
        Execute baseline transcription.
        In strict real execution, calls standard HuggingFace/Whisper if available or raises.
        """
        # Strict dependency check
        try:
            import torch  # type: ignore
            import whisper  # type: ignore
            model = whisper.load_model(self.model_name, device=self.device)
            result = model.transcribe(sample.audio_path)
            return {"transcript": result["text"]}
        except ImportError as e:
            raise RuntimeError(
                f"Real baseline execution requires whisper & torch installed. Missing: {e}"
            )


def compare_abci_vs_baseline(
    abci_results: Dict[str, Any],
    baseline_results: Dict[str, Any],
) -> Dict[str, Any]:
    """Compute performance deltas between ABCI-MI and baseline system."""
    wer_delta = None
    if abci_results.get("mean_wer") is not None and baseline_results.get("mean_wer") is not None:
        wer_delta = abci_results["mean_wer"] - baseline_results["mean_wer"]

    der_delta = None
    if abci_results.get("mean_der") is not None and baseline_results.get("mean_der") is not None:
        der_delta = abci_results["mean_der"] - baseline_results["mean_der"]

    rtf_delta = None
    if abci_results.get("mean_rtf") is not None and baseline_results.get("mean_rtf") is not None:
        rtf_delta = abci_results["mean_rtf"] - baseline_results["mean_rtf"]

    return {
        "dataset_name": abci_results.get("dataset_name"),
        "abci_model": abci_results.get("model_name"),
        "baseline_model": baseline_results.get("model_name"),
        "wer_delta": wer_delta,  # negative means ABCI-MI has lower error (better)
        "der_delta": der_delta,
        "rtf_delta": rtf_delta,
    }
