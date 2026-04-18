#!/usr/bin/env python3
"""Validate stored OHLCV data quality. Production entry point — thin wrapper."""
import argparse
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Run data quality checks on stored OHLCV data")
    parser.add_argument("--config-dir", type=Path, default=Path("config/"), help="Config directory")
    parser.add_argument("--db-path", type=Path, required=True, help="Path to research.duckdb")
    args = parser.parse_args()

    try:
        from datetime import date

        from nyse_ats.monitoring.data_quality import DataQualityChecker
        from nyse_ats.storage.research_store import ResearchStore
    except ImportError as exc:
        print(f"Error: missing dependency — {exc}. Run 'pip install -e .'", file=sys.stderr)
        return 1

    try:
        store = ResearchStore(args.db_path)
        # Load all available data
        all_symbols_df, load_diag = store.load_ohlcv(
            symbols=[],
            start=date(2000, 1, 1),
            end=date(2099, 12, 31),
        )

        checker = DataQualityChecker()
        results, diag = checker.check_all(all_symbols_df)

        any_failed = False
        for r in results:
            status = "PASS" if r.passed else "FAIL"
            print(f"  [{status}] {r.check_name}: {r.details}")
            if not r.passed:
                any_failed = True

        store.close()
        return 1 if any_failed else 0
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
