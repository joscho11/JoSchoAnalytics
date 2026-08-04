"""v3.9x — the canonical panel-key contract, and the adapter defect that stopped the first real run.

WHAT FAILED. The authorized real run cleared both gates, read both pinned snapshots, and then died in
the adapter with:

    AssemblyError: adapter: the join reordered the feature rows

**The rows were not reordered.** Measured on the real frames: 7,153 rows in, 7,153 out, every key value
in the identical position. The feature reader emitted `player_id` as pandas `string[python]`; the
outcome reader emitted it as numpy `object`; the left merge resolved the key to `object`; and the
assertion used `DataFrame.equals`, which compares DTYPES as well as values. A pure dtype disagreement
between the two readers was reported as a row-ordering failure.

WHY NO TEST CAUGHT IT. Every test that reached the adapter built both sides from ONE frame, so the two
readers' key dtypes were never contrasted — including the v3.9w end-to-end test, whose synthetic
outcome was derived from the feature frame's own keys and therefore inherited `string` on both sides.

THE REPAIR IS A CONTRACT, NOT A RELAXATION. One canonical key schema, enforced at BOTH real reader
boundaries so the sides cannot disagree; a defensive assertion in `assemble_panel_core` for injected
frames; and dtype and ordering checked SEPARATELY in the adapter so each failure is named accurately.

NOTHING HERE READS THE CANONICAL WEEKLY OUTCOME SNAPSHOT. Every frame below is synthetic or a
purpose-built temporary parquet.
"""
import pathlib
import sys

import numpy as np
import pandas as pd
import pytest

HERE = pathlib.Path(__file__).resolve().parent
COACH = HERE.parent
if str(COACH) not in sys.path:
    sys.path.insert(0, str(COACH))

import assemble_real_panel_v39 as ARP                     # noqa: E402

KEYS = list(ARP.PANEL_KEYS)
STR = pd.StringDtype(storage="python")


def _ids(n, start=0):
    return [f"00-00{i:05d}" for i in range(start, start + n)]


def _features(n=6, id_dtype=STR, season_dtype=np.int32, ids=None, seasons=None):
    ids = _ids(n) if ids is None else ids
    seasons = list(range(2018, 2018 + len(ids))) if seasons is None else seasons
    return pd.DataFrame({
        ARP.PLAYER_KEY: pd.array(ids, dtype=id_dtype) if isinstance(id_dtype, pd.StringDtype)
        else np.array(ids, dtype=id_dtype),
        ARP.SEASON_KEY: np.array(seasons, dtype=season_dtype),
    })


def _outcomes(features, id_dtype=object, season_dtype=np.int32):
    ids = list(features[ARP.PLAYER_KEY].astype(object))
    seasons = list(features[ARP.SEASON_KEY])
    return pd.DataFrame({
        ARP.PLAYER_KEY: pd.array(ids, dtype=id_dtype) if isinstance(id_dtype, pd.StringDtype)
        else np.array(ids, dtype=id_dtype),
        ARP.SEASON_KEY: np.array(seasons, dtype=season_dtype),
        ARP.OUTCOME_COLUMN: np.arange(len(ids), dtype=float),
    })


def _contract_features(id_dtype=STR, per_season=2):
    """A SYNTHETIC feature frame satisfying the frozen VETERAN contract exactly.

    `validate_feature_frame` demands the 40 frozen columns in order and every panel season present,
    so the key-contract tests that run through `assemble_panel_core` / `panel_for_experiment` need a
    schema-complete frame. Values are arbitrary; only the keys and the schema matter here.
    """
    seasons = list(ARP.ALL_PANEL_SEASONS)
    rows = [(f"00-00{i:05d}", s) for s in seasons for i in range(per_season)]
    ids = [r[0] for r in rows]
    frame = pd.DataFrame({
        ARP.PLAYER_KEY: (pd.array(ids, dtype=id_dtype) if isinstance(id_dtype, pd.StringDtype)
                         else np.array(ids, dtype=id_dtype)),
        ARP.SEASON_KEY: np.array([r[1] for r in rows], dtype=np.int32),
    })
    for col in ARP.FROZEN_FEATURE_COLUMNS:
        if col in (ARP.PLAYER_KEY, ARP.SEASON_KEY):
            continue
        if col in ("player", "norm_name"):
            frame[col] = [f"player {i}" for i in range(len(frame))]
        elif col == "position":
            frame[col] = ["TE"] * len(frame)
        elif col == "team":
            frame[col] = ["ARI"] * len(frame)
        elif col in ("reconstructed", "is_rookie", "coach_changed", "qb_changed",
                     "missed_prior_season"):
            frame[col] = np.zeros(len(frame), dtype=np.int64)
        else:
            frame[col] = np.linspace(0.0, 1.0, len(frame))
    return frame[list(ARP.FROZEN_FEATURE_COLUMNS)]


# =====================================================================================================
# 1. the contract itself
# =====================================================================================================
def test_the_canonical_key_dtypes_are_frozen():
    assert ARP.PANEL_KEY_DTYPES == {ARP.PLAYER_KEY: pd.StringDtype(storage="python"),
                                    ARP.SEASON_KEY: np.dtype("int32")}
    assert ARP.PANEL_KEY_DTYPES[ARP.PLAYER_KEY].storage == "python"


def test_canonicalization_produces_the_contract_from_the_object_shape():
    got = ARP.canonicalize_panel_keys(_features(id_dtype=object), "probe")
    assert got[ARP.PLAYER_KEY].dtype == STR
    assert got[ARP.SEASON_KEY].dtype == np.dtype("int32")
    assert ARP.canonical_key_dtype_problems(got, "probe") == []


def test_canonicalization_is_idempotent_and_preserves_values_and_order():
    src = _features(id_dtype=object, season_dtype="int64")
    once = ARP.canonicalize_panel_keys(src, "p")
    twice = ARP.canonicalize_panel_keys(once, "p")
    assert np.array_equal(ARP.ordered_key_values(once), ARP.ordered_key_values(twice))
    assert np.array_equal(ARP.ordered_key_values(once), ARP.ordered_key_values(src))


def test_dtype_problems_names_the_column_and_both_dtypes():
    problems = ARP.canonical_key_dtype_problems(_features(id_dtype=object), "here")
    assert len(problems) == 1
    assert ARP.PLAYER_KEY in problems[0] and "here" in problems[0]
    assert "string" in problems[0]


# =====================================================================================================
# 2. rejections — never coerced, never manufactured
# =====================================================================================================
@pytest.mark.parametrize("label,ids", [
    ("null", np.array(["00-0000001", None], dtype=object)),
    ("nan float", np.array(["00-0000001", np.nan], dtype=object)),
    ("stringified nan", ["00-0000001", "nan"]),
    ("stringified None", ["00-0000001", "None"]),
    ("stringified NA", ["00-0000001", "<NA>"]),
    ("empty", ["00-0000001", ""]),
    ("whitespace", ["00-0000001", "   "]),
])
def test_null_and_stringified_null_player_ids_are_REFUSED(label, ids):
    with pytest.raises(ARP.AssemblyError) as e:
        ARP.canonicalize_panel_keys(_features(ids=list(ids), id_dtype=object), "probe")
    assert ARP.PLAYER_KEY in str(e.value)


@pytest.mark.parametrize("ids", [[1, 2], [1.0, 2.0], [True, False]])
def test_numeric_player_ids_are_REFUSED_not_stringified(ids):
    """`astype(str)` would happily turn 1 into '1' and a null into 'nan'. Both are fabricated identity."""
    frame = pd.DataFrame({ARP.PLAYER_KEY: ids, ARP.SEASON_KEY: np.array([2018, 2019], dtype=np.int32)})
    with pytest.raises(ARP.AssemblyError) as e:
        ARP.canonicalize_panel_keys(frame, "probe")
    assert "not textual" in str(e.value)


def test_the_module_does_not_blindly_cast_the_player_key():
    """No EXECUTABLE blind string cast anywhere in the assembly module.

    Checked over the AST, not the text: the prose above and the module's own comments legitimately
    NAME the banned call while explaining why it is banned, and a substring scan would match those.
    The needle is assembled at runtime so this test cannot match itself either.
    """
    import ast
    needle = "as" + "type"
    tree = ast.parse((COACH / "assemble_real_panel_v39.py").read_text(encoding="utf-8"))
    offenders = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
            continue
        if node.func.attr != needle or not node.args:
            continue
        arg = node.args[0]
        if (isinstance(arg, ast.Name) and arg.id == "str") or            (isinstance(arg, ast.Constant) and arg.value == "str"):
            offenders.append(node.lineno)
    assert not offenders, (f"blind string cast(s) at line(s) {offenders}: this turns a null into "
                           f"the textual identity 'nan'")


@pytest.mark.parametrize("label,seasons", [
    ("fractional", [2018.5, 2019.0]),
    ("tiny fraction", [2018.0000001, 2019.0]),
    ("below range", [1800, 2019]),
    ("overflowing int32", [2018, 2 ** 40]),
    ("negative", [-1, 2019]),
])
def test_bad_seasons_are_REFUSED(label, seasons):
    frame = pd.DataFrame({ARP.PLAYER_KEY: pd.array(_ids(2), dtype=STR),
                          ARP.SEASON_KEY: seasons})
    with pytest.raises(ARP.AssemblyError) as e:
        ARP.canonicalize_panel_keys(frame, "probe")
    assert ARP.SEASON_KEY in str(e.value)


@pytest.mark.parametrize("seasons", [[None, 2019], [np.nan, 2019]])
def test_null_seasons_are_REFUSED(seasons):
    frame = pd.DataFrame({ARP.PLAYER_KEY: pd.array(_ids(2), dtype=STR), ARP.SEASON_KEY: seasons})
    with pytest.raises(ARP.AssemblyError) as e:
        ARP.canonicalize_panel_keys(frame, "probe")
    assert "null" in str(e.value)


def test_nonnumeric_seasons_are_REFUSED():
    frame = pd.DataFrame({ARP.PLAYER_KEY: pd.array(_ids(2), dtype=STR),
                          ARP.SEASON_KEY: ["2018", "2019"]})
    with pytest.raises(ARP.AssemblyError) as e:
        ARP.canonicalize_panel_keys(frame, "probe")
    assert "numeric" in str(e.value)


def test_an_integral_float_season_IS_accepted_and_narrows_losslessly():
    got = ARP.canonicalize_panel_keys(
        pd.DataFrame({ARP.PLAYER_KEY: pd.array(_ids(2), dtype=STR),
                      ARP.SEASON_KEY: [2018.0, 2019.0]}), "probe")
    assert got[ARP.SEASON_KEY].tolist() == [2018, 2019]
    assert got[ARP.SEASON_KEY].dtype == np.dtype("int32")


def test_duplicate_keys_are_REFUSED():
    frame = pd.DataFrame({ARP.PLAYER_KEY: pd.array(["00-0000001"] * 2, dtype=STR),
                          ARP.SEASON_KEY: np.array([2018, 2018], dtype=np.int32)})
    with pytest.raises(ARP.AssemblyError) as e:
        ARP.canonicalize_panel_keys(frame, "probe")
    assert "duplicate" in str(e.value)


def test_a_missing_key_column_is_REFUSED():
    with pytest.raises(ARP.AssemblyError) as e:
        ARP.canonicalize_panel_keys(pd.DataFrame({ARP.SEASON_KEY: [2018]}), "probe")
    assert ARP.PLAYER_KEY in str(e.value)


# =====================================================================================================
# 3. THE EXACT REAL FAILURE SHAPE
# =====================================================================================================
def test_THE_REAL_FAILURE_SHAPE_string_features_vs_object_outcomes_is_reproduced_and_fixed():
    """string[python] features, object outcomes, identical values in identical order."""
    feats = _features(id_dtype=STR)
    outs = _outcomes(feats, id_dtype=object)
    assert feats[ARP.PLAYER_KEY].dtype == STR and outs[ARP.PLAYER_KEY].dtype == object

    # the historical assertion: values and order identical, yet `.equals` is False purely on dtype
    aligned = feats[KEYS].merge(outs, on=KEYS, how="left", validate="one_to_one")
    lhs = feats[KEYS].reset_index(drop=True)
    assert np.array_equal(ARP.ordered_key_values(lhs), ARP.ordered_key_values(aligned[KEYS]))
    assert aligned[KEYS].equals(lhs) is False, "this is the exact shape that killed the first run"

    # the contract removes the disagreement at the source
    canon = ARP.canonicalize_panel_keys(outs, "outcome")
    assert canon[ARP.PLAYER_KEY].dtype == feats[ARP.PLAYER_KEY].dtype
    assert ARP.canonical_key_dtype_problems(canon, "o") == []
    assert np.array_equal(ARP.ordered_key_values(canon[KEYS]), ARP.ordered_key_values(lhs))


def test_a_noncanonical_injected_frame_fails_on_DTYPE_not_on_ordering():
    """Same values, same order, wrong dtype: the message must say dtype, never 'reordered'."""
    feats = _contract_features(id_dtype=STR)
    outs = _outcomes(feats, id_dtype=object)
    with pytest.raises(ARP.AssemblyError) as e:
        ARP.assemble_panel_core(feats, outs)
    msg = str(e.value)
    assert "dtype" in msg and ARP.PLAYER_KEY in msg
    assert "reorder" not in msg.lower()


def test_canonical_reader_output_shapes_pass_assemble_panel_core():
    feats = ARP.canonicalize_panel_keys(_contract_features(id_dtype=object), "f")
    outs = ARP.canonicalize_panel_keys(_outcomes(feats, id_dtype=object), "o")
    core = ARP.assemble_panel_core(feats, outs)
    assert set(core) >= {"features", "outcomes", "accounting"}
    assert len(core["features"]) == len(feats)


# =====================================================================================================
# 4. the adapter distinguishes dtype from ordering
# =====================================================================================================
def _assembled(feats, outs):
    aligned = feats[KEYS].merge(outs, on=KEYS, how="left", validate="one_to_one")
    aligned["outcome_state"] = ARP.STATE_MATCHED
    return {"features": feats, "outcomes": aligned}


def _reordering_merge(monkeypatch, transform):
    """Force the alignment merge to return a REORDERED frame.

    A pandas LEFT merge preserves the left frame's order, so the adapter's ordering branch cannot be
    reached by any arrangement of the inputs — it is a guard against a future change in that
    guarantee. Reaching it therefore requires FAULT INJECTION, and saying so is the point: without
    this the ordering assertion would be permanently vacuous and no test would notice.
    """
    real_merge = pd.DataFrame.merge

    def patched(self, right, *a, **k):
        out = real_merge(self, right, *a, **k)
        if ARP.OUTCOME_COLUMN in getattr(right, "columns", []):
            return transform(out)
        return out

    monkeypatch.setattr(pd.DataFrame, "merge", patched, raising=True)


def test_ACTUAL_reordering_is_still_reported_as_reordering(monkeypatch):
    feats = ARP.canonicalize_panel_keys(_contract_features(id_dtype=object), "f")
    outs = ARP.canonicalize_panel_keys(_outcomes(feats, id_dtype=object), "o")
    assembled = _assembled(feats, outs)
    _reordering_merge(monkeypatch, lambda d: d.iloc[::-1].reset_index(drop=True))
    with pytest.raises(ARP.AssemblyError) as e:
        ARP.panel_for_experiment(assembled, require_bucket_coverage=False)
    assert "reordered" in str(e.value)


def test_the_reordering_message_names_the_first_moved_position(monkeypatch):
    feats = ARP.canonicalize_panel_keys(_contract_features(id_dtype=object), "f")
    outs = ARP.canonicalize_panel_keys(_outcomes(feats, id_dtype=object), "o")
    assembled = _assembled(feats, outs)

    def swap_2_and_3(d):
        out = d.copy()
        out.iloc[[2, 3]] = out.iloc[[3, 2]].to_numpy()
        return out

    _reordering_merge(monkeypatch, swap_2_and_3)
    with pytest.raises(ARP.AssemblyError) as e:
        ARP.panel_for_experiment(assembled, require_bucket_coverage=False)
    msg = str(e.value)
    assert "reordered" in msg and "position 2" in msg


def test_the_ordering_comparison_ignores_dtype_and_only_sees_moved_VALUES():
    """The comparison primitive itself: same values in different containers are EQUAL."""
    a = _features(id_dtype=STR)
    b = _features(id_dtype=object)
    assert np.array_equal(ARP.ordered_key_values(a), ARP.ordered_key_values(b))
    assert not np.array_equal(ARP.ordered_key_values(a),
                              ARP.ordered_key_values(a.iloc[::-1].reset_index(drop=True)))


def test_the_adapter_reports_a_dtype_violation_as_a_dtype_violation():
    feats = ARP.canonicalize_panel_keys(_contract_features(id_dtype=object), "f")
    outs = ARP.canonicalize_panel_keys(_outcomes(feats, id_dtype=object), "o")
    assembled = _assembled(feats, outs)
    assembled["features"] = assembled["features"].astype({ARP.PLAYER_KEY: object})
    with pytest.raises(ARP.AssemblyError) as e:
        ARP.panel_for_experiment(assembled, require_bucket_coverage=False)
    msg = str(e.value)
    assert "DTYPE failure" in msg and "not a row-ordering failure" in msg


def test_missing_extra_and_duplicate_keys_still_fail_in_the_adapter():
    feats = ARP.canonicalize_panel_keys(_contract_features(id_dtype=object), "f")
    outs = ARP.canonicalize_panel_keys(_outcomes(feats, id_dtype=object), "o")

    short = _assembled(feats, outs)
    short["outcomes"] = short["outcomes"].iloc[:3].reset_index(drop=True)
    with pytest.raises(ARP.AssemblyError) as e:
        ARP.panel_for_experiment(short, require_bucket_coverage=False)
    assert "row count" in str(e.value) or "no outcome key" in str(e.value)

    dup = _assembled(feats, outs)
    dup["outcomes"] = pd.concat([dup["outcomes"], dup["outcomes"].iloc[[0]]], ignore_index=True)
    with pytest.raises(ARP.AssemblyError) as e:
        ARP.panel_for_experiment(dup, require_bucket_coverage=False)
    assert "duplicate" in str(e.value)


# =====================================================================================================
# 5. both REAL reader boundaries emit the contract — exercised on synthetic parquets
# =====================================================================================================
def test_the_grouped_outcome_reader_emits_the_canonical_key_dtypes():
    """`grouped_season_totals` on a synthetic weekly frame — the canonical snapshot is NOT read."""
    weekly = pd.DataFrame({
        ARP.PLAYER_KEY: np.array(_ids(3) * 2, dtype=object),      # object, as the parquet carries it
        ARP.SEASON_KEY: np.array([2018] * 3 + [2019] * 3, dtype="int64"),
        "season_type": ["REG"] * 6,
        "fantasy_points": [10.0, 20.0, 30.0, 11.0, 21.0, 31.0],
        "receptions": [2, 4, 6, 3, 5, 7],
    })
    out = ARP.grouped_season_totals(weekly, seasons=[2018, 2019])
    assert ARP.canonical_key_dtype_problems(out, "outcome reader") == []
    assert out[ARP.PLAYER_KEY].dtype == STR and out[ARP.SEASON_KEY].dtype == np.dtype("int32")
    # groupby sorts player-major, then season
    assert out[ARP.OUTCOME_COLUMN].tolist() == [11.0, 12.5, 22.0, 23.5, 33.0, 34.5]


def test_the_outcome_reader_REG_filter_and_formula_are_unchanged():
    weekly = pd.DataFrame({
        ARP.PLAYER_KEY: np.array(_ids(1) * 2, dtype=object),
        ARP.SEASON_KEY: np.array([2018, 2018], dtype="int64"),
        "season_type": ["REG", "POST"],
        "fantasy_points": [10.0, 99.0],
        "receptions": [2, 9],
    })
    out = ARP.grouped_season_totals(weekly, seasons=[2018])
    assert out[ARP.OUTCOME_COLUMN].tolist() == [11.0], "POSTSEASON must not enter the target"


def test_reader_to_core_to_adapter_reaches_an_aligned_panel_without_the_real_snapshot(tmp_path):
    """End to end through the REAL `grouped_season_totals` and `assemble_panel_core`, on temp parquets.

    Both parquets carry `player_id` as `object` — the disagreement that broke the run reaches this
    path — and an aligned panel still results, because each boundary canonicalizes.
    """
    feats_src = _contract_features(id_dtype=object)
    ids = list(feats_src[ARP.PLAYER_KEY])
    seasons = list(feats_src[ARP.SEASON_KEY])

    weekly = pd.DataFrame({
        ARP.PLAYER_KEY: np.array(ids, dtype=object),
        ARP.SEASON_KEY: np.array(seasons, dtype="int64"),
        "season_type": ["REG"] * len(ids),
        "fantasy_points": np.arange(len(ids), dtype=float) * 2.0,
        "receptions": np.arange(len(ids)) % 5,
    })
    wpath, fpath = tmp_path / "synthetic_weekly.parquet", tmp_path / "synthetic_features.parquet"
    weekly.to_parquet(wpath)
    feats_src.to_parquet(fpath)

    outs = ARP.grouped_season_totals(pd.read_parquet(wpath), seasons=sorted(set(seasons)))
    feats = ARP.canonicalize_panel_keys(pd.read_parquet(fpath), "synthetic feature reader")
    assert ARP.canonical_key_dtype_problems(feats, "f") == []
    assert ARP.canonical_key_dtype_problems(outs, "o") == []

    core = ARP.assemble_panel_core(feats, outs)
    aligned = core["outcomes"]
    assert len(aligned) == len(feats)
    assert np.array_equal(ARP.ordered_key_values(aligned[KEYS]), ARP.ordered_key_values(feats[KEYS]))
    assert (aligned["outcome_state"] == ARP.STATE_MATCHED).all()
    assert aligned[ARP.OUTCOME_COLUMN].notna().all()


def test_the_canonical_weekly_snapshot_is_NOT_read_by_this_module():
    """This module must never touch the real outcome snapshot; the repair was chosen blind to it.

    The needles are assembled at runtime. Spelling them literally would make this test match its own
    source — the self-reference defect this project has hit before — and the fix is to break the
    literal, never to weaken the check.
    """
    src = pathlib.Path(__file__).read_text(encoding="utf-8")
    for needle in ("authorized_" + "outcome_reader", "WEEKLY_" + "SNAPSHOT",
                   "player_stats_" + "2011_2025"):
        assert needle not in src, f"this module must not reference {needle}"
