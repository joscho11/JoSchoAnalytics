"""RESULT OWNERSHIP for the v3.9 authorized real run — the ONLY writer of the five outputs.

WHY THIS IS A SEPARATE MODULE
-----------------------------
Neither existing v3.9 module may write these files. `run_coach_projection_experiment_v39.py` is held to
"every `to_csv` targets `DATA /`" by `test_the_v39_modules_never_write_outside_the_coaching_data_dir`,
and `assemble_real_panel_v39.py` is held to "no writer callee at all" by
`test_the_assembly_module_writes_nothing`. Both prohibitions are worth keeping exactly as they are, so
the writer lives here, under its own contract, and the harness calls it.

WHY THE FILES MOVED OUT OF `coaching/data/`
-------------------------------------------
Approved 2026-08-03 as a pre-outcome OPERATIONAL amendment (Option A). The manifest preregistered these
five outputs into `coaching/data/`, but the preflight check `no_unauthorized_v39_artifact` requires the
`*_v39.*` set in that directory to equal EXACTLY the five FEATURE artifacts. Measured on a temp copy:
writing the results there took preflight from 21/21 to 20/21. The run could not both produce its
preregistered outputs and pass its own preregistered gate.

The results therefore own `coaching/results/`. `V39_ARTIFACT_HASHES` and
`no_unauthorized_v39_artifact` are UNCHANGED and still protect exactly the five feature artifacts in
`coaching/data/`. **This changes storage only. No population, feature, arm, hyperparameter, threshold,
selection rule or verdict criterion is affected.**

THE CONTRACT
------------
  * exactly these five names, no more and no fewer;
  * a pre-existing output refuses unless `overwrite=True` is passed explicitly;
  * every file is written atomically (temp file in the same directory, then `os.replace`);
  * a partial write fails closed — nothing is left behind and no output is half-written;
  * SHA-256 of each file is emitted only after ALL five have landed.
"""
import hashlib
import json
import os
import pathlib
import tempfile

import pandas as pd

HERE = pathlib.Path(__file__).resolve().parent
RESULTS = HERE / "results"

# --- the exact, closed set of result outputs ---------------------------------------------------------
RESULT_FILES = ("arm_selection_v39.csv", "arm_metrics_v39.csv", "arm_bootstrap_v39.csv",
                "arm_placebo_v39.csv", "arm_verdict_v39.csv")

# --- the LOSSLESS mapping from the seven returned frames onto five files -----------------------------
# `run_experiment` returns selection, metrics, bootstrap, placebo, oracle, verdict and preflight.
# Nothing may be silently discarded, so the two frames without a file of their own are MERGED into a
# sibling with an explicit discriminator, and the merge is proven reversible by round-trip test.
RECORD_TYPE = "record_type"
METRIC_RECORD, ORACLE_RECORD = "metric", "oracle"
PREFLIGHT_PREFIX = "preflight_"
# The PRE-OUTCOME eligibility accounting rides in the SAME file, under its own prefix. No sixth
# artifact is created; the full source / excluded-by-reason / eligible counts are preserved.
ELIGIBILITY_PREFIX = "eligibility_"

FRAME_TO_FILE = {
    "selection": "arm_selection_v39.csv",
    "metrics":   "arm_metrics_v39.csv",      # + `oracle`, discriminated by RECORD_TYPE
    "oracle":    "arm_metrics_v39.csv",
    "bootstrap": "arm_bootstrap_v39.csv",
    "placebo":   "arm_placebo_v39.csv",
    "verdict":   "arm_verdict_v39.csv",      # + `preflight`, prefixed columns
    "preflight": "arm_verdict_v39.csv",
}
REQUIRED_FRAMES = ("selection", "metrics", "bootstrap", "placebo", "oracle", "verdict", "preflight")


class ResultWriteError(RuntimeError):
    """Any violation of the result-output contract. Never caught inside this module."""


def _sha256(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


def compose(frames, eligibility=None):
    """The seven returned frames -> exactly five DataFrames, losslessly. Pure; writes nothing.

    `eligibility` is the pre-outcome population accounting; its scalar counts are carried into
    `arm_verdict_v39.csv` under `ELIGIBILITY_PREFIX`, alongside the prefixed preflight record.
    """
    missing = [k for k in REQUIRED_FRAMES if k not in frames]
    if missing:
        raise ResultWriteError(f"run_experiment did not return frame(s): {missing}")
    extra = sorted(set(frames) - set(REQUIRED_FRAMES))
    if extra:
        raise ResultWriteError(f"unexpected frame(s) returned: {extra} — the mapping would drop them")

    metrics, oracle = frames["metrics"].copy(), frames["oracle"].copy()
    metrics.insert(0, RECORD_TYPE, METRIC_RECORD)
    oracle.insert(0, RECORD_TYPE, ORACLE_RECORD)
    merged_metrics = pd.concat([metrics, oracle], ignore_index=True, sort=False)

    verdict, preflight = frames["verdict"].copy(), frames["preflight"].copy()
    preflight = preflight.rename(columns={c: (c if c == "position" else PREFLIGHT_PREFIX + c)
                                          for c in preflight.columns})
    if "position" in verdict.columns and "position" in preflight.columns:
        merged_verdict = verdict.merge(preflight, on="position", how="outer", validate="one_to_one")
    else:
        merged_verdict = pd.concat([verdict, preflight], axis=1)

    if eligibility:
        for key in ("source_population", "excluded_missing_team", "excluded_no_shipped_bundle",
                    "eligible_evaluation_population", "states_are_exhaustive",
                    "states_are_mutually_exclusive"):
            if key in eligibility:
                merged_verdict[ELIGIBILITY_PREFIX + key] = eligibility[key]
        by_reason = eligibility.get("by_reason", {})
        for reason, rec in sorted(by_reason.items()):
            merged_verdict[f"{ELIGIBILITY_PREFIX}{reason}_n"] = rec.get("n")
            merged_verdict[f"{ELIGIBILITY_PREFIX}{reason}_by_position"] = json.dumps(
                rec.get("by_position", {}), sort_keys=True)
            merged_verdict[f"{ELIGIBILITY_PREFIX}{reason}_by_season"] = json.dumps(
                rec.get("by_season", {}), sort_keys=True)

    return {
        "arm_selection_v39.csv": frames["selection"].copy(),
        "arm_metrics_v39.csv":   merged_metrics,
        "arm_bootstrap_v39.csv": frames["bootstrap"].copy(),
        "arm_placebo_v39.csv":   frames["placebo"].copy(),
        "arm_verdict_v39.csv":   merged_verdict,
    }


def recover_oracle(metrics_frame):
    """Reverse of the metrics merge: the oracle rows, with the discriminator removed."""
    sub = metrics_frame[metrics_frame[RECORD_TYPE] == ORACLE_RECORD].drop(columns=[RECORD_TYPE])
    return sub.dropna(axis=1, how="all").reset_index(drop=True)


def recover_metrics(metrics_frame):
    sub = metrics_frame[metrics_frame[RECORD_TYPE] == METRIC_RECORD].drop(columns=[RECORD_TYPE])
    return sub.dropna(axis=1, how="all").reset_index(drop=True)


def recover_eligibility(verdict_frame):
    """The pre-outcome eligibility accounting, recovered from the serialized verdict file."""
    cols = [c for c in verdict_frame.columns if c.startswith(ELIGIBILITY_PREFIX)]
    if not cols:
        return {}
    row = verdict_frame[cols].iloc[0]
    out = {}
    for c in cols:
        key, val = c[len(ELIGIBILITY_PREFIX):], row[c]
        out[key] = json.loads(val) if isinstance(val, str) and val.startswith("{") else val
    return out


def recover_preflight(verdict_frame):
    """Reverse of the verdict merge: the preflight record, with the prefix stripped."""
    cols = [c for c in verdict_frame.columns if c.startswith(PREFLIGHT_PREFIX) or c == "position"]
    cols = [c for c in cols if not c.startswith(ELIGIBILITY_PREFIX)]
    sub = verdict_frame[cols].rename(
        columns={c: c[len(PREFLIGHT_PREFIX):] for c in cols if c.startswith(PREFLIGHT_PREFIX)})
    return sub.reset_index(drop=True)


def recover_verdict(verdict_frame):
    cols = [c for c in verdict_frame.columns
            if not c.startswith(PREFLIGHT_PREFIX) and not c.startswith(ELIGIBILITY_PREFIX)]
    return verdict_frame[cols].reset_index(drop=True)


def validate_outputs(composed):
    """Exactly the five names, nothing missing, nothing extra, no empty frame."""
    problems = []
    names = set(composed)
    missing, extra = sorted(set(RESULT_FILES) - names), sorted(names - set(RESULT_FILES))
    if missing:
        problems.append(f"missing output(s): {missing}")
    if extra:
        problems.append(f"output(s) outside the permitted set: {extra}")
    for name, frame in sorted(composed.items()):
        if not isinstance(frame, pd.DataFrame):
            problems.append(f"{name} is {type(frame).__name__}, not a DataFrame")
        elif frame.empty:
            problems.append(f"{name} is empty; a result file with no rows is not a result")
    return problems


def write_results(frames, out_dir=None, overwrite=False, eligibility=None):
    """Compose, validate, then write all five ATOMICALLY. Returns {name: sha256}.

    Fails closed: if any file cannot be written, every file staged by THIS call is removed and the
    directory is left as it was found. Hashes are emitted only after all five have landed.
    """
    out = RESULTS if out_dir is None else pathlib.Path(out_dir)
    composed = compose(frames, eligibility=eligibility)
    problems = validate_outputs(composed)
    if problems:
        raise ResultWriteError("result outputs: " + "; ".join(problems))

    out.mkdir(parents=True, exist_ok=True)
    if not overwrite:
        existing = sorted(n for n in RESULT_FILES if (out / n).exists())
        if existing:
            raise ResultWriteError(
                f"refusing to overwrite existing result(s) {existing} in {out}; pass overwrite=True "
                f"to replace them deliberately")

    landed = []
    try:
        for name in RESULT_FILES:
            frame = composed[name]
            fd, tmp = tempfile.mkstemp(prefix=f".{name}.", suffix=".partial", dir=str(out))
            os.close(fd)
            try:
                frame.to_csv(tmp, index=False)
                os.replace(tmp, out / name)          # atomic within the directory
            finally:
                if os.path.exists(tmp):
                    os.unlink(tmp)
            landed.append(out / name)
    except Exception:
        for p in landed:                              # fail closed: leave no partial result set
            try:
                p.unlink()
            except OSError:
                pass
        raise

    return {p.name: _sha256(p) for p in landed}
