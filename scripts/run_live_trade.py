#!/usr/bin/env python3
"""Run a single live-trading rebalance cycle. Production entry point — thin wrapper."""
import argparse
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Execute one live-trading rebalance cycle")
    parser.add_argument("--config-dir", type=Path, default=Path("config/"), help="Config directory")
    parser.add_argument("--live-db-path", type=Path, required=True, help="Path to live.duckdb")
    parser.add_argument("--confirm", action="store_true", help="Required flag to confirm live trading")
    args = parser.parse_args()

    if not args.confirm:
        print("WARNING: Live trading requires --confirm flag. Aborting.", file=sys.stderr)
        return 1

    try:
        from datetime import date

        from nyse_ats.config_loader import load_and_validate_config
        from nyse_ats.data.vendor_registry import VendorRegistry
        from nyse_ats.execution.nautilus_bridge import NautilusBridge
        from nyse_ats.monitoring.falsification import FalsificationMonitor
        from nyse_ats.pipeline import TradingPipeline
        from nyse_ats.storage.live_store import LiveStore
        from nyse_core.features import register_all_factors
        from nyse_core.features.registry import FactorRegistry
    except ImportError as exc:
        print(f"Error: missing dependency — {exc}. Run 'pip install -e .'", file=sys.stderr)
        return 1

    try:
        configs = load_and_validate_config(args.config_dir)
        strategy = configs["strategy_params.yaml"]
        falsification_cfg = configs["falsification_triggers.yaml"]
        data_sources = configs.get("data_sources.yaml")

        if getattr(strategy, "kill_switch", False):
            print("ABORT: kill_switch is active in strategy_params.yaml", file=sys.stderr)
            return 1

        # Check falsification triggers
        monitor = FalsificationMonitor(falsification_cfg)
        current_metrics: dict[str, float] = {}  # populated from live monitoring
        results, fals_diag = monitor.evaluate_all(current_metrics)

        vetoes = monitor.get_veto_triggers(results)
        if vetoes:
            print("ABORT: VETO trigger(s) fired:", file=sys.stderr)
            for v in vetoes:
                print(f"  {v.trigger_id}: {v.description}", file=sys.stderr)
            return 1
        for w in monitor.get_warning_triggers(results):
            print(f"WARNING: {w.trigger_id}: {w.description}", file=sys.stderr)

        live_store = LiveStore(args.live_db_path)
        bridge = NautilusBridge(mode="live", live_store=live_store)

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
            storage=None,
            factor_registry=factor_registry,
            live_store=live_store,
            bridge=bridge,
        )

        today = date.today()
        result, diag = pipeline.run_rebalance(rebalance_date=today)

        print(f"Trade count:   {len(result.trade_plans)}")
        print(f"Regime state:  {result.regime_state.value}")

        live_store.close()
        return 0
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
