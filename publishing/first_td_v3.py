"""Frozen First TD v3 parameters and the sharpened-share formula.

The sharpening exponent ``k``, the 2026 offense-scores-first constant and the
long-shot price cap are fitted in the private model repository and copied into
this tree as ``params.json`` beside the v3 ledgers. This module only reads that
copy and applies one fixed formula to a game's frozen candidate lambdas; it fits
nothing and imports no site page code.

    q_i = lambda_i ** k / sum_j(lambda_j ** k) * p_offense

``j`` runs over every frozen candidate in the game, quoted or not, which is the
same denominator the flat First TD share (``p_first``) uses at ``k = 1``.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from publishing.contract import PublicationError

STRATEGY_ID_V3 = "first_td_best_value_v3"
_ROOT = Path(__file__).resolve().parents[1]
V3_DIR = _ROOT / "betting" / "anytime_td" / "strategies" / STRATEGY_ID_V3
PARAMS_FILENAME = "params.json"
PARAMS_PATH = V3_DIR / PARAMS_FILENAME
# v3 is tracked from the 2026 Week 7 board on; earlier boards keep the legacy rule.
FIRST_V3_SEASON = 2026
FIRST_V3_WEEK = 7
# A release-supplied p_first_v3 must match the lambda-derived value this closely.
MASS_MISMATCH_TOLERANCE = 1e-9
_MAX_K = 10.0
# The model repository's params file names the cap `cap_american` (null means no cap);
# the other spellings are accepted too.
_CAP_KEYS = ("cap_american", "price_cap_american", "price_cap", "cap")


@dataclass(frozen=True)
class FirstTdV3Params:
    k: float
    p_offense: float
    price_cap: int | None  # longest allowed American price; None means no cap
    sha256: str


def uses_first_td_v3(season, week) -> bool:
    """True for boards that carry v3 probabilities and picks (2026 Week 7 on)."""
    try:
        return (int(season), int(week)) >= (FIRST_V3_SEASON, FIRST_V3_WEEK)
    except (TypeError, ValueError):
        return False


def _finite(value, name: str) -> float:
    if isinstance(value, bool):
        raise PublicationError(f"First TD v3 params: {name} must be a number")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise PublicationError(f"First TD v3 params: {name} must be a number") from exc
    if not math.isfinite(number):
        raise PublicationError(f"First TD v3 params: {name} must be finite")
    return number


def _cap_value(raw) -> int:
    text = str(raw).strip().lstrip("+") if isinstance(raw, str) else raw
    number = _finite(text, "price cap")
    if not number.is_integer() or number < 100:
        raise PublicationError("First TD v3 params: the price cap must be a whole American price of +100 or longer")
    return int(number)


def params_sha256(payload: Mapping) -> str:
    """Digest of the canonical JSON (sorted keys, LF), so line endings never matter."""
    try:
        canonical = json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n"
    except (TypeError, ValueError) as exc:
        raise PublicationError("First TD v3 params are not valid JSON data") from exc
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def load_params(path: str | Path | None = None) -> FirstTdV3Params:
    """Read and validate the frozen v3 params copy; raise a clear error if absent."""
    target = Path(path) if path is not None else PARAMS_PATH
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PublicationError(
            f"First TD v3 params file not found: {target}. Copy "
            "td_count_model_beta/first_td/artifacts/first_td_v3_params.json there first."
        ) from exc
    except (OSError, ValueError) as exc:
        raise PublicationError(f"First TD v3 params file is unreadable: {target}") from exc
    if not isinstance(payload, dict):
        raise PublicationError("First TD v3 params must be a JSON object")
    k = _finite(payload.get("k"), "k")
    if not 0 < k <= _MAX_K:
        raise PublicationError(f"First TD v3 params: k must be in (0, {_MAX_K:g}]")
    p_offense = _finite(payload.get("p_offense_2026"), "p_offense_2026")
    if not 0 < p_offense <= 1:
        raise PublicationError("First TD v3 params: p_offense_2026 must be a probability in (0, 1]")
    caps = {
        None if payload[key] is None else _cap_value(payload[key])
        for key in _CAP_KEYS if key in payload
    }
    if not caps:
        raise PublicationError(
            "First TD v3 params have no price cap (expected one of: " + ", ".join(_CAP_KEYS) + ")"
        )
    if len(caps) != 1:
        raise PublicationError("First TD v3 params disagree on the price cap")
    return FirstTdV3Params(k=k, p_offense=p_offense, price_cap=caps.pop(), sha256=params_sha256(payload))


def sharpen_lambdas(lambdas: Mapping[str, float], p_offense: float, k: float) -> dict[str, float]:
    """Return q_i = lambda_i**k / sum_j(lambda_j**k) * p_offense for one game.

    ``k = 1`` is the flat lambda share, so the values sum to ``p_offense``.
    """
    if not lambdas:
        raise ValueError("a game needs at least one candidate lambda")
    powered: dict[str, float] = {}
    for key, value in lambdas.items():
        lam = float(value)
        if not math.isfinite(lam) or lam < 0:
            raise ValueError("candidate lambdas must be finite and non-negative")
        powered[str(key)] = lam ** k
    total = math.fsum(powered.values())
    if not total > 0:
        raise ValueError("candidate lambdas must have positive total mass")
    return {key: (value / total) * p_offense for key, value in powered.items()}


def _is_sha256(value) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def frozen_mass_is_intact(record) -> bool:
    """True when a release's frozen candidate-mass record is complete and untampered.

    Mirrors the model repository's own check: the record hash recomputes, the
    stored total equals the sum of the frozen lambdas, and every lambda is a
    finite non-negative number.
    """
    if not isinstance(record, Mapping):
        return False
    if record.get("complete") is not True or record.get("status") != "frozen_complete":
        return False
    lambdas = record.get("candidate_lambdas")
    expected = record.get("record_sha256")
    if not isinstance(lambdas, Mapping) or not lambdas or not _is_sha256(expected):
        return False
    try:
        payload = {key: value for key, value in record.items() if key != "record_sha256"}
        actual = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
        ).hexdigest()
        total = float(record["total_lambda"])
        values = [float(value) for value in lambdas.values()]
    except (KeyError, TypeError, ValueError):
        return False
    if actual != expected:
        return False
    if not math.isfinite(total) or total <= 0 or not all(math.isfinite(v) and v >= 0 for v in values):
        return False
    return math.isclose(total, math.fsum(values), rel_tol=1e-5, abs_tol=1e-8)


def derived_probabilities(record: Mapping, params: FirstTdV3Params) -> dict[str, float]:
    """v3 probability for every frozen candidate in one game's mass record."""
    return sharpen_lambdas(record["candidate_lambdas"], params.p_offense, params.k)
