"""Season Totals page: HIGH-first layout, artifact-driven numbers, language fence.

Hermetic (APP_OFFLINE=1). READ-ONLY over futures/published/season_totals_2026.csv
and futures/published/evidence.json.
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
sys.path.insert(0, str(_HERE / "futures"))

import page_futures as pf

_CSV = _HERE / "futures" / "published" / "season_totals_2026.csv"
_EVIDENCE = _HERE / "futures" / "published" / "evidence.json"
_PAGE = _HERE / "site_pages" / "page_futures.py"

pytestmark = pytest.mark.skipif(
    not _CSV.exists(),
    reason="published season totals missing (run season_totals_v2_prod: python src/publish_site.py)",
)


def _entry():
    import page_futures
    page_futures.render()


def _run(fn=None):
    at = AppTest.from_function(fn or _entry, default_timeout=180).run()
    assert not at.exception, at.exception
    assert not at.error, [e.value for e in at.error]
    return at


def _text(at):
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


def _tables(at):
    matches = []
    for el in at.dataframe:
        v = el.value
        d = v.data if hasattr(v, "data") else v
        try:
            if "Proj Wins" in list(d.columns) and pf.HIGH_COL in list(d.columns):
                matches.append(d)
        except Exception:
            pass
    return matches


def _table(at):
    found = _tables(at)
    return found[0] if found else None


def test_proj_wins_display_is_one_decimal():
    src = _PAGE.read_text(encoding="utf-8")
    assert '"Proj Wins": st.column_config.NumberColumn(format="%.1f"' in src


def test_page_renders_and_shows_the_projection_table():
    at = _run()
    df = _table(at)
    assert df is not None, "the projection table must render"
    assert len(df) == 32, f"expected 32 teams, got {len(df)}"
    for c in ("Team", "Proj Wins", "Posted", "vs posted", pf.HIGH_COL):
        assert c in list(df.columns), f"expected column {c} missing"


def test_display_matches_the_artifact():
    at = _run()
    df = _table(at)
    csv = pd.read_csv(_CSV)
    from team_display import public_team_abbr

    shown = csv["team"].map(public_team_abbr)
    assert set(df["Team"]) == set(shown)
    assert "LA" not in set(df["Team"])
    assert "LAR" in set(df["Team"])
    assert "LAC" in set(df["Team"])
    merged = df.merge(csv.assign(_shown=shown), left_on="Team", right_on="_shown")
    assert len(merged) == 32
    assert (merged["Proj Wins"] - merged["proj_wins"]).abs().max() < 1e-9
    assert (merged["Posted"] - merged["posted"]).abs().max() < 1e-9
    assert (merged["vs posted"] - merged["vs_posted"]).abs().max() < 1e-9
    if "certified" in csv.columns:
        want = merged["certified"].map(
            lambda x: pf.HIGH_YES if str(x).strip().lower() == "yes" else pf.HIGH_NO
        )
        assert list(merged[pf.HIGH_COL]) == list(want)


def test_league_conservation_survives_to_the_display():
    at = _run()
    df = _table(at)
    assert abs(float(df["Proj Wins"].sum()) - 272.0) < 0.01


def test_the_backtest_result_is_stated_plainly():
    at = _run()
    text = _text(at).lower()
    assert "does not beat" in text or "worse than the posted" in text
    assert "posted" in text
    assert "backtested" in text and "not live-validated" in text.replace(
        "live validated", "live-validated"
    )


def test_claim_label_is_read_from_the_artifact_not_retyped():
    at = _run()
    label = str(pd.read_csv(_CSV)["claim"].iloc[0])
    assert label in _text(at)


def test_displayed_evidence_numbers_come_from_the_artifacts():
    at = _run()
    text = _text(at)
    ev = json.loads(_EVIDENCE.read_text(encoding="utf-8"))
    high = ev["ou_high"]
    pct = 100.0 * high["ats"]
    wilson = 100.0 * high["wilson_lower"]
    assert "high confidence" in text.lower()
    assert f"{high['wins']}/{high['n']}" in text
    assert f"{pct:.2f}%" in text
    assert f"{wilson:.2f}%" in text
    assert "52.4" in text
    assert "as of" in text.lower()
    assert "ARI" in text
    assert "hitting" not in text.lower()


def test_accuracy_ladder_lives_in_the_backtest_expander():
    at = _run()
    assert any(
        "Full projection accuracy" in str(e.label) for e in at.expander
    ), "backtest expander missing"
    src = _PAGE.read_text(encoding="utf-8")
    assert "Average miss (wins)" in src
    assert 'ev.get("ladder")' in src


def test_evidence_section_degrades_without_its_artifact(tmp_path, monkeypatch):
    monkeypatch.setattr(pf, "_EVIDENCE", tmp_path / "absent.json")
    at = AppTest.from_function(_entry, default_timeout=180).run()
    assert not at.exception, at.exception
    assert not at.error, [e.value for e in at.error]
    assert _table(at) is not None


def test_no_hardcoded_backtest_number_in_the_source():
    ev = json.loads(_EVIDENCE.read_text(encoding="utf-8"))
    src = _PAGE.read_text(encoding="utf-8")
    for n in (ev["mae_model"], ev["mae_market"], ev["mae_persist"], ev["mae_retired_m4c"]):
        for literal in (f"{n:.2f}", f"{n:.3f}", f"{n:.4f}"):
            assert literal not in src
    high = ev["ou_high"]
    assert f"{high['wins']}/{high['n']}" not in src
    assert f"{100.0 * high['ats']:.2f}" not in src


def test_language_fence_holds_against_the_guards_own_vocabulary():
    from language_fence import BANNED, tokens

    at = _run()
    hits = sorted(tokens(_text(at)) & BANNED)
    assert not hits, f"fenced vocabulary on the Season Totals page: {hits}"


def test_season_totals_title_has_no_beta_flag():
    at = _run()
    titles = " ".join(str(t.value) for t in at.title)
    assert "Season Totals" in titles
    assert "(Beta)" not in titles
    assert "Season Totals (Beta)" not in _text(at)


def test_no_market_columns_reach_the_display():
    market = ("win_total_line", "book", "line_as_of", "p_over", "p_under",
              "Line", "Book", "Over", "Under", "Push")
    at = _run()
    cols = {str(c) for el in at.dataframe
            for c in list((el.value.data if hasattr(el.value, "data") else el.value).columns)}
    assert not (cols & set(market))
    assert "Posted" in cols


def test_runtime_separation_no_training_dependency():
    tree = ast.parse(_PAGE.read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    banned = {"sklearn", "lightgbm", "xgboost", "scipy", "joblib", "numpy", "nflreadpy",
              "m4_engine", "papermill", "torch", "season_totals_v2_prod"}
    assert not (imported & banned)
    assert imported <= {"json", "pathlib", "pandas", "streamlit"}


def test_no_dash_pause_glyphs_in_page_copy():
    em, en = chr(0x2014), chr(0x2013)
    src = _PAGE.read_text(encoding="utf-8")
    assert em not in src and en not in src
    rendered = _text(_run())
    assert em not in rendered and en not in rendered


def test_page_uses_only_shared_layout_primitives():
    src = _PAGE.read_text(encoding="utf-8")
    assert "unsafe_allow_html" not in src
    assert "width=\"stretch\"" in src


def test_registered_in_the_multipage_entrypoint():
    src = (_HERE / "app.py").read_text(encoding="utf-8")
    assert 'url_path="season-totals"' in src
    assert '"season-totals": fut_pg' in src


def test_app_boots_with_the_page_wired_in():
    at = AppTest.from_file(str(_HERE / "app.py"), default_timeout=240).run()
    assert not at.exception, at.exception
    assert not at.error, [e.value for e in at.error]


def test_phone_table_uses_short_headers_and_pinned_widths():
    at = _run()
    tables = _tables(at)
    assert len(tables) >= 2, "desktop and phone copies must both render"
    desktop, phone = tables[0], tables[1]
    assert list(desktop.columns) == list(phone.columns)
    assert list(phone.columns) == ["#", "Team", "Proj Wins", "Posted", "vs posted", pf.HIGH_COL]
    assert phone.shape[0] == desktop.shape[0] == 32

    cfg = pf._phone_column_config()
    assert cfg["Proj Wins"]["label"] == "Proj"
    assert cfg["vs posted"]["label"] == "vs"
    assert cfg[pf.HIGH_COL]["label"] == "HIGH"
    assert cfg["Proj Wins"]["width"] == pf._PHONE_WIDTHS["Proj Wins"]
    assert cfg["Proj Wins"]["pinned"] is True
    assert cfg["Posted"]["pinned"] is True
    assert cfg["vs posted"]["pinned"] is True
    assert cfg[pf.HIGH_COL]["pinned"] is True
    assert cfg["Team"]["pinned"] is True
    assert cfg["Team"]["width"] == pf._PHONE_WIDTHS["Team"]

    desktop_cfg = pf._totals_column_config()
    assert desktop_cfg["Proj Wins"].get("label") in (None, "", "Proj Wins")
    assert desktop_cfg[pf.HIGH_COL].get("label") in (None, "", pf.HIGH_COL)


def test_phone_high_calls_are_one_line_and_desktop_stays_a_row():
    src = _PAGE.read_text(encoding="utf-8")
    assert "jsa-st-high-desktop" in src
    assert "jsa-st-high-phone" in src
    assert "jsa-st-hero" in src
    css = (_HERE / "mobile.py").read_text(encoding="utf-8")
    assert "st-key-jsa-st-high-desktop" in css
    assert "st-key-jsa-st-high-phone" in css
    assert "st-key-jsa-st-hero" in css
    assert "st-key-jsa-st-ladder" in css
    at = _run()
    text = _text(at)
    assert "proj vs" in text
    assert " vs " in text
    assert "BAL" in text and "ARI" in text
