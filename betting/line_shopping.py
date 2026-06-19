"""Multi-book line shopping for NFL spreads & totals (The Odds API).

The validated edge is measured vs the CLOSING line, but you bet at the line you
can GET — so taking the best number across books is free CLV. One bulk call
returns every US book; this finds the most favorable spread/total per side and
quantifies how much shopping is worth (points gained vs the median book).

    python betting/line_shopping.py board                 # shopping value across the slate
    python betting/line_shopping.py board --min-gain 0.5  # only games where shopping gains >=0.5 pt

`best_for_pick(event, side)` is the reusable hook the weekly execution path uses
to route each model pick to the book offering the best number.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from statistics import median

import odds_client as oc


def american(dec: float) -> str:
    return f"+{round((dec - 1) * 100)}" if dec >= 2.0 else f"-{round(100 / (dec - 1))}"


def shop_event(event: dict) -> dict | None:
    """Collect every book's spread (per team) and total (over/under) for one game."""
    home = oc.NFL_TEAMS.get(event.get("home_team"))
    away = oc.NFL_TEAMS.get(event.get("away_team"))
    if not home or not away:
        return None
    spreads = {"home": [], "away": []}
    totals = {"Over": [], "Under": []}
    for bk in event.get("bookmakers", []):
        for mk in bk.get("markets", []):
            if mk["key"] == "spreads":
                for o in mk.get("outcomes", []):
                    if o.get("point") is None:
                        continue
                    side = oc.NFL_TEAMS.get(o["name"])
                    if side == home:
                        spreads["home"].append((o["point"], o["price"], bk["key"]))
                    elif side == away:
                        spreads["away"].append((o["point"], o["price"], bk["key"]))
            elif mk["key"] == "totals":
                for o in mk.get("outcomes", []):
                    if o.get("point") is not None and o["name"] in totals:
                        totals[o["name"]].append((o["point"], o["price"], bk["key"]))
    return {"home": home, "away": away, "date": str(event.get("commence_time", ""))[:10],
            "spreads": spreads, "totals": totals}


def best_quote(quotes: list[tuple]) -> dict | None:
    """Best (most favorable) quote: highest point, then best price. `shop_gain` =
    points gained vs the median book (the value of shopping)."""
    if not quotes:
        return None
    best = max(quotes, key=lambda t: (t[0], t[1]))
    pts = [q[0] for q in quotes]
    return {"point": best[0], "price": best[1], "book": best[2], "n_books": len(quotes),
            "worst_point": min(pts), "median_point": median(pts),
            "shop_gain": round(best[0] - median(pts), 2)}


def best_for_pick(event: dict, side: str, market: str = "spreads") -> dict | None:
    """Best book/number for a model pick. side: 'home'|'away' (spreads) or
    'Over'|'Under' (totals)."""
    shopped = shop_event(event)
    if not shopped:
        return None
    quotes = shopped["spreads"].get(side) if market == "spreads" else shopped["totals"].get(side)
    return best_quote(quotes or [])


def board_cmd(args) -> None:
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    events, hdr = oc.api_get(f"/sports/{oc.SPORT}/odds/", regions=args.regions,
                             markets="spreads,totals", oddsFormat="decimal",
                             commenceTimeFrom=now_iso)
    rows = []
    for ev in events:
        s = shop_event(ev)
        if not s:
            continue
        bh, ba = best_quote(s["spreads"]["home"]), best_quote(s["spreads"]["away"])
        if not bh or not ba:
            continue
        # spread shopping value = how many points separate best and worst book for a side
        gain = max(bh["shop_gain"], ba["shop_gain"])
        rows.append((s, bh, ba, gain))
    rows.sort(key=lambda r: -r[3])

    shown = [r for r in rows if r[3] >= args.min_gain]
    print(f"Line-shopping board ({len(rows)} games, {events and len(events)} fetched, "
          f"{rows and rows[0][1]['n_books']} books)\n")
    print(f"{'date':11s} {'matchup':14s} {'best home':>16} {'best away':>16} {'shop pts':>9}")
    print("-" * 72)
    for s, bh, ba, gain in shown:
        hh = f"{bh['point']:+g} {american(bh['price'])}({bh['book'][:4]})"
        aa = f"{ba['point']:+g} {american(ba['price'])}({ba['book'][:4]})"
        print(f"{s['date']:11s} {s['away']+' @ '+s['home']:14s} {hh:>16} {aa:>16} {gain:>9.1f}")
    avg_gain = sum(r[3] for r in rows) / len(rows) if rows else 0
    print(f"\n  avg best-vs-median shopping gain: {avg_gain:.2f} pts/side  "
          f"(free CLV from shopping {rows and rows[0][1]['n_books']} books)")
    print(f"  quota: {hdr['remaining']} remaining, {hdr['used']} used")


def main() -> None:
    p = argparse.ArgumentParser(description="NFL multi-book line shopping")
    sub = p.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("board", help="shopping value across the upcoming slate")
    b.add_argument("--regions", default="us")
    b.add_argument("--min-gain", type=float, default=0.0,
                   help="only show games where shopping gains >= this many points")
    b.set_defaults(func=board_cmd)
    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
