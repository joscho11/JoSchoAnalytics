"""Hermetic tests for the player-prop scanner — no network."""
import props_scanner as ps


def _proj_row(name, pos, **stats):
    row = {"player_display_name": name, "position": pos,
           "pred_qb_pass_yards": None, "pred_qb_rush_yards": None,
           "pred_rush_yards": None, "pred_rec_yards": None,
           "pred_wr_receptions": None, "pred_wr_rec_yards": None,
           "pred_te_receptions": None, "pred_te_rec_yards": None}
    row.update(stats)
    return row


def _event_pass_yds(player, line, over=1.91, under=1.91):
    mk = {"key": "player_pass_yds", "outcomes": [
        {"name": "Over", "description": player, "point": line, "price": over},
        {"name": "Under", "description": player, "point": line, "price": under}]}
    return {"bookmakers": [{"key": "fanduel", "markets": [mk]},
                           {"key": "draftkings", "markets": [mk]}]}


def test_projected_stat_by_position():
    qb = _proj_row("Josh Allen", "QB", pred_qb_pass_yards=290, pred_qb_rush_yards=40)
    rb = _proj_row("Bijan Robinson", "RB", pred_rush_yards=85, pred_rec_yards=30)
    wr = _proj_row("CeeDee Lamb", "WR", pred_wr_receptions=7, pred_wr_rec_yards=95)
    assert ps.projected_stat(qb, "player_pass_yds") == 290
    assert ps.projected_stat(qb, "player_rush_yds") == 40       # QB uses qb_rush
    assert ps.projected_stat(rb, "player_rush_yds") == 85       # RB uses rush_yards
    assert ps.projected_stat(wr, "player_receptions") == 7
    assert ps.projected_stat(wr, "player_reception_yds") == 95


def test_consensus_line_is_median():
    ev = {"bookmakers": [
        {"key": "a", "markets": [{"key": "player_pass_yds", "outcomes": [
            {"name": "Over", "description": "Josh Allen", "point": 248.5, "price": 1.9}]}]},
        {"key": "b", "markets": [{"key": "player_pass_yds", "outcomes": [
            {"name": "Over", "description": "Josh Allen", "point": 251.5, "price": 1.95}]}]}]}
    cons = ps.consensus_props(ev, "player_pass_yds")
    assert cons["josh allen"]["line"] == 250.0
    assert cons["josh allen"]["over"] == 1.95   # best (max) over price


def test_scan_flags_over_when_projection_above_line():
    proj = {"josh allen": _proj_row("Josh Allen", "QB", pred_qb_pass_yards=290)}
    ev = _event_pass_yds("Josh Allen", 248.5)
    rows = ps.scan_event(ev, proj, ["player_pass_yds"], min_edge=5.0)
    assert len(rows) == 1
    r = rows[0]
    assert r["side"] == "Over" and r["edge_units"] > 0 and r["ev"] > 0
    assert r["p"] > 0.5


def test_scan_skips_unmatched_player():
    proj = {"josh allen": _proj_row("Josh Allen", "QB", pred_qb_pass_yards=290)}
    ev = _event_pass_yds("Patrick Mahomes", 248.5)  # not in projections
    assert ps.scan_event(ev, proj, ["player_pass_yds"], min_edge=5.0) == []


def test_scan_respects_min_edge():
    proj = {"josh allen": _proj_row("Josh Allen", "QB", pred_qb_pass_yards=250)}
    ev = _event_pass_yds("Josh Allen", 248.5)  # only 1.5 yds gap < min_edge 5
    assert ps.scan_event(ev, proj, ["player_pass_yds"], min_edge=5.0) == []


def test_name_normalization():
    assert ps.normalize_name("Michael Pittman Jr.") == "michael pittman"
    assert ps.normalize_name("A.J. Brown") == "aj brown"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"ok  {fn.__name__}")
    print(f"\n{len(fns)} passed")


# ---- review 2026-07-17 U4A-5 / U4A-7 / U4B-8 -----------------------------------
def test_events_on_matches_eastern_date(monkeypatch):
    # SNF 8:20pm ET on 2026-09-13 = 00:20Z on 09-14: must be INCLUDED for 09-13
    evs = [{"id": "snf", "commence_time": "2026-09-14T00:20:00Z"},
           {"id": "next_week", "commence_time": "2026-09-20T17:00:00Z"}]
    monkeypatch.setattr(ps.oc, "api_get", lambda *a, **k: (evs, {"remaining": 1, "used": 1}))
    got, _ = ps._events_on("2026-09-13")
    assert [e["id"] for e in got] == ["snf"]


def test_scan_rejects_unknown_market_before_api(monkeypatch):
    import pytest
    import types
    def boom(*a, **k):
        raise AssertionError("api_get must not be called for an unknown market")
    monkeypatch.setattr(ps.oc, "api_get", boom)
    with pytest.raises(SystemExit):
        ps.scan_cmd(types.SimpleNamespace(markets="player_anytime_td",
                                          proj="x.csv", date="2026-09-13",
                                          min_edge=5.0))


def test_thin_consensus_skipped(monkeypatch):
    ev = {"bookmakers": [
        {"key": "b1", "markets": [{"key": "player_rush_yds", "outcomes": [
            {"name": "Over", "description": "Test Player", "point": 70.5, "price": 1.9},
            {"name": "Under", "description": "Test Player", "point": 70.5, "price": 1.9}]}]},
        {"key": "b2", "markets": [{"key": "player_rush_yds", "outcomes": [
            {"name": "Over", "description": "Test Player", "point": 71.5, "price": 1.95},
            {"name": "Under", "description": "Test Player", "point": 71.5, "price": 1.9}]}]},
    ]}
    rows = ps.scan_event(ev, {"test player": {"proj_rush_yds": 90.0}},
                         ["player_rush_yds"], min_edge=5.0)
    assert rows == []   # n=2 books < MIN_PROP_BOOKS=3 -> skipped, no EV row
