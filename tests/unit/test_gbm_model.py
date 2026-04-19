"""Unit tests for GBMModel -- fit, predict, feature importance, fallback, import error."""

from __future__ import annotations

from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from nyse_core.models.gbm_model import GBMModel

# -- Helpers -----------------------------------------------------------------


def _make_training_data(n: int = 50, n_features: int = 3, seed: int = 42) -> tuple[pd.DataFrame, pd.Series]:
    """Synthetic training data with features in [0, 1]."""
    rng = np.random.RandomState(seed)
    X = pd.DataFrame(
        rng.uniform(0, 1, size=(n, n_features)),
        columns=[f"f{i}" for i in range(n_features)],
    )
    true_weights = rng.uniform(-1, 1, size=n_features)
    y = pd.Series(X.values @ true_weights + rng.normal(0, 0.1, size=n))
    return X, y


# -- Fit Tests ---------------------------------------------------------------


class TestFit:
    def test_fit_predict_basic(self) -> None:
        """Basic fit + predict on 30-stock, 3-feature synthetic data."""
        model = GBMModel(n_estimators=20, max_depth=2)
        X, y = _make_training_data(n=30, n_features=3)
        diag = model.fit(X, y)

        # If lightgbm is not installed, fit returns an error diagnostic
        if diag.has_errors:
            error_msgs = [m.message for m in diag.messages]
            assert any("not installed" in m for m in error_msgs)
            pytest.skip("lightgbm not installed")

        scores, pred_diag = model.predict(X)
        assert len(scores) == len(X)
        assert not pred_diag.has_errors

    def test_ap8_violation_raises(self) -> None:
        """Feature values outside [0, 1] must raise ValueError."""
        model = GBMModel()
        X = pd.DataFrame({"f1": [0.0, 1.5], "f2": [0.5, 0.5]})
        y = pd.Series([0.1, 0.9])
        with pytest.raises(ValueError, match="AP-8"):
            model.fit(X, y)

    def test_early_stopping_with_large_data(self) -> None:
        """With >= 20 samples, early stopping should be used."""
        model = GBMModel(n_estimators=50)
        X, y = _make_training_data(n=60, n_features=3)
        diag = model.fit(X, y)

        if diag.has_errors:
            pytest.skip("lightgbm not installed")

        info_msgs = [m for m in diag.messages if "fit" in m.source]
        assert any("early stopping" in m.message.lower() for m in info_msgs)
        # Should have n_val in context
        assert any("n_val" in m.context for m in info_msgs)

    def test_small_data_no_early_stopping(self) -> None:
        """With < 20 samples, fit should work without early stopping."""
        model = GBMModel(n_estimators=10)
        X, y = _make_training_data(n=15, n_features=2)
        diag = model.fit(X, y)

        if diag.has_errors:
            pytest.skip("lightgbm not installed")

        info_msgs = [m for m in diag.messages if "fit" in m.source]
        assert any("without early stopping" in m.message.lower() for m in info_msgs)


# -- Predict Tests -----------------------------------------------------------


class TestPredict:
    def test_unfitted_predict_raises(self) -> None:
        """Predict before fit must raise RuntimeError."""
        model = GBMModel()
        X = pd.DataFrame({"f1": [0.5], "f2": [0.5]})
        with pytest.raises(RuntimeError, match="not been fit"):
            model.predict(X)

    def test_predict_preserves_index(self) -> None:
        """Predictions must preserve the input DataFrame index."""
        model = GBMModel(n_estimators=10)
        X, y = _make_training_data(n=30)
        X.index = pd.Index([f"stock_{i}" for i in range(30)])
        y.index = X.index
        diag = model.fit(X, y)

        if diag.has_errors:
            pytest.skip("lightgbm not installed")

        scores, _ = model.predict(X)
        assert list(scores.index) == list(X.index)

    def test_predict_ap8_violation(self) -> None:
        """Predict with out-of-range features must raise."""
        model = GBMModel(n_estimators=10)
        X, y = _make_training_data(n=30)
        diag = model.fit(X, y)

        if diag.has_errors:
            pytest.skip("lightgbm not installed")

        X_bad = pd.DataFrame({"f0": [-0.1], "f1": [0.5], "f2": [0.5]})
        with pytest.raises(ValueError, match="AP-8"):
            model.predict(X_bad)


# -- Feature Importance Tests ------------------------------------------------


class TestFeatureImportance:
    def test_feature_importance_normalized(self) -> None:
        """Feature importance values should sum to approximately 1.0."""
        model = GBMModel(n_estimators=20)
        X, y = _make_training_data(n=50, n_features=3)
        diag = model.fit(X, y)

        if diag.has_errors:
            pytest.skip("lightgbm not installed")

        imp = model.get_feature_importance()
        assert sum(imp.values()) == pytest.approx(1.0, abs=1e-6)

    def test_feature_importance_keys_match(self) -> None:
        """Importance keys must match training feature names."""
        model = GBMModel(n_estimators=20)
        X, y = _make_training_data(n=50, n_features=4)
        diag = model.fit(X, y)

        if diag.has_errors:
            pytest.skip("lightgbm not installed")

        imp = model.get_feature_importance()
        assert set(imp.keys()) == set(X.columns)

    def test_feature_importance_empty_before_fit(self) -> None:
        """Before fit, importance should be empty dict."""
        model = GBMModel()
        assert model.get_feature_importance() == {}

    def test_feature_importance_all_non_negative(self) -> None:
        """All importance values must be non-negative."""
        model = GBMModel(n_estimators=20)
        X, y = _make_training_data(n=50)
        diag = model.fit(X, y)

        if diag.has_errors:
            pytest.skip("lightgbm not installed")

        imp = model.get_feature_importance()
        assert all(v >= 0 for v in imp.values())


# -- Fallback Tests ----------------------------------------------------------


class TestFallback:
    def test_fallback_on_error(self) -> None:
        """If second fit fails, model should fall back to previous."""
        model = GBMModel(n_estimators=10)
        X, y = _make_training_data(n=30)
        diag1 = model.fit(X, y)

        if diag1.has_errors:
            pytest.skip("lightgbm not installed")

        first_scores, _ = model.predict(X)

        # Force an error on second fit by patching LGBMRegressor at its library path.
        # `lgb` is imported lazily inside gbm_model.fit, so it is not a module-level
        # attribute of nyse_core.models.gbm_model — patching lightgbm.LGBMRegressor
        # directly affects the same object the lazy import resolves to.
        with patch(
            "lightgbm.LGBMRegressor",
            side_effect=RuntimeError("mock training error"),
        ):
            diag2 = model.fit(X, y)

        assert diag2.has_errors
        # Model should still be usable via fallback
        fallback_scores, pred_diag = model.predict(X)
        assert len(fallback_scores) == len(X)
        assert pred_diag.messages[0].context.get("is_fallback") is True


# -- Determinism Tests -------------------------------------------------------


class TestDeterminism:
    def test_deterministic_with_seed(self) -> None:
        """Two fits with same data should produce identical predictions."""
        X, y = _make_training_data(n=40, seed=99)

        model1 = GBMModel(n_estimators=20)
        diag1 = model1.fit(X, y)
        if diag1.has_errors:
            pytest.skip("lightgbm not installed")

        model2 = GBMModel(n_estimators=20)
        model2.fit(X, y)

        scores1, _ = model1.predict(X)
        scores2, _ = model2.predict(X)
        pd.testing.assert_series_equal(scores1, scores2)


# -- ImportError Tests -------------------------------------------------------


class TestImportError:
    def test_lightgbm_import_error(self) -> None:
        """When lightgbm is not available, fit should return error diagnostic."""
        import builtins

        original_import = builtins.__import__

        def mock_import(name: str, *args, **kwargs):  # type: ignore[no-untyped-def]
            if name == "lightgbm":
                raise ImportError("No module named 'lightgbm'")
            return original_import(name, *args, **kwargs)

        model = GBMModel()
        X, y = _make_training_data(n=30)

        with patch("builtins.__import__", side_effect=mock_import):
            diag = model.fit(X, y)

        assert diag.has_errors
        error_msgs = [m.message for m in diag.messages]
        assert any("not installed" in m for m in error_msgs)
