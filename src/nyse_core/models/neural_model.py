"""PyTorch MLP implementation of the CombinationModel protocol.

Uses a simple 2-layer MLP with dropout and Adam optimizer.
Early stopping via validation loss with configurable patience.
Gracefully handles missing torch installation.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from nyse_core.contracts import Diagnostics
from nyse_core.signal_combination import _validate_feature_range

_HOLDOUT_FRACTION = 0.2
_RANDOM_SEED = 42


class NeuralModel:
    """CombinationModel implementation using PyTorch MLP.

    Architecture: Input -> Linear -> ReLU -> Dropout -> Linear -> ReLU -> Dropout -> Linear(1)

    Attributes:
        hidden_dims: Tuple of hidden layer sizes.
        lr: Adam learning rate.
        epochs: Maximum training epochs.
        batch_size: Mini-batch size.
        dropout: Dropout probability.
        weight_decay: L2 regularization for Adam.
    """

    def __init__(
        self,
        hidden_dims: tuple[int, ...] = (32, 16),
        lr: float = 0.001,
        epochs: int = 100,
        batch_size: int = 64,
        dropout: float = 0.2,
        weight_decay: float = 1e-4,
        patience: int = 10,
        **kwargs: object,
    ) -> None:
        self.hidden_dims = hidden_dims
        self.lr = lr
        self.epochs = epochs
        self.batch_size = batch_size
        self.dropout = dropout
        self.weight_decay = weight_decay
        self.patience = patience

        self._model: object | None = None  # torch.nn.Module
        self._feature_names: list[str] = []
        self._feature_importances: dict[str, float] = {}
        self._y_mean: float = 0.0
        self._y_std: float = 1.0
        self._prev_state_dict: dict | None = None
        self._is_fallback: bool = False
        self._n_features: int = 0

    def fit(self, X: pd.DataFrame, y: pd.Series) -> Diagnostics:
        """Train the MLP on feature matrix X and target y.

        AP-8: All values in X must be in [0, 1].
        Standardizes y to zero mean unit variance for training.
        Uses early stopping with patience on 20% holdout.
        Falls back to previous weights on error.
        """
        diag = Diagnostics()
        source = "neural_model.fit"

        _validate_feature_range(X, source)

        try:
            import torch
            import torch.nn as nn
        except ImportError:
            diag.error(
                source,
                "torch is not installed. Install with: pip install 'nyse-trading[ml]'",
            )
            return diag

        self._feature_names = list(X.columns)
        self._n_features = len(self._feature_names)
        self._is_fallback = False

        try:
            torch.manual_seed(_RANDOM_SEED)
            np.random.seed(_RANDOM_SEED)

            # Standardize y
            self._y_mean = float(y.mean())
            self._y_std = float(y.std())
            if self._y_std < 1e-12:
                self._y_std = 1.0
            y_norm = (y.values - self._y_mean) / self._y_std

            # Build model
            model = self._build_mlp(self._n_features, nn)

            # 80/20 split
            n_samples = len(X)
            indices = np.random.RandomState(_RANDOM_SEED).permutation(n_samples)
            split = max(int(n_samples * (1 - _HOLDOUT_FRACTION)), 1)
            train_idx = indices[:split]
            val_idx = indices[split:] if split < n_samples else indices[:1]

            X_train_t = torch.tensor(X.values[train_idx], dtype=torch.float32)
            y_train_t = torch.tensor(y_norm[train_idx], dtype=torch.float32).unsqueeze(1)
            X_val_t = torch.tensor(X.values[val_idx], dtype=torch.float32)
            y_val_t = torch.tensor(y_norm[val_idx], dtype=torch.float32).unsqueeze(1)

            optimizer = torch.optim.Adam(model.parameters(), lr=self.lr, weight_decay=self.weight_decay)
            loss_fn = nn.MSELoss()

            best_val_loss = float("inf")
            patience_counter = 0
            best_state = None

            epoch = 0
            for epoch in range(self.epochs):  # noqa: B007 -- used after loop
                model.train()
                # Mini-batch training
                perm = torch.randperm(len(X_train_t))
                epoch_loss = 0.0
                n_batches = 0

                for start in range(0, len(X_train_t), self.batch_size):
                    batch_idx = perm[start : start + self.batch_size]
                    xb = X_train_t[batch_idx]
                    yb = y_train_t[batch_idx]

                    optimizer.zero_grad()
                    pred = model(xb)
                    loss = loss_fn(pred, yb)
                    loss.backward()
                    optimizer.step()

                    epoch_loss += loss.item()
                    n_batches += 1  # noqa: SIM113

                # Validation loss for early stopping
                model.eval()
                with torch.no_grad():
                    val_pred = model(X_val_t)
                    val_loss = loss_fn(val_pred, y_val_t).item()

                if val_loss < best_val_loss:
                    best_val_loss = val_loss
                    patience_counter = 0
                    best_state = {k: v.clone() for k, v in model.state_dict().items()}
                else:
                    patience_counter += 1
                    if patience_counter >= self.patience:
                        break

            # Restore best weights
            if best_state is not None:
                model.load_state_dict(best_state)

            self._prev_state_dict = {k: v.clone() for k, v in model.state_dict().items()}
            self._model = model

            # Compute gradient-based feature importance on validation set
            self._compute_gradient_importance(model, X_val_t, torch)

            diag.info(
                source,
                "Neural fit completed.",
                n_samples=n_samples,
                n_features=self._n_features,
                epochs_run=epoch + 1,
                best_val_loss=best_val_loss,
                y_mean=self._y_mean,
                y_std=self._y_std,
            )

        except Exception as exc:
            diag.error(
                source,
                f"Neural fit failed: {exc}. Falling back to previous weights.",
                n_samples=len(X),
                n_features=len(self._feature_names),
            )
            if self._prev_state_dict is not None:
                try:
                    model = self._build_mlp(self._n_features, nn)
                    model.load_state_dict(self._prev_state_dict)
                    self._model = model
                    self._is_fallback = True
                except Exception:
                    diag.error(source, "Fallback weight restoration also failed.")
            else:
                diag.error(source, "No previous weights available for fallback.")

        return diag

    def predict(self, X: pd.DataFrame) -> tuple[pd.Series, Diagnostics]:
        """Produce composite scores for the feature matrix X.

        AP-8: All values in X must be in [0, 1].
        Un-normalizes predictions back to original y scale.

        Raises:
            RuntimeError: If the model has not been fit.
        """
        diag = Diagnostics()
        source = "neural_model.predict"

        _validate_feature_range(X, source)

        if self._model is None:
            raise RuntimeError("NeuralModel has not been fit yet. Call fit() first.")

        try:
            import torch
        except ImportError:
            diag.error(source, "torch is not installed.")
            return pd.Series(dtype=float), diag

        self._model.eval()  # type: ignore[union-attr]
        with torch.no_grad():
            X_t = torch.tensor(X.values, dtype=torch.float32)
            pred_norm = self._model(X_t).squeeze(1).numpy()  # type: ignore[union-attr]

        # Un-normalize to original scale
        predictions = pred_norm * self._y_std + self._y_mean
        result = pd.Series(predictions, index=X.index)

        diag.info(
            source,
            "Neural prediction completed.",
            n_samples=len(X),
            is_fallback=self._is_fallback,
        )
        return result, diag

    def get_feature_importance(self) -> dict[str, float]:
        """Return normalized gradient-based feature importance.

        Returns an empty dict if the model has not been fit.
        """
        if not self._feature_importances:
            return {}
        return dict(self._feature_importances)

    def _build_mlp(self, n_features: int, nn: object) -> object:
        """Build the MLP architecture.

        Input -> Linear(h1) -> ReLU -> Dropout -> Linear(h2) -> ReLU -> Dropout -> Linear(1)
        """
        layers = []
        in_dim = n_features

        for h_dim in self.hidden_dims:
            layers.append(nn.Linear(in_dim, h_dim))  # type: ignore[union-attr]
            layers.append(nn.ReLU())  # type: ignore[union-attr]
            layers.append(nn.Dropout(self.dropout))  # type: ignore[union-attr]
            in_dim = h_dim

        layers.append(nn.Linear(in_dim, 1))  # type: ignore[union-attr]
        return nn.Sequential(*layers)  # type: ignore[union-attr]

    def _compute_gradient_importance(self, model: object, X_val: object, torch_module: object) -> None:
        """Compute feature importance via absolute gradient magnitude."""

        model.eval()  # type: ignore[union-attr]
        X_val_grad = X_val.clone().requires_grad_(True)  # type: ignore[union-attr]
        output = model(X_val_grad)  # type: ignore[union-attr]
        output.sum().backward()  # type: ignore[union-attr]

        # Mean absolute gradient per feature
        abs_grads = X_val_grad.grad.abs().mean(dim=0).numpy()  # type: ignore[union-attr]
        total = abs_grads.sum()

        if total == 0:
            n = len(self._feature_names)
            self._feature_importances = {name: 1.0 / n for name in self._feature_names}
        else:
            normalized = abs_grads / total
            self._feature_importances = dict(zip(self._feature_names, normalized.tolist(), strict=False))
