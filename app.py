"""
FPL squad optimiser — Streamlit app.

Pulls live data from the official FPL API and solves an integer linear program
to pick the optimal 15-man squad, starting XI, and captain under the budget and
all squad rules. Tweak the constraints in the sidebar and it re-optimises.

Run locally:
    streamlit run app.py
"""

import sys
from pathlib import Path

import plotly.express as px
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent / "src"))
import fetch_data  # noqa: E402
import optimise  # noqa: E402

st.set_page_config(page_title="FPL squad optimiser", page_icon="⚽", layout="wide")


@st.cache_data(ttl=3600, show_spinner="Fetching live FPL data…")
def load_players():
    return fetch_data.fetch()


df = load_players()
season_live = df["ep_next"].sum() > 0

st.title("⚽ FPL squad optimiser")
st.caption(
    "Picks the optimal 15-man Fantasy Premier League squad — the starting XI and "
    "captain too — by **integer linear programming**, under the £100m budget, the "
    "2/5/5/3 squad shape, a valid formation, and max 3 players per club. Live data "
    "from the official FPL API."
)
if not season_live:
    st.info(
        "Off-season: FPL's live point projections (`ep_next`) are zero, so we optimise on "
        "**last season's points** as the expected-points signal — i.e. a pre-season squad "
        "planner. Once the season starts, switch the objective to *FPL projection*."
    )

# ---- controls ----
st.sidebar.header("Constraints")
budget = st.sidebar.slider("Budget (£m)", 80.0, 100.0, 100.0, 0.5)
max_team = st.sidebar.slider("Max players per club", 1, 3, 3)
exclude = st.sidebar.checkbox("Exclude unavailable (injured/suspended)", value=False)
obj_label = st.sidebar.radio(
    "Optimise for",
    ["Last season's points", "FPL projection (ep_next)"],
    help="ep_next is FPL's own next-gameweek estimate — only meaningful in-season.",
)
objective = "total_points" if obj_label.startswith("Last") else "ep_next"
max_own = st.sidebar.slider(
    "Differential mode — max ownership %", 1, 100, 100,
    help="Lower this to force in less-owned 'differential' picks. 100 = off.",
)

pool = df if max_own >= 100 else df[df["selected_by_pct"] <= max_own]

try:
    squad, summary = optimise.optimise_squad(
        pool, budget=budget, objective=objective,
        max_per_team=max_team, exclude_unavailable=exclude,
    )
except RuntimeError as exc:
    st.error(f"No valid squad: {exc}")
    st.stop()

# ---- summary ----
c1, c2, c3, c4 = st.columns(4)
c1.metric("Projected points", f"{summary['projected_points']:.0f}")
c2.metric("Squad cost", f"£{summary['squad_cost']}m")
c3.metric("Formation", summary["formation"])
c4.metric("Captain (×2)", summary["captain"])

cols = ["position", "name", "team_short", "price", "total_points", "ep_next", "value", "selected_by_pct"]
nice = {"team_short": "team", "total_points": "pts (last szn)", "ep_next": "fpl proj",
        "value": "pts/£m", "selected_by_pct": "owned %"}

left, right = st.columns([3, 2])
with left:
    st.subheader("Starting XI")
    st.dataframe(squad[squad["role"] != "Bench"][cols].rename(columns=nice),
                 hide_index=True, use_container_width=True)
    st.subheader("Bench")
    st.dataframe(squad[squad["role"] == "Bench"][cols].rename(columns=nice),
                 hide_index=True, use_container_width=True)
with right:
    st.subheader("Points vs price")
    plot_df = df.copy()
    plot_df["picked"] = plot_df["id"].isin(squad["id"]).map({True: "in squad", False: "not picked"})
    fig = px.scatter(
        plot_df, x="price", y=objective, color="picked", hover_name="name",
        hover_data=["team_short", "position"], opacity=0.6,
        color_discrete_map={"in squad": "#c0392b", "not picked": "#bdc3c7"},
        labels={"price": "price (£m)", objective: obj_label},
    )
    fig.update_layout(legend_title=None, height=520, margin=dict(t=10))
    st.plotly_chart(fig, use_container_width=True)

with st.expander("Best value players (points per £m)"):
    val = df.sort_values("value", ascending=False).head(15)[
        ["position", "name", "team_short", "price", "total_points", "value"]
    ].rename(columns=nice)
    st.dataframe(val, hide_index=True, use_container_width=True)

st.caption("Data: official Fantasy Premier League API. Solver: PuLP (CBC). Built by Abas Ukanga.")
