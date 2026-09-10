"""Weekly Fantasy page. 2025 demo CSVs plus validated 2026 releases."""
import html as _html
import itertools as _it
import json
import os
from datetime import datetime as dt
from pathlib import Path

import pandas as pd
import streamlit as st

import page_common
from fantasy_scoring import DEFAULT_SCORING, SCORING_MODES, points_from_half_ppr
from dashboard_chrome import TABLE_HEIGHT, dataframe_phone_desktop, _OFFLINE
from publishing.manifest import published_builds
from publishing.paths import resolve_site_path

_HERE = Path(__file__).resolve().parents[1]
DEMO_SEASON = 2025
DEMO_WEEK = 17
LIVE_FROM_SEASON = 2026
LIVE_WEEK = 1
REG_WEEKS = tuple(range(1, 19))
LIVE_FORMAT_PREVIEW = (DEMO_SEASON, DEMO_WEEK)
# The frozen Week 17 artifact mislabeled this Reserve/Injured player as healthy.
# Keep the archived source byte-identical and correct only the public preview.
WEEKLY_DISPLAY_EXCLUSIONS = {
    LIVE_FORMAT_PREVIEW: frozenset({"00-0040715"}),
}
# injury_status_score: 0 Out, 0.1 Doubtful, 0.5 Questionable, 1.0 healthy.
# Questionable players often play; Out and Doubtful do not belong on the board.
RULED_OUT_INJURY_SCORE = 0.1
RULED_OUT_STATUSES = frozenset({"Out", "Doubtful"})
# Weekly roster codes. Season-roster fallback omits INA (D45: season INA undercounts).
UNAVAILABLE_WEEKLY_STATUS = frozenset({"IR", "RES", "PUP", "INA", "OUT", "SUS"})
UNAVAILABLE_SEASON_STATUS = frozenset({"IR", "RES", "PUP", "OUT", "SUS"})
PREVIEW_DETAIL_SOURCE_COLUMNS = (
    "pred_qb_pass_yards", "pred_qb_rush_yards", "pred_rush_yards",
    "pred_rec_yards", "pred_wr_rec_yards", "pred_te_rec_yards",
    "off_epa_rank", "implied_team_total", "injury_status_score",
)
PREVIEW_SIMPLE_COLUMNS = ["Player", "Opponent", "Proj Pts"]
PREVIEW_PHONE_COLUMNS = ["#", "Player", "Opponent", "Proj Pts", "Health", "Actual Pts"]
PREVIEW_PHONE_SLEEPER_COLUMNS = [
    "#", "Player", "Proj Pts", "Sleeper", "Opponent", "Health", "Actual Pts",
]
PREVIEW_PROJECTED_COLUMNS = {
    "QB": ["Proj Pass Yds", "Proj Rush Yds"],
    "RB": ["Proj Rush Yds", "Proj Rec Yds"],
    "WR": ["Proj Rec Yds"],
    "TE": ["Proj Rec Yds"],
}
PREVIEW_CONTEXT_COLUMNS = ["EPA Rank", "Team Total", "Health"]
PREVIEW_ACTUAL_COLUMNS = {
    "QB": ["Actual Pass Yds", "Actual Rush Yds"],
    "RB": ["Actual Rush Yds", "Actual Rec Yds"],
    "WR": ["Actual Rec Yds"],
    "TE": ["Actual Rec Yds"],
}
_JSA_PROJ_DIR = _HERE / "fantasy" / "fantasy_projections"


def _parse_proj_name(name: str) -> tuple[int, int] | None:
    stem = name.replace(".csv", "")
    parts = stem.split("_")
    try:
        season = int(parts[1])
        week = int(parts[2].replace("week", ""))
    except (IndexError, ValueError):
        return None
    return season, week


def available_projection_files() -> dict[tuple[int, int], Path]:
    """Return public artifacts only: 2025 legacy files plus validated releases."""
    available: dict[tuple[int, int], Path] = {}
    if _JSA_PROJ_DIR.is_dir():
        for path in sorted(_JSA_PROJ_DIR.glob("projections_*.csv")):
            parsed = _parse_proj_name(path.name)
            if parsed is not None and parsed[0] < LIVE_FROM_SEASON:
                available[parsed] = path
    manifest = page_common.load_release_manifest()
    for build in published_builds("fantasy", manifest=manifest, root=_HERE):
        try:
            key = (int(build["season"]), int(build["week"]))
            path = resolve_site_path(build["artifact"], _HERE)
        except (KeyError, TypeError, ValueError):
            continue
        if path.is_file():
            available[key] = path
    return available


def _weeks_by_season(available: dict[tuple[int, int], Path]) -> dict[int, list[int]]:
    demo_weeks = sorted({w for (season, w) in available if season == DEMO_SEASON})
    weeks = {
        LIVE_FROM_SEASON: list(REG_WEEKS),
        DEMO_SEASON: demo_weeks or [10],
    }
    for season, week in available:
        if season in weeks:
            continue
        weeks.setdefault(season, [])
        if week not in weeks[season]:
            weeks[season].append(week)
    for season in weeks:
        weeks[season] = sorted(weeks[season])
    return weeks


def _fantasy_season_week_controls(
    available: dict[tuple[int, int], Path],
    default: tuple[int, int] = (DEMO_SEASON, DEMO_WEEK),
) -> tuple[int, int]:
    """Own Season/Week widgets, seeded by the active validated release."""
    weeks_by = _weeks_by_season(available)
    seasons = sorted(weeks_by, reverse=True)
    with st.container(key="jsa-filter-bar"):
        cols = st.columns(2)
        season_seeded = page_common.seed_widget_from_query("wf_season", "wf_season", seasons)
        season_kwargs = {
            "key": "wf_season",
            "on_change": page_common.reset_widget_and_query,
            "args": ("wf_week", "wf_week"),
        }
        if not season_seeded and "wf_season" not in st.session_state and default[0] in seasons:
            season_kwargs["index"] = seasons.index(default[0])
        season = int(cols[0].selectbox("Season", seasons, **season_kwargs))
        page_common.sync_query_value("wf_season", season)
        weeks = weeks_by[season]
        want = default[1] if season == default[0] else (
            DEMO_WEEK if season == DEMO_SEASON else (
                LIVE_WEEK if season >= LIVE_FROM_SEASON else weeks[0]
            )
        )
        if "wf_week" in st.session_state and st.session_state["wf_week"] not in weeks:
            del st.session_state["wf_week"]
        seeded = page_common.seed_widget_from_query("wf_week", "wf_week", weeks)
        week_kwargs = {"key": "wf_week"}
        if not seeded and "wf_week" not in st.session_state:
            week_kwargs["index"] = weeks.index(want) if want in weeks else 0
        week = int(cols[1].selectbox("Week", weeks, **week_kwargs))
        page_common.sync_query_value("wf_week", week)
    return season, week


def _coming_soon_copy(season: int, week: int) -> str:
    return (
        f"{season} Week {week} projections are not published yet. They land later "
        "this week. Fantasy is published as immutable revisions: each game's rows "
        "lock at kickoff while future games remain eligible for the next revision. "
        "Switch Season to 2025 for a demo of this board."
    )


def _preview_detail_available(frame: pd.DataFrame) -> bool:
    return set(PREVIEW_DETAIL_SOURCE_COLUMNS) <= set(frame.columns)


_WEEKLY_RECEPTION_COLUMNS = {
    "QB": "pred_qb_receptions", "RB": "pred_rb_receptions",
    "WR": "pred_wr_receptions", "TE": "pred_te_receptions",
}
_WEEKLY_RECEPTION_FALLBACKS = {"QB": 0.0, "RB": 2.5, "WR": 5.5, "TE": 4.5}


def apply_weekly_scoring(frame: pd.DataFrame, scoring: str) -> pd.DataFrame:
    """Apply the selected format to both our and Sleeper's weekly points."""
    out = frame.copy()
    receptions = pd.Series(float("nan"), index=out.index, dtype="float64")
    for position, column in _WEEKLY_RECEPTION_COLUMNS.items():
        mask = out["position"].eq(position)
        if column in out.columns:
            values = pd.to_numeric(out.loc[mask, column], errors="coerce")
            receptions.loc[mask] = values.fillna(_WEEKLY_RECEPTION_FALLBACKS[position])
        else:
            receptions.loc[mask] = _WEEKLY_RECEPTION_FALLBACKS[position]

    out["_scoring_pts"] = points_from_half_ppr(out["projected_pts"], receptions, scoring)
    if "slp_proj" in out.columns:
        out["_sleeper_scoring_pts"] = points_from_half_ppr(
            out["slp_proj"], receptions, scoring
        )
    return out


def _show_sleeper_comparison(season: int, week: int) -> bool:
    """Show Sleeper beside our number for live week 1 only.

    Measured on the 2025 holdout, week 1: our MAE beats Sleeper at every
    position (3.29 vs 3.49 overall) but our rank correlation loses at every
    position (0.728 vs 0.784; RB 0.697 vs 0.828). A start/sit board is a
    ranking product, so at week 1 we are the weaker ranker and say so instead
    of hiding it. From week 2 the window fills with current-season games and
    the gap closes, so the comparison column comes off.
    """
    return int(season) >= LIVE_FROM_SEASON and int(week) == 1


def _uses_preview_layout(season: int, week: int) -> bool:
    return (int(season), int(week)) == LIVE_FORMAT_PREVIEW or int(season) >= LIVE_FROM_SEASON


def _apply_display_exclusions(
    frame: pd.DataFrame,
    season: int,
    week: int,
) -> pd.DataFrame:
    excluded_ids = WEEKLY_DISPLAY_EXCLUSIONS.get(
        (int(season), int(week)), frozenset()
    )
    if not excluded_ids or "player_id" not in frame.columns:
        return frame
    return frame.loc[
        ~frame["player_id"].astype(str).isin(excluded_ids)
    ].copy()


def _ruled_out_by_injury(frame: pd.DataFrame) -> pd.Series:
    """True for Out or Doubtful. Questionable stays until box-score DNP."""
    mask = pd.Series(False, index=frame.index)
    if "injury_status_score" in frame.columns:
        score = pd.to_numeric(frame["injury_status_score"], errors="coerce")
        mask = mask | score.le(RULED_OUT_INJURY_SCORE)
    if "injury_status" in frame.columns:
        status = frame["injury_status"].astype("string").str.strip()
        mask = mask | status.isin(RULED_OUT_STATUSES)
    return mask.fillna(False)


def eligible_board_rows(
    frame: pd.DataFrame,
    season: int,
    week: int,
    *,
    played_ids: set[str] | frozenset[str] | None = None,
    unavailable_ids: set[str] | frozenset[str] | None = None,
) -> pd.DataFrame:
    """Rows allowed on the public board. Frozen CSVs stay byte-identical.

    Drops hardcoded exclusions, Out/Doubtful, roster IR/inactives, and (once
    box scores exist) anyone with no player_stats row for that week.
    """
    out = _apply_display_exclusions(frame, season, week)
    if out.empty or "player_id" not in out.columns:
        return out
    out = out.loc[~_ruled_out_by_injury(out)].copy()
    pid = out["player_id"].astype(str)

    def alias_hit(values) -> pd.Series:
        wanted = {str(x) for x in values}
        mask = pd.Series(False, index=out.index)
        for col in ("player_id", "gsis_id", "sleeper_id"):
            if col in out.columns:
                mask = mask | out[col].astype(str).isin(wanted)
        return mask

    blocked = {str(x) for x in (unavailable_ids or ())}
    if blocked:
        out = out.loc[~alias_hit(blocked)].copy()
        pid = out["player_id"].astype(str)
    if played_ids is not None:
        out = out.loc[alias_hit(played_ids)].copy()
    return out


def _roster_player_id_column(frame: pd.DataFrame) -> str | None:
    for col in ("gsis_id", "player_id"):
        if col in frame.columns:
            return col
    return None


def _ids_with_status(frame: pd.DataFrame, statuses: frozenset[str]) -> frozenset[str]:
    id_cols = [col for col in ("gsis_id", "sleeper_id", "player_id") if col in frame.columns]
    if not id_cols or "status" not in frame.columns or frame.empty:
        return frozenset()
    status = frame["status"].astype("string").str.strip().str.upper()
    selected = frame.loc[status.isin({s.upper() for s in statuses})]
    values = set()
    for col in id_cols:
        values.update(selected[col].dropna().astype(str).str.strip())
    return frozenset(value for value in values if value)


def _to_pandas(raw):
    return raw.to_pandas() if hasattr(raw, "to_pandas") else raw


@st.cache_data(ttl=3600, max_entries=4)
def _load_weekly_rosters_season(season: int) -> pd.DataFrame | None:
    try:
        import nflreadpy as nfl
        raw = _to_pandas(nfl.load_rosters_weekly([season]))
        keep = [c for c in ("gsis_id", "player_id", "week", "status") if c in raw.columns]
        return raw.loc[:, keep].copy() if keep else None
    except Exception as err:
        import logging as _logging
        _logging.warning("load_rosters_weekly(%s) failed: %s", season, err)
        return None


@st.cache_data(ttl=3600, max_entries=4)
def _load_season_rosters(season: int) -> pd.DataFrame | None:
    try:
        import nflreadpy as nfl
        raw = _to_pandas(nfl.load_rosters([season]))
        keep = [c for c in ("gsis_id", "player_id", "status") if c in raw.columns]
        return raw.loc[:, keep].copy() if keep else None
    except Exception as err:
        import logging as _logging
        _logging.warning("load_rosters(%s) failed: %s", season, err)
        return None


def unavailable_roster_ids(season: int, week: int) -> frozenset[str]:
    """Players who should not appear before box scores exist.

    Weekly INA is the inactive list. Season IR/RES/PUP still apply so a
    reserve player does not sit on the board until that list posts.
    """
    if _OFFLINE:
        return frozenset()
    ids: set[str] = set()
    weekly = _load_weekly_rosters_season(int(season))
    if weekly is not None and "week" in weekly.columns:
        week_rows = weekly.loc[
            pd.to_numeric(weekly["week"], errors="coerce").eq(int(week))
        ]
        ids.update(_ids_with_status(week_rows, UNAVAILABLE_WEEKLY_STATUS))
    seasonal = _load_season_rosters(int(season))
    if seasonal is not None:
        ids.update(_ids_with_status(seasonal, UNAVAILABLE_SEASON_STATUS))
    return frozenset(ids)


def _preview_table_columns(
    position: str,
    show_more_info: bool,
    actuals_in: bool,
    show_sleeper: bool = False,
) -> list[str]:
    columns = list(PREVIEW_SIMPLE_COLUMNS)
    if show_sleeper:
        columns.append("Sleeper")
    if show_more_info:
        columns.extend(PREVIEW_PROJECTED_COLUMNS[position])
        columns.extend(PREVIEW_CONTEXT_COLUMNS)
    if actuals_in:
        columns.append("Actual Pts")
        columns.extend(PREVIEW_ACTUAL_COLUMNS[position])
    return columns


def _preview_phone_columns(available_columns, *, show_sleeper: bool) -> list[str]:
    """Keep the Week 1 benchmark next to our projection on narrow screens."""
    preferred = PREVIEW_PHONE_SLEEPER_COLUMNS if show_sleeper else PREVIEW_PHONE_COLUMNS
    return [column for column in preferred if column in available_columns]


@st.cache_data(ttl=3600)
def _load_proj_csv(path: str) -> pd.DataFrame:
    return pd.read_csv(path)


_ACTUAL_STAT_COLUMNS = [
    'season_type', 'week', 'position', 'player_id',
    'passing_yards', 'passing_tds', 'passing_interceptions',
    'rushing_yards', 'rushing_tds', 'receptions', 'receiving_yards',
    'receiving_tds', 'rushing_fumbles_lost', 'receiving_fumbles_lost',
]


@st.cache_data(ttl=3600, max_entries=4)
def _load_actual_stats_season(season: int) -> pd.DataFrame | None:
    """Fetch one season once; week selection stays a cheap local filter."""
    try:
        import nflreadpy as nfl
        raw = nfl.load_player_stats([season])
        if hasattr(raw, 'to_pandas'):
            raw = raw.to_pandas()
        return raw.loc[
            (raw['season_type'] == 'REG') &
            raw['position'].isin(['QB', 'RB', 'WR', 'TE']),
            _ACTUAL_STAT_COLUMNS,
        ].copy()
    except Exception as _e:
        import logging as _logging
        _logging.warning(f"_load_actual_stats_season({season}) failed: {_e}")
        return None


def load_actual_stats(season: int, week: int) -> dict:
    """Build the existing weekly lookup schema from a cached season pull."""
    if _OFFLINE:
        return {}
    raw = _load_actual_stats_season(season)
    if raw is None:
        return {}
    try:
        stats = raw[raw['week'] == week].copy()
        stats['actual_half_ppr'] = (
            stats['passing_yards'].fillna(0) * 0.04 +
            stats['passing_tds'].fillna(0) * 4 +
            stats['passing_interceptions'].fillna(0) * -2 +
            stats['rushing_yards'].fillna(0) * 0.1 +
            stats['rushing_tds'].fillna(0) * 6 +
            stats['receptions'].fillna(0) * 0.5 +
            stats['receiving_yards'].fillna(0) * 0.1 +
            stats['receiving_tds'].fillna(0) * 6 +
            stats['rushing_fumbles_lost'].fillna(0) * -2 +
            stats['receiving_fumbles_lost'].fillna(0) * -2
        )
        by_pos = {pos: grp.set_index('player_id') for pos, grp in stats.groupby('position')}

        def _col(pos_key, col):
            g = by_pos.get(pos_key)
            return g[col].fillna(0).to_dict() if g is not None and col in g.columns else {}

        return {
            'half_ppr':    stats.set_index('player_id')['actual_half_ppr'].to_dict(),
            'qb_pass_yds': _col('QB', 'passing_yards'),
            'qb_rush_yds': _col('QB', 'rushing_yards'),
            'rb_rush_yds': _col('RB', 'rushing_yards'),
            'rb_rec_yds':  _col('RB', 'receiving_yards'),
            'wr_rec_yds':  _col('WR', 'receiving_yards'),
            'wr_recs':     _col('WR', 'receptions'),
            'te_rec_yds':  _col('TE', 'receiving_yards'),
            'te_recs':     _col('TE', 'receptions'),
            'qb_recs':     _col('QB', 'receptions'),
            'rb_recs':     _col('RB', 'receptions'),
        }
    except Exception as _e:
        import logging as _logging
        _logging.warning(f"load_actual_stats({season}, {week}) failed: {_e}")
        return {}


def render():
    st.title("Weekly fantasy projections")
    st.caption(
        "Player rankings by scoring format, independent stat estimates when published, "
        "and postgame actuals."
    )
    available = available_projection_files()
    default = page_common.release_default_selection(
        "fantasy", (DEMO_SEASON, DEMO_WEEK)
    )
    season, week = _fantasy_season_week_controls(available, default)
    page_common.render_release_status("fantasy", season, week)
    scoring = st.segmented_control(
        "Scoring format", list(SCORING_MODES), default=DEFAULT_SCORING,
        key="wf_scoring", help="Choose how reception points are counted.",
    ) or DEFAULT_SCORING
    st.caption(
        f"Scoring view: **{scoring}**. Projection points recalculate from receptions; "
        "live slim artifacts use position-level reception estimates when individual "
        "reception projections are not included."
    )

    st.subheader(f"Week {week} · {season} season")

    if (season, week) not in available:
        if int(season) >= LIVE_FROM_SEASON:
            st.info(_coming_soon_copy(int(season), int(week)))
        else:
            listed = ", ".join(
                f"W{w}" for (s, w) in sorted(available) if s == season
            ) or "none for this season"
            st.info(
                f"No fantasy projections for Season {season} Week {week}. "
                f"Available weeks: {listed}. "
                "2025 on this page is a demo."
            )
    else:
        live_format_preview = (int(season), int(week)) == LIVE_FORMAT_PREVIEW
        if int(season) >= LIVE_FROM_SEASON:
            st.success(
                "Live 2026. Our model scores the players; Sleeper supplies coverage and, "
                "in Week 1 only, the comparison. Rankings lock per game at kickoff, and later "
                "revisions change future games only."
            )
        elif live_format_preview:
            st.info(
                "2026 format preview: these are the frozen 2025 Week 17 projections "
                "in the planned live layout. Rankings are simple by default; turn on "
                "More info for the full matchup and stat context. The source CSV has "
                "not been changed."
            )
        elif int(season) == DEMO_SEASON:
            st.info(f"This is the 2025 Week {week} demo from the previous weekly model.")
        preview_layout = _uses_preview_layout(season, week)

        # Actual results (available after week is played)
        _actuals       = load_actual_stats(season, week)
        actuals_in     = bool(_actuals.get('half_ppr'))
        _half_ppr_dict     = _actuals.get('half_ppr',    {})
        actual_qb_pass_yds = _actuals.get('qb_pass_yds', {})
        actual_qb_rush_yds = _actuals.get('qb_rush_yds', {})
        actual_rush_yds    = _actuals.get('rb_rush_yds', {})
        actual_rb_rec_yds  = _actuals.get('rb_rec_yds',  {})
        actual_wr_rec_yds  = _actuals.get('wr_rec_yds',  {})
        actual_wr_recs     = _actuals.get('wr_recs',     {})
        actual_te_rec_yds  = _actuals.get('te_rec_yds',  {})
        actual_te_recs     = _actuals.get('te_recs',     {})
        actual_qb_recs     = _actuals.get('qb_recs',     {})
        actual_rb_recs     = _actuals.get('rb_recs',     {})

        played_ids = (
            {str(pid) for pid in _half_ppr_dict} if actuals_in else None
        )
        unavailable_ids = (
            frozenset() if actuals_in else unavailable_roster_ids(season, week)
        )
        proj_df = eligible_board_rows(
            _load_proj_csv(str(available[(season, week)])),
            season,
            week,
            played_ids=played_ids,
            unavailable_ids=unavailable_ids,
        )

        # The preview exercises the live 2026 surface, which has no legacy agent cards.
        fantasy_analysis = None
        if not live_format_preview:
            fa_path = str(_HERE / "fantasy" / f"agent_analysis_{season}_week{week}.json")
            try:
                if os.path.exists(fa_path):
                    with open(fa_path) as _f:
                        fantasy_analysis = json.load(_f)
            except (IOError, json.JSONDecodeError):
                fantasy_analysis = None

        if actuals_in:
            st.success(f"Results are in! Actual stats are now shown alongside projections for Week {week}.")
        else:
            st.caption("Games not yet played · actual stats appear after the week's results are in.")

        if _show_sleeper_comparison(season, week):
            st.info(
                "**Week 1 shows Sleeper's projection beside ours.** For start/sit "
                "ordering, use Sleeper where the two disagree this week.",
                icon=":material/compare_arrows:",
            )
            with st.expander("Why Sleeper is included for Week 1", expanded=False):
                st.markdown(
                    "Week 1 is the model's weakest week: with no current-season games "
                    "yet, every player's form comes from his last four games of last "
                    "season, which is mostly noise across an eight-month gap. Measured on 2025 "
                    "Week 1, our average error was smaller than Sleeper's at every "
                    "position, but our ordering was worse at every position (rank "
                    "correlation 0.73 against 0.78, and 0.70 against 0.83 at running "
                    "back). A start/sit board is a ranking, so Sleeper is the better bet "
                    "where the two disagree. The comparison column comes off in Week 2, "
                    "when the window fills with current-season games."
                )

        st.divider()

        show_more_info = False
        if preview_layout:
            detail_available = _preview_detail_available(proj_df)
            show_more_info = bool(st.toggle(
                "More info: projected yards for player props",
                value=False,
                key="wf_more_info",
                disabled=not detail_available,
                help=(
                    "Show projected pass, rush, and receiving yards by position, plus "
                    "last-four offensive EPA rank, implied team total, and health."
                ),
            )) and detail_available
            if detail_available:
                st.caption(
                    "Enable **More info** to compare our projected yardage with sportsbook "
                    "player-prop over/under lines. These are model estimates, not sportsbook "
                    "lines or betting recommendations."
                )
            else:
                st.caption(
                    "Player-prop yardage estimates will unlock here when the weekly release "
                    "includes component stat and matchup fields."
                )

        player_search = st.text_input(
            "Search player",
            placeholder="e.g. Mahomes, Jefferson, Kelce",
            key="fantasy_search"
        )

        ptab_qb, ptab_rb, ptab_wr, ptab_te = st.tabs(
            ["QB", "RB", "WR", "TE"],
            key="wf_position_tabs",
            on_change="rerun",
        )

        def injury_icon(score):
            if score >= 0.9:   return "✅"
            if score >= 0.5:   return "🟡"
            if score > 0:      return "⚠️"
            return "❌"

        def ordinal(n):
            if pd.isna(n):
                return "—"
            n = int(n)
            if 11 <= (n % 100) <= 13:
                return f"{n}th"
            return f"{n}{['th','st','nd','rd','th'][min(n % 10, 4)]}"

        def rank_color(rank, total=32):
            if pd.isna(rank):
                return ""
            ratio = (total - int(rank)) / (total - 1)
            r = int(255 * (1 - ratio))
            g = int(82 + 118 * ratio)
            return f"color: rgb({r},{g},82); font-weight: 600"

        def total_color(val, lo=16.0, hi=30.0):
            ratio = max(0.0, min(1.0, (val - lo) / (hi - lo)))
            r = int(255 * (1 - ratio))
            g = int(82 + 118 * ratio)
            return f"color: rgb({r},{g},82); font-weight: 600"

        def make_style_table(display_df):
            def _style(df):
                styles = pd.DataFrame("", index=df.index, columns=df.columns)
                if "Off EPA" in df.columns or "EPA Rank" in df.columns:
                    for i, rank in enumerate(display_df["off_epa_rank"]):
                        if "Off EPA" in df.columns:
                            styles.iloc[i, df.columns.get_loc("Off EPA")] = rank_color(rank)
                        if "EPA Rank" in df.columns:
                            styles.iloc[i, df.columns.get_loc("EPA Rank")] = rank_color(rank)
                if "Team Total" in df.columns:
                    for i, val in enumerate(display_df["implied_team_total"]):
                        styles.iloc[i, df.columns.get_loc("Team Total")] = total_color(val)
                styles["Proj Pts"] = "font-weight: 700; font-size: 15px"
                if "Actual Pts" in df.columns:
                    styles["Actual Pts"] = "font-weight: 700; font-size: 15px"
                return styles
            return _style

        _early_req = ["position", "projected_pts"]
        _early_missing = [c for c in _early_req if c not in proj_df.columns]
        if _early_missing:
            st.warning(f"Projection CSV is missing columns: {_early_missing}.")
            st.stop()

        proj_df = proj_df.copy()
        proj_df = apply_weekly_scoring(proj_df, scoring)

        for ptab, pos in zip([ptab_qb, ptab_rb, ptab_wr, ptab_te], ["QB", "RB", "WR", "TE"]):
            if not ptab.open:
                continue
            with ptab:
                pos_subset = proj_df[proj_df["position"] == pos]
                if pos == "QB" and "depth_chart_position" in pos_subset.columns:
                    pos_subset = pos_subset[pos_subset["depth_chart_position"] == 1]
                    pos_subset = pos_subset.sort_values("_scoring_pts", ascending=False).drop_duplicates(subset="team")
                # Rows shown per position tab. QB is 24 to match the scored
                # universe cap in the producer (UNIVERSE_CAPS), which is also
                # roughly a 12-team league's startable pool plus streamers.
                top_n = {"QB": 24, "RB": 40, "WR": 40, "TE": 24}.get(pos, 20)
                pos_df = pos_subset.sort_values("_scoring_pts", ascending=False)
                if player_search:
                    mask = pos_df["player_display_name"].str.contains(player_search, case=False, na=False, regex=False)
                    pos_df = pos_df[mask]
                elif (
                    _show_sleeper_comparison(season, week)
                    and "_sleeper_scoring_pts" in pos_df.columns
                    and pos_df["_sleeper_scoring_pts"].notna().any()
                ):
                    # Week 1 only: show the UNION of our top N and Sleeper's top N.
                    # Our week-1 ordering is the weaker of the two (rank correlation
                    # 0.73 against 0.78), so cutting the board at our own top N hides
                    # players Sleeper ranks as startable. Measured on this slate that
                    # was 26 players, including Mark Andrews, Jayden Daniels and
                    # Jaylen Waddle, most of them on new teams whose windows still
                    # describe their old role. Rows stay sorted by our projection so
                    # the disagreement is visible rather than resolved silently.
                    ours = pos_df.head(top_n)
                    theirs = pos_df.nlargest(top_n, "_sleeper_scoring_pts")
                    pos_df = (
                        pd.concat([ours, theirs])
                        .drop_duplicates(subset="player_id")
                        .sort_values("_scoring_pts", ascending=False)
                    )
                else:
                    pos_df = pos_df.head(top_n)
                pos_df = pos_df.reset_index(drop=True)
                pos_df.index += 1

                has_qb_stats = pos == "QB" and "pred_qb_pass_yards" in pos_df.columns
                has_rb_yds   = pos == "RB" and "pred_rush_yards" in pos_df.columns
                has_wr_stats = pos == "WR" and "pred_wr_rec_yards" in pos_df.columns
                has_te_stats = pos == "TE" and "pred_te_rec_yards" in pos_df.columns

                _core_cols = ["player_id", "player_display_name", "team", "opponent_team",
                              "projected_pts"]
                _missing_req = [c for c in _core_cols if c not in pos_df.columns]
                if _missing_req:
                    st.warning(f"Projection CSV is missing columns: {_missing_req}.")
                    continue
                keep = list(_core_cols)
                for extra in ("injury_status_score", "is_home", "off_epa_roll4",
                              "off_epa_rank", "implied_team_total", "slp_proj"):
                    if extra in pos_df.columns:
                        keep.append(extra)
                display = pos_df[keep].copy()
                if preview_layout:
                    empty_stat = pd.Series(float("nan"), index=pos_df.index)
                    display["Proj Pass Yds"] = (
                        pd.to_numeric(pos_df["pred_qb_pass_yards"], errors="coerce")
                        if pos == "QB" and "pred_qb_pass_yards" in pos_df else empty_stat
                    )
                    if pos == "QB" and "pred_qb_rush_yards" in pos_df:
                        display["Proj Rush Yds"] = pd.to_numeric(
                            pos_df["pred_qb_rush_yards"], errors="coerce"
                        )
                    elif pos == "RB" and "pred_rush_yards" in pos_df:
                        display["Proj Rush Yds"] = pd.to_numeric(
                            pos_df["pred_rush_yards"], errors="coerce"
                        )
                    else:
                        display["Proj Rush Yds"] = empty_stat
                    if pos == "RB" and "pred_rec_yards" in pos_df:
                        display["Proj Rec Yds"] = pd.to_numeric(
                            pos_df["pred_rec_yards"], errors="coerce"
                        )
                    elif pos == "WR" and "pred_wr_rec_yards" in pos_df:
                        display["Proj Rec Yds"] = pd.to_numeric(
                            pos_df["pred_wr_rec_yards"], errors="coerce"
                        )
                    elif pos == "TE" and "pred_te_rec_yards" in pos_df:
                        display["Proj Rec Yds"] = pd.to_numeric(
                            pos_df["pred_te_rec_yards"], errors="coerce"
                        )
                    else:
                        display["Proj Rec Yds"] = empty_stat
                else:
                    if has_qb_stats:
                        display["Proj Pass Yds"] = pos_df["pred_qb_pass_yards"].fillna(0).round(0).astype(int)
                        display["Proj Rush Yds"] = pos_df["pred_qb_rush_yards"].fillna(0).round(0).astype(int)
                    if has_rb_yds:
                        display["Proj Rush Yds"] = pos_df["pred_rush_yards"].fillna(0).round(0).astype(int)
                        display["Proj Rec Yds"]  = pos_df["pred_rec_yards"].fillna(0).round(0).astype(int)
                    if has_wr_stats:
                        display["Proj Receptions"] = pos_df["pred_wr_receptions"].fillna(0).round(1)
                        display["Proj Rec Yds"]    = pos_df["pred_wr_rec_yards"].fillna(0).round(0).astype(int)
                    if has_te_stats:
                        display["Proj Receptions"] = pos_df["pred_te_receptions"].fillna(0).round(1)
                        display["Proj Rec Yds"]    = pos_df["pred_te_rec_yards"].fillna(0).round(0).astype(int)

                display["Player"] = display["player_display_name"] + " - " + display["team"]
                if "is_home" in display.columns:
                    sep = display["is_home"].map(lambda h: "vs" if h in (1, True, 1.0) else "@")
                    display["Opponent"] = sep + " " + display["opponent_team"].astype(str)
                else:
                    display["Opponent"] = display["opponent_team"]
                display["Proj Pts"] = pos_df["_scoring_pts"].round(1).to_numpy()
                has_health = "injury_status_score" in display.columns
                has_epa_value = "off_epa_roll4" in display.columns
                has_epa_rank = "off_epa_rank" in display.columns
                has_epa = has_epa_value and has_epa_rank
                has_total = "implied_team_total" in display.columns
                if has_health:
                    display["Health"] = display["injury_status_score"].map(injury_icon)
                if has_epa_value:
                    display["Off EPA"] = display["off_epa_roll4"].round(3)
                if has_epa_rank:
                    display["EPA Rank"] = display["off_epa_rank"].map(ordinal)
                if has_total:
                    display["Team Total"] = display["implied_team_total"].round(1)

                _show_slp = (
                    _show_sleeper_comparison(season, week)
                    and "slp_proj" in display.columns
                    and display["slp_proj"].notna().any()
                )
                if _show_slp:
                    display["Sleeper"] = pd.to_numeric(
                        pos_df.loc[display.index, "_sleeper_scoring_pts"], errors="coerce"
                    ).round(1)
                if preview_layout:
                    base_cols = _preview_table_columns(
                        pos, show_more_info, actuals_in=False, show_sleeper=_show_slp
                    )
                else:
                    extra_stat = []
                    if has_qb_stats:
                        extra_stat = ["Proj Pass Yds", "Proj Rush Yds"]
                    elif has_rb_yds:
                        extra_stat = ["Proj Rush Yds", "Proj Rec Yds"]
                    elif has_wr_stats or has_te_stats:
                        extra_stat = ["Proj Receptions", "Proj Rec Yds"]
                    tail = []
                    if has_epa:
                        tail.extend(["Off EPA", "EPA Rank"])
                    if has_total:
                        tail.append("Team Total")
                    if has_health:
                        tail.append("Health")
                    base_cols = ["Player", "Opponent", "Proj Pts"] + extra_stat + tail

                if actuals_in:
                    _actual_raw = display["player_id"].map(_half_ppr_dict)
                    _actual_recs = {"QB": actual_qb_recs, "RB": actual_rb_recs,
                                    "WR": actual_wr_recs, "TE": actual_te_recs}[pos]
                    display["Actual Pts"] = points_from_half_ppr(
                        _actual_raw, display["player_id"].map(_actual_recs), scoring
                    ).round(1)
                    if preview_layout:
                        display["Actual Pass Yds"] = pd.to_numeric(
                            display["player_id"].map(actual_qb_pass_yds if pos == "QB" else {}),
                            errors="coerce",
                        )
                        if pos == "QB":
                            rush_actuals = actual_qb_rush_yds
                        elif pos == "RB":
                            rush_actuals = actual_rush_yds
                        else:
                            rush_actuals = {}
                        display["Actual Rush Yds"] = pd.to_numeric(
                            display["player_id"].map(rush_actuals), errors="coerce"
                        )
                        if pos == "RB":
                            rec_actuals = actual_rb_rec_yds
                        elif pos == "WR":
                            rec_actuals = actual_wr_rec_yds
                        elif pos == "TE":
                            rec_actuals = actual_te_rec_yds
                        else:
                            rec_actuals = {}
                        display["Actual Rec Yds"] = pd.to_numeric(
                            display["player_id"].map(rec_actuals), errors="coerce"
                        )
                        tbl_cols = _preview_table_columns(
                            pos, show_more_info, actuals_in=True
                        )
                    elif has_qb_stats:
                        display["Actual Pass Yds"] = pd.to_numeric(display["player_id"].map(actual_qb_pass_yds), errors="coerce")
                        display["Actual Rush Yds"] = pd.to_numeric(display["player_id"].map(actual_qb_rush_yds), errors="coerce")
                        tbl_cols = base_cols + ["Actual Pts", "Actual Pass Yds", "Actual Rush Yds"]
                    elif has_rb_yds:
                        display["Actual Rush Yds"] = pd.to_numeric(display["player_id"].map(actual_rush_yds),    errors="coerce")
                        display["Actual Rec Yds"]  = pd.to_numeric(display["player_id"].map(actual_rb_rec_yds),  errors="coerce")
                        tbl_cols = base_cols + ["Actual Pts", "Actual Rush Yds", "Actual Rec Yds"]
                    elif has_wr_stats:
                        display["Actual Receptions"] = pd.to_numeric(display["player_id"].map(actual_wr_recs),    errors="coerce")
                        display["Actual Rec Yds"]    = pd.to_numeric(display["player_id"].map(actual_wr_rec_yds), errors="coerce")
                        tbl_cols = base_cols + ["Actual Pts", "Actual Receptions", "Actual Rec Yds"]
                    elif has_te_stats:
                        display["Actual Receptions"] = pd.to_numeric(display["player_id"].map(actual_te_recs),    errors="coerce")
                        display["Actual Rec Yds"]    = pd.to_numeric(display["player_id"].map(actual_te_rec_yds), errors="coerce")
                        tbl_cols = base_cols + ["Actual Pts", "Actual Receptions", "Actual Rec Yds"]
                    else:
                        tbl_cols = base_cols + ["Actual Pts"]
                else:
                    tbl_cols = base_cols

                tbl = display[tbl_cols].copy()
                # Row counter for the table as currently sorted/searched — a reading aid only.
                tbl.insert(0, "#", range(1, len(tbl) + 1))
                style_fn = make_style_table(display)

                _dnp_note = "Blank = missing from the box-score feed. Players who did not play are removed from this board."
                col_config = {
                    "#":          st.column_config.NumberColumn("#", format="%d", width=50, pinned=True,   # grid minimum; pinned = grow 0, so it keeps that exact width
                                      help="Row number in this table as currently sorted and filtered — a counter to keep your place, not a ranking."),
                    "Player":     st.column_config.TextColumn("Player",
                                      help="Player name and NFL team."),
                    "Opponent":   st.column_config.TextColumn("Opponent",
                                      help="This week's opponent. '@' = away game, 'vs' = home game. Note: column sorts alphabetically — meaningful numeric sort not available for matchup labels."),
                    "EPA Rank":   st.column_config.TextColumn("EPA Rank",
                                      help="Team's last-four-game offensive EPA rank among all 32 NFL teams (1 = best offense, 32 = worst). Green is better; red is worse. Note: this text column sorts alphabetically."),
                    "Health":     st.column_config.TextColumn("Health",
                                      help="Player's injury status from the weekly NFL injury report.\n\n✅ Healthy  🟡 Questionable\n\nOut, Doubtful, IR, and anyone who did not play are removed from the board.\n\nNote: sorts alphabetically due to a Streamlit limitation."),
                    "Proj Pts":   st.column_config.NumberColumn("Proj Pts",   format="%.1f",
                                      help=f"Projected {scoring} fantasy points for this week. Standard = 0 points per reception, Half-PPR = 0.5, PPR = 1.0; yardage and touchdown scoring stays unchanged."),
                    "Sleeper":    st.column_config.NumberColumn("Sleeper",    format="%.1f",
                                      help=f"Sleeper's own {scoring} projection for this week, shown for comparison in week 1 only. On 2025 week 1 Sleeper ranked players better than we did at every position, so where the two disagree this week, theirs is the better bet. Not an input to our model."),
                    "Off EPA":    st.column_config.NumberColumn("Off EPA",    format="%+.3f",
                                      help="Team's offensive Expected Points Added (EPA) per play, averaged over the last 4 games. EPA measures how many points each play is worth above expectation. Higher = more efficient offense."),
                    "Team Total": st.column_config.NumberColumn("Team Total", format="%.1f",
                                      help="Vegas implied team total — the number of points Vegas expects this team to score. Derived by splitting the game over/under based on the point spread. Higher = Vegas expects more scoring, which generally means more fantasy opportunity."),
                }
                if preview_layout:
                    if show_more_info:
                        col_config["Proj Pass Yds"] = st.column_config.NumberColumn(
                            "Proj Pass Yds", format="%.1f",
                            help="Independent weekly passing-yards estimate. Blank when not applicable."
                        )
                        col_config["Proj Rush Yds"] = st.column_config.NumberColumn(
                            "Proj Rush Yds", format="%.1f",
                            help="Independent weekly rushing-yards estimate. Blank when not applicable."
                        )
                        col_config["Proj Rec Yds"] = st.column_config.NumberColumn(
                            "Proj Rec Yds", format="%.1f",
                            help="Independent weekly receiving-yards estimate. Blank when not applicable."
                        )
                else:
                    if has_qb_stats:
                        col_config["Proj Pass Yds"] = st.column_config.NumberColumn("Proj Pass Yds", format="%d",
                                          help="Projected passing yards for this game, from a separate XGBoost model trained specifically on QB passing stats. Useful as a reference for pass yards prop bets.")
                        col_config["Proj Rush Yds"] = st.column_config.NumberColumn("Proj Rush Yds", format="%d",
                                          help="Projected rushing yards for this game, from a separate XGBoost model trained on QB rushing stats. Useful as a reference for rush yards prop bets.")
                    if has_rb_yds:
                        col_config["Proj Rush Yds"] = st.column_config.NumberColumn("Proj Rush Yds", format="%d",
                                          help="Projected rushing yards for this game, from a separate XGBoost model trained on RB rushing stats. Useful as a reference for rush yards prop bets.")
                        col_config["Proj Rec Yds"]  = st.column_config.NumberColumn("Proj Rec Yds",  format="%d",
                                          help="Projected receiving yards for this game, from a separate XGBoost model trained on RB receiving stats. Useful as a reference for receiving yards prop bets.")
                    if has_wr_stats or has_te_stats:
                        col_config["Proj Receptions"] = st.column_config.NumberColumn("Proj Receptions", format="%.1f",
                                          help="Projected number of receptions for this game, from a separate XGBoost model. Useful as a reference for receptions prop bets.")
                        col_config["Proj Rec Yds"]    = st.column_config.NumberColumn("Proj Rec Yds",    format="%d",
                                          help="Projected receiving yards for this game, from a separate XGBoost model. Useful as a reference for receiving yards prop bets.")
                if actuals_in:
                    col_config["Actual Pts"]        = st.column_config.NumberColumn("Actual Pts",        format="%.1f",
                                      help=f"Actual half-PPR fantasy points scored in this game. {_dnp_note}")
                    col_config["Actual Pass Yds"]   = st.column_config.NumberColumn("Actual Pass Yds",   format="%d",
                                      help=f"Actual passing yards recorded in this game. {_dnp_note}")
                    col_config["Actual Rush Yds"]   = st.column_config.NumberColumn("Actual Rush Yds",   format="%d",
                                      help=f"Actual rushing yards recorded in this game. {_dnp_note}")
                    col_config["Actual Rec Yds"]    = st.column_config.NumberColumn("Actual Rec Yds",    format="%d",
                                      help=f"Actual receiving yards recorded in this game. {_dnp_note}")
                    col_config["Actual Receptions"] = st.column_config.NumberColumn("Actual Receptions", format="%.1f",
                                      help=f"Actual number of receptions recorded in this game. {_dnp_note}")

                if preview_layout:
                    phone_keep = _preview_phone_columns(
                        tbl.columns, show_sleeper=_show_slp,
                    )
                else:
                    phone_keep = [
                        col for col in (
                            "#", "Player", "Opponent", "Proj Pts", "Health", "Actual Pts",
                        ) if col in tbl.columns
                    ]
                dataframe_phone_desktop(
                    tbl.style.apply(style_fn, axis=None),
                    tbl[phone_keep].style.apply(style_fn, axis=None),
                    slug=f"wf-{pos.lower()}",
                    hide_index=True,
                    width="stretch",
                    height=TABLE_HEIGHT,
                    column_config=col_config,
                    key=(
                        f"wf_grid_{pos}_{season}_{week}_{player_search}_{len(tbl)}_"
                        f"{scoring}_{'detail' if show_more_info else 'simple'}"
                    ),
                )

                # ── Agent Analysis ────────────────────────────────────────────
                if fantasy_analysis and pos in fantasy_analysis:
                    pa = fantasy_analysis[pos]
                    st.markdown("#### 🤖 Agent Analysis")

                    # Headers row
                    # jsa-ff-head / jsa-ff-pair are inert on desktop. The card rows below are
                    # a raw CSS grid that does NOT stack on a phone, so mobile.py keeps these
                    # two headers side by side with it rather than letting st.columns stack
                    # them away from the cards they label.
                    h1, h2 = st.columns(2)
                    h1.markdown(
                        "<div class='jsa-ff-head' style='background:#0d2b0d;border:1px solid #00c853;"
                        "border-radius:8px;padding:10px 16px'>"
                        "<span style='color:#00c853;font-weight:700;font-size:13px;"
                        "letter-spacing:1px'>📈 LIKELY TO OUTPERFORM</span></div>",
                        unsafe_allow_html=True
                    )
                    h2.markdown(
                        "<div class='jsa-ff-head' style='background:#2b0d0d;border:1px solid #ff5252;"
                        "border-radius:8px;padding:10px 16px'>"
                        "<span style='color:#ff5252;font-weight:700;font-size:13px;"
                        "letter-spacing:1px'>📉 LIKELY TO UNDERPERFORM</span></div>",
                        unsafe_allow_html=True
                    )

                    # Paired rows so each card pair shares the same height
                    ups = pa.get("upside", [])
                    dns = pa.get("downside", [])
                    for up, dn in _it.zip_longest(ups, dns):
                        card_style = "display:flex;flex-direction:column;justify-content:space-between;" \
                                     "border-radius:4px;padding:10px 14px;height:100%"
                        up_html = (
                            f"<div style='background:#1a2a1a;border-left:3px solid #00c853;{card_style}'>"
                            f"<b style='color:#e8e8e8'>{_html.escape(up['player'])}</b> "
                            f"<span style='color:#888;font-size:12px'>({_html.escape(up['team'])})</span><br>"
                            f"<span style='color:#aaa;font-size:13px'>{_html.escape(up['reason'])}</span>"
                            f"</div>"
                        ) if up else "<div></div>"
                        dn_html = (
                            f"<div style='background:#2a1a1a;border-left:3px solid #ff5252;{card_style}'>"
                            f"<b style='color:#e8e8e8'>{_html.escape(dn['player'])}</b> "
                            f"<span style='color:#888;font-size:12px'>({_html.escape(dn['team'])})</span><br>"
                            f"<span style='color:#aaa;font-size:13px'>{_html.escape(dn['reason'])}</span>"
                            f"</div>"
                        ) if dn else "<div></div>"
                        row_html = (
                            "<div class='jsa-ff-pair' style='display:grid;"
                            "grid-template-columns:1fr 1fr;"
                            "gap:8px;align-items:stretch;margin-top:8px'>"
                            + up_html + dn_html +
                            "</div>"
                        )
                        st.markdown(row_html, unsafe_allow_html=True)
                elif not preview_layout:
                    st.info("No agent notes for this week.")
