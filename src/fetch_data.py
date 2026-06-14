"""
Fetch the current Fantasy Premier League dataset from the official public API.

No API key needed. The `bootstrap-static` endpoint returns every player with
prices, points, and underlying stats; we flatten it into one tidy table.

Run:
    python src/fetch_data.py
Output:
    data/players.parquet
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import requests

API = "https://fantasy.premierleague.com/api/bootstrap-static/"
OUT = Path(__file__).resolve().parents[1] / "data" / "players.parquet"


def _f(v: object) -> float:
    """Parse FPL's stringy floats; missing/None (e.g. off-season ep_next) -> 0.0."""
    return float(v) if v not in (None, "", "None") else 0.0


def fetch() -> pd.DataFrame:
    data = requests.get(API, timeout=30).json()
    teams = {t["id"]: t["name"] for t in data["teams"]}
    short = {t["id"]: t["short_name"] for t in data["teams"]}
    positions = {t["id"]: t["singular_name_short"] for t in data["element_types"]}

    rows = []
    for e in data["elements"]:
        rows.append({
            "id": e["id"],
            "name": e["web_name"],
            "team": teams[e["team"]],
            "team_short": short[e["team"]],
            "position": positions[e["element_type"]],
            "price": e["now_cost"] / 10.0,
            "total_points": e["total_points"],
            "points_per_game": _f(e["points_per_game"]),
            "minutes": e["minutes"],
            "form": _f(e["form"]),
            "selected_by_pct": _f(e["selected_by_percent"]),
            "xgi": _f(e["expected_goal_involvements"]),
            "ict_index": _f(e["ict_index"]),
            "goals": e["goals_scored"],
            "assists": e["assists"],
            "clean_sheets": e["clean_sheets"],
            "bonus": e["bonus"],
            "ep_next": _f(e["ep_next"]),       # FPL's own forward estimate
            "status": e["status"],                # 'a' available, 'i' injured, ...
        })
    df = pd.DataFrame(rows)
    df["value"] = (df["total_points"] / df["price"]).round(1)   # points per £m
    return df


def main() -> None:
    df = fetch()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(OUT, index=False)
    print(f"Saved {len(df)} players -> {OUT}")
    print(f"Positions: {df['position'].value_counts().to_dict()}")
    print(f"Top scorer: {df.loc[df['total_points'].idxmax(), 'name']} "
          f"({df['total_points'].max()} pts)")


if __name__ == "__main__":
    main()
