"""Every protected artifact must have EXACTLY ONE writer.

Two separate incidents in this subproject came from a second writer silently overwriting an
artifact whose meaning had changed:

  source_ledger.csv               written by report_coverage.py while the table was rebuilt
                                  elsewhere -> the repo held 2021-10-18 in one file and the
                                  fabricated 2021-01-01 in the other.
  preseason_staff_snapshot.csv    build_exposure.py --build wrote its PRE-v3.5 retrospective frame
                                  over the eligibility-gated point-in-time artifact.

A grep-based test is the cheap durable guard.
"""
import pathlib
import re

COACH = pathlib.Path(__file__).resolve().parent.parent

OWNER = {
    "game_level_identity.csv": "build_exposure.py",
    "coach_exposure.csv": "build_exposure.py",
    "caller_known_share.csv": "build_exposure.py",
    "retrospective_staff_transitions.csv": "build_preseason_snapshot.py",
    "preseason_staff_snapshot.csv": "build_preseason_snapshot.py",
    "preseason_evidence_ledger.csv": "build_preseason_snapshot.py",
    "actual_play_caller.csv": "build_playcaller_table.py",
    "source_ledger.csv": "build_playcaller_table.py",
    "coach_reliability.csv": "build_reliability.py",
    # v3.8: team_offense_panel.csv had TWO writers -- build_team_offense_panel.py wrote it and
    # build_allocation_panel.py read+overwrote it, so running the efficiency builder AFTER the
    # allocation builder silently erased the allocation and OL fields.
    "team_offense_base.csv": "build_team_offense_panel.py",
    "team_offense_panel.csv": "build_allocation_panel.py",
    "personnel_controls.csv": "build_personnel_controls.py",
    "coach_reliability_lineage.csv": "build_reliability.py",
    # v3.9 Phase 2A
    "team_coach_features_design_a_v39.csv": "build_arm_features_v39.py",
    "team_coach_features_design_b_oracle_v39.csv": "build_arm_features_v39.py",
    "arm_feature_coverage_v39.csv": "build_arm_features_v39.py",
    "arm_feature_lineage_v39.csv": "build_arm_features_v39.py",
}

# Artifacts written with `write_text` rather than `to_csv`.
TEXT_OWNER = {
    "arm_feature_manifest_v39.json": "build_arm_features_v39.py",
}

# v3.9 authorises EXACTLY these five new data artifacts under coaching/data/. Anything else the
# v3.9 code needs (the head-coach win ledger) is a derived cache and belongs in SCRATCH.
V39_AUTHORIZED_ARTIFACTS = {
    "team_coach_features_design_a_v39.csv",
    "team_coach_features_design_b_oracle_v39.csv",
    "arm_feature_manifest_v39.json",
    "arm_feature_coverage_v39.csv",
    "arm_feature_lineage_v39.csv",
}


def _writers(artifact):
    """Modules containing a `.to_csv(... "<artifact>" ...)` call."""
    pat = re.compile(r"to_csv\(\s*[^)]*" + re.escape(artifact))
    out = []
    for f in sorted(COACH.glob("*.py")):
        if pat.search(f.read_text(encoding="utf-8", errors="ignore")):
            out.append(f.name)
    return out


def _text_writers(artifact):
    """Modules containing a `write_text` call on `<artifact>`."""
    pat = re.compile(re.escape(artifact) + r"\"\s*\)\s*\.write_text")
    return [f.name for f in sorted(COACH.glob("*.py"))
            if pat.search(f.read_text(encoding="utf-8", errors="ignore"))]


def test_each_protected_artifact_has_exactly_one_writer():
    problems = []
    for artifact, owner in OWNER.items():
        w = _writers(artifact)
        if w != [owner]:
            problems.append(f"{artifact}: expected [{owner}], found {w}")
    assert not problems, "artifact ownership violated:\n  " + "\n  ".join(problems)


def test_each_protected_text_artifact_has_exactly_one_writer():
    problems = []
    for artifact, owner in TEXT_OWNER.items():
        w = _text_writers(artifact)
        if w != [owner]:
            problems.append(f"{artifact}: expected [{owner}], found {w}")
    assert not problems, "text artifact ownership violated:\n  " + "\n  ".join(problems)


def test_build_arm_features_v39_writes_only_the_five_authorized_artifacts():
    src = (COACH / "build_arm_features_v39.py").read_text(encoding="utf-8")
    written = set(re.findall(r'to_csv\(DATA / "([^"]+)"', src))
    written |= set(re.findall(r'DATA / "([^"]+)"\)\.write_text', src))
    assert written == V39_AUTHORIZED_ARTIFACTS, written


def test_the_harness_writes_no_repo_artifact_at_all():
    src = (COACH / "run_coach_projection_experiment_v39.py").read_text(encoding="utf-8")
    assert not re.findall(r'to_csv\(DATA / "', src)
    assert not re.findall(r'DATA / "[^"]+"\)\.write_text', src)


def test_no_unauthorized_v39_artifact_exists_on_disk():
    """A 6th v3.9 data file would mean the pre-registered artifact set had silently grown."""
    found = {p.name for p in (COACH / "data").glob("*_v39.*")}
    assert found == V39_AUTHORIZED_ARTIFACTS, f"unexpected v3.9 artifacts on disk: {found}"


def test_the_head_coach_win_ledger_is_derived_in_memory_not_cached():
    """It used to be a scratch-dir CSV, which made a clean rebuild depend on state outside the
    checkout. It is now computed from the repo-owned frozen schedule snapshot on every call."""
    src = (COACH / "build_arm_features_v39.py").read_text(encoding="utf-8")
    body = src.split("def hc_game_results", 1)[1].split("\ndef ", 1)[0]
    assert ".to_csv(" not in body, "the win ledger must not be persisted anywhere"
    assert "snapshot_schedules()" in body
    assert "SCRATCH" not in src and "tempfile" not in src


def test_the_v39_modules_never_write_outside_the_coaching_data_dir():
    """Every write must target `coaching/data/`. For `to_csv`/`to_parquet` the destination is the
    first ARGUMENT; for `write_text`/`write_bytes` it is the RECEIVER, so the two are matched
    separately -- reading the argument of `write_text` only finds the content."""
    for mod in ("build_arm_features_v39.py", "run_coach_projection_experiment_v39.py"):
        src = (COACH / mod).read_text(encoding="utf-8")
        for m in re.finditer(r"\.(to_csv|to_parquet)\(([^,)]*)", src):
            target = m.group(2).strip()
            # `to_csv()` / `to_csv(index=False)` with NO positional path returns a STRING and writes
            # nothing — `compare_coverage` uses that to round-trip a derived frame in memory.
            if target == "" or "=" in target:
                continue
            assert target.startswith("DATA /"), (
                f"{mod} {m.group(1)} -> {target!r}, outside coaching/data/")
        for m in re.finditer(r"\(([^()]*)\)\s*\.write_(?:text|bytes)\(", src):
            recv = m.group(1).strip()
            assert recv.startswith("DATA /"), (
                f"{mod} write_text -> {recv!r}, outside coaching/data/")
        assert ".to_parquet(" not in src, f"{mod} must never write a parquet into the repo"


def test_build_exposure_writes_only_its_three_artifacts():
    src = (COACH / "build_exposure.py").read_text(encoding="utf-8")
    written = set(re.findall(r'to_csv\(DATA / "([^"]+)"', src))
    assert written == {"game_level_identity.csv", "coach_exposure.csv", "caller_known_share.csv"}, (
        f"build_exposure.py writes {written}")


def test_build_exposure_print_message_matches_what_it_writes():
    """It once printed that it had written preseason_staff_snapshot.csv while writing something
    else. A false success message is worse than none."""
    src = (COACH / "build_exposure.py").read_text(encoding="utf-8")
    claimed = set()
    for line in src.splitlines():
        if "print(" in line and "wrote" in line:
            claimed |= set(re.findall(r"[\w]+\.csv", line))
    assert claimed == {"game_level_identity.csv", "coach_exposure.csv",
                       "caller_known_share.csv"}, (
        f"print claims {claimed} but the module writes only its three artifacts")
