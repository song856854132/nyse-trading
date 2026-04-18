"""Tests for production entry-point scripts in scripts/.

Each test verifies:
1. Argparse configuration is correct
2. Correct modules are wired together
3. Exit codes are proper (0=success, 1=failure)

All heavy operations (data fetch, storage, pipeline) are mocked.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# ── Helpers ──────────────────────────────────────────────────────────────────

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"


def _import_script(name: str):
    """Import a script module from scripts/ by filename (without .py)."""
    script_path = SCRIPTS_DIR / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, script_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ── Tests ────────────────────────────────────────────────────────────────────


class TestScriptEntryPoints:
    """Test suite for all 8 production entry-point scripts."""

    # ── download_data ────────────────────────────────────────────────────

    def test_download_data_argparse(self, monkeypatch):
        """download_data.py parses --config-dir, --start-date, --end-date, --source."""
        _import_script("download_data")
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "download_data.py",
                "--start-date",
                "2024-01-01",
                "--end-date",
                "2024-06-30",
                "--source",
                "finmind",
                "--config-dir",
                "config/",
            ],
        )

        mock_configs = {
            "data_sources.yaml": MagicMock(),
        }
        mock_store = MagicMock()
        mock_store.store_ohlcv.return_value = MagicMock(has_errors=False)
        mock_adapter = MagicMock()
        mock_adapter.fetch.return_value = (
            MagicMock(empty=False, __len__=lambda s: 100),
            MagicMock(has_errors=False),
        )
        mock_registry = MagicMock()
        mock_registry.get.return_value = mock_adapter

        mock_vendor_cls = MagicMock()
        mock_vendor_cls.from_config.return_value = mock_registry

        with patch.dict(
            "sys.modules",
            {
                "nyse_core.config_schema": MagicMock(
                    load_and_validate_config=MagicMock(return_value=mock_configs)
                ),
                "nyse_ats.data.vendor_registry": MagicMock(VendorRegistry=mock_vendor_cls),
                "nyse_ats.storage.research_store": MagicMock(
                    ResearchStore=MagicMock(return_value=mock_store)
                ),
            },
        ):
            # Re-import after patching sys.modules
            mod2 = _import_script("download_data")
            exit_code = mod2.main()

        assert exit_code == 0

    # ── validate_data ────────────────────────────────────────────────────

    def test_validate_data_returns_exit_code(self, monkeypatch):
        """validate_data.py returns 0 when all checks pass, 1 when any fail."""
        _import_script("validate_data")

        # Test: all checks pass
        monkeypatch.setattr(
            sys,
            "argv",
            ["validate_data.py", "--db-path", "test.duckdb"],
        )

        mock_store = MagicMock()
        mock_store.load_ohlcv.return_value = (MagicMock(), MagicMock(has_errors=False))

        pass_result = MagicMock(passed=True, check_name="test_check", details="OK")
        mock_checker = MagicMock()
        mock_checker.check_all.return_value = ([pass_result], MagicMock())

        with patch.dict(
            "sys.modules",
            {
                "nyse_ats.monitoring.data_quality": MagicMock(
                    DataQualityChecker=MagicMock(return_value=mock_checker)
                ),
                "nyse_ats.storage.research_store": MagicMock(
                    ResearchStore=MagicMock(return_value=mock_store)
                ),
            },
        ):
            mod2 = _import_script("validate_data")
            assert mod2.main() == 0

        # Test: one check fails
        fail_result = MagicMock(passed=False, check_name="stale_prices", details="3 symbols stale")
        mock_checker2 = MagicMock()
        mock_checker2.check_all.return_value = ([pass_result, fail_result], MagicMock())

        with patch.dict(
            "sys.modules",
            {
                "nyse_ats.monitoring.data_quality": MagicMock(
                    DataQualityChecker=MagicMock(return_value=mock_checker2)
                ),
                "nyse_ats.storage.research_store": MagicMock(
                    ResearchStore=MagicMock(return_value=mock_store)
                ),
            },
        ):
            mod3 = _import_script("validate_data")
            assert mod3.main() == 1

    # ── run_backtest ─────────────────────────────────────────────────────

    def test_run_backtest_produces_output(self, monkeypatch, tmp_path):
        """run_backtest.py writes JSON output and prints metrics."""
        output_path = tmp_path / "result.json"
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "run_backtest.py",
                "--db-path",
                "test.duckdb",
                "--start-date",
                "2020-01-01",
                "--end-date",
                "2023-12-31",
                "--output",
                str(output_path),
                "--config-dir",
                "config/",
            ],
        )

        mock_result = MagicMock(
            oos_sharpe=1.2,
            oos_cagr=0.15,
            max_drawdown=-0.18,
            annual_turnover=3.5,
            cost_drag_pct=0.8,
            per_fold_sharpe=[1.1, 1.3, 1.2],
            per_factor_contribution={"mom": 0.4, "val": 0.6},
        )
        mock_pipeline = MagicMock()
        mock_pipeline.run_backtest.return_value = (mock_result, MagicMock())

        mock_configs = {
            "strategy_params.yaml": MagicMock(),
        }

        with patch.dict(
            "sys.modules",
            {
                "nyse_core.config_schema": MagicMock(
                    load_and_validate_config=MagicMock(return_value=mock_configs)
                ),
                "nyse_ats.pipeline": MagicMock(TradingPipeline=MagicMock(return_value=mock_pipeline)),
                "nyse_ats.storage.research_store": MagicMock(ResearchStore=MagicMock()),
            },
        ):
            mod = _import_script("run_backtest")
            exit_code = mod.main()

        assert exit_code == 0
        assert output_path.exists()

    # ── run_paper_trade ──────────────────────────────────────────────────

    def test_run_paper_trade_uses_paper_mode(self, monkeypatch):
        """run_paper_trade.py creates NautilusBridge with mode='paper'."""
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "run_paper_trade.py",
                "--db-path",
                "test.duckdb",
                "--live-db-path",
                "live.duckdb",
                "--config-dir",
                "config/",
            ],
        )

        mock_result = MagicMock(
            trade_plans=[],
            cost_estimate_usd=0.0,
            regime_state=MagicMock(value="BULL"),
            skipped_reason=None,
        )
        mock_pipeline = MagicMock()
        mock_pipeline.run_rebalance.return_value = (mock_result, MagicMock())

        mock_configs = {"strategy_params.yaml": MagicMock()}
        bridge_cls = MagicMock()

        with patch.dict(
            "sys.modules",
            {
                "nyse_core.config_schema": MagicMock(
                    load_and_validate_config=MagicMock(return_value=mock_configs)
                ),
                "nyse_ats.pipeline": MagicMock(TradingPipeline=MagicMock(return_value=mock_pipeline)),
                "nyse_ats.storage.research_store": MagicMock(ResearchStore=MagicMock()),
                "nyse_ats.storage.live_store": MagicMock(LiveStore=MagicMock()),
                "nyse_ats.execution.nautilus_bridge": MagicMock(NautilusBridge=bridge_cls),
            },
        ):
            mod = _import_script("run_paper_trade")
            mod.main()

        bridge_cls.assert_called_once()
        call_kwargs = bridge_cls.call_args
        assert (
            call_kwargs[1].get("mode") == "paper"
            or call_kwargs[0][0] == "paper"
            or (len(call_kwargs.kwargs) > 0 and call_kwargs.kwargs.get("mode") == "paper")
        )

    # ── run_live_trade ───────────────────────────────────────────────────

    def test_run_live_trade_requires_confirm(self, monkeypatch):
        """run_live_trade.py returns 1 when --confirm is not passed."""
        monkeypatch.setattr(
            sys,
            "argv",
            ["run_live_trade.py", "--live-db-path", "live.duckdb"],
        )
        mod = _import_script("run_live_trade")
        assert mod.main() == 1

    def test_run_live_trade_checks_kill_switch(self, monkeypatch):
        """run_live_trade.py returns 1 when kill_switch is active."""
        monkeypatch.setattr(
            sys,
            "argv",
            ["run_live_trade.py", "--live-db-path", "live.duckdb", "--confirm", "--config-dir", "config/"],
        )

        mock_strategy = MagicMock(kill_switch=True)
        mock_configs = {
            "strategy_params.yaml": mock_strategy,
            "falsification_triggers.yaml": MagicMock(),
        }

        with patch.dict(
            "sys.modules",
            {
                "nyse_core.config_schema": MagicMock(
                    load_and_validate_config=MagicMock(return_value=mock_configs)
                ),
                "nyse_ats.execution.nautilus_bridge": MagicMock(),
                "nyse_ats.monitoring.falsification": MagicMock(),
                "nyse_ats.pipeline": MagicMock(),
                "nyse_ats.storage.live_store": MagicMock(),
            },
        ):
            mod = _import_script("run_live_trade")
            assert mod.main() == 1

    def test_run_live_trade_checks_falsification(self, monkeypatch):
        """run_live_trade.py returns 1 when a VETO falsification trigger fires."""
        monkeypatch.setattr(
            sys,
            "argv",
            ["run_live_trade.py", "--live-db-path", "live.duckdb", "--confirm", "--config-dir", "config/"],
        )

        mock_strategy = MagicMock(kill_switch=False)
        mock_configs = {
            "strategy_params.yaml": mock_strategy,
            "falsification_triggers.yaml": MagicMock(),
        }

        mock_veto = MagicMock(
            trigger_id="F1",
            description="Signal death",
            current_value=0.005,
            threshold=0.01,
        )
        mock_monitor = MagicMock()
        mock_monitor.evaluate_all.return_value = ([mock_veto], MagicMock())
        mock_monitor.get_veto_triggers.return_value = [mock_veto]

        with patch.dict(
            "sys.modules",
            {
                "nyse_core.config_schema": MagicMock(
                    load_and_validate_config=MagicMock(return_value=mock_configs)
                ),
                "nyse_ats.execution.nautilus_bridge": MagicMock(),
                "nyse_ats.monitoring.falsification": MagicMock(
                    FalsificationMonitor=MagicMock(return_value=mock_monitor)
                ),
                "nyse_ats.pipeline": MagicMock(),
                "nyse_ats.storage.live_store": MagicMock(),
            },
        ):
            mod = _import_script("run_live_trade")
            assert mod.main() == 1

    # ── evaluate_gates ───────────────────────────────────────────────────

    def test_evaluate_gates_prints_table(self, monkeypatch):
        """evaluate_gates.py prints gate-by-gate results and returns correct exit code."""
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "evaluate_gates.py",
                "--db-path",
                "test.duckdb",
                "--factor",
                "momentum_12m",
                "--config-dir",
                "config/",
            ],
        )

        mock_verdict = MagicMock(
            gate_results={"G0": True, "G1": True, "G2": False},
            gate_metrics={"G0_value": 0.85, "G1_value": 0.03, "G2_value": 0.01},
            passed_all=False,
        )

        mock_gate = MagicMock(metric="oos_sharpe", threshold=0.3, direction=">=")
        mock_gates_cfg = MagicMock()
        for attr in ("G0", "G1", "G2", "G3", "G4", "G5"):
            setattr(mock_gates_cfg, attr, mock_gate)

        mock_configs = {
            "gates.yaml": mock_gates_cfg,
        }

        with patch.dict(
            "sys.modules",
            {
                "nyse_core.config_schema": MagicMock(
                    load_and_validate_config=MagicMock(return_value=mock_configs)
                ),
                "nyse_core.gates": MagicMock(
                    evaluate_factor_gates=MagicMock(return_value=(mock_verdict, MagicMock()))
                ),
                "nyse_ats.storage.research_store": MagicMock(ResearchStore=MagicMock()),
            },
        ):
            mod = _import_script("evaluate_gates")
            exit_code = mod.main()

        # Factor failed G2 so overall passed_all=False -> exit code 1
        assert exit_code == 1

    # ── run_dashboard ────────────────────────────────────────────────────

    def test_run_dashboard_placeholder(self, monkeypatch, capsys):
        """run_dashboard.py prints placeholder message and exits 0."""
        monkeypatch.setattr(
            sys,
            "argv",
            ["run_dashboard.py"],
        )
        mod = _import_script("run_dashboard")
        assert mod.main() == 0
        captured = capsys.readouterr()
        assert "not yet implemented" in captured.out.lower()

    # ── run_permutation_test ─────────────────────────────────────────────

    def test_run_permutation_test_exit_code(self, monkeypatch):
        """run_permutation_test.py returns 1 if p > 0.05, 0 otherwise."""
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "run_permutation_test.py",
                "--db-path",
                "test.duckdb",
                "--n-reps",
                "100",
                "--config-dir",
                "config/",
            ],
        )

        mock_configs = {"strategy_params.yaml": MagicMock()}

        with patch.dict(
            "sys.modules",
            {
                "nyse_core.config_schema": MagicMock(
                    load_and_validate_config=MagicMock(return_value=mock_configs)
                ),
                "nyse_core.statistics": MagicMock(
                    permutation_test=MagicMock(return_value=(0.03, MagicMock())),
                    block_bootstrap_ci=MagicMock(return_value=((0.5, 1.8), MagicMock())),
                    romano_wolf_stepdown=MagicMock(return_value=({"strategy": 0.04}, MagicMock())),
                ),
                "nyse_ats.storage.research_store": MagicMock(ResearchStore=MagicMock()),
            },
        ):
            mod = _import_script("run_permutation_test")
            exit_code = mod.main()

        # p=0.03 < 0.05 -> exit 0
        assert exit_code == 0
