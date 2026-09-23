"""2026 live Tuesday-model display rules. Not the 2025 3-voter demo.

Production lives in the private leftover Ridge (`spread_v3_prod`). For 2026
releases, the Tuesday US median drives the model, pick, model edge, and HIGH
flag. The best US Tuesday quote for that side is displayed separately and used
for grading. A later market move alone cannot add HIGH; an explicitly published
model-version correction may change the edge and HIGH labels. No MEDIUM.

The 2021-2025 benchmark below is the current leakage-fixed median-triggered
ticket set graded at the best US Tuesday number. Prior release builds remain
immutable; a corrected Week 1 release is published as a new build.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

LIVE_SEASON = 2026
HIGH_GAP = 3.0
LAST_REG_WEEK = 18
SLATE_NAME = "slate_2026.csv"

# The producer's versioned candidate benchmark is the source of public values
# and per-season splits. Keeping the renderer data-only avoids loading training
# code or a serialized model in the public app.
HIGH_AUDIT_PATH = Path(__file__).with_name("market_model_benchmark_v2.json")
_HIGH_AUDIT = json.loads(HIGH_AUDIT_PATH.read_text(encoding="utf-8"))
if _HIGH_AUDIT.get("schema_version") != 1 or _HIGH_AUDIT.get("report_id") != "qb_retaining_market_ridge_v2":
    raise ValueError(f"unsupported HIGH audit artifact: {HIGH_AUDIT_PATH}")
_HIGH_BENCHMARK = _HIGH_AUDIT["historical"]["high"]
LIVE_HIGH_WINS = int(_HIGH_BENCHMARK["wins"])
LIVE_HIGH_N = int(_HIGH_BENCHMARK["graded_n"])
LIVE_HIGH_ATS = float(_HIGH_BENCHMARK["ats"])
LIVE_HIGH_WILSON_Z = 1.64485
LIVE_HIGH_WILSON_LOWER = float(_HIGH_BENCHMARK["wilson_lower_one_sided_95"])
BREAKEVEN = 0.524
LIVE_HIGH_WILSON_CLEARS = LIVE_HIGH_WILSON_LOWER > BREAKEVEN
TRACKER_2025_MD5 = "88d526ca46e8cbb9f1eea77a3d96fa08"


def live_high_bar_sentence() -> str:
    """Interval vs 52.4%. Interpolate this. Do not hardcode above/below."""
    bar = f"{BREAKEVEN * 100:.1f}%"
    if LIVE_HIGH_WILSON_CLEARS:
        return f"That interval is above {bar}."
    return (
        f"That interval is below {bar}. "
        "This book does not show an edge over break-even."
    )


def leftover_to_home_margin(leftover, sportsbook_spread) -> float:
    """cover_margin hat minus sportsbook spread (negative = home favored)."""
    return float(leftover) - float(sportsbook_spread)


def sportsbook_to_nflverse(sportsbook_spread) -> float:
    """nflverse / site sign: positive = home favored."""
    return -float(sportsbook_spread)


def tracker_2025_payload(path) -> bytes:
    """Header plus 2025 data rows, original bytes. 2026 appends must not rewrite these."""
    data = Path(path).read_bytes()
    lines = data.splitlines(keepends=True)
    if not lines:
        return data
    kept = [lines[0]]
    for row in lines[1:]:
        raw = row.replace(b"\r\n", b"").replace(b"\n", b"").replace(b"\r", b"")
        if not raw:
            continue
        fields = raw.split(b",")
        if len(fields) > 8 and fields[8] == b"2025":
            kept.append(row)
    return b"".join(kept)


def is_live_season(season) -> bool:
    return int(season) == LIVE_SEASON


def is_finale_week(season, week, game_type: str = "REG") -> bool:
    if str(game_type) != "REG":
        return False
    last = 17 if int(season) <= 2020 else LAST_REG_WEEK
    return int(week) == last


def tuesday_high(pred, tuesday_spread) -> bool:
    if pred is None or tuesday_spread is None:
        return False
    if pd.isna(pred) or pd.isna(tuesday_spread):
        return False
    return abs(float(pred) - float(tuesday_spread)) >= HIGH_GAP


def display_high(pred, tuesday_spread, live_spread=None, *, season=LIVE_SEASON, week=1, game_type="REG") -> bool:
    """True only if the Tuesday ticket was HIGH and the live line still is."""
    if is_finale_week(season, week, game_type):
        return False
    if not tuesday_high(pred, tuesday_spread):
        return False
    line = tuesday_spread if live_spread is None or pd.isna(live_spread) else live_spread
    return abs(float(pred) - float(line)) >= HIGH_GAP


def high_dropped(pred, tuesday_spread, live_spread, *, season=LIVE_SEASON, week=1, game_type="REG") -> bool:
    """Tuesday ticket was HIGH; live line shrank it under HIGH_GAP."""
    if is_finale_week(season, week, game_type):
        return False
    if not tuesday_high(pred, tuesday_spread):
        return False
    if live_spread is None or pd.isna(live_spread):
        return False
    return abs(float(pred) - float(live_spread)) < HIGH_GAP


def has_pick(row) -> bool:
    pred = row_pred(row)
    return pred is not None and not pd.isna(pred)


def _num(val):
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    try:
        if pd.isna(val):
            return None
    except (TypeError, ValueError):
        return None
    return float(val)


def row_pred(row):
    pred = row.get("ens_predicted_margin")
    if pred is None or pd.isna(pred):
        pred = row.get("predicted_margin")
    return pred


def row_tuesday_spread(row):
    tue = _num(row.get("tuesday_spread_line"))
    if tue is not None:
        return tue
    return _num(row.get("spread_line"))


def row_qualifying_spread(row):
    """Tuesday US median used for the model pick, edge, and HIGH decision.

    Older candidates without the explicit median field fall back to their
    original spread. The shopped Tuesday quote remains available separately via
    :func:`row_tuesday_spread` for display and grading.
    """
    median = _num(row.get("tuesday_median_spread_line"))
    if median is not None:
        return median
    original = _num(row.get("spread_line"))
    if original is not None:
        return original
    return row_tuesday_spread(row)


def row_qualifying_edge(row):
    """Model disagreement with the Tuesday US median."""
    pred = _num(row_pred(row))
    line = _num(row_qualifying_spread(row))
    if pred is None or line is None:
        return None
    return pred - line


def row_live_spread(row):
    return _num(row.get("live_spread_line"))


def row_game_type(row) -> str:
    gt = row.get("game_type")
    if gt is None or pd.isna(gt) or str(gt) == "nan":
        return "REG"
    return str(gt)


def row_display_high(row) -> bool:
    return display_high(
        row_pred(row),
        row_qualifying_spread(row),
        row_live_spread(row),
        season=int(row.get("season", LIVE_SEASON)),
        week=int(row.get("week", 1)),
        game_type=row_game_type(row),
    )


def row_high_dropped(row) -> bool:
    return high_dropped(
        row_pred(row),
        row_qualifying_spread(row),
        row_live_spread(row),
        season=int(row.get("season", LIVE_SEASON)),
        week=int(row.get("week", 1)),
        game_type=row_game_type(row),
    )


def attach_slate(tracker: pd.DataFrame, base_dir) -> pd.DataFrame:
    """Keep tracker rows. Add 2026 matchups whose game_id is not already logged."""
    path = Path(base_dir) / "betting" / SLATE_NAME
    if not path.is_file():
        return tracker
    slate = pd.read_csv(path)
    if slate.empty:
        return tracker
    if "season" in slate.columns:
        slate["season"] = slate["season"].astype(int)
    if "week" in slate.columns:
        slate["week"] = slate["week"].astype(int)
    if tracker is None or tracker.empty:
        return slate
    extra = slate.loc[~slate["game_id"].isin(tracker["game_id"])]
    if extra.empty:
        return tracker
    return pd.concat([tracker, extra], ignore_index=True, sort=False)


def season_high_record(df, season: int = LIVE_SEASON):
    """Graded HIGH ATS record for a live season, matching the Track Record page.

    Returns ``(wins, n, pct)`` with ``pct`` None when ``n == 0``. Same filter the
    Track Record live branch uses: rows for ``season`` with a graded
    ``actual_margin``, HIGH by :func:`row_display_high`, correct by
    ``ens_model_correct`` (falling back to ``model_correct``). One source of truth
    so the Home strip and Track Record can never disagree.
    """
    if df is None or getattr(df, "empty", True):
        return 0, 0, None
    if "season" not in df.columns or "actual_margin" not in df.columns:
        return 0, 0, None
    sdf = df[(df["season"] == season) & (df["actual_margin"].notna())]
    if sdf.empty:
        return 0, 0, None
    correct_col = (
        "ens_model_correct"
        if ("ens_model_correct" in sdf.columns and sdf["ens_model_correct"].notna().any())
        else "model_correct"
    )
    if correct_col not in sdf.columns:
        return 0, 0, None
    mask = sdf.apply(row_display_high, axis=1)
    hdf = sdf[mask]
    wins = int(hdf[correct_col].sum())
    n = int(hdf[correct_col].notna().sum())
    pct = round(wins / n * 100, 1) if n > 0 else None
    return wins, n, pct
