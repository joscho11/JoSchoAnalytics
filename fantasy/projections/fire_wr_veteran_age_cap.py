"""One-shot fire runner for PREREG_wr_veteran_age_cap_2026-07-24.

Writes no model or result artifact.  It evaluates only the locked direct-total
baseline/challenger comparison when invoked explicitly with --fire.
"""
from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import build_rb_projection as B
import wr_veteran_age_cap_harness as H

STAGE_DIR = Path("C:/tmp/wr_veteran_age_cap_fire_20260724")
BASELINE_RESULTS = HERE / "results" / "wr_walkforward_predictions.csv"

def _md5(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def _load_veterans() -> pd.DataFrame:
    required = {"player_id", "position", "is_rookie", "season", *H.FROZEN_BASELINE_FEATURES}
    forbidden = [c for c in required if any(t in c.lower() for t in H.FORBIDDEN_MARKET_TOKENS)]
    assert not forbidden, f"market column requested: {forbidden}"
    df = pd.read_csv(H.SEASON_DATASET, usecols=lambda c: c in required)
    assert required.issubset(df.columns), "season dataset columns drifted"
    assert not any(any(t in c.lower() for t in H.FORBIDDEN_MARKET_TOKENS) for c in df.columns)
    df = df[(df.position == "WR") & (df.is_rookie == 0)].copy()
    target = B.season_total_target()
    df = df.merge(target, on=["player_id", "season"], how="left")
    df.loc[df.season <= B.MAXOBS, "y"] = df.loc[df.season <= B.MAXOBS, "y"].fillna(0.0)
    df[H.CHALLENGER_AGE_COL] = df.age.clip(upper=30.0)
    return df


def _walk_forward(df: pd.DataFrame, features: tuple[str, ...], label: str,
                  years: tuple[int, ...] = H.TEST_SEASONS, verbose: bool = True) -> pd.DataFrame:
    rows = []
    for year in years:
        train = df[(df.season < year) & df.y.notna()].copy()
        test = df[(df.season == year) & df.y.notna()].copy()
        assert not train.empty and not test.empty, f"empty fold {label}/{year}"
        assert (train.season < year).all(), f"walk-forward leakage {label}/{year}"
        (family, params, inner_mae), _ = B.nested_select(train, list(features))
        x_train, x_test = B._prep(family, train, test, list(features))
        pred = B._fit_predict(family, params, x_train, train.y.to_numpy(float), x_test)
        rows.append(pd.DataFrame({
            "season": year,
            "player_id": test.player_id.to_numpy(),
            "age": test.age.to_numpy(float),
            "y": test.y.to_numpy(float),
            "pred": pred,
            "model": family,
            "inner_mae": inner_mae,
        }))
        if verbose:
            print(f"  {label} {year}: {family}, inner MAE={inner_mae:.3f}, train={len(train)}, test={len(test)}")
    return pd.concat(rows, ignore_index=True)


def _cluster_t(values: pd.DataFrame) -> float:
    clusters = values.groupby("player_id", sort=False).delta.mean()
    assert len(clusters) >= 2 and clusters.std(ddof=1) > 0, "fewer than two nonconstant player clusters"
    return float(clusters.mean() / clusters.std(ddof=1))


def tune(year: int, family: str) -> None:
    """Persist one frozen inner-CV family grid without an outer prediction or metric."""
    assert year in H.TEST_SEASONS and family in B.FAMILIES
    df = _load_veterans()
    train = df[(df.season < year) & df.y.notna()].copy()
    scores = []
    for params in B._grid(family):
        maes = []
        for season in sorted(train.season.unique()):
            inner_train, valid = train[train.season != season], train[train.season == season]
            if len(inner_train) < 50 or len(valid) < 5:
                continue
            x_train, x_valid = B._prep(family, inner_train, valid, list(H.challenger_features()))
            pred = B._fit_predict(family, params, x_train, inner_train.y.to_numpy(float), x_valid)
            maes.append(B._mae(valid.y, pred))
        if maes:
            scores.append((params, float(np.mean(maes))))
    assert scores, f"no inner-CV scores for {year}/{family}"
    STAGE_DIR.mkdir(parents=True, exist_ok=True)
    pd.to_pickle(scores, STAGE_DIR / f"tune_{year}_{family}.pkl")
    (STAGE_DIR / f"tune_{year}_{family}.sha256").write_text(_locked_source_hash(), encoding="utf-8")
    print(f"staged locked inner-CV {year}/{family}; no outer prediction or metric printed")


def _placebo(all_rows: pd.DataFrame, older_counts: dict[int, int]) -> np.ndarray:
    rng = np.random.default_rng(42)
    all_rows = all_rows[["season", "player_id", "delta"]].copy()
    draws = []
    for _ in range(1000):
        selected = []
        for year, n_older in older_counts.items():
            pool = all_rows[all_rows.season == year]
            selected.append(pool.iloc[rng.choice(len(pool), size=n_older, replace=False)])
        draws.append(_cluster_t(pd.concat(selected, ignore_index=True)))
    return np.asarray(draws, dtype=float)


def _locked_source_hash() -> str:
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def stage(year: int) -> None:
    """Compute the challenger folds without printing an outcome metric."""
    assert year in H.TEST_SEASONS, f"invalid outer test year: {year}"
    assert hashlib.sha256(HERE.joinpath("wr_veteran_age_cap_harness.py").read_bytes()).hexdigest() == \
        "288350a7c3b36c5298cc2c98b7b5c9fe030092e8efd058ed52a4f84afd1a1225", "locked structural harness changed"
    before = H.artifact_hashes()
    H.structural_summary(H.load_structural_panel())
    df = _load_veterans()
    baseline = pd.read_csv(BASELINE_RESULTS)
    baseline = baseline[(baseline.grp == "vet") & (baseline.season == year)].copy()
    missing = [family for family in B.FAMILIES if not (STAGE_DIR / f"tune_{year}_{family}.pkl").exists()]
    assert not missing, f"missing inner-CV stages for {year}: {missing}"
    assert all((STAGE_DIR / f"tune_{year}_{family}.sha256").read_text(encoding="utf-8") == _locked_source_hash()
               for family in B.FAMILIES), "inner-CV stages were produced by different source"
    options = [(mae, family, params) for family in B.FAMILIES
               for params, mae in pd.read_pickle(STAGE_DIR / f"tune_{year}_{family}.pkl")]
    inner_mae, family, params = min(options, key=lambda row: row[0])
    train = df[(df.season < year) & df.y.notna()].copy()
    test = df[(df.season == year) & df.y.notna()].copy()
    x_train, x_test = B._prep(family, train, test, list(H.challenger_features()))
    pred = B._fit_predict(family, params, x_train, train.y.to_numpy(float), x_test)
    challenger = pd.DataFrame({"season": year, "player_id": test.player_id.to_numpy(),
                               "age": test.age.to_numpy(float), "y": test.y.to_numpy(float),
                               "pred": pred, "model": family, "inner_mae": inner_mae})
    keys = ["season", "player_id"]
    baseline = baseline.sort_values(keys).reset_index(drop=True)
    challenger = challenger.sort_values(keys).reset_index(drop=True)
    assert baseline[keys].equals(challenger[keys]), "baseline/challenger outer identities differ"
    assert np.allclose(baseline.y, challenger.y), "baseline/challenger targets differ"
    staged = baseline.merge(challenger[keys + ["pred"]], on=keys, suffixes=("_baseline", "_capped"), validate="one_to_one")
    assert len(staged) == len(baseline) == len(challenger)
    staged["delta"] = np.abs(staged.y - staged.pred_baseline) - np.abs(staged.y - staged.pred_capped)
    STAGE_DIR.mkdir(parents=True, exist_ok=True)
    staged.to_pickle(STAGE_DIR / f"fold_{year}.pkl")
    (STAGE_DIR / f"fold_{year}.sha256").write_text(_locked_source_hash(), encoding="utf-8")
    assert before == H.artifact_hashes(), "stage altered a protected WR artifact"
    print(f"staged locked age-cap challenger fold {year}; no outcome metric printed")


def fire() -> dict[str, object]:
    assert hashlib.sha256(HERE.joinpath("wr_veteran_age_cap_harness.py").read_bytes()).hexdigest() == \
        "288350a7c3b36c5298cc2c98b7b5c9fe030092e8efd058ed52a4f84afd1a1225", "locked structural harness changed"
    before = H.artifact_hashes()
    H.structural_summary(H.load_structural_panel())
    missing = [year for year in H.TEST_SEASONS if not (STAGE_DIR / f"fold_{year}.pkl").exists()]
    assert not missing, f"missing staged challenger folds: {missing}"
    assert all((STAGE_DIR / f"fold_{year}.sha256").read_text(encoding="utf-8") == _locked_source_hash()
               for year in H.TEST_SEASONS), "staged folds were produced by different source"
    merged = pd.concat([pd.read_pickle(STAGE_DIR / f"fold_{year}.pkl") for year in H.TEST_SEASONS], ignore_index=True)
    older = merged[merged.age >= 30.0].copy()
    younger = merged[merged.age < 30.0].copy()
    got_counts = older.groupby("season").size().to_dict()
    assert got_counts == H.EXPECTED_OLDER_COUNTS and older.player_id.nunique() == H.EXPECTED_OLDER_PLAYERS
    t_older = _cluster_t(older)
    placebo = _placebo(merged, got_counts)
    bar = float(np.quantile(placebo, 0.95))
    t_younger = _cluster_t(younger)
    season_delta = older.groupby("season").delta.mean().to_dict()
    a = t_older > bar
    b = sum(x > 0 for x in season_delta.values()) >= 4
    c = t_younger >= -0.100
    verdict = "PASS" if a and b and c else "FAIL"
    after = H.artifact_hashes()
    assert before == after, "fire altered a protected WR artifact"
    print("\nWR VETERAN AGE-CAP — THE ONE SHOT")
    print(f"age-30+ direct-MAE delta: {older.delta.mean():+.3f} (n={len(older)}, players={older.player_id.nunique()})")
    print("per-season age-30+ deltas: " + "  ".join(f"{y}:{season_delta[y]:+.3f}" for y in H.TEST_SEASONS))
    print(f"(a) T_30plus {t_older:+.3f} > placebo p95 {bar:+.3f}: {a}")
    print(f"(b) positive age-tail seasons {sum(x > 0 for x in season_delta.values())}/5 >= 4: {b}")
    print(f"(c) T_under30 {t_younger:+.3f} >= -0.100: {c}")
    print(f"VERDICT: {verdict}")
    return {"verdict": verdict, "t_30plus": t_older, "placebo_p95": bar, "t_under30": t_younger,
            "age_tail_mae_delta": float(older.delta.mean()), "season_deltas": season_delta,
            "positive_seasons": int(sum(x > 0 for x in season_delta.values()))}


def execute() -> dict[str, object]:
    """Run the locked challenger end-to-end, then emit its sole readout."""
    assert hashlib.sha256(HERE.joinpath("wr_veteran_age_cap_harness.py").read_bytes()).hexdigest() == \
        "288350a7c3b36c5298cc2c98b7b5c9fe030092e8efd058ed52a4f84afd1a1225", "locked structural harness changed"
    before = H.artifact_hashes()
    H.structural_summary(H.load_structural_panel())
    df = _load_veterans()
    baseline = pd.read_csv(BASELINE_RESULTS)
    baseline = baseline[(baseline.grp == "vet") & baseline.season.isin(H.TEST_SEASONS)].copy()
    challenger = _walk_forward(df, H.challenger_features(), "capped", H.TEST_SEASONS, verbose=False)
    keys = ["season", "player_id"]
    baseline = baseline.sort_values(keys).reset_index(drop=True)
    challenger = challenger.sort_values(keys).reset_index(drop=True)
    assert baseline[keys].equals(challenger[keys]), "baseline/challenger outer identities differ"
    assert np.allclose(baseline.y, challenger.y), "baseline/challenger targets differ"
    merged = baseline.merge(challenger[keys + ["age", "pred"]], on=keys,
                            suffixes=("_baseline", "_capped"), validate="one_to_one")
    merged["delta"] = np.abs(merged.y - merged.pred_baseline) - np.abs(merged.y - merged.pred_capped)
    STAGE_DIR.mkdir(parents=True, exist_ok=True)
    for year in H.TEST_SEASONS:
        merged[merged.season == year].to_pickle(STAGE_DIR / f"fold_{year}.pkl")
        (STAGE_DIR / f"fold_{year}.sha256").write_text(_locked_source_hash(), encoding="utf-8")
    assert before == H.artifact_hashes(), "execute altered a protected WR artifact"
    return fire()


def main() -> None:
    parser = argparse.ArgumentParser(description="One-shot WR veteran age-cap fire runner")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--tune", nargs=2, metavar=("YEAR", "FAMILY"), help="stage one inner-CV family grid")
    group.add_argument("--stage", type=int, metavar="YEAR", help="stage one frozen fold without a metric")
    group.add_argument("--fire", action="store_true", help="emit the single final readout from staged folds")
    group.add_argument("--execute", action="store_true", help="run the locked challenger and emit its sole readout")
    args = parser.parse_args()
    if args.tune is not None:
        tune(int(args.tune[0]), args.tune[1])
    elif args.stage is not None:
        stage(args.stage)
    elif args.execute:
        execute()
    else:
        fire()


if __name__ == "__main__":
    main()
