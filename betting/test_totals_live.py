"""Live-totals inference: the as-of wiring, the fail-closed preflight, and the proof that
historical values did not move.

WHAT IS REAL AND WHAT IS SYNTHETIC — read before citing any of this.
  * The SCHEDULE is real, retained nflverse data (`fixtures/totals_live_schedule.csv`,
    586 rows, 10 franchises, seasons 2016/2017/2019/2020/2021, regenerable with
    `fixtures/build_totals_live_fixture.py`). Team aliases (SD→LAC, OAK→LV), byes, the 2020
    COVID reschedules, playoff weeks, first-week-of-season rows and null weather are all
    genuine rows, not constructed cases.
  * The WEATHER file is a real slice of the same source, kept only where the source had a
    value — so a lookup miss (49% of rows) is the normal case, as it is in production.
  * The PLAY-BY-PLAY is SYNTHETIC. Retaining real PBP would dwarf the repo. A deterministic
    seeded play table is generated from the real game ids. This affects `pace_5g` only, and
    the equivalence proof compares old vs new over the SAME synthetic table, so the
    comparison is still valid — but "pace matches production values" is NOT claimed.
  * The legacy builder is VENDORED verbatim from commit `3dbd110`
    (`fixtures/legacy_totals_builder.py`, sha256-pinned) and EXECUTED. The
    "historical values are unchanged" claim comes from running both builders side by side,
    not from reading the diff.

Nothing here touches `betting/totals_tracker.csv` or `betting/predictions_tracker.csv`; an
autouse fixture fails the session if either file's bytes change while these tests run.
"""
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

_BETTING = Path(__file__).resolve().parent
_FIXTURES = _BETTING / "fixtures"
for _p in (str(_BETTING), str(_FIXTURES)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from legacy_totals_builder import (  # noqa: E402
    LEGACY_CELL_SHA256, LEGACY_CELL_SOURCE_COMMIT,
    build_totals_features as legacy_build_totals_features,
)
from totals_asof import (  # noqa: E402
    MUST_VARY_COLS, TOTALS_FEATURE_COLS_EXPECTED, TotalsPreflightError,
    WEATHER_SOURCE_COLS, totals_live_preflight,
)

SCHEDULE_CSV = _FIXTURES / "totals_live_schedule.csv"
WEATHER_CSV = _FIXTURES / "totals_live_weather.csv"
NOTEBOOK = _BETTING / "totals_features.ipynb"

# The designated FUTURE slate: the last week of the fixture. Its six real games carry three
# distinct roof strings, which is what makes the is_dome assertion meaningful.
FUTURE_SEASON, FUTURE_WEEK = 2021, 18

TRACKERS = [_BETTING / "totals_tracker.csv", _BETTING / "predictions_tracker.csv"]


# ── guardrails ────────────────────────────────────────────────────────────────────────
@pytest.fixture(scope="session", autouse=True)
def _forward_logs_are_untouched():
    """The trackers are append-only forward logs. Nothing in this suite may write to them."""
    before = {p: (p.stat().st_mtime_ns, hashlib.sha256(p.read_bytes()).hexdigest())
              for p in TRACKERS if p.exists()}
    yield
    for p, (mtime, digest) in before.items():
        now = hashlib.sha256(p.read_bytes()).hexdigest()
        assert now == digest, f"FORWARD LOG MUTATED by the test session: {p}"
        assert p.stat().st_mtime_ns == mtime, f"forward log was rewritten: {p}"


# ── loading the notebook's public surface ─────────────────────────────────────────────
def _load_builder():
    """Exec `totals_features.ipynb` with RUN_TESTS=False, the way the consumers load it."""
    ns = {"RUN_TESTS": False, "__name__": "totals_features_nb"}
    nb = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
    for cell in nb["cells"]:
        if cell["cell_type"] == "code":
            exec("".join(cell["source"]), ns)  # noqa: S102
    return ns


@pytest.fixture(scope="module")
def nb():
    return _load_builder()


# ── fixture data ──────────────────────────────────────────────────────────────────────
def _schedule():
    s = pd.read_csv(SCHEDULE_CSV)
    s["season"] = s["season"].astype(int)
    s["week"] = s["week"].astype(int)
    return s


def _future_split():
    """(sched_with_future_unplayed, completed_only_sched, future_game_ids)."""
    s = _schedule()
    fut = (s["season"] == FUTURE_SEASON) & (s["week"] == FUTURE_WEEK)
    assert fut.sum() >= 4, "future slate too small to interpret"
    s.loc[fut, ["home_score", "away_score", "result"]] = np.nan
    completed = s[s["home_score"].notna()].copy()
    return s, completed, list(s.loc[fut, "game_id"])


def _synth_pbp(sched, seed=7):
    """Deterministic play table over the REAL game ids. Synthetic by design — see module doc."""
    played = sched[sched["home_score"].notna()]
    rng = np.random.default_rng(seed)
    gid, team = [], []
    for g, h, a in zip(played["game_id"], played["home_team"], played["away_team"]):
        for t in (h, a):
            n = int(rng.integers(52, 85))
            gid.extend([g] * n)
            team.extend([t] * n)
    return pd.DataFrame({"game_id": gid, "posteam": team})


def _g_from(sched, game_ids=None):
    """A `g` frame shaped like the spread pipeline's output (roof already ordinal-encoded,
    scores NOT carried — the builder pulls them from sched, as in the training path)."""
    d = sched if game_ids is None else sched[sched["game_id"].isin(game_ids)]
    g = d[["game_id", "season", "week", "home_team", "away_team",
           "spread_line", "total_line", "div_game"]].copy().reset_index(drop=True)
    codes = {"outdoors": 0, "dome": 1, "closed": 2, "open": 3}
    g["roof"] = d["roof"].map(codes).fillna(0).astype(int).to_numpy()
    return g


def _cmp(a, b, cols):
    """Column-by-column equality treating NaN as equal. Returns {col: n_differing}."""
    out = {}
    for c in cols:
        x = pd.to_numeric(a[c], errors="coerce").to_numpy(dtype="float64")
        y = pd.to_numeric(b[c], errors="coerce").to_numpy(dtype="float64")
        same = (np.isnan(x) & np.isnan(y)) | (x == y)
        if not same.all():
            out[c] = int((~same).sum())
    return out


# ── the fixture really does cover the documented shapes ───────────────────────────────
def test_fixture_covers_the_documented_real_schedule_shapes():
    s = _schedule()
    teams = set(s["home_team"]) | set(s["away_team"])

    # relocations / aliases: the SAME franchise under two codes, in the real rows
    for old, new in [("SD", "LAC"), ("OAK", "LV")]:
        assert old in teams and new in teams, f"alias pair {old}/{new} missing from fixture"
    assert s.loc[s["home_team"] == "SD", "season"].max() < \
        s.loc[s["home_team"] == "LAC", "season"].min(), "SD/LAC eras overlap — not a relocation"

    # byes: at least one team has a gap in its week sequence within a season
    long = pd.concat([s[["season", "week", "home_team"]].rename(columns={"home_team": "t"}),
                      s[["season", "week", "away_team"]].rename(columns={"away_team": "t"})])
    reg = long[long["week"] <= 17]
    gaps = (reg.groupby(["t", "season"])["week"]
            .apply(lambda w: sorted(w) != list(range(min(w), max(w) + 1))))
    assert gaps.any(), "no bye weeks in the fixture"

    # first game of a season, playoffs, missing weather, postponed/out-of-order dates
    assert (s["week"] == 1).any()
    assert (s["week"] > 18).any(), "no playoff rows"
    assert s["temp"].isna().mean() > 0.2, "weather is not meaningfully missing"
    # postponed games: the real 2020 COVID reschedules, which land on weekdays no NFL game
    # is normally played on and push a week's span past the usual Thu–Mon window.
    gd = pd.to_datetime(s["gameday"])
    postponed = s[gd.dt.dayofweek.isin([1, 2])]  # Tue / Wed
    assert len(postponed) >= 3, f"no postponed rows retained: {len(postponed)}"
    d2020 = s[(s["season"] == 2020) & (s["week"].between(1, 17))]
    spans = d2020.groupby("week")["gameday"].agg(["min", "max"])
    assert (pd.to_datetime(spans["max"]) - pd.to_datetime(spans["min"])).dt.days.max() >= 6, \
        "no rescheduled/postponed week in the fixture"
    # ordering is resolved on (season, week), never on date — so a team may not appear twice
    # in one (season, week) slot, which is the tie the as-of key cannot break.
    dup = (pd.concat([s[["season", "week", "home_team"]].rename(columns={"home_team": "t"}),
                      s[["season", "week", "away_team"]].rename(columns={"away_team": "t"})])
           .duplicated(subset=["season", "week", "t"]).sum())
    assert dup == 0, f"{dup} team-week collisions — the as-of key would be ambiguous"

    wx = pd.read_csv(WEATHER_CSV)
    assert 0 < len(wx) < len(s), "weather fixture must be a partial cover"


# ── the vendored legacy builder is the real pre-fix code ──────────────────────────────
def test_vendored_legacy_builder_matches_the_committed_notebook_cell():
    """The equivalence proof is only worth anything if the 'old' code really is the old code."""
    try:
        raw = subprocess.check_output(
            ["git", "-c", "safe.directory=*", "show",
             f"{LEGACY_CELL_SOURCE_COMMIT}:betting/totals_features.ipynb"],
            cwd=str(_BETTING.parent), stderr=subprocess.DEVNULL)
    except (OSError, subprocess.CalledProcessError):  # pragma: no cover - env dependent
        pytest.skip("git history unavailable in this environment")
    src = "".join(json.loads(raw.decode("utf-8"))["cells"][10]["source"])
    assert hashlib.sha256(src.encode("utf-8")).hexdigest() == LEGACY_CELL_SHA256
    assert src.startswith("def build_totals_features(g, sched, pbp_full, weather_path=None):")
    vendored = (_FIXTURES / "legacy_totals_builder.py").read_text(encoding="utf-8")
    assert src in vendored, "vendored copy has drifted from the committed cell"


# ── 1. HISTORICAL VALUES DID NOT MOVE ─────────────────────────────────────────────────
# MEASURED, not assumed. Thirteen of the fourteen columns come back BIT-IDENTICAL. The
# fourteenth, `league_avg_total_4wk`, differs on 150 of 784 rows by exactly ONE ULP
# (max |Δ| 7.1e-15, max relative 1.7e-16). Cause: the legacy value is
# `pandas.rolling(4).mean()`, which accumulates a running sum, while the as-of value is
# `numpy.mean` over a slice, which sums pairwise. Same mathematical quantity, different
# summation order, last representable bit. The other columns are unaffected because their
# window values are integer game scores and play counts, which sum exactly in float64.
# This bound is asserted, so a real value movement cannot hide behind the tolerance.
ULP_ONLY_COLS = {"league_avg_total_4wk"}
MAX_ULPS = 1


def _ulps(a, b):
    m = ~(np.isnan(a) & np.isnan(b))
    step = np.abs(np.nextafter(a[m], np.inf) - a[m])
    return np.abs(a[m] - b[m]) / np.where(step == 0, 1.0, step)


def _assert_historically_identical(old, new):
    assert len(old) == len(new)
    assert (old["game_id"].to_numpy() == new["game_id"].to_numpy()).all()
    exact = [c for c in TOTALS_FEATURE_COLS_EXPECTED if c not in ULP_ONLY_COLS]
    diffs = _cmp(old, new, exact)
    assert not diffs, f"historical feature values MOVED: {diffs} (rows={len(old)})"
    for c in ULP_ONLY_COLS:
        u = _ulps(old[c].to_numpy(dtype="float64"), new[c].to_numpy(dtype="float64"))
        assert u.max() <= MAX_ULPS, (
            f"{c} moved by {u.max():.1f} ULPs — that is more than float summation order "
            f"can explain")


def test_new_builder_reproduces_the_legacy_values_on_every_historical_row(nb):
    """Executed proof, not an argument: both builders, same inputs, all 14 columns."""
    _, completed, _ = _future_split()
    pbp = _synth_pbp(completed)
    g = _g_from(completed)

    old = legacy_build_totals_features(g.copy(), completed, pbp, weather_path=WEATHER_CSV)
    new = nb["build_totals_features"](g.copy(), completed, pbp,
                                      weather_path=WEATHER_CSV, impute_missing=True)
    assert len(g) > 700, f"only {len(g)} historical rows compared"
    _assert_historically_identical(old, new)


def test_the_one_column_that_moved_moved_only_in_the_last_bit(nb):
    """Pin the exact measured discrepancy so it cannot silently grow."""
    _, completed, _ = _future_split()
    pbp = _synth_pbp(completed)
    g = _g_from(completed)
    old = legacy_build_totals_features(g.copy(), completed, pbp, weather_path=WEATHER_CSV)
    new = nb["build_totals_features"](g.copy(), completed, pbp,
                                      weather_path=WEATHER_CSV, impute_missing=True)
    a = old["league_avg_total_4wk"].to_numpy(dtype="float64")
    b = new["league_avg_total_4wk"].to_numpy(dtype="float64")
    d = np.abs(a - b)
    assert np.nanmax(d) < 1e-13, f"max abs difference {np.nanmax(d):.3e} is not float noise"
    assert np.nanmax(d / np.abs(a)) < 1e-15
    assert _ulps(a, b).max() <= 1


def test_historical_equivalence_also_holds_without_a_weather_file(nb):
    _, completed, _ = _future_split()
    pbp = _synth_pbp(completed)
    g = _g_from(completed)
    old = legacy_build_totals_features(g.copy(), completed, pbp, weather_path=None)
    new = nb["build_totals_features"](g.copy(), completed, pbp,
                                      weather_path=None, impute_missing=True)
    _assert_historically_identical(old, new)


def test_the_historical_fixture_actually_exercises_the_hard_rows(nb):
    """A green equivalence test over trivial data proves nothing — pin what it covered."""
    _, completed, _ = _future_split()
    out = nb["build_totals_features"](_g_from(completed).copy(), completed,
                                      _synth_pbp(completed), weather_path=WEATHER_CSV,
                                      impute_missing=False)
    assert len(out) > 400, f"only {len(out)} historical rows compared"
    first = out[out["week"] == 1]
    assert len(first) > 20 and first["home_pts_scored_5g"].isna().any(), \
        "no season-opening row with no prior history was exercised"
    assert out["is_dome"].nunique() == 2, "fixture has no dome/outdoor contrast"
    assert (out["temp_f_source"] == "weather_file").any()
    assert (out["temp_f_source"] == "default_outdoor").any()
    assert (out["temp_f_source"] == "dome_neutralized").any()


# ── 2. THE DEFECT, AND THAT THE NEW WIRING FIXES IT ───────────────────────────────────
def test_red_the_legacy_builder_leaves_the_future_slate_empty():
    """Red proof of the reported defect, on the real future slate.

    The legacy builder with the completed-games-only `sched` the live notebook used to pass:
    every rolling feature comes back NaN, which the notebook's blanket .fillna(0) then turned
    into 0.0. is_dome comes back 0 because the roof string was not there to merge.
    """
    sched, completed, fut_ids = _future_split()
    pbp = _synth_pbp(completed)
    g = _g_from(sched, fut_ids)
    g["home_score"] = np.nan  # the live path carries (empty) score columns
    g["away_score"] = np.nan
    out = legacy_build_totals_features(g.copy(), completed, pbp, weather_path=WEATHER_CSV)

    broken = [c for c in TOTALS_FEATURE_COLS_EXPECTED if out[c].isna().all()]
    assert set(broken) >= {"home_pts_scored_5g", "home_pts_allowed_5g", "away_pts_scored_5g",
                           "away_pts_allowed_5g", "combined_pts_5g",
                           "league_avg_total_4wk", "pace_5g"}, broken
    assert (out["is_dome"] == 0).all(), "expected the legacy is_dome to be silently 0"
    zeroed = out[TOTALS_FEATURE_COLS_EXPECTED].fillna(0)
    assert int((zeroed == 0).all().sum()) >= 8, \
        "expected the blanket fillna(0) to zero out most of the totals block"


def test_live_smoke_a_future_game_gets_real_features(nb):
    """The fix: real, varying, correctly-roofed features for games that have not kicked off."""
    sched, completed, fut_ids = _future_split()
    pbp = _synth_pbp(completed)
    g = _g_from(sched, fut_ids)
    out = nb["build_totals_features"](g.copy(), sched, pbp,
                                      weather_path=WEATHER_CSV, impute_missing=False)

    assert len(out) == len(fut_ids)
    assert not out[TOTALS_FEATURE_COLS_EXPECTED].isna().any().any(), \
        out[TOTALS_FEATURE_COLS_EXPECTED].isna().sum().to_dict()
    for c in MUST_VARY_COLS + ["league_avg_total_4wk", "total_line"]:
        assert (out[c] > 0).all(), f"{c} contains a non-positive value"
    for c in MUST_VARY_COLS:
        assert out[c].nunique() > 1, f"{c} is constant across the future slate"

    # is_dome must equal the REAL roof string of the real games, not a default.
    roof = sched.set_index("game_id")["roof"]
    expected = out["game_id"].map(roof).isin(["dome", "closed"]).astype(int)
    assert (out["is_dome"].astype(int).to_numpy() == expected.to_numpy()).all()
    assert 0 < int(out["is_dome"].sum()) < len(out), \
        "future slate must contain both dome and non-dome games for this to mean anything"
    assert (out.loc[out["is_dome"] == 1, "wind_mph"] == 0).all()
    assert (out.loc[out["is_dome"] == 1, "temp_f"] == 70).all()


def test_future_features_equal_what_the_team_actually_did_beforehand(nb):
    """Spot-check the as-of value against a hand-computed strictly-prior mean."""
    sched, completed, fut_ids = _future_split()
    out = nb["build_totals_features"](_g_from(sched, fut_ids).copy(), sched,
                                      _synth_pbp(completed), weather_path=WEATHER_CSV,
                                      impute_missing=False)
    row = out.iloc[0]
    team = row["home_team"]
    prior = completed[((completed["home_team"] == team) | (completed["away_team"] == team))
                      & (completed["season"] * 100 + completed["week"]
                         < FUTURE_SEASON * 100 + FUTURE_WEEK)].sort_values(["season", "week"])
    scored = np.where(prior["home_team"] == team, prior["home_score"], prior["away_score"])
    assert row["home_pts_scored_5g"] == pytest.approx(float(np.mean(scored[-5:])))


# ── 3. TARGET-OUTCOME MUTATION INVARIANCE ─────────────────────────────────────────────
@pytest.mark.parametrize("scenario", ["future", "historical"])
def test_mutating_the_target_games_outcome_changes_no_pregame_feature(nb, scenario):
    """A pregame feature that moves when the target's own score moves is leakage."""
    sched, completed, fut_ids = _future_split()
    if scenario == "future":
        targets, hist_sched = fut_ids, sched
    else:
        targets = list(completed.loc[(completed["season"] == 2020)
                                     & (completed["week"] == 12), "game_id"])
        assert targets, "no historical target games selected"
        hist_sched = sched

    pbp = _synth_pbp(completed)
    g = _g_from(sched, targets)
    base = nb["build_totals_features"](g.copy(), hist_sched.copy(), pbp,
                                       weather_path=WEATHER_CSV, impute_missing=False)

    mutated = hist_sched.copy()
    hit = mutated["game_id"].isin(targets)
    assert hit.sum() == len(targets)
    mutated.loc[hit, "home_score"] = 73.0    # absurd on purpose
    mutated.loc[hit, "away_score"] = 0.0
    mutated.loc[hit, "result"] = 73.0
    after = nb["build_totals_features"](g.copy(), mutated, pbp,
                                        weather_path=WEATHER_CSV, impute_missing=False)

    diffs = _cmp(base, after, TOTALS_FEATURE_COLS_EXPECTED)
    assert not diffs, f"pregame features moved with the target outcome ({scenario}): {diffs}"


# ── 4. THE PREFLIGHT FAILS CLOSED ─────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def live_features(nb):
    sched, completed, fut_ids = _future_split()
    return nb["build_totals_features"](_g_from(sched, fut_ids).copy(), sched,
                                       _synth_pbp(completed), weather_path=WEATHER_CSV,
                                       impute_missing=False)


def test_preflight_passes_on_the_real_future_slate(live_features):
    rep = totals_live_preflight(live_features)
    assert rep["ok"] is True and rep["n_failed"] == 0
    assert rep["n_checks"] >= 10
    assert rep["n_games"] == len(live_features)


def test_preflight_returns_a_report_it_does_not_only_print(live_features, capsys):
    rep = totals_live_preflight(live_features)
    assert isinstance(rep, dict) and set(rep) >= {"ok", "checks", "failures", "n_failed"}
    assert capsys.readouterr().out == "", "the preflight must not communicate by printing"


def test_red_preflight_aborts_on_an_all_zero_slate(live_features):
    """The exact shipped-defect state: the blanket fillna(0) output."""
    bad = live_features.copy()
    bad[TOTALS_FEATURE_COLS_EXPECTED] = 0.0
    with pytest.raises(TotalsPreflightError) as e:
        totals_live_preflight(bad)
    assert "no_zero_or_negative_scoring_features" in str(e.value)


def test_red_preflight_aborts_on_a_constant_slate(live_features):
    """Mean-imputation over an all-NaN column: plausible values, identical everywhere."""
    bad = live_features.copy()
    for c in MUST_VARY_COLS:
        bad[c] = float(bad[c].mean())
    with pytest.raises(TotalsPreflightError) as e:
        totals_live_preflight(bad)
    assert "rolling_features_vary_across_slate" in str(e.value)


def test_red_preflight_aborts_on_nan_missing_column_and_bad_types(live_features):
    for mutate, expect in [
        (lambda d: d.assign(pace_5g=np.nan), "no_missing_values"),
        (lambda d: d.drop(columns=["is_dome"]), "required_columns_present"),
        (lambda d: d.assign(is_dome=2), "binary_flags_are_binary"),
        (lambda d: d.assign(league_avg_total_4wk=500.0), "values_in_sane_range"),
        (lambda d: d.drop(columns=WEATHER_SOURCE_COLS), "weather_provenance_recorded"),
        (lambda d: d.assign(temp_f_source="guessed"), "weather_provenance_recorded"),
        (lambda d: d.iloc[0:0], "non_empty"),
    ]:
        with pytest.raises(TotalsPreflightError) as e:
            totals_live_preflight(mutate(live_features.copy()))
        assert expect in str(e.value), f"expected {expect}, got {e.value}"


def test_red_preflight_aborts_on_a_default_dominated_slate(live_features):
    bad = live_features.copy()
    assert len(bad) >= 4
    for c in MUST_VARY_COLS:
        v = bad[c].to_numpy(dtype="float64").copy()
        v[: len(v) - 1] = v[0]        # one modal value, one dissenter -> not constant
        bad[c] = v
    with pytest.raises(TotalsPreflightError) as e:
        totals_live_preflight(bad)
    assert "no_default_dominated_feature" in str(e.value)


def test_preflight_cannot_be_talked_out_of_a_check(live_features):
    """No caller-supplied vocabulary: strict_weather can only ADD a requirement."""
    import inspect

    import totals_asof
    params = inspect.signature(totals_asof.totals_live_preflight).parameters
    assert set(params) == {"features_df", "strict_weather"}, \
        f"preflight grew a caller-controlled parameter: {list(params)}"
    bad = live_features.copy()
    bad[TOTALS_FEATURE_COLS_EXPECTED] = 0.0
    with pytest.raises(TotalsPreflightError):
        totals_live_preflight(bad, strict_weather=False)
    with pytest.raises(TotalsPreflightError):
        totals_live_preflight(bad, strict_weather=True)


def test_strict_weather_flags_a_defaulted_slate(live_features):
    assert totals_live_preflight(live_features)["ok"] is True
    share = (live_features["temp_f_source"] == "default_outdoor").mean()
    if share > 0.5:
        with pytest.raises(TotalsPreflightError) as e:
            totals_live_preflight(live_features, strict_weather=True)
        assert "weather_not_default_dominated" in str(e.value)
    else:
        assert totals_live_preflight(live_features, strict_weather=True)["ok"] is True


# ── 5. WEATHER SEMANTICS ──────────────────────────────────────────────────────────────
def test_weather_provenance_is_recorded_for_every_row(nb, live_features):
    from totals_asof import WEATHER_SOURCES
    for c in WEATHER_SOURCE_COLS:
        assert live_features[c].notna().all()
        assert set(live_features[c]).issubset(set(WEATHER_SOURCES))
    dome = live_features["is_dome"] == 1
    assert (live_features.loc[dome, "temp_f_source"] == "dome_neutralized").all()
    assert (live_features.loc[~dome, "temp_f_source"] == "default_outdoor").all(), \
        "the future slate has no retained weather, so outdoor rows must say so"


def test_the_documented_fallback_constants_are_what_gets_written(nb):
    from totals_asof import TEMP_FALLBACK_F, WIND_FALLBACK_MPH
    sched, completed, fut_ids = _future_split()
    out = nb["build_totals_features"](_g_from(sched, fut_ids).copy(), sched,
                                      _synth_pbp(completed), weather_path=WEATHER_CSV,
                                      impute_missing=False)
    outdoor = out[out["is_dome"] == 0]
    assert len(outdoor) > 0
    assert (outdoor["temp_f"] == TEMP_FALLBACK_F).all()
    assert (outdoor["wind_mph"] == WIND_FALLBACK_MPH).all()


def test_live_mode_never_substitutes_a_zero_or_a_slate_mean(nb):
    """Live mode leaves a hole as a hole. Week 1 of the fixture's first season has no prior
    history at all, so the honest answer is NaN — and the preflight then aborts."""
    s = _schedule()
    first = s[(s["season"] == 2016) & (s["week"] == 1)]
    out = nb["build_totals_features"](_g_from(s, list(first["game_id"])).copy(), s,
                                      _synth_pbp(s), weather_path=WEATHER_CSV,
                                      impute_missing=False)
    assert out["home_pts_scored_5g"].isna().all(), "week 1 of the first season is not knowable"
    assert not (out["home_pts_scored_5g"] == 0).any(), "a zero was substituted"
    assert "slate_mean" not in set(out["temp_f_source"])
    with pytest.raises(TotalsPreflightError):
        totals_live_preflight(out)


# ── 6. THE NOTEBOOK SURFACE ITSELF ────────────────────────────────────────────────────
def test_notebook_feature_list_is_pinned_to_the_preflights_copy(nb):
    assert nb["TOTALS_FEATURE_COLS"] == TOTALS_FEATURE_COLS_EXPECTED
    assert len(nb["TOTALS_FEATURE_COLS"]) == 14


def test_builder_refuses_a_schedule_without_roof_or_an_unkeyed_g(nb):
    sched, completed, fut_ids = _future_split()
    pbp = _synth_pbp(completed)
    with pytest.raises(AssertionError, match="roof"):
        nb["build_totals_features"](_g_from(sched, fut_ids), sched.drop(columns=["roof"]), pbp)
    g = _g_from(sched, fut_ids)
    g.loc[0, "week"] = np.nan
    with pytest.raises(AssertionError, match="as-of key"):
        nb["build_totals_features"](g, sched, pbp)


def _run_inference_cell(nb_ns, game_rows):
    """Execute `predict_totals.ipynb`'s inference cell against stub models.

    Grepping the notebook proves the text changed; running the cell proves it works. No
    real model is loaded and nothing is written anywhere — the cell only builds `X_live`
    and the tier list.
    """
    import features as prod_features

    cells = json.loads((_BETTING / "predict_totals.ipynb").read_text(encoding="utf-8"))["cells"]
    src = "".join(cells[12]["source"])
    assert "totals_live_preflight" in src, "cell 12 is not the inference cell any more"

    prod = list(prod_features.PROD_FEATURES_35)
    rows = game_rows.copy()
    rng = np.random.default_rng(1)
    for c in prod:
        rows[c] = rng.normal(size=len(rows))

    class _Stub:
        def predict(self, X):
            return np.linspace(-3.0, 3.0, len(X))

    class _Scaler:
        def transform(self, X):
            return X

    ns = {
        "game_rows": rows, "pd": pd, "np": np,
        "PROD_FEATURES_35": prod,
        "TOTALS_FEATURE_COLS": nb_ns["TOTALS_FEATURE_COLS"],
        "TOTALS_ALL_COLS": prod + nb_ns["TOTALS_FEATURE_COLS"],
        "totals_live_preflight": nb_ns["totals_live_preflight"],
        "xgb_totals": _Stub(), "ridge_totals": _Stub(), "scaler_totals": _Scaler(),
    }
    exec(src, ns)  # noqa: S102
    return ns


def test_the_inference_cell_runs_on_a_real_future_slate(nb, live_features):
    ns = _run_inference_cell(nb, live_features)
    X = ns["X_live"]
    assert X.shape == (len(live_features), 49) and X.dtype == np.float32
    assert not np.isnan(X).any(), "X_live still contains NaN"
    tail = X[:, -14:]
    assert not (tail == 0).all(axis=0).any(), "a totals feature column is entirely zero"
    assert set(ns["tiers"]) <= {"HIGH", "PASS"}


def test_red_the_inference_cell_refuses_the_pre_fix_zero_vector(nb, live_features):
    broken = live_features.copy()
    broken[nb["TOTALS_FEATURE_COLS"]] = 0.0
    with pytest.raises(TotalsPreflightError):
        _run_inference_cell(nb, broken)


def test_predict_totals_calls_the_builder_with_the_full_schedule_and_preflights():
    """The call site is half the fix; a green builder with a broken caller ships the bug."""
    src = json.dumps(json.loads(
        (_BETTING / "predict_totals.ipynb").read_text(encoding="utf-8")))
    assert "game_rows, full_schedule, pbp_full_live" in src, \
        "predict_totals must pass the COMPLETE schedule, not coach_hist_df"
    assert "coach_hist_df, pbp_full_live" not in src
    assert "impute_missing=False" in src
    assert "totals_live_preflight(game_rows)" in src
    assert "game_rows[TOTALS_ALL_COLS].fillna(0)" not in src, \
        "the blanket zero-fill over the totals block is back"
