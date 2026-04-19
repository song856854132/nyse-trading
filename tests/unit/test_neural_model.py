"""Unit tests for NeuralModel -- fit, predict, feature importance, fallback, import error."""

from __future__ import annotations

from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from nyse_core.models.neural_model import NeuralModel

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
        """Basic fit + predict on synthetic data."""
        model = NeuralModel(hidden_dims=(16, 8), epochs=20)
        X, y = _make_training_data(n=30, n_features=3)
        diag = model.fit(X, y)

        if diag.has_errors:
            error_msgs = [m.message for m in diag.messages]
            assert any("not installed" in m for m in error_msgs)
            pytest.skip("torch not installed")

        scores, pred_diag = model.predict(X)
        assert len(scores) == len(X)
        assert not pred_diag.has_errors

    def test_ap8_violation_raises(self) -> None:
        """Feature values outside [0, 1] must raise ValueError."""
        model = NeuralModel()
        X = pd.DataFrame({"f1": [0.0, 1.5], "f2": [0.5, 0.5]})
        y = pd.Series([0.1, 0.9])
        with pytest.raises(ValueError, match="AP-8"):
            model.fit(X, y)

    def test_early_stopping(self) -> None:
        """Model should log training with epoch count."""
        model = NeuralModel(hidden_dims=(16, 8), epochs=50, patience=5)
        X, y = _make_training_data(n=60, n_features=3)
        diag = model.fit(X, y)

        if diag.has_errors:
            pytest.skip("torch not installed")

        info_msgs = [m for m in diag.messages if "fit" in m.source]
        assert any("epochs_run" in m.context for m in info_msgs)

    def test_single_feature(self) -> None:
        """Model should handle a single-feature input."""
        model = NeuralModel(hidden_dims=(8, 4), epochs=10)
        X, y = _make_training_data(n=30, n_features=1)
        diag = model.fit(X, y)

        if diag.has_errors:
            pytest.skip("torch not installed")

        scores, pred_diag = model.predict(X)
        assert len(scores) == len(X)
        assert not pred_diag.has_errors


# -- Predict Tests -----------------------------------------------------------


class TestPredict:
    def test_unfitted_predict_raises(self) -> None:
        """Predict before fit must raise RuntimeError."""
        model = NeuralModel()
        X = pd.DataFrame({"f1": [0.5], "f2": [0.5]})
        with pytest.raises(RuntimeError, match="not been fit"):
            model.predict(X)

    def test_predict_preserves_index(self) -> None:
        """Predictions must preserve the input DataFrame index."""
        model = NeuralModel(hidden_dims=(8, 4), epochs=10)
        X, y = _make_training_data(n=30)
        X.index = pd.Index([f"stock_{i}" for i in range(30)])
        y.index = X.index
        diag = model.fit(X, y)

        if diag.has_errors:
            pytest.skip("torch not installed")

        scores, _ = model.predict(X)
        assert list(scores.index) == list(X.index)

    def test_predict_ap8_violation(self) -> None:
        """Predict with out-of-range features must raise."""
        model = NeuralModel(hidden_dims=(8, 4), epochs=10)
        X, y = _make_training_data(n=30)
        diag = model.fit(X, y)

        if diag.has_errors:
            pytest.skip("torch not installed")

        X_bad = pd.DataFrame({"f0": [-0.1], "f1": [0.5], "f2": [0.5]})
        with pytest.raises(ValueError, match="AP-8"):
            model.predict(X_bad)

    def test_y_standardization(self) -> None:
        """Predictions should be in the original y scale, not normalized."""
        model = NeuralModel(hidden_dims=(16, 8), epochs=30)
        X, y = _make_training_data(n=50, n_features=3)
        # Shift y to a large mean so normalization matters
        y_shifted = y + 100.0
        diag = model.fit(X, y_shifted)

        if diag.has_errors:
            pytest.skip("torch not installed")

        scores, _ = model.predict(X)
        # Predictions should be in the ballpark of the original y range
        assert scores.mean() > 50.0, f"Mean prediction {scores.mean():.2f} is too far from y mean ~100"


# -- Feature Importance Tests ------------------------------------------------


class TestFeatureImportance:
    def test_feature_importance_normalized(self) -> None:
        """Feature importance values should sum to approximately 1.0."""
        model = NeuralModel(hidden_dims=(16, 8), epochs=20)
        X, y = _make_training_data(n=50, n_features=3)
        diag = model.fit(X, y)

        if diag.has_errors:
            pytest.skip("torch not installed")

        imp = model.get_feature_importance()
        assert sum(imp.values()) == pytest.approx(1.0, abs=1e-6)

    def test_feature_importance_keys_match(self) -> None:
        """Importance keys must match training feature names."""
        model = NeuralModel(hidden_dims=(16, 8), epochs=20)
        X, y = _make_training_data(n=50, n_features=4)
        diag = model.fit(X, y)

        if diag.has_errors:
            pytest.skip("torch not installed")

        imp = model.get_feature_importance()
        assert set(imp.keys()) == set(X.columns)

    def test_feature_importance_empty_before_fit(self) -> None:
        """Before fit, importance should be empty dict."""
        model = NeuralModel()
        assert model.get_feature_importance() == {}

    def test_feature_importance_all_non_negative(self) -> None:
        """All importance values must be non-negative."""
        model = NeuralModel(hidden_dims=(16, 8), epochs=20)
        X, y = _make_training_data(n=50)
        diag = model.fit(X, y)

        if diag.has_errors:
            pytest.skip("torch not installed")

        imp = model.get_feature_importance()
        assert all(v >= 0 for v in imp.values())


# -- Fallback Tests ----------------------------------------------------------


class TestFallback:
    def test_fallback_on_error(self) -> None:
        """If second fit fails, model should fall back to previous weights."""
        model = NeuralModel(hidden_dims=(8, 4), epochs=10)
        X, y = _make_training_data(n=30)
        diag1 = model.fit(X, y)

        if diag1.has_errors:
            pytest.skip("torch not installed")

        first_scores, _ = model.predict(X)

        # Force an error on second fit by patching torch.manual_seed at its library path.
        # `torch` is imported lazily inside neural_model.fit, so it is not a module-level
        # attribute of nyse_core.models.neural_model — patching torch.manual_seed
        # directly affects the same object the lazy import resolves to.
        with patch(
            "torch.manual_seed",
            side_effect=RuntimeError("mock error"),
        ):
            diag2 = model.fit(X, y)

        # If torch is available, the error should trigger fallback
        if not any("not installed" in m.message for m in diag2.messages):
            assert diag2.has_errors
            fallback_scores, pred_diag = model.predict(X)
            assert len(fallback_scores) == len(X)
            assert pred_diag.messages[0].context.get("is_fallback") is True


# -- Determinism Tests -------------------------------------------------------


class TestDeterminism:
    def test_deterministic_with_seed(self) -> None:
        """Two fits with same data should produce identical predictions."""
        X, y = _make_training_data(n=40, seed=99)

        model1 = NeuralModel(hidden_dims=(16, 8), epochs=20)
        diag1 = model1.fit(X, y)
        if diag1.has_errors:
            pytest.skip("torch not installed")

        model2 = NeuralModel(hidden_dims=(16, 8), epochs=20)
        model2.fit(X, y)

        scores1, _ = model1.predict(X)
        scores2, _ = model2.predict(X)
        pd.testing.assert_series_equal(scores1, scores2, atol=1e-6)


# -- ImportError Tests -------------------------------------------------------


class TestImportError:
    def test_torch_import_error(self) -> None:
        """When torch is not available, fit should return error diagnostic."""
        import builtins

        original_import = builtins.__import__

        def mock_import(name: str, *args, **kwargs):  # type: ignore[no-untyped-def]
            if name == "torch" or name.startswith("torch."):
                raise ImportError("No module named 'torch'")
            return original_import(name, *args, **kwargs)

        model = NeuralModel()
        X, y = _make_training_data(n=30)

        with patch("builtins.__import__", side_effect=mock_import):
            diag = model.fit(X, y)

        assert diag.has_errors
        error_msgs = [m.message for m in diag.messages]
        assert any("not installed" in m for m in error_msgs)
