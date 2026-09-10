"""
Model Verification & Hardware Inspection Engine (Phase 4.12C)
Inspects pretrained model configurations, PyTorch/CUDA hardware availability,
and distinguishes between REAL_MODEL, FIXTURE, and MOCK execution modes in provenance tags.
"""

from typing import Any, Dict, Optional
import sys

from app.ai.multilingual_asr import MultilingualASREngine


class ModelVerificationService:
    """
    Verifies actual AI/ASR model configuration, hardware status, and execution provenance tags.
    Ensures clear separation between real model inference, fixture simulation, and mock runs.
    """

    @staticmethod
    def check_cuda_hardware() -> Dict[str, Any]:
        """
        Inspects PyTorch and CUDA GPU availability dynamically.
        Returns hardware diagnostic summary.
        """
        torch_available = "torch" in sys.modules
        if not torch_available:
            try:
                import torch
                torch_available = True
            except ImportError:
                torch_available = False

        if not torch_available:
            return {
                "torch_installed": False,
                "cuda_available": False,
                "device_count": 0,
                "device_name": None,
                "recommended_mode": "FIXTURE",
            }

        import torch  # type: ignore

        cuda_avail = torch.cuda.is_available()
        dev_count = torch.cuda.device_count() if cuda_avail else 0
        dev_name = torch.cuda.get_device_name(0) if cuda_avail and dev_count > 0 else None

        return {
            "torch_installed": True,
            "cuda_available": cuda_avail,
            "device_count": dev_count,
            "device_name": dev_name,
            "recommended_mode": "REAL_MODEL" if cuda_avail else "FIXTURE",
        }

    @staticmethod
    def verify_whisper_config() -> Dict[str, Any]:
        """
        Verifies actual pretrained Whisper model identifier and version constants.
        """
        engine = MultilingualASREngine()
        return {
            "configured_model_name": engine.PRETRAINED_MODEL_NAME,
            "configured_model_version": engine.PRETRAINED_MODEL_VERSION,
            "expected_model_name": "openai/whisper-large-v3",
            "expected_model_version": "v3-turbo",
            "model_identifier_valid": engine.PRETRAINED_MODEL_NAME == "openai/whisper-large-v3",
            "model_version_valid": engine.PRETRAINED_MODEL_VERSION == "v3-turbo",
            "supported_languages_count": len(engine.SUPPORTED_LANGUAGES),
        }

    @classmethod
    def get_execution_provenance_tag(
        cls,
        use_fixture: bool = True,
        use_mock: bool = False,
    ) -> str:
        """
        Determines the correct provenance mode tag: REAL_MODEL, FIXTURE, or MOCK.
        """
        if use_mock:
            return "MOCK"
        if use_fixture:
            return "FIXTURE"

        hw = cls.check_cuda_hardware()
        if hw["cuda_available"]:
            return "REAL_MODEL"
        return "FIXTURE"

    @classmethod
    def run_cuda_smoke_test(cls) -> Dict[str, Any]:
        """
        Optional real-inference smoke test for RTX 3060 / CUDA environments.
        Safely falls back if CUDA or PyTorch is unavailable without breaking tests.
        """
        hw = cls.check_cuda_hardware()
        whisper_cfg = cls.verify_whisper_config()

        if not hw["cuda_available"]:
            return {
                "smoke_test_executed": False,
                "mode": "FIXTURE",
                "reason": "CUDA hardware or PyTorch GPU runtime not available in sandbox container.",
                "hardware": hw,
                "whisper_config": whisper_cfg,
            }

        # If CUDA is available, attempt small PyTorch CUDA memory operation
        try:
            import torch

            x = torch.randn(10, 10, device="cuda")
            y = x @ x
            cuda_op_success = y is not None

            return {
                "smoke_test_executed": True,
                "mode": "REAL_MODEL",
                "cuda_operation_success": cuda_op_success,
                "hardware": hw,
                "whisper_config": whisper_cfg,
            }
        except Exception as e:
            return {
                "smoke_test_executed": False,
                "mode": "FIXTURE",
                "error": str(e),
                "hardware": hw,
                "whisper_config": whisper_cfg,
            }

    @staticmethod
    def verify_moss_config() -> Dict[str, Any]:
        """
        Verifies actual pretrained MOSS model identifier and configuration.
        """
        from app.core.config import get_settings
        settings = get_settings()
        model_id = getattr(settings, "OPENMOSS_MODEL_ID", "fnlp/moss-transcribe-diarize-0.9b")
        return {
            "configured_model_name": model_id,
            "expected_model_name": "fnlp/moss-transcribe-diarize-0.9b",
            "model_identifier_valid": "moss-transcribe-diarize-0.9b" in model_id,
        }

    @staticmethod
    def verify_moss_hardware_requirements() -> Dict[str, Any]:
        """
        Inspects if the hardware has sufficient RAM or VRAM to load fnlp/moss-transcribe-diarize-0.9b.
        If MOSS requires more VRAM than the current environment provides: reports MODEL_BLOCKED_INSUFFICIENT_VRAM.
        """
        import psutil
        
        gpu_threshold_gb = 4.0
        cpu_threshold_gb = 6.0

        cpu_mem = psutil.virtual_memory()
        total_cpu_ram_gb = cpu_mem.total / (1024**3)

        cuda_avail = False
        try:
            import torch
            cuda_avail = torch.cuda.is_available()
        except ImportError:
            pass

        vram_gb = 0.0
        gpu_name = None

        if cuda_avail:
            try:
                import torch
                gpu_name = torch.cuda.get_device_name(0)
                vram_bytes = torch.cuda.get_device_properties(0).total_memory
                vram_gb = vram_bytes / (1024**3)
            except Exception:
                pass

        blocked = False
        reason = None

        if cuda_avail:
            if vram_gb < gpu_threshold_gb:
                blocked = True
                reason = "MODEL_BLOCKED_INSUFFICIENT_VRAM"
        else:
            if total_cpu_ram_gb < cpu_threshold_gb:
                blocked = True
                reason = "MODEL_BLOCKED_INSUFFICIENT_RAM"

        return {
            "cuda_available": cuda_avail,
            "gpu_name": gpu_name,
            "vram_gb": vram_gb,
            "total_cpu_ram_gb": total_cpu_ram_gb,
            "sufficient_vram": vram_gb >= gpu_threshold_gb if cuda_avail else False,
            "sufficient_cpu_ram": total_cpu_ram_gb >= cpu_threshold_gb,
            "blocked": blocked,
            "status_code": reason if blocked else "HARDWARE_COMPLIANT",
            "message": f"Hardware verification: {reason if blocked else 'HARDWARE_COMPLIANT'}. RAM: {total_cpu_ram_gb:.2f}GB, VRAM: {vram_gb:.2f}GB (GPU: {gpu_name})"
        }

