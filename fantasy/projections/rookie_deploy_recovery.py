"""Deploy-only recovery for rookies missing from nflverse's GSIS draft bridge.

The frozen hit-probability harness is intentionally left untouched: changing it would
invalidate its one-shot fire manifest.  This module corrects only the 2026 projection
matrix when a player already has a canonical GSIS row in ``season_dataset`` but nflverse
has not yet populated that player's ``gsis_id`` in ``load_draft_picks``.  College/PFF
values use the same normalized-name, final-college-season sources as the frozen harness.
"""
from pathlib import Path

import pandas as pd


SEAS = Path(__file__).resolve().parent.parent / "seasonal_projections"
PFF = SEAS / "pff"
PFF_SEASONS = range(2014, 2026)


def _final_pff_by_name(kind: str, feature_cols: list[str]) -> pd.DataFrame:
    """Return final-college-season PFF values for the requested projected columns."""
    prefix = f"pff_{kind}_"
    raw_cols = [c.removeprefix(prefix) for c in feature_cols if c.startswith(prefix)]
    if not raw_cols:
        return pd.DataFrame(columns=["norm_name"])

    frames = []
    for season in PFF_SEASONS:
        path = PFF / f"college_{season}" / f"college_{kind}_summary_{season}.csv"
        if not path.exists():
            continue
        frame = pd.read_csv(path)
        if "player" not in frame.columns:
            continue
        frame["norm_name"] = frame["player"].map(_norm_name)
        frame["season"] = season
        frames.append(frame)
    if not frames:
        return pd.DataFrame(columns=["norm_name"] + [f"{prefix}{c}" for c in raw_cols])

    data = pd.concat(frames, ignore_index=True)
    available = [c for c in raw_cols if c in data.columns]
    final = data.loc[data.groupby("norm_name")["season"].idxmax(), ["norm_name"] + available].copy()
    return final.rename(columns={c: f"{prefix}{c}" for c in available}).drop_duplicates("norm_name")


def _norm_name(value: object) -> str:
    """Use the project's established normalizer without importing the frozen harness."""
    from _utils import norm_name
    return norm_name(value)


def recover_missing_deploy_profiles(
    rook: pd.DataFrame,
    profile_cols: list[str],
    pff_kind: str,
    *,
    deploy_season: int = 2026,
) -> pd.DataFrame:
    """Fill all-empty 2026 rookie profiles from existing college/PFF sources by name.

    Rows that already have any profile value are deliberately preserved.  This is an
    identity recovery, not imputation: values unavailable from the source remain NaN.
    """
    result = rook.copy()
    required = {"season", "norm_name"}
    missing_required = required.difference(result.columns)
    if missing_required:
        raise KeyError(f"rookie recovery requires columns: {sorted(missing_required)}")
    absent_features = set(profile_cols).difference(result.columns)
    if absent_features:
        raise KeyError(f"rookie recovery profile columns missing: {sorted(absent_features)}")

    needs_recovery = (result["season"].eq(deploy_season)
                      & result[profile_cols].isna().all(axis=1))
    if not needs_recovery.any():
        return result

    cfb_cols = [c for c in profile_cols if c.startswith("cfb_")]
    college = pd.read_csv(SEAS / "college_features.csv")
    college_cols = [c for c in cfb_cols if c in college.columns]
    college = college[["norm_name"] + college_cols].drop_duplicates("norm_name")
    pff = _final_pff_by_name(pff_kind, profile_cols)

    lookup = college.merge(pff, on="norm_name", how="outer", validate="one_to_one")
    fill = result.loc[needs_recovery, ["norm_name"]].merge(
        lookup, on="norm_name", how="left", validate="many_to_one"
    )
    fill.index = result.index[needs_recovery]
    for col in profile_cols:
        if col in fill.columns:
            result.loc[needs_recovery, col] = fill[col]
    return result


def assert_drafted_deploy_profiles(
    rook: pd.DataFrame,
    profile_cols: list[str],
    *,
    deploy_season: int = 2026,
    drafted_names: set[str] | None = None,
) -> None:
    """Prevent a deployed drafted rookie from silently being scored on draft capital alone."""
    required = {"season", "norm_name", "player"}
    missing_required = required.difference(rook.columns)
    if missing_required:
        raise KeyError(f"coverage guard requires columns: {sorted(missing_required)}")
    if drafted_names is None:
        import nflreadpy as nfl

        draft = nfl.load_draft_picks()
        if hasattr(draft, "to_pandas"):
            draft = draft.to_pandas()
        drafted_names = set(
            draft.loc[draft["season"].eq(deploy_season), "pfr_player_name"].dropna().map(_norm_name)
        )
    draftees = rook[rook["season"].eq(deploy_season) & rook["norm_name"].isin(drafted_names)]
    empty = draftees[draftees[profile_cols].isna().all(axis=1)]
    if not empty.empty:
        names = ", ".join(empty["player"].astype(str).sort_values())
        raise AssertionError(
            "drafted deploy rookies have no college/combine/PFF profile after identity recovery: " + names
        )
