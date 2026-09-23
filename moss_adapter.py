"""
ABCI-MI Open-MOSS Adapter Wrapper (Root)
Re-exports OpenMOSSProvider, MOSSAdapter, and audio validation interfaces from app.ai.moss_adapter.
"""

import os
import sys

root_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.join(root_dir, "backend")

for d in (backend_dir, root_dir):
    if d not in sys.path:
        sys.path.insert(0, d)

from app.ai.moss_adapter import (
    ASRProvider,
    OpenMOSSProvider,
    MOSSAdapter,
    OpenMOSSAdapter,
    ASRSegment,
    ASRWordTimestamp,
    validate_audio,
    get_moss_adapter,
)

__all__ = [
    "ASRProvider",
    "OpenMOSSProvider",
    "MOSSAdapter",
    "OpenMOSSAdapter",
    "ASRSegment",
    "ASRWordTimestamp",
    "validate_audio",
    "get_moss_adapter",
]
