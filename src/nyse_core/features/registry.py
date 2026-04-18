"""Factor Registry — single source of truth for all registered alpha factors.

Enforces anti-pattern AP-3: no factor may appear in both SIGNAL and RISK domains
(DoubleDipError). Manages sign conventions so individual compute functions stay pure.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import pandas as pd

from nyse_core.contracts import Diagnostics
from nyse_core.schema import UsageDomain

if TYPE_CHECKING:
    from collections.abc import Callable
    from datetime import date


class DoubleDipError(Exception):
    """AP-3: A factor was registered for both SIGNAL and RISK domains."""


@dataclass(frozen=True)
class FactorEntry:
    """Immutable descriptor for a registered factor."""

    name: str
    compute_fn: Callable[[pd.DataFrame], tuple[pd.Series, Diagnostics]]
    usage_domain: UsageDomain
    sign_convention: int  # +1 = high is buy, -1 = low is buy
    description: str
    data_source: str = "ohlcv"  # which dataset this factor requires


class FactorRegistry:
    """Central registry for alpha factors with domain enforcement.

    Responsibilities:
      1. Register factors with domain + sign convention metadata.
      2. Prevent double-dip (same factor in SIGNAL and RISK).
      3. Run all registered compute functions and apply sign inversion.
    """

    def __init__(self) -> None:
        self._factors: dict[str, FactorEntry] = {}
        self._domain_map: dict[str, UsageDomain] = {}

    def register(
        self,
        name: str,
        compute_fn: Callable[[pd.DataFrame], tuple[pd.Series, Diagnostics]],
        usage_domain: UsageDomain,
        sign_convention: int,
        description: str = "",
        data_source: str = "ohlcv",
    ) -> None:
        """Register a factor.

        Note: This is a mutator method that modifies registry state.
        It does NOT return (result, Diagnostics) because registration
        is a setup-time operation, not a data-processing step.
        Errors are raised as exceptions, not captured in Diagnostics.

        Raises:
            ValueError: If a factor with `name` is already registered.
            DoubleDipError: If the same factor base name appears in both
                           SIGNAL and RISK domains (AP-3).
        """
        if name in self._factors:
            raise ValueError(f"Factor '{name}' is already registered.")

        # AP-3: check double-dip — same base name in opposite domain
        existing_domain = self._domain_map.get(name)
        if existing_domain is not None and existing_domain != usage_domain:
            raise DoubleDipError(
                f"Factor '{name}' already registered in domain "
                f"{existing_domain.value}; cannot also register in "
                f"{usage_domain.value} (anti-pattern AP-3)."
            )

        entry = FactorEntry(
            name=name,
            compute_fn=compute_fn,
            usage_domain=usage_domain,
            sign_convention=sign_convention,
            description=description,
            data_source=data_source,
        )
        self._factors[name] = entry
        self._domain_map[name] = usage_domain

    def get_signal_factors(self) -> list[str]:
        """Return names of factors in the SIGNAL domain."""
        return [name for name, entry in self._factors.items() if entry.usage_domain == UsageDomain.SIGNAL]

    def get_risk_factors(self) -> list[str]:
        """Return names of factors in the RISK domain."""
        return [name for name, entry in self._factors.items() if entry.usage_domain == UsageDomain.RISK]

    def compute_all(
        self,
        data: pd.DataFrame | dict[str, pd.DataFrame],
        rebalance_date: date,
    ) -> tuple[pd.DataFrame, Diagnostics]:
        """Run every registered compute_fn and assemble a feature matrix.

        Parameters
        ----------
        data : pd.DataFrame | dict[str, pd.DataFrame]
            Either a single DataFrame (backwards compatible — treated as "ohlcv")
            or a dict keyed by data source name (e.g. ``{"ohlcv": ...,
            "fundamentals": ..., "short_interest": ...}``).  Each factor's
            ``data_source`` field determines which key it reads from.
        rebalance_date : date
            The as-of date for feature computation.

        For factors with sign_convention == -1 the raw values are negated so
        that a higher value always means 'buy' in the returned matrix.

        Returns
        -------
        tuple[pd.DataFrame, Diagnostics]
            (feature_matrix, diagnostics).
        """
        diag = Diagnostics()
        results: dict[str, pd.Series] = {}

        # Normalise input to dict form
        if isinstance(data, pd.DataFrame):
            data_sources: dict[str, pd.DataFrame] = {"ohlcv": data}
        else:
            data_sources = data

        for name, entry in self._factors.items():
            src_key = entry.data_source
            if src_key not in data_sources:
                diag.warning(
                    "registry.compute_all",
                    f"Factor '{name}' requires data source '{src_key}' which was not provided — skipping.",
                    factor=name,
                    missing_source=src_key,
                )
                continue

            try:
                series, factor_diag = entry.compute_fn(data_sources[src_key])
            except Exception as exc:
                diag.error(
                    "registry.compute_all",
                    f"Factor '{name}' computation raised {type(exc).__name__}: {exc} — skipping.",
                    factor=name,
                    exception_type=type(exc).__name__,
                    exception_msg=str(exc),
                )
                continue
            diag.merge(factor_diag)

            # Apply sign inversion so downstream always sees +1 convention
            if entry.sign_convention == -1:
                series = -series
                diag.info(
                    "registry.compute_all",
                    f"Inverted sign for factor '{name}' (sign_convention=-1).",
                    factor=name,
                )

            results[name] = series

        feature_df = pd.DataFrame(results)
        diag.info(
            "registry.compute_all",
            "Feature matrix assembled.",
            n_factors=len(results),
            n_rows=len(feature_df),
            rebalance_date=str(rebalance_date),
            data_sources=list(data_sources.keys()),
        )
        return feature_df, diag
