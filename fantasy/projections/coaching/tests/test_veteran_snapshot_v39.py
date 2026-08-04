"""The frozen Arm 0 VETERAN feature snapshot — scope, immutability, and 2026-independence.

WHY IT EXISTS. The experiment used to pin `season_dataset_2014_2026.csv` by whole-file md5. That file
is LIVE: it carries deploy-season 2026, which is refreshed as the season evolves. On 2026-08-03 a
concurrent session populated `qb_changed` for 916 rows of 2026 and the md5 moved, refusing activation
for a reason that had nothing to do with the experiment's inputs.

Measured, and re-measured here rather than asserted:
  * every difference confined to season 2026;
  * nine columns differed only by CSV float round-trip noise, max |diff| 3.5527e-15, no null flips;
  * the one substantive change was `qb_changed` on 916 rows of 2026;
  * NO 2014-2025 value differed, bitwise, in any of the 47 columns.

The consumed window is now an immutable snapshot. These tests pin that it is feature-only, that it
equals the source's 2014-2025 consumed values, that 2026 cannot reach it, and that any 2014-2025
mutation would be caught.

No fantasy outcome is read anywhere here. The snapshot carries none by construction, and several
tests exist precisely to prove that.
"""
import hashlib
import importlib.util
import json
import pathlib
import sys

import numpy as np
import pandas as pd
import pytest

COACH = pathlib.Path(__file__).resolve().parent.parent
REPO = COACH.parent.parent.parent
SEAS = REPO / "fantasy" / "seasonal_projections"
sys.path.insert(0, str(COACH))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import arm0_bundle_pins as PINS                            # noqa: E402
import assemble_real_panel_v39 as ARP                      # noqa: E402
import run_coach_projection_experiment_v39 as EX           # noqa: E402

GENERATOR = REPO / ARP.VETERAN_SNAPSHOT_GENERATOR
SOURCE = SEAS / "season_dataset_2014_2026.csv"
PRE_REFRESH = SEAS / "season_dataset_2014_2026.pre_qbchanged.csv"

# Independently pinned here, not imported from the module under test.
EXPECTED_ROWS = 7350
EXPECTED_COLS = 40
EXPECTED_SEASONS = tuple(range(2014, 2026))


def _generator():
    spec = importlib.util.spec_from_file_location("build_veteran_arm0_snapshot_under_test", GENERATOR)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def snap():
    return pd.read_parquet(ARP.VETERAN_SNAPSHOT)


@pytest.fixture(scope="module")
def source_window():
    """The source's 2014-2025 consumed block, read with the SAME explicit column list."""
    df = pd.read_csv(SOURCE, usecols=list(ARP.VETERAN_FEATURE_COLUMNS))
    df = df[df[ARP.SEASON_KEY].isin(EXPECTED_SEASONS)]
    return df.sort_values([ARP.SEASON_KEY, ARP.PLAYER_KEY],
                          kind="mergesort").reset_index(drop=True)[list(ARP.VETERAN_FEATURE_COLUMNS)]


# =====================================================================================================
# Seasons, keys, population, ordered schema
# =====================================================================================================
def test_the_snapshot_verifies_clean():
    entry = ARP.verify_veteran_snapshot_provenance()
    assert entry["sha256"] == ARP.VETERAN_SNAPSHOT_SHA256
    assert hashlib.sha256(ARP.VETERAN_SNAPSHOT.read_bytes()).hexdigest() == entry["sha256"]


def test_exact_seasons_keys_and_population(snap):
    assert len(snap) == EXPECTED_ROWS == ARP.VETERAN_SNAPSHOT_ROWS
    assert sorted(int(s) for s in snap[ARP.SEASON_KEY].unique()) == list(EXPECTED_SEASONS)
    assert 2026 not in set(snap[ARP.SEASON_KEY].tolist()), "the deploy season leaked into the snapshot"
    assert not snap.duplicated(subset=list(ARP.PANEL_KEYS)).any()
    assert not snap[ARP.PLAYER_KEY].isna().any()


def test_the_ordered_schema_is_the_LIVE_consumed_contract(snap):
    """Derived, not hand-copied: the schema must equal the contract the reader uses."""
    import pyarrow.parquet as pq
    on_disk = tuple(pq.ParquetFile(ARP.VETERAN_SNAPSHOT).schema_arrow.names)
    assert on_disk == tuple(ARP.VETERAN_FEATURE_COLUMNS) == tuple(snap.columns)
    assert len(on_disk) == EXPECTED_COLS == ARP.VETERAN_SNAPSHOT_COLS
    assert tuple(ARP.VETERAN_FEATURE_COLUMNS) == ARP.IDENTITY_COLUMNS + ARP.ARM0_VETERAN_FEATURES


def test_the_schema_covers_every_shipped_VETERAN_bundle_pool(snap):
    """Cross-checked against the bundles' own feature_cols, via the independent pins."""
    for (pos, bucket), pin in PINS.BUNDLE_FEATURE_PINS.items():
        if bucket != "veteran":
            continue
        missing = [c for c in pin["feature_cols"] if c not in snap.columns]
        assert not missing, f"{pos}/{bucket} needs {missing}"


def test_the_manifest_entry_matches_the_file(snap):
    entry = json.loads(ARP.SNAPSHOT_MANIFEST.read_text(encoding="utf-8"))[
        ARP.VETERAN_SNAPSHOT_MANIFEST_KEY]
    assert entry["sha256"] == ARP.VETERAN_SNAPSHOT_SHA256
    assert (entry["rows"], entry["cols"]) == (EXPECTED_ROWS, EXPECTED_COLS)
    assert entry["seasons"] == list(EXPECTED_SEASONS)
    assert tuple(entry["schema"]) == tuple(ARP.VETERAN_FEATURE_COLUMNS)
    assert tuple(entry["keys"]) == ARP.PANEL_KEYS
    assert entry["generator"] == ARP.VETERAN_SNAPSHOT_GENERATOR
    assert entry["source"]["path"].endswith("season_dataset_2014_2026.csv")


# =====================================================================================================
# Feature-only: no outcome, target, label, weight, ADP or market field
# =====================================================================================================
def test_no_forbidden_field_is_present(snap):
    assert not (set(snap.columns) & ARP.FORBIDDEN_IN_FEATURES)


# PRECISE tokens. A first draft used bare "target" and "half_ppr", which flagged the legitimate
# prior-season features `prior_target_share`, `prior_targets_pg`, `prior_yptarget` and
# `prior_half_ppr` — the over-broad-matcher defect this project keeps hitting. What is banned is the
# TARGET variable and market prices, not any column whose name contains the word.
@pytest.mark.parametrize("token", ["target_ppg", "target_games", "sample_weight", "adp_", "sleeper",
                                   "outcome", "season_total", "fantasy_points", "_label"])
def test_no_column_name_carries_an_outcome_or_market_token(snap, token):
    hits = [c for c in snap.columns if token in c.lower()]
    assert not hits, f"{token!r} appears in {hits}"


@pytest.mark.parametrize("exact", ["y", "target", "label", "ppg", "games", "adp", "half_ppr",
                                   "sleeper_pts_half_ppr", "adp_half_ppr"])
def test_no_column_is_EXACTLY_an_outcome_or_market_field(snap, exact):
    assert exact not in {c.lower() for c in snap.columns}


def test_the_legitimate_prior_season_features_ARE_kept(snap):
    """Non-vacuity for the two tests above: these look outcome-ish and are correctly retained."""
    for c in ("prior_half_ppr", "prior_ppg", "prior_target_share", "prior_targets_pg",
              "prior_yptarget"):
        assert c in snap.columns, f"{c} was wrongly excluded"


def test_the_source_columns_the_snapshot_DROPPED_include_every_market_and_target_field():
    """Non-vacuity: the source really does carry forbidden fields, and the snapshot really excludes
    them — otherwise 'feature-only' would be an empty claim."""
    src_cols = set(pd.read_csv(SOURCE, nrows=0).columns)
    dropped = src_cols - set(ARP.VETERAN_FEATURE_COLUMNS)
    assert {"target_ppg", "target_games", "sample_weight", "adp_half_ppr", "adp_overall_rank",
            "adp_pos_rank", "sleeper_pts_half_ppr"} <= dropped
    assert set(ARP.FORBIDDEN_IN_FEATURES) & src_cols, "the source carries no forbidden field at all"


# =====================================================================================================
# Equality to the source's 2014-2025 consumed values
# =====================================================================================================
def test_the_snapshot_equals_the_SOURCE_2014_2025_consumed_values(snap, source_window):
    assert list(snap.columns) == list(source_window.columns)
    assert len(snap) == len(source_window)
    for c in snap.columns:
        s, v = snap[c], source_window[c]
        if pd.api.types.is_numeric_dtype(s) and pd.api.types.is_numeric_dtype(v):
            assert np.allclose(s.to_numpy(dtype=float), v.to_numpy(dtype=float),
                               rtol=0, atol=0, equal_nan=True), f"{c} differs"
        else:
            # null-aware: the snapshot stores `string` dtype (NA) and the CSV read gives object
            # (NaN), so a bare `.astype(str)` compares "<NA>" against "nan" and false-fails.
            sn, vn = s.isna().to_numpy(), v.isna().to_numpy()
            assert (sn == vn).all(), f"{c} differs in null placement"
            both = ~sn
            assert (s[both].astype(str).to_numpy() == v[both].astype(str).to_numpy()).all(), \
                f"{c} differs"


# =====================================================================================================
# 2026 cannot affect the snapshot or activation
# =====================================================================================================
@pytest.mark.skipif(not PRE_REFRESH.exists(), reason="pre-refresh copy not present in this checkout")
def test_building_from_the_PRE_REFRESH_source_reproduces_the_SAME_bytes(tmp_path):
    """The decisive property. The 2026-08-03 qb_changed refresh cannot move this artifact."""
    gen = _generator()
    out = tmp_path / "from_pre.parquet"
    gen.build(out=out, source=PRE_REFRESH, verbose=False)
    assert hashlib.sha256(out.read_bytes()).hexdigest() == ARP.VETERAN_SNAPSHOT_SHA256


@pytest.mark.skipif(not PRE_REFRESH.exists(), reason="pre-refresh copy not present in this checkout")
def test_the_two_sources_DIFFER_only_in_2026_and_only_as_measured():
    """Re-measures the finding rather than trusting it, and is non-vacuous: the files DO differ."""
    a = pd.read_csv(PRE_REFRESH)
    b = pd.read_csv(SOURCE)
    assert hashlib.md5(PRE_REFRESH.read_bytes()).hexdigest() != \
        hashlib.md5(SOURCE.read_bytes()).hexdigest(), "the files are identical; the test proves nothing"
    assert list(a.columns) == list(b.columns) and a[["player_id", "season"]].equals(
        b[["player_id", "season"]])

    noise_max, substantive = 0.0, []
    for c in a.columns:
        x, y = a[c], b[c]
        if pd.api.types.is_numeric_dtype(x):
            neq = ~((x.isna() & y.isna()) | np.isclose(x, y, rtol=0, atol=0, equal_nan=True))
        else:
            neq = ~((x.isna() & y.isna()) | (x.astype(str) == y.astype(str)))
        if not int(neq.sum()):
            continue
        assert set(a.loc[neq, "season"]) == {2026}, f"{c} differs outside season 2026"
        if c == "qb_changed":
            substantive.append((c, int(neq.sum())))
        else:
            noise_max = max(noise_max, float(np.nanmax((y - x).abs().to_numpy())))
            assert not int((x.isna() != y.isna()).sum()), f"{c} flipped a null"

    assert noise_max <= 3.6e-15, f"a non-qb_changed column moved by {noise_max}, not round-trip noise"
    assert substantive == [("qb_changed", 916)], substantive


@pytest.mark.skipif(not PRE_REFRESH.exists(), reason="pre-refresh copy not present in this checkout")
def test_NO_2014_2025_cell_differs_between_the_two_sources():
    a = pd.read_csv(PRE_REFRESH)
    b = pd.read_csv(SOURCE)
    a, b = a[a.season <= 2025].reset_index(drop=True), b[b.season <= 2025].reset_index(drop=True)
    assert len(a) == len(b) == EXPECTED_ROWS
    for c in a.columns:
        x, y = a[c], b[c]
        if pd.api.types.is_numeric_dtype(x):
            same = ((x.isna() & y.isna()) | np.isclose(x, y, rtol=0, atol=0, equal_nan=True)).all()
        else:
            same = ((x.isna() & y.isna()) | (x.astype(str) == y.astype(str))).all()
        assert same, f"a 2014-2025 value differs in {c}"


def test_a_2026_only_mutation_of_the_source_cannot_change_the_snapshot(tmp_path):
    """Directly: perturb ONLY 2026 rows, rebuild, and the bytes must not move."""
    gen = _generator()
    df = pd.read_csv(SOURCE)
    m = df["season"] == 2026
    assert int(m.sum()) > 0
    df.loc[m, "qb_changed"] = 1.0
    df.loc[m, "prior_ppg"] = 999.0
    mutated = tmp_path / "mutated_2026.csv"
    df.to_csv(mutated, index=False)

    out = tmp_path / "rebuilt.parquet"
    gen.build(out=out, source=mutated, verbose=False)
    assert hashlib.sha256(out.read_bytes()).hexdigest() == ARP.VETERAN_SNAPSHOT_SHA256


def test_activation_does_not_depend_on_the_live_production_csv():
    """`verify_pinned_activation_inputs` must not hash the mutable CSV at all."""
    import inspect
    src = inspect.getsource(ARP.verify_pinned_activation_inputs)
    assert "FEATURE_SOURCE" not in src, "activation still consults the mutable production CSV"
    assert "verify_veteran_snapshot_provenance" in src
    assert ARP.verify_pinned_activation_inputs(strict=False) == []


def test_the_authorized_reader_reads_the_snapshot_not_the_csv():
    import inspect
    src = inspect.getsource(ARP.authorized_feature_reader)
    assert "VETERAN_SNAPSHOT" in src
    assert "read_csv" not in src, "the authorized feature reader still reads a CSV"
    df = ARP.authorized_feature_reader()()
    assert len(df) == EXPECTED_ROWS and list(df.columns) == list(ARP.VETERAN_FEATURE_COLUMNS)
    assert ARP.validate_feature_frame(df) == []


# =====================================================================================================
# Any 2014-2025 consumed-value mutation fails
# =====================================================================================================
@pytest.mark.parametrize("column", ["prior_ppg", "age", "qb_changed", "draft_pick", "is_rookie"])
def test_a_2014_2025_consumed_value_mutation_CHANGES_the_rebuild(tmp_path, column):
    """RED: the snapshot is not indifferent to the window it actually consumes."""
    gen = _generator()
    df = pd.read_csv(SOURCE)
    m = df["season"] == 2019
    assert int(m.sum()) > 0
    df.loc[m, column] = 7.0 if column != "is_rookie" else 1
    mutated = tmp_path / f"mutated_{column}.csv"
    df.to_csv(mutated, index=False)

    out = tmp_path / "rebuilt.parquet"
    gen.build(out=out, source=mutated, verbose=False)
    assert hashlib.sha256(out.read_bytes()).hexdigest() != ARP.VETERAN_SNAPSHOT_SHA256, (
        f"mutating 2014-2025 {column} did not change the snapshot")


def test_a_corrupted_snapshot_is_refused_by_the_reader(tmp_path, snap):
    bad = snap.copy()
    bad.loc[bad.index[0], "prior_ppg"] = 999.0
    p = tmp_path / "bad.parquet"
    bad.to_parquet(p, index=False, engine="pyarrow", compression="snappy")
    with pytest.raises(ARP.AssemblyError) as e:
        ARP.authorized_feature_reader(path=p, verify_manifest=False)()
    assert "sha256" in str(e.value)


def test_a_dropped_or_extra_column_is_refused(tmp_path, snap):
    for label, frame in (("dropped", snap.drop(columns=["prior_ppg"])),
                         ("extra", snap.assign(bonus=1.0))):
        p = tmp_path / f"{label}.parquet"
        frame.to_parquet(p, index=False, engine="pyarrow", compression="snappy")
        with pytest.raises(ARP.AssemblyError):
            ARP.verify_veteran_snapshot_provenance(path=p, verify_hash=False, verify_manifest=False)


def test_a_2026_row_smuggled_into_the_snapshot_is_refused(tmp_path, snap):
    bad = pd.concat([snap, snap.tail(1).assign(season=2026)], ignore_index=True)
    p = tmp_path / "with_2026.parquet"
    bad.to_parquet(p, index=False, engine="pyarrow", compression="snappy")
    with pytest.raises(ARP.AssemblyError):
        ARP.verify_veteran_snapshot_provenance(path=p, verify_hash=False, verify_manifest=False)


# =====================================================================================================
# Determinism, and the rookie matrix left alone
# =====================================================================================================
def test_two_fresh_rebuilds_are_byte_identical(tmp_path):
    gen = _generator()
    hashes = []
    for i in (1, 2):
        out = tmp_path / f"rebuild_{i}.parquet"
        gen.build(out=out, verbose=False)
        hashes.append(hashlib.sha256(out.read_bytes()).hexdigest())
    assert hashes[0] == hashes[1] == ARP.VETERAN_SNAPSHOT_SHA256


def test_the_corrected_rookie_matrix_is_UNCHANGED_and_was_not_rebuilt():
    """This pass touches the veteran path only."""
    assert hashlib.sha256(ARP.ROOKIE_MATRIX.read_bytes()).hexdigest() == ARP.ROOKIE_MATRIX_SHA256
    assert ARP.ROOKIE_MATRIX_SHA256 == \
        "7625980495886141efd65fb9c65862ef7f3cf8af67e50f231c6c3c12d9f45385"
    ARP.verify_rookie_matrix_provenance()
    m = pd.read_parquet(ARP.ROOKIE_MATRIX)
    assert m.shape == (ARP.ROOKIE_MATRIX_ROWS, ARP.ROOKIE_MATRIX_COLS) == (1263, 61)
    for col in ARP.ROOKIE_MATRIX_PROVENANCE:
        nn = m[col].notna()
        assert int((m.loc[nn, "season"] - m.loc[nn, col]).min()) >= 1


def test_the_generator_reads_the_csv_but_the_experiment_never_does():
    """The asymmetry that makes this design work, stated and checked."""
    gen_src = GENERATOR.read_text(encoding="utf-8")
    assert "season_dataset_2014_2026.csv" in gen_src, "the generator must name its source"
    assert "read_csv" in gen_src

    arp_src = (COACH / "assemble_real_panel_v39.py").read_text(encoding="utf-8")
    reader_block = arp_src.split("def authorized_feature_reader", 1)[1].split("\ndef ", 1)[0]
    assert "read_csv" not in reader_block


# =====================================================================================================
# The stop state is unaffected by any of this
# =====================================================================================================
def test_preflight_readiness_and_gate_after_the_rescope():
    pf = EX.preflight(pipeline_assertions={k: 3 for k in EX._PIPELINE_ASSERTIONS})
    assert pf["all_ok"] is True and pf["n_checks"] == 21 and pf["n_failed"] == 0
    assert ARP.activation_readiness()[0] is True
    ok, detail = ARP.authorized_real_gate(pf)
    assert ok is False and "BOTH LOCKS CLOSED" in detail
    assert "gate 2" not in detail
    assert EX.real_fit_lock_state() == (False, False)
