#!/usr/bin/env python3
"""Run walk-forward backtest. Production entry point — thin wrapper."""
import argparse
import json
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Run walk-forward backtest over a date range")
    parser.add_argument("--config-dir", type=Path, default=Path("config/"), help="Config directory")
    parser.add_argument("--db-path", type=Path, required=True, help="Path to research.duckdb")
    parser.add_argument("--start-date", required=True, help="Start date YYYY-MM-DD")
    parser.add_argument("--end-date", required=True, help="End date YYYY-MM-DD")
    parser.add_argument("--output", type=Path, default=Path("backtest_result.json"), help="Output JSON path")
    args = parser.parse_args()

    try:
        from datetime import date

        from nyse_ats.config_loader import load_and_validate_config
        from nyse_ats.pipeline import TradingPipeline
        from nyse_ats.storage.research_store import ResearchStore
    except ImportError as exc:
        print(f"Error: missing dependency — {exc}. Run 'pip install -e .'", file=sys.stderr)
        return 1

    try:
        configs = load_and_validate_config(args.config_dir)
        strategy = configs["strategy_params.yaml"]
        store = ResearchStore(args.db_path)

        start = date.fromisoformat(args.start_date)
        end = date.fromisoformat(args.end_date)

        pipeline = TradingPipeline(
            config={"strategy_params": strategy},
            data_adapters={},
            storage=store,
            factor_registry=None,  # loaded from storage in backtest mode
        )

        result, diag = pipeline.run_backtest(start_date=start, end_date=end)

        print(f"Sharpe:    {result.oos_sharpe:.4f}")
        print(f"CAGR:      {result.oos_cagr:.4f}")
        print(f"MaxDD:     {result.max_drawdown:.4f}")
        print(f"Turnover:  {result.annual_turnover:.2f}")
        print(f"CostDrag:  {result.cost_drag_pct:.4f}")

        out = {
            "oos_sharpe": result.oos_sharpe,
            "oos_cagr": result.oos_cagr,
            "max_drawdown": result.max_drawdown,
            "annual_turnover": result.annual_turnover,
            "cost_drag_pct": result.cost_drag_pct,
            "per_fold_sharpe": result.per_fold_sharpe,
            "per_factor_contribution": result.per_factor_contribution,
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(out, indent=2))
        print(f"\nFull result saved to {args.output}")

        store.close()
        return 0
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
