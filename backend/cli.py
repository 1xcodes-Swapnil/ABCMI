#!/usr/bin/env python3
"""
ABCI-MI CLI Wrapper Module
Enables invocation via `python -m backend.cli [args]` or `./backend/cli.py [args]`.
"""

import os
import sys

# Ensure directory paths are configured in sys.path
backend_dir = os.path.dirname(os.path.abspath(__file__))
workspace_dir = os.path.dirname(backend_dir)

for d in (backend_dir, workspace_dir):
    if d not in sys.path:
        sys.path.insert(0, d)

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "benchmark":
        # Shift sys.argv so app.benchmarks.cli parses subsequent args
        sys.argv.pop(1)
        from app.benchmarks.cli import main as benchmark_main
        benchmark_main()
    else:
        from app.cli import main
        main()

