"""NFL player-prop value scanner: weekly fantasy projections vs book prop lines.

Reuses the existing per-stat fantasy projections (`fantasy/fantasy_projections/
projections_<season>_week<W>.csv`) as the model, fetches player-prop lines from
The Odds API (per-event endpoint), and flags over/under value where the model's
per-game projection diverges from the posted line.

Markets handled (mapped to projection columns):
    player_pass_yds      -> pred_qb_pass_yards
    player_rush_yds      -> pred_qb_rush_yards (QB) / pred_rush_yards (RB)
    player_reception_yds -> pred_rec_yards / pred_wr_rec_yards / pred_te_rec_yards
    player_receptions    -> pred_wr_receptions / pred_te_receptions

Not handled: anytime-TD (the only market posted far out) — the fantasy model has
no TD projection, so we can't honestly price it. That needs a TD-rate model
(future work); pricing it off nothing would be worse than skipping it.

Value uses a rough normal approximation per stat (SDs below are documented
estimates, not fitted) to turn the projection-vs-line gap into a hit probability
and EV against the posted price.

    python betting/props_scanner.py available --date 2026-09-13
    python betting/props_scanner.py scan --proj fantasy/fantasy_projections/projections_2025_week17.csv --date 2025-12-28
"""
from __future__ import annotations

import argparse
import math
import re
from statistics import median

import pandas as pd

import odds_client as oc

YARDAGE_MARKETS = ["player_pass_yds", "player_rush_yds",
                   "player_reception_yds", "player_receptions"]

# rough per-game SDs (documented estimates, not fitted) for the normal model
DEFAULT_SD = {"player_pass_yds": 66.0, "player_rush_yds": 28.0,
              "player_reception_yds": 26.0, "player_receptions": 1.8}


def normalize_name(name: str) -> str:
    n = str(name).lower()
    n = re.sub(r"\b(jr|sr|ii|iii|iv|v)\b\.?", "", n)
    n = re.sub(r"[^a-z ]", "", n)
    return " ".join(n.split())


def projected_stat(row: dict, market: str):
    """Model per-game projection for a market given the player's projection row."""
    pos = row.get("position")
    if market == "player_pass_yds":
        return row.get("pred_qb_pass_yards")
    if market == "player_rush_yds":
        return row.get("pred_qb_rush_yards") if pos == "QB" else row.get("pred_rush_yards")
    if market == "player_reception_yds":
        for c in ("pred_rec_yards", "pred_wr_rec_yards", "pred_te_rec_yards"):
            v = row.get(c)
            if pd.notna(v):
                return v
        return None
    if market == "player_receptions":
        for c in ("pred_wr_receptions", "pred_te_receptions"):
            v = row.get(c)
            if pd.notna(v):
                return v
        return None
    return None


def normal_cdf(z: float) -> float:
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def american(dec: float) -> str:
    return f"+{round((dec - 1) * 100)}" if dec >= 2.0 else f"-{round(100 / (dec - 1))}"


def load_projections(path: str) -> dict:
    df = pd.read_csv(path)
    return {normalize_name(r["player_display_name"]): r.to_dict()
            for _, r in df.iterrows()}


def consensus_props(event: dict, market: str) -> dict:
    """player(normalized) -> {line, over, under, n} consensus across books.
    Prop outcomes carry the player in `description`, the line in `point`."""
    by_player: dict = {}
    for bk in event.get("bookmakers", []):
        for mk in bk.get("markets", []):
            if mk["key"] != market:
                continue
            for oc_ in mk.get("outcomes", []):
                player = normalize_name(oc_.get("description", ""))
                pt, side, price = oc_.get("point"), oc_.get("name"), oc_.get("price")
                if not player or pt is None:
                    continue
                d = by_player.setdefault(player, {"points": [], "over": [], "under": []})
                d["points"].append(pt)
                if side == "Over":
                    d["over"].append(price)
                elif side == "Under":
                    d["under"].append(price)
    out = {}
    for player, d in by_player.items():
        out[player] = {"line": median(d["points"]),
                       "over": max(d["over"]) if d["over"] else None,
                       "under": max(d["under"]) if d["under"] else None,
                       "n": len(d["points"])}
    return out


def scan_event(event: dict, projections: dict, markets: list[str],
               min_edge: float) -> list[dict]:
    rows = []
    for market in markets:
        cons = consensus_props(event, market)
        sd = DEFAULT_SD[market]
        for player, info in cons.items():
            if player not in projections:
                continue
            proj = projected_stat(projections[player], market)
            if proj is None or pd.isna(proj):
                continue
            proj, line = float(proj), float(info["line"])
            p_over = normal_cdf((proj - line) / sd)
            side = "Over" if proj > line else "Under"
            p_side = p_over if side == "Over" else 1 - p_over
            price = info["over"] if side == "Over" else info["under"]
            if price is None:
                continue
            ev = p_side * (price - 1) - (1 - p_side)
            edge_units = proj - line  # signed model-vs-line gap, in stat units
            if abs(edge_units) >= min_edge and ev > 0:
                rows.append({"player": projections[player]["player_display_name"],
                             "market": market, "side": side, "line": line,
                             "proj": round(proj, 1), "p": round(p_side, 3),
                             "price": price, "ev": round(ev, 3),
                             "edge_units": round(edge_units, 1)})
    rows.sort(key=lambda r: -r["ev"])
    return rows


# ---- commands ------------------------------------------------------------
def _events_on(date_str: str):
    # floor the API window at the requested date (was hardcoded 2026 -> 2025 scans
    # returned nothing); then filter to the exact date client-side.
    ev_list, hdr = oc.api_get(f"/sports/{oc.SPORT}/events/",
                              commenceTimeFrom=f"{date_str}T00:00:00Z")
    return [e for e in ev_list if str(e.get("commence_time", ""))[:10] == date_str], hdr


def available_cmd(args):
    evs, hdr = _events_on(args.date)
    if not evs:
        print(f"No events on {args.date}.")
        return
    e = evs[0]
    data, hdr = oc.api_get(f"/sports/{oc.SPORT}/events/{e['id']}/odds/",
                           regions="us", markets=",".join(YARDAGE_MARKETS + ["player_anytime_td"]),
                           oddsFormat="decimal")
    found = sorted({mk["key"] for bk in data.get("bookmakers", []) for mk in bk.get("markets", [])})
    print(f"Prop markets posted for {e['away_team']} @ {e['home_team']} ({args.date}):")
    print(" ", found or "NONE yet (yardage props post within a few days of kickoff)")
    print(f"quota: {hdr['remaining']} remaining, {hdr['used']} used")


def scan_cmd(args):
    projections = load_projections(args.proj)
    evs, hdr = _events_on(args.date)
    if not evs:
        print(f"No events on {args.date}.")
        return
    markets = args.markets.split(",") if args.markets else YARDAGE_MARKETS
    print(f"Player-prop value, {args.date}, min edge {args.min_edge} units, "
          f"projections={args.proj.split('/')[-1]}\n")
    any_found = False
    for e in evs:
        data, hdr = oc.api_get(f"/sports/{oc.SPORT}/events/{e['id']}/odds/",
                               regions="us", markets=",".join(markets), oddsFormat="decimal")
        for r in scan_event(data, projections, markets, args.min_edge):
            any_found = True
            print(f"{american(r['price']):>5} ({r['price']:>5})  {r['player']:22s} "
                  f"{r['market'].replace('player_',''):16s} {r['side']:5s} {r['line']:>6} "
                  f"(proj {r['proj']}, edge {r['edge_units']:+}) p={r['p']:.0%} ev {r['ev']:+.2f}")
    if not any_found:
        print("No prop value found (or yardage props not posted yet this far out).")
    print(f"\nquota: {hdr['remaining']} remaining, {hdr['used']} used")


def main():
    p = argparse.ArgumentParser(description="NFL player-prop value scanner")
    sub = p.add_subparsers(dest="cmd", required=True)

    av = sub.add_parser("available", help="which prop markets are posted for a date")
    av.add_argument("--date", required=True)
    av.set_defaults(func=available_cmd)

    sc = sub.add_parser("scan", help="find prop value vs the fantasy projections")
    sc.add_argument("--proj", required=True, help="path to projections_<season>_week<W>.csv")
    sc.add_argument("--date", required=True, help="match date YYYY-MM-DD")
    sc.add_argument("--markets", help=f"comma-sep (default {','.join(YARDAGE_MARKETS)})")
    sc.add_argument("--min-edge", type=float, default=5.0,
                    help="min |projection - line| in stat units (default 5)")
    sc.set_defaults(func=scan_cmd)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
