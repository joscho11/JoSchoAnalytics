"""Tests for the real-panel assembly path.

No real outcome VALUE is read, printed, aggregated or compared anywhere here. Fixtures are synthetic
frames and temporary files written by the tests themselves. The two authorized readers ARE invoked —
against temporary synthetic files — because the previous revision never ran the real feature reader's
output through its own validator, which is exactly why a reader that returned 2026 rows and forbidden
target columns passed all 663 tests.
"""
import ast
import contextlib
import hashlib
import inspect
import json
import pathlib
import re
import sys

import numpy as np
import pandas as pd
import pytest

COACH = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(COACH))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import arm0_bundle_pins as PINS                            # noqa: E402  independent frozen literals
import assemble_real_panel_v39 as ARP                      # noqa: E402
import run_coach_projection_experiment_v39 as EX           # noqa: E402


def _pool_sha(feature_cols):
    return hashlib.sha256("\n".join(feature_cols).encode("utf-8")).hexdigest()


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
    # C5-A: three statements, authorization -> clearance -> return; the seal moved, it did not go.
    assert len(fn.body) == 3
    assert fn.body[1].value.func.id == EX.PREFLIGHT_CLEARANCE_NAME
    assert isinstance(fn.body[2], ast.Return)
    assert not EX._entry_point_is_sealed(tree)
    assert EX._entry_point_is_sealed(tree, contract_mode=EX.RUN_MODE_SYNTHETIC_PREFIT), (
        'C5-S must reject the implemented door, or the two contracts are interchangeable')


def test_assemble_real_panel_still_raises_with_both_locks_closed():
    """The door is implemented now, so it takes injected readers — and must refuse before either."""
    calls = []

    def _tripwire(name):
        def _r():
            calls.append(name)
            raise AssertionError(f"the {name} reader RAN")
        return _r

    assert EX.real_fit_lock_state() == (False, False)
    with pytest.raises(RuntimeError) as exc:
        EX.assemble_real_panel(_tripwire("feature"), _tripwire("outcome"))
    assert "NOT AUTHORIZED" in str(exc.value)
    assert calls == [], "a reader ran with both locks closed"


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
    """SUPERSEDED ROUTE (v3.9v): this used to monkeypatch `REAL_FIT_AUTHORIZED = True`, which no
    longer authorizes anything. Both locks are now the two exact tokens, presented together, which
    mint an invocation-scoped capability."""
    auth = EX.grant_real_fit_authorization(
        EX.REAL_FIT_CLI_TOKEN, env={EX.REAL_FIT_ENV_SWITCH: EX.REAL_FIT_ENV_TOKEN})
    assert EX.real_fit_is_unlocked(auth) is True
    assert EX.validate_run_mode(EX.RUN_MODE_AUTHORIZED_REAL, authorization=auth)[0] is True
    assert EX.validate_run_mode(EX.RUN_MODE_SYNTHETIC_PREFIT, authorization=auth)[0] is False

    # and the retired route is genuinely dead
    monkeypatch.setattr(EX, "REAL_FIT_AUTHORIZED", True, raising=False)
    monkeypatch.setenv(EX.REAL_FIT_ENV_SWITCH, EX.REAL_FIT_ENV_TOKEN)
    assert EX.real_fit_is_unlocked() is False
    assert EX.validate_run_mode(EX.RUN_MODE_AUTHORIZED_REAL)[0] is False


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
    # SUPERSEDED SCOPE (2026-08-03): this pinned the whole LIVE production CSV, so an ordinary
    # deploy-season-2026 refresh moved the hash and refused activation for a reason unrelated
    # to the experiment. The consumed 2014-2025 window is now an immutable snapshot, and THAT
    # is what is pinned. The CSV is the generator's input only.
    assert ARP.file_sha256(ARP.VETERAN_SNAPSHOT) == ARP.VETERAN_SNAPSHOT_SHA256
    assert not hasattr(ARP, "FEATURE_SOURCE_MD5"), (
        "the whole-CSV md5 pin must be gone, not merely unused")


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


# --- §3: every shipped bundle pinned INDEPENDENTLY -------------------------------------------------
# The pins live in `arm0_bundle_pins.py` as literals transcribed once. Nothing below re-reads the
# bundle to build its own expectation, so reordering / replacing / adding / deleting a feature fails.
@pytest.mark.parametrize("key", sorted(PINS.BUNDLE_FEATURE_PINS), ids=lambda k: f"{k[0]}-{k[1]}")
def test_every_shipped_bundle_matches_its_independent_pin(key):
    import pickle
    pin = PINS.BUNDLE_FEATURE_PINS[key]
    path = COACH.parent / "models" / pin["bundle"]
    assert path.exists(), path
    b = pickle.loads(path.read_bytes())
    fc = tuple(b["feature_cols"])
    assert fc == pin["feature_cols"], (
        f"{key} ordered feature_cols differ from the frozen pin "
        f"(bundle n={len(fc)}, pin n={len(pin['feature_cols'])})")
    assert len(fc) == pin["n"]
    assert b.get("target") == pin["target"] == ARP.OUTCOME_COLUMN
    assert _pool_sha(fc) == pin["sha256"]


@pytest.mark.parametrize("key", sorted(PINS.BUNDLE_FEATURE_PINS), ids=lambda k: f"{k[0]}-{k[1]}")
@pytest.mark.parametrize("mutation", ["reorder", "replace", "add", "delete"])
def test_mutating_any_bundle_pool_fails_the_pin(key, mutation):
    """RED: the pin must reject each of the four ways a pool can drift."""
    pin = PINS.BUNDLE_FEATURE_PINS[key]
    fc = list(pin["feature_cols"])
    if mutation == "reorder":
        fc[0], fc[1] = fc[1], fc[0]
    elif mutation == "replace":
        fc[0] = "some_other_feature"
    elif mutation == "add":
        fc.append("an_extra_feature")
    elif mutation == "delete":
        fc.pop()
    mutated = tuple(fc)
    assert mutated != pin["feature_cols"]
    assert _pool_sha(mutated) != pin["sha256"], f"{mutation} was not detected by the pin"


def test_the_pins_cover_exactly_the_seven_shipped_buckets():
    assert set(PINS.BUNDLE_FEATURE_PINS) == set(ARP.SHIPPED_ARM0_BUCKETS)
    for key, pin in PINS.BUNDLE_FEATURE_PINS.items():
        assert pin["bundle"] == ARP.SHIPPED_ARM0_BUCKETS[key][0]
        assert pin["n"] == ARP.SHIPPED_ARM0_BUCKETS[key][1]


def test_the_veteran_buckets_are_fully_supplied_by_the_season_dataset():
    for row in ARP.arm0_bucket_table():
        if row["bucket"] == "veteran":
            assert row["complete"] is True, row["missing_from_declared_source"]
            assert row["source"] == ARP.SOURCE_SEASON_DATASET
            assert row["n_missing_from_season_dataset"] == 0


# --- §2: the missing counts are DERIVED from the real header, then asserted ------------------------
@pytest.mark.parametrize("pos,expected_missing,n_total",
                         [("RB", 32, 41), ("WR", 35, 44), ("TE", 35, 44)])
def test_the_rookie_missing_counts_are_derived_not_asserted(pos, expected_missing, n_total):
    """Recompute from the bundle's own feature_cols and the REAL CSV header, then check the figure.

    The previous test compared one hard-coded constant to another hard-coded claim, which proves
    nothing. This reads the actual header (column NAMES only, zero data rows) and the actual bundle.
    """
    import pickle
    header = set(pd.read_csv(ARP.FEATURE_SOURCE, nrows=0).columns)
    pin = PINS.BUNDLE_FEATURE_PINS[(pos, "rookie")]
    fc = tuple(pickle.loads((COACH.parent / "models" / pin["bundle"]).read_bytes())["feature_cols"])
    derived = [c for c in fc if c not in header]

    assert len(fc) == n_total
    assert len(derived) == expected_missing, (
        f"{pos}/rookie: derived {len(derived)} missing from the season dataset, expected "
        f"{expected_missing}")
    # the module's recorded figure and the pin must agree with the derivation
    assert ARP.ROOKIE_MISSING_FROM_SEASON_DATASET[(pos, "rookie")] == (expected_missing, n_total)
    assert pin["n_missing_from_season_dataset"] == expected_missing
    row = next(r for r in ARP.arm0_bucket_table()
               if r["position"] == pos and r["bucket"] == "rookie")
    assert row["n_missing_from_season_dataset"] == expected_missing


# --- §1: the two missingness concepts stay apart ---------------------------------------------------
def test_the_two_missingness_concepts_are_separate_fields():
    """Still two different denominators, and now the rookie rows PROVE it rather than coinciding.

    The rookie matrix supplies every rookie feature, so `n_missing_from_declared_source` is 0 while
    `n_missing_from_season_dataset` stays 32/35 — the same two numbers that were once printed together
    as if they meant the same thing.
    """
    for row in ARP.arm0_bucket_table():
        assert "n_missing_from_season_dataset" in row
        assert "n_missing_from_declared_source" in row
        assert row["source_exists"] is True
        assert row["n_missing_from_declared_source"] == 0
        if row["bucket"] == "veteran":
            # the declared source IS the season dataset, so both are 0 and coincide
            assert row["n_missing_from_season_dataset"] == 0
        else:
            expected = ARP.ROOKIE_MISSING_FROM_SEASON_DATASET[(row["position"], "rookie")][0]
            assert row["n_missing_from_season_dataset"] == expected > 0
            assert row["n_missing_from_season_dataset"] < row["n_features"]


def test_the_two_concepts_STILL_stay_apart_when_the_rookie_source_is_absent():
    """The v3.9h property, kept alive by injecting the absent-source state it was written for."""
    for row in ARP.arm0_bucket_table(rookie_columns=set()):
        if row["bucket"] == "veteran":
            assert row["n_missing_from_season_dataset"] == row["n_missing_from_declared_source"] == 0
        else:
            assert row["source_exists"] is False
            assert row["n_missing_from_declared_source"] == row["n_features"]
            assert row["n_missing_from_season_dataset"] < row["n_features"]


def test_the_readiness_message_is_internally_consistent():
    """It must not print '32/41' and '41/41' as if they were the same denominator."""
    ok, detail = ARP.activation_readiness(rookie_columns=set())
    assert ok is False
    assert "DOES NOT EXIST" in detail
    for pos, (missing, total) in ARP.ROOKIE_MISSING_FROM_SEASON_DATASET.items():
        assert f"lacks {missing} of {total}" in detail, (pos, detail)
    assert "41/41" not in detail and "44/44" not in detail, (
        "the absent-source case must not be reported as a feature-overlap ratio")


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
def test_activation_readiness_FAILS_CLOSED_when_the_rookie_source_is_absent():
    """The v3.9g behaviour, kept as a live RED case by injecting an empty rookie source.

    It stopped being the state of the tree on 2026-08-03 (Option A), so the absent-source state is
    injected rather than observed — otherwise the fail-closed path would silently stop being tested.
    """
    ok, detail = ARP.activation_readiness(rookie_columns=set())
    assert ok is False, "activation must not report ready while three bundles cannot be assembled"
    for pos in ("RB", "WR", "TE"):
        assert f"{pos}/rookie" in detail
    assert "lacks 32 of 41" in detail and "lacks 35 of 44" in detail


def test_activation_readiness_is_TRUE_on_all_seven_buckets():
    """TWICE SUPERSEDED, and this is the current state.

    v3.9g-v3.9m: False, no rookie source at all. v3.9n: briefly True on a leaked matrix. v3.9o: False
    again on a "the bundles were trained on contaminated features" blocker that rested on a FALSE
    PREMISE — `fit_predict` builds a fresh estimator every fold and the serialized weights never enter
    (see `test_arm0_refits_from_scratch_v39.py`). That blocker is WITHDRAWN, so readiness is True: all
    seven buckets have a complete, pinned, point-in-time feature source and a well-formed spec.
    """
    ok, detail = ARP.activation_readiness()
    assert ok is True, detail
    assert "all 7 shipped Arm 0 buckets" in detail
    assert ARP.SOURCE_ROOKIE_MATRIX in detail and ARP.SOURCE_SEASON_DATASET in detail
    assert "NOT AUTHORIZED" in detail
    assert EX.real_fit_lock_state() == (False, False)


def test_readiness_still_FAILS_CLOSED_on_a_malformed_bundle_spec():
    """RED counterpart: the check is not hard-wired to pass. Injected; no bundle is modified."""
    saved = ARP.bundle_spec_problems
    ARP.bundle_spec_problems = lambda b: ["injected: spec field 'seed' is absent"]
    try:
        ok, detail = ARP.activation_readiness()
    finally:
        ARP.bundle_spec_problems = saved
    assert ok is False
    assert "bundle SPECIFICATION is not" in detail and "seed" in detail
    assert ARP.activation_readiness()[0] is True


def test_prefit_integrity_and_activation_readiness_are_DIFFERENT_layers():
    """21/21 preflight must never be read as 'ready to activate', in EITHER direction.

    Readiness turning True must not make the prefit checkpoint mean more than it did, and readiness
    turning False must not turn the committed v3.9d checkpoint red. The layering is what is under
    test, not the current value of either layer.
    """
    pf = EX.preflight(require_pipeline_assertions=False)
    assert pf["all_ok"] is True and pf["n_failed"] == 0
    assert ARP.activation_readiness()[0] is True
    assert ARP.activation_readiness(rookie_columns=set())[0] is False
    assert "activation_readiness" not in pf["checks"], (
        "activation readiness must stay OUT of the prefit preflight, or a blocked activation would "
        "turn the committed v3.9d checkpoint red")
    # and a blocked readiness leaves preflight untouched
    assert EX.preflight(require_pipeline_assertions=False)["n_failed"] == 0


def _all_bundle_features():
    every = set()
    for row in ARP.arm0_bucket_table(feature_columns=set()):
        every |= set(row["feature_cols"])
    return every


@contextlib.contextmanager
def _readiness_injected_pass():
    """Make gate 2 pass using ONLY injected state. Canonical files are never modified."""
    patched = dict(ARP.SHIPPED_ARM0_BUCKETS)
    for key in (("RB", "rookie"), ("WR", "rookie"), ("TE", "rookie")):
        b, n, _src = patched[key]
        patched[key] = (b, n, ARP.SOURCE_SEASON_DATASET)
    saved = ARP.SHIPPED_ARM0_BUCKETS
    ARP.SHIPPED_ARM0_BUCKETS = patched
    try:
        yield _all_bundle_features()
    finally:
        ARP.SHIPPED_ARM0_BUCKETS = saved


def _authorized_shaped_preflight(**overrides):
    """A preflight result SHAPED as an authorized-real pass, matching the REAL emitted schema.

    Measured from `preflight()`: `failures` is an empty DICT (not an integer, not a list), `n_checks`
    is an int, and each `checks` value is a dict carrying `ok` and `detail`.
    """
    pf = {
        "all_ok": True,
        "run_mode": ARP.AUTHORIZED_RUN_MODE,
        "n_checks": len(ARP.FROZEN_AUTHORIZED_PREFLIGHT_CHECKS),
        "n_failed": 0,
        "failures": {},
        "checks": {name: {"ok": True, "detail": "synthetic fixture"}
                   for name in ARP.FROZEN_AUTHORIZED_PREFLIGHT_CHECKS},
    }
    pf.update(overrides)
    return pf


def test_the_authorized_real_gate_needs_BOTH_and_currently_REFUSES():
    """The real tree: preflight is 21/21, readiness is now True, and the run STILL fails closed.

    Before Option A the refusal came from gate 2. It now comes from gate 1 — the result is a
    `synthetic_prefit` one, whose whole meaning is that both locks are closed. The refusal moved; it
    did not weaken.
    """
    pf = EX.preflight(require_pipeline_assertions=False)
    assert pf["all_ok"] is True and pf["n_failed"] == 0
    assert ARP.activation_readiness()[0] is True
    ok, detail = ARP.authorized_real_gate(pf)
    assert ok is False
    # Gate 2 is CLEAR; the refusal is gate 1 alone, because the result is a synthetic_prefit one,
    # whose whole meaning is that both locks are closed.
    assert "gate 1" in detail and "BOTH LOCKS CLOSED" in detail
    assert "gate 2" not in detail, f"gate 2 must be clear; it said: {detail}"
    assert EX.real_fit_lock_state() == (False, False)


def test_the_gate_still_refuses_on_gate_2_when_readiness_is_blocked():
    """Gate 2's refusal path stays exercised, via an injected empty rookie source."""
    ok, detail = ARP.authorized_real_gate(_authorized_shaped_preflight(), rookie_columns=set())
    assert ok is False
    assert "gate 2" in detail and "ACTIVATION NOT READY" in detail


# --- RED: the two reproduced fail-opens ------------------------------------------------------------
def test_RED_a_preflight_with_only_all_ok_is_refused():
    """`{"all_ok": True}` used to pass gate 1: absent keys are falsy, which read as 'no failures'."""
    with _readiness_injected_pass() as every:
        ok, detail = ARP.authorized_real_gate({"all_ok": True}, feature_columns=every)
    assert ok is False, "a preflight result with no run_mode/n_checks/n_failed/checks was accepted"
    for expected in ("run_mode", "n_checks", "n_failed", "checks"):
        assert expected in detail, f"the refusal must name the missing {expected}"


def test_RED_a_synthetic_prefit_result_can_never_authorize_a_real_run():
    """The serious one: the REAL 21/21 synthetic_prefit result used to authorize a real run.

    That result's whole meaning is that BOTH LOCKS ARE CLOSED.
    """
    pf = EX.preflight(require_pipeline_assertions=False)
    assert pf["run_mode"] == ARP.SYNTHETIC_RUN_MODE
    assert pf["all_ok"] is True and pf["n_failed"] == 0 and pf["n_checks"] == 21
    assert EX.real_fit_lock_state() == (False, False)
    with _readiness_injected_pass() as every:
        ok, detail = ARP.authorized_real_gate(pf, feature_columns=every)
    assert ok is False, "a synthetic_prefit preflight authorized a REAL run"
    assert "BOTH LOCKS CLOSED" in detail


@pytest.mark.parametrize("label,overrides", [
    ("missing run_mode",    {"run_mode": None}),
    ("missing n_checks",    {"n_checks": None}),
    ("missing n_failed",    {"n_failed": None}),
    ("missing checks",      {"checks": None}),
    ("wrong check count",   {"n_checks": 20}),
    ("n_failed nonzero",    {"n_failed": 1}),
    ("n_failed True",       {"n_failed": True}),      # bool is an int subclass; must not slip through
    ("all_ok truthy str",   {"all_ok": "yes"}),
    ("failures nonzero",    {"failures": ["protected_hashes"]}),
    ("checks not a dict",   {"checks": ["a", "b"]}),
    ("checks missing one",  {"checks": {n: {"ok": True} for n in EX.PREFLIGHT_CHECKS[:-1]}}),
    ("checks extra entry",  {"checks": {**{n: {"ok": True} for n in EX.PREFLIGHT_CHECKS},
                                        "bonus": {"ok": True}}}),
])
def test_RED_every_malformed_or_contradictory_preflight_is_refused(label, overrides):
    with _readiness_injected_pass() as every:
        ok, detail = ARP.authorized_real_gate(_authorized_shaped_preflight(**overrides),
                                              feature_columns=every)
    assert ok is False, f"{label} was accepted"
    assert "gate 1" in detail


def test_RED_one_check_false_while_all_ok_is_true_is_refused():
    """A contradictory result: the summary says pass, a check says fail."""
    checks = {n: {"ok": True} for n in EX.PREFLIGHT_CHECKS}
    checks["protected_hashes"] = {"ok": False, "detail": "18/18 mismatch"}
    with _readiness_injected_pass() as every:
        ok, detail = ARP.authorized_real_gate(_authorized_shaped_preflight(checks=checks),
                                              feature_columns=every)
    assert ok is False
    assert "not explicitly ok" in detail and "protected_hashes" in detail


@pytest.mark.parametrize("bad", [None, {}, [], "authorized_real", 21,
                                 {"all_ok": None}, {"n_failed": 0}])
def test_RED_a_non_dict_or_empty_preflight_is_refused(bad):
    with _readiness_injected_pass() as every:
        ok, _ = ARP.authorized_real_gate(bad, feature_columns=every)
    assert ok is False, f"{bad!r} was accepted"


@pytest.mark.parametrize("constant_open,env_open", [(False, False), (True, False), (False, True)])
def test_RED_a_partial_or_closed_lock_state_cannot_produce_an_authorizing_preflight(
        monkeypatch, constant_open, env_open):
    """The lock contract is represented THROUGH the preflight result: only both-open yields
    run_mode='authorized_real', and `validate_run_mode` refuses every other combination."""
    monkeypatch.setattr(EX, "REAL_FIT_AUTHORIZED", constant_open, raising=False)
    if env_open:
        monkeypatch.setenv(EX.REAL_FIT_ENV_SWITCH, EX.REAL_FIT_ENV_TOKEN)
    else:
        monkeypatch.delenv(EX.REAL_FIT_ENV_SWITCH, raising=False)

    ok_mode, _ = EX.validate_run_mode(EX.RUN_MODE_AUTHORIZED_REAL)
    assert ok_mode is False, "a partial/closed lock state must not validate as authorized_real"

    pf = EX.preflight(require_pipeline_assertions=False)
    assert pf["run_mode"] != ARP.AUTHORIZED_RUN_MODE
    with _readiness_injected_pass() as every:
        ok, detail = ARP.authorized_real_gate(pf, feature_columns=every)
    assert ok is False and "run_mode" in detail


# --- GREEN: the positive control -------------------------------------------------------------------
def test_GREEN_an_authorized_shaped_preflight_plus_readiness_passes():
    """Proves the gate is not hard-wired to refuse.

    The preflight result is CONSTRUCTED in authorized-real shape; no lock is opened and nothing on the
    real tree changes. The REAL preflight still refuses afterwards, because it is synthetic_prefit.
    """
    with _readiness_injected_pass() as every:
        ok, detail = ARP.authorized_real_gate(_authorized_shaped_preflight(), feature_columns=every)
    assert ok is True, detail
    assert "both gates clear" in detail
    assert ARP.AUTHORIZED_RUN_MODE in detail

    real = EX.preflight(require_pipeline_assertions=False)
    assert ARP.authorized_real_gate(real)[0] is False, "the real tree must still be refused"
    assert EX.real_fit_lock_state() == (False, False), "no lock may have been opened"


def test_the_gate_refuses_when_only_gate_1_is_clear():
    """Authorized-shaped preflight, but a blocked readiness (injected empty rookie source)."""
    ok, detail = ARP.authorized_real_gate(_authorized_shaped_preflight(), rookie_columns=set())
    assert ok is False and "gate 2" in detail


# =====================================================================================================
# The frozen authorization VOCABULARY is not caller-controlled
# =====================================================================================================
def test_the_frozen_authorization_vocabulary_matches_the_harness():
    """The literal tuple in the assembly module must equal the harness's canonical PREFLIGHT_CHECKS.

    Pinned by VALUE and in order. The gate uses only this tuple; the harness list is the thing it must
    agree with, and this test is the only place the two are compared.
    """
    assert ARP.FROZEN_AUTHORIZED_PREFLIGHT_CHECKS == tuple(EX.PREFLIGHT_CHECKS)
    assert len(ARP.FROZEN_AUTHORIZED_PREFLIGHT_CHECKS) == 21
    assert len(set(ARP.FROZEN_AUTHORIZED_PREFLIGHT_CHECKS)) == 21, "duplicate check name"


def test_the_gate_exposes_no_parameter_that_can_change_the_vocabulary():
    """RED: `expected_checks=()` used to authorize a real run on '0/0 checks'."""
    sig = inspect.signature(ARP.authorized_real_gate)
    assert "expected_checks" not in sig.parameters, (
        "the gate must not accept a caller-supplied vocabulary")
    vsig = inspect.signature(ARP.validate_authorized_preflight)
    assert list(vsig.parameters) == ["preflight_result"], (
        f"the validator must take only the result; got {list(vsig.parameters)}")
    with pytest.raises(TypeError):
        ARP.authorized_real_gate(_authorized_shaped_preflight(), expected_checks=())


@pytest.mark.parametrize("label,checks,n_checks", [
    ("empty vocabulary", {}, 0),
    ("subset", {n: {"ok": True} for n in ARP.FROZEN_AUTHORIZED_PREFLIGHT_CHECKS[:5]}, 5),
    ("subset claiming 21", {n: {"ok": True} for n in ARP.FROZEN_AUTHORIZED_PREFLIGHT_CHECKS[:5]}, 21),
    ("replaced names", {f"fake_{i}": {"ok": True} for i in range(21)}, 21),
    ("extended", {**{n: {"ok": True} for n in ARP.FROZEN_AUTHORIZED_PREFLIGHT_CHECKS},
                  "bonus_check": {"ok": True}}, 22),
])
def test_RED_an_attempted_vocabulary_substitution_is_refused(label, checks, n_checks):
    with _readiness_injected_pass() as every:
        ok, detail = ARP.authorized_real_gate(
            _authorized_shaped_preflight(checks=checks, n_checks=n_checks), feature_columns=every)
    assert ok is False, f"{label} was accepted"
    assert "gate 1" in detail


def test_RED_a_reordered_vocabulary_is_still_the_same_SET_and_passes_by_design():
    """Order of the dict keys is not meaningful; the SET and the count are. Stated, not assumed."""
    reordered = {n: {"ok": True}
                 for n in reversed(ARP.FROZEN_AUTHORIZED_PREFLIGHT_CHECKS)}
    with _readiness_injected_pass() as every:
        ok, _ = ARP.authorized_real_gate(_authorized_shaped_preflight(checks=reordered),
                                         feature_columns=every)
    assert ok is True, "a dict with the same keys in another insertion order is the same vocabulary"


# =====================================================================================================
# Malformed shapes must REFUSE, never raise
# =====================================================================================================
@pytest.mark.parametrize("label,value", [
    ("True", True), ("None", None), ("string", "ok"), ("list", ["ok"]),
    ("empty dict", {}), ("int", 1), ("dict without ok", {"detail": "x"}),
    ("ok truthy string", {"ok": "yes"}), ("ok 1", {"ok": 1}),
])
def test_RED_a_malformed_check_VALUE_refuses_and_never_raises(label, value):
    """`checks={"protected_hashes": True}` used to raise AttributeError. A crash is not a refusal."""
    checks = {n: {"ok": True} for n in ARP.FROZEN_AUTHORIZED_PREFLIGHT_CHECKS}
    checks["protected_hashes"] = value
    with _readiness_injected_pass() as every:
        ok, detail = ARP.authorized_real_gate(_authorized_shaped_preflight(checks=checks),
                                              feature_columns=every)
    assert ok is False, f"check value {label} was accepted"
    assert isinstance(detail, str) and detail


@pytest.mark.parametrize("label,pf", [
    ("failures MISSING", {k: v for k, v in _authorized_shaped_preflight().items()
                          if k != "failures"}),
    ("failures None", _authorized_shaped_preflight(failures=None)),
    ("failures []", _authorized_shaped_preflight(failures=[])),
    ("failures False", _authorized_shaped_preflight(failures=False)),
    ("failures True", _authorized_shaped_preflight(failures=True)),
    ("failures 0 (int)", _authorized_shaped_preflight(failures=0)),
    ("failures 3", _authorized_shaped_preflight(failures=3)),
    ("failures nonempty dict", _authorized_shaped_preflight(failures={"protected_hashes": "bad"})),
    ("failures nonempty list", _authorized_shaped_preflight(failures=["protected_hashes"])),
    ("checks MISSING", {k: v for k, v in _authorized_shaped_preflight().items() if k != "checks"}),
    ("n_checks True", _authorized_shaped_preflight(n_checks=True)),
    ("n_failed True", _authorized_shaped_preflight(n_failed=True)),
    ("n_checks MISSING", {k: v for k, v in _authorized_shaped_preflight().items()
                          if k != "n_checks"}),
])
def test_RED_every_schema_violation_refuses_and_never_raises(label, pf):
    with _readiness_injected_pass() as every:
        ok, detail = ARP.authorized_real_gate(pf, feature_columns=every)
    assert ok is False, f"{label} was accepted"
    assert isinstance(detail, str) and "gate 1" in detail


def test_the_frozen_failures_schema_matches_what_preflight_actually_emits():
    """MEASURED, not assumed: the real preflight emits `failures` as an EMPTY DICT, not integer 0."""
    real = EX.preflight(require_pipeline_assertions=False)
    assert "failures" in real
    assert isinstance(real["failures"], dict), (
        f"failures is {type(real['failures']).__name__}; the frozen schema must match the emitter")
    assert real["failures"] == {}
    assert isinstance(real["n_checks"], int) and not isinstance(real["n_checks"], bool)
    for name, entry in real["checks"].items():
        assert isinstance(entry, dict) and "ok" in entry, f"{name} entry is not a dict with ok"


def test_the_positive_control_uses_the_real_emitted_schema():
    """The GREEN fixture must be shaped like the real thing, or it proves nothing."""
    real = EX.preflight(require_pipeline_assertions=False)
    fixture = _authorized_shaped_preflight()
    assert set(fixture) <= set(real) | {"failures"}
    assert type(fixture["failures"]) is type(real["failures"])
    assert type(fixture["n_checks"]) is type(real["n_checks"])
    assert type(fixture["n_failed"]) is type(real["n_failed"])
    for entry in fixture["checks"].values():
        assert isinstance(entry, dict) and entry["ok"] is True


def test_no_adversarial_input_ever_raises_out_of_the_gate():
    """Sweep: nothing in the corpus may propagate an exception."""
    corpus = [None, {}, [], "x", 0, True, set(), object(),
              {"all_ok": True},
              {"all_ok": True, "run_mode": ARP.AUTHORIZED_RUN_MODE, "n_checks": 0, "n_failed": 0,
               "failures": 0, "checks": {}},
              _authorized_shaped_preflight(checks=True),
              _authorized_shaped_preflight(checks={"protected_hashes": True}),
              _authorized_shaped_preflight(failures=object()),
              _authorized_shaped_preflight(n_checks="21"),
              ]
    for pf in corpus:
        try:
            ok, detail = ARP.authorized_real_gate(pf)
        except Exception as exc:                      # noqa: BLE001 - that is the finding
            raise AssertionError(f"the gate RAISED {type(exc).__name__} on {pf!r}") from exc
        assert ok is False and isinstance(detail, str)


def test_the_gate_refuses_when_only_gate_2_is_clear():
    with _readiness_injected_pass() as every:
        ok, detail = ARP.authorized_real_gate(_authorized_shaped_preflight(all_ok=False),
                                              feature_columns=every)
    assert ok is False and "gate 1" in detail


# =====================================================================================================
# §5 — the MANIFEST must actually state the gate requirements (it previously did not)
# =====================================================================================================
MANIFEST = COACH / "V39_ACTIVATION_MANIFEST.md"


def test_the_manifest_states_the_required_activation_gates():
    """A prior report claimed these were mandatory in the manifest while the manifest was silent."""
    text = MANIFEST.read_text(encoding="utf-8")
    required = [
        "preflight() returns 21/21 IN `authorized_real` MODE",
        "activation_readiness() == True",
        "authorized_real_gate()` MUST execute and return `True` BEFORE any outcome reader",
        "can never** authorize a real run",
    ]
    missing = [r for r in required if r.replace("`", "") not in text.replace("`", "")]
    assert not missing, f"the manifest is missing required gate language: {missing}"


def test_the_manifest_lists_readiness_failure_as_a_stop_condition():
    text = MANIFEST.read_text(encoding="utf-8")
    stop = text.split("## 7.")[1].split("## 8.")[0] if "## 7." in text else ""
    assert "activation_readiness()` returns False".replace("`", "") in stop.replace("`", ""), \
        "readiness failure must be a §7 stop condition"
    assert "authorized_real_gate()` returns False".replace("`", "") in stop.replace("`", ""), \
        "gate failure must be a §7 stop condition"


def test_the_manifest_still_records_the_run_as_not_executed_and_not_authorized():
    """SUPERSEDED FACT, 2026-08-03: the manifest used to be required to say 'NOT READY'.

    Option A made `activation_readiness()` True, so demanding that phrase would force the document to
    state something false. What must remain true is the part that actually protects the run: it has not
    been executed, it is not authorized, and the locks are closed. The readiness value is checked
    against the module, not against prose.
    """
    text = MANIFEST.read_text(encoding="utf-8")
    plain = text.replace("`", "")
    assert "NOT EXECUTED" in text and "NOT AUTHORIZED" in text
    assert "REAL_FIT_AUTHORIZED is False" in plain
    assert "authorized_real_gate() returns False" in plain
    # Readiness is True and the manifest must not ASSERT otherwise. §7 legitimately states
    # "activation_readiness() returns False" as a STOP CONDITION, so the check is per-line and demands
    # a same-line qualifier marking it conditional rather than a claim about the current value.
    unqualified = [ln for ln in plain.splitlines()
                   if "activation_readiness() returns False" in ln
                   and not any(q in ln for q in ("on its own it stops the run", "It was", "it was"))]
    assert not unqualified, ("the manifest asserts readiness is False while it returns True:\n  "
                             + "\n  ".join(unqualified))
    assert "WITHDRAWN" in text and "FALSE PREMISE" in text, (
        "the withdrawn contaminated-bundles blocker must be recorded as withdrawn")
    assert ARP.activation_readiness()[0] is True
    assert ARP.authorized_real_gate(EX.preflight(require_pipeline_assertions=False))[0] is False
    assert EX.real_fit_lock_state() == (False, False)


# =====================================================================================================
# §6 — the permanent hermeticity scanner, with self-probes
# =====================================================================================================
_HERMETIC_TARGETS = (
    "V39_ACTIVATION_MANIFEST.md",
    "V39_PREFIT_STOP_REPORT.md",
    "REQUIREMENT_MATRIX.md",
    "AUDIT_TODO.md",
    "data/RESEARCH_LOG.md",
    "../preregs/PREREG_coach_quality_2026-07-28.md",
    "assemble_real_panel_v39.py",
    "run_coach_projection_experiment_v39.py",
)
# A claim is UNQUALIFIED unless the SAME physical line scopes it.
_HERMETIC_SCOPE = re.compile(
    r"outcome|veteran|four|WITHDRAWN|SUPERSEDED|RETRACTED|not activation-ready|NOT READY|rookie|"
    r"seven-bundle|scope|qualif", re.I)
_HERMETIC_CLAIMS = (
    ("already hermetic",    r"already hermetic"),
    ("run is hermetic",     r"run is (?:already )?hermetic"),
    ("is hermetic",         r"\bis hermetic\b"),
    ("no new input",        r"no new (?:input )?artifact|needs? no (?:new )?input|no extra input|"
                            r"nothing must be created or fetched"),
    ("no fetch",            r"no fetch|needs no network(?!-capable)|no network access"),
    ("none is needed",      r"because none is needed"),
)


def _scan_hermetic(text):
    hits = []
    for i, line in enumerate(text.splitlines(), 1):
        for label, pat in _HERMETIC_CLAIMS:
            if re.search(pat, line, re.I) and not _HERMETIC_SCOPE.search(line):
                hits.append((i, label, line.strip()[:110]))
    return hits


def test_no_live_document_makes_an_unqualified_hermeticity_claim():
    problems = []
    for rel in _HERMETIC_TARGETS:
        p = (COACH / rel).resolve()
        assert p.exists(), f"hermeticity scan target missing: {rel}"
        if p.name == pathlib.Path(__file__).name:
            continue
        for lineno, label, line in _scan_hermetic(p.read_text(encoding="utf-8")):
            problems.append(f"{p.name}:{lineno} [{label}] {line}")
    assert not problems, ("unqualified whole-run hermeticity claim(s):\n  " + "\n  ".join(problems))


@pytest.mark.parametrize("label,probe", [
    ("already hermetic", "The first authorized run is already hermetic."),
    ("run is hermetic",  "The run is hermetic."),
    ("is hermetic",      "This build is hermetic."),
    ("no new input",     "It requires no new input artifact."),
    ("no fetch",         "The run needs no fetch."),
    ("none is needed",   "No input artifact created, because none is needed."),
])
def test_the_hermeticity_scanner_detects_each_retired_form(label, probe):
    """Self-probes: a scanner that silently stopped matching would pass the test above vacuously."""
    caught = {lbl for _i, lbl, _l in _scan_hermetic(probe)}
    assert label in caught, f"the scanner MISSED an unqualified {label!r}"
    scoped = probe.replace("The run", "The OUTCOME path").replace("It requires", "The outcome requires")
    scoped = scoped if "outcome" in scoped.lower() else scoped + " (OUTCOME path only)"
    assert not _scan_hermetic(scoped), f"the scanner ignores the same-line scope for {label!r}"


def test_the_scanner_covers_the_eight_stated_targets():
    assert len(_HERMETIC_TARGETS) == 8
    for rel in _HERMETIC_TARGETS:
        assert (COACH / rel).resolve().exists(), rel


# =====================================================================================================
# Documentation: no incompatible UNCONDITIONAL current-result suite count
# =====================================================================================================
# One test in the suite is environment-dependent: the OPTIONAL git cross-check of the vendored
# historical validator passes when the pinned blob is reachable and skips when it is not (after the
# repo rename it is owned by another account, so git refuses without `-c safe.directory=...`). A green
# run therefore legitimately reports `818 passed` OR `817 passed, 1 skipped` — the same result. A bare
# unconditional "N passed" line in a document turns that into an apparent contradiction between two
# correct reviews.
_COUNT_DOCS = (
    "V39_PREFIT_STOP_REPORT.md",
    "V39_ACTIVATION_MANIFEST.md",
    "REQUIREMENT_MATRIX.md",
    "AUDIT_TODO.md",
    "../preregs/PREREG_coach_quality_2026-07-28.md",
)
# words that reconcile the two forms on the SAME physical line
_COUNT_RECONCILERS = re.compile(
    r"collected|mandatory|optional|skip|either|HISTORICAL|SUPERSEDED|WITHDRAWN|at that point|"
    r"at that amendment|at that freeze|cross-check", re.I)


def _canonical_counts():
    """(total, mandatory) READ FROM the canonical stop-report table.

    Derived, never hard-coded: an earlier revision pinned the literals `817|818` into the scanner and
    it silently stopped detecting the very forms it existed to ban the moment the suite grew. The two
    values this returns are independently checked elsewhere — against a live `--collect-only` and
    against `mandatory == total - 1` — by
    `test_the_stop_report_carries_the_canonical_four_part_count_statement`.
    """
    text = (COACH / "V39_PREFIT_STOP_REPORT.md").read_text(encoding="utf-8")
    total = re.search(r"\|\s*canonical collection total\s*\|\s*\*\*(\d+)\*\*\s*\|", text)
    mandatory = re.search(r"\|\s*mandatory tests\s*\|\s*\*\*(\d+) passed\*\*\s*\|", text)
    assert total and mandatory, "the canonical count table is missing or malformed"
    return int(total.group(1)), int(mandatory.group(1))


def _suite_count_pattern(total, mandatory):
    return re.compile(rf"\b({total}|{mandatory})\s+passed\b", re.I)


def _scan_unconditional_counts(text, total=None, mandatory=None):
    """Lines asserting a bare suite-level pass count without a same-line reconciler.

    `total`/`mandatory` default to the canonical table, so the scanner tracks the current numbers
    instead of a frozen generation of them.
    """
    if total is None or mandatory is None:
        total, mandatory = _canonical_counts()
    pat = _suite_count_pattern(total, mandatory)
    return [(i, line.strip()[:110]) for i, line in enumerate(text.splitlines(), 1)
            if pat.search(line) and not _COUNT_RECONCILERS.search(line)]


def test_no_document_states_an_incompatible_unconditional_suite_count():
    total, mandatory = _canonical_counts()

    # The stale-literal defect itself: the pattern must be BUILT from the canonical values, never
    # frozen into the module. The needle is assembled at runtime so this guard cannot match itself.
    src = pathlib.Path(__file__).read_text(encoding="utf-8")
    frozen_marker = "_SUITE" + "_COUNT = re.compile"
    assert frozen_marker not in src, "a module-level frozen count pattern is back"
    pat = _suite_count_pattern(total, mandatory)
    assert pat.search(f"{total} passed") and pat.search(f"{mandatory} passed")
    for stale in (817, 818, 785, 753):
        if stale not in (total, mandatory):
            assert not pat.search(f"{stale} passed"), f"the pattern still matches a stale {stale}"

    problems = []
    for rel in _COUNT_DOCS:
        p = (COACH / rel).resolve()
        assert p.exists(), rel
        for lineno, line in _scan_unconditional_counts(p.read_text(encoding="utf-8"),
                                                       total, mandatory):
            problems.append(f"{p.name}:{lineno}  {line}")
    assert not problems, (
        f"unconditional suite-count line(s) — state {total} collected / {mandatory} mandatory / "
        f"1 optional cross-check instead:\n  " + "\n  ".join(problems))


def _count_probes():
    """Six probes built from the CURRENT canonical numbers, not from any literal."""
    total, mandatory = _canonical_counts()
    return [
        (f"full coaching suite   {total} passed", True),
        (f"the suite reports {mandatory} passed", True),
        (f"{total} collected; {mandatory} mandatory passed; 1 optional cross-check", False),
        (f"{mandatory} passed, 1 optional cross-check skipped", False),
        (f"either `{total} passed` or `{mandatory} passed, 1 skipped` — the same result", False),
        ("141 passed, 6 deselected", False),          # the baseline is unambiguous, and stays allowed
    ]


@pytest.mark.parametrize("probe,should_flag", _count_probes())
def test_the_count_scanner_flags_only_the_unconditional_forms(probe, should_flag):
    """Self-probes, generated from the canonical table: bare `{total} passed` and `{mandatory} passed`
    must be rejected, the reconciled forms and the 141/6 baseline must be allowed. A scanner pinned to
    a stale generation of numbers would pass the test above while detecting nothing."""
    flagged = bool(_scan_unconditional_counts(probe))
    assert flagged is should_flag, f"{probe!r}: flagged={flagged}, expected {should_flag}"




def test_the_stop_report_carries_the_canonical_four_part_count_statement():
    """The four labels must be present, and the two numbers must reconcile — derived, not hard-coded.

    Hard-coding the totals here is what broke this test when the suite grew: the assertion must check
    the STRUCTURE and the internal arithmetic, so it survives every legitimate count change.
    """
    text = (COACH / "V39_PREFIT_STOP_REPORT.md").read_text(encoding="utf-8")
    for label in ("canonical collection total", "mandatory tests", "optional git cross-check",
                  "otherwise skips", "runs in BOTH states"):
        assert label in text, f"the canonical count statement is missing: {label!r}"

    total = re.search(r"\|\s*canonical collection total\s*\|\s*\*\*(\d+)\*\*\s*\|", text)
    mandatory = re.search(r"\|\s*mandatory tests\s*\|\s*\*\*(\d+) passed\*\*\s*\|", text)
    assert total and mandatory, "the canonical table must state both numbers"
    total_n, mandatory_n = int(total.group(1)), int(mandatory.group(1))
    assert mandatory_n == total_n - 1, (
        f"canonical statement is inconsistent: {total_n} collected vs {mandatory_n} mandatory; "
        f"exactly one test (the optional git cross-check) is environment-dependent")

    collected = _collect_count()
    assert total_n == collected, (
        f"the stop report says {total_n} collected; the suite actually collects {collected}")


def _collect_count():
    """Collect the suite without running it, so the documented total is checked against reality."""
    import subprocess
    out = subprocess.run([sys.executable, "-m", "pytest", str(COACH / "tests"),
                          "-q", "--collect-only", "-p", "no:warnings"],
                         capture_output=True, text=True, cwd=str(COACH.parent.parent.parent))
    m = re.search(r"(\d+) tests? collected", out.stdout) or re.search(r"(\d+)/(\d+)", out.stdout)
    assert m, f"could not read a collection count:\n{out.stdout[-400:]}"
    return int(m.group(1))


def test_the_optional_cross_check_is_the_only_environment_dependent_test():
    """The red proof must never skip — it loads the vendored fixture, not git. Checked on the AST."""
    src = (COACH / "tests" / "test_boundary_corpus.py").read_text(encoding="utf-8")
    tree = ast.parse(src)

    def _skips_in(fn):
        return [n.lineno for n in ast.walk(fn) if isinstance(n, ast.Call)
                and getattr(n.func, "attr", None) == "skip"
                and getattr(getattr(n.func, "value", None), "id", None) == "pytest"]

    by_name = {n.name: n for n in ast.walk(tree)
               if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    assert "historical" in by_name, "the vendored-fixture loader is missing"
    assert not _skips_in(by_name["historical"]), (
        "the historical-validator fixture must never skip; only the git cross-check may")

    cross = "test_the_frozen_fixture_still_matches_the_pinned_revision_when_git_is_available"
    assert cross in by_name, "the optional git cross-check is missing"
    assert _skips_in(by_name[cross]), "the optional cross-check is the one test allowed to skip"

    skipping = sorted(n for n, fn in by_name.items() if _skips_in(fn))
    assert skipping == [cross], f"more than one test can skip: {skipping}"


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


def _write_feature_snapshot(tmp_path, name="veteran_fixture.parquet", include_2026=False,
                            include_forbidden=False, frame=None):
    """The reader now consumes the frozen PARQUET snapshot, not the mutable production CSV.

    The snapshot is feature-only and already windowed by construction, so these fixtures exist to
    prove the reader still refuses a snapshot that violates either property.
    """
    df = synthetic_features() if frame is None else frame
    if include_2026:
        extra = df[df[ARP.SEASON_KEY] == 2025].copy()
        extra[ARP.SEASON_KEY] = ARP.DEPLOY_SEASON
        df = pd.concat([df, extra], ignore_index=True)
    if include_forbidden:
        for c in ("target_ppg", "target_games", "sample_weight", "sleeper_pts_half_ppr",
                  "adp_half_ppr"):
            df[c] = 1.0
    out = tmp_path / name
    df.to_parquet(out, index=False, engine="pyarrow", compression="snappy")
    return out


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
    src = _write_feature_snapshot(tmp_path)
    out = ARP.authorized_feature_reader(path=src, verify_hash=False, verify_manifest=False)()
    seasons = sorted(set(out[ARP.SEASON_KEY]))
    assert seasons == list(ARP.ALL_PANEL_SEASONS)
    assert ARP.DEPLOY_SEASON not in seasons
    assert not (set(out.columns) & ARP.FORBIDDEN_IN_FEATURES)
    assert list(out.columns) == list(ARP.FROZEN_FEATURE_COLUMNS)
    assert ARP.validate_feature_frame(out) == []


def test_the_feature_reader_output_passes_its_own_validator(tmp_path):
    """The gap that let a broken reader pass 663 tests: nobody ran its OUTPUT through the validator."""
    src = _write_feature_snapshot(tmp_path)
    out = ARP.authorized_feature_reader(path=src, verify_hash=False, verify_manifest=False)()
    assert ARP.validate_feature_frame(out) == []


def test_the_feature_reader_refuses_a_snapshot_carrying_2026(tmp_path):
    """The snapshot must never contain the deploy season; the reader refuses it rather than filtering
    it away silently, because a 2026 row means the artifact was built wrong."""
    src = _write_feature_snapshot(tmp_path, "with_2026.parquet", include_2026=True)
    with pytest.raises(ARP.AssemblyError):
        ARP.authorized_feature_reader(path=src, verify_hash=False, verify_manifest=False)()


def test_the_feature_reader_refuses_a_snapshot_carrying_a_forbidden_column(tmp_path):
    src = _write_feature_snapshot(tmp_path, "forbidden.parquet", include_forbidden=True)
    with pytest.raises(ARP.AssemblyError):
        ARP.authorized_feature_reader(path=src, verify_hash=False, verify_manifest=False)()


def test_the_feature_reader_fails_on_a_missing_frozen_column(tmp_path):
    src = _write_feature_snapshot(tmp_path, "short.parquet",
                                  frame=synthetic_features().drop(columns=["prior_ppg"]))
    with pytest.raises(ARP.AssemblyError) as exc:
        ARP.authorized_feature_reader(path=src, verify_hash=False, verify_manifest=False)()
    assert "schema differs" in str(exc.value)


def test_the_feature_reader_fails_on_hash_drift(tmp_path):
    src = _write_feature_snapshot(tmp_path)
    with pytest.raises(ARP.AssemblyError) as exc:
        ARP.authorized_feature_reader(path=src, verify_hash=True, verify_manifest=False)()
    assert "sha256" in str(exc.value)


def test_the_feature_reader_enforces_unique_keys(tmp_path):
    df = synthetic_features()
    src = _write_feature_snapshot(tmp_path, "dup.parquet",
                                  frame=pd.concat([df, df.iloc[[0]]], ignore_index=True))
    with pytest.raises(ARP.AssemblyError) as exc:
        ARP.authorized_feature_reader(path=src, verify_hash=False, verify_manifest=False)()
    assert "duplicate" in str(exc.value) or "row count" in str(exc.value)


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
    fsrc = _write_feature_snapshot(tmp_path)
    wsrc = tmp_path / "weekly.parquet"
    synthetic_weekly().to_parquet(wsrc, index=False)

    features = ARP.authorized_feature_reader(path=fsrc, verify_hash=False,
                                             verify_manifest=False)()
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
    fsrc = _write_feature_snapshot(tmp_path)
    wsrc = tmp_path / "weekly_missing.parquet"
    weekly = synthetic_weekly(players=5)          # feature fixture has 6 players
    weekly.to_parquet(wsrc, index=False)

    features = ARP.authorized_feature_reader(path=fsrc, verify_hash=False,
                                             verify_manifest=False)()
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
    """SUPERSEDED SHAPE, same property. The door is now implemented under C5-A, so statement 2 is the
    clearance rather than a raise — but authorization is still first and no reader precedes it."""
    src = (COACH / "run_coach_projection_experiment_v39.py").read_text(encoding="utf-8")
    fn = next(n for n in ast.walk(ast.parse(src))
              if isinstance(n, ast.FunctionDef) and n.name == "assemble_real_panel")
    body = [s for s in fn.body if not (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant))]
    assert isinstance(body[0], ast.Expr) and body[0].value.func.id == "require_real_fit_authorization"
    assert isinstance(body[1], ast.Expr) and body[1].value.func.id == EX.PREFLIGHT_CLEARANCE_NAME
    callees = {getattr(n.func, "id", None) for n in ast.walk(fn) if isinstance(n, ast.Call)}
    assert not (callees & EX.ENTRY_POINT_BANNED_READER_CALLEES), (
        "the door may not contain a reader callee at all")


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
