#!/usr/bin/env python3
"""
Root entry point to download, prepare, and verify ABCI-MI benchmark datasets locally.
Usage:
  python download_datasets.py
  python download_datasets.py --dataset ami --samples 5
  python download_datasets.py --verify-only
  python download_datasets.py --offline
"""

import os
import sys
from pathlib import Path

# Add backend to sys.path
root_dir = Path(__file__).resolve().parent
backend_dir = root_dir / "backend"

for p in (str(backend_dir), str(root_dir)):
    if p not in sys.path:
        sys.path.insert(0, p)

from scripts.download_benchmark_datasets import main

if __name__ == "__main__":
    main()
