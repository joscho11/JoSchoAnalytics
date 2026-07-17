"""Hermetic tests for line shopping — no network."""
import line_shopping as ls


def _event():
    def spread(book, hp, hpr, ap, apr):
        return {"key": book, "markets": [
            {"key": "spreads", "outcomes": [
                {"name": "Kansas City Chiefs", "point": hp, "price": hpr},
                {"name": "Buffalo Bills", "point": ap, "price": apr}]},
            {"key": "totals", "outcomes": [
                {"name": "Over", "point": 47.5, "price": 1.91},
                {"name": "Under", "point": 47.5, "price": 1.91}]}]}
    return {"home_team": "Kansas City Chiefs", "away_team": "Buffalo Bills",
            "commence_time": "2026-09-13T17:00:00Z",
            "bookmakers": [spread("fanduel", -3.0, 1.91, 3.0, 1.91),
                           spread("draftkings", -3.5, 1.95, 3.5, 1.87),
                           spread("betmgm", -2.5, 1.87, 2.5, 1.95)]}


def test_shop_event_collects_all_books():
    s = ls.shop_event(_event())
    assert s["home"] == "KC" and s["away"] == "BUF"
    assert len(s["spreads"]["home"]) == 3 and len(s["spreads"]["away"]) == 3


def test_best_quote_picks_highest_point_then_price():
    s = ls.shop_event(_event())
    # home points: -3.0, -3.5, -2.5  -> best (max) is -2.5 (betmgm)
    bh = ls.best_quote(s["spreads"]["home"])
    assert bh["point"] == -2.5 and bh["book"] == "betmgm"
    # away points: 3.0, 3.5, 2.5 -> best is 3.5 (draftkings)
    ba = ls.best_quote(s["spreads"]["away"])
    assert ba["point"] == 3.5 and ba["book"] == "draftkings"


def test_shop_gain_vs_median():
    s = ls.shop_event(_event())
    bh = ls.best_quote(s["spreads"]["home"])
    # home median point = -3.0, best = -2.5 -> gain +0.5
    assert bh["median_point"] == -3.0 and bh["shop_gain"] == 0.5


def test_best_for_pick_routes_side():
    ev = _event()
    assert ls.best_for_pick(ev, "away", "spreads")["book"] == "draftkings"
    assert ls.best_for_pick(ev, "Over", "totals")["point"] == 47.5


def test_unknown_team_returns_none():
    ev = _event(); ev["home_team"] = "Toronto Argonauts"
    assert ls.shop_event(ev) is None


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"ok  {fn.__name__}")
    print(f"\n{len(fns)} passed")


# ---- review 2026-07-17 U4A-3 / U4B-6: divergent totals, favorability by side ----
def _divergent_totals_event():
    return {"home_team": "Atlanta Falcons", "away_team": "Los Angeles Rams",
            "commence_time": "2026-09-13T17:00:00Z",
            "bookmakers": [
                {"key": b, "title": b, "markets": [{"key": "totals", "outcomes": [
                    {"name": "Over", "point": pt, "price": 1.91},
                    {"name": "Under", "point": pt, "price": 1.91}]}]}
                for b, pt in [("bookA", 46.5), ("bookB", 47.5), ("bookC", 48.5)]]}


def test_totals_over_prefers_lowest_point():
    ev = _divergent_totals_event()
    best = ls.best_for_pick(ev, "Over", "totals")
    assert best["point"] == 46.5, "Over must shop to the LOWEST total"
    assert best["shop_gain"] == 1.0          # 47.5 median - 46.5, positive gain


def test_totals_under_prefers_highest_point():
    ev = _divergent_totals_event()
    best = ls.best_for_pick(ev, "Under", "totals")
    assert best["point"] == 48.5, "Under must shop to the HIGHEST total"
    assert best["shop_gain"] == 1.0


def test_best_quote_tiebreak_deterministic():
    quotes = [(47.5, 1.91, "zbook"), (47.5, 1.91, "abook")]
    assert ls.best_quote(quotes)["book"] == "zbook"       # (pt, price, book) max
    assert ls.best_quote(quotes, prefer_low_point=True)["book"] == "abook"
