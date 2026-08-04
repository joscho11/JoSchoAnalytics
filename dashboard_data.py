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
import json
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


@st.cache_data(ttl=300)
def load_predictions():
    """Spread predictions tracker. Raises FileNotFoundError if absent — the calling
    page decides how to degrade (st.error + st.stop), never this loader."""
    return load_tracker(str(_HERE))


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
        except Exception:
            pass
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
