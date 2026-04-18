"""CombinationModel protocol and factory for signal combination.

Defines the interface all combination models must satisfy and provides
a factory function that routes to concrete implementations.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

import pandas as pd

from nyse_core.contracts import Diagnostics
from nyse_core.schema import CombinationModelType


@runtime_checkable
class CombinationModel(Protocol):
    """Protocol for signal combination models.

    All implementations must:
      - Accept feature matrices where ALL values are in [0, 1] (AP-8).
      - Return (result, Diagnostics) from fit/predict.
      - Expose feature importance as normalized absolute weights.
    """

    def fit(self, X: pd.DataFrame, y: pd.Series) -> Diagnostics:
        """Train the model on feature matrix X and target y."""
        ...

    def predict(self, X: pd.DataFrame) -> tuple[pd.Series, Diagnostics]:
        """Produce composite scores for the feature matrix X."""
        ...

    def get_feature_importance(self) -> dict[str, float]:
        """Return normalized absolute feature weights."""
        ...


def _validate_feature_range(X: pd.DataFrame, source: str) -> None:
    """AP-8: Assert all feature values are in [0, 1].

    Raises:
        ValueError: If any non-NaN value falls outside [0, 1].
    """
    numeric_vals = X.select_dtypes(include="number")
    min_val = numeric_vals.min().min()
    max_val = numeric_vals.max().max()

    if pd.isna(min_val) and pd.isna(max_val):
        # All NaN — nothing to validate
        return

    if (not pd.isna(min_val) and min_val < 0.0) or (not pd.isna(max_val) and max_val > 1.0):
        raise ValueError(
            f"[{source}] AP-8 violation: feature values must be in [0, 1]. "
            f"Found range [{min_val}, {max_val}]."
        )


def create_model(model_type: str, **kwargs: object) -> tuple[CombinationModel, Diagnostics]:
    """Factory: create a CombinationModel by type name.

    Args:
        model_type: One of 'ridge', 'gbm', 'neural'.
        **kwargs: Passed to the model constructor.

    Returns:
        (model, diagnostics) tuple.

    Raises:
        ValueError: If model_type is not recognized or not yet implemented.
    """
    diag = Diagnostics()
    source = "signal_combination.create_model"

    # Validate against the enum to catch typos early
    try:
        mt = CombinationModelType(model_type)
    except ValueError:
        valid = [e.value for e in CombinationModelType]
        raise ValueError(f"Unknown model_type '{model_type}'. Valid types: {valid}") from None

    if mt == CombinationModelType.RIDGE:
        from nyse_core.models.ridge_model import RidgeModel

        diag.info(source, "Created ridge model", model_type=model_type)
        return RidgeModel(**kwargs), diag  # type: ignore[arg-type]
    elif mt == CombinationModelType.GBM:
        from nyse_core.models.gbm_model import GBMModel

        diag.info(source, "Created gbm model", model_type=model_type)
        return GBMModel(**kwargs), diag  # type: ignore[arg-type]
    elif mt == CombinationModelType.NEURAL:
        from nyse_core.models.neural_model import NeuralModel

        diag.info(source, "Created neural model", model_type=model_type)
        return NeuralModel(**kwargs), diag  # type: ignore[arg-type]

    raise ValueError(f"Model type '{model_type}' not recognized.")
