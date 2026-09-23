"""Production-model importance data for the Help & Guide page.

The displayed summaries are stored in a small JSON snapshot.
Production never loads a serialized model to render Help.
"""
from __future__ import annotations

import copy
import html
import json
from functools import lru_cache
from pathlib import Path


HERE = Path(__file__).resolve().parent
SNAPSHOT_PATH = HERE / "model_explanations_snapshot.json"

# Read-only walk-forward audit of non-rookie season-total projections. Bias is
# prediction minus actual half-PPR points; negative values are underprojections.
# Top tier is the highest predicted quintile within each position-season.
VETERAN_CALIBRATION_AUDIT = [
    {"position": "QB", "n": 380, "overall_bias": -9.90, "top_n": 77, "top_bias": 16.29},
    {"position": "RB", "n": 645, "overall_bias": -7.70, "top_n": 130, "top_bias": -21.33},
    {"position": "WR", "n": 1006, "overall_bias": 0.53, "top_n": 203, "top_bias": 4.15},
    {"position": "TE", "n": 558, "overall_bias": -2.57, "top_n": 112, "top_bias": -1.58},
]

# The spread season chart reads the same versioned audit artifact as the live
# HIGH headline. Do not copy season splits into this module.
_HIGH_AUDIT_PATH = HERE / "betting" / "market_model_benchmark_v3.json"
_HIGH_AUDIT = json.loads(_HIGH_AUDIT_PATH.read_text(encoding="utf-8"))
SPREAD_HIGH_BY_SEASON = [
    {"season": int(row["season"]), "wins": int(row["wins"]), "n": int(row["graded_n"])}
    for row in _HIGH_AUDIT["historical"]["high_by_season"]
]

# Absolute ridge coefficients from season_totals_v2_prod artifacts/prod_card.json
# (fitter line_in). Signs kept for the Help caption; the bar uses |coef| share.
SEASON_TOTALS_COEF = {
    "Posted win total": 1.0292064770630556,
    "True home games": 0.3684852134281236,
    "QB unavailable": -0.3011450968877932,
    "Prior special-teams EPA": 0.1952411878103743,
    "Prior pass offense EPA": 0.1894523513088307,
    "Forward strength of schedule": -0.14151717343486517,
}

DRAFT_BOARD_EVAL = {
    "model_mae": 49.31,
    "adp_mae": 51.75,
    "model_pairwise": 0.7101,
    "adp_pairwise": 0.6965,
    "seasons_beat_adp": "5 of 6",
    "lost_season": 2020,
}

ROOKIE_HIT_AUC = {
    "draft_only": 0.838,
    "full": 0.843,
    "holdout": "2019-2023 classes",
}

# Cards Help actually draws. Frozen into model_explanations_snapshot.json.
DISPLAYED_HELP_IDS = (
    "spread_xgb",
    "season_rb_rook",
    "season_wr_rook",
    "season_te_rook",
    "weekly_qb",
    "weekly_rb",
    "weekly_wr",
    "weekly_te",
    "totals_xgboost",
    "totals_ridge",
)


def season_totals_importance(k: int = 6) -> list[tuple[str, float]]:
    items = [(name, abs(value)) for name, value in SEASON_TOTALS_COEF.items()]
    total = sum(value for _, value in items) or 1.0
    top = sorted(items, key=lambda row: -row[1])[:k]
    return [(name, round(100.0 * value / total, 1)) for name, value in top]


def spread_high_season_rows() -> list[dict]:
    rows = []
    for row in SPREAD_HIGH_BY_SEASON:
        pct = 100.0 * row["wins"] / row["n"]
        rows.append({
            "season": str(row["season"]),
            "wins": row["wins"],
            "n": row["n"],
            "pct": round(pct, 1),
            "record": f"{row['wins']}/{row['n']}",
        })
    return rows


def card_by_id(model_id: str) -> dict | None:
    for model in shap_models()[0] + native_models():
        if model.get("id") == model_id:
            return model
    return None


def weekly_point_cards() -> list[dict]:
    order = ("weekly_qb", "weekly_rb", "weekly_wr", "weekly_te")
    return [card for card_id in order if (card := card_by_id(card_id))]


def rookie_projection_cards() -> list[dict]:
    order = ("season_rb_rook", "season_wr_rook", "season_te_rook")
    return [card for card_id in order if (card := card_by_id(card_id))]


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
    """Static labels recorded with the Help snapshot. Not file hashes."""
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
