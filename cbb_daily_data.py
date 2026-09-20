"""Cached, hash-verifying loaders for the public CBB daily release."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from publishing.cbb_daily import cbb_status, load_cbb_card, load_cbb_manifest, load_cbb_results


ROOT = Path(__file__).resolve().parent


def _fixture_root() -> Path:
    configured = __import__("os").environ.get("JSA_CBB_FIXTURE_DIR")
    if configured and __import__("os").environ.get("APP_OFFLINE") == "1":
        return Path(configured).resolve()
    return ROOT


@st.cache_data(ttl=60, max_entries=1, show_spinner=False)
def load_manifest() -> dict:
    return load_cbb_manifest(_fixture_root(), strict=False)


@st.cache_data(ttl=60, max_entries=20, show_spinner=False)
def load_card(day: str) -> tuple[pd.DataFrame, dict, dict]:
    return load_cbb_card(day, root=_fixture_root())


@st.cache_data(ttl=60, max_entries=20, show_spinner=False)
def load_results(day: str) -> pd.DataFrame | None:
    return load_cbb_results(day, root=_fixture_root())


def release_status() -> dict:
    return cbb_status(root=_fixture_root())


__all__ = ["load_manifest", "load_card", "load_results", "release_status"]
