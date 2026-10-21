"""Frozen, versioned First TD strategy ledgers and published-board rankings.

The public page reads these artifacts; the private release notebook is the
only intended writer. Outcome/settlement columns are deliberately excluded
from the source-input digest so grading cannot invalidate a frozen decision.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Mapping

import pandas as pd

from publishing.contract import PublicationError
from publishing.td_releases import read_td_release, release_for_path
from site_pages.attd_tracker import american_to_decimal, qualifies_first_td_actual_ev


STRATEGY_ID = "first_td_actual_ev_v2"
_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LEDGER_ROOT = _ROOT / "betting" / "anytime_td" / "strategies" / STRATEGY_ID
_RANK_REQUIRED = {"game_id", "player_id", "player_display_name", "p_first"}
_LEDGER_SOURCE_COLS = (
    "game_id", "player_id", "player_display_name", "team", "opponent_team",
    "p_first", "first_amer", "snapped_at_et", "bet_eligible", "model_version",
)


def _digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _json_bytes(payload: dict) -> bytes:
    return (json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")


def _timestamp(value, *, label: str) -> pd.Timestamp:
    try:
        stamp = pd.Timestamp(value)
    except (TypeError, ValueError) as exc:
        raise PublicationError(f"Invalid First TD v2 {label} timestamp: {value}") from exc
    if pd.isna(stamp):
        raise PublicationError(f"First TD v2 requires a valid {label} timestamp")
    if stamp.tzinfo is None:
        try:
            stamp = stamp.tz_localize("America/New_York", ambiguous="raise", nonexistent="raise")
        except (TypeError, ValueError) as exc:
            raise PublicationError(f"Invalid First TD v2 {label} timestamp: {value}") from exc
    return stamp.tz_convert("America/New_York")


def _truthy(value) -> bool:
    if isinstance(value, bool):
        return value
    if pd.isna(value):
        return False
    return str(value).strip().lower() in {"true", "1", "yes", "y", "on"}


def _safe_decimal(value) -> float | None:
    try:
        price = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(price) or abs(price) < 100 or not price.is_integer():
        return None
    return float(american_to_decimal(price))


def _canonical_rows(frame: pd.DataFrame, columns: tuple[str, ...]) -> bytes:
    present = [column for column in columns if column in frame]
    rows = frame[present].copy()
    if "player_id" in rows:
        rows["player_id"] = rows.player_id.astype("string")
        rows = rows.sort_values([column for column in ("game_id", "player_id") if column in rows], kind="stable")
    return rows.to_csv(index=False, lineterminator="\n", na_rep="").encode("utf-8")


def _read_strategy_file(path: Path, *, season: int, week: int) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise PublicationError(f"Invalid First TD v2 ledger: {path}") from exc
    supplied_hash = payload.pop("ledger_sha256", None)
    if payload.get("schema_version") != 1 or payload.get("strategy_id") != STRATEGY_ID:
        raise PublicationError(f"Unsupported First TD strategy ledger: {path}")
    if int(payload.get("season", -1)) != int(season) or int(payload.get("week", -1)) != int(week):
        raise PublicationError(f"First TD v2 ledger key disagrees with its path: {path}")
    if supplied_hash != _digest(_json_bytes(payload)):
        raise PublicationError(f"First TD v2 ledger checksum mismatch: {path}")
    payload["ledger_sha256"] = supplied_hash
    return payload


def freeze_first_td_actual_ev_v2(
    release_path: str | Path,
    *,
    frozen_at_et: str,
    kickoff_by_game: Mapping[str, str],
    ledger_root: str | Path | None = None,
) -> dict:
    """Freeze all positive-EV, eligible player quotes in this live release.

    A game with published First TD prices is locked even when it has zero
    selections. An existing game decision is immutable. Games without prices
    remain available for a later pregame release. The function is idempotent.
    """
    source = Path(release_path).resolve()
    entry = release_for_path(source)
    if not entry or "metadata_path" not in entry:
        raise PublicationError("First TD v2 can freeze only a manifest-validated release")
    if entry.get("prediction_mode") != "live":
        raise PublicationError("First TD v2 accepts live releases only")
    frame = read_td_release(source)
    required = set(_LEDGER_SOURCE_COLS) | {"season", "week"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise PublicationError(f"First TD v2 release is missing columns: {', '.join(missing)}")
    metadata = json.loads(Path(entry["metadata_path"]).read_text(encoding="utf-8"))
    if metadata.get("release_mode") != "live":
        raise PublicationError("First TD v2 accepts live releases only")
    if metadata.get("season") != entry["season"] or metadata.get("week") != entry["week"]:
        raise PublicationError("First TD v2 release metadata disagrees with its manifest")

    season, week = int(entry["season"]), int(entry["week"])
    metadata_sha = str(entry.get("metadata_sha256", ""))
    if not re_full_hash(metadata_sha):
        raise PublicationError("First TD v2 requires a manifest-verified metadata hash")
    published_at = _timestamp(metadata.get("publish_now_et"), label="release")
    frozen_at = _timestamp(frozen_at_et, label="freeze")
    if frozen_at < published_at:
        raise PublicationError("First TD v2 freeze time precedes the published release")
    ledger_dir = Path(ledger_root) if ledger_root is not None else DEFAULT_LEDGER_ROOT
    ledger_dir.mkdir(parents=True, exist_ok=True)
    ledger_path = ledger_dir / f"{season}_week{week:02d}.json"
    if ledger_path.is_file():
        payload = _read_strategy_file(ledger_path, season=season, week=week)
    else:
        payload = {
            "schema_version": 1,
            "strategy_id": STRATEGY_ID,
            "season": season,
            "week": week,
            "rule": "every eligible quoted player with model_probability * decimal_odds - 1 > 0; 1 unit each",
            "games": [],
        }
    locked = {str(item["game_id"]): item for item in payload["games"]}
    added = []
    skipped = 0
    all_selected = 0
    all_zero = 0
    csv_rel = str(entry.get("csv", source.name))

    for game_id, rows in frame.groupby(frame.game_id.astype(str), sort=True):
        american = pd.to_numeric(rows.first_amer, errors="coerce")
        priced = rows[american.notna()].copy()
        if priced.empty:
            continue
        game_id = str(game_id)
        kickoff_value = kickoff_by_game.get(game_id)
        if kickoff_value is None:
            raise PublicationError(f"First TD v2 is missing kickoff time for {game_id}")
        kickoff = _timestamp(kickoff_value, label=f"kickoff for {game_id}")
        if not published_at < kickoff or not frozen_at < kickoff:
            raise PublicationError(f"First TD v2 prices must be frozen before {game_id} kickoff")
        if "snapped_at_et" not in priced or priced.snapped_at_et.isna().any():
            raise PublicationError(f"First TD v2 is missing quote capture time for {game_id}")
        captures = priced.snapped_at_et.map(lambda value: _timestamp(value, label=f"quote for {game_id}"))
        if captures.ge(kickoff).any():
            raise PublicationError(f"First TD v2 contains a post-kickoff quote for {game_id}")
        if captures.gt(frozen_at).any():
            raise PublicationError(f"First TD v2 contains a post-freeze quote for {game_id}")
        if captures.gt(published_at).any():
            raise PublicationError(f"First TD v2 contains a quote captured after release publication for {game_id}")
        if captures.nunique() != 1:
            raise PublicationError(f"First TD v2 prices were captured at multiple times for {game_id}")

        mass = metadata.get("first_td_candidate_mass", {}).get(game_id)
        if (
            not isinstance(mass, dict)
            or mass.get("complete") is not True
            or mass.get("status") != "frozen_complete"
            or not isinstance(mass.get("candidate_lambdas"), dict)
            or not mass.get("candidate_lambdas")
        ):
            raise PublicationError(f"First TD v2 has no complete frozen model mass for {game_id}")
        if not re_full_hash(mass.get("record_sha256")):
            raise PublicationError(f"First TD v2 frozen model mass hash is invalid for {game_id}")

        valid_price_mask = american.map(lambda value: _safe_decimal(value) is not None)
        if not valid_price_mask.any():
            continue
        csv_input_sha = _digest(_canonical_rows(rows, _LEDGER_SOURCE_COLS))
        source_hash = _digest(_json_bytes({
            "csv_inputs_sha256": csv_input_sha,
            "metadata_sha256": metadata_sha,
            "model_mass_sha256": str(mass["record_sha256"]),
        }))
        existing = locked.get(game_id)
        if existing:
            if existing.get("source_release") == csv_rel:
                if existing.get("frozen_inputs_sha256") != source_hash:
                    raise PublicationError(f"Frozen First TD v2 inputs changed for {game_id}")
            elif published_at < _timestamp(existing.get("release_published_at_et"), label="prior release"):
                raise PublicationError(f"First TD v2 snapshot arrived out of order for {game_id}")
            skipped += 1
            continue

        model_players = set(map(str, mass["candidate_lambdas"]))
        bets = []
        exclusions: dict[str, int] = {}
        for row_index, row in priced.iterrows():
            player_id = str(row.player_id).strip()
            p_first = pd.to_numeric(pd.Series([row.p_first]), errors="coerce").iloc[0]
            decimal = _safe_decimal(row.first_amer)
            reason = None
            if player_id not in model_players:
                reason = "player_missing_from_frozen_model_mass"
            elif pd.isna(p_first) or not math.isfinite(float(p_first)) or not 0 <= float(p_first) <= 1:
                reason = "invalid_model_probability"
            elif not _truthy(row.bet_eligible):
                reason = "identity_history_or_availability_exclusion"
            elif decimal is None:
                reason = "invalid_american_price"
            if reason:
                exclusions[reason] = exclusions.get(reason, 0) + 1
                continue
            expected_return = float(p_first) * decimal - 1.0
            if expected_return <= 0.0:
                continue
            bets.append({
                "player_id": player_id,
                "player_display_name": str(row.player_display_name),
                "team": str(row.team),
                "opponent_team": str(row.opponent_team),
                "p_first": float(p_first),
                "first_amer": int(float(row.first_amer)),
                "decimal_odds": decimal,
                "expected_return": expected_return,
                "stake_units": 1.0,
            })
        decision = {
            "game_id": game_id,
            "source_release": csv_rel,
            "source_metadata_sha256": metadata_sha,
            "source_model_version": str(entry.get("model_version", metadata.get("model_version", ""))),
            "source_model_bundle_sha256": str(metadata.get("model_bundle_sha256", "")),
            "release_published_at_et": published_at.isoformat(),
            "quotes_captured_at_et": captures.iloc[0].isoformat(),
            "kickoff_et": kickoff.isoformat(),
            "frozen_at_et": frozen_at.isoformat(),
            "frozen_inputs_sha256": source_hash,
            "decision_sha256": _digest(_json_bytes({"bets": bets, "frozen_inputs_sha256": source_hash})),
            "decision_status": "frozen",
            "selected_bet_count": len(bets),
            "bets": bets,
            "exclusion_counts": exclusions,
        }
        locked[game_id] = decision
        added.append(decision)
        all_selected += len(bets)
        all_zero += int(not bets)

    if added:
        payload["games"] = [locked[key] for key in sorted(locked)]
        payload.pop("ledger_sha256", None)
        payload["ledger_sha256"] = _digest(_json_bytes(payload))
        temporary = ledger_path.with_name(ledger_path.name + ".tmp")
        temporary.write_bytes(_json_bytes(payload))
        temporary.replace(ledger_path)
    elif not ledger_path.exists():
        payload["ledger_sha256"] = _digest(_json_bytes(payload))
        ledger_path.write_bytes(_json_bytes(payload))

    return {
        "strategy_id": STRATEGY_ID,
        "season": season,
        "week": week,
        "ledger_path": str(ledger_path),
        "ledger_sha256": payload.get("ledger_sha256"),
        "added_games": len(added),
        "skipped_locked_games": skipped,
        "selected_bets": all_selected,
        "zero_pick_games": all_zero,
    }


def re_full_hash(value) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def load_first_td_actual_ev_v2(
    *,
    ledger_root: str | Path | None = None,
    releases: Mapping[tuple[int, int], str | Path] | None = None,
) -> tuple[pd.DataFrame, dict]:
    """Read frozen v2 selections and attach current, verified settlements."""
    ledger_dir = Path(ledger_root) if ledger_root is not None else DEFAULT_LEDGER_ROOT
    bets: list[dict] = []
    decisions: list[dict] = []
    if not ledger_dir.is_dir():
        return pd.DataFrame(), {"strategy_id": STRATEGY_ID, "games": [], "ledger_hashes": []}
    for ledger_path in sorted(ledger_dir.glob("*_week*.json")):
        try:
            season, week = map(int, ledger_path.stem.split("_week"))
        except ValueError as exc:
            raise PublicationError(f"Invalid First TD v2 ledger filename: {ledger_path.name}") from exc
        payload = _read_strategy_file(ledger_path, season=season, week=week)
        decisions.extend({**game, "season": season, "week": week} for game in payload["games"])
        for game in payload["games"]:
            for bet in game.get("bets", []):
                bets.append({
                    **bet,
                    "season": season,
                    "week": week,
                    "game_id": game["game_id"],
                    "model_version": game["source_model_version"],
                    "source_release": game["source_release"],
                    "frozen_at_et": game["frozen_at_et"],
                    "bet_eligible_first_actual_v2": True,
                    "scored_first": pd.NA,
                    "settlement_status_first": "awaiting_evidence",
                })
    bet_frame = pd.DataFrame(bets)
    if bet_frame.empty:
        return bet_frame, {"strategy_id": STRATEGY_ID, "games": decisions, "ledger_hashes": []}

    release_map = dict(releases or {})
    for (season, week), group in bet_frame.groupby(["season", "week"]):
        release = release_map.get((int(season), int(week)))
        if release is None:
            continue
        try:
            board = read_td_release(release)
        except (OSError, ValueError, PublicationError):
            continue
        settlements = {}
        if {"game_id", "player_id"} <= set(board.columns):
            for _, row in board.iterrows():
                settlements[(str(row.game_id), str(row.player_id))] = (
                    row.get("scored_first", pd.NA), row.get("settlement_status_first", "awaiting_evidence")
                )
        result_sidecar = Path(release).parent / f"first_td_results_{int(season)}_week{int(week):02d}.json"
        if result_sidecar.is_file():
            try:
                result_payload = json.loads(result_sidecar.read_text(encoding="utf-8"))
                if (
                    result_payload.get("schema_version") != 1
                    or int(result_payload.get("season", -1)) != int(season)
                    or int(result_payload.get("week", -1)) != int(week)
                    or result_payload.get("source_release") != Path(release).name
                ):
                    raise PublicationError(f"First TD result sidecar does not match its release: {result_sidecar}")
                for game in result_payload.get("games", []):
                    per_player = game.get("player_settlements", {})
                    if isinstance(per_player, list):
                        per_player = {str(item.get("player_id")): item for item in per_player}
                    for player_id, result in per_player.items():
                        if isinstance(result, dict):
                            settlements[(str(game.get("game_id")), str(player_id))] = (
                                result.get("scored_first", pd.NA), result.get("settlement_status_first", result.get("status", "awaiting_evidence"))
                            )
            except PublicationError:
                raise
            except (OSError, ValueError, TypeError, KeyError) as exc:
                raise PublicationError(f"Invalid First TD result sidecar: {result_sidecar}") from exc
        for idx in group.index:
            key = (str(bet_frame.at[idx, "game_id"]), str(bet_frame.at[idx, "player_id"]))
            if key in settlements:
                outcome, status = settlements[key]
                bet_frame.at[idx, "scored_first"] = outcome
                bet_frame.at[idx, "settlement_status_first"] = status
    hashes = sorted({str(decision.get("decision_sha256")) for decision in decisions})
    return bet_frame, {"strategy_id": STRATEGY_ID, "games": decisions, "decision_hashes": hashes}


def published_board_rankings(frame: pd.DataFrame, game_results: Mapping[str, dict] | None = None) -> tuple[pd.DataFrame, dict]:
    """Rank the published player board, independently of price eligibility."""
    missing = sorted(_RANK_REQUIRED - set(frame.columns))
    if missing:
        raise PublicationError(f"First TD ranking board is missing columns: {', '.join(missing)}")
    outcomes = {str(key): value for key, value in (game_results or {}).items()}
    summaries = []
    hits_one = hits_three = graded = pending = unavailable = 0
    for game_id, group in frame.groupby(frame.game_id.astype(str), sort=True):
        probabilities = pd.to_numeric(group.p_first, errors="coerce")
        valid = probabilities.notna() & probabilities.map(lambda value: math.isfinite(float(value)) and 0 <= float(value) <= 1)
        if not valid.all() or group.player_id.isna().any():
            unavailable += 1
            summaries.append({
                "Game": game_id, "Top 1": "Model probability unavailable", "Top 3": "—",
                "First TD result": "Model probability unavailable", "Top 1 result": "—", "Top 3 result": "—",
            })
            continue
        ranked = group.assign(
            _probability=probabilities,
            _player_sort_id=group.player_id.astype(str),
        ).sort_values(
            ["_probability", "_player_sort_id"], ascending=[False, True], kind="stable",
        )
        top1 = ranked.iloc[0]
        top3 = ranked.head(3)
        result = outcomes.get(str(game_id), {})
        status = str(result.get("status", "pending")).lower()
        kind = str(result.get("outcome_kind", "unresolved")).lower()
        scorer_id = str(result.get("scorer_player_id") or "").strip()
        if status != "resolved" or kind == "unresolved":
            pending += 1
            result_label = "Awaiting evidence"
            top1_result = top3_result = "Awaiting evidence"
        elif kind == "no_touchdown":
            graded += 1
            result_label = "No touchdown"
            top1_result = top3_result = "Miss"
        elif kind == "defense":
            graded += 1
            result_label = "Defense"
            top1_result = top3_result = "Miss"
        elif not scorer_id:
            pending += 1
            result_label = "Awaiting scorer identity"
            top1_result = top3_result = "Awaiting evidence"
        else:
            graded += 1
            scorer_rows = group[group.player_id.astype(str).eq(scorer_id)]
            scorer_on_board = result.get("scorer_on_board")
            if scorer_on_board is False:
                scorer_rows = group.iloc[0:0]
            elif scorer_rows.empty and scorer_on_board is True:
                scorer_name = str(result.get("scorer_name") or "").strip().casefold()
                scorer_team = str(result.get("scorer_team") or "").strip().upper()
                if scorer_name and scorer_team and {"team", "player_display_name"} <= set(group.columns):
                    scorer_rows = group[
                        group.player_display_name.astype(str).str.strip().str.casefold().eq(scorer_name)
                        & group.team.astype(str).str.strip().str.upper().eq(scorer_team)
                    ]
            if scorer_rows.empty:
                result_label = str(result.get("scorer_name") or "Outside published board")
                if result.get("scorer_on_board") is False and result_label != "Outside published board":
                    result_label += " · outside board"
                top1_hit = top3_hit = False
            else:
                result_label = str(result.get("scorer_name") or scorer_rows.iloc[0].player_display_name)
                winning_id = str(scorer_rows.iloc[0].player_id)
                top1_hit = str(top1.player_id) == winning_id
                top3_hit = bool(top3.player_id.astype(str).eq(winning_id).any())
            hits_one += int(top1_hit)
            hits_three += int(top3_hit)
            top1_result = "Hit" if top1_hit else "Miss"
            top3_result = "Hit" if top3_hit else "Miss"
        if status == "resolved" and kind in {"no_touchdown", "defense"}:
            pass
        summaries.append({
            "Game": game_id,
            "Top 1": f"{top1.player_display_name} · {top1.team}",
            "Top 3": ", ".join(f"{row.player_display_name} · {row.team}" for _, row in top3.iterrows()),
            "First TD result": result_label,
            "Top 1 result": top1_result,
            "Top 3 result": top3_result,
        })
    table = pd.DataFrame(summaries)
    return table, {
        "ranked_games": len(summaries) - unavailable,
        "graded_games": graded,
        "pending_games": pending,
        "unavailable_games": unavailable,
        "top1_hits": hits_one,
        "top3_hits": hits_three,
    }
