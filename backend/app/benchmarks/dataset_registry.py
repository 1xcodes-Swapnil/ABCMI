"""
Dataset Registry for ABCI-MI benchmark evaluation.
Provides registration, lookup, metadata extraction, and capability querying.
"""

from typing import Any, Dict, List, Optional

from app.benchmarks.datasets.base import BaseDatasetAdapter
from app.benchmarks.datasets.ami import AMIDatasetAdapter
from app.benchmarks.datasets.voxconverse import VoxConverseDatasetAdapter
from app.benchmarks.datasets.dihard import DIHARDDatasetAdapter
from app.benchmarks.datasets.aishell import AISHELLDatasetAdapter
from app.benchmarks.datasets.common_voice import CommonVoiceDatasetAdapter


class DatasetRegistry:
    """Registry managing available benchmark dataset adapters."""

    def __init__(self):
        self._adapters: Dict[str, BaseDatasetAdapter] = {}
        self._register_default_adapters()

    def _register_default_adapters(self) -> None:
        """Register default standardized benchmark adapters."""
        self.register_adapter(AMIDatasetAdapter())
        self.register_adapter(VoxConverseDatasetAdapter())
        self.register_adapter(DIHARDDatasetAdapter())
        self.register_adapter(AISHELLDatasetAdapter())
        self.register_adapter(CommonVoiceDatasetAdapter())

    def register_adapter(self, adapter: BaseDatasetAdapter) -> None:
        """Register a new dataset adapter."""
        key = adapter.name.lower().replace("-", "_").replace(" ", "_")
        self._adapters[key] = adapter

    def get_adapter(self, name: str) -> Optional[BaseDatasetAdapter]:
        """Retrieve adapter by name or alias."""
        key = name.lower().replace("-", "_").replace(" ", "_")
        return self._adapters.get(key)

    def list_datasets(self) -> List[Dict[str, Any]]:
        """List summary metadata for all registered datasets."""
        result = []
        for key, adapter in sorted(self._adapters.items()):
            result.append({
                "key": key,
                "name": adapter.name,
                "version": adapter.version,
                "description": adapter.description,
                "license": adapter.license_notice,
                "expected_audio_format": adapter.expected_audio_format,
                "supported_tasks": adapter.supported_tasks,
                "requires_auth": adapter.requires_auth,
                "auth_instructions": adapter.auth_instructions,
                "recommended_sample_size": adapter.recommended_sample_size,
            })
        return result


# Global singleton instance
_GLOBAL_REGISTRY: Optional[DatasetRegistry] = None


def get_dataset_registry() -> DatasetRegistry:
    """Retrieve global DatasetRegistry singleton."""
    global _GLOBAL_REGISTRY
    if _GLOBAL_REGISTRY is None:
        _GLOBAL_REGISTRY = DatasetRegistry()
    return _GLOBAL_REGISTRY
