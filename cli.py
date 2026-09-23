#!/usr/bin/env python3
"""
ABCI-MI Root CLI Entry Point
Enables direct invocation from the repository root:
  python cli.py [meeting_file] [options]
  python cli.py benchmark [dataset] [options]
  python -m cli [options]
"""

import os
import sys

root_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.join(root_dir, "backend")

for d in (backend_dir, root_dir):
    if d not in sys.path:
        sys.path.insert(0, d)

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "benchmark":
        sys.argv.pop(1)
        from app.benchmarks.cli import main as benchmark_main
        benchmark_main()
    else:
        from app.cli import main
        main()
