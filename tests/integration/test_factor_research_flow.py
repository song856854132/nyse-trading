"""Integration tests for the factor research flow.

End-to-end tests using synthetic data that exercise:
  FactorRegistry -> FeatureMatrix -> Normalization -> Ridge -> IC -> Gates
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

from nyse_core.contracts import Diagnostics
from nyse_core.features.registry import FactorRegistry
from nyse_core.gates import evaluate_factor_gates
from nyse_core.metrics import information_coefficient
from nyse_core.normalize import rank_percentile
from nyse_core.schema import UsageDomain
from nyse_core.signal_combination import create_model

# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_compute_fn(col_name: str):
    """Build a compute function that extracts and returns a column from data."""

    def compute_fn(data: pd.DataFrame) -> tuple[pd.Series, Diagnostics]:
        diag = Diagnostics()
        diag.info("test_factor", f"Computing {col_name}")
        return data[col_name].astype(float), diag

    return compute_fn


def _generate_synthetic_data(
    n_stocks: int = 50,
    seed: int = 42,
) -> pd.DataFrame:
    """Generate synthetic feature data with 3 factor columns and forward returns."""
    rng = np.random.default_rng(seed)
    symbols = [f"SYM_{i:02d}" for i in range(n_stocks)]

    factor_a = rng.normal(0.0, 1.0, n_stocks)
    factor_b = rng.normal(0.5, 0.8, n_stocks)
    factor_c = rng.normal(-0.2, 1.2, n_stocks)

    # Forward returns partially correlated with factor_a (planted signal)
    noise = rng.normal(0.0, 0.02, n_stocks)
    fwd_returns = 0.01 * factor_a + noise

    return pd.DataFrame(
        {
            "symbol": symbols,
            "factor_a": factor_a,
            "factor_b": factor_b,
            "factor_c": factor_c,
            "fwd_ret_5d": fwd_returns,
        }
    )


# ── Test: register and compute all factors ───────────────────────────────────


class TestRegisterAndComputeAllFactors:
    """Create a FactorRegistry, register 3 factors, compute_all, verify shape."""

    def test_register_and_compute_all_factors(self) -> None:
        data = _generate_synthetic_data()
        registry = FactorRegistry()

        for col in ["factor_a", "factor_b", "factor_c"]:
            registry.register(
                name=col,
                compute_fn=_make_compute_fn(col),
                usage_domain=UsageDomain.SIGNAL,
                sign_convention=1,
                description=f"Test factor: {col}",
            )

        result, diag = registry.compute_all(data, rebalance_date=date(2024, 6, 1))

        assert result.shape == (len(data), 3), f"Expected ({len(data)}, 3), got {result.shape}"
        assert list(result.columns) == ["factor_a", "factor_b", "factor_c"]
        assert not result.isna().any().any(), "Feature matrix should have no NaN values"


# ── Test: normalize feature matrix ───────────────────────────────────────────


class TestNormalizeFeatureMatrix:
    """Apply rank_percentile to each column; verify all values in [0, 1]."""

    def test_normalize_feature_matrix(self) -> None:
        data = _generate_synthetic_data()
        registry = FactorRegistry()

        for col in ["factor_a", "factor_b", "factor_c"]:
            registry.register(
                name=col,
                compute_fn=_make_compute_fn(col),
                usage_domain=UsageDomain.SIGNAL,
                sign_convention=1,
            )

        features, _ = registry.compute_all(data, rebalance_date=date(2024, 6, 1))

        # Normalize each column
        normalized = pd.DataFrame(index=features.index)
        for col in features.columns:
            normalized[col], _ = rank_percentile(features[col])

        # All values must be in [0, 1]
        assert normalized.min().min() >= 0.0, "Normalized values below 0"
        assert normalized.max().max() <= 1.0, "Normalized values above 1"

        # No NaN should remain (all input values were non-NaN)
        assert not normalized.isna().any().any(), "NaN found after normalization"


# ── Test: Ridge model on normalized features ─────────────────────────────────


class TestRidgeOnNormalizedFeatures:
    """Generate normalized features, fit Ridge, predict, verify output shape."""

    def test_ridge_on_normalized_features(self) -> None:
        rng = np.random.default_rng(42)
        n = 100

        # Generate features in [0, 1]
        X = pd.DataFrame(
            {
                "f1": rng.uniform(0, 1, n),
                "f2": rng.uniform(0, 1, n),
                "f3": rng.uniform(0, 1, n),
            }
        )
        y = pd.Series(rng.normal(0, 0.05, n))

        model, _ = create_model("ridge", alpha=1.0)
        diag = model.fit(X, y)
        assert not diag.has_errors, "Ridge fit should not produce errors"

        predictions, pred_diag = model.predict(X)
        assert len(predictions) == n, f"Expected {n} predictions, got {len(predictions)}"
        assert predictions.index.equals(X.index), "Prediction index mismatch"
        assert not predictions.isna().any(), "NaN in predictions"


# ── Test: IC computation on synthetic signal ─────────────────────────────────


class TestICComputationOnSyntheticSignal:
    """Plant a monotonic signal, compute IC, verify IC > 0."""

    def test_ic_computation_on_synthetic_signal(self) -> None:
        rng = np.random.default_rng(42)
        n = 100

        # Planted signal: factor = forward returns + noise
        fwd_returns = pd.Series(rng.normal(0.0, 0.05, n))
        factor_scores = fwd_returns + pd.Series(rng.normal(0.0, 0.01, n))

        ic, _ = information_coefficient(factor_scores, fwd_returns)
        assert ic > 0, f"Expected positive IC for planted signal, got {ic:.4f}"
        assert ic > 0.3, f"Expected strong IC for planted signal, got {ic:.4f}"


# ── Test: factor correlation matrix ──────────────────────────────────────────


class TestFactorCorrelationMatrix:
    """Compute correlation between 3 factors, verify 3x3 matrix, diagonal=1.0."""

    def test_factor_correlation_matrix(self) -> None:
        rng = np.random.default_rng(42)
        n = 100

        features = pd.DataFrame(
            {
                "f1": rng.normal(0, 1, n),
                "f2": rng.normal(0, 1, n),
                "f3": rng.normal(0, 1, n),
            }
        )

        corr_matrix = features.corr()

        assert corr_matrix.shape == (3, 3), f"Expected 3x3, got {corr_matrix.shape}"
        np.testing.assert_allclose(
            np.diag(corr_matrix.values),
            1.0,
            atol=1e-10,
            err_msg="Diagonal of correlation matrix should be 1.0",
        )
        # Off-diagonal should be in [-1, 1]
        assert (corr_matrix.values >= -1.0 - 1e-10).all(), "Correlation below -1"
        assert (corr_matrix.values <= 1.0 + 1e-10).all(), "Correlation above 1"


# ── Test: gate evaluation on strong factor ───────────────────────────────────


class TestGateEvaluationOnStrongFactor:
    """Compute metrics for a strong planted signal, pass through gates."""

    def test_gate_evaluation_on_strong_factor(self) -> None:
        factor_metrics = {
            "oos_sharpe": 1.5,
            "permutation_p": 0.001,
            "ic_mean": 0.08,
            "ic_ir": 2.0,
            "max_drawdown": -0.05,
            "marginal_contribution": 0.3,
        }

        verdict, _diag = evaluate_factor_gates(factor_metrics)
        assert verdict.passed_all is True, (
            f"Strong factor should pass all gates. gate_results={verdict.gate_results}"
        )


# ── Test: gate evaluation on noise ───────────────────────────────────────────


class TestGateEvaluationOnNoise:
    """Pure noise factor should fail at least one gate."""

    def test_gate_evaluation_on_noise(self) -> None:
        # Noise factor has bad metrics
        factor_metrics = {
            "oos_sharpe": 0.0,
            "permutation_p": 0.8,
            "ic_mean": 0.001,
            "ic_ir": 0.05,
            "max_drawdown": -0.50,
            "marginal_contribution": -0.01,
        }

        verdict, _diag = evaluate_factor_gates(factor_metrics)
        assert verdict.passed_all is False, (
            f"Noise factor should fail at least one gate, but passed all. gate_results={verdict.gate_results}"
        )

        # Verify at least one specific gate failed
        n_failed = sum(1 for v in verdict.gate_results.values() if not v)
        assert n_failed >= 1, "Expected at least one gate to fail for pure noise"
