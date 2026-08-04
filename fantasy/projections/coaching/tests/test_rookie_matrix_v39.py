"""Corruption tests for the frozen rookie Arm 0 feature matrix (Option A, 2026-08-03).

Every test here reads DERIVED FEATURE VALUES only. The matrix carries no fantasy outcome, target,
label, sample weight, ADP, market projection or target-season realized statistic — several tests exist
precisely to prove that, and none of them reads, prints, aggregates or compares an outcome value.

The pattern throughout: mutate a COPY in `tmp_path`, then assert the validator refuses. A test that
only proved the clean file passes would not distinguish a real check from a check that always says yes,
which is the failure mode this whole pass keeps finding.
"""
import ast
import pathlib
import pickle
import subprocess
import sys

import pandas as pd
import pytest

COACH = pathlib.Path(__file__).resolve().parent.parent
REPO = COACH.parent.parent.parent
sys.path.insert(0, str(COACH))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import arm0_bundle_pins as PINS                            # noqa: E402  independent frozen literals
import assemble_real_panel_v39 as ARP                      # noqa: E402
import run_coach_projection_experiment_v39 as EX           # noqa: E402

GENERATOR = REPO / ARP.ROOKIE_MATRIX_GENERATOR

# Independently pinned here, NOT imported from the module under test: the frozen 2014-2025 rookie
# population, measured once at build time. 584 + 387 + 292 = 1263.
EXPECTED_POSITION_COUNTS = {"WR": 584, "RB": 387, "TE": 292}
ROOKIE_BUCKETS = (("RB", "rookie"), ("WR", "rookie"), ("TE", "rookie"))


@pytest.fixture(scope="module")
def matrix():
    return pd.read_parquet(ARP.ROOKIE_MATRIX)


def _write(df, tmp_path, name="corrupt.parquet"):
    p = tmp_path / name
    df.to_parquet(p, index=False, engine="pyarrow", compression="snappy")
    return p


def _provenance(path):
    """File-level check with the hash and manifest switched OFF, so the OTHER checks are exercised."""
    return ARP.verify_rookie_matrix_provenance(path=path, verify_hash=False, verify_manifest=False)


# =====================================================================================================
# The clean file, and the three pins agreeing with each other
# =====================================================================================================
def test_the_frozen_matrix_verifies_clean():
    entry = ARP.verify_rookie_matrix_provenance()
    assert entry["sha256"] == ARP.ROOKIE_MATRIX_SHA256
    assert ARP.rookie_matrix_columns() == ARP.ROOKIE_MATRIX_COLUMNS


def test_the_pinned_schema_literal_matches_the_file_on_disk():
    """The literal in the module is an INDEPENDENT pin, so it must be checked against the real file."""
    import pyarrow.parquet as pq
    actual = tuple(pq.ParquetFile(ARP.ROOKIE_MATRIX).schema_arrow.names)
    assert actual == ARP.ROOKIE_MATRIX_COLUMNS
    assert len(actual) == ARP.ROOKIE_MATRIX_COLS == 61
    assert len(set(actual)) == len(actual)


def test_the_file_hash_matches_the_pin_and_the_manifest():
    import hashlib
    import json
    raw = ARP.ROOKIE_MATRIX.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == ARP.ROOKIE_MATRIX_SHA256
    entry = json.loads(ARP.SNAPSHOT_MANIFEST.read_text(encoding="utf-8"))[
        ARP.ROOKIE_MATRIX_MANIFEST_KEY]
    assert entry["sha256"] == ARP.ROOKIE_MATRIX_SHA256
    assert (entry["rows"], entry["cols"]) == (ARP.ROOKIE_MATRIX_ROWS, ARP.ROOKIE_MATRIX_COLS)
    assert sorted(entry["seasons"]) == list(ARP.ALL_PANEL_SEASONS)
    assert tuple(entry["keys"]) == ARP.PANEL_KEYS
    assert tuple(entry["positions"]) == ARP.ROOKIE_MATRIX_POSITIONS
    assert entry["generator"] == ARP.ROOKIE_MATRIX_GENERATOR


def test_the_declared_generator_exists_and_is_the_file_that_built_it():
    assert GENERATOR.exists(), f"declared generator missing: {GENERATOR}"
    src = GENERATOR.read_text(encoding="utf-8")
    assert "rookie_arm0_features_2014_2025.parquet" in src


def _generator_module():
    import importlib.util
    spec = importlib.util.spec_from_file_location("build_rookie_arm0_features_under_test", GENERATOR)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_every_non_pff_input_is_pinned_and_currently_matches():
    """A rebuild against a drifted input must fail loudly, not quietly change the artifact."""
    gen = _generator_module()
    # SUPERSEDED SCOPE (2026-08-03): the generator used to pin the whole mutable production CSV. It
    # now consumes the IMMUTABLE veteran snapshot, which carries every identity/routing key and every
    # landing-spot column it needs, so a deploy-season-2026 refresh cannot move the rookie matrix.
    assert set(gen.INPUT_PINS) == {"snapshots/veteran_arm0_features_2014_2025.parquet",
                                   "college_features.csv",
                                   "snapshots/combine.parquet", "snapshots/draft_picks.parquet"}
    assert not any("season_dataset" in k for k in gen.INPUT_PINS), (
        "the mutable production CSV must no longer be a pinned rookie input")
    digests = gen.verify_inputs()
    for rel, (algo, pinned) in gen.INPUT_PINS.items():
        assert digests[rel] == pinned, f"{rel} drifted"
        assert len(pinned) == (32 if algo == "md5" else 64)


def test_a_drifted_input_is_refused(tmp_path, monkeypatch):
    """RED: corrupt one pin and the build must refuse before reading a value."""
    gen = _generator_module()
    monkeypatch.setitem(gen.INPUT_PINS, "snapshots/combine.parquet", ("sha256", "0" * 64))
    with pytest.raises(gen.BuildError) as e:
        gen.verify_inputs()
    assert "combine.parquet" in str(e.value)


def test_the_private_pff_library_is_deliberately_NOT_pinned():
    """Stated, not hidden: the PFF input is outside the repo's hash contract, which is WHY the derived
    output is frozen rather than regenerated on demand."""
    gen = _generator_module()
    assert not any("pff" in k.lower() for k in gen.INPUT_PINS)
    assert "deliberately NOT pinned" in GENERATOR.read_text(encoding="utf-8")


def test_the_frozen_population_is_rookie_only_and_fully_present(matrix):
    assert len(matrix) == ARP.ROOKIE_MATRIX_ROWS == 1263
    assert dict(matrix["position"].value_counts()) == EXPECTED_POSITION_COUNTS
    assert sum(EXPECTED_POSITION_COUNTS.values()) == ARP.ROOKIE_MATRIX_ROWS
    assert bool((matrix["is_rookie"] == 1).all())
    assert not matrix.duplicated(subset=list(ARP.PANEL_KEYS)).any()
    assert sorted(int(s) for s in matrix["season"].unique()) == list(ARP.ALL_PANEL_SEASONS)


def test_nulls_are_PRESERVED_not_imputed(matrix):
    """A row with no combine or no PFF row is KEPT with nulls. Zero nulls would mean silent imputation."""
    features = [c for c in ARP.ROOKIE_MATRIX_COLUMNS if c not in ARP.ROOKIE_MATRIX_IDENTITY]
    assert matrix[features].isna().any().any(), "no null anywhere — measurements were imputed"
    # and no row was dropped for being incompletely measured
    assert int(matrix[features].isna().any(axis=1).sum()) > 0
    assert len(matrix) == ARP.ROOKIE_MATRIX_ROWS


# =====================================================================================================
# It carries no outcome, target, label, weight, ADP or market projection
# =====================================================================================================
def test_no_forbidden_column_is_present(matrix):
    assert not (set(matrix.columns) & ARP.FORBIDDEN_IN_FEATURES)


@pytest.mark.parametrize("token", ["fantasy_points", "half_ppr", "season_total", "target_ppg",
                                   "target_games", "sample_weight", "adp", "sleeper", "hit_prob",
                                   "outcome", "yhat", "actual", "finish"])
def test_no_column_name_carries_an_outcome_or_market_token(matrix, token):
    hits = [c for c in matrix.columns if token in c.lower()]
    assert not hits, f"{token!r} appears in {hits}"


GENERATOR_EXEMPT_ASSIGNMENTS = ("FORBIDDEN_SUBSTRINGS", "FORBIDDEN_EXACT")


def test_the_generator_never_names_the_outcome():
    """An AST scan of the builder: no banned token in any executable string, same shape as C4.

    The exemption is NARROW and named: only the string literals bound by the generator's own two
    forbidden-token declarations. A blanket "unless the line also says FORBIDDEN" exemption would be
    self-voiding — each element of a tuple is its own Constant and carries none of the surrounding
    text — so the exemption is keyed on the ASSIGNMENT TARGET, which an injected read cannot claim.
    """
    tree = ast.parse(GENERATOR.read_text(encoding="utf-8"))
    banned = ("season_total_half_ppr", "fantasy_points", "target_ppg", "sample_weight")

    exempt, declared = set(), set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            names = {t.id for t in node.targets if isinstance(t, ast.Name)}
            if names & set(GENERATOR_EXEMPT_ASSIGNMENTS):
                declared |= names
                for sub in ast.walk(node.value):
                    if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
                        exempt.add(id(sub))
    assert declared == set(GENERATOR_EXEMPT_ASSIGNMENTS), (
        f"the exemption names {sorted(GENERATOR_EXEMPT_ASSIGNMENTS)} but the generator declares "
        f"{sorted(declared)} — an exemption for a declaration that no longer exists is dead")

    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            first = node.body[0] if node.body else None
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
                docstrings.add(id(first.value))

    hits = [(tok, node.lineno)
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
            and id(node) not in docstrings and id(node) not in exempt
            for tok in banned if tok in node.value]
    assert not hits, f"the generator names an outcome at {hits}"


def test_the_generator_scan_catches_an_injected_read():
    """Red proof: the scan above must fail on a generator that actually reads the outcome."""
    injected = GENERATOR.read_text(encoding="utf-8") + '\ny = df["season_total_half_ppr"]\n'
    tree = ast.parse(injected)
    exempt = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and {t.id for t in node.targets
                                             if isinstance(t, ast.Name)} & set(
                                                 GENERATOR_EXEMPT_ASSIGNMENTS):
            for sub in ast.walk(node.value):
                if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
                    exempt.add(id(sub))
    hits = [n.lineno for n in ast.walk(tree)
            if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in exempt
            and "season_total_half_ppr" in n.value]
    assert hits, "the scan would not catch a direct outcome read"


def test_raw_pff_is_untracked_while_derived_values_are_repo_owned(matrix):
    """Option A's condition: commit derived feature values, never the raw licensed files."""
    out = subprocess.run(["git", "-c", f"safe.directory={REPO}", "ls-files",
                          "fantasy/seasonal_projections/pff"],
                         cwd=REPO, capture_output=True, text=True)
    if out.returncode != 0:                        # no git available -> nothing to assert
        pytest.skip("git unavailable")
    assert out.stdout.strip() == "", f"raw PFF files are TRACKED: {out.stdout.splitlines()[:5]}"
    pff_cols = [c for c in matrix.columns if c.startswith("pff_")]
    assert pff_cols and matrix[pff_cols].notna().any().any(), "no derived PFF value survived"


def test_the_documented_pff_local_file_count_is_MEASURED_not_asserted():
    """The docs carried '418 local files' from v3.9g to v3.9m; it matched no measurement.

    Only the 0-tracked half had ever been verified. The count is now derived from disk and compared to
    what the documents say, so a stale figure fails instead of being quoted forward. The number itself
    is not a contract — the docs are allowed to move with it; what is banned is disagreeing with it.
    """
    pff = REPO / "fantasy" / "seasonal_projections" / "pff"
    if not pff.exists():
        pytest.skip("private PFF library not present in this checkout")
    n_files = sum(1 for p in pff.rglob("*") if p.is_file())
    n_csv = sum(1 for p in pff.rglob("*.csv"))
    assert n_files > 0 and n_csv > 0

    stale = []
    for rel in ("V39_ACTIVATION_MANIFEST.md", "V39_PREFIT_STOP_REPORT.md", "AUDIT_TODO.md"):
        text = (COACH / rel).read_text(encoding="utf-8")
        for lineno, line in enumerate(text.splitlines(), 1):
            if "418" not in line:
                continue
            if "SUPERSEDED" in line:
                continue                       # explicitly retired on the same line
            stale.append(f"{rel}:{lineno} {line.strip()[:90]}")
    assert not stale, ("a superseded PFF file count is stated without a same-line qualifier:\n  "
                       + "\n  ".join(stale))
    for rel in ("V39_ACTIVATION_MANIFEST.md", "V39_PREFIT_STOP_REPORT.md"):
        text = (COACH / rel).read_text(encoding="utf-8")
        assert f"{n_files} local files" in text, (
            f"{rel} does not state the measured local file count {n_files}")


# =====================================================================================================
# CORRUPTION — file level
# =====================================================================================================
def test_a_flipped_byte_is_refused(tmp_path):
    raw = bytearray(ARP.ROOKIE_MATRIX.read_bytes())
    raw[len(raw) // 2] ^= 0xFF
    p = tmp_path / "flipped.parquet"
    p.write_bytes(bytes(raw))
    with pytest.raises(ARP.AssemblyError) as e:
        ARP.verify_rookie_matrix_provenance(path=p, verify_manifest=False)
    assert "sha256" in str(e.value)


def test_an_absent_matrix_is_refused(tmp_path):
    with pytest.raises(ARP.AssemblyError) as e:
        ARP.verify_rookie_matrix_provenance(path=tmp_path / "nope.parquet")
    assert "missing" in str(e.value)


def test_a_reordered_schema_is_refused(matrix, tmp_path):
    cols = list(matrix.columns)
    cols[5], cols[6] = cols[6], cols[5]
    with pytest.raises(ARP.AssemblyError) as e:
        _provenance(_write(matrix[cols], tmp_path))
    assert "schema differs" in str(e.value)


def test_a_renamed_column_is_refused(matrix, tmp_path):
    df = matrix.rename(columns={"forty": "forty_yard"})
    with pytest.raises(ARP.AssemblyError) as e:
        _provenance(_write(df, tmp_path))
    assert "schema differs" in str(e.value)


def test_an_added_column_is_refused(matrix, tmp_path):
    df = matrix.assign(extra_feature=1.0)
    with pytest.raises(ARP.AssemblyError) as e:
        _provenance(_write(df, tmp_path))
    assert "schema differs" in str(e.value)


def test_a_dropped_column_is_refused(matrix, tmp_path):
    with pytest.raises(ARP.AssemblyError) as e:
        _provenance(_write(matrix.drop(columns=["speed_score"]), tmp_path))
    assert "schema differs" in str(e.value)


def test_row_loss_is_refused_at_the_file_level(matrix, tmp_path):
    with pytest.raises(ARP.AssemblyError) as e:
        _provenance(_write(matrix.iloc[:-1], tmp_path))
    assert "row count" in str(e.value)


@pytest.mark.parametrize("column", sorted(ARP.FORBIDDEN_IN_FEATURES))
def test_every_forbidden_column_is_refused_at_the_file_level(matrix, tmp_path, column):
    df = matrix.copy()
    df[column] = 0.0
    with pytest.raises(ARP.AssemblyError) as e:
        _provenance(_write(df, tmp_path, f"forbidden_{column}.parquet"))
    msg = str(e.value)
    assert "outcome-bearing" in msg or "schema differs" in msg


# =====================================================================================================
# CORRUPTION — manifest level
# =====================================================================================================
def _manifest_copy(tmp_path, **overrides):
    import json
    man = json.loads(ARP.SNAPSHOT_MANIFEST.read_text(encoding="utf-8"))
    if overrides.pop("_drop_entry", False):
        man.pop(ARP.ROOKIE_MATRIX_MANIFEST_KEY)
    else:
        man[ARP.ROOKIE_MATRIX_MANIFEST_KEY].update(overrides)
    p = tmp_path / "manifest.json"
    p.write_text(json.dumps(man, indent=2, sort_keys=True), encoding="utf-8")
    return p


def test_a_missing_manifest_entry_is_refused(tmp_path):
    with pytest.raises(ARP.AssemblyError) as e:
        ARP.verify_rookie_matrix_provenance(manifest_path=_manifest_copy(tmp_path, _drop_entry=True))
    assert "no entry" in str(e.value)


@pytest.mark.parametrize("field,bad", [
    ("sha256", "0" * 64),
    ("generator", "some/other/script.py"),
    ("rows", 1262),
    ("cols", 58),
    ("seasons", list(range(2015, 2026))),
    ("keys", ["player_id"]),
    ("positions", ["RB", "WR"]),
])
def test_a_manifest_field_disagreeing_with_the_pin_is_refused(tmp_path, field, bad):
    with pytest.raises(ARP.AssemblyError) as e:
        ARP.verify_rookie_matrix_provenance(manifest_path=_manifest_copy(tmp_path, **{field: bad}))
    assert field in str(e.value)


def test_a_missing_manifest_file_is_refused(tmp_path):
    with pytest.raises(ARP.AssemblyError) as e:
        ARP.verify_rookie_matrix_provenance(manifest_path=tmp_path / "gone.json")
    assert "manifest missing" in str(e.value)


# =====================================================================================================
# CORRUPTION — frame level (keys, seasons, positions, bundle ordering)
# =====================================================================================================
def test_the_clean_frame_validates(matrix):
    assert ARP.validate_rookie_matrix(matrix) == []


def test_a_duplicate_key_is_refused(matrix):
    df = matrix.copy()
    df.loc[df.index[5], ["player_id", "season"]] = df.loc[df.index[0], ["player_id", "season"]].values
    problems = ARP.validate_rookie_matrix(df)
    assert any("duplicate" in p for p in problems), problems


def test_a_null_key_is_refused(matrix):
    df = matrix.copy()
    df.loc[df.index[3], "player_id"] = None
    assert any("null player_id" in p for p in ARP.validate_rookie_matrix(df)), "null key accepted"


def test_row_loss_is_refused_at_the_frame_level(matrix):
    assert any("row count" in p for p in ARP.validate_rookie_matrix(matrix.iloc[:-3]))


def test_a_missing_season_is_refused(matrix):
    df = matrix[matrix["season"] != 2014]
    assert any("season coverage" in p for p in ARP.validate_rookie_matrix(df))


def test_an_out_of_range_season_is_refused(matrix):
    df = matrix.copy()
    df.loc[df.index[0], "season"] = 2026
    assert any("season coverage" in p for p in ARP.validate_rookie_matrix(df))


def test_a_foreign_position_is_refused(matrix):
    df = matrix.copy()
    df.loc[df.index[0], "position"] = "QB"
    assert any("positions" in p for p in ARP.validate_rookie_matrix(df))


def test_a_non_rookie_row_is_refused(matrix):
    df = matrix.copy()
    df.loc[df.index[0], "is_rookie"] = 0
    assert any("non-rookie" in p for p in ARP.validate_rookie_matrix(df))


@pytest.mark.parametrize("position,bucket", ROOKIE_BUCKETS)
def test_every_rookie_bundle_selects_in_bundle_order(matrix, position, bucket):
    fc = tuple(PINS.BUNDLE_FEATURE_PINS[(position, bucket)]["feature_cols"])
    frame = ARP.rookie_bucket_frame(matrix, position, bucket)
    assert tuple(c for c in frame.columns if c in set(fc)) == fc
    assert len(frame) == EXPECTED_POSITION_COUNTS[position]


def test_the_three_pools_CANNOT_share_one_storage_order(matrix):
    """Stated because the validator was briefly written as if they could.

    RB and WR order their common features differently, so demanding that the stored column order equal
    every bundle order at once is unsatisfiable. Storage order is pinned by the schema literal; feed
    order is enforced on the per-bucket frame. This test measures the conflict rather than asserting it.
    """
    cols = list(matrix.columns)
    inverted = []
    for position, _bucket in ROOKIE_BUCKETS:
        fc = list(PINS.BUNDLE_FEATURE_PINS[(position, "rookie")]["feature_cols"])
        idx = [cols.index(c) for c in fc]
        if idx != sorted(idx):
            inverted.append(position)
    assert inverted, "if every pool were monotonic the weaker contract would be unnecessary"
    assert set(inverted) == {"RB", "WR", "TE"}


@pytest.mark.parametrize("position,bucket", ROOKIE_BUCKETS)
def test_dropping_one_bundle_feature_is_refused(matrix, position, bucket):
    fc = PINS.BUNDLE_FEATURE_PINS[(position, bucket)]["feature_cols"]
    df = matrix.drop(columns=[fc[-1]])
    problems = ARP.validate_rookie_matrix(df)
    assert any(f"{position}/{bucket} missing" in p for p in problems), problems
    with pytest.raises(ARP.AssemblyError):
        ARP.rookie_bucket_frame(df, position, bucket)


def test_a_bucket_frame_with_shuffled_features_is_refused(matrix):
    """The order guard, at the point where order is real — the frame a model would be fed."""
    fc = list(PINS.BUNDLE_FEATURE_PINS[("RB", "rookie")]["feature_cols"])
    frame = ARP.rookie_bucket_frame(matrix, "RB", "rookie")
    cols = list(frame.columns)
    i, j = cols.index(fc[0]), cols.index(fc[1])
    cols[i], cols[j] = cols[j], cols[i]
    with pytest.raises(ARP.AssemblyError) as e:
        ARP.bucket_frame_satisfies_bundle(cols, "RB", "rookie")
    assert "bundle order" in str(e.value)


def test_reordering_the_stored_schema_is_refused_by_the_schema_pin(matrix):
    cols = list(matrix.columns)
    cols[5], cols[6] = cols[6], cols[5]
    problems = ARP.validate_rookie_matrix(matrix[cols])
    assert any("schema differs" in p for p in problems), problems


def test_a_veteran_bucket_cannot_be_pulled_from_the_rookie_matrix(matrix):
    with pytest.raises(ARP.AssemblyError) as e:
        ARP.rookie_bucket_frame(matrix, "QB", "veteran")
    assert "not sourced from the rookie matrix" in str(e.value)


def test_a_frame_with_no_identity_at_all_reports_and_does_not_raise(matrix):
    problems = ARP.validate_rookie_matrix(matrix.drop(columns=list(ARP.ROOKIE_MATRIX_IDENTITY)))
    assert problems and any("schema differs" in p for p in problems)


# =====================================================================================================
# The reader
# =====================================================================================================
def test_the_default_rookie_reader_refuses():
    with pytest.raises(ARP.AssemblyError) as e:
        ARP.default_rookie_matrix_reader()
    assert "closed" in str(e.value)


def test_constructing_the_authorized_reader_reads_nothing(tmp_path):
    reader = ARP.authorized_rookie_matrix_reader(path=tmp_path / "does_not_exist.parquet")
    with pytest.raises(ARP.AssemblyError):
        reader()                                   # only CALLING it touches the disk


def test_the_authorized_reader_returns_the_frozen_frame():
    df = ARP.authorized_rookie_matrix_reader()()
    assert tuple(df.columns) == ARP.ROOKIE_MATRIX_COLUMNS
    assert len(df) == ARP.ROOKIE_MATRIX_ROWS
    assert ARP.OUTCOME_COLUMN not in df.columns


def test_the_reader_runs_its_own_output_through_its_own_validator(matrix, tmp_path):
    """The exact defect that let a reader which could not work pass 663 tests."""
    df = matrix.copy()
    df.loc[df.index[0], "position"] = "QB"
    p = _write(df, tmp_path, "bad_position.parquet")
    reader = ARP.authorized_rookie_matrix_reader(path=p, verify_hash=False, verify_manifest=False)
    with pytest.raises(ARP.AssemblyError) as e:
        reader()
    assert "failed its own validator" in str(e.value)


# =====================================================================================================
# Readiness, and the fact that readiness is NOT authorization
# =====================================================================================================
def test_all_seven_bundles_have_their_FEATURES(monkeypatch):
    """Feature availability only. Whether a bundle is USABLE is a separate question — the three
    rookie bundles were trained on the leaked PFF join, so `complete` is False for them."""
    rows = ARP.arm0_bucket_table()
    assert len(rows) == 7
    assert all(r["features_available"] for r in rows), [r for r in rows
                                                        if not r["features_available"]]
    assert all(r["error"] is None for r in rows)
    assert all(r["n_missing_from_declared_source"] == 0 for r in rows)
    by_source = {r["source"] for r in rows}
    assert by_source == {ARP.SOURCE_SEASON_DATASET, ARP.SOURCE_ROOKIE_MATRIX}


@pytest.mark.parametrize("position,bucket", ROOKIE_BUCKETS)
def test_each_rookie_bundle_is_sourced_from_the_frozen_matrix(position, bucket):
    row = next(r for r in ARP.arm0_bucket_table() if (r["position"], r["bucket"]) == (position, bucket))
    assert row["source"] == ARP.SOURCE_ROOKIE_MATRIX
    assert row["n_features"] == row["expected_n"] == PINS.BUNDLE_FEATURE_PINS[(position, bucket)]["n"]
    assert row["features_available"] is True
    assert row["spec_contract_ok"] is True
    assert row["complete"] is True


def test_activation_readiness_is_TRUE_with_a_point_in_time_matrix():
    """The features are complete AND point-in-time, and the bundle specs are well-formed.

    A v3.9o revision briefly refused here on the grounds that the rookie bundles had been TRAINED on
    the leaked join. That blocker rested on a false premise — every fold builds a fresh estimator and
    the serialized weights never enter — and is withdrawn; see test_arm0_refits_from_scratch_v39.py.
    """
    ok, detail = ARP.activation_readiness()
    assert ok is True, detail
    assert "all 7 shipped Arm 0 buckets" in detail
    assert "NOT AUTHORIZED" in detail and "locks remain closed" in detail


def test_readiness_says_in_its_own_words_that_it_is_not_authorization():
    _ok, detail = ARP.activation_readiness()
    assert "NOT AUTHORIZED" in detail and "locks remain closed" in detail


def test_readiness_fails_CLOSED_when_the_matrix_cannot_be_verified(monkeypatch, tmp_path):
    monkeypatch.setattr(ARP, "ROOKIE_MATRIX", tmp_path / "vanished.parquet")
    ok, detail = ARP.activation_readiness()
    assert ok is False
    assert "rookie matrix missing" in detail


def test_readiness_fails_CLOSED_on_a_hash_mismatch(monkeypatch):
    monkeypatch.setattr(ARP, "ROOKIE_MATRIX_SHA256", "0" * 64)
    ok, detail = ARP.activation_readiness()
    assert ok is False
    assert "sha256" in detail


def test_a_clean_preflight_still_does_not_open_the_gate():
    """The whole point of the two layers: prefit integrity is not activation authority."""
    ran = {k: 3 for k in EX._PIPELINE_ASSERTIONS}
    pf = EX.preflight(pipeline_assertions=ran)
    assert pf["all_ok"] is True and pf["n_failed"] == 0 and pf["n_checks"] == 21
    assert ARP.activation_readiness()[0] is True
    ok, detail = ARP.authorized_real_gate(pf)
    assert ok is False
    assert "REFUSED" in detail
    assert EX.REAL_FIT_AUTHORIZED is False


def test_the_locks_are_still_closed():
    import os
    assert EX.REAL_FIT_AUTHORIZED is False
    assert os.environ.get("COACH_V39_REAL_FIT_AUTHORIZED_BY_JOSEPH") is None


def test_the_activation_entry_point_is_still_sealed():
    """The seal MOVED from `the body raises` to `the body cannot reach data unauthorized` (C5-A).

    What must remain true, and is checked here: authorization is statement 1, the clearance is
    statement 2, and the body contains no reader callee at all.
    """
    src = (COACH / "run_coach_projection_experiment_v39.py").read_text(encoding="utf-8")
    fn = next(n for n in ast.walk(ast.parse(src))
              if isinstance(n, ast.FunctionDef) and n.name == "assemble_real_panel")
    body = [s for s in fn.body if not (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant))]
    assert len(body) == 3
    assert isinstance(body[0], ast.Expr) and body[0].value.func.id == "require_real_fit_authorization"
    assert isinstance(body[1], ast.Expr) and body[1].value.func.id == EX.PREFLIGHT_CLEARANCE_NAME
    assert isinstance(body[2], ast.Return)
    callees = {getattr(n.func, "id", None) for n in ast.walk(fn) if isinstance(n, ast.Call)}
    assert not (callees & EX.ENTRY_POINT_BANNED_READER_CALLEES)
    assert EX.real_fit_lock_state() == (False, False)


def test_the_assembly_contract_still_holds_with_the_matrix_wired_in():
    ok, detail = ARP.assembly_module_contract()
    assert ok is True, detail


def test_the_blocker_text_no_longer_claims_the_matrix_is_absent():
    assert "RESOLVED" in ARP.ROOKIE_INPUT_BLOCKER
    assert "DOES NOT EXIST" not in ARP.ROOKIE_INPUT_BLOCKER
    assert "untracked" in ARP.ROOKIE_INPUT_BLOCKER


def test_the_bundle_pins_and_the_matrix_agree_on_every_rookie_pool(matrix):
    """Cross-check against the independent literal pins, not against the module's own constants."""
    for (position, bucket) in ROOKIE_BUCKETS:
        pin = PINS.BUNDLE_FEATURE_PINS[(position, bucket)]
        live = tuple(pickle.loads((ARP.MODELS_DIR / ARP.SHIPPED_ARM0_BUCKETS[(position, bucket)][0])
                                  .read_bytes())["feature_cols"])
        assert live == tuple(pin["feature_cols"])
        assert set(live) <= set(matrix.columns)
