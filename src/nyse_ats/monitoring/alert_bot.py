"""Telegram notification bot for trading alerts.

Sends formatted alerts for falsification triggers, rebalance summaries,
and ad-hoc messages.  Falls back to logging when Telegram is not configured.
"""

from __future__ import annotations

import os
from typing import Any

import requests
from tenacity import retry, stop_after_attempt, wait_exponential

from nyse_core.contracts import (
    Diagnostics,
    FalsificationCheckResult,
    PortfolioBuildResult,
)
from nyse_core.schema import Severity

_SRC = "monitoring.alert_bot"
_TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"


class AlertBot:
    """Telegram notification bot for trading alerts.

    If *telegram_token* / *telegram_chat_id* are ``None`` the bot reads
    ``TELEGRAM_BOT_TOKEN`` and ``TELEGRAM_CHAT_ID`` from environment
    variables.  When neither source is available, alerts are logged only.
    """

    def __init__(
        self,
        telegram_token: str | None = None,
        telegram_chat_id: str | None = None,
    ) -> None:
        self._token = telegram_token or os.environ.get("TELEGRAM_BOT_TOKEN")
        self._chat_id = telegram_chat_id or os.environ.get("TELEGRAM_CHAT_ID")

    @property
    def _configured(self) -> bool:
        return bool(self._token and self._chat_id)

    # ── Public API ──────────────────────────────────────────────────────────

    def send_alert(self, message: str, severity: Severity) -> Diagnostics:
        """Send a generic alert.  VETO = urgent, WARNING = normal."""
        diag = Diagnostics()
        formatted = self._format_message(message, severity)
        self._dispatch(formatted, diag)
        return diag

    def send_rebalance_summary(self, result: PortfolioBuildResult) -> Diagnostics:
        """Format and send a weekly rebalance summary."""
        diag = Diagnostics()
        lines = [
            "[REBALANCE SUMMARY]",
            f"Date: {result.rebalance_date}",
            f"Regime: {result.regime_state.value}",
            f"Positions held: {result.held_positions}",
            f"New entries: {result.new_entries}",
            f"Exits: {result.exits}",
            f"Turnover: {result.turnover_pct:.1f}%",
            f"Est. cost: ${result.cost_estimate_usd:,.2f}",
        ]
        if result.skipped_reason:
            lines.append(f"SKIPPED: {result.skipped_reason}")
        self._dispatch("\n".join(lines), diag)
        return diag

    def send_falsification_alert(
        self,
        results: list[FalsificationCheckResult],
    ) -> Diagnostics:
        """Send alert for any fired triggers."""
        diag = Diagnostics()
        fired = [r for r in results if not r.passed]
        if not fired:
            diag.info(_SRC, "No triggers fired; skipping alert.")
            return diag

        lines = ["[FALSIFICATION ALERT]"]
        for r in fired:
            prefix = "[VETO]" if r.severity == Severity.VETO else "[WARNING]"
            lines.append(
                f"{prefix} {r.trigger_id}: {r.description} (value={r.current_value}, threshold={r.threshold})"
            )

        max_severity = Severity.VETO if any(r.severity == Severity.VETO for r in fired) else Severity.WARNING
        formatted = self._format_message("\n".join(lines), max_severity)
        self._dispatch(formatted, diag)
        return diag

    # ── Internals ───────────────────────────────────────────────────────────

    def _format_message(self, text: str, severity: Severity) -> str:
        prefix = "[VETO]" if severity == Severity.VETO else "[WARNING]"
        return f"{prefix} {text}"

    def _dispatch(self, text: str, diag: Diagnostics) -> None:
        """Send *text* via Telegram, or fall back to logging."""
        if not self._configured:
            diag.info(_SRC, f"Telegram not configured. Message: {text}")
            return
        try:
            self._send_telegram(text)
            diag.info(_SRC, "Telegram message sent.")
        except Exception as exc:
            diag.error(_SRC, f"Telegram send failed after retries: {exc}")

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=0.1, max=2))
    def _send_telegram(self, text: str) -> dict[str, Any]:
        """POST to Telegram sendMessage API with 3-attempt retry."""
        url = _TELEGRAM_API.format(token=self._token)
        payload = {"chat_id": self._chat_id, "text": text, "parse_mode": "HTML"}
        resp = requests.post(url, json=payload, timeout=10)
        resp.raise_for_status()
        return resp.json()
