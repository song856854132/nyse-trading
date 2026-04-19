#!/usr/bin/env python3
"""Evaluate a factor through G0-G5 gates. Production entry point — thin wrapper."""

import argparse
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Run factor through G0-G5 admission gates")
    parser.add_argument("--config-dir", type=Path, default=Path("config/"), help="Config directory")
    parser.add_argument("--db-path", type=Path, required=True, help="Path to research.duckdb")
    parser.add_argument("--factor", required=True, help="Factor name to evaluate")
    args = parser.parse_args()

    try:
        from nyse_ats.config_loader import load_and_validate_config
        from nyse_ats.storage.research_store import ResearchStore
        from nyse_core.gates import evaluate_factor_gates
    except ImportError as exc:
        print(f"Error: missing dependency — {exc}. Run 'pip install -e .'", file=sys.stderr)
        return 1

    try:
        configs = load_and_validate_config(args.config_dir)
        gates_cfg = configs["gates.yaml"]
        store = ResearchStore(args.db_path)

        # Build gate_config dict from the validated GatesConfig model
        gate_config = {}
        for gate_name in (
            "G0_coverage",
            "G1_standalone",
            "G2_redundancy",
            "G3_walk_forward",
            "G4_full_sample",
            "G5_date_align",
        ):
            gcfg = getattr(gates_cfg, gate_name)
            short_name = gate_name.split("_")[0]
            gate_config[short_name] = {
                "metric": gcfg.metric,
                "threshold": gcfg.threshold,
                "direction": gcfg.direction,
            }

        # Placeholder: factor_metrics would be loaded from store / computed
        factor_metrics: dict[str, float] = {}

        verdict, diag = evaluate_factor_gates(
            factor_metrics=factor_metrics,
            gate_config=gate_config,
        )

        print(f"Factor: {args.factor}")
        print(f"{'Gate':<6} {'Metric':<25} {'Value':>10} {'Threshold':>10} {'Result':>8}")
        print("-" * 65)
        for gate_name, passed in sorted(verdict.gate_results.items()):
            metric_val = verdict.gate_metrics.get(f"{gate_name}_value", float("nan"))
            cfg = gate_config.get(gate_name, {})
            threshold = cfg.get("threshold", float("nan"))
            status = "PASS" if passed else "FAIL"
            metric_name = cfg.get("metric", "?")
            print(f"{gate_name:<6} {metric_name:<25} {metric_val:>10.4f} {threshold:>10.4f} {status:>8}")

        print(f"\nOverall: {'PASS' if verdict.passed_all else 'FAIL'}")
        store.close()
        return 0 if verdict.passed_all else 1
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
