"""Ridge regression implementation of the CombinationModel protocol.

Uses sklearn.linear_model.Ridge with singular matrix fallback.
Stores previous weights so that if a LinAlgError occurs during fit,
the model falls back to the last known good weights.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.metrics import r2_score

from nyse_core.contracts import Diagnostics
from nyse_core.signal_combination import _validate_feature_range


class RidgeModel:
    """CombinationModel implementation using Ridge regression.

    Attributes:
        alpha: Ridge regularization strength.
    """

    def __init__(self, alpha: float = 1.0, **kwargs: object) -> None:
        self.alpha = alpha
        self._model: Ridge | None = None
        self._feature_names: list[str] = []
        self._prev_coef: np.ndarray | None = None
        self._prev_intercept: float = 0.0
        self._is_fallback: bool = False

    def fit(self, X: pd.DataFrame, y: pd.Series) -> Diagnostics:
        """Train the Ridge model on feature matrix X and target y.

        AP-8: All values in X must be in [0, 1].
        On singular matrix (LinAlgError), falls back to previous weights.
        """
        diag = Diagnostics()
        source = "ridge_model.fit"

        _validate_feature_range(X, source)

        if X.isna().all().all():
            diag.error(source, "All feature values are NaN — cannot fit model.")
            return diag

        self._feature_names = list(X.columns)
        self._is_fallback = False

        try:
            model = Ridge(alpha=self.alpha)
            model.fit(X.values, y.values)

            # Store current weights as fallback for future errors
            self._prev_coef = model.coef_.copy()
            self._prev_intercept = float(model.intercept_)
            self._model = model

            y_pred = model.predict(X.values)
            r2 = r2_score(y.values, y_pred)

            diag.info(
                source,
                "Ridge fit completed.",
                n_samples=len(X),
                n_features=len(self._feature_names),
                alpha=self.alpha,
                r2=float(r2),
            )

        except np.linalg.LinAlgError:
            diag.error(
                source,
                "Singular matrix during Ridge fit. Falling back to previous weights.",
                alpha=self.alpha,
                n_samples=len(X),
                n_features=len(self._feature_names),
            )

            if self._prev_coef is not None:
                # Build a model shell with previous weights
                model = Ridge(alpha=self.alpha)
                model.coef_ = self._prev_coef
                model.intercept_ = self._prev_intercept
                model.n_features_in_ = len(self._feature_names)
                self._model = model
                self._is_fallback = True
            else:
                diag.error(
                    source,
                    "No previous weights available for fallback. Model is unfit.",
                )

        return diag

    def predict(self, X: pd.DataFrame) -> tuple[pd.Series, Diagnostics]:
        """Produce composite scores for the feature matrix X.

        AP-8: All values in X must be in [0, 1].

        Raises:
            RuntimeError: If the model has not been fit.
        """
        diag = Diagnostics()
        source = "ridge_model.predict"

        _validate_feature_range(X, source)

        if self._model is None:
            raise RuntimeError("RidgeModel has not been fit yet. Call fit() first.")

        predictions = self._model.predict(X.values)
        result = pd.Series(predictions, index=X.index)

        diag.info(
            source,
            "Ridge prediction completed.",
            n_samples=len(X),
            is_fallback=self._is_fallback,
        )
        return result, diag

    def get_feature_importance(self) -> dict[str, float]:
        """Return normalized absolute coefficient values.

        Returns an empty dict if the model has not been fit.
        """
        if self._model is None or not hasattr(self._model, "coef_"):
            return {}

        abs_coefs = np.abs(self._model.coef_)
        total = abs_coefs.sum()

        if total == 0:
            # All coefficients are zero — equal importance
            n = len(self._feature_names)
            return {name: 1.0 / n for name in self._feature_names}

        normalized = abs_coefs / total
        return dict(zip(self._feature_names, normalized.tolist(), strict=False))

    def get_raw_coefficients(self) -> dict[str, float]:
        """Return signed Ridge coefficients keyed by feature name.

        Unlike ``get_feature_importance`` (which returns normalized absolute
        values and is sign-agnostic), this method preserves the original
        sign. Per RALPH TODO-10 the backtest engine needs access to the
        raw signed weights to emit a WARNING when a price-volume factor
        receives a negative Ridge weight on real data (possible sign-
        convention bug) — the abs/normalized importance hides that signal.

        Returns an empty dict if the model has not been fit.
        """
        if self._model is None or not hasattr(self._model, "coef_"):
            return {}
        return dict(zip(self._feature_names, [float(c) for c in self._model.coef_], strict=False))
