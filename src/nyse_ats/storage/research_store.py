"""DuckDB storage for research/backtest data.

Manages the ``research.duckdb`` database which holds:
- OHLCV price history (upsert-capable)
- Normalized feature matrices per rebalance date
- Walk-forward backtest results with full metrics
- Gate verdicts per factor

All public methods return ``Diagnostics`` or ``(result, Diagnostics)`` tuples,
consistent with the nyse_core contract style.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING, Any

import duckdb
import pandas as pd

from nyse_core.contracts import BacktestResult, Diagnostics
from nyse_core.schema import (
    COL_CLOSE,
    COL_DATE,
    COL_HIGH,
    COL_LOW,
    COL_OPEN,
    COL_SYMBOL,
    COL_VOLUME,
)

if TYPE_CHECKING:
    from pathlib import Path

logger = logging.getLogger(__name__)

_SRC = "storage.research_store"

# ── DDL ──────────────────────────────────────────────────────────────────────

_OHLCV_DDL = f"""
CREATE TABLE IF NOT EXISTS ohlcv (
    {COL_DATE}   DATE NOT NULL,
    {COL_SYMBOL} VARCHAR NOT NULL,
    {COL_OPEN}   DOUBLE NOT NULL,
    {COL_HIGH}   DOUBLE NOT NULL,
    {COL_LOW}    DOUBLE NOT NULL,
    {COL_CLOSE}  DOUBLE NOT NULL,
    {COL_VOLUME} BIGINT NOT NULL,
    PRIMARY KEY ({COL_DATE}, {COL_SYMBOL})
);
"""

_FEATURES_DDL = f"""
CREATE TABLE IF NOT EXISTS features (
    {COL_DATE}   DATE NOT NULL,
    {COL_SYMBOL} VARCHAR NOT NULL,
    factor_name  VARCHAR NOT NULL,
    value        DOUBLE NOT NULL,
    PRIMARY KEY ({COL_DATE}, {COL_SYMBOL}, factor_name)
);
"""

_BACKTEST_DDL = """
CREATE TABLE IF NOT EXISTS backtest_results (
    run_id       VARCHAR PRIMARY KEY,
    timestamp    TIMESTAMP NOT NULL,
    metrics_json VARCHAR NOT NULL
);
"""

_GATE_DDL = """
CREATE TABLE IF NOT EXISTS gate_verdicts (
    factor_name  VARCHAR NOT NULL,
    gate_name    VARCHAR NOT NULL,
    passed       BOOLEAN NOT NULL,
    metric_value DOUBLE NOT NULL,
    timestamp    TIMESTAMP NOT NULL,
    PRIMARY KEY (factor_name, gate_name, timestamp)
);
"""

# Long-format XBRL facts from EDGAR. One row per (filing, metric). `date` is the
# filing_date (PiT key — when the data became public), `period_end` is the
# reporting period the metric describes. `value` is NULLable because XBRL
# parse failures surface as NaN.
_FUNDAMENTALS_DDL = f"""
CREATE TABLE IF NOT EXISTS fundamentals (
    {COL_DATE}   DATE NOT NULL,
    {COL_SYMBOL} VARCHAR NOT NULL,
    metric_name  VARCHAR NOT NULL,
    value        DOUBLE,
    filing_type  VARCHAR,
    period_end   DATE NOT NULL,
    PRIMARY KEY ({COL_DATE}, {COL_SYMBOL}, metric_name, period_end)
);
"""


class ResearchStore:
    """DuckDB-backed store for research and backtest data.

    Args:
        db_path: Path to the DuckDB database file.  Use ``Path(":memory:")``
                 for an ephemeral in-memory database (useful for tests).
    """

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        if str(db_path) != ":memory:":
            db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = duckdb.connect(str(db_path))
        self._create_tables()
        logger.info("ResearchStore initialized: %s", db_path)

    def _create_tables(self) -> None:
        self._conn.execute(_OHLCV_DDL)
        self._conn.execute(_FEATURES_DDL)
        self._conn.execute(_BACKTEST_DDL)
        self._conn.execute(_GATE_DDL)
        self._conn.execute(_FUNDAMENTALS_DDL)

    # ── OHLCV ────────────────────────────────────────────────────────────────

    def store_ohlcv(self, data: pd.DataFrame) -> Diagnostics:
        """Bulk upsert OHLCV data.

        The DataFrame must contain columns: date, symbol, open, high, low, close, volume.
        Existing rows with matching (date, symbol) are replaced.
        """
        diag = Diagnostics()
        required = {COL_DATE, COL_SYMBOL, COL_OPEN, COL_HIGH, COL_LOW, COL_CLOSE, COL_VOLUME}
        missing = required - set(data.columns)
        if missing:
            diag.error(_SRC, f"Missing required columns: {missing}")
            return diag

        if data.empty:
            diag.warning(_SRC, "Empty DataFrame passed to store_ohlcv — nothing stored")
            return diag

        col_order = [COL_DATE, COL_SYMBOL, COL_OPEN, COL_HIGH, COL_LOW, COL_CLOSE, COL_VOLUME]
        subset = data[col_order].copy()
        subset[COL_DATE] = pd.to_datetime(subset[COL_DATE]).dt.date

        n_in = len(subset)

        # Drop rows with NaN in any required column. The ohlcv table has
        # NOT NULL constraints on every column; one NaN row would otherwise
        # abort the whole INSERT (learned the hard way: 962k-row download
        # failed silently because a handful of halted-trading days had NaN
        # volume after pd.to_numeric(errors="coerce")).
        subset = subset.dropna(subset=col_order)
        n_after_nan = len(subset)
        n_dropped_nan = n_in - n_after_nan

        # Drop duplicate (date, symbol) keeping the last row. FinMind
        # occasionally returns overlapping windows at symbol batch boundaries;
        # the INSERT's PRIMARY KEY would otherwise fail.
        subset = subset.drop_duplicates(subset=[COL_DATE, COL_SYMBOL], keep="last")
        n_after_dedupe = len(subset)
        n_dropped_dupe = n_after_nan - n_after_dedupe

        # Cast volume to int64 for the BIGINT column. pd.to_numeric produces
        # float64, which DuckDB will accept only if all values are integral.
        subset[COL_VOLUME] = subset[COL_VOLUME].astype("int64")

        if n_dropped_nan > 0:
            diag.warning(
                _SRC,
                f"Dropped {n_dropped_nan} rows with NaN in required columns "
                f"(would have violated NOT NULL constraint)",
                dropped=n_dropped_nan,
            )
        if n_dropped_dupe > 0:
            diag.warning(
                _SRC,
                f"Dropped {n_dropped_dupe} duplicate (date, symbol) rows",
                dropped=n_dropped_dupe,
            )

        if subset.empty:
            diag.warning(
                _SRC,
                f"All {n_in} input rows were dropped during sanitization — nothing stored",
            )
            return diag

        try:
            self._conn.execute("DELETE FROM ohlcv WHERE (date, symbol) IN (SELECT date, symbol FROM subset)")
            self._conn.execute("INSERT INTO ohlcv SELECT * FROM subset")
            diag.info(
                _SRC,
                f"Stored {len(subset)} OHLCV rows "
                f"(input={n_in}, dropped_nan={n_dropped_nan}, dropped_dupe={n_dropped_dupe})",
                stored=len(subset),
                input_rows=n_in,
            )
        except Exception as exc:
            diag.error(_SRC, f"OHLCV write failed: {exc}")

        return diag

    def load_ohlcv(
        self,
        symbols: list[str],
        start: date,
        end: date,
    ) -> tuple[pd.DataFrame, Diagnostics]:
        """Read OHLCV data for given symbols and date range."""
        diag = Diagnostics()
        empty = pd.DataFrame(
            columns=[COL_DATE, COL_SYMBOL, COL_OPEN, COL_HIGH, COL_LOW, COL_CLOSE, COL_VOLUME]
        )

        if not symbols:
            diag.warning(_SRC, "Empty symbol list — returning empty DataFrame")
            return empty, diag

        try:
            result = self._conn.execute(
                f"""
                SELECT {COL_DATE}, {COL_SYMBOL}, {COL_OPEN}, {COL_HIGH},
                       {COL_LOW}, {COL_CLOSE}, {COL_VOLUME}
                FROM ohlcv
                WHERE {COL_SYMBOL} IN (SELECT UNNEST($1::VARCHAR[]))
                  AND {COL_DATE} >= $2::DATE
                  AND {COL_DATE} <= $3::DATE
                ORDER BY {COL_DATE}, {COL_SYMBOL}
                """,
                [symbols, str(start), str(end)],
            ).fetchdf()
            diag.info(_SRC, f"Loaded {len(result)} OHLCV rows")
            return result, diag
        except Exception as exc:
            diag.error(_SRC, f"OHLCV read failed: {exc}")
            return empty, diag

    # ── Fundamentals (EDGAR XBRL facts, long format) ─────────────────────────

    def store_fundamentals(self, data: pd.DataFrame) -> Diagnostics:
        """Bulk upsert long-format XBRL facts from EDGAR.

        Expected columns: date, symbol, metric_name, value, filing_type, period_end.
        `date` is the filing_date (PiT key). `value` may be NaN (XBRL parse
        failures); filing_type may be empty. Rows with NULL in the PK columns
        (date, symbol, metric_name, period_end) are dropped.
        """
        diag = Diagnostics()
        required = {COL_DATE, COL_SYMBOL, "metric_name", "value", "filing_type", "period_end"}
        missing = required - set(data.columns)
        if missing:
            diag.error(_SRC, f"Missing required columns: {missing}")
            return diag

        if data.empty:
            diag.warning(_SRC, "Empty DataFrame passed to store_fundamentals — nothing stored")
            return diag

        col_order = [COL_DATE, COL_SYMBOL, "metric_name", "value", "filing_type", "period_end"]
        subset = data[col_order].copy()
        subset[COL_DATE] = pd.to_datetime(subset[COL_DATE]).dt.date
        subset["period_end"] = pd.to_datetime(subset["period_end"]).dt.date

        n_in = len(subset)

        # Drop rows with NULL in PK columns — these would violate NOT NULL. NaN
        # in `value` is allowed (maps to SQL NULL) because XBRL parse failures
        # legitimately produce missing metric values.
        pk_cols = [COL_DATE, COL_SYMBOL, "metric_name", "period_end"]
        subset = subset.dropna(subset=pk_cols)
        n_after_nan = len(subset)
        n_dropped_nan = n_in - n_after_nan

        # Dedupe on PK. EDGAR may return the same filing twice across overlapping
        # windows; the PRIMARY KEY would otherwise fail the INSERT.
        subset = subset.drop_duplicates(subset=pk_cols, keep="last")
        n_after_dedupe = len(subset)
        n_dropped_dupe = n_after_nan - n_after_dedupe

        # Coerce value to numeric. pd.to_numeric with errors="coerce" turns
        # unparseable strings (shouldn't happen, but defense-in-depth) into NaN,
        # which DuckDB writes as NULL in the DOUBLE column.
        subset["value"] = pd.to_numeric(subset["value"], errors="coerce")

        if n_dropped_nan > 0:
            diag.warning(
                _SRC,
                f"Dropped {n_dropped_nan} fundamentals rows with NULL in PK columns",
                dropped=n_dropped_nan,
            )
        if n_dropped_dupe > 0:
            diag.warning(
                _SRC,
                f"Dropped {n_dropped_dupe} duplicate fundamentals PK rows",
                dropped=n_dropped_dupe,
            )

        if subset.empty:
            diag.warning(
                _SRC,
                f"All {n_in} fundamentals input rows dropped during sanitization",
            )
            return diag

        try:
            self._conn.execute(
                "DELETE FROM fundamentals "
                "WHERE (date, symbol, metric_name, period_end) IN "
                "(SELECT date, symbol, metric_name, period_end FROM subset)"
            )
            self._conn.execute("INSERT INTO fundamentals SELECT * FROM subset")
            diag.info(
                _SRC,
                f"Stored {len(subset)} fundamentals rows "
                f"(input={n_in}, dropped_nan={n_dropped_nan}, dropped_dupe={n_dropped_dupe})",
                stored=len(subset),
                input_rows=n_in,
            )
        except Exception as exc:
            diag.error(_SRC, f"Fundamentals write failed: {exc}")

        return diag

    def load_fundamentals(
        self,
        symbols: list[str],
        start: date,
        end: date,
        metric_names: list[str] | None = None,
    ) -> tuple[pd.DataFrame, Diagnostics]:
        """Read fundamentals for given symbols/filing-date range.

        `start`/`end` filter on filing date (the PiT key), not period_end, so
        downstream consumers can reconstruct the "what was known on this date"
        view without leakage. `metric_names=None` returns every metric.
        """
        diag = Diagnostics()
        cols = [COL_DATE, COL_SYMBOL, "metric_name", "value", "filing_type", "period_end"]
        empty = pd.DataFrame(columns=cols)

        if not symbols:
            diag.warning(_SRC, "Empty symbol list — returning empty DataFrame")
            return empty, diag

        try:
            if metric_names:
                result = self._conn.execute(
                    f"""
                    SELECT {COL_DATE}, {COL_SYMBOL}, metric_name, value,
                           filing_type, period_end
                    FROM fundamentals
                    WHERE {COL_SYMBOL} IN (SELECT UNNEST($1::VARCHAR[]))
                      AND metric_name IN (SELECT UNNEST($2::VARCHAR[]))
                      AND {COL_DATE} >= $3::DATE
                      AND {COL_DATE} <= $4::DATE
                    ORDER BY {COL_DATE}, {COL_SYMBOL}, metric_name
                    """,
                    [symbols, metric_names, str(start), str(end)],
                ).fetchdf()
            else:
                result = self._conn.execute(
                    f"""
                    SELECT {COL_DATE}, {COL_SYMBOL}, metric_name, value,
                           filing_type, period_end
                    FROM fundamentals
                    WHERE {COL_SYMBOL} IN (SELECT UNNEST($1::VARCHAR[]))
                      AND {COL_DATE} >= $2::DATE
                      AND {COL_DATE} <= $3::DATE
                    ORDER BY {COL_DATE}, {COL_SYMBOL}, metric_name
                    """,
                    [symbols, str(start), str(end)],
                ).fetchdf()
            diag.info(_SRC, f"Loaded {len(result)} fundamentals rows")
            return result, diag
        except Exception as exc:
            diag.error(_SRC, f"Fundamentals read failed: {exc}")
            return empty, diag

    # ── Features ─────────────────────────────────────────────────────────────

    def store_features(self, data: pd.DataFrame, rebalance_date: date) -> Diagnostics:
        """Bulk upsert feature values for a single rebalance date.

        The DataFrame must contain columns: date, symbol, factor_name, value.
        """
        diag = Diagnostics()
        required = {COL_DATE, COL_SYMBOL, "factor_name", "value"}
        missing = required - set(data.columns)
        if missing:
            diag.error(_SRC, f"Missing required columns: {missing}")
            return diag

        if data.empty:
            diag.warning(_SRC, "Empty DataFrame passed to store_features — nothing stored")
            return diag

        col_order = [COL_DATE, COL_SYMBOL, "factor_name", "value"]
        subset = data[col_order].copy()
        subset[COL_DATE] = pd.to_datetime(subset[COL_DATE]).dt.date

        try:
            self._conn.execute(
                "DELETE FROM features WHERE (date, symbol, factor_name) "
                "IN (SELECT date, symbol, factor_name FROM subset)"
            )
            self._conn.execute("INSERT INTO features SELECT * FROM subset")
            diag.info(
                _SRC,
                f"Stored {len(subset)} feature rows for rebalance_date={rebalance_date}",
            )
        except Exception as exc:
            diag.error(_SRC, f"Feature write failed: {exc}")

        return diag

    def load_features(self, rebalance_date: date) -> tuple[pd.DataFrame, Diagnostics]:
        """Read all feature values for a single rebalance date."""
        diag = Diagnostics()
        empty = pd.DataFrame(columns=[COL_DATE, COL_SYMBOL, "factor_name", "value"])

        try:
            result = self._conn.execute(
                f"""
                SELECT {COL_DATE}, {COL_SYMBOL}, factor_name, value
                FROM features
                WHERE {COL_DATE} = $1::DATE
                ORDER BY {COL_SYMBOL}, factor_name
                """,
                [str(rebalance_date)],
            ).fetchdf()
            diag.info(_SRC, f"Loaded {len(result)} feature rows for {rebalance_date}")
            return result, diag
        except Exception as exc:
            diag.error(_SRC, f"Feature read failed: {exc}")
            return empty, diag

    # ── Backtest Results ─────────────────────────────────────────────────────

    def store_backtest_result(self, result: BacktestResult, run_id: str) -> Diagnostics:
        """Persist a backtest result under the given run_id."""
        diag = Diagnostics()

        metrics: dict[str, Any] = {
            "oos_sharpe": result.oos_sharpe,
            "oos_cagr": result.oos_cagr,
            "max_drawdown": result.max_drawdown,
            "annual_turnover": result.annual_turnover,
            "cost_drag_pct": result.cost_drag_pct,
            "per_fold_sharpe": result.per_fold_sharpe,
            "per_factor_contribution": result.per_factor_contribution,
            "permutation_p_value": result.permutation_p_value,
            "bootstrap_ci_lower": result.bootstrap_ci_lower,
            "bootstrap_ci_upper": result.bootstrap_ci_upper,
            "romano_wolf_p_values": result.romano_wolf_p_values,
        }
        if result.daily_returns is not None:
            metrics["daily_returns_values"] = result.daily_returns.tolist()
            idx = result.daily_returns.index
            if isinstance(idx, pd.DatetimeIndex):
                metrics["daily_returns_index"] = [d.isoformat() for d in idx]
                metrics["daily_returns_index_type"] = "datetime"
            else:
                metrics["daily_returns_index"] = list(idx)
                metrics["daily_returns_index_type"] = "other"

        try:
            self._conn.execute(
                """
                INSERT INTO backtest_results (run_id, timestamp, metrics_json)
                VALUES ($1, $2, $3)
                ON CONFLICT (run_id) DO UPDATE SET
                    timestamp = EXCLUDED.timestamp,
                    metrics_json = EXCLUDED.metrics_json
                """,
                [run_id, datetime.now(UTC), json.dumps(metrics)],
            )
            diag.info(_SRC, f"Stored backtest result run_id={run_id}")
        except Exception as exc:
            diag.error(_SRC, f"Backtest write failed: {exc}")

        return diag

    def load_backtest_result(
        self,
        run_id: str,
    ) -> tuple[BacktestResult | None, Diagnostics]:
        """Load a backtest result by run_id. Returns None if not found."""
        diag = Diagnostics()

        try:
            rows = self._conn.execute(
                "SELECT metrics_json FROM backtest_results WHERE run_id = $1",
                [run_id],
            ).fetchall()

            if not rows:
                diag.warning(_SRC, f"No backtest result found for run_id={run_id}")
                return None, diag

            metrics: dict = json.loads(rows[0][0])

            daily_values = metrics.get("daily_returns_values", [])
            daily_index = metrics.get("daily_returns_index")
            idx_type = metrics.get("daily_returns_index_type", "other")
            if daily_index is not None and idx_type == "datetime":
                daily_returns = pd.Series(
                    daily_values,
                    index=pd.to_datetime(daily_index, format="ISO8601"),
                )
            else:
                daily_returns = pd.Series(daily_values, dtype=float)

            bt = BacktestResult(
                daily_returns=daily_returns,
                oos_sharpe=metrics["oos_sharpe"],
                oos_cagr=metrics["oos_cagr"],
                max_drawdown=metrics["max_drawdown"],
                annual_turnover=metrics["annual_turnover"],
                cost_drag_pct=metrics["cost_drag_pct"],
                per_fold_sharpe=metrics["per_fold_sharpe"],
                per_factor_contribution=metrics["per_factor_contribution"],
                permutation_p_value=metrics.get("permutation_p_value"),
                bootstrap_ci_lower=metrics.get("bootstrap_ci_lower"),
                bootstrap_ci_upper=metrics.get("bootstrap_ci_upper"),
                romano_wolf_p_values=metrics.get("romano_wolf_p_values"),
            )
            diag.info(_SRC, f"Loaded backtest result run_id={run_id}")
            return bt, diag

        except Exception as exc:
            diag.error(_SRC, f"Backtest read failed: {exc}")
            return None, diag

    # ── Gate Verdicts ────────────────────────────────────────────────────────

    def write_gate_verdict(self, factor_name: str, gate_results: dict[str, Any]) -> Diagnostics:
        """Record gate verdicts for a factor.

        Args:
            factor_name: Name of the factor evaluated.
            gate_results: Dict mapping gate_name to
                ``{"passed": bool, "metric_value": float}``.
        """
        diag = Diagnostics()
        now = datetime.now(UTC)
        try:
            for gate_name, info in gate_results.items():
                self._conn.execute(
                    """
                    INSERT INTO gate_verdicts
                        (factor_name, gate_name, passed, metric_value, timestamp)
                    VALUES ($1, $2, $3, $4, $5)
                    """,
                    [
                        factor_name,
                        gate_name,
                        bool(info["passed"]),
                        float(info["metric_value"]),
                        now,
                    ],
                )
            diag.info(_SRC, f"Wrote {len(gate_results)} gate verdicts for factor={factor_name}")
        except Exception as exc:
            diag.error(_SRC, f"Gate verdict write failed: {exc}")

        return diag

    def read_gate_verdicts(self, factor_name: str | None = None) -> pd.DataFrame:
        """Read gate verdicts, optionally filtered by factor name."""
        if factor_name is None:
            return self._conn.execute(
                """
                SELECT factor_name, gate_name, passed, metric_value, timestamp
                FROM gate_verdicts
                ORDER BY timestamp DESC, factor_name, gate_name
                """
            ).fetchdf()
        else:
            return self._conn.execute(
                """
                SELECT factor_name, gate_name, passed, metric_value, timestamp
                FROM gate_verdicts
                WHERE factor_name = $1
                ORDER BY timestamp DESC, gate_name
                """,
                [factor_name],
            ).fetchdf()

    # ── Lifecycle ────────────────────────────────────────────────────────────

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()
        logger.info("ResearchStore closed: %s", self._db_path)

    def __enter__(self) -> ResearchStore:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
