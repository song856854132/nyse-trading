"""Unit tests for AlertBot (Telegram notification)."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

from nyse_ats.monitoring.alert_bot import AlertBot
from nyse_core.contracts import (
    FalsificationCheckResult,
    PortfolioBuildResult,
)
from nyse_core.schema import RegimeState, Severity

# ── Helpers ─────────────────────────────────────────────────────────────────


def _mock_portfolio_result() -> PortfolioBuildResult:
    return PortfolioBuildResult(
        trade_plans=[],
        cost_estimate_usd=150.0,
        turnover_pct=45.0,
        regime_state=RegimeState.BULL,
        rebalance_date=date(2026, 4, 15),
        held_positions=20,
        new_entries=3,
        exits=2,
    )


def _fired_veto() -> FalsificationCheckResult:
    return FalsificationCheckResult(
        trigger_id="F3_excessive_drawdown",
        trigger_name="Max drawdown exceeds -25%",
        current_value=-0.30,
        threshold=-0.25,
        severity=Severity.VETO,
        passed=False,
        description="Max drawdown exceeds -25%",
    )


def _fired_warning() -> FalsificationCheckResult:
    return FalsificationCheckResult(
        trigger_id="F4_concentration",
        trigger_name="Single stock weight exceeds 15%",
        current_value=0.20,
        threshold=0.15,
        severity=Severity.WARNING,
        passed=False,
        description="Single stock weight exceeds 15%",
    )


def _passing_result() -> FalsificationCheckResult:
    return FalsificationCheckResult(
        trigger_id="F5_turnover_spike",
        trigger_name="Monthly turnover",
        current_value=100.0,
        threshold=200.0,
        severity=Severity.WARNING,
        passed=True,
        description="Monthly turnover OK",
    )


# ── Tests ───────────────────────────────────────────────────────────────────


class TestAlertBot:
    # -- Telegram POST body ---------------------------------------------------

    @patch("nyse_ats.monitoring.alert_bot.requests.post")
    def test_send_alert_posts_to_telegram(self, mock_post: MagicMock) -> None:
        mock_post.return_value = MagicMock(status_code=200)
        mock_post.return_value.raise_for_status = MagicMock()
        mock_post.return_value.json.return_value = {"ok": True}

        bot = AlertBot(telegram_token="tok123", telegram_chat_id="chat456")
        diag = bot.send_alert("Test message", Severity.WARNING)

        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args
        assert "chat456" in str(call_kwargs)
        assert "tok123" in str(call_kwargs)
        assert not diag.has_errors

    # -- Telegram not configured: graceful fallback ---------------------------

    @patch.dict("os.environ", {}, clear=True)
    def test_telegram_not_configured_logs_only(self) -> None:
        bot = AlertBot(telegram_token=None, telegram_chat_id=None)
        diag = bot.send_alert("Hello", Severity.WARNING)
        assert not diag.has_errors
        info_msgs = [m for m in diag.messages if "not configured" in m.message.lower()]
        assert len(info_msgs) >= 1

    # -- Rebalance summary formatting -----------------------------------------

    @patch.dict("os.environ", {}, clear=True)
    def test_rebalance_summary_format(self) -> None:
        bot = AlertBot()  # not configured → logged
        result = _mock_portfolio_result()
        diag = bot.send_rebalance_summary(result)
        assert not diag.has_errors
        logged = " ".join(m.message for m in diag.messages)
        assert "REBALANCE SUMMARY" in logged
        assert "20" in logged  # held_positions
        assert "45.0%" in logged  # turnover

    # -- Falsification alert with VETO severity -------------------------------

    @patch.dict("os.environ", {}, clear=True)
    def test_falsification_alert_veto(self) -> None:
        bot = AlertBot()
        results = [_fired_veto(), _passing_result()]
        diag = bot.send_falsification_alert(results)
        assert not diag.has_errors
        logged = " ".join(m.message for m in diag.messages)
        assert "[VETO]" in logged
        assert "F3_excessive_drawdown" in logged

    @patch.dict("os.environ", {}, clear=True)
    def test_falsification_alert_no_fired_skips(self) -> None:
        bot = AlertBot()
        diag = bot.send_falsification_alert([_passing_result()])
        info = [m for m in diag.messages if "skipping" in m.message.lower()]
        assert len(info) >= 1

    # -- Telegram API down: retry and log failure -----------------------------

    @patch("nyse_ats.monitoring.alert_bot.requests.post")
    def test_telegram_api_down_logs_error(self, mock_post: MagicMock) -> None:
        mock_post.side_effect = ConnectionError("Telegram unreachable")
        bot = AlertBot(telegram_token="tok", telegram_chat_id="chat")
        diag = bot.send_alert("urgent", Severity.VETO)
        assert diag.has_errors
        assert mock_post.call_count == 3  # 3 retries

    # -- Message formatting with severity prefix ------------------------------

    def test_format_message_veto(self) -> None:
        bot = AlertBot()
        msg = bot._format_message("halt now", Severity.VETO)
        assert msg.startswith("[VETO]")

    def test_format_message_warning(self) -> None:
        bot = AlertBot()
        msg = bot._format_message("check this", Severity.WARNING)
        assert msg.startswith("[WARNING]")
