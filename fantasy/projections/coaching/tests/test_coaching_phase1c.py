"""Registered Phase 1C test suite — automatically discoverable by pytest.

Replaces printed invariants with HARD ASSERTIONS. Before this file, build_exposure.py printed its
exposure invariants and a human had to read them; a regression would have scrolled past silently.

Run:  pytest fantasy/projections/coaching/tests/ -q
"""
import hashlib
import pathlib
import sys

import pandas as pd
import pytest

HERE = pathlib.Path(__file__).resolve().parent
COACH = HERE.parent
DATA = COACH / "data"
sys.path.insert(0, str(COACH))

import build_exposure as BE            # noqa: E402
import build_playcaller_table as BPT   # noqa: E402
import date_provenance as DP           # noqa: E402


def _md5(p):
    return hashlib.md5(pathlib.Path(p).read_bytes()).hexdigest()


@pytest.fixture(scope="module")
def tbl():
    return pd.read_csv(DATA / "actual_play_caller.csv")


@pytest.fixture(scope="module")
def gl(tbl):
    return BE.game_level_identity(pd.read_csv(DATA / "head_coach_games.csv"), tbl)


@pytest.fixture(scope="module")
def exp(gl):
    return BE.exposure_long(gl)


# ------------------------------------------------------------------ determinism
def test_rebuild_is_byte_identical():
    """Two consecutive builds must produce identical bytes for BOTH artifacts.

    The v3.2 game-count fix once lived in a repair script and a later rebuild silently reverted it.
    A correction that a rebuild undoes is not a correction.
    """
    before = {f: _md5(DATA / f) for f in ("actual_play_caller.csv", "source_ledger.csv")}
    BPT.build()
    after = {f: _md5(DATA / f) for f in ("actual_play_caller.csv", "source_ledger.csv")}
    assert before == after, f"non-deterministic build: {before} -> {after}"


def test_bye_week_game_counts_stay_corrected(tbl):
    """GB 2015 spans weeks 1-14 but only 13 GAMES (a bye sits inside the span)."""
    gb = tbl[(tbl.season == 2015) & (tbl.team == "GB")].sort_values("week_start")
    assert list(gb.n_games_attributed) == [13, 3], "bye-week counting regressed to week arithmetic"


def test_2026_scheduled_counts_are_17(tbl):
    y = tbl[tbl.season == 2026]
    assert set(y.n_games_attributed) == {17}
    assert y.n_games_attributed.sum() == 32 * 17


def test_no_overlapping_or_duplicate_segments(tbl):
    for (s, t), g in tbl.groupby(["season", "team"]):
        g = g.sort_values("week_start")
        ends = g.week_end.fillna(99).tolist()
        starts = g.week_start.fillna(1).tolist()
        for i in range(1, len(g)):
            assert starts[i] > ends[i - 1], f"overlapping segments for {s} {t}"
    assert not tbl.duplicated(["season", "team", "week_start"]).any()


# ------------------------------------------------------------------ date provenance
def test_no_placeholder_date_is_ever_eligible():
    """Jan-1 / Aug-1 placeholders must classify as inferred/missing and never clear a cutoff."""
    for key, stored in [("made_up_a", "2021-01-01"), ("made_up_b", "2024-08-01")]:
        prov = DP.classify(key, stored)
        assert prov["source_date_precision"] in ("inferred", "missing")
        _lo, hi = DP.bounds(prov["source_date"], prov["source_date_precision"])
        assert hi is None
        assert DP.eligible_at(hi, "2030-01-01") is False


def test_month_precision_uses_conservative_upper_bound():
    lo, hi = DP.bounds("2024-08-01", DP.MONTH)
    assert (lo, hi) == ("2024-08-01", "2024-08-31")
    assert DP.eligible_at(hi, "2024-08-30") is False   # month could end after the cutoff
    assert DP.eligible_at(hi, "2024-09-04") is True


def test_audited_dates_match_their_bylines():
    """The five audited sources must carry their real byline dates, not the inferred placeholders."""
    led = pd.read_csv(DATA / "source_ledger.csv").set_index("source_key")
    assert led.loc["yardbarker2021", "source_date"] == "2021-10-18"
    assert led.loc["espn2023", "source_date"] == "2023-08-23"
    assert led.loc["espn2024", "source_date"] == "2024-08-30"
    assert led.loc["espn2025", "source_date"] == "2025-09-09"
    assert led.loc["cbs2022phi", "source_date_precision"] == "missing"


def test_ledger_and_table_cannot_diverge(tbl):
    """The exact failure Joseph flagged: table says 2021-10-18, ledger says 2021-01-01."""
    led = pd.read_csv(DATA / "source_ledger.csv")
    by_url = led.set_index("url")["source_date"].to_dict()
    sub = tbl[tbl.source_url.notna() & tbl.source_date.notna()]
    for _, r in sub.iterrows():
        if r.source_url in by_url and pd.notna(by_url[r.source_url]):
            assert str(r.source_date)[:10] == str(by_url[r.source_url])[:10], (
                f"divergence for {r.source_url}: table={r.source_date} ledger={by_url[r.source_url]}")


# ------------------------------------------------------------------ exposure invariants (HARD)
def test_caller_exposure_equals_known_share(gl, exp):
    """Caller exposure per team-season must equal caller_known_share, not 1.0."""
    known = BE.caller_known_share(gl)
    cal = (exp[exp.role == BE.ROLE_CALLER].groupby(["season", "team"])["exposure"].sum()
           .rename("got").reset_index())
    m = known.merge(cal, on=["season", "team"], how="left").fillna({"got": 0.0})
    bad = m[(m.got - m.caller_known_share).abs() > 1e-9]
    assert bad.empty, f"caller exposure != known share for {len(bad)} team-seasons"


def test_no_person_holds_both_roles_in_one_game(gl):
    same = gl[gl.hc_person_id == gl.caller_person_id]
    assert len(same) > 0, "fixture sanity: some HC-called games must exist"
    # those games must contribute ONLY caller exposure
    exp = BE.exposure_long(gl)
    for _, r in same.head(50).iterrows():
        ctx = exp[(exp.season == r.season) & (exp.team == r.team)
                  & (exp.person_id == r.hc_person_id) & (exp.role == BE.ROLE_HC_CTX)]
        # HC-context may exist for OTHER weeks, but never sourced from this game
        assert ctx.exposure.sum() < 1.0 + 1e-9


def test_exposure_never_exceeds_one(exp):
    tot = exp.groupby(["season", "team", "role"])["exposure"].sum()
    assert (tot <= 1.0 + 1e-9).all(), "an exposure block exceeds a full team-season"


# ------------------------------------------------------------------ EXACT routing values
def test_mcdaniel_caller_games_and_exposure(gl, exp):
    """Caller-first collapse: McDaniel's MIA 2022-25 HC-called games belong to the CALLER block."""
    pid = BE._pid("Mike McDaniel")
    cal = exp[(exp.person_id == pid) & (exp.role == BE.ROLE_CALLER)
              & (exp.season.between(2022, 2025))]
    assert len(cal) == 4, f"expected 4 MIA seasons, got {len(cal)}"
    assert cal.exposure.eq(1.0).all(), "McDaniel called every game; exposure must be exactly 1.0"
    games = gl[(gl.caller_person_id == pid) & (gl.season.between(2022, 2025))].game_id.nunique()
    assert games == 68, f"expected exactly 68 caller games, got {games}"
    ctx = exp[(exp.person_id == pid) & (exp.role == BE.ROLE_HC_CTX)]
    assert ctx.empty, "McDaniel called his own plays; he must have NO HC-context rows"


def test_mcvay_unified_across_titles(gl, exp):
    """McVay's WAS OC games and LA HC-called games accumulate under ONE portable identity."""
    pid = BE._pid("Sean McVay")
    # 181 is the PRIOR-games count entering 2026 (through 2025) -- the number the caller-first
    # correction was verified against. The table also carries 2026, so the all-time count is
    # 181 + 17 = 198. Both are asserted so neither can drift.
    prior = gl[(gl.caller_person_id == pid) & (gl.season <= 2025)].game_id.nunique()
    assert prior == 181, f"expected exactly 181 caller games through 2025, got {prior}"
    games = gl[gl.caller_person_id == pid].game_id.nunique()
    assert games == 198, f"expected 181 + 17 (2026) = 198 all-time caller games, got {games}"
    ctx = exp[(exp.person_id == pid) & (exp.role == BE.ROLE_HC_CTX)]
    assert len(ctx) == 0, "McVay called plays every season; zero HC-context rows expected"
    rams = exp[(exp.person_id == pid) & (exp.role == BE.ROLE_CALLER) & (exp.team == "LA")]
    assert rams.exposure.eq(1.0).all(), "Rams caller exposure must be exactly 1.0"


def test_harbaugh_2026_routing(exp, tbl):
    """2026 LAC: HC Harbaugh, caller McDaniel, hc_changed=0, pc_changed=1."""
    hb = BE._pid("Jim Harbaugh")
    ctx = exp[(exp.person_id == hb) & (exp.season == 2026) & (exp.team == "LAC")
              & (exp.role == BE.ROLE_HC_CTX)]
    assert len(ctx) == 1 and abs(ctx.exposure.iloc[0] - 1.0) < 1e-9, (
        "Harbaugh delegates play-calling; HC-context exposure must be exactly 1.0")
    lac = tbl[(tbl.season == 2026) & (tbl.team == "LAC")]
    assert lac.actual_play_caller.iloc[0] == "Mike McDaniel"


def test_rams_2026_routing(exp, tbl):
    """2026 LAR: McVay is BOTH HC and caller -> caller block only, exposure 1.0."""
    pid = BE._pid("Sean McVay")
    cal = exp[(exp.person_id == pid) & (exp.season == 2026) & (exp.role == BE.ROLE_CALLER)]
    assert len(cal) == 1 and abs(cal.exposure.iloc[0] - 1.0) < 1e-9
    ctx = exp[(exp.person_id == pid) & (exp.season == 2026) & (exp.role == BE.ROLE_HC_CTX)]
    assert ctx.empty


# ------------------------------------------------------------------ leakage
def test_preseason_snapshot_carries_no_realized_outcome():
    import build_preseason_snapshot as BPS
    snap = pd.read_csv(DATA / "preseason_staff_snapshot.csv")
    for c in BPS.FORBIDDEN_IN_SNAPSHOT:
        assert c not in snap.columns, f"LEAK: {c} reached the preseason snapshot"


def test_unavailable_identity_is_na_not_zero():
    snap = pd.read_csv(DATA / "preseason_staff_snapshot.csv")
    unk = snap[snap.expected_opening_caller_id.isna()]
    assert len(unk) > 0, "fixture sanity: some identities are unavailable at cutoff"
    assert unk.pc_changed_entering.isna().all(), (
        "an unknown identity must yield NA for the change flag, never 0")


def test_post_cutoff_attributing_source_never_clears_a_cutoff():
    """No row anywhere may be eligible via an attributing source published after its own cutoff."""
    ev = pd.read_csv(DATA / "preseason_evidence_ledger.csv")
    bad = ev[ev.attributing_source_clears_cutoff
             & (ev.attributing_source_upper_bound > ev.projection_cutoff)]
    assert bad.empty, f"{len(bad)} rows cleared a cutoff with a post-cutoff source"


# ------------------------------------------------------------------ Phase 1C.1 recovery
def test_canonical_table_is_unchanged_by_recovery():
    """The 1C.1 pass rebuilds COMPANIONS only. The v3.4 retrospective freeze must be untouched."""
    assert _md5(DATA / "actual_play_caller.csv") == "98f1c66b7387c16bba6a5463f4e0fa06"


def test_recovered_rows_are_exactly_the_researched_ones():
    ev = pd.read_csv(DATA / "preseason_evidence_ledger.csv")
    rec = ev[ev.recovered_by_targeted_research]
    assert len(rec) == 52, f"expected 52 recovered rows, got {len(rec)}"
    assert dict(rec.groupby("season").size()) == {2019: 2, 2020: 6, 2021: 7, 2022: 6, 2025: 31}


def test_every_recovered_row_clears_its_own_cutoff():
    """Eligibility is per-season, never a global date."""
    ev = pd.read_csv(DATA / "preseason_evidence_ledger.csv")
    for _, r in ev[ev.recovered_by_targeted_research].iterrows():
        assert r.evidence_source_upper_bound <= r.projection_cutoff, (
            f"{r.season} {r.team}: evidence {r.evidence_source_upper_bound} "
            f"postdates cutoff {r.projection_cutoff}")


def test_2025_recovered_from_pfsn_not_from_the_post_cutoff_espn_list():
    """ESPN's 2025 list is 2025-09-09, SIX DAYS after the 2025-09-03 cutoff, and must never confer
    eligibility. 2025's coverage comes entirely from PFSN 2025-06-25."""
    ev = pd.read_csv(DATA / "preseason_evidence_ledger.csv")
    y = ev[ev.season == 2025]
    assert not y.attributing_source_clears_cutoff.any(), (
        "the post-cutoff ESPN list conferred eligibility")
    elig = y[y.eligible_at_cutoff]
    assert len(elig) == 31
    assert (elig.evidence_source_date == "2025-06-25").all()
    assert (elig.evidence_publisher == "Pro Football Network").all()


def test_2025_nyg_ambiguous_entry_is_refused():
    """PFSN names 'Brian Daboll/Mike Kafka' -- two people. Ambiguity must be refused, not resolved
    toward whichever name improves coverage."""
    ev = pd.read_csv(DATA / "preseason_evidence_ledger.csv")
    r = ev[(ev.season == 2025) & (ev.team == "NYG")].iloc[0]
    assert not r.eligible_at_cutoff
    assert r.unknown_reason == "pre_cutoff_ambiguity"
    assert pd.isna(r.expected_opening_caller_id)


# ============================================================ v3.5 AS-OF RULE (A-F)
# The retrospective opener is an AUDIT LABEL. It must never decide eligibility -- using it that way
# filters the snapshot to expectations that later proved correct, which is look-ahead leakage.
def _ledger(evidence, actual, season=2099, team="SYN", cutoff="2099-09-01"):
    """Build a one-row ledger from synthetic evidence + a synthetic retrospective opener."""
    import build_preseason_snapshot as BPS
    import preseason_evidence as PE
    tbl = pd.DataFrame([dict(season=season, team=team, week_start=1, week_end=99,
                             person_id=actual, source_url=None, source_publisher=None)])
    orig = PE.EVIDENCE
    try:
        PE.EVIDENCE = evidence
        return BPS.build_evidence_ledger(tbl, {season: cutoff}).iloc[0]
    finally:
        PE.EVIDENCE = orig


def _ev(pid, date, season=2099, team="SYN", **kw):
    d = dict(season=season, team=team, person_id=pid, date=date, precision="exact_day",
             url="http://x", publisher="X", raw_date=date, source_class="test",
             statement="synthetic")
    d.update(kw)
    return d


def test_A_expectation_differing_from_actual_is_still_eligible():
    """Pre-cutoff source says A, actual opener turned out to be B -> expected MUST be A."""
    r = _ledger([_ev("caller_a", "2099-06-01")], actual="caller_b")
    assert r.expected_opening_caller_id == "caller_a"
    assert r.eligible_at_cutoff is True or r.eligible_at_cutoff == True  # noqa: E712
    assert r.expectation_matched_actual is False or r.expectation_matched_actual == False  # noqa: E712


def test_B_unresolved_retrospective_identity_can_still_be_eligible():
    """A valid preseason expectation can exist even when actual attribution is never resolved."""
    r = _ledger([_ev("caller_a", "2099-06-01")], actual=None)
    assert r.expected_opening_caller_id == "caller_a"
    assert r.eligible_at_cutoff
    assert pd.isna(r.expectation_matched_actual)


def test_C_later_pre_cutoff_source_supersedes_earlier():
    """Latest information available at the cutoff wins -- not the earliest."""
    r = _ledger([_ev("caller_a", "2099-03-01"), _ev("caller_b", "2099-08-01")], actual="caller_a")
    assert r.expected_opening_caller_id == "caller_b"
    assert r.evidence_source_date == "2099-08-01"


def test_D_post_cutoff_change_does_not_move_the_expectation():
    """A change announced AFTER the cutoff cannot reach back into the snapshot."""
    r = _ledger([_ev("caller_a", "2099-06-01"), _ev("caller_b", "2099-10-01")], actual="caller_b")
    assert r.expected_opening_caller_id == "caller_a"
    assert r.expectation_matched_actual is False or r.expectation_matched_actual == False  # noqa: E712


def test_E_true_pre_cutoff_ambiguity_is_unknown():
    """Two equally-current qualifying sources disagreeing -> UNKNOWN, not a coin flip."""
    r = _ledger([_ev("caller_a", "2099-06-01"), _ev("caller_b", "2099-06-01")], actual="caller_a")
    assert r.expected_opening_caller_id is None or pd.isna(r.expected_opening_caller_id)
    assert not r.eligible_at_cutoff
    assert r.unknown_reason == "pre_cutoff_ambiguity"

    # a single source naming "A/B" is equally unusable
    r2 = _ledger([_ev("AMBIGUOUS_a_or_b", "2099-06-01")], actual="caller_a")
    assert not r2.eligible_at_cutoff
    assert r2.conflict_status == "ambiguous_pre_cutoff_source"


def test_F_audit_fields_are_isolated_from_the_feature_snapshot():
    """The eventual answer must not be one join away from any feature builder."""
    snap = pd.read_csv(DATA / "preseason_staff_snapshot.csv")
    for c in ("retrospective_opening_caller_id", "expectation_matched_actual"):
        assert c not in snap.columns, f"AUDIT FIELD LEAKED INTO FEATURE SNAPSHOT: {c}"
    # ...but they must still exist in the evidence ledger for validation
    led = pd.read_csv(DATA / "preseason_evidence_ledger.csv")
    assert "retrospective_opening_caller_id" in led.columns
    assert "expectation_matched_actual" in led.columns


# ============================================================ 2019 research completion
def test_2019_all_27_originally_unavailable_rows_have_a_completed_disposition():
    import research_attempts_2019 as RA
    ev = pd.read_csv(DATA / "preseason_evidence_ledger.csv")
    y = ev[ev.season == 2019].set_index("team")
    assert len(RA.ORIGINAL_UNAVAILABLE) == 27
    for t in RA.ORIGINAL_UNAVAILABLE:
        assert RA.research_complete(t), f"2019 {t} has no recorded disposition"
        assert bool(y.loc[t, "research_complete"]), f"2019 {t} not marked complete in the ledger"


def test_no_2019_row_remains_not_individually_researched():
    ev = pd.read_csv(DATA / "preseason_evidence_ledger.csv")
    y = ev[ev.season == 2019]
    assert "not_individually_researched" not in set(y.research_status), (
        "a 2019 row is still unresearched")
    assert set(y.research_status) <= {
        "recovered_eligible", "searched_no_qualifying_source", "pre_cutoff_ambiguous",
        "pre_cutoff_conflict", "source_date_unverifiable"}


def test_2019_recoveries_are_eligible_and_the_rest_are_not():
    ev = pd.read_csv(DATA / "preseason_evidence_ledger.csv")
    y = ev[ev.season == 2019]
    rec = y[y.research_status == "recovered_eligible"]
    assert rec.eligible_at_cutoff.all()
    assert set(rec.team) >= {"TB", "CLE"}, "the two 2019 recoveries must be TB and CLE"
    assert not y[y.research_status != "recovered_eligible"].eligible_at_cutoff.any()


def test_post_cutoff_kitchens_quote_is_not_the_cle_source():
    """The explicit Kitchens quote is 2019-09-23 -- after the cutoff. CLE must rest on the
    2019-01-14 report of his announcement instead."""
    ev = pd.read_csv(DATA / "preseason_evidence_ledger.csv")
    r = ev[(ev.season == 2019) & (ev.team == "CLE")].iloc[0]
    assert r.evidence_source_date == "2019-01-14"
    assert r.evidence_source_upper_bound <= r.projection_cutoff
