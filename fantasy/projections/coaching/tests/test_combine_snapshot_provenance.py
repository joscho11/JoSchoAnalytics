"""Provenance tests for the frozen public NFL Combine snapshot.

Fetched once under explicit authorization on 2026-08-03 from
`https://github.com/nflverse/nflverse-data/releases/download/combine/combine.parquet`
and frozen byte-for-byte. These tests NEVER call `load_combine` and never touch the network: they
read the local file and `snapshots/manifest.json` only.

The snapshot unblocks the 10 combine-sourced columns the three rookie bundles need
(`bench, bmi, broad_jump, cone, forty, ht_in, shuttle, speed_score, vertical, wt`), but it is NOT the
rookie matrix and on its own it makes nothing activation-ready.
"""
import ast
import datetime as dt
import hashlib
import json
import pathlib
import re

import pandas as pd
import pyarrow.parquet as pq
import pytest

COACH = pathlib.Path(__file__).resolve().parent.parent
SEAS = COACH.parent.parent / "seasonal_projections"
SNAP = SEAS / "snapshots"
COMBINE = SNAP / "combine.parquet"
MANIFEST = SNAP / "manifest.json"

MANIFEST_KEY = "combine"
PINNED_SHA256 = "1b6c48a0b56e515b043dd678ea38a2e6ae83cb9de488e6a0a89f8b2f980bf2cf"
PINNED_BYTES = 374_318
PINNED_ROWS = 8_968
PINNED_COLS = 18
SOURCE_URL = "https://github.com/nflverse/nflverse-data/releases/download/combine/combine.parquet"
PINNED_FETCHED_UTC = "2026-08-03T18:03:58Z"
# the exact ORDERED 18-column schema of the frozen file
PINNED_SCHEMA = ("season", "draft_year", "draft_team", "draft_round", "draft_ovr", "pfr_id",
                 "cfb_id", "player_name", "pos", "school", "ht", "wt", "forty", "bench",
                 "vertical", "broad_jump", "cone", "shuttle")

# The eight RAW fields the production rookie harness reads. `bmi` and `speed_score` are DERIVED from
# ht/wt/forty by `assemble_features.py` and must not be expected in the source.
RAW_COMBINE_FIELDS = ("forty", "vertical", "broad_jump", "cone", "shuttle", "bench", "ht", "wt")
DERIVED_NOT_IN_SOURCE = ("bmi", "speed_score")
FORBIDDEN_SUBSTRINGS = ("fantasy_points", "half_ppr", "target_ppg", "target_games", "sample_weight",
                        "season_total", "adp", "sleeper", "projection", "hit_", "label", "outcome")


@pytest.fixture(scope="module")
def manifest_entry():
    man = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert MANIFEST_KEY in man, f"manifest has no {MANIFEST_KEY!r} entry"
    return man[MANIFEST_KEY]


def test_the_combine_snapshot_exists_and_matches_the_frozen_pin():
    assert COMBINE.exists(), f"missing snapshot: {COMBINE}"
    raw = COMBINE.read_bytes()
    assert len(raw) == PINNED_BYTES
    assert hashlib.sha256(raw).hexdigest() == PINNED_SHA256
    assert raw[:4] == b"PAR1" and raw[-4:] == b"PAR1", "not a Parquet file"


def test_the_manifest_matches_the_file(manifest_entry):
    meta = pq.ParquetFile(COMBINE).metadata
    assert manifest_entry["sha256"] == hashlib.sha256(COMBINE.read_bytes()).hexdigest()
    assert manifest_entry["sha256"] == PINNED_SHA256
    assert manifest_entry["loader"] == "load_combine"
    assert manifest_entry["nflreadpy"] == "0.1.5"
    assert manifest_entry["rows"] == meta.num_rows == PINNED_ROWS
    assert manifest_entry["cols"] == meta.num_columns == PINNED_COLS
    assert manifest_entry["source_url"] == SOURCE_URL

    # provenance fields pinned exactly, not merely present
    assert manifest_entry["path"] == "fantasy/seasonal_projections/snapshots/combine.parquet"
    assert (SEAS.parent.parent / manifest_entry["path"]).resolve() == COMBINE.resolve()
    assert manifest_entry["args"] == "(seasons=True)"
    assert manifest_entry["schema_version"] == 1
    assert manifest_entry["fetched_utc"] == PINNED_FETCHED_UTC
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", manifest_entry["fetched_utc"]), \
        "fetched_utc must be UTC ISO-8601 with a trailing Z, matching the other entries"
    assert dt.datetime.strptime(manifest_entry["fetched_utc"], "%Y-%m-%dT%H:%M:%SZ")

    # the exact ORDERED 18-column schema
    assert tuple(pq.ParquetFile(COMBINE).schema.names) == PINNED_SCHEMA
    assert len(PINNED_SCHEMA) == PINNED_COLS


def test_the_manifest_season_coverage_matches_the_file(manifest_entry):
    seasons = sorted(int(s) for s in pd.unique(pd.read_parquet(COMBINE, columns=["season"])["season"]
                                               .dropna()))
    assert manifest_entry["seasons"] == seasons
    assert manifest_entry["season_min"] == seasons[0]
    assert manifest_entry["season_max"] == seasons[-1]
    # the frozen rookie window must be fully inside the snapshot
    assert set(range(2014, 2026)) <= set(seasons)


def test_the_required_raw_combine_columns_exist():
    cols = set(pq.ParquetFile(COMBINE).schema.names)
    missing = [c for c in RAW_COMBINE_FIELDS if c not in cols]
    assert not missing, f"snapshot is missing raw combine field(s): {missing}"
    assert "pfr_id" in cols, "pfr_id is the join key to the draft/rookie panel"


def test_bmi_and_speed_score_are_derived_not_source_fields():
    """Production computes them from ht/wt/forty; treating them as source fields would be wrong."""
    cols = set(pq.ParquetFile(COMBINE).schema.names)
    for c in DERIVED_NOT_IN_SOURCE:
        assert c not in cols, f"{c} unexpectedly present in the source snapshot"
    src = (COACH.parent.parent / "rookie" / "harness" / "assemble_features.py").read_text(
        encoding="utf-8")
    assert 'p["bmi"]' in src and 'p["speed_score"]' in src, "production no longer derives them"


def test_the_snapshot_carries_no_fantasy_outcome_column():
    cols = list(pq.ParquetFile(COMBINE).schema.names)
    hits = sorted({c for c in cols for f in FORBIDDEN_SUBSTRINGS if f in c.lower()})
    assert not hits, f"forbidden outcome/market column(s) in the combine snapshot: {hits}"


def test_the_production_combine_transformation_consumes_the_local_snapshot_offline(monkeypatch):
    """Drive the REAL `assemble_features.build_features()` against the frozen local snapshots.

    An earlier version of this test re-implemented `ht_to_in`, `bmi` and `speed_score` inside the test
    body. That is a parallel implementation, not production-equivalence evidence — the exact defect
    class this project has hit repeatedly. This now imports the production module and calls the real
    function, with every external source injected:

      * `nfl.load_draft_picks` -> the repo-owned draft_picks snapshot
      * `nfl.load_combine`     -> the frozen combine snapshot (this checkpoint's artifact)
      * `_pff_long`            -> an empty frame, so NO private PFF file is read
      * `college_features.csv` -> read normally; it is repo-owned and outcome-free

    No network call is possible: both loaders are replaced before `build_features` runs. It is the
    combine/draft/college path only — this builds no rookie matrix and reads no fantasy outcome.
    """
    import importlib.util
    import sys

    harness = COACH.parent.parent / "rookie" / "harness"
    sys.path.insert(0, str(harness))                       # for `from _utils import norm_name`
    spec = importlib.util.spec_from_file_location("assemble_features_under_test",
                                                  harness / "assemble_features.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)

    draft_local = pd.read_parquet(SNAP / "draft_picks.parquet")
    combine_local = pd.read_parquet(COMBINE)

    calls = {"draft": 0, "combine": 0}

    def _fake_draft(*_a, **_k):
        calls["draft"] += 1
        return draft_local

    def _fake_combine(*_a, **_k):
        calls["combine"] += 1
        return combine_local

    def _no_pff(kind, cols):
        # the point-in-time selector's empty-input contract: no rows, hence no PFF block
        return pd.DataFrame(columns=["norm_name", "pff_season", "pff_player_id", "pff_position"])

    monkeypatch.setattr(mod.nfl, "load_draft_picks", _fake_draft)
    monkeypatch.setattr(mod.nfl, "load_combine", _fake_combine)
    monkeypatch.setattr(mod, "_pff_long", _no_pff)

    # minimal panel keyed on an identity present in BOTH local snapshots (2014 WR, pick 4)
    GSIS, PFR = "00-0031325", "WatkSa00"
    panel = pd.DataFrame({"gsis_id": [GSIS], "season": [2014], "round": [1], "pick": [4],
                          "position": ["WR"]})

    feat, groups, feature_cols = mod.build_features(panel)

    assert calls == {"draft": 1, "combine": 1}, f"injected loaders not used exactly once: {calls}"
    assert len(feat) == 1, "production dropped or duplicated the panel row"

    row = feat.iloc[0]
    assert row["pfr_player_id"] == PFR, "the draft join did not attach the expected identity"

    # the eight RAW combine fields arrived through production's own join
    for c in RAW_COMBINE_FIELDS:
        col = "ht_in" if c == "ht" else c
        assert col in feat.columns, f"production output is missing {col}"
    for c in ("forty", "vertical", "broad_jump", "cone", "shuttle", "bench", "wt"):
        assert pd.notna(row[c]), f"{c} is null for an identity the snapshot measures"

    # the three DERIVED values, computed by production and not by this test
    assert row["ht_in"] == 73, f"ht '6-1' should be 73 inches, got {row['ht_in']}"
    assert row["bmi"] == pytest.approx(703 * 211.0 / (73 ** 2), rel=1e-9)
    assert row["speed_score"] == pytest.approx(211.0 * 200.0 / (4.43 ** 4), rel=1e-9)

    assert set(groups["combine"]) == {"forty", "vertical", "broad_jump", "cone", "shuttle",
                                      "bench", "ht_in", "wt", "bmi", "speed_score"}

    # no fantasy outcome reached the production output
    hits = sorted({c for c in feat.columns for f in FORBIDDEN_SUBSTRINGS if f in c.lower()})
    assert not hits, f"production output carries outcome/market column(s): {hits}"

    # the PFF join is point-in-time, and it ran (with an empty source) rather than being skipped
    for kind in ("receiving", "rushing", "passing"):
        assert f"pff_{kind}_source_season" in feat.columns


def test_these_tests_never_call_load_combine_or_any_network_function():
    """AST proof: no loader call, no network import, in this module."""
    tree = ast.parse(pathlib.Path(__file__).read_text(encoding="utf-8"))
    banned_calls = {"load_combine", "urlopen", "urlretrieve"}
    network_roots = {"requests", "httpx", "urllib", "urllib3", "aiohttp", "nflreadpy", "socket"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = getattr(node.func, "attr", getattr(node.func, "id", None))
            assert name not in banned_calls, f"forbidden call {name}() at line {node.lineno}"
        if isinstance(node, ast.Import):
            for a in node.names:
                assert a.name.split(".")[0] not in network_roots, f"network import {a.name}"
        if isinstance(node, ast.ImportFrom):
            assert (node.module or "").split(".")[0] not in network_roots, \
                f"network import from {node.module}"


def test_the_snapshot_alone_does_not_make_activation_ready():
    """The combine snapshot is an INPUT, not the rookie matrix.

    SUPERSEDED FACT, corrected 2026-08-03: this test used to assert `activation_readiness() is False`
    and that the rookie matrix did not exist. Option A built that matrix, so readiness is now True —
    but not *because of this snapshot*. The property still worth holding is the original one: with the
    derived rookie matrix removed from the picture, the combine snapshot supplies nothing to the three
    rookie bundles and readiness fails closed.
    """
    import sys
    sys.path.insert(0, str(COACH))
    import assemble_real_panel_v39 as ARP
    ready, detail = ARP.activation_readiness(rookie_columns=set())
    assert ready is False, "the combine snapshot alone made activation ready"
    assert "rookie" in detail.lower()
    # and the matrix that closed the FEATURE gap is a separate, independently pinned artifact
    matrix = SNAP / "rookie_arm0_features_2014_2025.parquet"
    assert matrix.exists() and matrix != COMBINE
    # with the real matrix in place, readiness IS True — but not because of this snapshot
    assert ARP.activation_readiness()[0] is True
