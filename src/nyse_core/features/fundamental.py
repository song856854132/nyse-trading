"""Fundamental factor computations — Piotroski, accruals, profitability.

All functions accept a long-format DataFrame of raw XBRL facts (as produced by
``nyse_ats.data.edgar_adapter.EdgarAdapter.fetch`` and stored via
``ResearchStore.store_fundamentals``) with columns:

    date, symbol, metric_name, value, filing_type, period_end

``date`` is the filing date (PiT key). ``period_end`` is the reporting period
these facts cover. For each symbol, the computations identify the most recent
filing ("current") and the nearest filing from ~1 year earlier ("prior"), and
derive factor values by combining fields across the two.

Sign conventions are documented but NOT applied here — the FactorRegistry
handles inversion (low accruals → buy is applied by sign_convention=-1).

PiT discipline: callers are responsible for passing in only facts available at
the rebalance date. ``load_fundamentals(start, end)`` filters on filing date
(not period_end), so feeding its output directly here is leak-safe.
"""

from __future__ import annotations

import pandas as pd

from nyse_core.contracts import Diagnostics
from nyse_core.schema import COL_SYMBOL

# Approximate "same quarter a year ago" window. Quarters don't land on identical
# calendar dates across years (leap years, company fiscal shifts) so we accept
# any filing whose period_end falls 300–400 days before the current one.
_PRIOR_WINDOW_MIN_DAYS = 300
_PRIOR_WINDOW_MAX_DAYS = 400
_PRIOR_TARGET_DAYS = 365


def _pivot_symbol_facts(raw_facts: pd.DataFrame, symbol: str) -> pd.DataFrame:
    """Return wide frame indexed by period_end, columns = metric_name.

    Empty DataFrame if symbol has no rows. Duplicate (period_end, metric_name)
    entries keep the last by filing date — this matters when an annual filing
    re-states a prior quarter's numbers.
    """
    sub = raw_facts[raw_facts[COL_SYMBOL] == symbol]
    if sub.empty:
        return pd.DataFrame()
    wide = sub.pivot_table(
        index="period_end",
        columns="metric_name",
        values="value",
        aggfunc="last",
    )
    return wide.sort_index()


def _current_and_prior(
    wide: pd.DataFrame,
) -> tuple[pd.Series | None, pd.Series | None]:
    """Given a symbol's period_end-indexed wide frame, return (current, prior).

    ``current`` is the row with the latest period_end. ``prior`` is the row
    whose period_end falls ~1 year earlier (300–400 day window). ``prior`` is
    None if no such filing exists.
    """
    if wide.empty:
        return None, None
    current_pe = wide.index[-1]
    current = wide.loc[current_pe]
    target = current_pe - pd.Timedelta(days=_PRIOR_TARGET_DAYS)
    lower = current_pe - pd.Timedelta(days=_PRIOR_WINDOW_MAX_DAYS)
    upper = current_pe - pd.Timedelta(days=_PRIOR_WINDOW_MIN_DAYS)
    candidates = [pe for pe in wide.index if lower <= pe <= upper]
    if not candidates:
        return current, None
    prior_pe = min(candidates, key=lambda pe: abs((pe - target).days))
    return current, wide.loc[prior_pe]


def _safe_div(numerator: float, denominator: float) -> float:
    """Return numerator/denominator, or NaN if either operand is NaN / zero."""
    if pd.isna(numerator) or pd.isna(denominator) or denominator == 0:
        return float("nan")
    return float(numerator) / float(denominator)


def _get(row: pd.Series | None, key: str) -> float:
    """Safe lookup: NaN if row is None or column is absent."""
    if row is None:
        return float("nan")
    val = row.get(key, float("nan"))
    return float(val) if pd.notna(val) else float("nan")


def _gross_profit(row: pd.Series | None) -> float:
    """Return gross_profit, deriving it from revenue - cost_of_revenue if absent."""
    gp = _get(row, "gross_profit")
    if not pd.isna(gp):
        return gp
    rev = _get(row, "revenue")
    cor = _get(row, "cost_of_revenue")
    if pd.isna(rev) or pd.isna(cor):
        return float("nan")
    return rev - cor


def _normalize_raw_facts(raw_facts: pd.DataFrame) -> pd.DataFrame:
    """Coerce period_end to pd.Timestamp so date arithmetic works downstream."""
    if raw_facts.empty:
        return raw_facts
    out = raw_facts.copy()
    out["period_end"] = pd.to_datetime(out["period_end"])
    return out


# ── Piotroski F-score ───────────────────────────────────────────────────────


def compute_piotroski_f_score(
    raw_facts: pd.DataFrame,
) -> tuple[pd.Series, Diagnostics]:
    """Piotroski F-score (0–9) from raw XBRL facts.

    Scores the nine Piotroski (2000) binary signals:

      Profitability (4):
        F1  ROA > 0               (net_income / total_assets)
        F2  CFO > 0                (operating_cash_flow)
        F3  ΔROA > 0               (this year vs prior-year same period)
        F4  CFO > NI              (earnings quality)
      Leverage / liquidity (3):
        F5  ΔLeverage ≤ 0         (long_term_debt / total_assets)
        F6  ΔCurrentRatio > 0     (current_assets / current_liabilities)
        F7  No new shares issued  (shares_outstanding)
      Operating efficiency (2):
        F8  ΔGrossMargin > 0      (gross_profit / revenue)
        F9  ΔAssetTurnover > 0    (revenue / total_assets)

    When a metric required for a signal is missing, that signal evaluates to 0
    (conservative). When the prior-year filing itself is missing, the score is
    NaN because five of nine signals can't be evaluated at all.

    Sign convention: +1 (high F-score = buy).
    """
    diag = Diagnostics()
    source = "fundamental.compute_piotroski_f_score"

    if raw_facts.empty:
        diag.warning(source, "Empty raw_facts DataFrame — returning empty Series")
        s = pd.Series(dtype=float, name="piotroski_f_score")
        s.index.name = COL_SYMBOL
        return s, diag

    facts = _normalize_raw_facts(raw_facts)
    results: dict[str, float] = {}
    n_no_prior = 0
    n_no_current = 0

    for symbol in facts[COL_SYMBOL].unique():
        wide = _pivot_symbol_facts(facts, symbol)
        current, prior = _current_and_prior(wide)

        if current is None:
            n_no_current += 1
            results[symbol] = float("nan")
            continue
        if prior is None:
            n_no_prior += 1
            results[symbol] = float("nan")
            continue

        # Fetch raw metrics
        ni_c = _get(current, "net_income")
        ni_p = _get(prior, "net_income")
        ta_c = _get(current, "total_assets")
        ta_p = _get(prior, "total_assets")
        cfo_c = _get(current, "operating_cash_flow")
        ltd_c = _get(current, "long_term_debt")
        ltd_p = _get(prior, "long_term_debt")
        ca_c = _get(current, "current_assets")
        ca_p = _get(prior, "current_assets")
        cl_c = _get(current, "current_liabilities")
        cl_p = _get(prior, "current_liabilities")
        sh_c = _get(current, "shares_outstanding")
        sh_p = _get(prior, "shares_outstanding")
        rev_c = _get(current, "revenue")
        rev_p = _get(prior, "revenue")

        # Derived ratios
        roa_c = _safe_div(ni_c, ta_c)
        roa_p = _safe_div(ni_p, ta_p)
        lev_c = _safe_div(ltd_c, ta_c)
        lev_p = _safe_div(ltd_p, ta_p)
        cr_c = _safe_div(ca_c, cl_c)
        cr_p = _safe_div(ca_p, cl_p)
        gm_c = _safe_div(_gross_profit(current), rev_c)
        gm_p = _safe_div(_gross_profit(prior), rev_p)
        tr_c = _safe_div(rev_c, ta_c)
        tr_p = _safe_div(rev_p, ta_p)

        # Signals (NaN → 0)
        def sig(cond: bool) -> int:
            return 1 if cond else 0

        f1 = sig(pd.notna(roa_c) and roa_c > 0)
        f2 = sig(pd.notna(cfo_c) and cfo_c > 0)
        f3 = sig(pd.notna(roa_c) and pd.notna(roa_p) and roa_c > roa_p)
        f4 = sig(pd.notna(cfo_c) and pd.notna(ni_c) and cfo_c > ni_c)
        f5 = sig(pd.notna(lev_c) and pd.notna(lev_p) and lev_c <= lev_p)
        f6 = sig(pd.notna(cr_c) and pd.notna(cr_p) and cr_c > cr_p)
        f7 = sig(pd.notna(sh_c) and pd.notna(sh_p) and sh_c <= sh_p)
        f8 = sig(pd.notna(gm_c) and pd.notna(gm_p) and gm_c > gm_p)
        f9 = sig(pd.notna(tr_c) and pd.notna(tr_p) and tr_c > tr_p)

        results[symbol] = float(f1 + f2 + f3 + f4 + f5 + f6 + f7 + f8 + f9)

    series = pd.Series(results, name="piotroski_f_score")
    series.index.name = COL_SYMBOL

    diag.info(
        source,
        "Cross-sectional Piotroski F-score computed from raw XBRL facts.",
        n_symbols=len(results),
        n_no_current=n_no_current,
        n_no_prior=n_no_prior,
    )
    return series, diag


# ── Accruals (Collins–Hribar 2002 operating accruals) ───────────────────────


def compute_accruals(raw_facts: pd.DataFrame) -> tuple[pd.Series, Diagnostics]:
    """Operating accruals = (net_income − operating_cash_flow) / avg_assets.

    Uses the Collins–Hribar (2002) cash-flow-statement definition rather than
    Sloan (1996) balance-sheet working-capital deltas — simpler and directly
    supported by two XBRL tags we already parse.

    ``avg_assets`` is the mean of current and prior-year total assets when both
    are available; falls back to current-period total_assets otherwise. NaN if
    any operand is missing.

    Sign convention: −1 (low accruals = buy). The FactorRegistry applies the
    negation, so callers of ``compute_all`` see "higher is better" downstream.
    """
    diag = Diagnostics()
    source = "fundamental.compute_accruals"

    if raw_facts.empty:
        diag.warning(source, "Empty raw_facts DataFrame — returning empty Series")
        s = pd.Series(dtype=float, name="accruals")
        s.index.name = COL_SYMBOL
        return s, diag

    facts = _normalize_raw_facts(raw_facts)
    results: dict[str, float] = {}

    for symbol in facts[COL_SYMBOL].unique():
        wide = _pivot_symbol_facts(facts, symbol)
        current, prior = _current_and_prior(wide)
        if current is None:
            results[symbol] = float("nan")
            continue

        ni = _get(current, "net_income")
        cfo = _get(current, "operating_cash_flow")
        ta_c = _get(current, "total_assets")
        ta_p = _get(prior, "total_assets")

        avg_assets = (ta_c + ta_p) / 2.0 if pd.notna(ta_p) and pd.notna(ta_c) else ta_c

        if pd.isna(ni) or pd.isna(cfo) or pd.isna(avg_assets) or avg_assets == 0:
            results[symbol] = float("nan")
            continue

        results[symbol] = float((ni - cfo) / avg_assets)

    series = pd.Series(results, name="accruals")
    series.index.name = COL_SYMBOL

    diag.info(
        source,
        "Cross-sectional accruals (Collins–Hribar) computed from raw XBRL facts.",
        n_symbols=len(results),
    )
    return series, diag


# ── Gross profitability (Novy-Marx 2013) ─────────────────────────────────────


def compute_profitability(
    raw_facts: pd.DataFrame,
) -> tuple[pd.Series, Diagnostics]:
    """Gross profitability = gross_profit / total_assets (Novy-Marx 2013).

    Uses the asset-scaled gross profit definition rather than Fama–French
    (2015) book-equity scaling — avoids the extra tags (SG&A, interest, book
    equity) that our XBRL extraction doesn't currently pull, at the cost of
    slight construct drift. Literature shows gross profitability captures most
    of the "profitability premium" on its own.

    Derives gross_profit as (revenue − cost_of_revenue) when the direct
    GrossProfit tag is absent.

    Sign convention: +1 (high profitability = buy).
    """
    diag = Diagnostics()
    source = "fundamental.compute_profitability"

    if raw_facts.empty:
        diag.warning(source, "Empty raw_facts DataFrame — returning empty Series")
        s = pd.Series(dtype=float, name="operating_profitability")
        s.index.name = COL_SYMBOL
        return s, diag

    facts = _normalize_raw_facts(raw_facts)
    results: dict[str, float] = {}

    for symbol in facts[COL_SYMBOL].unique():
        wide = _pivot_symbol_facts(facts, symbol)
        current, _prior = _current_and_prior(wide)
        if current is None:
            results[symbol] = float("nan")
            continue

        gp = _gross_profit(current)
        ta = _get(current, "total_assets")

        if pd.isna(gp) or pd.isna(ta) or ta == 0:
            results[symbol] = float("nan")
            continue

        results[symbol] = float(gp / ta)

    series = pd.Series(results, name="operating_profitability")
    series.index.name = COL_SYMBOL

    diag.info(
        source,
        "Cross-sectional gross profitability computed from raw XBRL facts.",
        n_symbols=len(results),
    )
    return series, diag
