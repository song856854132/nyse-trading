"""Pydantic models for all 6 YAML config files. Fail-fast validation at startup.

This module defines PURE schema models only -- no filesystem I/O.
Use nyse_ats.config_loader.load_and_validate_config() for loading YAML files.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class _StrictBase(BaseModel):
    """Base with extra='forbid' -- rejects unknown/typo'd config keys at parse time."""

    model_config = ConfigDict(extra="forbid")


# ── market_params.yaml ────────────────────────────────────────────────────────


class MarketParams(_StrictBase):
    market: Literal["NYSE"]
    currency: Literal["USD"]
    lot_size: Literal[1]
    transaction_tax_rate: float = Field(ge=0.0, le=0.01)
    commission_per_share: float = Field(gt=0.0, le=0.05)
    base_spread_bps: float = Field(gt=0.0, le=50.0)
    monday_multiplier: float = Field(ge=1.0, le=3.0)
    earnings_week_multiplier: float = Field(ge=1.0, le=5.0)
    trading_days_per_year: int = Field(ge=250, le=253)
    settlement_days: int = Field(ge=1, le=3)


# ── strategy_params.yaml ─────────────────────────────────────────────────────


class UniverseConfig(_StrictBase):
    source: str
    min_price: float = Field(gt=0.0)
    min_adv_20d: int = Field(gt=0)


class RebalanceConfig(_StrictBase):
    frequency: Literal["weekly", "monthly"]
    day_of_week: Literal["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
    execution_delay_days: int = Field(ge=0, le=5)


class AllocatorConfig(_StrictBase):
    top_n: int = Field(ge=5, le=100)
    weighting: Literal["equal"]
    sell_buffer: float = Field(ge=1.0, le=3.0)


class RegimeConfig(_StrictBase):
    type: Literal["sma200_binary"]
    benchmark: str
    bull_exposure: float = Field(ge=0.0, le=1.0)
    bear_exposure: float = Field(ge=0.0, le=1.0)


class CombinationConfig(_StrictBase):
    model: Literal["ridge", "gbm", "neural"]
    alpha: float = Field(gt=0.0)
    normalization: Literal["rank_percentile", "winsorize", "z_score"]
    target_horizon_days: int = Field(ge=1, le=63)


class RiskConfig(_StrictBase):
    max_position_pct: float = Field(gt=0.0, le=0.25)
    max_sector_pct: float = Field(gt=0.0, le=0.50)
    position_inertia_threshold: float = Field(ge=0.0, le=0.50)
    beta_cap_low: float = Field(ge=0.0, le=1.0)
    beta_cap_high: float = Field(ge=1.0, le=3.0)
    daily_loss_limit: float = Field(lt=0.0, ge=-0.10)
    earnings_event_cap: float = Field(gt=0.0, le=0.20)
    earnings_event_days: int = Field(ge=1, le=10)


class VolatilityTargetConfig(_StrictBase):
    annual_pct: float = Field(gt=0.0, le=0.50)


class ExecutionConfig(_StrictBase):
    algorithm: Literal["twap", "vwap"]
    twap_duration_minutes: int = Field(ge=5, le=120)
    max_participation_rate: float = Field(gt=0.0, le=0.20)


class StrategyParams(_StrictBase):
    universe: UniverseConfig
    rebalance: RebalanceConfig
    allocator: AllocatorConfig
    regime: RegimeConfig
    combination: CombinationConfig
    risk: RiskConfig
    kill_switch: bool = False
    volatility_target: VolatilityTargetConfig
    execution: ExecutionConfig


# ── gates.yaml ────────────────────────────────────────────────────────────────


class GateConfig(_StrictBase):
    metric: str
    threshold: float
    direction: Literal[">=", ">", "<", "<="]
    description: str = ""


class GatesConfig(_StrictBase):
    G0: GateConfig
    G1: GateConfig
    G2: GateConfig
    G3: GateConfig
    G4: GateConfig
    G5: GateConfig


# ── falsification_triggers.yaml ───────────────────────────────────────────────


class TriggerConfig(_StrictBase):
    metric: str
    threshold: float | bool
    months: int | None = None
    severity: Literal["VETO", "WARNING"]
    description: str = ""


class FalsificationTriggersConfig(_StrictBase):
    frozen_date: str
    triggers: dict[str, TriggerConfig]


# ── data_sources.yaml ─────────────────────────────────────────────────────────


class FinMindConfig(_StrictBase):
    base_url: str
    token_env_var: str
    rate_limit_per_minute: int = Field(gt=0)
    datasets: dict[str, str]
    bulk_start_date: str


class EdgarConfig(_StrictBase):
    base_url: str
    rate_limit_per_second: int = Field(gt=0)
    user_agent_env_var: str
    filing_types: list[str]


class FinraConfig(_StrictBase):
    short_interest_url: str
    publication_lag_days: int = Field(ge=0)
    update_frequency: str


class ConstituencyConfig(_StrictBase):
    source: str
    backup_source: str = ""
    csv_path: str = ""


class DataSourcesConfig(_StrictBase):
    finmind: FinMindConfig
    edgar: EdgarConfig
    finra: FinraConfig
    constituency: ConstituencyConfig


# ── deployment_ladder.yaml ────────────────────────────────────────────────────


class StageExitCriteria(BaseModel, extra="allow"):
    """Flexible exit criteria -- different per stage."""

    pass


class StageConfig(BaseModel, extra="allow"):
    """Deployment stage. Extra fields allowed for stage-specific config."""

    min_duration_days: int = Field(ge=1)
    entry_gate: str


class GraduationCriteria(_StrictBase):
    min_trading_days: int = Field(ge=1)
    mean_slippage_bps_lt: float = Field(gt=0)
    rejection_rate_lt: float = Field(ge=0, le=1)
    settlement_failures_eq: int = Field(ge=0)
    fill_rate_gt: float = Field(ge=0, le=1)
    rolling_ic_20d_gt: float
    cost_drag_pct_lt: float = Field(gt=0)


class DeploymentLadderConfig(_StrictBase):
    stages: dict[str, StageConfig]
    graduation_criteria: GraduationCriteria
