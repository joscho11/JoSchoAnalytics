"""Back up the published artifacts, then promote the staged ones. Gated.

Promotion runs ONLY if `gate_staging_dataset.py` last reported `all_pass: true` and every
staged model hash in the manifest still matches the file on disk. Everything replaced is
copied first to `fantasy/backup_pre_depthfix_<utc>/`, and the exact backup is recorded in
`fantasy/staging/promotion.json` so the promotion is reversible.

    python promote_staging.py --dry-run
    python promote_staging.py
    python promote_staging.py --rollback fantasy/backup_pre_depthfix_...
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

_HERE = Path(__file__).parent
STAGING = _HERE / "staging"
PROD_MODELS = _HERE / "models"


def sha256(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def promote(dry_run: bool = False) -> Path:
    gate = json.loads((STAGING / "gate_report.json").read_text(encoding="utf-8"))
    if not gate.get("all_pass"):
        failed = [g["gate"] for g in gate["gates"] if g["status"] == "FAIL"]
        raise SystemExit(f"REFUSING to promote — gates failed: {failed}")

    manifest = json.loads((STAGING / "manifest_primary.json").read_text(encoding="utf-8"))
    for name, digest in manifest["artifacts"].items():
        actual = sha256(STAGING / "models" / name)
        if actual != digest:
            raise SystemExit(f"REFUSING to promote — {name} sha256 {actual[:12]} does not "
                             f"match the manifest {digest[:12]}")
    if len(manifest["artifacts"]) != 12:
        raise SystemExit(f"REFUSING to promote — expected 12 staged models, found "
                         f"{len(manifest['artifacts'])}")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = _HERE / f"backup_pre_depthfix_{stamp}"
    moves = [(STAGING / "features_dataset.staging.csv", _HERE / "features_dataset.csv"),
             (STAGING / "raw_dataset.staging.csv", _HERE / "raw_dataset.csv")]
    moves += [(STAGING / "models" / n, PROD_MODELS / n)
              for n in sorted(manifest["artifacts"])]

    record = {"promoted_utc": datetime.now(timezone.utc).isoformat(),
              "backup_dir": str(backup), "gate_report_all_pass": True,
              "manifest": "manifest_primary.json", "files": []}

    if dry_run:
        for src, dst in moves:
            print(f"  would copy {src.name} -> {dst.relative_to(_HERE)}")
        return backup

    (backup / "models").mkdir(parents=True, exist_ok=True)
    for src, dst in moves:
        if dst.exists():
            bdst = backup / ("models/" + dst.name if dst.parent == PROD_MODELS
                             else dst.name)
            shutil.copy2(dst, bdst)
            record["files"].append({"target": str(dst.relative_to(_HERE)),
                                    "backup_sha256": sha256(bdst),
                                    "new_sha256": sha256(src)})
        shutil.copy2(src, dst)
        print(f"  promoted {dst.relative_to(_HERE)}")

    (STAGING / "promotion.json").write_text(json.dumps(record, indent=1),
                                            encoding="utf-8")
    print(f"\nBackup: {backup}")
    return backup


def rollback(backup: Path):
    for p in sorted(backup.glob("*.csv")):
        shutil.copy2(p, _HERE / p.name)
        print(f"  restored {p.name}")
    for p in sorted((backup / "models").glob("*.pkl")):
        shutil.copy2(p, PROD_MODELS / p.name)
        print(f"  restored models/{p.name}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--rollback")
    a = ap.parse_args()
    if a.rollback:
        rollback(Path(a.rollback))
    else:
        promote(a.dry_run)
