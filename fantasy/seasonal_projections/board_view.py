"""Display-rank helpers for the Draft Board dashboard tab (pure pandas, no heavy deps).

Why this exists: every rank shown side by side must be computed on the SAME population
(the drafted pool the board displays). The board CSV's `our_pos_rank` is computed over
the FULL player universe (~610 players, ~81 QBs incl. every backup), while the overall
rank shown on the board is computed over the drafted pool (~176 players, ~24 QBs). Mixing
them makes the table self-contradict — e.g. a player shown 170th overall but "28th at QB",
because the positional rank secretly counted 80+ backup QBs. This module recomputes every
display rank WITHIN the pool it's given, so overall and positional ranks are mutually
consistent.

Imported by app.py (Draft Board tab) and exercised by test_draft_board.py.
"""
import pandas as pd


def add_display_ranks(pool):
    """Return a copy of the drafted-pool frame with mutually-consistent display ranks,
    all computed WITHIN this frame:

      model_ovr / model_posrk   from `vor`               (higher vor = better; rank 1 = best)
      adp_posrk                 from `adp_overall_rank`   (lower ADP  = better; rank 1 = best)
      value_disp                adp_posrk - model_posrk   (+ = we rank higher than the market)
      actual_ovr / actual_posrk from `actual_total`       (added only if actuals are present)

    Overall ranks span all positions; positional ranks reset within each position. Because
    model_ovr and model_posrk both derive from `vor`, a player's positional rank always
    equals the rank of their overall position within their position group (no contradiction).
    """
    d = pool.copy()
    d["model_ovr"]   = d["vor"].rank(ascending=False, method="min")
    d["model_posrk"] = d.groupby("position")["vor"].rank(ascending=False, method="min")
    d["adp_ovr"]     = d["adp_overall_rank"].rank(ascending=True, method="min")    # ADP overall, within pool
    d["adp_posrk"]   = d.groupby("position")["adp_overall_rank"].rank(ascending=True, method="min")
    d["value_disp"]  = d["adp_posrk"] - d["model_posrk"]

    # "Blend projected points": the Pred rank is a RANK blend (our 0.2 / ADP 0.3 / Sleeper 0.5),
    # but ADP has no point value, so a literal blend-of-points doesn't exist. We combine the two
    # point-bearing inputs (our model + Sleeper) in the blend's proportions (0.2 : 0.5, renormalized),
    # falling back to our model where Sleeper's projection is missing. This is the projection shown
    # as "Proj Pts" so a higher projection tracks a better Pred rank. (Weights mirror BLEND_WEIGHTS.)
    if "sleeper_pts_half_ppr" in d.columns and "projected_total" in d.columns:
        w_our, w_slp = 0.20, 0.50
        has_slp = d["sleeper_pts_half_ppr"].notna()
        num = w_our * d["projected_total"] + w_slp * d["sleeper_pts_half_ppr"].fillna(0)
        den = w_our + w_slp * has_slp.astype(float)
        d["blend_proj"] = num / den
    elif "projected_total" in d.columns:
        d["blend_proj"] = d["projected_total"]

    # Pred = the RANK of the blended projection, so Proj Pts and Pred are ALWAYS in the same order
    # (higher projection => better Pred rank). ADP is kept only as a comparison column, not in Pred.
    if "blend_proj" in d.columns:
        d["pred_ovr"]   = d["blend_proj"].rank(ascending=False, method="min")
        d["pred_posrk"] = d.groupby("position")["blend_proj"].rank(ascending=False, method="min")

    if "actual_total" in d.columns and d["actual_total"].notna().any():
        d["actual_ovr"]   = d["actual_total"].rank(ascending=False, method="min")
        d["actual_posrk"] = d.groupby("position")["actual_total"].rank(ascending=False, method="min")
    return d
