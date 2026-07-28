"""DFS Optimizer page (site revamp Batch 2). The tab4 "coming soon" body moved
byte-identical from app.py (copy freeze). Any "tab"->"page" wording change is a
separate flagged copy decision, not this build.
"""
import streamlit as st


def render():
    st.title("🎯 DFS Optimizer")
    st.caption("DraftKings NFL Classic lineup optimizer — powered by the same weekly projections as the Weekly Fantasy page.")

    st.divider()

    st.info(
        "**Coming soon — launching with the 2026 NFL season.**\n\n"
        "The DFS optimizer is currently in development. When live, this page will let you:\n\n"
        "- Browse this week's projected DraftKings points for every skill-position player\n"
        "- Upload your DraftKings salary CSV (exported from any NFL Classic contest)\n"
        "- Generate an ILP-optimized 9-player lineup (QB / 2 RB / 3 WR / 1 TE / FLEX / DST)\n"
        "- Lock or exclude specific players and re-run in one click\n"
        "- Download the finished lineup ready for DraftKings import\n\n"
        "Projections are converted to full DraftKings Classic scoring automatically, "
        "including the full-PPR reception bonus and milestone bonuses "
        "(300+ passing yards, 100+ rushing yards, 100+ receiving yards)."
    )

    st.divider()

    col_a, col_b, col_c = st.columns(3)
    with col_a:
        st.metric("Scoring", "DK Classic (full PPR)")
    with col_b:
        st.metric("Salary cap", "$50,000")
    with col_c:
        st.metric("Roster slots", "9 (QB/2RB/3WR/TE/FLEX/DST)")

    st.caption(
        "Under the hood: `fantasy/dfs/dfs_pipeline.ipynb` — "
        "integer linear program via PuLP, projections from my per-position XGBoost models."
    )
