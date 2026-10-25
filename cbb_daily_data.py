"""Cached, hash-verifying loaders for the public CBB daily release."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

from publishing.cbb_daily import cbb_status, load_cbb_card, load_cbb_manifest, load_cbb_results


ROOT = Path(__file__).resolve().parent
# A repo file, not part of a release: the fixture directory never overrides it.
CONFERENCE_ORDER_PATH = ROOT / "data" / "cbb" / "conference_order_2027.json"
NO_CONFERENCE_ORDER = {"order": [], "aliases": {}, "captured_on": None, "source": None, "available": False}


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


def _parse_conference_order(payload: object) -> dict:
    """The order file as a dict, or raise ValueError when it is not the shape the page relies on."""
    if not isinstance(payload, dict):
        raise ValueError("conference order must be an object")
    order, aliases = payload.get("order"), payload.get("aliases", {})
    if not isinstance(order, list) or not order or not all(isinstance(name, str) and name.strip() for name in order) or len(set(order)) != len(order):
        raise ValueError("conference order must be a list of unique names")
    if not isinstance(aliases, dict) or not all(isinstance(key, str) and value in order for key, value in aliases.items()):
        raise ValueError("every conference alias must point at a name in the order")
    captured = payload.get("captured_on")
    if captured is not None:
        captured = date.fromisoformat(str(captured)).isoformat()
    return {"order": list(order), "aliases": dict(aliases), "captured_on": captured, "source": payload.get("source"), "available": True}


@st.cache_data(ttl=600, max_entries=1, show_spinner=False)
def load_conference_order() -> dict:
    """Conference display order from ``data/cbb/conference_order_2027.json``.

    Fail soft: an unreadable or malformed file gives ``available == False`` and an empty
    order, and the page falls back to alphabetical order with a note.
    """
    try:
        return _parse_conference_order(json.loads(CONFERENCE_ORDER_PATH.read_text(encoding="utf-8")))
    except (OSError, ValueError, TypeError):
        return dict(NO_CONFERENCE_ORDER)


def release_status() -> dict:
    return cbb_status(root=_fixture_root())


__all__ = ["load_manifest", "load_card", "load_results", "load_conference_order", "release_status"]
