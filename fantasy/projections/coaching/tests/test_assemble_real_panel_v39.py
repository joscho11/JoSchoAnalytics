"""Tests for the real-panel assembly path.

No real outcome VALUE is read, printed, aggregated or compared anywhere here. Fixtures are synthetic
frames and temporary files written by the tests themselves. The two authorized readers ARE invoked —
against temporary synthetic files — because the previous revision never ran the real feature reader's
output through its own validator, which is exactly why a reader that returned 2026 rows and forbidden
target columns passed all 663 tests.
"""
import ast
import json
import pathlib
import sys

import numpy as np
import pandas as pd
import pytest

COACH = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(COACH))

import assemble_real_panel_v39 as ARP                      # noqa: E402
import run_coach_projection_experiment_v39 as EX           # noqa: E402


# =====================================================================================================
# Synthetic fixtures
# =====================================================================================================
def synthetic_features(seasons=ARP.ALL_PANEL_SEASONS, players=6, seed=11):
    rng = np.random.default_rng(seed)
    rows = []
    for s in seasons:
        for p in range(players):
            row = {ARP.PLAYER_KEY: f"00-00{p:04d}", ARP.SEASON_KEY: int(s),
                   "player": f"P{p}", "norm_name": f"p{p}",
                   "position": ["RB", "WR", "TE", "QB"][p % 4], "team": "AAA",
                   "reconstructed": 0, "is_rookie": 0}
            for c in ARP.ARM0_VETERAN_FEATURES:
                row[c] = float(rng.normal())
            rows.append(row)
    return pd.DataFrame(rows)[list(ARP.FROZEN_FEATURE_COLUMNS)]


def synthetic_outcomes(features, seed=12, drop=0):
    rng = np.random.default_rng(seed)
    keys = features[list(ARP.PANEL_KEYS)].drop_duplicates().reset_index(drop=True)
    if drop:
        keys = keys.iloc[:-drop].reset_index(drop=True)
    keys[ARP.OUTCOME_COLUMN] = rng.normal(150, 40, size=len(keys))
    return keys


def synthetic_weekly(seasons=ARP.ALL_PANEL_SEASONS, players=6, weeks=3, seed=5,
                     include_post=True, include_2013=True):
    rng = np.random.default_rng(seed)
    rows = []
    seasons = list(seasons) + ([2013] if include_2013 else [])
    for s in seasons:
        for p in range(players):
            for w in range(1, weeks + 1):
                rows.append({ARP.PLAYER_KEY: f"00-00{p:04d}", ARP.SEASON_KEY: int(s),
                             "season_type": "REG", "fantasy_points": float(rng.uniform(0, 20)),
                             "receptions": float(rng.integers(0, 6))})
                if include_post:
                    rows.append({ARP.PLAYER_KEY: f"00-00{p:04d}", ARP.SEASON_KEY: int(s),
                                 "season_type": "POST", "fantasy_points": 999.0,
                                 "receptions": 99.0})
    return pd.DataFrame(rows)


@pytest.fixture
def feats():
    return synthetic_features()


@pytest.fixture
def outs(feats):
    return synthetic_outcomes(feats)


# =====================================================================================================
# The door is still SEALED
# =====================================================================================================
def test_the_entry_point_is_still_sealed_and_this_pass_did_not_weaken_it():
    ok, detail = EX.no_real_outcome_access()
    assert ok is True, detail
    assert detail == EX.NO_OUTCOME_OK_DETAIL
    tree = EX._executable_tree((COACH / "run_coach_projection_experiment_v39.py")
                               .read_text(encoding="utf-8"))
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == EX.ENTRY_POINT_NAME)
    assert len(fn.body) == 2 and isinstance(fn.body[1], ast.Raise)
    assert not EX._entry_point_is_sealed(tree)


def test_assemble_real_panel_still_raises_with_both_locks_closed():
    assert EX.real_fit_lock_state() == (False, False)
    with pytest.raises(RuntimeError) as exc:
        EX.assemble_real_panel()
    assert "NOT AUTHORIZED" in str(exc.value)


@pytest.mark.parametrize("constant_open,env_open", [(False, False), (True, False), (False, True)])
def test_every_partial_or_closed_lock_state_refuses(monkeypatch, constant_open, env_open):
    monkeypatch.setattr(EX, "REAL_FIT_AUTHORIZED", constant_open, raising=False)
    if env_open:
        monkeypatch.setenv(EX.REAL_FIT_ENV_SWITCH, EX.REAL_FIT_ENV_TOKEN)
    else:
        monkeypatch.delenv(EX.REAL_FIT_ENV_SWITCH, raising=False)
    assert EX.real_fit_is_unlocked() is False
    with pytest.raises(RuntimeError):
        EX.require_real_fit_authorization()
    assert EX.validate_run_mode(EX.RUN_MODE_AUTHORIZED_REAL)[0] is False


def test_authorized_real_requires_BOTH_locks_open(monkeypatch):
    monkeypatch.setattr(EX, "REAL_FIT_AUTHORIZED", True, raising=False)
    monkeypatch.setenv(EX.REAL_FIT_ENV_SWITCH, EX.REAL_FIT_ENV_TOKEN)
    assert EX.real_fit_is_unlocked() is True
    assert EX.validate_run_mode(EX.RUN_MODE_AUTHORIZED_REAL)[0] is True
    assert EX.validate_run_mode(EX.RUN_MODE_SYNTHETIC_PREFIT)[0] is False


def test_an_unknown_run_mode_fails_closed():
    for mode in ("real", "REAL", "authorized", "", None, "prefit"):
        assert EX.validate_run_mode(mode)[0] is False, mode


# =====================================================================================================
# The run is ALREADY HERMETIC — both inputs repo-owned and pinned
# =====================================================================================================
def test_the_weekly_snapshot_is_repo_owned_and_matches_its_pin():
    """The earlier 'no repo-owned outcome / network fetch required' claim was WRONG and is withdrawn."""
    assert ARP.WEEKLY_SNAPSHOT.exists(), f"{ARP.WEEKLY_SNAPSHOT} missing"
    assert ARP.file_sha256(ARP.WEEKLY_SNAPSHOT) == ARP.WEEKLY_SNAPSHOT_SHA256


def test_the_weekly_snapshot_provenance_matches_the_manifest():
    entry = ARP.verify_weekly_snapshot_provenance()
    assert entry["loader"] == "load_player_stats"
    assert entry["rows"] == 269_594 and entry["cols"] == 115


def test_the_feature_source_matches_the_production_pin():
    assert ARP.file_md5(ARP.FEATURE_SOURCE) == ARP.FEATURE_SOURCE_MD5


def test_no_outcome_snapshot_constant_survives():
    """The nonexistent-snapshot design is retired; nothing may still reference it."""
    for gone in ("OUTCOME_SNAPSHOT", "OUTCOME_SNAPSHOT_MD5", "OUTCOME_SNAPSHOT_COLUMNS"):
        assert not hasattr(ARP, gone), f"{gone} should have been removed"


def test_manifest_provenance_drift_is_caught(tmp_path):
    bad = tmp_path / "manifest.json"
    bad.write_text(json.dumps({ARP.WEEKLY_SNAPSHOT_MANIFEST_KEY:
                               {"sha256": "0" * 64, "loader": "load_player_stats",
                                "rows": 269_594, "cols": 115}}), encoding="utf-8")
    with pytest.raises(ARP.AssemblyError) as exc:
        ARP.verify_weekly_snapshot_provenance(bad)
    assert "sha256" in str(exc.value)


# =====================================================================================================
# A1-A6
# =====================================================================================================
def test_importing_the_module_reads_nothing():
    ok, detail = ARP.assembly_module_contract()
    assert ok is True, detail


def test_no_module_level_reader_call_exists():
    """RED before GREEN."""
    bad = ARP.assembly_module_contract(source="import pandas as pd\ndf = pd.read_csv('x.csv')\n")
    assert bad[0] is False and "module-level" in bad[1]
    good = ARP.assembly_module_contract(
        source="import pandas as pd\ndef f():\n    return pd.read_csv('x.csv')\n")
    assert good[0] is True
    assert ARP.assembly_module_contract()[0] is True


@pytest.mark.parametrize("snippet,fragment", [
    ("def f():\n    return load_player_stats(seasons=[2024])\n", "load_player_stats"),
    ("def f():\n    return load_combine()\n", "load_combine"),
    ("def f():\n    return load_draft_picks()\n", "load_draft_picks"),
    ("from urllib.request import urlopen\ndef f():\n    return urlopen('http://x')\n", "urlopen"),
])
def test_a_live_loader_is_rejected(snippet, fragment):
    bad = ARP.assembly_module_contract(source=snippet)
    assert bad[0] is False and fragment in bad[1]


# --- A2 repaired: the four evasions that used to return ok=True ------------------------------------
@pytest.mark.parametrize("label,snippet", [
    ("import alias",        "import requests as r\ndef f():\n    return r.get('http://x')\n"),
    ("from-imported get",   "from requests import get\ndef f():\n    return get('http://x')\n"),
    ("chained Session",     "import requests\ndef f():\n    return requests.Session().get('http://x')\n"),
    ("client variable",     "import requests\ndef f():\n    c = requests.Session()\n"
                            "    return c.get('http://x')\n"),
    ("direct nflreadpy",    "import nflreadpy as nfl\ndef f():\n"
                            "    return nfl.load_player_stats(seasons=[2024])\n"),
    ("httpx alias",         "import httpx as h\ndef f():\n    return h.get('http://x')\n"),
    ("socket",              "import socket\ndef f():\n    return socket.socket()\n"),
    ("from urllib",         "from urllib import request\ndef f():\n    return request\n"),
])
def test_every_network_evasion_is_rejected_by_banning_the_import(label, snippet):
    """Receiver-name matching missed all of these. Banning the IMPORT catches them regardless of alias.

    RED-BEFORE-GREEN is inherent here: each of these returned ok=True under the previous rule.
    """
    ok, detail = ARP.assembly_module_contract(source=snippet)
    assert ok is False, f"{label}: NOT rejected"
    assert "A2" in detail, detail


@pytest.mark.parametrize("snippet", [
    "def f(d):\n    return d.get('k')\n",
    "def g(cfg):\n    return cfg.get('a', 1)\n",
    "def h(client):\n    return client.get('x')\n",          # injected object, not an import
    "import json\nimport pathlib\ndef f():\n    return json.loads('{}')\n",
])
def test_the_network_check_does_not_false_positive(snippet):
    """POSITIVE CONTROLS: `dict.get`, `config.get` and non-network imports stay legal.

    Banning every callee named `get` was the same over-broad-matcher defect as `config.putenv()`
    failing C7.
    """
    ok, detail = ARP.assembly_module_contract(source=snippet)
    assert ok is True, detail


def test_canonical_source_imports_no_network_module():
    assert ARP.assembly_module_contract()[0] is True
    src = (COACH / ARP.ASSEMBLY_MODULE).read_text(encoding="utf-8")
    tree = ast.parse(src)
    roots = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            roots |= {a.name.split(".")[0] for a in n.names}
        elif isinstance(n, ast.ImportFrom):
            roots.add((n.module or "").split(".")[0])
    assert not (roots & ARP.NETWORK_ROOT_MODULES), f"network import present: {roots}"


def test_the_a2_limits_are_stated_not_hidden():
    doc = ARP.assembly_module_contract.__doc__ or ""
    for limit in ("importlib", "eval", "exec", "injected as a function argument"):
        assert limit in doc, f"A2 must state that it does not cover {limit}"


# =====================================================================================================
# §1 — ALL SEVEN shipped Arm 0 bundles
# =====================================================================================================
def test_all_seven_shipped_buckets_are_declared():
    assert len(ARP.SHIPPED_ARM0_BUCKETS) == 7
    assert ("QB", "rookie") not in ARP.SHIPPED_ARM0_BUCKETS, "the QB rookie arm was HELD"
    expected_n = {("QB", "veteran"): 32, ("RB", "veteran"): 32, ("WR", "veteran"): 32,
                  ("TE", "veteran"): 32, ("RB", "rookie"): 41, ("WR", "rookie"): 44,
                  ("TE", "rookie"): 44}
    assert {k: v[1] for k, v in ARP.SHIPPED_ARM0_BUCKETS.items()} == expected_n


def test_every_bundle_feature_count_matches_the_declared_table():
    """The previous pass pinned ONLY rb_veteran_model.pkl, which is why the omission was invisible."""
    for row in ARP.arm0_bucket_table():
        assert row["error"] is None, row["error"]
        assert row["n_features"] == row["expected_n"], (
            f"{row['position']}/{row['bucket']}: bundle has {row['n_features']} features, "
            f"table says {row['expected_n']}")
        assert row["target"] == ARP.OUTCOME_COLUMN


def test_the_veteran_buckets_are_fully_supplied_by_the_season_dataset():
    for row in ARP.arm0_bucket_table():
        if row["bucket"] == "veteran":
            assert row["complete"] is True, f"{row['position']}/veteran missing {row['missing']}"
            assert row["source"] == ARP.SOURCE_SEASON_DATASET


@pytest.mark.parametrize("pos,n_missing,n_total", [("RB", 32, 41), ("WR", 35, 44), ("TE", 35, 44)])
def test_the_rookie_buckets_have_no_repo_owned_feature_source(pos, n_missing, n_total):
    """Measured, not asserted: these counts are the reason activation is not ready."""
    row = next(r for r in ARP.arm0_bucket_table()
               if r["position"] == pos and r["bucket"] == "rookie")
    assert row["n_features"] == n_total
    assert row["complete"] is False
    assert ARP.ROOKIE_MISSING_COUNTS[(pos, "rookie")] == (n_missing, n_total)


def test_the_veteran_contract_is_named_as_veteran_scope():
    """It must not be presented as the whole Arm 0 contract again."""
    assert hasattr(ARP, "VETERAN_FEATURE_COLUMNS")
    assert ARP.VETERAN_FEATURE_COLUMNS == ARP.IDENTITY_COLUMNS + ARP.ARM0_VETERAN_FEATURES
    assert ARP.FROZEN_FEATURE_COLUMNS == ARP.VETERAN_FEATURE_COLUMNS


def test_a_bucket_frame_must_carry_every_bundle_feature_in_order():
    ARP.bucket_frame_satisfies_bundle(list(ARP.VETERAN_FEATURE_COLUMNS), "RB", "veteran")
    with pytest.raises(ARP.AssemblyError) as exc:
        ARP.bucket_frame_satisfies_bundle(list(ARP.ARM0_VETERAN_FEATURES)[:-1], "RB", "veteran")
    assert "missing" in str(exc.value)
    scrambled = list(reversed(ARP.ARM0_VETERAN_FEATURES))
    with pytest.raises(ARP.AssemblyError) as exc2:
        ARP.bucket_frame_satisfies_bundle(scrambled, "RB", "veteran")
    assert "bundle order" in str(exc2.value)
    with pytest.raises(ARP.AssemblyError) as exc3:
        ARP.bucket_frame_satisfies_bundle(list(ARP.ARM0_VETERAN_FEATURES) + ["target_ppg"],
                                          "RB", "veteran")
    assert "outcome-bearing" in str(exc3.value)


# =====================================================================================================
# §4 — activation readiness FAILS CLOSED and is separate from prefit integrity
# =====================================================================================================
def test_activation_readiness_is_currently_FALSE_and_names_the_blocked_buckets():
    ok, detail = ARP.activation_readiness()
    assert ok is False, "activation must not report ready while three bundles cannot be assembled"
    for pos in ("RB", "WR", "TE"):
        assert f"{pos}/rookie" in detail
    assert "32/41" in detail and "35/44" in detail
    assert "gitignore" in detail.lower() or "ZERO tracked" in detail


def test_activation_readiness_would_pass_if_every_bucket_had_a_source():
    """GREEN counterpart: the check is not hard-wired to fail."""
    every = set()
    for row in ARP.arm0_bucket_table(feature_columns=set()):
        every |= set(row["feature_cols"])
    ok, detail = ARP.activation_readiness(feature_columns=every)
    assert ok is False, "rookie buckets declare the rookie_matrix source, which is still empty"
    assert "RB/rookie" in detail


def test_prefit_integrity_and_activation_readiness_are_DIFFERENT_layers():
    """21/21 preflight must never be read as 'ready to activate'."""
    pf = EX.preflight(require_pipeline_assertions=False)
    assert pf["all_ok"] is True and pf["n_failed"] == 0
    ready, _ = ARP.activation_readiness()
    assert ready is False
    assert "activation_readiness" not in pf["checks"], (
        "activation readiness must stay OUT of the prefit preflight, or a blocked activation would "
        "turn the committed v3.9d checkpoint red")


def test_the_committed_prefit_checkpoint_stays_green():
    pf = EX.preflight(require_pipeline_assertions=False)
    assert pf["all_ok"] is True
    assert pf["checks"]["assembly_module_contract"]["ok"] is True


def test_the_default_readers_refuse():
    for reader in (ARP.default_feature_reader, ARP.default_outcome_reader):
        with pytest.raises(ARP.AssemblyError):
            reader()


def test_building_a_reader_does_not_read():
    assert callable(ARP.authorized_feature_reader())
    assert callable(ARP.authorized_outcome_reader())


# =====================================================================================================
# §2 — the authorized FEATURE reader, red before green
# =====================================================================================================
def _write_feature_csv(tmp_path, include_2026=True, include_forbidden=True):
    df = synthetic_features()
    if include_2026:
        extra = df[df[ARP.SEASON_KEY] == 2025].copy()
        extra[ARP.SEASON_KEY] = ARP.DEPLOY_SEASON
        df = pd.concat([df, extra], ignore_index=True)
    if include_forbidden:
        for c in ("target_ppg", "target_games", "sample_weight", "sleeper_pts_half_ppr",
                  "adp_half_ppr"):
            df[c] = 1.0
    p = tmp_path / "season_dataset_fixture.csv"
    df.to_csv(p, index=False)
    return p


def test_RED_a_naive_full_read_of_the_fixture_violates_the_validator(tmp_path):
    """RED: this is exactly what the previous reader did — read everything, return everything."""
    src = _write_feature_csv(tmp_path)
    naive = pd.read_csv(src)
    problems = ARP.validate_feature_frame(naive)
    assert problems, "the fixture must be able to fail the validator"
    joined = "; ".join(problems)
    assert "unexpected season" in joined and str(ARP.DEPLOY_SEASON) in joined
    assert "outcome-bearing" in joined


def test_GREEN_the_authorized_feature_reader_returns_only_2014_2025_and_no_forbidden_column(tmp_path):
    src = _write_feature_csv(tmp_path)
    out = ARP.authorized_feature_reader(path=src, verify_hash=False)()
    seasons = sorted(set(out[ARP.SEASON_KEY]))
    assert seasons == list(ARP.ALL_PANEL_SEASONS)
    assert ARP.DEPLOY_SEASON not in seasons
    assert not (set(out.columns) & ARP.FORBIDDEN_IN_FEATURES)
    assert list(out.columns) == list(ARP.FROZEN_FEATURE_COLUMNS)
    assert ARP.validate_feature_frame(out) == []


def test_the_feature_reader_output_passes_its_own_validator(tmp_path):
    """The gap that let a broken reader pass 663 tests: nobody ran its OUTPUT through the validator."""
    src = _write_feature_csv(tmp_path)
    out = ARP.authorized_feature_reader(path=src, verify_hash=False)()
    assert ARP.validate_feature_frame(out) == []


def test_the_feature_reader_fails_on_a_missing_frozen_column(tmp_path):
    df = synthetic_features().drop(columns=["prior_ppg"])
    p = tmp_path / "short.csv"
    df.to_csv(p, index=False)
    with pytest.raises(ARP.AssemblyError) as exc:
        ARP.authorized_feature_reader(path=p, verify_hash=False)()
    assert "missing frozen column" in str(exc.value) and "prior_ppg" in str(exc.value)


def test_the_feature_reader_fails_on_hash_drift(tmp_path):
    src = _write_feature_csv(tmp_path)
    with pytest.raises(ARP.AssemblyError) as exc:
        ARP.authorized_feature_reader(path=src, verify_hash=True)()
    assert "hash drift" in str(exc.value)


def test_the_feature_reader_enforces_unique_keys(tmp_path):
    df = synthetic_features()
    df = pd.concat([df, df.iloc[[0]]], ignore_index=True)
    p = tmp_path / "dup.csv"
    df.to_csv(p, index=False)
    with pytest.raises(ARP.AssemblyError) as exc:
        ARP.authorized_feature_reader(path=p, verify_hash=False)()
    assert "duplicate" in str(exc.value)


def test_the_frozen_feature_contract_matches_the_production_bundles():
    import pickle
    bundle = pickle.loads((COACH.parent / "models" / "rb_veteran_model.pkl").read_bytes())
    assert tuple(bundle["feature_cols"]) == ARP.ARM0_VETERAN_FEATURES
    assert bundle["target"] == ARP.OUTCOME_COLUMN


# =====================================================================================================
# §3 — production target semantics
# =====================================================================================================
def test_grouped_totals_are_REG_only_and_windowed(tmp_path):
    weekly = synthetic_weekly()
    tot = ARP.grouped_season_totals(weekly)
    assert sorted(set(tot[ARP.SEASON_KEY])) == list(ARP.ALL_PANEL_SEASONS), "2013 leaked or a year lost"
    assert set(tot.columns) == {ARP.PLAYER_KEY, ARP.SEASON_KEY, ARP.OUTCOME_COLUMN}
    assert tot.duplicated(subset=list(ARP.PANEL_KEYS)).sum() == 0


def test_postseason_never_enters_the_target():
    """POST rows carry a deliberately absurd value; if they leaked the totals would explode."""
    reg_only = synthetic_weekly(include_post=False)
    with_post = synthetic_weekly(include_post=True)
    a = ARP.grouped_season_totals(reg_only).sort_values(list(ARP.PANEL_KEYS)).reset_index(drop=True)
    b = ARP.grouped_season_totals(with_post).sort_values(list(ARP.PANEL_KEYS)).reset_index(drop=True)
    pd.testing.assert_frame_equal(a, b)


def test_the_target_formula_is_the_production_one():
    weekly = pd.DataFrame({
        ARP.PLAYER_KEY: ["00-000001"] * 2, ARP.SEASON_KEY: [2020, 2020],
        "season_type": ["REG", "REG"], "fantasy_points": [10.0, np.nan],
        "receptions": [4.0, 6.0]})
    tot = ARP.grouped_season_totals(weekly)
    # (10 + 0.5*4) + (0 + 0.5*6) = 12 + 3
    assert float(tot[ARP.OUTCOME_COLUMN].iloc[0]) == pytest.approx(15.0)


def test_weekly_schema_drift_is_caught():
    weekly = synthetic_weekly().drop(columns=["receptions"])
    with pytest.raises(ARP.AssemblyError) as exc:
        ARP.grouped_season_totals(weekly)
    assert "schema drift" in str(exc.value)


def test_PRODUCTION_EQUIVALENCE_a_rostered_player_with_no_stat_row_is_kept_with_zero(feats):
    """Production left-joins and fills pre-2026 y with 0.0. The panel must keep that row."""
    outs = synthetic_outcomes(feats, drop=4)
    out = ARP.assemble_panel_core(feats, outs)
    assert out["accounting"]["n_feature_rows"] == len(feats), "a feature row was dropped"
    assert out["accounting"][ARP.STATE_ZERO_FILLED] == 4
    zeros = out["outcomes"][out["outcomes"]["outcome_state"] == ARP.STATE_ZERO_FILLED]
    assert len(zeros) == 4
    assert (zeros[ARP.OUTCOME_COLUMN] == 0.0).all()
    assert out["outcomes"][ARP.OUTCOME_COLUMN].notna().all()


def test_no_feature_row_is_ever_silently_dropped(feats):
    for drop in (0, 1, 7, len(feats) - 1):
        out = ARP.assemble_panel_core(feats, synthetic_outcomes(feats, drop=drop))
        assert len(out["outcomes"]) == len(feats)


# =====================================================================================================
# §4 — the accounting partition is mutually exclusive and exhaustive
# =====================================================================================================
def test_the_accounting_states_partition_the_feature_rows(feats):
    outs = synthetic_outcomes(feats, drop=3)
    ghost = pd.DataFrame({ARP.PLAYER_KEY: ["00-999999"], ARP.SEASON_KEY: [2020],
                          ARP.OUTCOME_COLUMN: [1.0]})
    outs = pd.concat([outs, ghost], ignore_index=True)
    acct = ARP.assemble_panel_core(feats, outs)["accounting"]

    feature_side = (acct[ARP.STATE_MISSING_IDENTITY] + acct[ARP.STATE_ZERO_FILLED]
                    + acct[ARP.STATE_MATCHED])
    assert feature_side == acct["n_feature_rows"], "the partition does not sum to the feature rows"
    assert acct[ARP.STATE_UNMATCHED_OUTCOME] == 1
    assert acct[ARP.STATE_ZERO_FILLED] == 3


def test_the_states_cannot_overlap(feats):
    out = ARP.assemble_panel_core(feats, synthetic_outcomes(feats, drop=2))
    states = out["outcomes"]["outcome_state"]
    assert set(states) <= set(ARP.FEATURE_ROW_STATES)
    assert len(states) == len(feats)              # exactly one state per row, by construction


def test_a_null_player_id_is_missing_identity_only(feats):
    """It used to increment BOTH missing_identity and missing_outcome."""
    broken = feats.copy()
    broken.loc[0, ARP.PLAYER_KEY] = np.nan
    with pytest.raises(ARP.AssemblyError) as exc:
        ARP.assemble_panel_core(broken, synthetic_outcomes(feats))
    msg = str(exc.value)
    assert "null" in msg and ARP.PLAYER_KEY in msg
    assert ARP.STATE_ZERO_FILLED not in msg


def test_unmatched_outcome_keys_use_a_different_denominator(feats, outs):
    ghosts = pd.DataFrame({ARP.PLAYER_KEY: ["00-99999" + str(i) for i in range(3)],
                           ARP.SEASON_KEY: [2020, 2021, 2022],
                           ARP.OUTCOME_COLUMN: [1.0, 2.0, 3.0]})
    acct = ARP.assemble_panel_core(feats, pd.concat([outs, ghosts], ignore_index=True))["accounting"]
    assert acct[ARP.STATE_UNMATCHED_OUTCOME] == 3
    assert acct[ARP.STATE_MATCHED] == len(feats)
    assert acct["n_outcome_rows"] == len(outs) + 3


# =====================================================================================================
# Separation, schema, seasons
# =====================================================================================================
def test_features_and_outcomes_are_separate_objects(feats, outs):
    out = ARP.assemble_panel_core(feats, outs)
    assert ARP.OUTCOME_COLUMN not in out["features"].columns
    assert not (set(out["features"].columns) & ARP.FORBIDDEN_IN_FEATURES)
    assert list(out["outcomes"].columns) == [*ARP.PANEL_KEYS, ARP.OUTCOME_COLUMN, "outcome_state"]


@pytest.mark.parametrize("col", ["target_ppg", "target_games", "sample_weight",
                                 "sleeper_pts_half_ppr", "adp_half_ppr", "ppg"])
def test_every_forbidden_column_is_rejected_from_the_feature_frame(feats, outs, col):
    leaky = feats.copy()
    leaky[col] = 0.0
    with pytest.raises(ARP.AssemblyError) as exc:
        ARP.assemble_panel_core(leaky, outs)
    assert col in str(exc.value)


def test_a_missing_or_extra_season_fails(feats):
    trimmed = feats[feats[ARP.SEASON_KEY] != 2019]
    with pytest.raises(ARP.AssemblyError) as exc:
        ARP.assemble_panel_core(trimmed, synthetic_outcomes(trimmed))
    assert "missing season" in str(exc.value)

    extra = pd.concat([feats, feats[feats[ARP.SEASON_KEY] == 2025].assign(season=2026)],
                      ignore_index=True)
    with pytest.raises(ARP.AssemblyError) as exc2:
        ARP.assemble_panel_core(extra, synthetic_outcomes(extra))
    assert "unexpected season" in str(exc2.value)


def test_duplicate_keys_fail_on_both_sides(feats, outs):
    with pytest.raises(ARP.AssemblyError):
        ARP.assemble_panel_core(pd.concat([feats, feats.iloc[[0]]], ignore_index=True), outs)
    with pytest.raises(ARP.AssemblyError):
        ARP.assemble_panel_core(feats, pd.concat([outs, outs.iloc[[0]]], ignore_index=True))


def test_outcome_schema_drift_fails(feats, outs):
    with pytest.raises(ARP.AssemblyError) as exc:
        ARP.assemble_panel_core(feats, outs.rename(columns={ARP.OUTCOME_COLUMN: "y"}))
    assert "schema drift" in str(exc.value)


def test_assert_no_outcome_in_matrix_is_a_hard_gate():
    ARP.assert_no_outcome_in_matrix(list(ARP.ARM0_VETERAN_FEATURES))
    with pytest.raises(ARP.AssemblyError):
        ARP.assert_no_outcome_in_matrix(["prior_ppg", ARP.OUTCOME_COLUMN])
    with pytest.raises(ARP.AssemblyError):
        ARP.assert_no_outcome_in_matrix(["prior_ppg", "target_ppg"], label="ARM_3 X")


# =====================================================================================================
# §5 — full integration through BOTH authorized readers, on temporary files
# =====================================================================================================
def test_INTEGRATION_both_authorized_readers_feed_assemble_panel_core(tmp_path):
    """The end-to-end path, with the real reader code, on synthetic temporary files.

    This is the test whose absence let a reader that returned 2026 rows and forbidden target columns
    pass the entire suite: nothing ever ran the reader's OUTPUT through the assembler.
    """
    fsrc = _write_feature_csv(tmp_path, include_2026=True, include_forbidden=True)
    wsrc = tmp_path / "weekly.parquet"
    synthetic_weekly().to_parquet(wsrc, index=False)

    features = ARP.authorized_feature_reader(path=fsrc, verify_hash=False)()
    outcomes = ARP.authorized_outcome_reader(path=wsrc, verify_hash=False,
                                             verify_manifest=False)()

    out = ARP.assemble_panel_core(features, outcomes)
    assert out["seasons"] == tuple(ARP.ALL_PANEL_SEASONS)
    assert out["accounting"]["n_feature_rows"] == len(features)
    assert not (set(out["features"].columns) & ARP.FORBIDDEN_IN_FEATURES)
    assert out["outcomes"][ARP.OUTCOME_COLUMN].notna().all()
    partition = sum(out["accounting"][s] for s in ARP.FEATURE_ROW_STATES)
    assert partition == out["accounting"]["n_feature_rows"]


def test_INTEGRATION_a_player_absent_from_weekly_stats_survives_with_zero(tmp_path):
    fsrc = _write_feature_csv(tmp_path, include_2026=False, include_forbidden=False)
    wsrc = tmp_path / "weekly_missing.parquet"
    weekly = synthetic_weekly(players=5)          # feature fixture has 6 players
    weekly.to_parquet(wsrc, index=False)

    features = ARP.authorized_feature_reader(path=fsrc, verify_hash=False)()
    outcomes = ARP.authorized_outcome_reader(path=wsrc, verify_hash=False, verify_manifest=False)()
    out = ARP.assemble_panel_core(features, outcomes)

    assert out["accounting"][ARP.STATE_ZERO_FILLED] == len(ARP.ALL_PANEL_SEASONS)
    zeros = out["outcomes"][out["outcomes"]["outcome_state"] == ARP.STATE_ZERO_FILLED]
    assert (zeros[ARP.OUTCOME_COLUMN] == 0.0).all()
    assert len(out["outcomes"]) == len(features)


def test_the_real_reader_is_never_called_in_synthetic_prefit(feats, outs):
    calls = []

    def _tripwire(*_a, **_k):
        calls.append("READ")
        raise AssertionError("a real reader ran during synthetic_prefit")

    saved = (ARP.authorized_feature_reader, ARP.authorized_outcome_reader)
    ARP.authorized_feature_reader = _tripwire
    ARP.authorized_outcome_reader = _tripwire
    try:
        ARP.assemble_panel_core(feats, outs)
    finally:
        ARP.authorized_feature_reader, ARP.authorized_outcome_reader = saved
    assert calls == []

    pf = EX.preflight(require_pipeline_assertions=False)
    assert pf["all_ok"] is True
    assert pf["checks"]["assembly_module_contract"]["ok"] is True


def test_authorization_must_precede_the_reader_in_the_activation_path():
    src = (COACH / "run_coach_projection_experiment_v39.py").read_text(encoding="utf-8")
    fn = next(n for n in ast.walk(ast.parse(src))
              if isinstance(n, ast.FunctionDef) and n.name == "assemble_real_panel")
    body = [s for s in fn.body if not (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant))]
    assert isinstance(body[0], ast.Expr) and body[0].value.func.id == "require_real_fit_authorization"
    assert isinstance(body[1], ast.Raise)


# =====================================================================================================
# Nothing in this pass may touch production or the artifacts
# =====================================================================================================
def test_the_assembly_module_writes_nothing():
    tree = ast.parse((COACH / ARP.ASSEMBLY_MODULE).read_text(encoding="utf-8"))
    writers = [(getattr(n.func, "attr", getattr(n.func, "id", None)), n.lineno)
               for n in ast.walk(tree) if isinstance(n, ast.Call)
               and getattr(n.func, "attr", getattr(n.func, "id", None))
               in ("to_csv", "to_parquet", "write_text", "write_bytes", "savefig", "dump")]
    assert not writers, f"the assembly module writes: {writers}"


def test_design_b_remains_oracle_only_and_unselectable():
    pf = EX.preflight(require_pipeline_assertions=False)
    assert pf["checks"]["design_b_oracle_and_unselectable"]["ok"] is True


def test_artifacts_and_production_untouched():
    pf = EX.preflight(require_pipeline_assertions=False)
    for check in ("v39_artifacts_pinned", "protected_hashes", "production_models_identical",
                  "no_unauthorized_v39_artifact", "no_coaching_parquet"):
        assert pf["checks"][check]["ok"] is True, pf["checks"][check]["detail"]
