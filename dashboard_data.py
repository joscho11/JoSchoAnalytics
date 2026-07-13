"""Shared, cached data loaders for the multipage site (site revamp Batch 1).

Import-safe: this module DEFINES cached loaders and runs no data loads, GA calls,
or st.stop() at import time (the import-side-effect fix from the design's 4i). Each
page calls a loader inside its own render() and handles a missing/empty file locally,
so one bad file degrades that page — not the whole site. Loaders are @st.cache_data
so repeated calls across pages/sessions are cheap.

(compute_hc_stats — the agent high-confidence tally used only by the betting pages —
is intentionally deferred to the betting-page extraction batch, extracted alongside
its sole consumers to avoid copy-drift on a long function with no Batch-1 caller.)
"""
import sys
from pathlib import Path

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
