"""The permanent, explicitly enumerated boundary red/green corpus (v3.9d follow-up 3).

Why this file exists
--------------------
Earlier passes reported "N injections passed before, 0 now" from an ad-hoc scratchpad probe. Two things
were wrong with that. First, no test materialised the historical validator, so the arithmetic was prose,
not evidence. Second, counting `test_c5*`/`test_c6*`/`test_c7*` collected nodes conflates injections with
positive controls and with unrelated statistical tests that merely share a prefix — which is how a
"46-case" figure appeared for a corpus that never had 46 injections.

So the corpus is enumerated HERE, once, with a stable id per case, and both validators are run against
it: the current one, and the one committed at `HISTORICAL_REV`, materialised with `git show` into a temp
directory. Canonical source is never modified — every case is a pure in-memory string.

`historical_undetected=True` means: that injection slipped past the validator as it stood at
`HISTORICAL_REV`. Those flags are measured, not asserted from memory; `test_boundary_corpus.py` fails if
the historical validator's behaviour stops matching the table.
"""
import pathlib

HISTORICAL_REV = "a5b4af7"
# Full provenance of the frozen historical validator, so "the state at a5b4af7" is checkable rather
# than asserted. The fixture is REPO-OWNED: the red proof runs with no git, no network and no
# reachable history, which is what lets the test fail closed instead of skipping.
HISTORICAL_COMMIT = "a5b4af7c71b8cf5663757488770181de13e32664"
HISTORICAL_BLOB = "85c438f7d908e9df7da8d5e44ad8e30d3bbeeffe"      # git rev-parse a5b4af7:<path>
HISTORICAL_PATH = "fantasy/projections/coaching/run_coach_projection_experiment_v39.py"
HISTORICAL_FIXTURE = "fixtures/historical_validator_a5b4af7.pysrc"
HISTORICAL_SHA256 = "17909c28b95bbc9394d0d1c208802fb02aeb542210ccfc42c37598eed2c46c27"
BUILDER = "build_arm_features_v39.py"
HARNESS = "run_coach_projection_experiment_v39.py"
COACH = pathlib.Path(__file__).resolve().parent.parent

# kind: "append" = concatenate the snippet onto the module; "replace_entry_point" = swap the whole
# `assemble_real_panel` definition; "drop_module"/"extra_module" = mutate the sources mapping.
#
# id, category, kind, module, payload, historical_undetected
CORPUS = (
    # ---- C5-A: the IMPLEMENTED door, malformed ------------------------------------------------
    # Judged by the live validator under ENTRY_POINT_CONTRACT_MODE = authorized_real. The historical
    # validator only knows C5-S, so it rejects every one of these on "body must be exactly 2
    # statements" — caught, but for a reason that says nothing about C5-A. Recorded as measured.
    ("c5a-missing-clearance", "C5A", "replace_entry_point", HARNESS,
     'def assemble_real_panel(feature_reader, outcome_reader):\n'
     '    require_real_fit_authorization()\n'
     '    _ = 1\n'
     '    return assemble_panel_core(feature_reader(), outcome_reader())', False),
    ("c5a-reader-callee-in-body", "C5A", "replace_entry_point", HARNESS,
     'def assemble_real_panel(feature_reader, outcome_reader):\n'
     '    require_real_fit_authorization()\n'
     '    require_preflight_clearance()\n'
     '    return assemble_panel_core(pd.read_csv("x.csv"), outcome_reader())', False),
    ("c5a-banned-outcome-callee", "C5A", "replace_entry_point", HARNESS,
     'def assemble_real_panel(feature_reader, outcome_reader):\n'
     '    require_real_fit_authorization()\n'
     '    require_preflight_clearance()\n'
     '    return assemble_panel_core(feature_reader(), load_player_stats())', False),
    ("c5a-returns-something-else", "C5A", "replace_entry_point", HARNESS,
     'def assemble_real_panel(feature_reader, outcome_reader):\n'
     '    require_real_fit_authorization()\n'
     '    require_preflight_clearance()\n'
     '    return (feature_reader(), outcome_reader())', False),
    ("c5a-statement-before-auth", "C5A", "replace_entry_point", HARNESS,
     'def assemble_real_panel(feature_reader, outcome_reader):\n'
     '    features = feature_reader()\n'
     '    require_real_fit_authorization()\n'
     '    require_preflight_clearance()\n'
     '    return assemble_panel_core(features, outcome_reader())', False),
    ("c5a-clearance-before-auth", "C5A", "replace_entry_point", HARNESS,
     'def assemble_real_panel(feature_reader, outcome_reader):\n'
     '    require_preflight_clearance()\n'
     '    require_real_fit_authorization()\n'
     '    return assemble_panel_core(feature_reader(), outcome_reader())', False),
    ("c5a-auth-with-args", "C5A", "replace_entry_point", HARNESS,
     'def assemble_real_panel(feature_reader, outcome_reader):\n'
     '    require_real_fit_authorization(True)\n'
     '    require_preflight_clearance()\n'
     '    return assemble_panel_core(feature_reader(), outcome_reader())', False),
    ("c5a-clearance-renamed", "C5A", "replace_entry_point", HARNESS,
     'def assemble_real_panel(feature_reader, outcome_reader):\n'
     '    require_real_fit_authorization()\n'
     '    _looks_like_clearance()\n'
     '    return assemble_panel_core(feature_reader(), outcome_reader())', False),
    ("c5a-decorated", "C5A", "replace_entry_point", HARNESS,
     '@staticmethod\n'
     'def assemble_real_panel(feature_reader, outcome_reader):\n'
     '    require_real_fit_authorization()\n'
     '    require_preflight_clearance()\n'
     '    return assemble_panel_core(feature_reader(), outcome_reader())', False),
    ("c5a-extra-statement", "C5A", "replace_entry_point", HARNESS,
     'def assemble_real_panel(feature_reader, outcome_reader):\n'
     '    require_real_fit_authorization()\n'
     '    require_preflight_clearance()\n'
     '    outcomes = outcome_reader()\n'
     '    return assemble_panel_core(feature_reader(), outcomes)', False),

    # ---- C5: the sealed entry point, rebound -------------------------------------------------
    ("c5-rebind-lambda", "C5", "append", HARNESS,
     "assemble_real_panel = lambda *_a, **_k: None", True),
    ("c5-rebind-second-def", "C5", "append", HARNESS,
     'def assemble_real_panel(*_a, **_k):\n'
     '    require_real_fit_authorization()\n'
     '    raise NotImplementedError("second")', True),
    ("c5-rebind-import-alias", "C5", "append", HARNESS,
     "from os import path as assemble_real_panel", True),
    ("c5-rebind-del", "C5", "append", HARNESS, "del assemble_real_panel", True),
    ("c5-rebind-walrus", "C5", "append", HARNESS,
     "def _r():\n    return (assemble_real_panel := None)", True),
    ("c5-rebind-augassign-standalone", "C5", "append", HARNESS,
     "assemble_real_panel += 1", True),
    ("c5-rebind-tuple-destructure", "C5", "append", HARNESS,
     "(assemble_real_panel,) = (None,)", True),
    ("c5-rebind-list-destructure", "C5", "append", HARNESS,
     "[assemble_real_panel] = [None]", True),
    ("c5-rebind-starred-destructure", "C5", "append", HARNESS,
     "*assemble_real_panel, _tail = (1, 2)", True),
    ("c5-rebind-for-target", "C5", "append", HARNESS,
     "for assemble_real_panel in [None]:\n    pass", True),
    ("c5-rebind-with-target", "C5", "append", HARNESS,
     "with open(__file__) as assemble_real_panel:\n    pass", True),
    ("c5-rebind-except-as", "C5", "append", HARNESS,
     "try:\n    raise Exception()\nexcept Exception as assemble_real_panel:\n    pass", True),
    ("c5-rebind-match-capture", "C5", "append", HARNESS,
     "match None:\n    case assemble_real_panel:\n        pass", True),
    ("c5-rebind-comprehension", "C5", "append", HARNESS,
     "_c = [0 for assemble_real_panel in [None]]", True),
    ("c5-rebind-class", "C5", "append", HARNESS,
     "class assemble_real_panel:\n    pass", True),
    # ---- C5: the body shape --------------------------------------------------------------------
    ("c5-body-early-return", "C5", "replace_entry_point", HARNESS,
     'def assemble_real_panel(*_a, **_k):\n'
     '    require_real_fit_authorization()\n'
     '    return None\n'
     '    raise NotImplementedError("unreachable")\n', True),
    ("c5-body-dormant-raise", "C5", "replace_entry_point", HARNESS,
     'def assemble_real_panel(*_a, **_k):\n'
     '    require_real_fit_authorization()\n'
     '    if False:\n'
     '        raise NotImplementedError("dormant")\n'
     '    return 1\n', True),
    ("c5-body-auth-with-args", "C5", "replace_entry_point", HARNESS,
     'def assemble_real_panel(*_a, **_k):\n'
     '    require_real_fit_authorization(True)\n'
     '    raise NotImplementedError("x")\n', True),
    ("c5-body-decorated", "C5", "replace_entry_point", HARNESS,
     '@staticmethod\n'
     'def assemble_real_panel(*_a, **_k):\n'
     '    require_real_fit_authorization()\n'
     '    raise NotImplementedError("x")\n', True),
    ("c5-body-wrong-exception", "C5", "replace_entry_point", HARNESS,
     'def assemble_real_panel(*_a, **_k):\n'
     '    require_real_fit_authorization()\n'
     '    raise RuntimeError("x")\n', False),
    ("c5-body-auth-not-first", "C5", "replace_entry_point", HARNESS,
     'def assemble_real_panel(*_a, **_k):\n'
     '    panel = 1\n'
     '    require_real_fit_authorization()\n'
     '    raise NotImplementedError("x")\n', False),

    # ---- C6: the lock ---------------------------------------------------------------------------
    ("c6-annassign-true", "C6", "append", HARNESS, "REAL_FIT_AUTHORIZED: bool = True", False),
    ("c6-augassign", "C6", "append", HARNESS, "REAL_FIT_AUTHORIZED |= True", False),
    ("c6-walrus", "C6", "append", HARNESS,
     "def _i():\n    return (REAL_FIT_AUTHORIZED := True)", False),
    ("c6-second-false", "C6", "append", HARNESS, "REAL_FIT_AUTHORIZED = False", False),
    ("c6-tuple-destructure-true", "C6", "append", HARNESS, "(REAL_FIT_AUTHORIZED,) = (True,)", True),
    ("c6-list-destructure-true", "C6", "append", HARNESS, "[REAL_FIT_AUTHORIZED] = [True]", True),
    ("c6-for-target", "C6", "append", HARNESS,
     "for REAL_FIT_AUTHORIZED in [True]:\n    pass", True),
    ("c6-with-target", "C6", "append", HARNESS,
     "with open(__file__) as REAL_FIT_AUTHORIZED:\n    pass", True),
    ("c6-except-as", "C6", "append", HARNESS,
     "try:\n    raise Exception()\nexcept Exception as REAL_FIT_AUTHORIZED:\n    pass", True),
    ("c6-match-capture", "C6", "append", HARNESS,
     "match None:\n    case REAL_FIT_AUTHORIZED:\n        pass", True),
    ("c6-import-alias", "C6", "append", HARNESS,
     "import pathlib as REAL_FIT_AUTHORIZED", True),
    ("c6-def-shadow", "C6", "append", HARNESS,
     "def REAL_FIT_AUTHORIZED():\n    return True", True),

    # ---- C7: the process environment -------------------------------------------------------------
    ("c7-subscript-write", "C7", "append", HARNESS,
     "def _e():\n    os.environ[REAL_FIT_ENV_SWITCH] = REAL_FIT_ENV_TOKEN", False),
    ("c7-update", "C7", "append", HARNESS,
     "def _e():\n    os.environ.update({REAL_FIT_ENV_SWITCH: REAL_FIT_ENV_TOKEN})", False),
    ("c7-setdefault", "C7", "append", HARNESS,
     "def _e():\n    os.environ.setdefault(REAL_FIT_ENV_SWITCH, REAL_FIT_ENV_TOKEN)", False),
    ("c7-os-putenv", "C7", "append", HARNESS,
     "def _e():\n    os.putenv(REAL_FIT_ENV_SWITCH, REAL_FIT_ENV_TOKEN)", False),
    ("c7-os-unsetenv", "C7", "append", HARNESS,
     "def _e():\n    os.unsetenv(REAL_FIT_ENV_SWITCH)", False),
    ("c7-assign-whole", "C7", "append", HARNESS,
     "def _e():\n    os.environ = {REAL_FIT_ENV_SWITCH: REAL_FIT_ENV_TOKEN}", True),
    ("c7-augassign-whole", "C7", "append", HARNESS,
     "def _e():\n    os.environ |= {REAL_FIT_ENV_SWITCH: REAL_FIT_ENV_TOKEN}", True),
    ("c7-annassign-whole", "C7", "append", HARNESS,
     "def _e():\n    os.environ: dict = {REAL_FIT_ENV_SWITCH: REAL_FIT_ENV_TOKEN}", True),
    ("c7-delete-whole", "C7", "append", HARNESS, "def _e():\n    del os.environ", True),
    ("c7-bare-name-assign", "C7", "append", HARNESS,
     "def _e():\n    environ = {'A': 'B'}\n    return environ", True),
    ("c7-tuple-destructure", "C7", "append", HARNESS,
     "def _e():\n    (os.environ,) = ({'A': 'B'},)", True),
    ("c7-list-destructure", "C7", "append", HARNESS,
     "def _e():\n    [os.environ] = [{'A': 'B'}]", True),
    ("c7-for-target", "C7", "append", HARNESS,
     "def _e():\n    for os.environ in [{'A': 'B'}]:\n        pass", True),
    ("c7-with-target", "C7", "append", HARNESS,
     "def _e():\n    with open(__file__) as os.environ:\n        pass", True),
    ("c7-except-as-bare", "C7", "append", HARNESS,
     "try:\n    raise Exception()\nexcept Exception as environ:\n    pass", True),
    ("c7-match-capture-bare", "C7", "append", HARNESS,
     "match None:\n    case environ:\n        pass", True),
    ("c7-def-shadow-bare", "C7", "append", HARNESS,
     "def environ():\n    return {}", True),
    ("c7-class-shadow-bare", "C7", "append", HARNESS,
     "class environ:\n    pass", True),
    ("c7-import-alias-bare", "C7", "append", HARNESS,
     "import pathlib as environ", True),

    # ---- C4 / C4b / C1, kept so the corpus covers the whole contract -----------------------------
    ("c4-composed-path-read", "C4", "append", BUILDER,
     'def _i():\n    return pd.read_csv(DATA / "season_dataset_2014_2026.csv")', False),
    ("c4-assigned-composed-path", "C4", "append", BUILDER,
     'def _i():\n    p = DATA / "season_dataset_2014_2026.csv"\n    return pd.read_csv(p)', False),
    ("c4-pathlib-literal", "C4", "append", BUILDER,
     'def _i():\n    p = pathlib.Path("season_dataset_2014_2026.csv")\n'
     '    return pd.read_parquet(p)', False),
    ("c4-token-in-dict", "C4", "append", BUILDER,
     'PATHS = {"panel": "season_dataset_2014_2026.csv"}', False),
    ("c4-token-in-list", "C4", "append", BUILDER,
     'COLS = ["sleeper_pts_half_ppr", "target_ppg"]', False),
    ("c4-token-in-fstring", "C4", "append", BUILDER,
     'def _i():\n    return f"x-sleeper_pts_half_ppr"', False),
    ("c4-literal-reader-arg", "C4", "append", BUILDER,
     "def _i():\n    return pd.read_csv('season_dataset_2014_2026.csv')", False),
    ("c4-literal-subscript", "C4", "append", BUILDER, "def _i():\n    return ps['half_ppr']", False),
    # C3 is the banned-CALLEE clause, not the banned-token clause: this case calls
    # `season_total_target()` and would be caught even with no banned string present anywhere.
    ("c3-banned-callee", "C3", "append", BUILDER, "def _i():\n    return season_total_target()", False),
    ("c4b-through-token-tuple", "C4b", "append", HARNESS,
     'def _i():\n    return pd.read_csv(DATA / BANNED_OUTCOME_TOKENS[0])', False),
    ("c4b-through-audit-record", "C4b", "append", HARNESS,
     'def _i():\n    return pd.read_csv(audit_production()["prediction_target"]["name"])', False),
    ("c1-module-omitted", "C1", "drop_module", BUILDER, None, False),
    ("c1-extra-module", "C1", "extra_module", "somewhere_else.py", "x = 1\n", False),
)

# Positive controls: these must be ok=True under the CURRENT validator. They are deliberately kept out
# of the injection corpus so that "N injections" never silently includes a control.
POSITIVE_CONTROLS = (
    ("ctl-canonical", "canonical source, untouched", None, None),
    ("ctl-config-environ-assign", "unrelated config.environ assignment", HARNESS,
     "class _Cfg:\n    pass\n\n\ndef _ok():\n    config = _Cfg()\n    config.environ = {}\n"
     "    return config"),
    ("ctl-config-environ-update", "unrelated config.environ.update()", HARNESS,
     "class _Cfg2:\n    pass\n\n\ndef _ok2():\n    config = _Cfg2()\n    config.environ = dict()\n"
     "    config.environ.update({})\n    return config"),
    ("ctl-config-putenv", "unrelated config.putenv()", HARNESS,
     "class _Cfg3:\n    def putenv(self, *a):\n        return None\n\n\n"
     "def _ok3():\n    return _Cfg3().putenv('A', 'B')"),
    ("ctl-config-unsetenv", "unrelated config.unsetenv()", HARNESS,
     "class _Cfg4:\n    def unsetenv(self, *a):\n        return None\n\n\n"
     "def _ok4():\n    return _Cfg4().unsetenv('A')"),
    ("ctl-docstring-tokens", "docstring naming banned tokens", BUILDER,
     'def _documented():\n'
     '    """Never reads season_dataset_2014_2026.csv or target_ppg."""\n'
     '    return None'),
    ("ctl-comment-tokens", "comment naming banned tokens", BUILDER,
     "# season_dataset_2014_2026.csv and target_ppg named in a COMMENT"),
)


# The C5-S door, verbatim as it stood while the historical measurement was taken. The live harness now
# carries the C5-A implemented door, and the vendored a5b4af7 validator only knows C5-S — so judging
# today's source with it would flag the door itself and make every other injection look "caught" for
# the wrong reason (measured: 41 -> 5). The historical arm therefore reverts ONLY the door; every other
# clause is still exercised against the live module body.
C5S_DOOR = '''def assemble_real_panel(*_a, **_k):
    """The C5-S door, as it stood at the historical revision."""
    require_real_fit_authorization()
    raise NotImplementedError("not implemented in the v3.9 prefit pass")'''


def pure_sources():
    """The LIVE module sources — what the CURRENT validator is measured against."""
    return {m: (COACH / m).read_text(encoding="utf-8") for m in (BUILDER, HARNESS)}


def historical_pure_sources():
    """Live sources with the entry point reverted to C5-S — the basis the historical arm needs.

    A red proof compares two validators; it is only meaningful if each judges a source its contract
    was written for. The 41/65 figure is a property of (historical validator x C5-S source shape) and
    is measured as such. The operative safety number, 0/65, is measured against the LIVE source.
    """
    s = pure_sources()
    s[HARNESS] = _replace_entry_point(s[HARNESS], C5S_DOOR)
    return s


def _replace_entry_point(src, replacement):
    import re
    pat = re.compile(r"\ndef assemble_real_panel\(.*?\n(?=\n\n(?:# |def |[A-Z_]+ ))", re.DOTALL)
    out, n = pat.subn("\n" + replacement, src)
    assert n == 1, f"expected one assemble_real_panel def, replaced {n}"
    return out


def build_sources(kind, module, payload, historical=False):
    """Materialise one case as an in-memory sources mapping. Canonical files are never touched.

    `historical=True` bases the case on the C5-S source shape, which is the only shape the vendored
    a5b4af7 validator's C5 clause was written for.
    """
    s = historical_pure_sources() if historical else pure_sources()
    if kind == "append":
        s[module] = s[module] + "\n\n" + payload + "\n"
    elif kind == "replace_entry_point":
        s[module] = _replace_entry_point(s[module], payload)
    elif kind == "drop_module":
        s.pop(module)
    elif kind == "extra_module":
        s[module] = payload
    else:
        raise ValueError(f"unknown case kind {kind!r}")
    return s


def case_sources(case, historical=False):
    _id, _cat, kind, module, payload, _hist = case
    return build_sources(kind, module, payload, historical=historical)


def control_sources(control, historical=False):
    _id, _label, module, payload = control
    if module is None:
        return historical_pure_sources() if historical else pure_sources()
    return build_sources("append", module, payload, historical=historical)


# Every clause of the frozen contract that the corpus exercises, in contract order. C3 (banned callee)
# is its own clause and was previously mislabelled C4 (banned token) — a case that calls
# `season_total_target()` is caught by C3 whether or not any banned string appears.
# C5A is the IMPLEMENTED-door contract, added when the entry point moved from C5-S to C5-A.
CATEGORIES = ("C1", "C3", "C4", "C4b", "C5", "C5A", "C6", "C7")


def totals():
    """(per-category {cat: (undetected_historically, n_cases)}, total_undetected, n_cases)."""
    per = {}
    for cid, cat, _k, _m, _p, hist in CORPUS:
        u, n = per.get(cat, (0, 0))
        per[cat] = (u + (1 if hist else 0), n + 1)
    tot_u = sum(u for u, _n in per.values())
    return per, tot_u, len(CORPUS)
