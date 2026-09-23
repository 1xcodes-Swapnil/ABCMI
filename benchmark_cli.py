#!/usr/bin/env python3
"""
ABCI-MI Root Benchmark CLI Entry Point
Enables direct invocation from project root:
  python benchmark_cli.py list
  python benchmark_cli.py run ami --samples 5
  python benchmark_cli.py run-all
  python benchmark_cli.py report latest
"""

import os
import sys

root_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.join(root_dir, "backend")

for d in (backend_dir, root_dir):
    if d not in sys.path:
        sys.path.insert(0, d)

from app.benchmarks.cli import main

if __name__ == "__main__":
    main()
