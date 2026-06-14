"""
The optimiser — an integer linear program that picks the best Fantasy Premier
League squad.

It chooses a 15-man squad AND the starting XI AND the captain in one solve,
maximising  (starters' points + captain's points again)  subject to every real
FPL rule: squad shape (2 GKP / 5 DEF / 5 MID / 3 FWD), a valid XI formation, the
£100m budget, and the max-3-players-per-club limit.

The objective column is swappable: use `total_points` for a season review, or
`ep_next` (FPL's forward estimate) to optimise live during a season.

Run (after fetch_data.py):
    python src/optimise.py
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pulp

DATA = Path(__file__).resolve().parents[1] / "data" / "players.parquet"

SQUAD = {"GKP": 2, "DEF": 5, "MID": 5, "FWD": 3}   # full 15-man squad
XI_MIN = {"GKP": 1, "DEF": 3, "MID": 2, "FWD": 1}  # valid starting-XI formation
XI_MAX = {"GKP": 1, "DEF": 5, "MID": 5, "FWD": 3}
FORMATION_ORDER = ["GKP", "DEF", "MID", "FWD"]


def optimise_squad(
    df: pd.DataFrame,
    *,
    budget: float = 100.0,
    objective: str = "total_points",
    max_per_team: int = 3,
    exclude_unavailable: bool = False,
) -> tuple[pd.DataFrame, dict]:
    """Return (the 15 chosen players with roles, a summary dict)."""
    pool = df[df["status"] == "a"].copy() if exclude_unavailable else df.copy()
    pool = pool.reset_index(drop=True)
    ids = list(pool.index)
    obj, price = pool[objective].tolist(), pool["price"].tolist()
    pos, team = pool["position"].tolist(), pool["team"].tolist()

    prob = pulp.LpProblem("fpl_squad", pulp.LpMaximize)
    sq = pulp.LpVariable.dicts("squad", ids, cat="Binary")
    st = pulp.LpVariable.dicts("start", ids, cat="Binary")
    cap = pulp.LpVariable.dicts("cap", ids, cat="Binary")

    # Maximise starting XI points, counting the captain twice.
    prob += pulp.lpSum(obj[i] * st[i] for i in ids) + pulp.lpSum(obj[i] * cap[i] for i in ids)

    for i in ids:
        prob += st[i] <= sq[i]      # can only start if in the squad
        prob += cap[i] <= st[i]     # can only captain a starter
    prob += pulp.lpSum(cap[i] for i in ids) == 1
    prob += pulp.lpSum(sq[i] for i in ids) == 15
    prob += pulp.lpSum(st[i] for i in ids) == 11
    prob += pulp.lpSum(price[i] * sq[i] for i in ids) <= budget

    for p, n in SQUAD.items():
        prob += pulp.lpSum(sq[i] for i in ids if pos[i] == p) == n
    for p in SQUAD:
        prob += pulp.lpSum(st[i] for i in ids if pos[i] == p) >= XI_MIN[p]
        prob += pulp.lpSum(st[i] for i in ids if pos[i] == p) <= XI_MAX[p]
    for t in set(team):
        prob += pulp.lpSum(sq[i] for i in ids if team[i] == t) <= max_per_team

    prob.solve(pulp.PULP_CBC_CMD(msg=False))
    status = pulp.LpStatus[prob.status]
    if status != "Optimal":
        raise RuntimeError(f"solver returned {status} (try a higher budget)")

    chosen = [i for i in ids if sq[i].value() == 1]
    out = pool.loc[chosen].copy()
    out["role"] = [
        "Captain" if cap[i].value() == 1
        else "Starter" if st[i].value() == 1
        else "Bench"
        for i in chosen
    ]
    out = out.sort_values(
        ["role", "position", objective],
        key=lambda s: s.map({"Captain": 0, "Starter": 1, "Bench": 2}) if s.name == "role"
        else s.map({p: i for i, p in enumerate(FORMATION_ORDER)}) if s.name == "position"
        else -s,
    )

    starters = out[out["role"] != "Bench"]
    formation = "-".join(
        str((starters["position"] == p).sum()) for p in ["DEF", "MID", "FWD"]
    )
    summary = {
        "objective": objective,
        "squad_cost": round(out["price"].sum(), 1),
        "budget": budget,
        "projected_points": round(
            starters[objective].sum() + out.loc[out["role"] == "Captain", objective].sum(), 1
        ),
        "formation": formation,
        "captain": out.loc[out["role"] == "Captain", "name"].iloc[0],
    }
    return out, summary


def main() -> None:
    df = pd.read_parquet(DATA)
    squad, summary = optimise_squad(df, objective="total_points")
    print(f"Optimal {summary['formation']} squad — cost £{summary['squad_cost']}m / "
          f"£{summary['budget']}m, projected {summary['projected_points']} pts, "
          f"captain {summary['captain']}\n")
    cols = ["role", "position", "name", "team_short", "price", "total_points", "value"]
    print(squad[cols].to_string(index=False))


if __name__ == "__main__":
    main()
