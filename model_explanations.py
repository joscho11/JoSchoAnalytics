"""Production-model importance data for the Help & Guide page.

The displayed summaries are stored in a small, artifact-pinned JSON snapshot.
CI verifies every source hash. Production therefore never imports the training
stack or unpickles models just to render a collapsed Help-page expander.
"""
from __future__ import annotations

import copy
import hashlib
import html
import json
from functools import lru_cache
from pathlib import Path


HERE = Path(__file__).resolve().parent
SNAPSHOT_PATH = HERE / "model_explanations_snapshot.json"


def _feature(name: str) -> str:
    aliases = {
        "prior_half_ppr": "Prior half-PPR",
        "ppg_2yr": "2-year PPG",
        "ppg_3yr": "3-year PPG",
        "ppg_trend": "PPG trend",
        "career_high_ppg": "Career-high PPG",
        "prior_snap_share_pg": "Prior snap share",
        "prior_ppg": "Prior PPG",
        "prior_team_pass_rate": "Team pass rate",
        "draft_pick": "Draft pick",
        "draft_round": "Draft round",
        "cfb_career_scrim_yds": "College career yards",
        "cfb_rec_ypg": "College receiving YPG",
        "cfb_best_dom": "College best dominance",
        "cfb_final_recshare": "College final rec. share",
        "pff_rushing_touchdowns": "PFF rush touchdowns",
        "pff_receiving_grades_offense": "PFF offense grade",
        "pff_receiving_yprr": "PFF YPRR",
        "pff_receiving_avg_depth_of_target": "PFF average depth",
        "pff_receiving_contested_catch_rate": "PFF contested-catch rate",
        "pff_receiving_yards": "PFF receiving yards",
        "pff_receiving_routes": "PFF routes",
        "vacated_target_share": "Vacated target share",
        "prior_air_yards_share": "Prior air-yards share",
        "prior_rec_epa": "Prior receiving EPA",
        "prior_games": "Prior games",
        "prior_td_rate": "Prior TD rate",
        "spread_line": "Vegas spread",
        "sack_diff": "Sack-rate matchup",
        "scoring_diff": "Scoring differential",
        "sack_diff_reverse": "Reverse sack matchup",
        "home_coach_win_pct_roll3": "Home coach recent win rate",
    }
    if name in aliases:
        return aliases[name]
    label = name.replace("_", " ")
    label = label.replace("roll3", "(last 3)").replace("roll5", "(last 5)")
    label = label.replace("ffo ", "expected ").replace("pct", "%")
    return label[:1].upper() + label[1:]


def _md5(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


# Mean absolute Tree SHAP over the exact 2026 deploy population for seasonal
# models, and over 2014-2024 production-training games for the spread XGBoost
# component. Shares are percentages of total mean absolute SHAP.
SHAP_SNAPSHOTS = [
    ("season_qb_vet", "QB", "Season projections · Non-rookie models", "fantasy/projections/models/qb_veteran_model.pkl",
     "7632549f95995b9702baefdf016d7271", 87,
     [("prior_half_ppr", 53.0), ("ppg_2yr", 6.2), ("draft_pick", 4.4),
      ("prior_snap_share_pg", 4.3), ("ppg_trend", 3.0)]),
    ("season_rb_vet", "RB", "Season projections · Non-rookie models", "fantasy/projections/models/rb_veteran_model.pkl",
     "167aca71a8511afcced37c0abc846004", 144,
     [("prior_half_ppr", 33.2), ("ppg_3yr", 9.4), ("prior_snap_share_pg", 7.1),
      ("age", 5.5), ("career_high_ppg", 4.1)]),
    ("season_rb_rook", "RB", "Season projections · Rookie models", "fantasy/projections/models/rb_rookie_model.pkl",
     "da230ee66575ca574f02cbc2139e1a80", 71,
     [("draft_pick", 26.4), ("age", 13.3), ("draft_round", 7.3),
      ("cfb_career_scrim_yds", 5.7), ("cfb_rec_ypg", 3.7)]),
    ("season_wr_vet", "WR", "Season projections · Non-rookie models", "fantasy/projections/models/wr_veteran_model.pkl",
     "17dfbcf01054bdd5ce032f2b55df9ad2", 240,
     [("prior_half_ppr", 34.8), ("ppg_3yr", 9.3), ("age", 8.4),
      ("ppg_2yr", 7.8), ("prior_ppg", 7.2)]),
    ("season_wr_rook", "WR", "Season projections · Rookie models", "fantasy/projections/models/wr_rookie_model.pkl",
     "6c9a3f3ed02ce32c53594f383aade882", 154,
     [("draft_pick", 29.8), ("age", 18.3), ("vacated_target_share", 5.8),
      ("cfb_career_scrim_yds", 3.8), ("pff_receiving_contested_catch_rate", 3.0)]),
    ("season_te_vet", "TE", "Season projections · Non-rookie models", "fantasy/projections/models/te_veteran_model.pkl",
     "5a2f0b504d4cc6fc9a2e04453fd76a44", 129,
     [("prior_half_ppr", 28.9), ("ppg_3yr", 17.3), ("ppg_2yr", 7.0),
      ("draft_pick", 4.6), ("prior_air_yards_share", 3.3)]),
    ("season_te_rook", "TE", "Season projections · Rookie models", "fantasy/projections/models/te_rookie_model.pkl",
     "f79dad0ab26af5cb4e06a9f1723328cd", 66,
     [("draft_pick", 18.2), ("pff_receiving_grades_offense", 8.7), ("age", 7.3),
      ("pff_receiving_yprr", 4.7), ("pff_receiving_avg_depth_of_target", 4.5)]),
    # RECOMPUTED 2026-08-03 after the dense-sack + All-Pro identity retrain. Note the
    # shape change: `sack_diff` (was #2 at 11.783) and `sack_diff_reverse` (was #4 at
    # 5.009) LEFT the top five entirely. Those were PROD_FEATURES_35 #2/#3 and carried the
    # contemporaneous-outcome leak; with it removed the model leans on spread_line and
    # coaching/rolling-form instead. Tree SHAP over the same n=3295 matrix.
    ("spread_xgb", "Spread · XGBoost component", "Betting",
     "betting/models/ensemble_prod_model.pkl", "58d1391be3bf68d17f74c36cb3ed77b7", 3295,
     [("spread_line", 39.167), ("scoring_diff", 7.175),
      ("away_coach_win_pct_prior", 4.225), ("home_coach_win_pct_prior", 3.906),
      ("away_rolling_avg_yards", 3.862)]),
]

# Read-only walk-forward audit of non-rookie season-total projections. Bias is
# prediction minus actual half-PPR points; negative values are underprojections.
# Top tier is the highest predicted quintile within each position-season.
VETERAN_CALIBRATION_AUDIT = [
    {"position": "QB", "n": 380, "overall_bias": -9.90, "top_n": 77, "top_bias": 16.29},
    {"position": "RB", "n": 645, "overall_bias": -7.70, "top_n": 130, "top_bias": -21.33},
    {"position": "WR", "n": 1006, "overall_bias": 0.53, "top_n": 203, "top_bias": 4.15},
    {"position": "TE", "n": 558, "overall_bias": -2.57, "top_n": 112, "top_bias": -1.58},
]


@lru_cache(maxsize=1)
def _snapshot() -> dict:
    try:
        data = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if (
        data.get("schema_version") != 1
        or not isinstance(data.get("shap_models"), list)
        or not isinstance(data.get("native_models"), list)
        or not isinstance(data.get("sources"), dict)
    ):
        return {}
    return data


def shap_models():
    models = _snapshot().get("shap_models")
    if models is None:
        return [], ["Model explanation snapshot"]
    return copy.deepcopy(models), []


def native_models():
    return copy.deepcopy(_snapshot().get("native_models", []))


def snapshot_sources() -> dict[str, str]:
    """Artifact fingerprints recorded when the checked snapshot was generated."""
    return dict(_snapshot().get("sources", {}))


def calibration_audit_html() -> str:
    def bias_cell(value: float) -> str:
        state = "under" if value < -3 else "over" if value > 3 else "neutral"
        sign = "+" if value > 0 else ""
        return f"<td class='ca-bias ca-{state}'>{sign}{value:.1f}</td>"

    rows = []
    for row in VETERAN_CALIBRATION_AUDIT:
        rows.append(
            "<tr>"
            f"<th scope='row'>{html.escape(row['position'])}</th>"
            f"<td>{row['n']:,}</td>"
            f"{bias_cell(row['overall_bias'])}"
            f"<td>{row['top_n']:,}</td>"
            f"{bias_cell(row['top_bias'])}"
            "</tr>"
        )
    return (
        "<div class='ca-wrap'><table class='ca-table'>"
        "<thead><tr><th>Position</th><th>All vets (n)</th><th>All-player bias</th>"
        "<th>Top 20% (n)</th><th>Top-20% bias</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table></div>"
    )


def chart_html(model: dict) -> str:
    features = model["features"]
    scale = max(value for _, value in features) or 1
    rows = []
    for name, value in features:
        rows.append(
            "<div class='mi-row'>"
            f"<div class='mi-name'>{html.escape(name)}</div>"
            "<div class='mi-track'>"
            f"<div class='mi-fill' style='width:{100 * value / scale:.1f}%'></div></div>"
            f"<div class='mi-value'>{value:.1f}%</div></div>"
        )
    sample = f"<span>n={model['n']}</span>" if model.get("n") else ""
    return (
        "<div class='mi-card'><div class='mi-head'>"
        f"<strong>{html.escape(model['label'])}</strong>{sample}</div>"
        + "".join(rows)
        + f"<div class='mi-method'>{html.escape(model['method'])}</div></div>"
    )


CHART_CSS = """
<style>
.mi-card{padding:16px 16px 12px;border:1px solid rgba(255,255,255,.08);border-radius:12px;
background:rgba(255,255,255,.025);margin:0 0 12px}
.mi-head{display:flex;justify-content:space-between;gap:12px;margin-bottom:11px;font-size:15px}
.mi-head span,.mi-method{color:#8c96a8;font-size:11px}
.mi-row{display:grid;grid-template-columns:minmax(120px,1.45fr) minmax(80px,1fr) 44px;
gap:9px;align-items:center;margin:7px 0;font-size:12px}
.mi-name{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.mi-track{height:9px;background:rgba(255,255,255,.08);border-radius:2px;overflow:hidden}
.mi-fill{height:100%;background:#8abcf5}
.mi-value{text-align:right;color:#aab2c0;font-variant-numeric:tabular-nums}
.mi-method{margin-top:10px}
@media(max-width:520px){.mi-row{grid-template-columns:minmax(105px,1.3fr) minmax(60px,1fr) 40px}}
.ca-wrap{overflow-x:auto;margin:8px 0 14px}
.ca-table{width:100%;border-collapse:collapse;font-size:13px;font-variant-numeric:tabular-nums}
.ca-table th,.ca-table td{padding:10px 12px;border-bottom:1px solid rgba(255,255,255,.08);
text-align:right;white-space:nowrap}
.ca-table thead th{color:#aab2c0;font-size:11px;font-weight:600}
.ca-table th:first-child,.ca-table td:first-child{text-align:left}
.ca-table tbody th{font-weight:700}
.ca-bias{font-weight:700}
.ca-under{color:#ff8f87}.ca-over{color:#76d39b}.ca-neutral{color:#d3ad63}
</style>
"""
