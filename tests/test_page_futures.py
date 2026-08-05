"""Season Totals page proof: renders, reports the backtest honestly, holds the language fence.

Hermetic (APP_OFFLINE=1). The page is READ-ONLY over `futures/futures_predictions.csv` plus two
artifact JSONs, so nothing here fits, simulates, or reaches the network.

What is asserted, and why each one exists:

* the page renders clean, and boots inside the multipage entrypoint;
* every number it displays is traceable to an artifact. The projection table comes from the CSV, the
  benchmark comparison to `model_comparison.json`, the interval accuracy to `model_metadata.json`.
  A page that hardcodes a backtest figure can drift silently from the artifact it describes;
* league conservation survives to the display layer (32 projections summing to the scheduled
  game count);
* **the §7 language fence**, checked mechanically against `futures/season_team_totals/tier_lock.py`'s
  own banned vocabulary rather than a list retyped here, because a hand-copied list is the kind that
  quietly falls out of sync with the guard it is supposed to mirror;
* **no market columns** reach the display, since gate C is shut. Note this is a schema assertion,
  not a vocabulary one: several of those column names carry no banned token at all, so the word
  scan above would pass them (the same finding notebook 05 records);
* the runtime stays separated: the page module imports no training or simulation dependency.

Deliberately NOT asserted here: browser geometry. Phone/tablet layout is the shared `mobile.py`
content layer, exercised by `tests/test_responsive_layout.py`; this page introduces no bespoke
layout, which `test_page_uses_only_shared_layout_primitives` pins.
"""
import ast
import json
import os
import sys
from pathlib import Path

os.environ["APP_OFFLINE"] = "1"

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

_HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_HERE))
sys.path.insert(0, str(_HERE / "site_pages"))
sys.path.insert(0, str(_HERE / "futures" / "season_team_totals"))

_CSV = _HERE / "futures" / "futures_predictions.csv"
_META = _HERE / "futures" / "artifacts" / "model_metadata.json"
_COMP = _HERE / "futures" / "artifacts" / "model_comparison.json"
_PAGE = _HERE / "site_pages" / "page_futures.py"

pytestmark = pytest.mark.skipif(not _CSV.exists(),
                                reason="futures_predictions.csv not built (run notebook 05)")


def _entry():
    import page_futures
    page_futures.render()


def _run(fn=None):
    at = AppTest.from_function(fn or _entry, default_timeout=180).run()
    assert not at.exception, at.exception
    assert not at.error, [e.value for e in at.error]
    return at


def _text(at):
    """Every string the page put on screen: titles, markdown, captions, alerts, metrics, help."""
    parts = []
    for group in (at.title, at.markdown, at.caption, at.warning, at.info, at.error,
                  at.subheader, at.header):
        parts += [str(e.value) for e in group]
    for m in at.metric:
        parts += [str(getattr(m, a, "") or "") for a in ("label", "value", "delta", "help")]
    for el in at.dataframe:
        v = el.value
        d = v.data if hasattr(v, "data") else v
        try:
            parts += [str(c) for c in d.columns]
        except Exception:
            pass
    return " ".join(parts)


def _table(at):
    for el in at.dataframe:
        v = el.value
        d = v.data if hasattr(v, "data") else v
        try:
            if "Proj Wins" in list(d.columns):
                return d
        except Exception:
            pass
    return None


# --------------------------------------------------------------------------- renders


def test_page_renders_and_shows_the_projection_table():
    at = _run()
    df = _table(at)
    assert df is not None, "the projection table must render"
    assert len(df) == 32, f"expected 32 teams, got {len(df)}"
    for c in ("Team", "Proj Wins", "p10", "Median", "p90", "80% Range"):
        assert c in list(df.columns), f"expected column {c} missing"


def test_display_matches_the_artifact():
    """The table is the CSV, not a re-derivation of it."""
    at = _run()
    df = _table(at)
    csv = pd.read_csv(_CSV)
    assert set(df["Team"]) == set(csv["team"])
    merged = df.merge(csv, left_on="Team", right_on="team")
    assert len(merged) == 32
    assert (merged["Proj Wins"] - merged["proj_wins"]).abs().max() < 1e-9
    assert (merged["Median"] - merged["p50"]).abs().max() < 1e-9
    assert ((merged["80% Range"]) - (merged["p90_y"] - merged["p10_y"])).abs().max() < 1e-9


def test_league_conservation_survives_to_the_display():
    at = _run()
    df = _table(at)
    games = int(pd.read_csv(_CSV)["games_scheduled"].sum() / 2)
    assert abs(float(df["Proj Wins"].sum()) - games) < 0.01, \
        "the displayed projections no longer sum to the scheduled game count"
    assert df["Proj Wins"].is_monotonic_decreasing


# --------------------------------------------------------------------------- honesty


def test_the_backtest_result_is_stated_plainly():
    at = _run()
    text = _text(at).lower()
    assert "does not beat" in text, "the gate B result must appear on the page, not only in a file"
    assert "backtested" in text and "not live-validated" in text.replace("live validated",
                                                                        "live-validated")
    # the benchmark is named per model_metadata.json claim_licence.naming
    assert "archived market consensus" in text
    for forbidden_name in ("vegas", "the sportsbook line"):
        assert forbidden_name not in text, f"benchmark must never be called {forbidden_name!r}"


def test_claim_label_is_read_from_the_artifact_not_retyped():
    """The label on the page must be byte-identical to the one notebook 04 recorded."""
    at = _run()
    label = str(pd.read_csv(_CSV)["claim_label"].iloc[0])
    assert label in _text(at), "the artifact's claim label must appear verbatim on the page"
    meta = json.loads(_META.read_text(encoding="utf-8"))
    assert label == meta["claim_licence"]["required_label"], \
        "the CSV label has drifted from model_metadata.json"


def test_displayed_evidence_numbers_come_from_the_artifacts():
    """Every backtest figure on the page is traceable; none is hardcoded copy."""
    at = _run()
    text = _text(at)
    meta = json.loads(_META.read_text(encoding="utf-8"))
    comp = json.loads(_COMP.read_text(encoding="utf-8"))
    mae = float(meta["evidence"]["pooled_mae_headline"])
    cov = float(meta["evidence"]["coverage80"])
    bench = float(comp["pooled_mae"]["headline"]["B0_market"])
    assert f"{mae:.2f} wins" in text, f"backtest MAE {mae:.2f} must be shown"
    assert f"{cov * 100:.0f}%" in text, f"interval accuracy {cov:.0%} must be shown"
    assert f"{bench:.2f}" in text, f"benchmark MAE {bench:.2f} must be shown from the artifact"
    # and the direction is reported the way the numbers actually run
    assert mae > bench, "the artifacts no longer support the 'does not beat' claim - re-read them"
    assert f"{mae - bench:+.2f}" in text, "the gap must be shown with its sign"


def test_no_hardcoded_backtest_number_in_the_source():
    """A literal like 2.25 typed into the page would survive an artifact change silently."""
    comp = json.loads(_COMP.read_text(encoding="utf-8"))
    meta = json.loads(_META.read_text(encoding="utf-8"))
    src = _PAGE.read_text(encoding="utf-8")
    for n in (comp["pooled_mae"]["headline"]["B0_market"],
              meta["evidence"]["pooled_mae_headline"],
              meta["evidence"]["coverage80"]):
        for literal in (f"{n:.2f}", f"{n:.3f}"):
            assert literal not in src, \
                f"{literal!r} is typed into page_futures.py - read it from the artifact instead"


# --------------------------------------------------------------------------- the fence


def test_language_fence_holds_against_the_guards_own_vocabulary():
    """PREREGISTRATION §7: the fenced words may not appear on the page while gate C is shut.

    The vocabulary is imported from tier_lock rather than retyped, so this test cannot fall out
    of sync with the pipeline guard. `GO-TIER-B` is an audited literal and is exempted the same
    way tier_lock exempts it, by exact string and never by token.
    """
    from tier_lock import TIER_C_BANNED, tokens

    at = _run()
    text = _text(at)
    for literal in ("GO-TIER-B",):
        text = text.replace(literal, " ")
    hits = sorted(tokens(text) & TIER_C_BANNED)
    assert not hits, f"fenced vocabulary on the Season Totals page: {hits}"


def test_no_market_columns_reach_the_display():
    """Gate C is shut. This is a SCHEMA check - the word scan above cannot catch these names,
    because most of them carry no banned token (the finding notebook 05 records)."""
    from tier_lock import TIER_C_BANNED, tokens

    market = ("win_total_line", "book", "line_as_of", "p_over", "p_under", "p_push",
              "Line", "Book", "Over", "Under", "Push")
    at = _run()
    cols = {str(c) for el in at.dataframe
            for c in list((el.value.data if hasattr(el.value, "data") else el.value).columns)}
    assert not (cols & set(market)), f"market columns on display: {sorted(cols & set(market))}"
    # pin the reason this test exists separately from the vocabulary one
    assert not (tokens("p_over") & TIER_C_BANNED), \
        "tier_lock now covers p_over - re-derive which mechanism excludes market columns"


# --------------------------------------------------------------------------- runtime


def test_runtime_separation_no_training_dependency():
    """PREREGISTRATION §8: the deployed page reads artifacts with pandas/streamlit only."""
    tree = ast.parse(_PAGE.read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    banned = {"sklearn", "lightgbm", "xgboost", "scipy", "joblib", "numpy", "nflreadpy",
              "m4_engine", "papermill", "torch"}
    assert not (imported & banned), f"page_futures imports training dependencies: {imported & banned}"
    assert imported <= {"json", "pathlib", "pandas", "streamlit"}, \
        f"unexpected page imports: {sorted(imported - {'json', 'pathlib', 'pandas', 'streamlit'})}"


def test_no_dash_pause_glyphs_in_page_copy():
    """Working rule 11: zero em dashes anywhere, including on-screen copy and code comments.

    The en dash is covered too when it is used as a pause; a numeric range takes a plain hyphen.
    The glyphs are built from codepoints rather than typed, so this file never contains the
    characters it rejects and cannot fail on its own source. It scans the page module and the
    rendered artifact text, not itself.
    """
    em, en = chr(0x2014), chr(0x2013)
    src = _PAGE.read_text(encoding="utf-8")
    assert em not in src, "em dash in page_futures.py"
    assert en not in src, "en dash in page_futures.py"
    at = _run()
    rendered = _text(at)
    assert em not in rendered, "em dash in the copy this page puts on screen"
    assert en not in rendered, "en dash in the copy this page puts on screen"
    label = str(pd.read_csv(_CSV)["claim_label"].iloc[0])
    assert em not in label and en not in label, "the artifact's claim label carries a dash glyph"


def test_page_uses_only_shared_layout_primitives():
    """No bespoke layout means the shared mobile.py content layer already covers this page at
    phone and tablet widths; nothing here needs its own responsive rules."""
    src = _PAGE.read_text(encoding="utf-8")
    assert "st.markdown(" in src
    assert "unsafe_allow_html" not in src, \
        "raw HTML would escape the shared mobile layer - use Streamlit primitives"
    assert "width=\"stretch\"" in src, "the table must stretch rather than carry a fixed pixel width"


# --------------------------------------------------------------------------- wiring


def test_registered_in_the_multipage_entrypoint():
    src = (_HERE / "app.py").read_text(encoding="utf-8")
    assert 'url_path="season-totals"' in src, "the page needs a stable url_path"
    assert '"season-totals": fut_pg' in src, "the page must be in the cross-link registry"
    # the nav label carries the beta flag; url_path deliberately does NOT, so removing the flag
    # later cannot break a shared link
    assert 'title="Season Totals (Beta)"' in src, "the nav label must carry the beta flag"
    assert 'url_path="season-totals"' in src
    # lazily imported like every other page
    tree = ast.parse(src)
    eager = {a.name for n in ast.walk(tree) if isinstance(n, ast.Import)
             for a in n.names if a.name.startswith("page_")}
    assert eager == set(), f"pages must stay lazily imported; eager: {eager}"


def test_app_boots_with_the_page_wired_in():
    at = AppTest.from_file(str(_HERE / "app.py"), default_timeout=240).run()
    assert not at.exception, at.exception
    assert not at.error, [e.value for e in at.error]


if __name__ == "__main__":
    test_page_renders_and_shows_the_projection_table()
    test_display_matches_the_artifact()
    test_league_conservation_survives_to_the_display()
    test_the_backtest_result_is_stated_plainly()
    test_claim_label_is_read_from_the_artifact_not_retyped()
    test_displayed_evidence_numbers_come_from_the_artifacts()
    test_no_hardcoded_backtest_number_in_the_source()
    test_language_fence_holds_against_the_guards_own_vocabulary()
    test_no_market_columns_reach_the_display()
    test_runtime_separation_no_training_dependency()
    test_no_dash_pause_glyphs_in_page_copy()
    test_page_uses_only_shared_layout_primitives()
    test_registered_in_the_multipage_entrypoint()
    test_app_boots_with_the_page_wired_in()
    print("OK  Season Totals page: renders, artifact-traceable numbers, fence holds, app boots")
