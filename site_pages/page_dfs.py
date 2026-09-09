"""Public UI for the reviewed DraftKings Classic optimizer."""
from __future__ import annotations

from io import BytesIO

import pandas as pd
import streamlit as st

import dfs_runtime as runtime
from dashboard_chrome import TABLE_HEIGHT, exact_table_height, dataframe_phone_desktop

_LINEUP_PHONE_COLS = ["Slot", "Player", "Pos", "Salary", "DK projection"]


def _player_labels(pool: pd.DataFrame) -> dict[str, str]:
    labels = {}
    for row in pool[pool["optimization_eligible"]].itertuples():
        labels[str(row.player_key)] = (
            f"{row.name} · {row.position} · {row.team} · ${int(row.salary):,} · {row.dfs_proj_pts:.1f} pts"
        )
    return labels


def _render_pool_summary(pool: pd.DataFrame, summary: dict) -> None:
    eligible = pool[pool["optimization_eligible"]]
    salary_skill = pool[pool["salary_eligible"] & pool["position"].ne("DST")]
    coverage = 100.0 * float(salary_skill["used_model"].mean()) if len(salary_skill) else 0.0
    excluded = int((~pool["optimization_eligible"]).sum())

    with st.container(horizontal=True, key="jsa-metric-even-dfs"):
        st.metric("Players", f"{len(pool):,}", border=True)
        st.metric("Eligible", f"{len(eligible):,}", border=True)
        st.metric("Model coverage", f"{coverage:.1f}%", border=True)
        st.metric("Excluded", f"{excluded:,}", border=True)
    games = ", ".join(summary.get("games", [])) or "Game metadata unavailable"
    dst_note = pool.attrs.get("dst_caption", "DST: DraftKings average (no game line)")
    st.caption(f"{summary.get('n_games', 0)} games · {games} · {dst_note}.")

    audit = pool[
        ["name", "position", "team", "salary", "status", "match", "match_name",
         "dfs_proj_pts", "optimization_eligible", "exclusion_reason"]
    ].rename(columns={
        "name": "Player", "position": "Pos", "team": "Team", "salary": "Salary",
        "status": "Status", "match": "Match", "match_name": "Projection player",
        "dfs_proj_pts": "DK projection", "optimization_eligible": "Eligible",
        "exclusion_reason": "Exclusion reason",
    })
    with st.expander("Review projection matches", expanded=False, icon=":material/fact_check:"):
        st.dataframe(
            audit,
            hide_index=True,
            column_config={
                "Salary": st.column_config.NumberColumn(format="$%d"),
                "DK projection": st.column_config.NumberColumn(format="%.1f"),
                "Eligible": st.column_config.CheckboxColumn(),
            },
        )


def _render_lineup(pipeline, lineup: pd.DataFrame) -> None:
    salary = int(lineup["salary"].sum())
    projection = float(lineup["dfs_proj_pts"].sum())
    st.subheader("Optimized lineup")
    with st.container(horizontal=True, key="jsa-metric-even-dfs-lineup"):
        st.metric("Projected DK points", f"{projection:.1f}", border=True)
        st.metric("Salary used", f"${salary:,}", border=True)
        st.metric("Cap remaining", f"${50_000 - salary:,}", border=True)

    table = lineup[["Slot", "name", "position", "team", "salary", "dfs_proj_pts", "status"]].rename(
        columns={"name": "Player", "position": "Pos", "team": "Team", "salary": "Salary",
                 "dfs_proj_pts": "DK projection", "status": "Status"}
    )
    col_config = {
        "Salary": st.column_config.NumberColumn(format="$%d"),
        "DK projection": st.column_config.NumberColumn(format="%.1f"),
    }
    phone_cols = [col for col in _LINEUP_PHONE_COLS if col in table.columns]
    dataframe_phone_desktop(
        table,
        table[phone_cols],
        slug="dfs-lineup",
        hide_index=True,
        width="stretch",
        height=exact_table_height(len(table)),
        column_config=col_config,
        key="dfs_lineup_grid",
    )
    st.download_button(
        "Download DraftKings lineup",
        data=pipeline.lineup_csv_text(lineup),
        file_name="dk_lineup.csv",
        mime="text/csv",
        type="primary",
        icon=":material/download:",
    )


def render():
    st.title("DFS optimizer")
    with st.container(horizontal=True, vertical_alignment="center"):
        st.badge("Beta", icon=":material/science:", color="orange")
        st.caption(
            "DraftKings NFL Classic. Calibrated DK-point projections. "
            "Integer lineup under the $50,000 cap."
        )
    st.warning(
        "**Beta.** Cash optimizes expected points; Tournament optimizes an "
        "85th-percentile player ceiling. Neither mode models stacking, ownership, or "
        "the full DraftKings player pool. Treat every lineup as a starting point, not a play.",
        icon=":material/science:",
    )
    with st.expander("What this beta does — and does not do", expanded=False):
        st.markdown(
            "Cash builds the highest-expected-score lineup from mean projections. "
            "Tournament swaps in a per-player 85th-percentile ceiling, which is the "
            "right direction for GPPs — first place usually needs roughly 4x salary "
            "per slot, around 200 points — but a ceiling objective alone is not a GPP "
            "model. There is no stacking or ownership leverage yet, so the lineup "
            "ignores correlation between a quarterback and his receivers and ignores "
            "what the field will roster. Anyone we do not project is excluded, which "
            "mostly removes minimum-salary players."
        )

    try:
        pipeline = runtime.load_pipeline()
    except runtime.DfsRuntimeUnavailable as exc:
        st.info(
            "DFS optimizer runtime is unavailable. Install the public site dependencies "
            "and reload this page."
        )
        st.caption(str(exc))
        return

    latest = runtime.latest_projection_path()
    left, right = st.columns(2)
    salary_upload = left.file_uploader(
        "DraftKings salary CSV",
        type=["csv"],
        key="dfs_salary_upload",
        help="Use the salary export from the NFL Classic contest you want to optimize.",
    )
    projection_upload = right.file_uploader(
        "Direct-DK projection CSV",
        type=["csv"],
        key="dfs_projection_upload",
        help="Required until a verified direct-DK artifact for the current week is published.",
    )

    if salary_upload is None:
        st.info("Upload a DraftKings NFL Classic salary CSV to inspect the slate.", icon=":material/upload_file:")
        if latest is not None:
            st.caption(f"Verified projection artifact ready: `{latest.name}`")
        return

    salary_bytes = runtime.read_bytes(salary_upload)
    try:
        salary_frame = pipeline.salary_eligibility(
            pipeline.load_dk_salaries(BytesIO(salary_bytes))
        )
        salary_summary = pipeline.slate_summary(salary_frame)
        if not salary_summary["dates"]:
            raise ValueError("salary slate has no parsable Game Info date")
        if not salary_frame["salary_eligible"].any():
            raise ValueError("salary file contains no eligible NFL Classic players")
    except (KeyError, ValueError, pd.errors.ParserError) as exc:
        st.error(f"Salary validation failed: {exc}", icon=":material/error:")
        return

    dates = ", ".join(salary_summary["dates"])
    st.success(
        f"Salary slate accepted: {salary_summary['n_rows']:,} players · "
        f"{salary_summary['n_games']} games · {dates}."
    )

    if projection_upload is None and latest is None:
        st.warning(
            "Your salary file is valid. Direct-DK projections for this slate are not published yet, "
            "so the optimizer cannot generate a lineup. This is a projection-data gap, not a problem "
            "with your DraftKings CSV. Upload a compatible direct-DK projection CSV or wait for the "
            "producer artifact."
        )
        return

    if projection_upload is not None:
        projection_bytes = runtime.read_bytes(projection_upload)
        projection_label = projection_upload.name
    else:
        projection_bytes = latest.read_bytes()
        projection_label = latest.name

    # Cash maximises the expected score. Tournaments pay the right tail, so they
    # optimise an 85th-percentile OUTCOME instead. Residuals are right skewed:
    # the median residual is negative at every position while the mean is zero,
    # so most players miss their projection and a few blow past it. A winning
    # GPP lineup is roughly 4x salary per $1000, about 200 points, which the
    # mean objective cannot reach by construction.
    objective = st.radio(
        "Objective",
        ["Cash (expected points)", "Tournament (ceiling)"],
        horizontal=True,
        key="dfs_objective",
        help=(
            "Cash builds the highest expected score. Tournament swaps in an "
            "85th-percentile outcome per player, which is what a first-place "
            "lineup actually needs. Ceiling models neither stacking nor "
            "ownership, so it is a starting point for a GPP, not a full one."
        ),
    )
    use_ceiling = objective.startswith("Tournament")
    if use_ceiling:
        _pf = pd.read_csv(BytesIO(projection_bytes))
        if "ceiling_pts" in _pf.columns and _pf["ceiling_pts"].notna().any():
            _pf["projected_pts"] = pd.to_numeric(_pf["ceiling_pts"], errors="coerce")
            projection_bytes = _pf.to_csv(index=False).encode("utf-8")
            projection_label = f"{projection_label} (ceiling)"
        else:
            st.warning(
                "This projection file has no `ceiling_pts` column, so Tournament "
                "mode falls back to expected points.",
                icon=":material/warning:",
            )
            use_ceiling = False

    source_key = runtime.source_digest(salary_bytes, projection_bytes)
    if st.session_state.get("dfs_input_key") != source_key:
        st.session_state["dfs_input_key"] = source_key
        st.session_state.pop("dfs_lineup", None)

    try:
        pool = pipeline.build_pool(BytesIO(salary_bytes), BytesIO(projection_bytes))
        summary = pipeline.slate_summary(pool)
    except (KeyError, ValueError, pd.errors.ParserError) as exc:
        st.error(f"Slate validation failed: {exc}", icon=":material/error:")
        return

    st.caption(
        f"Projection source: `{projection_label}` · "
        f"{pool.attrs['projection_season']} Week {pool.attrs['projection_week']} · direct DK points"
    )
    if projection_upload is None:
        # Say what the shipped artifact actually is. Week 1 is a calibrated
        # translation of Sleeper; Week 2 onward is our own half-PPR model,
        # calibrated the same way. Neither is trained on DraftKings points.
        st.info(
            "Week 1 projections come from Sleeper, mapped onto DraftKings Classic "
            "scoring with one calibration per position. Sleeper ranked players better "
            "than our model did at a season boundary on the 2025 check (Spearman 0.786 "
            "against 0.729), and our model has no in-season form to work from in Week 1. "
            "From Week 2 the site's own half-PPR projections take over, calibrated the "
            "same way against actual DK points on 2025 out-of-sample predictions. "
            "Tournament mode uses a per-position 85th-percentile ceiling rather than the "
            "mean. Neither mode is a model trained directly on DraftKings scoring, and "
            "neither models ownership or correlation. Lineups are a starting point, not "
            "a play recommendation.",
            icon=":material/info:",
        )
    _render_pool_summary(pool, summary)
    labels = _player_labels(pool)
    eligible = pool[pool["optimization_eligible"]]
    position_counts = eligible["position"].value_counts().to_dict()
    required = {"QB": 1, "RB": 2, "WR": 3, "TE": 1, "DST": 1}
    missing = {pos: need - position_counts.get(pos, 0) for pos, need in required.items()
               if position_counts.get(pos, 0) < need}
    if missing or int(eligible["position"].isin(["RB", "WR", "TE"]).sum()) < 7:
        st.error(f"The eligible pool cannot form a Classic roster. Missing position depth: {missing}")
        return

    with st.form("dfs_optimize_form"):
        st.subheader("Lineup controls")
        left, right = st.columns(2)
        locked = left.multiselect(
            "Lock players",
            options=list(labels),
            format_func=labels.get,
            key="dfs_locked",
        )
        excluded = right.multiselect(
            "Exclude players",
            options=list(labels),
            format_func=labels.get,
            key="dfs_excluded",
        )
        submitted = st.form_submit_button(
            "Optimize lineup",
            type="primary",
            icon=":material/auto_awesome:",
        )

    if submitted:
        st.session_state.pop("dfs_lineup", None)
        overlap = sorted(set(locked) & set(excluded))
        if overlap:
            st.error("A player cannot be both locked and excluded.")
        else:
            try:
                lineup = pipeline.solve_pool(pool, locked=locked, excluded=excluded)
            except (ValueError, RuntimeError) as exc:
                st.error(f"No legal lineup satisfies these locks and exclusions: {exc}")
            else:
                if lineup is None:
                    st.error("No legal lineup satisfies these locks and exclusions.")
                else:
                    st.session_state["dfs_lineup"] = lineup

    lineup = st.session_state.get("dfs_lineup")
    if isinstance(lineup, pd.DataFrame):
        _render_lineup(pipeline, lineup)

    st.caption(
        "Public optimizer preview. OUT/IR/D/PUP/SUSP/NFI and unmatched skill players are excluded by default; "
        "questionable players remain eligible. Verify late news and the DraftKings import preview before entry."
    )
    st.caption(
        "The optimizer maximizes this model's projections; historical diagnostics have not established a "
        "projection edge. Treat the output as research, not a performance claim."
    )
