#!/usr/bin/env python3
"""
ABCI-MI Backend Benchmark CLI Entry Point
Enables direct invocation from backend directory:
  python benchmark_cli.py [subcommand] [options]
  python -m backend.benchmark_cli [subcommand] [options]
"""

import os
import sys

# Ensure backend directory is in sys.path
backend_dir = os.path.dirname(os.path.abspath(__file__))
workspace_dir = os.path.dirname(backend_dir)

for d in (backend_dir, workspace_dir):
    if d not in sys.path:
        sys.path.insert(0, d)

from app.benchmarks.cli import main

if __name__ == "__main__":
    main()
