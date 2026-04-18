"""Unit tests for RidgeModel — fit, predict, feature importance, fallback."""

from __future__ import annotations

from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from nyse_core.models.ridge_model import RidgeModel

# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_training_data(n: int = 50, n_features: int = 3, seed: int = 42) -> tuple[pd.DataFrame, pd.Series]:
    """Synthetic training data with features in [0, 1]."""
    rng = np.random.RandomState(seed)
    X = pd.DataFrame(
        rng.uniform(0, 1, size=(n, n_features)),
        columns=[f"f{i}" for i in range(n_features)],
    )
    # Linear target with noise
    true_weights = rng.uniform(-1, 1, size=n_features)
    y = pd.Series(X.values @ true_weights + rng.normal(0, 0.1, size=n))
    return X, y


# ── Fit Tests ────────────────────────────────────────────────────────────────


class TestFit:
    def test_basic_fit(self) -> None:
        model = RidgeModel(alpha=1.0)
        X, y = _make_training_data()
        diag = model.fit(X, y)

        assert not diag.has_errors
        info_msgs = [m for m in diag.messages if m.level.value == "INFO"]
        assert len(info_msgs) >= 1

    def test_fit_logs_r2(self) -> None:
        model = RidgeModel()
        X, y = _make_training_data()
        diag = model.fit(X, y)

        # Check that R2 appears in diagnostics context
        info_msgs = [m for m in diag.messages if "fit" in m.source]
        assert any("r2" in m.context for m in info_msgs)

    def test_fit_with_custom_alpha(self) -> None:
        model = RidgeModel(alpha=0.01)
        X, y = _make_training_data()
        diag = model.fit(X, y)

        assert not diag.has_errors
        info_msgs = [m for m in diag.messages if "fit" in m.source]
        assert any(m.context.get("alpha") == 0.01 for m in info_msgs)

    def test_fit_rejects_out_of_range_features(self) -> None:
        model = RidgeModel()
        X = pd.DataFrame({"f1": [0.0, 1.5], "f2": [0.5, 0.5]})
        y = pd.Series([0.1, 0.9])
        with pytest.raises(ValueError, match="AP-8"):
            model.fit(X, y)

    def test_fit_all_nan_returns_error(self) -> None:
        """All-NaN features should produce error diagnostic, not crash."""
        model = RidgeModel()
        X = pd.DataFrame({"f1": [float("nan")] * 5, "f2": [float("nan")] * 5})
        y = pd.Series([0.1, 0.2, 0.3, 0.4, 0.5])
        diag = model.fit(X, y)
        assert diag.has_errors
        assert model._model is None


# ── Predict Tests ────────────────────────────────────────────────────────────


class TestPredict:
    def test_basic_predict(self) -> None:
        model = RidgeModel()
        X, y = _make_training_data()
        model.fit(X, y)

        scores, diag = model.predict(X)
        assert len(scores) == len(X)
        assert not diag.has_errors

    def test_predict_without_fit_raises(self) -> None:
        model = RidgeModel()
        X = pd.DataFrame({"f1": [0.5], "f2": [0.5]})
        with pytest.raises(RuntimeError, match="not been fit"):
            model.predict(X)

    def test_predict_preserves_index(self) -> None:
        model = RidgeModel()
        X, y = _make_training_data(n=10)
        X.index = pd.Index([f"stock_{i}" for i in range(10)])
        y.index = X.index
        model.fit(X, y)

        scores, _ = model.predict(X)
        assert list(scores.index) == list(X.index)

    def test_predict_rejects_out_of_range(self) -> None:
        model = RidgeModel()
        X_train, y = _make_training_data()
        model.fit(X_train, y)

        X_bad = pd.DataFrame({"f0": [-0.1], "f1": [0.5], "f2": [0.5]})
        with pytest.raises(ValueError, match="AP-8"):
            model.predict(X_bad)


# ── Feature Importance Tests ─────────────────────────────────────────────────


class TestFeatureImportance:
    def test_importance_keys_match_features(self) -> None:
        model = RidgeModel()
        X, y = _make_training_data(n_features=4)
        model.fit(X, y)

        imp = model.get_feature_importance()
        assert set(imp.keys()) == set(X.columns)

    def test_importance_sums_to_one(self) -> None:
        model = RidgeModel()
        X, y = _make_training_data()
        model.fit(X, y)

        imp = model.get_feature_importance()
        assert sum(imp.values()) == pytest.approx(1.0, abs=1e-9)

    def test_importance_all_non_negative(self) -> None:
        model = RidgeModel()
        X, y = _make_training_data()
        model.fit(X, y)

        imp = model.get_feature_importance()
        assert all(v >= 0 for v in imp.values())

    def test_importance_empty_before_fit(self) -> None:
        model = RidgeModel()
        assert model.get_feature_importance() == {}


# ── Singular Matrix Fallback Tests ───────────────────────────────────────────


class TestSingularFallback:
    def test_fallback_to_previous_weights(self) -> None:
        model = RidgeModel()
        X, y = _make_training_data()

        # First fit succeeds — stores weights
        diag1 = model.fit(X, y)
        assert not diag1.has_errors

        model.get_feature_importance()

        # Second fit raises LinAlgError — should fall back
        with patch.object(
            model._model.__class__,
            "fit",
            side_effect=np.linalg.LinAlgError("singular"),
        ):
            diag2 = model.fit(X, y)

        assert diag2.has_errors
        error_msgs = [m for m in diag2.messages if m.level.value == "ERROR"]
        assert any("Singular" in m.message or "Falling back" in m.message for m in error_msgs)

        # Model should still be usable with fallback weights
        scores, pred_diag = model.predict(X)
        assert len(scores) == len(X)
        assert pred_diag.messages[0].context.get("is_fallback") is True

    def test_fallback_no_previous_weights(self) -> None:
        model = RidgeModel()
        X, y = _make_training_data()

        # Force LinAlgError on first fit — no fallback available
        with patch(
            "nyse_core.models.ridge_model.Ridge.fit",
            side_effect=np.linalg.LinAlgError("singular"),
        ):
            diag = model.fit(X, y)

        assert diag.has_errors
        error_msgs = [m for m in diag.messages if m.level.value == "ERROR"]
        assert len(error_msgs) >= 2  # singular + no fallback

        # Model is unfit — predict should raise
        with pytest.raises(RuntimeError, match="not been fit"):
            model.predict(X)
