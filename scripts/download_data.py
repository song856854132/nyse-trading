#!/usr/bin/env python3
"""Download OHLCV / fundamental / short-interest data. Production entry point — thin wrapper."""

import argparse
import sys
from pathlib import Path


def _load_token_if_missing() -> None:
    """Populate FINMIND_API_TOKEN from ~/.config/finmind/token if unset.

    Env var wins if already set; we only read the file as a convenience so
    the operator doesn't have to `export` on every shell.
    """
    import os

    if os.environ.get("FINMIND_API_TOKEN"):
        return
    token_path = Path.home() / ".config" / "finmind" / "token"
    if token_path.is_file():
        os.environ["FINMIND_API_TOKEN"] = token_path.read_text().strip()


def _resolve_universe(config_dir: Path) -> list[str]:
    """Return the full S&P 500 universe from config/sp500_current.csv.

    NOTE: current-list-only. This introduces survivorship bias (we won't
    fetch data for tickers that were in the index earlier but have since
    been removed). Proper PiT reconstitution is tracked in the plan as
    Phase 0 deliverable (see nyse_core.universe.get_universe_at_date).
    """
    import pandas as pd

    csv_path = config_dir / "sp500_current.csv"
    if not csv_path.exists():
        raise FileNotFoundError(
            f"Universe CSV not found at {csv_path}. Generate it by scraping "
            f"https://en.wikipedia.org/wiki/List_of_S%26P_500_companies "
            f"(first table, 'Symbol' column)."
        )
    df = pd.read_csv(csv_path)
    if "symbol" not in df.columns:
        raise ValueError(f"{csv_path} missing 'symbol' column")
    return sorted(df["symbol"].dropna().astype(str).tolist())


def main() -> int:
    parser = argparse.ArgumentParser(description="Download market data via configured adapters")
    parser.add_argument("--config-dir", type=Path, default=Path("config/"), help="Config directory")
    parser.add_argument(
        "--symbols", nargs="*", default=None, help="Symbols to fetch (default: full universe)"
    )
    parser.add_argument("--start-date", required=True, help="Start date YYYY-MM-DD")
    parser.add_argument("--end-date", required=True, help="End date YYYY-MM-DD")
    parser.add_argument(
        "--source",
        choices=["finmind", "edgar", "finra", "all"],
        default="all",
        help="Data source",
    )
    parser.add_argument("--limit", type=int, default=None, help="Cap universe size (for smoke tests)")
    args = parser.parse_args()

    _load_token_if_missing()

    try:
        from datetime import date

        from nyse_ats.config_loader import load_and_validate_config
        from nyse_ats.data.vendor_registry import VendorRegistry
        from nyse_ats.storage.research_store import ResearchStore
    except ImportError as exc:
        print(f"Error: missing dependency — {exc}. Run 'pip install -e .'", file=sys.stderr)
        return 1

    try:
        configs = load_and_validate_config(args.config_dir)
        ds_cfg = configs["data_sources.yaml"]
        registry = VendorRegistry.from_config(ds_cfg)

        start = date.fromisoformat(args.start_date)
        end = date.fromisoformat(args.end_date)
        if args.symbols:
            symbols = args.symbols
        else:
            symbols = _resolve_universe(args.config_dir)
            print(
                f"Resolved universe: {len(symbols)} symbols from sp500_current.csv "
                f"(survivorship bias — see _resolve_universe docstring)",
                flush=True,
            )
        if args.limit:
            symbols = symbols[: args.limit]
            print(f"Applied --limit: {len(symbols)} symbols", flush=True)

        db_path = args.config_dir.parent / "research.duckdb"
        store = ResearchStore(db_path)
        total_rows = 0

        adapters = []
        if args.source in ("finmind", "all"):
            adapters.append(("finmind", registry.get("finmind")))
        if args.source in ("edgar", "all"):
            adapters.append(("edgar", registry.get("edgar")))
        if args.source in ("finra", "all"):
            adapters.append(("finra", registry.get("finra")))

        # Per-source writer routing. Each adapter emits a different schema:
        #   finmind → OHLCV (date, symbol, O/H/L/C, volume) → store_ohlcv
        #   edgar   → long-format XBRL facts (date, symbol, metric_name, value,
        #             filing_type, period_end) → store_fundamentals
        #   finra   → short-interest rows (not yet wired; adapter TBD)
        def _write(name: str, df):
            if name == "finmind":
                return store.store_ohlcv(df)
            if name == "edgar":
                return store.store_fundamentals(df)
            if name == "finra":
                # Placeholder: FINRA short-interest writer not yet implemented.
                # Surface a clear diagnostic instead of silently routing to the
                # wrong table.
                from nyse_core.contracts import Diagnostics

                d = Diagnostics()
                d.error(
                    f"download_data.{name}",
                    "FINRA short-interest storage not yet wired — row write skipped",
                )
                return d
            from nyse_core.contracts import Diagnostics

            d = Diagnostics()
            d.error(f"download_data.{name}", f"Unknown adapter: {name}")
            return d

        for name, adapter in adapters:
            df, diag = adapter.fetch(symbols, start, end)
            if diag.has_errors:
                errors = [m.message for m in diag.messages if m.level.value == "ERROR"]
                print(f"[{name}] fetch errors: {errors}", file=sys.stderr)
                continue
            if df.empty:
                print(f"[{name}] fetched 0 rows, nothing to store", file=sys.stderr)
                continue
            print(f"[{name}] fetched {len(df)} rows, storing...", flush=True)
            store_diag = _write(name, df)
            # Surface all store messages (warnings about dropped rows,
            # errors about write failures) so the operator sees what landed.
            for m in store_diag.messages:
                stream = sys.stderr if m.level.value in ("ERROR", "WARNING") else sys.stdout
                print(f"[{name}][store][{m.level.value}] {m.message}", file=stream)
            if store_diag.has_errors:
                print(f"[{name}] STORE FAILED — 0 rows written", file=sys.stderr)
                continue
            # Extract the actual stored count from the diag context
            stored = next(
                (m.context.get("stored", len(df)) for m in store_diag.messages if "Stored" in m.message),
                0,
            )
            total_rows += stored

        store.close()
        sym_count = len(symbols) if symbols else "full universe"
        print(f"\nSummary: {sym_count} symbols, {start} to {end}, {total_rows} rows stored")
        return 0
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
