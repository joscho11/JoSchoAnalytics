"""Live entrypoint for the multipage JoScho Analytics site."""
import importlib
import sys
from pathlib import Path

import streamlit as st

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
sys.path.insert(0, str(_HERE / "site_pages"))
sys.path.insert(0, str(_HERE / "betting"))

import dashboard_chrome as chrome
import theme_redesign  # redesign preview skin (revertible) — delete this import + the call below to revert
import mobile  # phone/tablet layer (revertible) — delete this import + the call below to revert
import nav_registry
import runtime_telemetry  # OFF unless APP_TELEMETRY=1; remove this import + begin/end to strip

runtime_telemetry.begin()


def _refresh_cloud_synced_modules() -> None:
    """Reload page helpers whose source changed without a process restart.

    Streamlit Cloud can copy new files into a live interpreter. Reloading only
    the selected page left ``league_insights_view`` pinned at the previous
    signature, so League History called four arguments into a three-argument
    ``render`` and crashed with a redacted TypeError at the call site.
    """
    page_common = importlib.import_module("page_common")

    # Root helpers first. Pages import names from them; a live Cloud copy
    # that reloads page_draft_board before seasonal_config raises ImportError
    # on app_today while Home is still the selected page.
    for name in (
        "seasonal_config",
        "draft_board_2026",
        "fantasy_scoring",
        "fantasy.league_intelligence",
        "league_insights_view",
    ):
        loaded = sys.modules.get(name)
        if loaded is not None:
            sys.modules[name] = page_common.reload_if_stale(loaded)
    site_pages = (_HERE / "site_pages").resolve()
    for name, loaded in list(sys.modules.items()):
        path = getattr(loaded, "__file__", None)
        if not path:
            continue
        try:
            resolved = Path(path).resolve()
        except OSError:
            continue
        if resolved.parent != site_pages or resolved.name == "page_common.py":
            continue
        sys.modules[name] = page_common.reload_if_stale(loaded)


def _lazy_render(module_name: str):
    """Return a page callable that imports its implementation only when selected."""
    def render():
        _refresh_cloud_synced_modules()
        page_common = importlib.import_module("page_common")
        module = page_common.reload_if_stale(importlib.import_module(module_name))
        sys.modules[module_name] = module
        module.render()

    render.__name__ = f"render_{module_name}"
    return render

st.set_page_config(page_title="JoScho Analytics | NFL predictions",
                   page_icon="🏈", layout="wide")
chrome.inject_css()
theme_redesign.inject()  # redesign preview skin (revertible) — remove this line to restore the stock look

# ── Pages — stable Home route plus product pages loaded only when selected ──
home_pg = st.Page(_lazy_render("page_home"), title="Home", icon=":material/home:",
                  url_path="", default=True)
tw_pg = st.Page(_lazy_render("page_this_week"), title="This Week", icon=":material/calendar_today:",
                url_path="this-week")
board_pg = st.Page(_lazy_render("page_draft_board"), title="Draft Board", icon=":material/list_alt:",
                   url_path="draft-board")
wp_pg = st.Page(_lazy_render("page_weekly_predictions"), title="Weekly Predictions", icon=":material/query_stats:",
                url_path="weekly-predictions")
atd_pg = st.Page(_lazy_render("page_anytime_td"), title="Anytime TDs", icon=":material/sports_score:",
                 url_path="anytime-tds")
wf_pg = st.Page(_lazy_render("page_weekly_fantasy"), title="Weekly Fantasy", icon=":material/trophy:",
                url_path="weekly-fantasy")
dfs_pg = st.Page(_lazy_render("page_dfs"), title="DFS Optimizer (Beta)", icon=":material/target:",
                 url_path="dfs-optimizer")
tr_pg = st.Page(_lazy_render("page_track_record"), title="Track Record", icon=":material/monitoring:",
                url_path="track-record")
film_pg = st.Page(_lazy_render("page_film_room"), title="Film Room", icon=":material/movie:",
                  url_path="film-room")
lh_pg = st.Page(_lazy_render("page_league_history"), title="League History", icon=":material/history:",
                url_path="league-history")
help_pg = st.Page(_lazy_render("page_help"), title="Help & Guide", icon=":material/help:",
                  url_path="help")
rb_pg = st.Page(_lazy_render("page_rookie_board"), title="Rookie Board", icon=":material/biotech:",
                url_path="rookie-board")
fut_pg = st.Page(_lazy_render("page_futures"), title="Season Totals", icon=":material/bar_chart:",
                 url_path="season-totals")

# cross-link registry (design 4g) — populated before nav.run() so pages can link
nav_registry.PAGES = {
    "home": home_pg, "this-week": tw_pg, "draft-board": board_pg, "weekly-predictions": wp_pg, "anytime-tds": atd_pg,
    "weekly-fantasy": wf_pg, "dfs-optimizer": dfs_pg,
    "track-record": tr_pg, "film-room": film_pg, "league-history": lh_pg, "help": help_pg,
    "rookie-board": rb_pg, "season-totals": fut_pg,
}

# Persistent brand label above the top nav. It is intentionally non-interactive;
# repository and support actions live in the normal-flow footer.
chrome.render_header()

# The phone/tablet layer goes HERE, immediately after render_header, and this order is
# load-bearing: render_header emits its own <style>, so injecting the mobile layer earlier
# (as it was) left it losing the cascade and needing !important on every header rule to
# claw it back. Last writer wins, so mobile.py can now override with plain specificity.
# Revertible: delete this line and the `import mobile` above. No-op above 640px.
mobile.inject()

nav = st.navigation(
    {"": [home_pg, tw_pg],
     "Fantasy": [wf_pg, dfs_pg, board_pg, rb_pg],
     "Betting": [wp_pg, atd_pg, tr_pg, fut_pg],
     "More": [film_pg, lh_pg, help_pg]},
    position="top",
)
nav.run()
chrome.render_footer()
chrome.site_pageview(getattr(nav, "title", "JoScho Analytics"),
                     getattr(nav, "url_path", ""))
# Selected page title only (a public label, no visitor data). Title rather than url_path:
# the default page's url_path is "", which would log inconsistently against the others.
runtime_telemetry.end(getattr(nav, "title", None))
