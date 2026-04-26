"""Unit tests for scripts/run_workstream_d_single_factor.py.

Covers the pure helper functions:
  - _verdict() truth table for >= and < directions, plus None/NaN -> INDETERMINATE
  - _classify_regime_per_date() BULL/BEAR/UNKNOWN labelling
  - _assert_gates_v2_frozen() pass/fail on sha256 mismatch

scripts/ is not a Python package on sys.path (per integration test convention),
so we load the module via importlib.
"""

from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "run_workstream_d_single_factor.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("run_workstream_d_single_factor", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def mod():
    return _load_module()


class TestVerdict:
    def test_ge_direction_pass(self, mod):
        assert mod._verdict(0.50, 0.30, ">=") == "PASS"

    def test_ge_direction_at_threshold_pass(self, mod):
        # >= is inclusive
        assert mod._verdict(0.30, 0.30, ">=") == "PASS"

    def test_ge_direction_fail(self, mod):
        assert mod._verdict(0.20, 0.30, ">=") == "FAIL"

    def test_lt_direction_pass(self, mod):
        assert mod._verdict(0.04, 0.05, "<") == "PASS"

    def test_lt_direction_at_threshold_fail(self, mod):
        # < is strict
        assert mod._verdict(0.05, 0.05, "<") == "FAIL"

    def test_lt_direction_fail(self, mod):
        assert mod._verdict(0.06, 0.05, "<") == "FAIL"

    def test_none_observed_indeterminate(self, mod):
        assert mod._verdict(None, 0.30, ">=") == "INDETERMINATE"

    def test_nan_observed_indeterminate(self, mod):
        assert mod._verdict(float("nan"), 0.30, ">=") == "INDETERMINATE"

    def test_unknown_direction_raises(self, mod):
        with pytest.raises(ValueError, match="unknown direction"):
            mod._verdict(0.5, 0.3, "==")


class TestClassifyRegime:
    def _make_spy(self, n_days=300, slope=0.02):
        # Synthetic SPY: monotonically rising so SMA200 trails close after warmup.
        dates = pd.date_range("2015-01-01", periods=n_days, freq="B")
        prices = 100.0 + np.arange(n_days) * slope
        return pd.Series(prices, index=dates, name="close")

    def test_bull_when_close_above_sma200(self, mod):
        spy = self._make_spy(n_days=300, slope=0.5)  # strongly rising
        # Pick a date well past the 200-day warmup
        target = spy.index[250]
        regimes = mod._classify_regime_per_date(pd.DatetimeIndex([target]), spy)
        assert regimes.iloc[0] == "BULL"

    def test_bear_when_close_below_sma200(self, mod):
        # First 250 days rise, then sharp drop
        rising = pd.Series(
            100.0 + np.arange(250) * 0.5, index=pd.date_range("2015-01-01", periods=250, freq="B")
        )
        falling = pd.Series(
            220.0 - np.arange(50) * 1.0,
            index=pd.date_range(rising.index[-1] + pd.Timedelta(days=1), periods=50, freq="B"),
        )
        spy = pd.concat([rising, falling])
        # Pick a date in the falling tail far enough below SMA200
        target = spy.index[-1]
        regimes = mod._classify_regime_per_date(pd.DatetimeIndex([target]), spy)
        assert regimes.iloc[0] == "BEAR"

    def test_unknown_when_pre_sma200_warmup(self, mod):
        # Only 100 days of SPY — SMA200 not yet computable
        spy = self._make_spy(n_days=100)
        target = spy.index[-1]
        regimes = mod._classify_regime_per_date(pd.DatetimeIndex([target]), spy)
        assert regimes.iloc[0] == "UNKNOWN"

    def test_unknown_when_target_before_first_spy_obs(self, mod):
        spy = self._make_spy(n_days=300)
        target = pd.Timestamp("2010-01-01")  # well before SPY's first date
        regimes = mod._classify_regime_per_date(pd.DatetimeIndex([target]), spy)
        assert regimes.iloc[0] == "UNKNOWN"

    def test_uses_last_obs_on_or_before_target(self, mod):
        # Target is a non-trading day; classifier should fall back to the prior obs
        spy = self._make_spy(n_days=300, slope=0.5)
        # Sandwich a missing date between two SPY days
        target = pd.Timestamp(spy.index[250].date()) + pd.Timedelta(days=1)
        # If this target happens to be in spy.index, shift by one more day
        while target in spy.index:
            target = target + pd.Timedelta(days=1)
        regimes = mod._classify_regime_per_date(pd.DatetimeIndex([target]), spy)
        # Should still classify (BULL or BEAR), not UNKNOWN
        assert regimes.iloc[0] in {"BULL", "BEAR"}


class TestAssertGatesFrozen:
    def test_match_does_not_raise(self, mod, tmp_path):
        # Write a file with bytes whose sha256 == _GATES_V2_SHA256? We can't
        # forge that, but we can verify the assertion uses the actual repo file.
        # Instead, copy the real config/gates_v2.yaml and check it passes.
        real_cfg = REPO_ROOT / "config" / "gates_v2.yaml"
        if not real_cfg.exists():
            pytest.skip("config/gates_v2.yaml not present in repo")
        # Direct call against the real path should not raise
        mod._assert_gates_v2_frozen(real_cfg)

    def test_mismatch_raises(self, mod, tmp_path):
        bad = tmp_path / "fake_gates.yaml"
        bad.write_text("bogus_content_with_different_hash\n")
        actual = hashlib.sha256(bad.read_bytes()).hexdigest()
        assert actual != mod._GATES_V2_SHA256
        with pytest.raises(RuntimeError, match="REFUSED.*gates_v2.yaml sha256"):
            mod._assert_gates_v2_frozen(bad)


class TestConstants:
    def test_pre_registered_thresholds_match_gl_0021(self, mod):
        assert mod._V_D1_THRESHOLD == 0.30
        assert mod._V_D2_THRESHOLD == 0.05
        assert mod._V_D3_THRESHOLD == 0.20
        assert mod._V_D4_THRESHOLD == 0.20

    def test_annual_factor_matches_weekly_5d_fwd(self, mod):
        assert mod._ANNUAL_FACTOR_WEEKLY == 52

    def test_perm_and_boot_params_match_v2_chain(self, mod):
        # Mirror simulate_v2_ensemble_phase3.py choices for evidence-chain consistency
        assert mod._PERM_REPS == 500
        assert mod._PERM_BLOCK == 21
        assert mod._BOOT_REPS == 10000
        assert mod._BOOT_BLOCK == 63
        assert mod._BOOT_ALPHA == 0.05


class TestBuildIvolPanel:
    def _synthetic_ohlcv(self, n_symbols=20, n_days=40):
        dates = pd.date_range("2016-01-01", periods=n_days, freq="B")
        rng = np.random.default_rng(0)
        rows = []
        for sym_i in range(n_symbols):
            sym = f"S{sym_i:02d}"
            base = 100.0 + sym_i
            noise = rng.normal(0, 0.5 + sym_i * 0.05, size=n_days).cumsum()
            for i, dt in enumerate(dates):
                price = float(base + noise[i])
                rows.append(
                    {
                        "date": dt.date(),
                        "symbol": sym,
                        "open": price,
                        "high": price,
                        "low": price,
                        "close": price,
                        "volume": 1_000_000,
                    }
                )
        return pd.DataFrame(rows)

    def test_panel_has_expected_columns_and_score_range(self, mod):
        ohlcv = self._synthetic_ohlcv(n_symbols=15, n_days=35)
        rebal = [pd.Timestamp(ohlcv["date"].max())]
        panel = mod._build_ivol_panel(ohlcv, rebal)
        assert list(panel.columns) == ["date", "symbol", "score"]
        assert not panel.empty
        # rank-percentile output is in [0, 1]
        assert panel["score"].between(0.0, 1.0).all()

    def test_panel_empty_with_no_rebalance_dates(self, mod):
        ohlcv = self._synthetic_ohlcv(n_symbols=10, n_days=30)
        panel = mod._build_ivol_panel(ohlcv, [])
        assert panel.empty
        assert list(panel.columns) == ["date", "symbol", "score"]

    def test_panel_deterministic_across_runs(self, mod):
        ohlcv = self._synthetic_ohlcv(n_symbols=12, n_days=32)
        rebal = [pd.Timestamp(ohlcv["date"].max())]
        p1 = mod._build_ivol_panel(ohlcv, rebal)
        p2 = mod._build_ivol_panel(ohlcv, rebal)
        # RNG seeded by date.toordinal() — same input -> identical output
        pd.testing.assert_frame_equal(
            p1.sort_values(["date", "symbol"]).reset_index(drop=True),
            p2.sort_values(["date", "symbol"]).reset_index(drop=True),
        )
