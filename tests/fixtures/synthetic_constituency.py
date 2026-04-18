"""Synthetic S&P 500 constituency change generator for NYSE ATS test infrastructure.

Generates ADD/REMOVE events simulating index reconstitution.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def generate_constituency_changes(
    initial_members: list[str],
    n_changes: int = 20,
    seed: int = 42,
) -> pd.DataFrame:
    """Generate synthetic S&P 500 constituency change events.

    Creates a plausible sequence of ADD/REMOVE events where:
    - Each REMOVE targets a current member
    - Each ADD introduces either a new symbol or re-adds a removed one
    - Events are spread across a ~3 year window
    - Changes come in pairs (one ADD, one REMOVE per reconstitution event)

    Parameters
    ----------
    initial_members : list[str]
        Starting set of index members.
    n_changes : int
        Total number of change events (default 20).
    seed : int
        Random seed for reproducibility.

    Returns
    -------
    pd.DataFrame
        Columns: date, symbol, action.
        action is 'ADD' or 'REMOVE'.
        Sorted by date.
    """
    rng = np.random.default_rng(seed)

    # Pool of potential new members (not in initial set)
    new_pool = [f"NEW_{i:02d}" for i in range(n_changes)]

    # Generate event dates spread across ~3 years
    date_range = pd.bdate_range(start="2022-01-10", end="2024-12-20", freq="B")
    event_dates = sorted(rng.choice(date_range, size=n_changes, replace=False))

    current_members = set(initial_members)
    removed_pool: list[str] = []
    records: list[dict] = []
    new_idx = 0

    for event_date in event_dates:
        event_dt = pd.Timestamp(event_date).date()

        # Alternate between ADD and REMOVE, preferring paired changes
        if len(records) % 2 == 0 and len(current_members) > 5:
            # REMOVE event
            removable = list(current_members)
            sym = rng.choice(removable)
            records.append(
                {
                    "date": event_dt,
                    "symbol": sym,
                    "action": "REMOVE",
                }
            )
            current_members.discard(sym)
            removed_pool.append(sym)
        else:
            # ADD event: either re-add a removed stock or bring in new
            if removed_pool and rng.random() < 0.3:
                sym = rng.choice(removed_pool)
                removed_pool.remove(sym)
            elif new_idx < len(new_pool):
                sym = new_pool[new_idx]
                new_idx += 1
            else:
                sym = f"EXTRA_{rng.integers(100, 999)}"

            records.append(
                {
                    "date": event_dt,
                    "symbol": sym,
                    "action": "ADD",
                }
            )
            current_members.add(sym)

    df = pd.DataFrame(records)
    if len(df) > 0:
        df = df.sort_values("date").reset_index(drop=True)

    return df
