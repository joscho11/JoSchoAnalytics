"""Every visual scene: route, publishing state, empty state, loaded intelligence.

Layers follow the recommended build order:
publishing -> matchup -> credibility -> fantasy -> league-history.
"""
from __future__ import annotations

from dataclasses import dataclass, field

ALL_VIEWPORTS = ("phone", "tablet", "desktop")
NARROW = ("phone", "desktop")

# url_path values from app.py. Home is the empty string.
NAV_ROUTES = {
    "": "Home",
    "this-week": "This Week",
    "draft-board": "Draft Board",
    "weekly-predictions": "Weekly Predictions",
    "anytime-tds": "Touchdown Props",
    "weekly-fantasy": "Weekly Fantasy",
    "dfs-optimizer": "DFS Optimizer",
    "track-record": "Track Record",
    "film-room": "Film Room",
    "league-history": "League History",
    "help": "Help & Guide",
    "rookie-board": "Rookie Board",
    "season-totals": "Season Totals",
    "college-basketball": "Daily spreads (Beta)",
}

LAYERS = (
    "publishing",
    "matchup",
    "credibility",
    "fantasy",
    "league-history",
)

LH_TABS = (
    "Draft & Roster Insights",
    "All-Time Leaderboard",
    "Hall of Fame",
    "Rivalries",
    "Report Cards",
    "Consistency & Luck",
)


@dataclass(frozen=True)
class Scene:
    id: str
    layer: str
    path: str
    query: str = ""
    action: str | None = None
    viewports: tuple[str, ...] = ALL_VIEWPORTS
    must_contain: tuple[str, ...] = ()
    must_not_contain: tuple[str, ...] = ()
    nav_route: str | None = field(default=None)

    def __post_init__(self) -> None:
        if self.nav_route is None:
            object.__setattr__(self, "nav_route", self.path)


def _s(
    scene_id: str,
    layer: str,
    path: str,
    *,
    query: str = "",
    action: str | None = None,
    viewports: tuple[str, ...] = ALL_VIEWPORTS,
    must_contain: tuple[str, ...] = (),
    must_not_contain: tuple[str, ...] = (),
) -> Scene:
    return Scene(
        id=scene_id,
        layer=layer,
        path=path,
        query=query,
        action=action,
        viewports=viewports,
        must_contain=must_contain,
        must_not_contain=must_not_contain,
    )


SCENES: tuple[Scene, ...] = (
    # ── 1. Publishing pipeline (badges and fail-closed empties) ──────────
    _s(
        "wp_published_2025w10",
        "publishing",
        "weekly-predictions",
        query="wp_season=2025&wp_week=10",
        must_contain=("Weekly predictions", "Published", "Demo test", "Week 10 · 2025 season"),
    ),
    _s(
        "wp_retrospective_2026w1",
        "publishing",
        "weekly-predictions",
        query="wp_season=2026&wp_week=1",
        must_contain=("Published", "Live 2026", "NE @ SEA"),
        must_not_contain=("Agent Confidence", "Retrospective model correction", "Retrospective model update"),
    ),
    _s(
        "wf_published_2025w17",
        "publishing",
        "weekly-fantasy",
        query="wf_season=2025&wf_week=17",
        must_contain=("Weekly fantasy", "Published", "2025"),
    ),
    _s(
        "wf_awaiting_2026w17",
        "publishing",
        "weekly-fantasy",
        query="wf_season=2026&wf_week=17",
        must_contain=("Awaiting projections", "Week 17", "2026"),
    ),
    _s(
        "this_week_home",
        "matchup",
        "this-week",
        must_contain=("This week",),
    ),
    _s(
        "wf_published_2025w10",
        "publishing",
        "weekly-fantasy",
        query="wf_season=2025&wf_week=10",
        must_contain=("Published", "Week 10", "demo"),
    ),
    # ── 2. Matchup pages (game cards, wrapping, SCORE column) ────────────
    _s(
        "wp_graded_2025w17",
        "matchup",
        "weekly-predictions",
        query="wp_season=2025&wp_week=17",
        must_contain=("Weekly predictions", "SCORE", "SPREAD", "PREDICTED", "Week 17 · 2025 season"),
    ),
    # ── 3. Credibility layer ─────────────────────────────────────────────
    _s(
        "home",
        "credibility",
        "",
        must_contain=("JoScho Analytics", "No paid picks", "preseason"),
    ),
    _s(
        "track_record_2025",
        "credibility",
        "track-record",
        query="tr_season=2025",
        must_contain=("Track record", "Demo test", "52.4%"),
    ),
    _s(
        "track_record_2026_live",
        "credibility",
        "track-record",
        query="tr_season=2026",
        must_contain=("Live 2026", "Retrospective model corrections are included in this season record: Week 1, Week 2"),
    ),
    _s(
        "help",
        "credibility",
        "help",
        must_contain=("Help & guide", "Site Guide", "Which page should I use?"),
    ),
    _s(
        "help_ats_open",
        "credibility",
        "help",
        query="help_topic=Betting",
        action="help_open_ats",
        viewports=NARROW,
        must_contain=("Against The Spread", "juice"),
    ),
    _s(
        "help_models",
        "credibility",
        "help",
        action="help_scroll_models",
        viewports=NARROW,
        must_contain=("How the models work",),
    ),
    _s(
        "season_totals",
        "credibility",
        "season-totals",
        must_contain=("Season Totals", "High-confidence", "All 32 team projections"),
    ),
    _s(
        "cbb_daily_empty",
        "publishing",
        "college-basketball",
        must_contain=("College basketball daily spreads", "No official College Basketball daily card"),
    ),
    _s(
        "anytime_tds",
        "credibility",
        "anytime-tds",
        must_contain=("Touchdown Props", "Live", "Priced"),
    ),
    _s(
        "anytime_tds_w17",
        "credibility",
        "anytime-tds",
        query="atd_year=2025&atd_week=17",
        viewports=NARROW,
        must_contain=("Touchdown Props",),
    ),
    _s(
        "first_td_view",
        "credibility",
        "anytime-tds",
        action="atd_first_td_view",
        viewports=NARROW,
        must_contain=("Touchdown Props", "First TD"),
    ),
    _s(
        "film_room",
        "credibility",
        "film-room",
        must_contain=("Film room",),
    ),
    _s(
        "film_room_walkthrough",
        "credibility",
        "film-room",
        query="video=league-history-guide",
        viewports=NARROW,
        must_contain=("Film room",),
    ),
    # ── 4. Fantasy workflow ──────────────────────────────────────────────
    _s(
        "draft_board",
        "fantasy",
        "draft-board",
        must_contain=("2026 draft board", "Sleeper ADP"),
    ),
    _s(
        "draft_board_qb",
        "fantasy",
        "draft-board",
        query="db26_pos=QB",
        must_contain=("2026 draft board",),
    ),
    _s(
        "draft_board_espn",
        "fantasy",
        "draft-board",
        query="db26_adp_src=ESPN+ADP",
        viewports=NARROW,
        must_contain=("ESPN ADP",),
    ),
    _s(
        "draft_board_yahoo",
        "fantasy",
        "draft-board",
        query="db26_adp_src=Yahoo+ADP",
        viewports=NARROW,
        must_contain=("Yahoo ADP",),
    ),
    _s(
        "rookie_board",
        "fantasy",
        "rookie-board",
        must_contain=("Rookie", "Backtested"),
    ),
    _s(
        "dfs_empty",
        "fantasy",
        "dfs-optimizer",
        must_contain=("DFS optimizer", "Upload a DraftKings"),
    ),
    _s(
        "dfs_uploaded",
        "fantasy",
        "dfs-optimizer",
        action="dfs_upload_and_optimize",
        must_contain=("Salary slate accepted", "Optimize lineup", "Optimized lineup"),
    ),
    # ── 5. League History intelligence ───────────────────────────────────
    _s(
        "lh_sleeper_empty",
        "league-history",
        "league-history",
        must_contain=("Fantasy league history", "Sleeper League ID", "Load league history"),
    ),
    _s(
        "lh_espn_empty",
        "league-history",
        "league-history",
        action="lh_espn",
        must_contain=("ESPN League ID",),
    ),
    _s(
        "lh_espn_private",
        "league-history",
        "league-history",
        action="lh_espn_private",
        viewports=NARROW,
        must_contain=("SWID", "espn_s2"),
    ),
    _s(
        "lh_yahoo_empty",
        "league-history",
        "league-history",
        action="lh_yahoo",
        must_contain=("Yahoo League ID",),
    ),
    _s(
        "lh_yahoo_private",
        "league-history",
        "league-history",
        action="lh_yahoo_private",
        viewports=NARROW,
        must_contain=("Y cookie", "T cookie"),
    ),
    _s(
        "lh_offline_error",
        "league-history",
        "league-history",
        action="lh_offline_error",
        must_contain=("unavailable offline",),
    ),
    _s(
        "lh_loaded_insights",
        "league-history",
        "league-history",
        action="lh_load_fixture",
        must_contain=("Test League", "My Team", "Draft & Roster Insights"),
    ),
    _s(
        "lh_loaded_best_values",
        "league-history",
        "league-history",
        action="lh_insights_best_values",
        viewports=NARROW,
        must_contain=("Test League", "Best Values"),
    ),
    _s(
        "lh_loaded_draft_room",
        "league-history",
        "league-history",
        action="lh_insights_draft_room",
        viewports=NARROW,
        must_contain=("Test League", "Draft Room"),
    ),
    _s(
        "lh_loaded_leaderboard",
        "league-history",
        "league-history",
        action="lh_tab_leaderboard",
        must_contain=("Test League", "All-Time Leaderboard", "Most Titles", "Best Win %"),
    ),
    _s(
        "lh_loaded_hof",
        "league-history",
        "league-history",
        action="lh_tab_hof",
        viewports=NARROW,
        must_contain=("Test League", "Hall of Fame", "Highest Score"),
    ),
    _s(
        "lh_loaded_rivalries",
        "league-history",
        "league-history",
        action="lh_tab_rivalries",
        viewports=NARROW,
        must_contain=("Test League", "Rivalries"),
    ),
    _s(
        "lh_loaded_report_cards",
        "league-history",
        "league-history",
        action="lh_tab_report_cards",
        viewports=NARROW,
        must_contain=("Test League", "Report Cards"),
    ),
    _s(
        "lh_loaded_consistency",
        "league-history",
        "league-history",
        action="lh_tab_consistency",
        viewports=NARROW,
        must_contain=("Test League", "Consistency & Luck"),
    ),
)


def cases() -> list[tuple[Scene, str]]:
    return [(scene, viewport) for scene in SCENES for viewport in scene.viewports]
