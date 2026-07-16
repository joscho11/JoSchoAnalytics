"""Schema validation, provenance stamps, and the shared dash-rule predicate.

Best-practices layer (R20): every pipeline boundary validates loudly (offending
rows printed, never silent coercion); every artifact carries a provenance
sidecar; the two-cell dash rule lives HERE, in one place, used by both artifact
builders (R12).
"""
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

CODE_VERSION = "talent-build 2026-07-16 phase2"


class SchemaError(ValueError):
    pass


def validate(df, name, required=None, no_nan=None, dtypes=None, checks=None):
    """Fail loud with offending rows printed. Returns df untouched."""
    problems = []
    if required:
        missing = [c for c in required if c not in df.columns]
        if missing:
            problems.append(f"missing columns {missing}")
    if no_nan:
        for c in [c for c in no_nan if c in df.columns]:
            bad = df[df[c].isna()]
            if len(bad):
                problems.append(f"{len(bad)} NaN in key column '{c}'; first rows:\n"
                                f"{bad.head(3)}")
    if dtypes:
        for c, kind in dtypes.items():
            if c in df.columns and not getattr(pd.api.types, f"is_{kind}_dtype")(df[c]):
                problems.append(f"column '{c}' is {df[c].dtype}, expected {kind}")
    if checks:
        for desc, mask_fn in checks.items():
            bad = df[~mask_fn(df)]
            if len(bad):
                problems.append(f"check '{desc}' fails on {len(bad)} rows; first:\n"
                                f"{bad.head(3)}")
    if problems:
        raise SchemaError(f"[schema:{name}] " + " | ".join(problems))
    return df


def join_audit(name, left_n, matched_n, collision_map=None, fail_on_collision=False):
    """Print matched/unmatched; print any normalized-name collision (name -> 2+ ids);
    fail the build if a collision would be silently dropped."""
    print(f"[join-audit:{name}] matched {matched_n}/{left_n} "
          f"({100*matched_n/max(left_n,1):.0f}%), unmatched {left_n-matched_n}")
    if collision_map:
        cols = {k: v for k, v in collision_map.items() if len(v) > 1}
        if cols:
            print(f"[join-audit:{name}] COLLISIONS (normalized name -> 2+ ids): {cols}")
            if fail_on_collision:
                raise SchemaError(f"[join-audit:{name}] unresolved collisions {cols}")
        else:
            print(f"[join-audit:{name}] no collisions")


def is_nfl(gsis_id, nfl_ids):
    """The dash rule (R12): a player with ANY NFL regular-season stat line
    (player_stats 2018+) carries a Talent Score; zero NFL snaps -> Rookie Score.
    One predicate, both artifact builders."""
    return gsis_id in nfl_ids


def stable_rank_sort(S):
    """Deterministic board order: score desc, then confidence (w) desc — the 3c
    near-tie rule — then gsis asc as the final total-order tiebreak."""
    out = S.assign(_g=S.index.astype(str)).sort_values(
        ["score", "w", "_g"], ascending=[False, False, True],
        kind="mergesort").drop(columns="_g")
    out["rank_pos"] = np.arange(1, len(out) + 1)
    return out


def provenance(ns, seed, extra=None):
    here = Path(__file__).resolve().parent
    try:
        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=here,
                              capture_output=True, text=True, timeout=10).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain"], cwd=here,
                               capture_output=True, text=True, timeout=10).stdout.strip()
        git = head + (" (dirty)" if dirty else "")
    except Exception:
        git = "unavailable"
    p = {"built_utc": datetime.now(timezone.utc).isoformat(),
         "git_head": git,
         "config_md5": hashlib.md5((here / "config.py").read_bytes()).hexdigest(),
         "NS": ns, "seed": seed, "code_version": CODE_VERSION}
    if extra:
        p.update(extra)
    return p


def write_artifact(df, path, ns, seed, extra=None):
    """CSV (deterministic float format) + provenance sidecar."""
    path = Path(path)
    df.to_csv(path, index=False, float_format="%.6f", lineterminator="\n")
    sidecar = path.with_suffix(".provenance.json")
    sidecar.write_text(json.dumps(provenance(ns, seed, extra), indent=1))
    print(f"[artifact] wrote {path.name} ({len(df)} rows) + {sidecar.name}")
