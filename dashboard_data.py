"""Shared, cached data loaders for the multipage site (site revamp Batch 1).

Import-safe: this module DEFINES cached loaders and runs no data loads, GA calls,
or st.stop() at import time (the import-side-effect fix from the design's 4i). Each
page calls a loader inside its own render() and handles a missing/empty file locally,
so one bad file degrades that page — not the whole site. Loaders are @st.cache_data
so repeated calls across pages/sessions are cheap.

(Batch 3a: compute_hc_stats + the live-accuracy derivations that Help / Weekly
Predictions / Track Record all consume were moved here byte-identical from app.py.)
"""
import glob
import hashlib
import json
import logging
import os
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
sys.path.insert(0, str(_HERE / "betting"))
from dashboard_utils import load_tracker, load_totals_tracker  # pure, Streamlit-free
from calibration import build_calibration
from live_2026 import attach_slate
from publishing.manifest import load_manifest, published_builds, resolve_build_artifact
from publishing.validators import read_table


def load_predictions():
    """Historical tracker plus every hash-verified release and unstamped slate."""
    manifest_path = _HERE / "data" / "releases" / "manifest.json"
    try:
        manifest_sha = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    except FileNotFoundError:
        manifest_sha = "missing"
    return _load_predictions_for_manifest(manifest_sha)


@st.cache_data(ttl=300)
def _load_predictions_for_manifest(manifest_sha: str):
    """Refresh the cached card as soon as the release manifest changes."""
    df = load_tracker(str(_HERE))
    df = overlay_published_predictions(df, _HERE)
    return attach_slate(df, _HERE)


def overlay_published_predictions(df: pd.DataFrame, root: str | Path) -> pd.DataFrame:
    """Overlay the newest valid build for every released week onto tracker history."""
    manifest = load_manifest(root)
    builds_by_week = {}
    for build in published_builds("predictions", manifest=manifest, root=root):
        key = (int(build["season"]), int(build["week"]))
        builds_by_week[key] = build
    out = df.copy()
    for build in builds_by_week.values():
        artifact = resolve_build_artifact(build, root=root, prefer_graded=True)
        if artifact is None:
            continue
        released = read_table(artifact)
        if not released.empty and "game_id" in released:
            correction = build.get("correction") or {}
            released["release_retrospective"] = correction.get("retrospective") is True
            released["release_build_id"] = str(build.get("build_id", ""))
            released["release_supersedes_build_id"] = str(
                correction.get("supersedes_build_id") or ""
            )
            released["release_correction_reason"] = str(correction.get("reason") or "")
            released_ids = set(released["game_id"].astype(str))
            out = out.loc[~out["game_id"].astype(str).isin(released_ids)]
            out = pd.concat([out, released], ignore_index=True, sort=False)
    return out


def retrospective_release_weeks(season: int, root: str | Path | None = None) -> list[int]:
    """Return published weeks whose current release is a retrospective correction.

    Read this from the release manifest rather than the graded row frame: Track
    Record must keep the disclosure visible even if a fallback tracker omits the
    release metadata columns.
    """
    release_root = Path(root) if root is not None else _HERE
    manifest = load_manifest(release_root)
    return sorted(
        {
            int(build["week"])
            for build in published_builds("predictions", manifest=manifest, root=release_root)
            if int(build["season"]) == int(season)
            and (build.get("correction") or {}).get("retrospective") is True
        }
    )


@st.cache_data(ttl=300)
def load_totals():
    """Totals tracker; empty DataFrame if the file is absent."""
    return load_totals_tracker(str(_HERE))


def load_calibration(df):
    """Honest cover-probability calibration; degrades to an empty result on any
    schema hiccup (matches app.py's guard) rather than breaking the page."""
    try:
        return build_calibration(df)
    except Exception:
        return {"n_graded": 0, "by_tier": {}, "overall": None}


@st.cache_data(ttl=300)
def _compute_hc_stats(acc_col: str, _df: pd.DataFrame) -> tuple:
    """High-confidence record, counted ONLY from artifacts the public gate approves.

    This used to `json.load` each `agent_analysis_*.json` directly, which bypassed the
    provenance gate entirely: an artifact the site refuses to render could still supply the
    HIGH/MEDIUM tiers behind a headline accuracy statistic. The tiers are not independent of
    the market claims — the agent reasoned to them FROM those claims — so a rejected
    artifact must contribute nothing. Routing through `load_agent_analysis` means one gate
    governs both rendering and statistics.
    """
    from page_common import load_agent_analysis  # public, gated reader
    hc_correct, hc_total = 0, 0
    for af in glob.glob(str(_HERE / "betting" / "agent_analysis_*.json")):
        try:
            stem = os.path.basename(af).replace('.json', '').split('_')
            s, w = int(stem[2]), int(stem[3].replace('week', ''))
            wdf = _df[(_df['season'] == s) & (_df['week'] == w) & _df[acc_col].notna()]
            ga = load_agent_analysis(w, s)
            if not ga:                     # rejected by the gate, or unreadable
                continue
            _gc = ga.get('game_confidence', {})
            _ga = ga.get('game_analysis',   {})
            for _, r in wdf.iterrows():
                key  = f"{r['home_team']}_{r['away_team']}"
                conf = _gc.get(key) if _gc else None
                if conf is None:
                    text = _ga.get(key, '')
                    conf = 'HIGH' if '🟢' in text else None
                if conf == 'HIGH':
                    hc_total += 1
                    hc_correct += int(float(r[acc_col]))
        except (ValueError, KeyError, TypeError, OSError, IndexError, json.JSONDecodeError):
            continue
        except Exception:
            logging.getLogger(__name__).exception(
                "hc_stats skipped a malformed agent artifact: %s", af)
            continue
    return hc_correct, hc_total


def accuracy_stats(df):
    """The live accuracy stats block (Help/betting-page copy inputs), moved verbatim
    from app.py. Runs only when called (import-safe). Returns the same derived values
    app.py's tab bodies read — the interpolated copy is byte-identical because the
    numbers are computed by the same expressions."""
    _acc_col   = 'ens_model_correct' if 'ens_model_correct' in df.columns and df['ens_model_correct'].notna().any() else 'model_correct'
    _completed = df[df[_acc_col].notna()]
    _overall_correct = int(_completed[_acc_col].sum())
    _overall_total   = len(_completed)
    _overall_pct     = round(_overall_correct / _overall_total * 100, 1) if _overall_total > 0 else 0

    _hc_correct, _hc_total = _compute_hc_stats(_acc_col, df)
    _hc_pct = round(_hc_correct / _hc_total * 100, 1) if _hc_total > 0 else None
    return {"acc_col": _acc_col, "completed": _completed,
            "overall_correct": _overall_correct, "overall_total": _overall_total,
            "overall_pct": _overall_pct, "hc_correct": _hc_correct,
            "hc_total": _hc_total, "hc_pct": _hc_pct}
