"""Proof for the College QB Talent Score (SPEC R35, shipped 2026-07-27).

Covers the artifact's contract, the two board integrations, and the identity discipline that
the build depends on — brand-new rookie QBs carry placeholder ids (MEN516487) rather than a
gsis, and the rookie board carries its OWN placeholders (GRE361852) that do not always equal
the season dataset's, so both joins are guarded name joins and must refuse ambiguity.

Hermetic (APP_OFFLINE=1); reads shipped artifacts only, writes nothing.
"""
import json
import os
import re
import sys
from pathlib import Path

import pandas as pd

os.environ["APP_OFFLINE"] = "1"

from streamlit.testing.v1 import AppTest

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
sys.path.insert(0, str(_HERE / "fantasy" / "seasonal_projections"))
sys.path.insert(0, str(_HERE / "fantasy" / "talent"))

ARTIFACT = _HERE / "fantasy" / "talent" / "college_qb_score_2026.csv"
PROV = _HERE / "fantasy" / "talent" / "college_qb_score_2026.provenance.json"

_FORBIDDEN = re.compile(
    r"\b(buy|sell|fade|steal|reach|must[- ]?draft|overvalued|undervalued|"
    r"hit[- ]?rate|accuracy)\b", re.I)


def test_artifact_schema_and_spec_constants():
    assert ARTIFACT.exists(), "college_qb_score_2026.csv missing — run build_college_qb_score.py"
    df = pd.read_csv(ARTIFACT)
    for col in ("pff_player_id", "gsis_id", "nfl_player_id", "player", "norm_name", "college",
                "final_season", "seasons", "reached_nfl", "is_2026_rookie", "college_qb",
                "score", "reliability", "rank_final_season"):
        assert col in df.columns, f"missing column {col}"
    assert len(df) > 500, f"suspiciously small artifact: {len(df)} rows"
    assert df["score"].between(40, 99).all(), "score outside the [40, 99] clip"
    assert not df["pff_player_id"].duplicated().any(), "duplicate college player"

    import build_college_qb_score as build  # noqa: E402  (path set above)
    assert abs(sum(build.WEIGHTS.values()) - 1.0) < 1e-9, "R35 weights must sum to 1.000"
    assert build.WEIGHTS["grades_pass"] == 0.250 and build.WEIGHTS["grades_run"] == 0.250
    assert build.GAMMA == 0.4, "R35 ratified gamma = 0.4"
    assert build.DB_FLOOR == 200, "R35 pool = qualified starters, 200+ dropbacks"


def test_provenance_records_the_anchor_pool():
    prov = json.loads(PROV.read_text(encoding="utf-8"))
    assert prov["gamma"] == 0.4 and prov["dropback_floor"] == 200
    # Stage 5 is anchored on NFL-REACHING QBs, not the full college pool — this is the
    # ratified decision that puts the college and NFL scales on comparable footing.
    assert prov["anchor"]["fitted_on"] == "NFL-reaching QBs"
    assert prov["anchor"]["n"] < prov["rows"], "anchor pool must be a subset of all QBs"
    assert prov["mom_k"]["grades_run"] < prov["mom_k"]["grades_pass"], \
        "designed runs are the thinnest facet — its k must be the smallest"


def test_rookie_and_returning_populations_are_disjoint():
    df = pd.read_csv(ARTIFACT)
    rookies = df[df["is_2026_rookie"].astype(bool)]
    returning = df[~df["is_2026_rookie"].astype(bool)]
    assert len(rookies) > 0 and len(returning) > 0
    assert set(rookies["pff_player_id"]).isdisjoint(set(returning["pff_player_id"]))
    # every flagged rookie resolved to a deploy id via the guarded name join
    assert rookies["nfl_player_id"].notna().all()
    assert not rookies["nfl_player_id"].duplicated().any(), "two college QBs hit one NFL id"


def test_draft_board_shows_college_talent_for_rookie_qbs():
    import draft_board_2026 as board

    df = board._load_board_2026().reset_index()
    qb = df[df["position"] == "QB"]
    scored = qb[qb["college_talent"].notna()]
    assert len(scored) >= 2, "rookie QBs on the board must now carry a College Talent score"
    names = set(scored["player"])
    assert {"Fernando Mendoza", "Ty Simpson"} <= names, names

    # the college QB source participates in the cache fingerprint
    paths = [p for p, _m, _s in board._board_source_fingerprint()]
    assert str(board.COLLEGE_QB_CSV) in paths

    # RB/WR/TE college talent is untouched by the QB fill (disjoint by position)
    art = pd.read_csv(ARTIFACT).set_index("nfl_player_id")["score"]
    for row in scored.itertuples():
        assert abs(float(row.college_talent) - float(art.get(row.player_id))) < 1e-6


def test_rookie_board_qb_fills_blanks_and_rb_wr_te_are_replaced():
    """QB (R35) FILLS blanks only. RB (R36), WR (R38) and TE (R40) REPLACE the box-score value
    wherever they cover a player."""
    import page_rookie_board as page

    raw = page._load(2026)
    df = page._attach_college_qb(page._attach_projection(raw, 2026), 2026)
    assert len(df) == len(raw)

    pos = raw.set_index("gsis_id")["position"]
    before = raw.set_index("gsis_id")["talent_score"]
    after = df.set_index("gsis_id")["talent_score"]
    for key, value in before[before.notna()].items():
        if pos[key] in ("RB", "WR", "TE"):
            continue          # RB/WR/TE (R36/R38/R40) are REPLACED by design — see below
        assert abs(float(after[key]) - float(value)) < 1e-6,             f"{key}: a QB talent score was overwritten ({value} -> {after[key]})"

    # RB rows covered by R36 must now carry the R36 value, not the box-score one
    rb_art = pd.read_csv(_HERE / "fantasy" / "talent" / "college_rb_score_2026.csv")
    rb_art = rb_art[rb_art["is_2026_rookie"].astype(bool)]
    by_name = rb_art.drop_duplicates("norm_name").set_index("norm_name")["score"]
    import page_rookie_board as _p
    replaced = 0
    for row in df[df["position"] == "RB"].itertuples():
        want = by_name.get(_p.norm_name(row.name))
        if want is not None and pd.notna(want):
            assert abs(float(row.talent_score) - float(want)) < 1e-6,                 f"{row.name}: RB row not replaced by R36 ({row.talent_score} != {want})"
            replaced += 1
    assert replaced >= 5, f"expected R36 to cover several RB rows, got {replaced}"

    assert df[df["position"] == "QB"]["talent_score"].notna().sum() >= 6
    # RB gained rows only where the box-score build had none
    rb_before = int(raw[raw["position"] == "RB"]["talent_score"].notna().sum())
    rb_after = int(df[df["position"] == "RB"]["talent_score"].notna().sum())
    assert rb_after >= rb_before, "RB coverage must not shrink"


def test_returning_college_qb_expander_is_collapsed_and_excludes_rookies():
    def _entry():
        import page_rookie_board
        page_rookie_board.render()

    at = AppTest.from_function(_entry, default_timeout=180).run()
    assert not at.exception, at.exception
    assert not at.error, [e.value for e in at.error]

    exps = [e for e in at.expander
            if "not in the" in str(getattr(e, "label", "")).lower()
            and "rookie class" in str(getattr(e, "label", "")).lower()]
    labels = [str(e.label) for e in exps]
    assert any("QB" in x for x in labels), f"returning-college-QB expander missing: {labels}"
    assert any("RB" in x for x in labels), f"returning-college-RB expander missing: {labels}"
    assert any("WR" in x for x in labels), f"returning-college-WR expander missing: {labels}"
    assert any("TE" in x for x in labels), f"returning-college-TE expander missing: {labels}"
    for e in exps:
        assert e.proto.expanded is False, f"{e.label} must be collapsed on load"

    shown = None
    for el in at.dataframe:
        v = el.value
        d = v.data if hasattr(v, "data") else v
        try:
            if "College Talent" in d.columns and "College" in d.columns:
                shown = d
        except Exception:
            pass
    assert shown is not None, "returning-QB table not rendered"
    art = pd.read_csv(ARTIFACT)
    rookie_names = set(art[art["is_2026_rookie"].astype(bool)]["player"])
    assert rookie_names.isdisjoint(set(shown["Player"])), \
        "this year's rookies must NOT appear in the returning-college view"


def test_no_forbidden_language_in_rookie_board_copy():
    def _entry():
        import page_rookie_board
        page_rookie_board.render()

    at = AppTest.from_function(_entry, default_timeout=180).run()
    text = " ".join(str(m.value) for m in at.markdown)
    text += " " + " ".join(str(c.value) for c in at.caption)
    hits = [h for h in _FORBIDDEN.findall(text)]
    assert not hits, f"forbidden language on the rookie board: {set(hits)}"


if __name__ == "__main__":
    test_artifact_schema_and_spec_constants()
    test_provenance_records_the_anchor_pool()
    test_rookie_and_returning_populations_are_disjoint()
    test_draft_board_shows_college_talent_for_rookie_qbs()
    test_rookie_board_qb_fills_blanks_and_rb_wr_te_are_replaced()
    test_returning_college_qb_expander_is_collapsed_and_excludes_rookies()
    test_no_forbidden_language_in_rookie_board_copy()
    print("OK  college QB talent score: artifact contract, provenance, disjoint populations, "
          "both board integrations, collapsed returning-QB view, clean copy")
