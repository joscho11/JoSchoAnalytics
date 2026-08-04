"""Tier-C lock — the mechanical guard for the futures/ pipeline.

PREREGISTRATION §7 gate C and §10 Amendment 1 A1.5: while `tier_c_open` is False, nothing in this
subproject may compute, name, or export a side, a probability against a posted line, a confidence
tier, expected value, break-even, or profitability. The market source is an archived consensus with
`book = null`, so gate C is unreachable and the fence is fully binding.

This is a **module, not a notebook**, at Joseph's direction (2026-08-03): a guard that every
downstream notebook must call should be imported, not reconstructed by exec-ing another notebook's
code cells. It is infrastructure, not analysis — the same carve-out `memory/prefer-ipynb-not-py.md`
makes for CI and retrain helpers.

Usage:

    import sys; sys.path.insert(0, str(REPO / "futures" / "season_team_totals"))
    from tier_lock import assert_no_tier_c, TIER_C_BANNED

    assert_no_tier_c(panel, "panel", allowed_literals=ALLOWED)
    assert_no_tier_c(metadata_dict, "metadata", allowed_literals=ALLOWED)

Self-test:  python futures/season_team_totals/tier_lock.py
"""
from __future__ import annotations

import re
from collections.abc import Mapping, Sequence

# Vocabulary that may not appear in a name, a key, or a value while gate C is shut.
TIER_C_BANNED = frozenset({
    "bet", "bets", "betting", "edge", "edges", "lock", "locks", "value", "play", "plays",
    "pick", "picks", "side", "sides", "ev", "kelly", "roi", "profit", "profitable",
    "confidence", "tier", "tiers", "vig", "juice", "price", "prices", "odds", "payout",
    "stake", "wager", "recommendation", "breakeven",
})

_SPLIT = re.compile(r"[^a-z0-9]+")


def tokens(s) -> set:
    """Split on non-alphanumerics so `games_played` yields {games, played}, not {play}."""
    return {t for t in _SPLIT.split(str(s).lower()) if t}


def _hits(s) -> list:
    return sorted(tokens(s) & TIER_C_BANNED)


def is_text_dtype(series) -> bool:
    """True if a pandas Series could hold text, across pandas versions.

    NOT `dtype == object`. Under pandas 3.x a string column's dtype is `str` (the new default
    StringDtype), so an `== object` check silently skips every string column and the value scan
    never runs — the guard then passes red controls whose only violation is in a *value*.
    Verified: pandas 2.3.3 -> object, pandas 3.0.3 -> str. Testing "not numeric/bool/temporal"
    is version-agnostic and fails safe (an unknown dtype gets scanned rather than skipped).
    """
    from pandas.api import types as ptypes
    return not (ptypes.is_numeric_dtype(series) or ptypes.is_bool_dtype(series)
                or ptypes.is_datetime64_any_dtype(series) or ptypes.is_timedelta64_dtype(series))


class TierCViolation(AssertionError):
    """Raised when Tier-C vocabulary appears while gate C is shut."""


def assert_no_tier_c(obj, where: str = "object", *, allowed_literals=(), tier_c_open: bool = False,
                     _path: str = "") -> None:
    """Recursively reject Tier-C vocabulary in `obj`.

    Walks DataFrame column names AND object-column values, mapping keys AND values, sequence
    elements, and bare strings — at any nesting depth. `allowed_literals` is an **exact-string**
    allowlist (proper nouns from audited provenance, e.g. "Covers Sports Odds History"); it never
    whitelists a token, so a near-miss like "Covers Sports Odds History Plus" still fails.

    No-op when `tier_c_open` is True — that state requires a named book (gate G3-C), which no
    archive source can supply.
    """
    if tier_c_open:
        return
    allowed = set(allowed_literals or ())
    at = f"{where}{_path}"

    # --- pandas objects (imported lazily so the guard has no hard dependency) ---
    mod = type(obj).__module__ or ""
    if mod.startswith("pandas"):
        if hasattr(obj, "columns"):                                    # DataFrame
            for col in obj.columns:
                if str(col) not in allowed and _hits(col):
                    raise TierCViolation(f"{at}: column {col!r} carries Tier-C vocabulary {_hits(col)}")
            for col in obj.columns:
                ser = obj[col]
                if not is_text_dtype(ser):
                    continue
                for v in ser.dropna().unique():
                    if str(v) in allowed:
                        continue
                    if _hits(v):
                        raise TierCViolation(
                            f"{at}[{col!r}]: value {v!r} carries Tier-C vocabulary {_hits(v)}")
            return
        if hasattr(obj, "dropna"):                                     # Series / Index
            for v in obj.dropna().unique() if hasattr(obj, "unique") else list(obj):
                assert_no_tier_c(v, where, allowed_literals=allowed, _path=_path)
            return

    # --- containers ---
    if isinstance(obj, Mapping):
        for k, v in obj.items():
            if str(k) not in allowed and _hits(k):
                raise TierCViolation(f"{at}: key {k!r} carries Tier-C vocabulary {_hits(k)}")
            assert_no_tier_c(v, where, allowed_literals=allowed, _path=f"{_path}[{k!r}]")
        return
    if isinstance(obj, (str, bytes)):
        s = obj.decode() if isinstance(obj, bytes) else obj
        if s not in allowed and _hits(s):
            raise TierCViolation(f"{at}: value {s!r} carries Tier-C vocabulary {_hits(s)}")
        return
    if isinstance(obj, Sequence) or isinstance(obj, (set, frozenset)):
        for i, v in enumerate(obj):
            assert_no_tier_c(v, where, allowed_literals=allowed, _path=f"{_path}[{i}]")
        return
    # numbers, None, dates, everything else: nothing to say
    return


def _self_test() -> None:
    import pandas as pd

    allowed = {"Covers Sports Odds History", "GO-TIER-B", "A+B"}

    # RED — every one of these must raise. The nested-dict cases are the defect Joseph found:
    # the pre-fix guard checked mapping keys but never descended into their values.
    red = [
        {"headline": "best bet of the week"},                       # <- the reported false negative
        {"a": {"b": ["fine", "expected value here"]}},
        {"results": [{"note": "confidence HIGH"}]},
        ["ok", ("ok", {"k": "kelly stake"})],
        "best odds available",
        {"price_over": -110},
        pd.DataFrame({"ev_estimate": [1.0]}),
        pd.DataFrame({"confidence": ["HIGH"]}),
        pd.DataFrame({"note": ["best bet of the week"]}),
        pd.DataFrame({"market_source": ["Covers Sports Odds History Plus"]}),   # near-miss literal
    ]
    for i, obj in enumerate(red):
        try:
            assert_no_tier_c(obj, "red", allowed_literals=allowed)
        except TierCViolation:
            continue
        raise AssertionError(f"red control {i} was NOT rejected: {obj!r}")

    # GREEN — none of these may raise.
    green = [
        {"games_played": 17, "prior_win_pct": 0.5, "market_line": 8.5},
        {"market_source": "Covers Sports Odds History", "verdict": "GO-TIER-B", "tiers": None}
        if False else {"market_source": "Covers Sports Odds History", "verdict": "GO-TIER-B"},
        {"nested": {"deep": ["games_played", "strictly_before_week1", 3, None]}},
        pd.DataFrame({"games_played": [17], "market_source": ["Covers Sports Odds History"]}),
        "the projection was closer than the archived consensus",
    ]
    for i, obj in enumerate(green):
        assert_no_tier_c(obj, "green", allowed_literals=allowed)

    # the open-gate escape hatch must actually disable the guard
    assert_no_tier_c({"headline": "best bet"}, "open", tier_c_open=True)

    # --- version-agnostic dtype detection -------------------------------------------------
    # The value scan is only reached for columns is_text_dtype() accepts. Under pandas 3 a string
    # column is dtype `str`, not `object`, so an `== object` test skips it and value-only red
    # controls escape. Assert the detector accepts text and rejects numerics under THIS pandas.
    assert is_text_dtype(pd.Series(["a", "b"])), \
        f"is_text_dtype rejects a string column under pandas {pd.__version__} — value scan would be skipped"
    assert is_text_dtype(pd.Series(["a", None], dtype=object))
    assert not is_text_dtype(pd.Series([1.0, 2.0])) and not is_text_dtype(pd.Series([True, False]))
    assert not is_text_dtype(pd.to_datetime(pd.Series(["2024-01-01"])))
    # and the end-to-end consequence, stated as its own check
    try:
        assert_no_tier_c(pd.DataFrame({"note": ["best bet of the week"]}), "dtype-probe")
        raise AssertionError(
            f"value-only violation escaped under pandas {pd.__version__} — the dtype gate is wrong")
    except TierCViolation:
        pass

    print(f"tier_lock self-test OK | pandas {pd.__version__} | {len(red)} red controls rejected, "
          f"{len(green)} green accepted, {len(TIER_C_BANNED)} banned tokens, dtype gate verified")


if __name__ == "__main__":
    _self_test()
