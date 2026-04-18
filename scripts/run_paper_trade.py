#!/usr/bin/env python3
"""Run a single paper-trading rebalance cycle. Production entry point — thin wrapper."""
import argparse
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Execute one paper-trading rebalance cycle")
    parser.add_argument("--config-dir", type=Path, default=Path("config/"), help="Config directory")
    parser.add_argument("--db-path", type=Path, required=True, help="Path to research.duckdb")
    parser.add_argument("--live-db-path", type=Path, required=True, help="Path to live.duckdb")
    args = parser.parse_args()

    try:
        from datetime import date

        from nyse_ats.config_loader import load_and_validate_config
        from nyse_ats.data.vendor_registry import VendorRegistry
        from nyse_ats.execution.nautilus_bridge import NautilusBridge
        from nyse_ats.pipeline import TradingPipeline
        from nyse_ats.storage.live_store import LiveStore
        from nyse_ats.storage.research_store import ResearchStore
        from nyse_core.features import register_all_factors
        from nyse_core.features.registry import FactorRegistry
    except ImportError as exc:
        print(f"Error: missing dependency — {exc}. Run 'pip install -e .'", file=sys.stderr)
        return 1

    try:
        configs = load_and_validate_config(args.config_dir)
        strategy = configs["strategy_params.yaml"]
        data_sources = configs.get("data_sources.yaml")

        store = ResearchStore(args.db_path)
        live_store = LiveStore(args.live_db_path)
        bridge = NautilusBridge(mode="paper", live_store=live_store)

        # Wire data adapters from config
        adapters: dict = {}
        if data_sources is not None:
            vendor_reg = VendorRegistry.from_config(data_sources)
            adapters = {"ohlcv": vendor_reg.get("finmind")}

        # Wire factor registry with all registered factors
        factor_registry = FactorRegistry()
        register_all_factors(factor_registry)

        pipeline = TradingPipeline(
            config={"strategy_params": strategy},
            data_adapters=adapters,
            storage=store,
            factor_registry=factor_registry,
            live_store=live_store,
            bridge=bridge,
        )

        today = date.today()
        result, diag = pipeline.run_rebalance(rebalance_date=today)

        trade_count = len(result.trade_plans)
        print(f"Trade count:   {trade_count}")
        print(f"Cost estimate: ${result.cost_estimate_usd:.2f}")
        print(f"Regime state:  {result.regime_state.value}")

        if result.skipped_reason:
            print(f"Skipped:       {result.skipped_reason}")

        store.close()
        live_store.close()
        return 0
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
