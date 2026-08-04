"""Regenerate the committed checkpoint FIXTURES from a real build directory.

Why this exists
---------------
The Phase-1/Phase-2 talent suites read pickled build checkpoints. Those used to
be read from a hardcoded machine-local scratch path (``C:/tmp/talent_build``),
which does not exist on a CI runner -- so all 14 checkpoint-dependent tests
SKIPPED and the job went green while testing nothing.

The heavy build cannot be reproduced in CI (it needs nflreadpy pulls and the
licensed PFF inputs), so the checkpoints are committed as fixtures instead.
FACETS.pkl is SLIMMED to only the fields the suites read (``defs`` pid columns
and ``nfl_ids``); the MODEL/BOARD checkpoints are copied whole because the
determinism, golden and k-derivation tests read every frame in them.

Usage (only after a real rebuild of the talent checkpoints)::

    TALENT_WORK=C:/tmp/talent_build python fantasy/talent/tests/fixtures/make_fixtures.py

It reads ``--src`` (default ``config.WORK``) and writes ``fixtures/work/``.
This script NEVER writes to the source directory.
"""
import argparse
import pickle
import shutil
import sys
from pathlib import Path

PKG = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PKG))

from config import WORK, FIXTURE_WORK  # noqa: E402

# Copied verbatim -- small (<350 KB each) and read field-by-field by the tests.
WHOLE = ["MODEL_reproduce.pkl", "BOARD_reproduce.pkl",
         "MODEL_ruled.pkl", "MODEL_ruled2.pkl",
         "BOARD_ruled.pkl", "BOARD_ruled2.pkl"]


def slim_facets(src: Path, dst: Path) -> None:
    """FACETS.pkl is ~14 MB; the suites read only defs[*].pid and nfl_ids."""
    with open(src, "rb") as fh:
        fac = pickle.load(fh)
    slim = {
        "defs": {P: [(nm, df[["pid"]].drop_duplicates().reset_index(drop=True))
                     for nm, df in defs]
                 for P, defs in fac["defs"].items()},
        "nfl_ids": set(fac["nfl_ids"]),
        "_slimmed": True,
    }
    with open(dst, "wb") as fh:
        pickle.dump(slim, fh, protocol=4)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=WORK, help="real build checkpoint dir")
    ap.add_argument("--dst", default=FIXTURE_WORK)
    a = ap.parse_args()
    src, dst = Path(a.src), Path(a.dst)
    dst.mkdir(parents=True, exist_ok=True)
    missing = [n for n in WHOLE + ["FACETS.pkl"] if not (src / n).exists()]
    if missing:
        raise SystemExit(f"source checkpoints missing in {src}: {missing}")
    for n in WHOLE:
        shutil.copyfile(src / n, dst / n)
        print(f"copied  {n:24s} {(dst / n).stat().st_size / 1024:8.1f} KB")
    slim_facets(src / "FACETS.pkl", dst / "FACETS.pkl")
    print(f"slimmed FACETS.pkl               "
          f"{(dst / 'FACETS.pkl').stat().st_size / 1024:8.1f} KB")


if __name__ == "__main__":
    main()
