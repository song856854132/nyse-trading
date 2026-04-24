"""Config loader -- I/O side effect belongs in nyse_ats, not nyse_core.

Loads YAML files from disk and validates them against the Pydantic schemas
defined in nyse_core.config_schema.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import yaml

from nyse_core.config_schema import (
    DataSourcesConfig,
    DeploymentLadderConfig,
    FalsificationTriggersConfig,
    GatesConfig,
    MarketParams,
    StrategyParams,
)

if TYPE_CHECKING:
    from pathlib import Path

    from pydantic import BaseModel


def load_and_validate_config(config_dir: Path) -> dict[str, BaseModel]:
    """Load all 6 YAML configs and validate with Pydantic. Raises on error."""
    configs: dict[str, BaseModel] = {}

    mapping: dict[str, type[BaseModel]] = {
        "market_params.yaml": MarketParams,
        "strategy_params.yaml": StrategyParams,
        "gates.yaml": GatesConfig,
        # V2-PREREG-2026-04-24 (GL-0014, GL-0015): v2 gate family is pre-registered
        # but NOT YET WIRED into admission decisions. Both files coexist; gates.yaml
        # remains operationally in-force until a scripts/evaluate_gates.py run with
        # --gates-version v2 activates v2 thresholds against a re-screen.
        "gates_v2.yaml": GatesConfig,
        "falsification_triggers.yaml": FalsificationTriggersConfig,
        "data_sources.yaml": DataSourcesConfig,
        "deployment_ladder.yaml": DeploymentLadderConfig,
    }

    for filename, model_class in mapping.items():
        filepath = config_dir / filename
        if not filepath.exists():
            raise FileNotFoundError(f"Config file not found: {filepath}")
        with open(filepath) as f:
            raw = yaml.safe_load(f)
        configs[filename] = model_class(**raw)

    return configs
