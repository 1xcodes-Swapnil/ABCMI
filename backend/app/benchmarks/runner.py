"""
Execution runner for ABCI-MI benchmark evaluation framework.
Coordinates sample loading, real pipeline execution, metric computation, failure isolation,
and persistent result reporting.
"""

import os
import time
import uuid
from typing import Any, Dict, List, Optional

from app.benchmarks.config import BenchmarkConfig, get_benchmark_config
from app.benchmarks.dataset_registry import DatasetRegistry, get_dataset_registry
from app.benchmarks.datasets.base import BenchmarkSample
from app.benchmarks.exceptions import BenchmarkError, MissingAudioError, AccessRequiredError
from app.benchmarks.metrics import (
    calculate_cer,
    calculate_der,
    calculate_rtf,
    calculate_timestamp_boundary_error,
    calculate_wer,
)
from app.benchmarks.reporting import BenchmarkReporter
from app.benchmarks.storage import BenchmarkStorage, SampleResultRecord


class BenchmarkRunner:
    """Orchestrates end-to-end benchmark execution across real speech datasets."""

    def __init__(
        self,
        config: Optional[BenchmarkConfig] = None,
        registry: Optional[DatasetRegistry] = None,
        storage: Optional[BenchmarkStorage] = None,
    ):
        self.config = config or get_benchmark_config()
        self.registry = registry or get_dataset_registry()
        self.storage = storage or BenchmarkStorage(self.config)
        self.reporter = BenchmarkReporter()

    def _execute_real_audio_pipeline(
        self,
        sample: BenchmarkSample,
        model_name: str,
        device: str,
    ) -> Dict[str, Any]:
        """
        Execute real audio transcription and diarization on the provided audio sample.
        STRICT REQUIREMENT: Never silently fall back to mock fixtures or hardcoded strings.
        If real acoustic dependencies (Whisper / Torch / PyAnnote) are absent, raises an exception.
        """
        # 1. Verify audio file existence
        if not sample.audio_path or not os.path.exists(sample.audio_path):
            raise FileNotFoundError(
                f"Audio file for sample '{sample.sample_id}' not found at '{sample.audio_path}'"
            )

        start_time = time.perf_counter()

        # 2. Strict Real Model Execution Check
        is_open_moss = "openmoss" in model_name.lower() or "moss" in model_name.lower()
        
        has_torch = False
        try:
            import torch  # type: ignore
            has_torch = True
        except ImportError:
            pass

        if is_open_moss:
            has_transformers = False
            has_librosa = False
            try:
                import transformers
                has_transformers = True
            except ImportError:
                pass
            try:
                import librosa
                has_librosa = True
            except ImportError:
                pass
                
            if not has_torch or not has_transformers or not has_librosa:
                raise RuntimeError(
                    "Real Open-MOSS dependency missing: PyTorch, Hugging Face transformers, or librosa is not installed. "
                    "Real-data benchmark strictly forbids mock/fixture execution in REAL mode."
                )
        else:
            has_whisper = False
            try:
                import faster_whisper  # type: ignore
                has_whisper = True
            except ImportError:
                try:
                    import whisper  # type: ignore
                    has_whisper = True
                except ImportError:
                    pass
            if not has_torch or not has_whisper:
                raise RuntimeError(
                    "Real acoustic model dependency missing: PyTorch/Whisper is not installed in the Python runtime. "
                    "Real-data benchmark strictly forbids mock/fixture execution."
                )

        # 3. Perform real inference
        predicted_text = ""
        predicted_segments: List[Dict[str, Any]] = []
        predicted_turns: List[Dict[str, Any]] = []

        try:
            if is_open_moss:
                from app.ai.multilingual_asr import OpenMOSSProvider
                from app.ai.speaker_diarization import SpeakerDiarizationEngine
                import asyncio
                import uuid
                provider = OpenMOSSProvider({
                    "model_id": model_name,
                    "device": device,
                })
                sd_engine = SpeakerDiarizationEngine()
                
                # Run the async transcribe and diarization in a thread-safe helper
                import threading
                result_holder = []
                err_holder = []
                
                audio_payload = None
                try:
                    with open(sample.audio_path, "rb") as f:
                        audio_payload = f.read()
                except Exception as io_err:
                    err_holder.append(io_err)
                
                if not err_holder:
                    def run_async():
                        try:
                            l = asyncio.new_event_loop()
                            asyncio.set_event_loop(l)
                            
                            # Run MOSS
                            moss_res = l.run_until_complete(provider.transcribe(sample.audio_path))
                            
                            # Run PyAnnote Diarization (Experiment B)
                            pyannote_res = None
                            if audio_payload:
                                try:
                                    pyannote_res = l.run_until_complete(sd_engine.diarize_audio(
                                        audio_payload=audio_payload,
                                        meeting_id=uuid.uuid4(),
                                        expected_speakers=None
                                    ))
                                except Exception as sd_err:
                                    print(f"[BENCHMARK WARNING] PyAnnote diarization failed: {sd_err}")
                            
                            result_holder.append((moss_res, pyannote_res))
                            l.close()
                        except Exception as ex:
                            err_holder.append(ex)
                    t = threading.Thread(target=run_async)
                    t.start()
                    t.join()
                
                if err_holder:
                    raise err_holder[0]
                
                segments, pyannote_res = result_holder[0]
                
                predicted_text = " ".join(s.transcript for s in segments)
                for s in segments:
                    predicted_segments.append({
                        "start_time": s.start_time,
                        "end_time": s.end_time,
                        "text": s.transcript,
                        "speaker": s.speaker_id or "speaker_0",
                    })
                    predicted_turns.append({
                        "speaker": s.speaker_id or "speaker_0",
                        "start_time": s.start_time,
                        "end_time": s.end_time,
                        "duration": round(s.end_time - s.start_time, 3),
                    })
                
                # Experiment A, B, C setup
                experiment_a = {
                    "transcript": predicted_text,
                    "speaker_turns": [{
                        "speaker": s.speaker_id or "speaker_0",
                        "start_time": s.start_time,
                        "end_time": s.end_time,
                    } for s in segments]
                }
                
                experiment_b = None
                experiment_c = None
                
                if pyannote_res:
                    experiment_b = {
                        "speaker_turns": [{
                            "speaker": t.speaker_id,
                            "start_time": t.start_time,
                            "end_time": t.end_time,
                        } for t in pyannote_res.speaker_turns]
                    }
                    
                    verification_report = sd_engine.verify_moss_with_pyannote(
                        moss_segments=segments,
                        pyannote_turns=pyannote_res.speaker_turns
                    )
                    
                    experiment_c = {
                        "accuracy": verification_report["accuracy"],
                        "speaker_mapping": verification_report["speaker_mapping"],
                        "disagreements": verification_report["disagreements"],
                    }
                    
                    print("\n" + "="*50)
                    print(f"RESEARCH EXPERIMENT COMPARISON for Sample {sample.sample_id}:")
                    print(f"- Experiment A (MOSS Native Speaker Turns): {len(segments)} segments")
                    print(f"- Experiment B (PyAnnote Independent): {len(pyannote_res.speaker_turns)} segments")
                    print(f"- Experiment C (MOSS + PyAnnote Verification Accuracy): {verification_report['accuracy']*100:.2f}%")
                    if verification_report["disagreements"]:
                        print(f"  Disagreements recorded: {len(verification_report['disagreements'])}")
                        for diag in verification_report["disagreements"][:3]:
                            print(f"    * {diag['message']}")
                    print("="*50 + "\n")
            else:
                import whisper  # type: ignore
                model = whisper.load_model(model_name, device=device)
                result = model.transcribe(
                    sample.audio_path,
                    language=sample.language if sample.language != "auto" else None,
                    word_timestamps=True,
                )
                predicted_text = result.get("text", "").strip()

                for seg in result.get("segments", []):
                    s_start = float(seg.get("start", 0.0))
                    s_end = float(seg.get("end", 0.0))
                    s_text = seg.get("text", "").strip()
                    predicted_segments.append({
                        "start_time": s_start,
                        "end_time": s_end,
                        "text": s_text,
                        "speaker": "speaker_0",
                    })
                    predicted_turns.append({
                        "speaker": "speaker_0",
                        "start_time": s_start,
                        "end_time": s_end,
                        "duration": round(s_end - s_start, 3),
                    })
        except Exception as model_ex:
            raise RuntimeError(f"Real model inference failed: {model_ex}") from model_ex

        elapsed_time = time.perf_counter() - start_time

        return {
            "predicted_transcript": predicted_text,
            "predicted_turns": predicted_turns,
            "predicted_segments": predicted_segments,
            "processing_time_seconds": round(elapsed_time, 4),
            "experiment_a": experiment_a if is_open_moss else None,
            "experiment_b": experiment_b if is_open_moss else None,
            "experiment_c": experiment_c if is_open_moss else None,
        }

    def run_benchmark(
        self,
        dataset_name: str,
        samples_count: int = 5,
        language: str = "en",
        dataset_version: Optional[str] = None,
        model_name: Optional[str] = None,
        device: Optional[str] = None,
        resume: bool = False,
        run_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Execute a full benchmark run on a specified dataset.
        """
        adapter = self.registry.get_adapter(dataset_name)
        if not adapter:
            available = [d["name"] for d in self.registry.list_datasets()]
            raise ValueError(
                f"Dataset '{dataset_name}' not registered. Available datasets: {', '.join(available)}"
            )

        active_run_id = run_id or f"run_{adapter.name.lower()}_{uuid.uuid4().hex[:8]}"
        active_model = model_name or self.config.default_model
        active_device = device or self.config.default_device
        version_str = dataset_version or adapter.version

        # 1. Print terminal banner
        self.reporter.print_run_header(
            run_id=active_run_id,
            dataset_name=adapter.name,
            version=version_str,
            model_name=active_model,
            device=active_device,
        )

        # 2. Check auth requirements
        if adapter.requires_auth:
            print(f"\033[33m[NOTICE] Dataset {adapter.name} requires authorization/agreement.\033[0m")
            print(f"  {adapter.auth_instructions}\n")

        # 3. Locate or download samples
        print(f"Locating real evaluation samples for {adapter.name} (limit: {samples_count})...")
        try:
            samples = adapter.locate_or_download_samples(
                target_dir=self.config.data_cache_dir,
                max_samples=samples_count,
                language=language,
            )
        except BenchmarkError as b_err:
            print(f"\033[31m[ERROR] [{b_err.error_code}] {b_err.message}\033[0m")
            # Create failed run record in storage
            self.storage.create_run(
                run_id=active_run_id,
                dataset_name=adapter.name,
                dataset_version=version_str,
                model_name=active_model,
                provider="abci-mi",
                device=active_device,
                language=language,
                samples_requested=samples_count,
            )
            self.storage.finalize_run(
                run_id=active_run_id,
                status="FAILED",
                summary_metrics={"samples_completed": 0, "samples_failed": samples_count},
                error_summary=f"[{b_err.error_code}] {b_err.message}",
            )
            return {
                "run_id": active_run_id,
                "dataset_name": adapter.name,
                "dataset_version": version_str,
                "model_name": active_model,
                "status": "FAILED",
                "error": str(b_err),
                "error_code": b_err.error_code,
                "samples_requested": samples_count,
                "samples_completed": 0,
                "samples_failed": samples_count,
                "samples": [],
            }

        if not samples:
            raise RuntimeError(f"No benchmark samples could be loaded for dataset '{adapter.name}'.")

        # 4. Initialize storage record
        self.storage.create_run(
            run_id=active_run_id,
            dataset_name=adapter.name,
            dataset_version=version_str,
            model_name=active_model,
            provider="abci-mi",
            device=active_device,
            language=language,
            samples_requested=len(samples),
        )

        completed_sample_ids = set()
        if resume:
            completed_sample_ids = set(self.storage.get_completed_sample_ids(active_run_id))
            if completed_sample_ids:
                print(f"Resuming run {active_run_id}: skipping {len(completed_sample_ids)} already completed samples.")

        # 5. Process each sample sequentially
        sample_results: List[Dict[str, Any]] = []
        completed_count = 0
        failed_count = 0

        wer_values: List[float] = []
        cer_values: List[float] = []
        der_values: List[float] = []
        rtf_values: List[float] = []

        import os  # Ensure os is available in scope

        for idx, sample in enumerate(samples, 1):
            if resume and sample.sample_id in completed_sample_ids:
                print(f"[{idx}/{len(samples)}] Sample {sample.sample_id} already completed (resumed).")
                continue

            print(f"[{idx}/{len(samples)}] Processing sample: {sample.sample_id} ({sample.duration_seconds:.1f}s)...")

            rec = SampleResultRecord(
                run_id=active_run_id,
                sample_id=sample.sample_id,
                dataset_name=adapter.name,
                dataset_version=version_str,
                audio_path=sample.audio_path,
                language=sample.language,
                duration_seconds=sample.duration_seconds,
                model_name=active_model,
                provider="abci-mi",
                status="RUNNING",
            )

            try:
                # Execute strictly real pipeline
                pipeline_out = self._execute_real_audio_pipeline(
                    sample=sample,
                    model_name=active_model,
                    device=active_device,
                )

                rec.processing_time_seconds = pipeline_out["processing_time_seconds"]
                rec.real_time_factor = calculate_rtf(
                    rec.processing_time_seconds, sample.duration_seconds
                )
                rec.predicted_transcript = pipeline_out["predicted_transcript"]
                rec.predicted_turns = pipeline_out["predicted_turns"]

                # ASR WER / CER computation
                if sample.reference_transcript:
                    rec.ground_truth_transcript = sample.reference_transcript
                    # For Chinese Mandarin or CJK, compute CER
                    if sample.language in ("zh", "ja"):
                        cer_res = calculate_cer(sample.reference_transcript, rec.predicted_transcript)
                        rec.cer = cer_res["cer"]
                        cer_values.append(rec.cer)
                    wer_res = calculate_wer(sample.reference_transcript, rec.predicted_transcript)
                    rec.wer = wer_res["wer"]
                    wer_values.append(rec.wer)

                # Diarization DER computation
                if sample.reference_speaker_turns:
                    rec.ground_truth_turns = sample.reference_speaker_turns
                    der_res = calculate_der(
                        sample.reference_speaker_turns,
                        rec.predicted_turns,
                        collar_seconds=self.config.default_collar_seconds,
                    )
                    rec.der = der_res["der"]
                    rec.missed_speech_rate = der_res["missed_speech_rate"]
                    rec.false_alarm_rate = der_res["false_alarm_rate"]
                    rec.speaker_confusion_rate = der_res["speaker_confusion_rate"]
                    der_values.append(rec.der)

                # Alignment Boundary computation
                if sample.reference_segments and pipeline_out.get("predicted_segments"):
                    align_res = calculate_timestamp_boundary_error(
                        sample.reference_segments,
                        pipeline_out["predicted_segments"],
                    )
                    rec.mean_boundary_error_ms = align_res["mean_boundary_error_ms"]

                if rec.real_time_factor is not None:
                    rtf_values.append(rec.real_time_factor)

                rec.status = "SUCCESS"
                completed_count += 1

            except Exception as sample_ex:
                rec.status = "FAILED"
                rec.error_message = str(sample_ex)
                failed_count += 1

            # Persist individual sample
            self.storage.save_sample_result(rec)
            sample_dict = {
                "sample_id": rec.sample_id,
                "duration_seconds": rec.duration_seconds,
                "status": rec.status,
                "wer": rec.wer,
                "cer": rec.cer,
                "der": rec.der,
                "missed_speech_rate": rec.missed_speech_rate,
                "false_alarm_rate": rec.false_alarm_rate,
                "speaker_confusion_rate": rec.speaker_confusion_rate,
                "mean_boundary_error_ms": rec.mean_boundary_error_ms,
                "processing_time_seconds": rec.processing_time_seconds,
                "real_time_factor": rec.real_time_factor,
                "error_message": rec.error_message,
            }
            sample_results.append(sample_dict)
            self.reporter.print_sample_card(sample_dict)

        # 6. Aggregate results
        mean_wer = round(sum(wer_values) / len(wer_values), 6) if wer_values else None
        mean_cer = round(sum(cer_values) / len(cer_values), 6) if cer_values else None
        mean_der = round(sum(der_values) / len(der_values), 6) if der_values else None
        mean_rtf = round(sum(rtf_values) / len(rtf_values), 4) if rtf_values else None

        final_status = "SUCCESS" if failed_count == 0 else ("PARTIAL" if completed_count > 0 else "FAILED")
        error_summary = f"{failed_count} of {len(samples)} samples failed." if failed_count > 0 else None

        summary_metrics = {
            "samples_completed": completed_count,
            "samples_failed": failed_count,
            "mean_wer": mean_wer,
            "mean_cer": mean_cer,
            "mean_der": mean_der,
            "mean_rtf": mean_rtf,
        }

        # 7. Finalize storage and report artifacts
        self.storage.finalize_run(
            run_id=active_run_id,
            status=final_status,
            summary_metrics=summary_metrics,
            error_summary=error_summary,
        )

        full_run_dict = self.storage.get_run(active_run_id) or {
            "run_id": active_run_id,
            "dataset_name": adapter.name,
            "dataset_version": version_str,
            "model_name": active_model,
            "provider": "abci-mi",
            "device": active_device,
            "status": final_status,
            "samples_requested": len(samples),
            "samples_completed": completed_count,
            "samples_failed": failed_count,
            "mean_wer": mean_wer,
            "mean_cer": mean_cer,
            "mean_der": mean_der,
            "mean_rtf": mean_rtf,
            "samples": sample_results,
        }

        self.reporter.save_run_reports(full_run_dict, self.config.results_dir)
        self.reporter.print_summary_table(full_run_dict)

        return full_run_dict
