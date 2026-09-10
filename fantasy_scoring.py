"""Shared fantasy scoring modes used by the live site."""
import pandas as pd

SCORING_MODES = ("Standard", "Half-PPR", "PPR")
DEFAULT_SCORING = "Half-PPR"

def points_from_half_ppr(points, receptions, mode: str):
    values = pd.to_numeric(points, errors="coerce")
    recs = pd.to_numeric(receptions, errors="coerce")
    if mode == "Standard":
        return values - 0.5 * recs
    if mode == "PPR":
        return values + 0.5 * recs
    return values
