"""Shared app-level helpers used by the extracted page modules (site revamp Batch 3).

Moved byte-identical from app.py. `_season_week_controls` takes `df` as a parameter
(app.py closed over the module-level df); each page binds its own df via a thin closure
so the extracted tab bodies stay byte-identical. app.py keeps its own inline copies until
the swap (3e) removes the tab layer — temporary duplication by design.
"""
import importlib
import json
import os
from pathlib import Path

import streamlit as st

from dashboard_utils import sanitize_agent_analysis
from publishing.manifest import (
    default_selection as _manifest_default_selection,
    load_manifest as _load_manifest,
    release_status as _manifest_release_status,
    track_record_default_season as _manifest_track_record_default,
)

_HERE = Path(__file__).resolve().parents[1]


@st.cache_data(ttl=60, max_entries=1, show_spinner=False)
def load_release_manifest() -> dict:
    """Small fail-closed public release pointer, cached independently of page data."""
    return _load_manifest(_HERE)


def release_default_selection(product: str, fallback: tuple[int, int]) -> tuple[int, int]:
    return _manifest_default_selection(
        product, fallback, manifest=load_release_manifest(), root=_HERE
    )


def track_record_default_season(fallback: int = 2025) -> int:
    return _manifest_track_record_default(
        fallback, manifest=load_release_manifest(), root=_HERE
    )


def render_release_status(product: str, season: int, week: int) -> dict:
    """Render the selected week's state from the validated release manifest."""
    manifest = load_release_manifest()
    state = _manifest_release_status(
        product, season, week, manifest=manifest, root=_HERE
    )
    st.badge(state["status"], icon=state["icon"], color=state["color"])
    st.caption(state["detail"])
    next_release = manifest.get("products", {}).get(product, {}).get("next_release") or {}
    try:
        next_season, next_week = int(next_release["season"]), int(next_release["week"])
    except (KeyError, TypeError, ValueError):
        next_season = next_week = None
    if (
        state["status"] == "Published"
        and next_season is not None
        and (next_season, next_week) != (season, week)
    ):
        upcoming = _manifest_release_status(
            product, next_season, next_week, manifest=manifest, root=_HERE
        )
        st.caption(
            f"Next: {next_season} Week {next_week} · {upcoming['status']}. {upcoming['detail']}"
        )
    return state


def query_value(name: str):
    """Return one scalar query value without exposing unrelated URL state."""
    try:
        value = st.query_params.get(name)
    except Exception:
        return None
    if isinstance(value, list):
        return value[-1] if value else None
    return value


def seed_widget_from_query(widget_key: str, query_key: str, options) -> bool:
    """Initialize one widget from a valid query value before it is rendered."""
    if widget_key in st.session_state:
        return False
    raw = query_value(query_key)
    if raw is None:
        return False
    raw = str(raw)
    for option in options:
        if str(option) == raw:
            st.session_state[widget_key] = option
            return True
    return False


def sync_query_value(query_key: str, value) -> None:
    """Write public filter state to the URL only when it actually changed."""
    encoded = str(value)
    if not encoded:
        try:
            if query_value(query_key) is not None:
                del st.query_params[query_key]
        except Exception:
            pass
        return
    if str(query_value(query_key) or "") != encoded:
        st.query_params[query_key] = encoded


def reset_widget_and_query(widget_key: str, query_key: str | None = None) -> None:
    """Clear a dependent widget when its parent selection changes."""
    st.session_state.pop(widget_key, None)
    try:
        target = query_key or widget_key
        if query_value(target) is not None:
            del st.query_params[target]
    except Exception:
        pass


def load_agent_analysis(week: int, season: int) -> dict:
    """Agent cache for one week, with unprovenanced market claims stripped.

    Every public read of an agent artifact goes through here, so the provenance gate
    cannot be bypassed by adding a new caller. Sanitisation is FAIL-CLOSED: an artifact
    without verifiable market provenance loses its Sharp Money / Line Movement lines
    entirely — they are removed, never replaced with a placeholder.
    """
    cache_file = str(_HERE / "betting" / f"agent_analysis_{season}_week{week}.json")
    if os.path.exists(cache_file):
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                payload = json.load(f)
        except (json.JSONDecodeError, OSError, UnicodeDecodeError):
            return None
        clean, _report = sanitize_agent_analysis(payload)
        return clean
    return None


def _season_week_controls(
    df,
    cols_container,
    key_prefix,
    with_week=True,
    with_edge=False,
    default_week=None,
    default_season=None,
):
    """Render a tab's own Season (+ optional Week, Min-edge) controls in its body.
    Query parameters and existing widget state take precedence over page defaults.
    Returns (season, week, edge_threshold)."""
    _seasons = sorted(df['season'].unique(), reverse=True)
    _season_key = f"{key_prefix}_season"
    _week_key = f"{key_prefix}_week"
    _season_seeded = seed_widget_from_query(_season_key, _season_key, _seasons)
    _season_kwargs = {"key": _season_key}
    if with_week:
        _season_kwargs.update(
            on_change=reset_widget_and_query,
            args=(_week_key, _week_key),
        )
    if (
        not _season_seeded
        and _season_key not in st.session_state
        and default_season in set(_seasons)
    ):
        _season_kwargs["index"] = _seasons.index(default_season)
    _season = cols_container[0].selectbox("Season", _seasons, **_season_kwargs)
    sync_query_value(_season_key, _season)
    _week = None
    _edge = 0.0
    _i = 1
    if with_week:
        _weeks = sorted(df[df['season'] == _season]['week'].unique(), reverse=True)
        _preferred_week = (
            default_week.get(_season)
            if isinstance(default_week, dict)
            else default_week
        )
        if _preferred_week is not None and _preferred_week in set(_weeks):
            _dwk = _weeks.index(_preferred_week)
        else:
            _dwk = next((i for i, w in enumerate(_weeks) if w == 10), 0)
        if _week_key in st.session_state and st.session_state[_week_key] not in _weeks:
            del st.session_state[_week_key]
        seeded = seed_widget_from_query(_week_key, _week_key, _weeks)
        _week_kwargs = {"key": _week_key}
        if not seeded and _week_key not in st.session_state:
            _week_kwargs["index"] = _dwk
        _week = cols_container[_i].selectbox("Week", _weeks, **_week_kwargs)
        sync_query_value(_week_key, _week)
        _i += 1
    if with_edge:
        _edge = cols_container[_i].slider(
            "Min Edge (pts)", min_value=0.0, max_value=5.0, value=0.0, step=0.5,
            key=f"{key_prefix}_edge",
            help="Only show games where model disagrees with spread by at least this many points")
    return _season, _week, _edge


_MODE_BADGE_COLORS = {
    'monday':   '#ffd600',
    'thursday': '#ff9800',
    'sunday':   '#00c853',
    'backfill': '#3D95CE',
    'matchup':  '#888888',
}

# ATS blurb — moved byte-identical from the retired sidebar onto the Betting pages.
ATS_BLURB = """
    <div style="padding: 2px 4px 6px 4px;">
        <p style="font-size:12px;color:#aaa;line-height:1.65;margin:0">
            ML model trained on NFL data since 2014. Predicts each game vs the Vegas spread.
            <b style="color:#3D95CE">52.4% ATS</b> is break-even.
            2026 uses the Tuesday HIGH book. 2025 weeks on this site are a demo.
        </p>
    </div>
    """


def reload_if_stale(module):
    """Reload a module when Streamlit Cloud copies a new file into a live process.

    ``_lazy_render`` already does this for the selected page. Sibling helpers
    imported from that page (``league_insights_view``, ``fantasy.league_intelligence``)
    stay pinned in ``sys.modules`` unless they get the same mtime check.
    """
    path = getattr(module, "__file__", None)
    if not path:
        return module
    try:
        mtime = Path(path).stat().st_mtime_ns
    except OSError:
        return module
    if getattr(module, "__joscho_source_mtime_ns__", None) != mtime:
        importlib.invalidate_caches()
        source = Path(path)
        cache_dir = source.parent / "__pycache__"
        if cache_dir.is_dir():
            for pyc in cache_dir.glob(f"{source.stem}*.pyc"):
                try:
                    pyc.unlink()
                except OSError:
                    pass
        module = importlib.reload(module)
    module.__joscho_source_mtime_ns__ = mtime
    return module


_PLOTLY_TOUCH = {"displayModeBar": False, "scrollZoom": False}


def unlabeled_scatter_copy(fig):
    """Keep hover text, drop on-chart labels. Phone copy of a labeled scatter."""
    import plotly.graph_objects as go

    phone = go.Figure(fig.to_dict())
    for trace in phone.data:
        mode = str(getattr(trace, "mode", None) or "")
        if "text" not in mode.split("+"):
            continue
        kept = [part for part in mode.split("+") if part != "text"]
        trace.mode = "+".join(kept) if kept else "markers"
    return phone


def plotly_phone_desktop(desktop_fig, phone_fig, *, slug: str) -> None:
    """Show desktop_fig above 640px and phone_fig at phone width.

    A phone figure with an explicit layout.width uses Streamlit's content
    sizing so Plotly keeps its fixed pixel width. CSS on the keyed container
    clips that width to the viewport and provides horizontal panning.
    """
    phone_fixed = phone_fig.layout.width not in (None, 0)
    phone_cfg = {**_PLOTLY_TOUCH, "responsive": False} if phone_fixed else _PLOTLY_TOUCH
    phone_width = "content" if phone_fixed else "stretch"
    with st.container(key=f"jsa-scatter-desktop-{slug}"):
        st.plotly_chart(desktop_fig, width="stretch", config=_PLOTLY_TOUCH)
    with st.container(key=f"jsa-scatter-phone-{slug}"):
        st.plotly_chart(phone_fig, width=phone_width, config=phone_cfg)


def plotly_labeled_scatter(fig, *, slug: str) -> None:
    """Desktop keeps names. Phone is dots only. CSS shows one copy."""
    plotly_phone_desktop(fig, unlabeled_scatter_copy(fig), slug=slug)
