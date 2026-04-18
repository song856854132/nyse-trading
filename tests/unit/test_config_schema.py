"""Tests for nyse_core.config_schema — Pydantic config validation.

Validates that:
- All 6 YAML config files in config/ pass validation
- Typos in field names raise ValidationError
- Missing required fields raise ValidationError
- Out-of-range values raise ValidationError
- Wrong types raise ValidationError
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from nyse_ats.config_loader import load_and_validate_config
from nyse_core.config_schema import (
    DataSourcesConfig,
    DeploymentLadderConfig,
    FalsificationTriggersConfig,
    GatesConfig,
    GraduationCriteria,
    MarketParams,
    StrategyParams,
)

CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"


# ── Valid Config Tests ───────────────────────────────────────────────────────


class TestValidConfigLoading:
    """All config/*.yaml files must pass Pydantic validation."""

    def test_all_configs_load_successfully(self) -> None:
        """load_and_validate_config should return 6 validated models."""
        configs = load_and_validate_config(CONFIG_DIR)
        assert len(configs) == 6
        assert "market_params.yaml" in configs
        assert "strategy_params.yaml" in configs
        assert "gates.yaml" in configs
        assert "falsification_triggers.yaml" in configs
        assert "data_sources.yaml" in configs
        assert "deployment_ladder.yaml" in configs

    def test_market_params_values(self) -> None:
        """market_params.yaml should contain expected NYSE defaults."""
        configs = load_and_validate_config(CONFIG_DIR)
        mp = configs["market_params.yaml"]
        assert isinstance(mp, MarketParams)
        assert mp.market == "NYSE"
        assert mp.currency == "USD"
        assert mp.lot_size == 1
        assert mp.commission_per_share == 0.005
        assert mp.trading_days_per_year == 252

    def test_strategy_params_values(self) -> None:
        """strategy_params.yaml should contain expected strategy defaults."""
        configs = load_and_validate_config(CONFIG_DIR)
        sp = configs["strategy_params.yaml"]
        assert isinstance(sp, StrategyParams)
        assert sp.universe.source == "SP500"
        assert sp.allocator.sell_buffer == 1.5
        assert sp.regime.bear_exposure == 0.4
        assert sp.combination.model == "ridge"
        assert sp.risk.max_position_pct == 0.10

    def test_gates_values(self) -> None:
        """gates.yaml should parse all 6 gates (G0-G5)."""
        configs = load_and_validate_config(CONFIG_DIR)
        gc = configs["gates.yaml"]
        assert isinstance(gc, GatesConfig)
        assert gc.G0.threshold == 0.3
        assert gc.G1.direction == "<"
        assert gc.G5.threshold == 0.0

    def test_falsification_triggers_values(self) -> None:
        """falsification_triggers.yaml should parse all triggers."""
        configs = load_and_validate_config(CONFIG_DIR)
        ft = configs["falsification_triggers.yaml"]
        assert isinstance(ft, FalsificationTriggersConfig)
        assert "F1_signal_death" in ft.triggers
        assert ft.triggers["F3_excessive_drawdown"].severity == "VETO"

    def test_data_sources_values(self) -> None:
        """data_sources.yaml should parse all data source configs."""
        configs = load_and_validate_config(CONFIG_DIR)
        ds = configs["data_sources.yaml"]
        assert isinstance(ds, DataSourcesConfig)
        assert ds.finmind.token_env_var == "FINMIND_API_TOKEN"
        assert ds.edgar.rate_limit_per_second == 10

    def test_deployment_ladder_values(self) -> None:
        """deployment_ladder.yaml should parse stages and graduation criteria."""
        configs = load_and_validate_config(CONFIG_DIR)
        dl = configs["deployment_ladder.yaml"]
        assert isinstance(dl, DeploymentLadderConfig)
        assert "paper" in dl.stages
        assert dl.graduation_criteria.min_trading_days == 20


# ── Typo / Unknown Field Tests ───────────────────────────────────────────────


class TestFieldNameTypos:
    """Typos in field names should raise ValidationError (strict models)."""

    def test_market_params_typo_raises(self) -> None:
        """A typo like 'currrency' instead of 'currency' should fail."""
        raw = _load_raw_yaml("market_params.yaml")
        raw["currrency"] = raw.pop("currency")
        with pytest.raises(ValidationError):
            MarketParams(**raw)

    def test_strategy_universe_typo_raises(self) -> None:
        """Typo in nested field: 'min_priice' instead of 'min_price'."""
        raw = _load_raw_yaml("strategy_params.yaml")
        raw["universe"]["min_priice"] = raw["universe"].pop("min_price")
        with pytest.raises(ValidationError):
            StrategyParams(**raw)


class TestExtraFieldRejection:
    """extra='forbid' must reject unknown fields even when all required fields present."""

    def test_market_params_extra_field_rejected(self) -> None:
        """An extra field on a valid config must be rejected."""
        raw = _load_raw_yaml("market_params.yaml")
        raw["bonus_field"] = "should_fail"
        with pytest.raises(ValidationError, match="extra"):
            MarketParams(**raw)

    def test_strategy_params_extra_field_rejected(self) -> None:
        raw = _load_raw_yaml("strategy_params.yaml")
        raw["unknown_section"] = {"foo": "bar"}
        with pytest.raises(ValidationError, match="extra"):
            StrategyParams(**raw)

    def test_nested_extra_field_rejected(self) -> None:
        """Extra field inside a nested model must also be rejected."""
        raw = _load_raw_yaml("strategy_params.yaml")
        raw["allocator"]["mystery_param"] = 42
        with pytest.raises(ValidationError, match="extra"):
            StrategyParams(**raw)

    def test_gates_extra_field_rejected(self) -> None:
        raw = _load_raw_yaml("gates.yaml")
        raw["G99_phantom"] = {"metric": "fake", "threshold": 0.5, "direction": ">"}
        with pytest.raises(ValidationError, match="extra"):
            GatesConfig(**raw)

    def test_graduation_criteria_extra_field_rejected(self) -> None:
        raw = _load_raw_yaml("deployment_ladder.yaml")
        raw["graduation_criteria"]["phantom_metric"] = 999
        with pytest.raises(ValidationError, match="extra"):
            DeploymentLadderConfig(**raw)


# ── Missing Required Field Tests ─────────────────────────────────────────────


class TestMissingRequiredFields:
    """Missing required fields must raise ValidationError."""

    def test_market_params_missing_market(self) -> None:
        """MarketParams without 'market' should fail."""
        raw = _load_raw_yaml("market_params.yaml")
        del raw["market"]
        with pytest.raises(ValidationError):
            MarketParams(**raw)

    def test_market_params_missing_commission(self) -> None:
        """MarketParams without 'commission_per_share' should fail."""
        raw = _load_raw_yaml("market_params.yaml")
        del raw["commission_per_share"]
        with pytest.raises(ValidationError):
            MarketParams(**raw)

    def test_strategy_missing_universe(self) -> None:
        """StrategyParams without 'universe' section should fail."""
        raw = _load_raw_yaml("strategy_params.yaml")
        del raw["universe"]
        with pytest.raises(ValidationError):
            StrategyParams(**raw)

    def test_strategy_missing_risk(self) -> None:
        """StrategyParams without 'risk' section should fail."""
        raw = _load_raw_yaml("strategy_params.yaml")
        del raw["risk"]
        with pytest.raises(ValidationError):
            StrategyParams(**raw)

    def test_gates_missing_G0(self) -> None:
        """GatesConfig without G0 should fail."""
        raw = _load_raw_yaml("gates.yaml")
        del raw["G0"]
        with pytest.raises(ValidationError):
            GatesConfig(**raw)

    def test_deployment_missing_graduation(self) -> None:
        """DeploymentLadderConfig without graduation_criteria should fail."""
        raw = _load_raw_yaml("deployment_ladder.yaml")
        del raw["graduation_criteria"]
        with pytest.raises(ValidationError):
            DeploymentLadderConfig(**raw)


# ── Out-of-Range Value Tests ─────────────────────────────────────────────────


class TestOutOfRangeValues:
    """Values outside Pydantic Field constraints must raise ValidationError."""

    def test_sell_buffer_below_minimum(self) -> None:
        """sell_buffer=0.5 when ge=1.0 should fail."""
        raw = _load_raw_yaml("strategy_params.yaml")
        raw["allocator"]["sell_buffer"] = 0.5
        with pytest.raises(ValidationError):
            StrategyParams(**raw)

    def test_sell_buffer_above_maximum(self) -> None:
        """sell_buffer=5.0 when le=3.0 should fail."""
        raw = _load_raw_yaml("strategy_params.yaml")
        raw["allocator"]["sell_buffer"] = 5.0
        with pytest.raises(ValidationError):
            StrategyParams(**raw)

    def test_max_position_pct_exceeds_limit(self) -> None:
        """max_position_pct=0.50 when le=0.25 should fail."""
        raw = _load_raw_yaml("strategy_params.yaml")
        raw["risk"]["max_position_pct"] = 0.50
        with pytest.raises(ValidationError):
            StrategyParams(**raw)

    def test_daily_loss_limit_positive(self) -> None:
        """daily_loss_limit=0.01 when lt=0.0 should fail."""
        raw = _load_raw_yaml("strategy_params.yaml")
        raw["risk"]["daily_loss_limit"] = 0.01
        with pytest.raises(ValidationError):
            StrategyParams(**raw)

    def test_commission_negative(self) -> None:
        """commission_per_share=-0.01 when gt=0.0 should fail."""
        raw = _load_raw_yaml("market_params.yaml")
        raw["commission_per_share"] = -0.01
        with pytest.raises(ValidationError):
            MarketParams(**raw)

    def test_commission_too_high(self) -> None:
        """commission_per_share=1.0 when le=0.05 should fail."""
        raw = _load_raw_yaml("market_params.yaml")
        raw["commission_per_share"] = 1.0
        with pytest.raises(ValidationError):
            MarketParams(**raw)

    def test_top_n_below_minimum(self) -> None:
        """top_n=2 when ge=5 should fail."""
        raw = _load_raw_yaml("strategy_params.yaml")
        raw["allocator"]["top_n"] = 2
        with pytest.raises(ValidationError):
            StrategyParams(**raw)

    def test_top_n_above_maximum(self) -> None:
        """top_n=500 when le=100 should fail."""
        raw = _load_raw_yaml("strategy_params.yaml")
        raw["allocator"]["top_n"] = 500
        with pytest.raises(ValidationError):
            StrategyParams(**raw)

    def test_bear_exposure_exceeds_one(self) -> None:
        """bear_exposure=1.5 when le=1.0 should fail."""
        raw = _load_raw_yaml("strategy_params.yaml")
        raw["regime"]["bear_exposure"] = 1.5
        with pytest.raises(ValidationError):
            StrategyParams(**raw)

    def test_target_horizon_zero(self) -> None:
        """target_horizon_days=0 when ge=1 should fail."""
        raw = _load_raw_yaml("strategy_params.yaml")
        raw["combination"]["target_horizon_days"] = 0
        with pytest.raises(ValidationError):
            StrategyParams(**raw)

    def test_graduation_fill_rate_above_one(self) -> None:
        """fill_rate_gt=1.5 when le=1 should fail."""
        with pytest.raises(ValidationError):
            GraduationCriteria(
                min_trading_days=20,
                mean_slippage_bps_lt=20,
                rejection_rate_lt=0.05,
                settlement_failures_eq=0,
                fill_rate_gt=1.5,
                rolling_ic_20d_gt=0.02,
                cost_drag_pct_lt=5.0,
            )


# ── Wrong Type Tests ─────────────────────────────────────────────────────────


class TestWrongTypes:
    """Wrong types for fields must raise ValidationError."""

    def test_market_string_for_lot_size(self) -> None:
        """lot_size='one' (string) should fail — expects int literal 1."""
        raw = _load_raw_yaml("market_params.yaml")
        raw["lot_size"] = "one"
        with pytest.raises(ValidationError):
            MarketParams(**raw)

    def test_strategy_frequency_invalid_literal(self) -> None:
        """frequency='daily' when only 'weekly'/'monthly' allowed should fail."""
        raw = _load_raw_yaml("strategy_params.yaml")
        raw["rebalance"]["frequency"] = "daily"
        with pytest.raises(ValidationError):
            StrategyParams(**raw)

    def test_strategy_model_invalid_literal(self) -> None:
        """model='random_forest' when only 'ridge'/'gbm'/'neural' allowed should fail."""
        raw = _load_raw_yaml("strategy_params.yaml")
        raw["combination"]["model"] = "random_forest"
        with pytest.raises(ValidationError):
            StrategyParams(**raw)

    def test_market_not_nyse(self) -> None:
        """market='NASDAQ' when only 'NYSE' allowed should fail."""
        raw = _load_raw_yaml("market_params.yaml")
        raw["market"] = "NASDAQ"
        with pytest.raises(ValidationError):
            MarketParams(**raw)

    def test_gate_direction_invalid(self) -> None:
        """direction='!=' when only '>=','>','<','<=' allowed should fail."""
        raw = _load_raw_yaml("gates.yaml")
        raw["G0"]["direction"] = "!="
        with pytest.raises(ValidationError):
            GatesConfig(**raw)

    def test_trigger_severity_invalid(self) -> None:
        """severity='CRITICAL' when only 'VETO'/'WARNING' allowed should fail."""
        raw = _load_raw_yaml("falsification_triggers.yaml")
        raw["triggers"]["F1_signal_death"]["severity"] = "CRITICAL"
        with pytest.raises(ValidationError):
            FalsificationTriggersConfig(**raw)


# ── Missing Config File Test ─────────────────────────────────────────────────


class TestMissingConfigFile:
    """Missing YAML files should raise FileNotFoundError."""

    def test_nonexistent_dir_raises(self, tmp_path: Path) -> None:
        """load_and_validate_config with empty dir should raise FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            load_and_validate_config(tmp_path)


# ── Helpers ──────────────────────────────────────────────────────────────────


def _load_raw_yaml(filename: str) -> dict:
    """Load a config YAML file as raw dict for mutation in tests."""
    filepath = CONFIG_DIR / filename
    with open(filepath) as f:
        return yaml.safe_load(f)
