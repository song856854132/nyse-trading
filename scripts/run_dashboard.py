#!/usr/bin/env python3
"""Launch monitoring dashboard. Production entry point — thin wrapper."""
import argparse
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Launch the trading monitoring dashboard")
    parser.add_argument("--config-dir", type=Path, default=Path("config/"), help="Config directory")
    parser.add_argument("--live-db-path", type=Path, default=Path("live.duckdb"), help="Path to live.duckdb")
    parser.add_argument("--port", type=int, default=8501, help="Dashboard port")
    args = parser.parse_args()

    print("Dashboard not yet implemented (EXP-2)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
