"""LightGBM implementation of the CombinationModel protocol.

Uses lightgbm.LGBMRegressor with early stopping on a holdout split.
Falls back to previous model state if training errors occur.
Gracefully handles missing lightgbm installation.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from nyse_core.contracts import Diagnostics
from nyse_core.signal_combination import _validate_feature_range

_MIN_SAMPLES_FOR_EARLY_STOPPING = 20
_EARLY_STOPPING_ROUNDS = 10
_HOLDOUT_FRACTION = 0.2
_RANDOM_SEED = 42


class GBMModel:
    """CombinationModel implementation using LightGBM.

    Attributes:
        n_estimators: Number of boosting rounds.
        max_depth: Maximum tree depth.
        learning_rate: Step size shrinkage.
        min_child_samples: Minimum samples per leaf.
        subsample: Row subsampling ratio per tree.
        reg_lambda: L2 regularization strength.
    """

    def __init__(
        self,
        n_estimators: int = 100,
        max_depth: int = 3,
        learning_rate: float = 0.1,
        min_child_samples: int = 5,
        subsample: float = 0.8,
        reg_lambda: float = 1.0,
        **kwargs: object,
    ) -> None:
        self.n_estimators = n_estimators
        self.max_depth = max_depth
        self.learning_rate = learning_rate
        self.min_child_samples = min_child_samples
        self.subsample = subsample
        self.reg_lambda = reg_lambda

        self._model: object | None = None
        self._feature_names: list[str] = []
        self._feature_importances: dict[str, float] = {}
        self._prev_model: object | None = None
        self._is_fallback: bool = False

    def fit(self, X: pd.DataFrame, y: pd.Series) -> Diagnostics:
        """Train the GBM model on feature matrix X and target y.

        AP-8: All values in X must be in [0, 1].
        Uses early stopping with 20% holdout when >= 20 samples.
        Falls back to previous model on error.
        """
        diag = Diagnostics()
        source = "gbm_model.fit"

        _validate_feature_range(X, source)

        try:
            import lightgbm as lgb
        except ImportError:
            diag.error(
                source,
                "lightgbm is not installed. Install with: pip install 'nyse-trading[ml]'",
            )
            return diag

        self._feature_names = list(X.columns)
        self._is_fallback = False

        try:
            model = lgb.LGBMRegressor(
                n_estimators=self.n_estimators,
                max_depth=self.max_depth,
                learning_rate=self.learning_rate,
                min_child_samples=self.min_child_samples,
                subsample=self.subsample,
                reg_lambda=self.reg_lambda,
                random_state=_RANDOM_SEED,
                verbose=-1,
            )

            n_samples = len(X)

            if n_samples >= _MIN_SAMPLES_FOR_EARLY_STOPPING:
                # 80/20 split for early stopping
                rng = np.random.RandomState(_RANDOM_SEED)
                indices = rng.permutation(n_samples)
                split = int(n_samples * (1 - _HOLDOUT_FRACTION))
                train_idx = indices[:split]
                val_idx = indices[split:]

                X_train, y_train = X.iloc[train_idx], y.iloc[train_idx]
                X_val, y_val = X.iloc[val_idx], y.iloc[val_idx]

                model.fit(
                    X_train.values,
                    y_train.values,
                    eval_set=[(X_val.values, y_val.values)],
                    callbacks=[lgb.early_stopping(_EARLY_STOPPING_ROUNDS, verbose=False)],
                )

                diag.info(
                    source,
                    "GBM fit completed with early stopping.",
                    n_samples=n_samples,
                    n_train=len(train_idx),
                    n_val=len(val_idx),
                    n_features=len(self._feature_names),
                    best_iteration=model.best_iteration_,
                )
            else:
                # Too few samples for holdout — fit on all data
                model.fit(X.values, y.values)

                diag.info(
                    source,
                    "GBM fit completed without early stopping (small dataset).",
                    n_samples=n_samples,
                    n_features=len(self._feature_names),
                )

            # Store model and feature importances (gain-based)
            self._prev_model = model
            self._model = model
            self._store_feature_importances(model)

        except Exception as exc:
            diag.error(
                source,
                f"GBM fit failed: {exc}. Falling back to previous model.",
                n_samples=len(X),
                n_features=len(self._feature_names),
            )
            if self._prev_model is not None:
                self._model = self._prev_model
                self._is_fallback = True
            else:
                diag.error(source, "No previous model available for fallback.")

        return diag

    def predict(self, X: pd.DataFrame) -> tuple[pd.Series, Diagnostics]:
        """Produce composite scores for the feature matrix X.

        AP-8: All values in X must be in [0, 1].

        Raises:
            RuntimeError: If the model has not been fit.
        """
        diag = Diagnostics()
        source = "gbm_model.predict"

        _validate_feature_range(X, source)

        if self._model is None:
            raise RuntimeError("GBMModel has not been fit yet. Call fit() first.")

        predictions = self._model.predict(X.values)  # type: ignore[union-attr]
        result = pd.Series(predictions, index=X.index)

        diag.info(
            source,
            "GBM prediction completed.",
            n_samples=len(X),
            is_fallback=self._is_fallback,
        )
        return result, diag

    def get_feature_importance(self) -> dict[str, float]:
        """Return normalized gain-based feature importance.

        Returns an empty dict if the model has not been fit.
        """
        if not self._feature_importances:
            return {}
        return dict(self._feature_importances)

    def _store_feature_importances(self, model: object) -> None:
        """Extract and normalize gain-based importance from fitted model."""
        raw = np.array(model.feature_importances_)  # type: ignore[union-attr]
        total = raw.sum()

        if total == 0:
            n = len(self._feature_names)
            self._feature_importances = {name: 1.0 / n for name in self._feature_names}
        else:
            normalized = raw / total
            self._feature_importances = dict(zip(self._feature_names, normalized.tolist(), strict=False))
