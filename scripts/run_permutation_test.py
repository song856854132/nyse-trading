#!/usr/bin/env python3
"""Run permutation test + Romano-Wolf stepdown. Production entry point — thin wrapper."""

import argparse
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Run permutation test and Romano-Wolf stepdown")
    parser.add_argument("--config-dir", type=Path, default=Path("config/"), help="Config directory")
    parser.add_argument("--db-path", type=Path, required=True, help="Path to research.duckdb")
    parser.add_argument("--n-reps", type=int, default=500, help="Number of bootstrap reps")
    parser.add_argument("--block-size", type=int, default=63, help="Block size for bootstrap")
    args = parser.parse_args()

    try:
        import pandas as pd

        from nyse_ats.config_loader import load_and_validate_config
        from nyse_ats.storage.research_store import ResearchStore
        from nyse_core.statistics import block_bootstrap_ci, permutation_test, romano_wolf_stepdown
    except ImportError as exc:
        print(f"Error: missing dependency — {exc}. Run 'pip install -e .'", file=sys.stderr)
        return 1

    try:
        load_and_validate_config(args.config_dir)
        store = ResearchStore(args.db_path)

        # Load the most recent backtest result for its daily returns
        # Placeholder: in practice, load a specific run_id
        returns = pd.Series(dtype=float)

        p_value, perm_diag = permutation_test(
            returns=returns,
            n_reps=args.n_reps,
            block_size=args.block_size,
        )
        print(f"Permutation p-value: {p_value:.4f}")

        ci, ci_diag = block_bootstrap_ci(
            returns=returns,
            n_reps=args.n_reps,
            block_size=args.block_size,
        )
        print(f"Bootstrap 95% CI:    [{ci[0]:.4f}, {ci[1]:.4f}]")

        # Romano-Wolf on factor-level returns (placeholder: single factor)
        factor_returns = {"strategy": returns}
        rw_pvalues, rw_diag = romano_wolf_stepdown(
            factor_returns=factor_returns,
            n_reps=args.n_reps,
        )
        print("Romano-Wolf adjusted p-values:")
        for name, pv in rw_pvalues.items():
            print(f"  {name}: {pv:.4f}")

        store.close()
        return 1 if p_value > 0.05 else 0
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
