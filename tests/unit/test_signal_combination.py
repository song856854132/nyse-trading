"""Unit tests for signal combination protocol, factory, and AP-8 validation."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from nyse_core.signal_combination import (
    CombinationModel,
    _validate_feature_range,
    create_model,
)

# ── Protocol Tests ───────────────────────────────────────────────────────────


class TestProtocol:
    def test_ridge_model_satisfies_protocol(self) -> None:
        model, _ = create_model("ridge")
        assert isinstance(model, CombinationModel)

    def test_protocol_has_required_methods(self) -> None:
        model, _ = create_model("ridge")
        assert hasattr(model, "fit")
        assert hasattr(model, "predict")
        assert hasattr(model, "get_feature_importance")
        assert callable(model.fit)
        assert callable(model.predict)
        assert callable(model.get_feature_importance)


# ── Factory Tests ────────────────────────────────────────────────────────────


class TestFactory:
    def test_create_ridge(self) -> None:
        model, _ = create_model("ridge")
        assert isinstance(model, CombinationModel)

    def test_create_ridge_with_alpha(self) -> None:
        model, _ = create_model("ridge", alpha=0.5)
        assert model.alpha == 0.5  # type: ignore[attr-defined]

    def test_unknown_type_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown model_type"):
            create_model("random_forest")

    def test_create_gbm(self) -> None:
        model, _ = create_model("gbm")
        assert isinstance(model, CombinationModel)

    def test_create_neural(self) -> None:
        model, _ = create_model("neural")
        assert isinstance(model, CombinationModel)


# ── AP-8 Feature Range Validation ────────────────────────────────────────────


class TestFeatureRangeValidation:
    def test_valid_range(self) -> None:
        X = pd.DataFrame({"a": [0.0, 0.5, 1.0], "b": [0.1, 0.9, 0.3]})
        _validate_feature_range(X, "test")  # Should not raise

    def test_below_zero_raises(self) -> None:
        X = pd.DataFrame({"a": [-0.1, 0.5, 1.0]})
        with pytest.raises(ValueError, match="AP-8"):
            _validate_feature_range(X, "test")

    def test_above_one_raises(self) -> None:
        X = pd.DataFrame({"a": [0.0, 0.5, 1.01]})
        with pytest.raises(ValueError, match="AP-8"):
            _validate_feature_range(X, "test")

    def test_all_nan_passes(self) -> None:
        X = pd.DataFrame({"a": [np.nan, np.nan]})
        _validate_feature_range(X, "test")  # Should not raise

    def test_boundary_values_pass(self) -> None:
        X = pd.DataFrame({"a": [0.0, 1.0], "b": [0.0, 1.0]})
        _validate_feature_range(X, "test")  # Should not raise


# ── Integration: Factory + Fit/Predict ───────────────────────────────────────


class TestFactoryIntegration:
    def test_factory_model_can_fit_and_predict(self) -> None:
        model, _ = create_model("ridge", alpha=1.0)
        X = pd.DataFrame(
            {
                "f1": [0.1, 0.2, 0.3, 0.4, 0.5],
                "f2": [0.9, 0.8, 0.7, 0.6, 0.5],
            }
        )
        y = pd.Series([0.1, 0.3, 0.5, 0.7, 0.9])

        diag = model.fit(X, y)
        assert not diag.has_errors

        scores, pred_diag = model.predict(X)
        assert len(scores) == 5
        assert not pred_diag.has_errors

    def test_factory_model_rejects_invalid_features(self) -> None:
        model, _ = create_model("ridge")
        X = pd.DataFrame({"f1": [0.0, 2.0]})  # 2.0 > 1.0
        y = pd.Series([0.1, 0.9])

        with pytest.raises(ValueError, match="AP-8"):
            model.fit(X, y)
