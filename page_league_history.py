"""League History page (site revamp Batch 3c). Tab6 body + its _sleeper_get /
_fetch_sleeper_history helpers moved byte-identical from app.py. The empty-league-ID
default + "enter your league ID" resting state (the earlier fix) move verbatim.
"""
import concurrent.futures as _cf
import glob
import html as _html
import itertools as _it
import json
import os
from datetime import datetime as dt
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import requests as req
import streamlit as st

import dashboard_data
import page_common
from dashboard_utils import metric_card, get_confidence, _md_to_html
from dashboard_chrome import _OFFLINE, TABLE_HEIGHT

_HERE = Path(__file__).resolve().parent


@st.cache_data(ttl=3600)
def _sleeper_get(url: str):
    if _OFFLINE:
        return None
    try:
        r = req.get(url, timeout=15)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None


@st.cache_data(ttl=3600)
def _fetch_sleeper_history(start_league_id: str) -> dict:
    seasons = {}
    league_name = None
    current_id  = start_league_id.strip()
    seen        = set()

    while current_id and current_id not in ("0", "") and current_id not in seen:
        if len(seen) >= 10:
            break
        seen.add(current_id)

        info = _sleeper_get(f"https://api.sleeper.app/v1/league/{current_id}")
        if not info or not isinstance(info, dict):
            break
        if league_name is None:
            league_name = info.get("name", "League")

        yr = info.get("season")
        if not yr:
            break

        users_raw   = _sleeper_get(f"https://api.sleeper.app/v1/league/{current_id}/users")   or []
        rosters_raw = _sleeper_get(f"https://api.sleeper.app/v1/league/{current_id}/rosters")  or []
        bracket_raw = _sleeper_get(f"https://api.sleeper.app/v1/league/{current_id}/winners_bracket") or []

        user_map = {
            u["user_id"]: {
                "username":  u.get("display_name") or "—",
                "team_name": (u.get("metadata") or {}).get("team_name") or "",
            }
            for u in users_raw if isinstance(u, dict)
        }

        playoff_finish = {}
        champion_rid   = None
        runner_up_rid  = None

        if bracket_raw and info.get("status") == "complete":
            valid = [m for m in bracket_raw if isinstance(m, dict)]
            max_r = max((m.get("r", 0) for m in valid), default=0)
            for m in valid:
                if m.get("r") != max_r or m.get("w") is None or m.get("l") is None:
                    continue
                w, l, p = str(m["w"]), str(m["l"]), m.get("p")
                if p == 1:
                    champion_rid  = w
                    runner_up_rid = l
                if p:
                    if w not in playoff_finish or p < playoff_finish[w]:
                        playoff_finish[w] = p
                    if l not in playoff_finish or p + 1 < playoff_finish[l]:
                        playoff_finish[l] = p + 1

        standings = []
        for ro in rosters_raw:
            if not isinstance(ro, dict):
                continue
            rid      = str(ro.get("roster_id", ""))
            owner_id = ro.get("owner_id")
            u        = user_map.get(owner_id, {"username": "—", "team_name": ""})
            s        = ro.get("settings") or {}
            fpts     = s.get("fpts", 0) + s.get("fpts_decimal", 0) / 100
            fpts_ag  = s.get("fpts_against", 0) + s.get("fpts_against_decimal", 0) / 100
            standings.append({
                "roster_id":     ro.get("roster_id"),
                "username":      u["username"],
                "team_name":     u["team_name"],
                "wins":          s.get("wins", 0),
                "losses":        s.get("losses", 0),
                "fpts":          round(fpts, 2),
                "fpts_against":  round(fpts_ag, 2),
                "playoff_finish": playoff_finish.get(rid),
            })

        standings.sort(key=lambda x: (x["playoff_finish"] or 99, -x["wins"], -x["fpts"]))

        def _by_rid(rid_str):
            for row in standings:
                if str(row["roster_id"]) == rid_str:
                    return row
            return {"username": "?", "team_name": ""}

        champ = _by_rid(champion_rid)  if champion_rid  else {"username": "?", "team_name": ""}
        ruup  = _by_rid(runner_up_rid) if runner_up_rid else {"username": "?", "team_name": ""}

        # Fetch weekly matchups — parallelised to avoid 18 serial HTTP calls per season
        _lg_settings  = info.get("settings") or {}
        _playoff_start = int(_lg_settings.get("playoff_week_start") or 15)

        def _fetch_wk(wk):
            try:
                r = req.get(
                    f"https://api.sleeper.app/v1/league/{current_id}/matchups/{wk}",
                    timeout=15,
                )
                r.raise_for_status()
                return wk, r.json()
            except Exception:
                return wk, None

        with _cf.ThreadPoolExecutor(max_workers=18) as _pool:
            _wk_data = dict(_pool.map(_fetch_wk, range(1, 19)))

        _matchups_season: list = []
        for _wk in range(1, 19):
            _wk_raw = _wk_data.get(_wk)
            if not _wk_raw or not isinstance(_wk_raw, list):
                continue
            _grps: dict = {}
            for _entry in _wk_raw:
                if not isinstance(_entry, dict):
                    continue
                _mid = _entry.get("matchup_id")
                if _mid is None:
                    continue
                _grps.setdefault(_mid, []).append(_entry)
            for _mid2, _ents in _grps.items():
                if len(_ents) == 2:
                    _ma, _mb = _ents[0], _ents[1]
                    _sa = float(_ma.get("points") or 0)
                    _sb = float(_mb.get("points") or 0)
                    if _sa == 0 and _sb == 0:
                        continue
                    _matchups_season.append({
                        "season":     yr,
                        "week":       _wk,
                        "is_playoff": _wk >= _playoff_start,
                        "rid_a":      str(_ma.get("roster_id", "")),
                        "score_a":    _sa,
                        "rid_b":      str(_mb.get("roster_id", "")),
                        "score_b":    _sb,
                    })

        seasons[yr] = {
            "league_id": current_id,
            "status":    info.get("status"),
            "champion":  {"username": champ["username"], "team_name": champ.get("team_name", "")},
            "runner_up": {"username": ruup["username"],  "team_name": ruup.get("team_name", "")},
            "standings": standings,
            "matchups":  _matchups_season,
        }

        prev = info.get("previous_league_id")
        current_id = prev if (prev and prev != "0") else ""

    return {"league_name": league_name or "League", "seasons": seasons}


def render():
    st.title("🏅 Fantasy League History")

    _league_id_input = st.text_input(
        "Sleeper League ID",
        value="",
        placeholder="e.g. 1255197436951932928",
        help="Find it in your Sleeper league URL: sleeper.com/leagues/{ID}/league",
        key="lh_league_id",
    )

    _lid = _league_id_input.strip()
    # Resting state (empty field, including offline): a neutral prompt, no fetch.
    if not _lid.isdigit():
        st.info("Enter your Sleeper league ID to load your league history.")
    elif _OFFLINE:
        st.info("League history needs a live connection to Sleeper and is "
                "unavailable offline.")
    else:
        with st.spinner("Loading league history from Sleeper…"):
            _lh = _fetch_sleeper_history(_lid)

        if not _lh["seasons"]:
            st.error("No data found — double-check the league ID and try again.")
        else:
            st.header(_lh["league_name"])

            # Season filter
            _seasons_list = sorted(_lh["seasons"].keys())
            _season_filter = st.selectbox(
                "Season",
                ["All Time"] + _seasons_list,
                key="lh_season_filter",
            )

            # Build cross-season helpers
            _rid_to_user: dict = {}
            for _yr0, _sd0 in _lh["seasons"].items():
                for _row0 in _sd0["standings"]:
                    _rid_to_user[(_yr0, str(_row0["roster_id"]))] = _row0["username"]

            _all_matchups = [
                _m for _sd0 in _lh["seasons"].values()
                for _m in _sd0.get("matchups", [])
            ]

            def _guser(_yr_g, _rid_g):
                return _rid_to_user.get((_yr_g, _rid_g), "?")

            # Expand matchups into per-player game records (full, unfiltered)
            _game_records = []
            for _m0 in _all_matchups:
                _ua0 = _guser(_m0["season"], _m0["rid_a"])
                _ub0 = _guser(_m0["season"], _m0["rid_b"])
                if "?" in (_ua0, _ub0):
                    continue
                _sa0, _sb0 = _m0["score_a"], _m0["score_b"]
                _game_records += [
                    {"season": _m0["season"], "week": _m0["week"],
                     "is_playoff": _m0["is_playoff"],
                     "username": _ua0, "score": _sa0, "won": _sa0 > _sb0,
                     "opp": _ub0, "opp_score": _sb0},
                    {"season": _m0["season"], "week": _m0["week"],
                     "is_playoff": _m0["is_playoff"],
                     "username": _ub0, "score": _sb0, "won": _sb0 > _sa0,
                     "opp": _ua0, "opp_score": _sa0},
                ]

            # Apply season filter
            if _season_filter == "All Time":
                _filt_records  = _game_records
                _filt_matchups = _all_matchups
                _filt_seasons  = _lh["seasons"]
            else:
                _filt_records  = [r for r in _game_records  if r["season"] == _season_filter]
                _filt_matchups = [m for m in _all_matchups  if m["season"] == _season_filter]
                _filt_seasons  = {k: v for k, v in _lh["seasons"].items() if k == _season_filter}

            _all_managers = sorted(set(r["username"] for r in _game_records))

            # Compute manager list once, before sub-tabs (used in both C and D)
            _h2h_managers = sorted(set(r["username"] for r in _filt_records)) if _season_filter != "All Time" else _all_managers

            # Sub-tabs
            _lhA, _lhB, _lhC, _lhD, _lhE, _lhF = st.tabs([
                "🏆 All-Time Records",
                "🎖️ Hall of Fame",
                "⚔️ Head-to-Head",
                "📋 Report Cards",
                "📊 Consistency & Luck",
                "📈 Score Trends",
            ])

            # ── Sub-tab A: All-Time Records ────────────────────────────────────
            with _lhA:
                _rec_label = "Season" if _season_filter != "All Time" else "All-Time"
                st.subheader(f"{_rec_label} Records")

                _at: dict = {}
                for _yr2, _sd2 in _filt_seasons.items():
                    for _s2 in _sd2["standings"]:
                        _u2 = _s2["username"]
                        if not _u2 or _u2 == "—":
                            continue
                        if _u2 not in _at:
                            _at[_u2] = {"titles": 0, "finals": 0, "seasons": 0,
                                        "wins": 0, "losses": 0, "fpts": 0.0, "best": 99}
                        _at[_u2]["seasons"] += 1
                        _at[_u2]["wins"]    += _s2["wins"]
                        _at[_u2]["losses"]  += _s2["losses"]
                        _at[_u2]["fpts"]    += _s2["fpts"]
                        _pf3 = _s2.get("playoff_finish")
                        if _pf3 and _pf3 < _at[_u2]["best"]:
                            _at[_u2]["best"] = _pf3
                    _cu = _sd2["champion"]["username"]
                    _ru = _sd2["runner_up"]["username"]
                    if _cu and _cu not in ("?", "—") and _cu in _at:
                        _at[_cu]["titles"] += 1
                    if _ru and _ru not in ("?", "—") and _ru in _at:
                        _at[_ru]["finals"] += 1

                _pf_label = "PF" if _season_filter != "All Time" else "Career PF"
                _at_rows = []
                for _u2, _stats in _at.items():
                    _tot2 = _stats["wins"] + _stats["losses"]
                    _at_rows.append({
                        "Manager":      _u2,
                        "Titles":       _stats["titles"],
                        "Finals":       _stats["titles"] + _stats["finals"],
                        "Best Finish":  str(_stats["best"]) if _stats["best"] < 99 else "DNQ",
                        "Seasons":      _stats["seasons"],
                        "W":            _stats["wins"],
                        "L":            _stats["losses"],
                        "Win %":        round(_stats["wins"] / _tot2 * 100, 1) if _tot2 > 0 else 0,
                        _pf_label:      round(_stats["fpts"], 2),
                    })

                _at_df = (
                    pd.DataFrame(_at_rows)
                    .sort_values(["Titles", "Win %"], ascending=[False, False])
                    .reset_index(drop=True)
                )
                _at_df.index += 1
                st.dataframe(
                    _at_df,
                    width="stretch",
                    height=TABLE_HEIGHT,
                    column_config={
                        "Titles":    st.column_config.NumberColumn("Titles",   help="Championship wins"),
                        "Finals":    st.column_config.NumberColumn("Finals",   help="Championship appearances"),
                        "Win %":     st.column_config.NumberColumn("Win %",    format="%.1f%%"),
                        _pf_label:   st.column_config.NumberColumn(_pf_label,  format="%.2f"),
                    }
                )

            # ── Sub-tab B: Hall of Fame / Shame ───────────────────────────────
            with _lhB:
                _hof_scope = _season_filter if _season_filter != "All Time" else "all seasons"
                st.subheader("Hall of Fame & Shame")
                st.caption(f"Records from {_hof_scope}, including playoffs.")

                if not _filt_records:
                    st.info("No weekly matchup data available.")
                else:
                    _played_recs = [r for r in _filt_records if r["score"] > 5]
                    _best_score  = max(_played_recs, key=lambda r: r["score"]) if _played_recs else None
                    _worst_score = min(_played_recs, key=lambda r: r["score"]) if _played_recs else None
                    _losses_recs = [r for r in _played_recs if not r["won"]]
                    _wins_recs   = [r for r in _played_recs if r["won"]]
                    _best_loss   = max(_losses_recs, key=lambda r: r["score"]) if _losses_recs else None
                    _luck_win    = min(_wins_recs,   key=lambda r: r["score"]) if _wins_recs   else None

                    _margins = []
                    for _m1 in _filt_matchups:
                        _ua1 = _guser(_m1["season"], _m1["rid_a"])
                        _ub1 = _guser(_m1["season"], _m1["rid_b"])
                        if "?" in (_ua1, _ub1):
                            continue
                        _sa1, _sb1 = _m1["score_a"], _m1["score_b"]
                        if _sa1 < 5 and _sb1 < 5:
                            continue
                        if _sa1 == _sb1:
                            continue
                        _hi1, _lo1 = max(_sa1, _sb1), min(_sa1, _sb1)
                        _win1 = _ua1 if _sa1 > _sb1 else _ub1
                        _los1 = _ub1 if _sa1 > _sb1 else _ua1
                        _margins.append({
                            "season": _m1["season"], "week": _m1["week"],
                            "winner": _win1, "loser": _los1,
                            "winner_score": _hi1, "loser_score": _lo1,
                            "margin": _hi1 - _lo1, "combined": _sa1 + _sb1,
                        })
                    _blowout     = max(_margins, key=lambda m: m["margin"])   if _margins else None
                    _closest     = min(_margins, key=lambda m: m["margin"])   if _margins else None
                    _hi_combined = max(_margins, key=lambda m: m["combined"]) if _margins else None
                    _lo_combined = min(_margins, key=lambda m: m["combined"]) if _margins else None

                    def _hof_card(emoji, title, headline, detail, color="#00c853"):
                        return (
                            f"<div style='background:#1a2332;border:1px solid #2d3748;"
                            f"border-radius:10px;padding:18px;margin-bottom:10px'>"
                            f"<span style='font-size:26px'>{emoji}</span>"
                            f"<div style='font-size:11px;color:#888;text-transform:uppercase;"
                            f"letter-spacing:1px;margin-top:4px'>{title}</div>"
                            f"<div style='font-size:20px;font-weight:800;color:{color};"
                            f"margin-top:2px'>{headline}</div>"
                            f"<div style='font-size:12px;color:#aaa;margin-top:4px'>{detail}</div>"
                            f"</div>"
                        )

                    _hc1, _hc2 = st.columns(2)
                    with _hc1:
                        if _best_score:
                            st.markdown(_hof_card(
                                "🏆", "Highest Single-Week Score",
                                f"{_best_score['score']:.2f} pts",
                                f"{_best_score['username']} · {_best_score['season']} Week {_best_score['week']}",
                                "#ffd700"
                            ), unsafe_allow_html=True)
                        if _best_loss:
                            st.markdown(_hof_card(
                                "😤", "Most Points in a Loss",
                                f"{_best_loss['score']:.2f} pts",
                                f"{_best_loss['username']} lost to {_best_loss['opp']} "
                                f"({_best_loss['opp_score']:.2f}) · "
                                f"{_best_loss['season']} Wk {_best_loss['week']}",
                                "#ff9800"
                            ), unsafe_allow_html=True)
                        if _blowout:
                            st.markdown(_hof_card(
                                "💥", "Biggest Blowout",
                                f"+{_blowout['margin']:.2f} pts",
                                f"{_blowout['winner']} def. {_blowout['loser']} "
                                f"({_blowout['winner_score']:.2f}–{_blowout['loser_score']:.2f}) · "
                                f"{_blowout['season']} Wk {_blowout['week']}",
                                "#e040fb"
                            ), unsafe_allow_html=True)
                        if _hi_combined:
                            st.markdown(_hof_card(
                                "🔥", "Highest-Scoring Game",
                                f"{_hi_combined['combined']:.2f} combined pts",
                                f"{_hi_combined['winner']} vs {_hi_combined['loser']} · "
                                f"{_hi_combined['season']} Wk {_hi_combined['week']}",
                                "#ff6e40"
                            ), unsafe_allow_html=True)
                    with _hc2:
                        if _worst_score:
                            st.markdown(_hof_card(
                                "💀", "Lowest Single-Week Score",
                                f"{_worst_score['score']:.2f} pts",
                                f"{_worst_score['username']} · {_worst_score['season']} Week {_worst_score['week']}",
                                "#ff5252"
                            ), unsafe_allow_html=True)
                        if _luck_win:
                            st.markdown(_hof_card(
                                "🍀", "Luckiest Win",
                                f"{_luck_win['score']:.2f} pts",
                                f"{_luck_win['username']} beat {_luck_win['opp']} "
                                f"({_luck_win['opp_score']:.2f}) · "
                                f"{_luck_win['season']} Wk {_luck_win['week']}",
                                "#00e5ff"
                            ), unsafe_allow_html=True)
                        if _closest:
                            st.markdown(_hof_card(
                                "🤝", "Closest Game",
                                f"{_closest['margin']:.2f} pt margin",
                                f"{_closest['winner']} def. {_closest['loser']} "
                                f"({_closest['winner_score']:.2f}–{_closest['loser_score']:.2f}) · "
                                f"{_closest['season']} Wk {_closest['week']}",
                                "#69f0ae"
                            ), unsafe_allow_html=True)
                        if _lo_combined:
                            st.markdown(_hof_card(
                                "🧊", "Lowest-Scoring Game",
                                f"{_lo_combined['combined']:.2f} combined pts",
                                f"{_lo_combined['winner']} vs {_lo_combined['loser']} · "
                                f"{_lo_combined['season']} Wk {_lo_combined['week']}",
                                "#82b1ff"
                            ), unsafe_allow_html=True)

            # ── Sub-tab C: Head-to-Head ───────────────────────────────────────
            with _lhC:
                _h2h_scope = _season_filter if _season_filter != "All Time" else "all-time"
                st.subheader("Head-to-Head Records")
                st.caption(f"Record against each opponent (W–L), {_h2h_scope}. Includes playoffs. Row beats column.")

                _h2h: dict = {}
                for _rh in _filt_records:
                    if not _rh["won"]:
                        continue
                    _kh = frozenset([_rh["username"], _rh["opp"]])
                    _h2h.setdefault(_kh, {})
                    _h2h[_kh][_rh["username"]] = _h2h[_kh].get(_rh["username"], 0) + 1
                    _h2h[_kh].setdefault(_rh["opp"], 0)

                _mgrs_sorted = _h2h_managers
                _matrix_rows = []
                for _um in _mgrs_sorted:
                    _row_d = {"Manager": _um}
                    for _vm in _mgrs_sorted:
                        if _um == _vm:
                            _row_d[_vm] = "—"
                        else:
                            _kh2 = frozenset([_um, _vm])
                            _w   = _h2h.get(_kh2, {}).get(_um, 0)
                            _l   = _h2h.get(_kh2, {}).get(_vm, 0)
                            _row_d[_vm] = f"{_w}–{_l}"
                    _matrix_rows.append(_row_d)

                _h2h_df = pd.DataFrame(_matrix_rows).set_index("Manager")
                st.dataframe(_h2h_df, width="stretch")

            # ── Sub-tab D: Report Cards ───────────────────────────────────────
            with _lhD:
                _rc_scope = _season_filter if _season_filter != "All Time" else "all-time"
                st.subheader("Manager Report Cards")

                if not _h2h_managers:
                    st.info("No managers found for this filter.")
                    _sel_mgr = None
                else:
                    _sel_mgr = st.selectbox("Select a manager", _h2h_managers, key="lh_manager")
                _mgr_games = [r for r in _filt_records if r["username"] == _sel_mgr] if _sel_mgr else []

                # Season history always shows full career (not filtered)
                _mgr_season_rows: dict = {}
                for _yr3, _sd3 in _lh["seasons"].items():
                    for _row3 in _sd3["standings"]:
                        if _row3["username"] == _sel_mgr:
                            _mgr_season_rows[_yr3] = _row3

                if not _mgr_games:
                    st.info(f"No data for this manager in {_rc_scope}.")
                else:
                    _sc_all = [r["score"] for r in _mgr_games]
                    _w_all  = sum(1 for r in _mgr_games if r["won"])
                    _l_all  = sum(1 for r in _mgr_games if not r["won"])
                    _titles = sum(1 for _sd4 in _filt_seasons.values()
                                  if _sd4["champion"]["username"] == _sel_mgr)
                    _finals = sum(1 for _sd4 in _filt_seasons.values()
                                  if _sd4["runner_up"]["username"] == _sel_mgr)
                    _playoff_apps = sum(
                        1 for _yr3p, _s4 in _mgr_season_rows.items()
                        if _s4.get("playoff_finish") is not None
                        and (_season_filter == "All Time" or _yr3p == _season_filter)
                    )

                    _d1, _d2, _d3, _d4, _d5 = st.columns(5)
                    _d1.metric("Championships", _titles)
                    _d2.metric("Finals", _titles + _finals)
                    _d3.metric("Playoff Apps", _playoff_apps)
                    _d4.metric("Record", f"{_w_all}–{_l_all}")
                    _d5.metric("Win %",
                               f"{_w_all / (_w_all + _l_all) * 100:.1f}%"
                               if (_w_all + _l_all) else "N/A")

                    _d6, _d7, _d8 = st.columns(3)
                    _d6.metric("Avg Score",  f"{sum(_sc_all)/len(_sc_all):.2f}")
                    _d7.metric("Best Week",  f"{max(_sc_all):.2f}")
                    _d8.metric("Worst Week", f"{min(_sc_all):.2f}")

                    st.divider()
                    st.markdown("**Season History**")
                    _s_hist = []
                    for _yr4 in sorted(_mgr_season_rows):
                        _row4 = _mgr_season_rows[_yr4]
                        _pf4  = _row4.get("playoff_finish")
                        _fin4 = {1: "🥇 Champion", 2: "🥈 Runner-up", 3: "🥉 3rd"}.get(
                            _pf4, f"{_pf4}th" if _pf4 else "DNQ")
                        _s_hist.append({
                            "Season":    _yr4,
                            "Team Name": _row4.get("team_name") or "—",
                            "Record":    f"{_row4['wins']}–{_row4['losses']}",
                            "PF":        _row4["fpts"],
                            "PA":        _row4["fpts_against"],
                            "Finish":    _fin4,
                        })
                    st.dataframe(
                        pd.DataFrame(_s_hist),
                        hide_index=True,
                        width="stretch",
                        column_config={
                            "PF": st.column_config.NumberColumn("PF", format="%.2f"),
                            "PA": st.column_config.NumberColumn("PA", format="%.2f"),
                        }
                    )

                    st.divider()
                    st.markdown("**Opponent Breakdown**")
                    _opp_recs: dict = {}
                    for _r4 in _mgr_games:
                        _opp4 = _r4["opp"]
                        _opp_recs.setdefault(_opp4, {"wins": 0, "losses": 0})
                        if _r4["won"]:
                            _opp_recs[_opp4]["wins"] += 1
                        else:
                            _opp_recs[_opp4]["losses"] += 1
                    _h2h_rows4 = sorted(
                        [{"Opponent": _o, "W": _v["wins"], "L": _v["losses"],
                          "+/-": _v["wins"] - _v["losses"]}
                         for _o, _v in _opp_recs.items()],
                        key=lambda r: -r["+/-"]
                    )
                    st.dataframe(pd.DataFrame(_h2h_rows4), hide_index=True, width="stretch")

            # ── Sub-tab E: Consistency & Luck ─────────────────────────────────
            with _lhE:
                _cl_scope = _season_filter if _season_filter != "All Time" else "all seasons"
                st.subheader("Consistency & Luck")
                st.caption(f"Regular season only · {_cl_scope}. Luck is measured relative to the league average score that week.")

                _rs_recs = [r for r in _filt_records if not r["is_playoff"]]

                _week_avg: dict = {}
                for _r5 in _rs_recs:
                    _k5 = (_r5["season"], _r5["week"])
                    _week_avg.setdefault(_k5, []).append(_r5["score"])
                _week_avg = {k: sum(v) / len(v) for k, v in _week_avg.items()}

                _mgr_cl: dict = {}
                for _r5 in _rs_recs:
                    _u5 = _r5["username"]
                    _mgr_cl.setdefault(_u5, {
                        "scores": [], "wins": 0, "losses": 0,
                        "lucky_wins": 0, "unlucky_losses": 0, "pts_in_losses": []
                    })
                    _mgr_cl[_u5]["scores"].append(_r5["score"])
                    _avg5 = _week_avg.get((_r5["season"], _r5["week"]), 0)
                    if _r5["won"]:
                        _mgr_cl[_u5]["wins"] += 1
                        if _r5["score"] < _avg5:
                            _mgr_cl[_u5]["lucky_wins"] += 1
                    else:
                        _mgr_cl[_u5]["losses"] += 1
                        _mgr_cl[_u5]["pts_in_losses"].append(_r5["score"])
                        if _r5["score"] > _avg5:
                            _mgr_cl[_u5]["unlucky_losses"] += 1

                _cl_rows = []
                for _u5, _st5 in _mgr_cl.items():
                    _sc5 = _st5["scores"]
                    _avg_loss5 = (sum(_st5["pts_in_losses"]) / len(_st5["pts_in_losses"])
                                  if _st5["pts_in_losses"] else 0)
                    _cl_rows.append({
                        "Manager":         _u5,
                        "Avg Score":       round(sum(_sc5) / len(_sc5), 2),
                        "Std Dev":         round(pd.Series(_sc5).std(), 2) if len(_sc5) > 1 else 0,
                        "Avg Pts in Loss": round(_avg_loss5, 2),
                        "Lucky Wins":      _st5["lucky_wins"],
                        "Unlucky Losses":  _st5["unlucky_losses"],
                    })

                _cl_df = (
                    pd.DataFrame(_cl_rows)
                    .sort_values("Avg Score", ascending=False)
                    .reset_index(drop=True)
                )
                _cl_df.index += 1
                st.dataframe(
                    _cl_df, width="stretch", height=TABLE_HEIGHT,
                    column_config={
                        "Avg Score":       st.column_config.NumberColumn("Avg Score",       format="%.2f"),
                        "Std Dev":         st.column_config.NumberColumn("Std Dev",         format="%.2f",
                                           help="Lower = more consistent week to week"),
                        "Avg Pts in Loss": st.column_config.NumberColumn("Avg Pts in Loss", format="%.2f",
                                           help="Average score when losing — higher means more unlucky"),
                        "Lucky Wins":      st.column_config.NumberColumn("Lucky Wins",
                                           help="Wins where you scored below the league average that week"),
                        "Unlucky Losses":  st.column_config.NumberColumn("Unlucky Losses",
                                           help="Losses where you scored above the league average that week"),
                    }
                )

                if _cl_rows:
                    _most_con  = min(_cl_rows, key=lambda r: r["Std Dev"])
                    _most_vol  = max(_cl_rows, key=lambda r: r["Std Dev"])
                    _most_unl  = max(_cl_rows, key=lambda r: r["Unlucky Losses"])
                    _most_luck = max(_cl_rows, key=lambda r: r["Lucky Wins"])
                    st.divider()
                    _e1, _e2 = st.columns(2)
                    with _e1:
                        st.info(
                            f"**Most Consistent:** {_most_con['Manager']}  \n"
                            f"Std Dev: {_most_con['Std Dev']:.2f} pts/week"
                        )
                        st.info(
                            f"**Most Volatile:** {_most_vol['Manager']}  \n"
                            f"Std Dev: {_most_vol['Std Dev']:.2f} pts/week"
                        )
                    with _e2:
                        st.warning(
                            f"**Most Unlucky:** {_most_unl['Manager']}  \n"
                            f"{_most_unl['Unlucky Losses']} losses where they scored above the weekly avg"
                        )
                        st.success(
                            f"**Most Lucky:** {_most_luck['Manager']}  \n"
                            f"{_most_luck['Lucky Wins']} wins where they scored below the weekly avg"
                        )

            # ── Sub-tab F: Score Trends ───────────────────────────────────────
            with _lhF:
                st.subheader("Score Trends")

                # Build avg score per manager per season (always uses full unfiltered data)
                _trend_data = []
                for _yr5, _sd5 in _lh["seasons"].items():
                    for _row5 in _sd5["standings"]:
                        _u5t = _row5["username"]
                        if not _u5t or _u5t in ("—", "?"):
                            continue
                        _wk_scores5 = [
                            r["score"] for r in _game_records
                            if r["username"] == _u5t
                            and r["season"] == _yr5
                            and not r["is_playoff"]
                        ]
                        if _wk_scores5:
                            _trend_data.append({
                                "Season":    _yr5,
                                "Manager":   _u5t,
                                "Avg Score": round(sum(_wk_scores5) / len(_wk_scores5), 2),
                            })

                if not _trend_data:
                    st.info("Not enough weekly data for trend chart.")
                elif _season_filter != "All Time":
                    # Single season: bar chart ranked by avg score
                    st.caption(f"Average regular season score per manager — {_season_filter}.")
                    _bar_data = [d for d in _trend_data if d["Season"] == _season_filter]
                    _bar_data.sort(key=lambda d: d["Avg Score"], reverse=True)
                    if _bar_data:
                        _fig_bar = go.Figure(go.Bar(
                            x=[d["Manager"]   for d in _bar_data],
                            y=[d["Avg Score"] for d in _bar_data],
                            marker_color="#00c853",
                            hovertemplate="%{x}: %{y:.2f} pts<extra></extra>",
                        ))
                        _fig_bar.update_layout(
                            height=420,
                            xaxis_title="Manager",
                            yaxis_title="Avg Weekly Score",
                            template="plotly_dark",
                            yaxis=dict(range=[
                                min(d["Avg Score"] for d in _bar_data) * 0.97,
                                max(d["Avg Score"] for d in _bar_data) * 1.03,
                            ]),
                        )
                        st.plotly_chart(_fig_bar, width="stretch")
                else:
                    # All-time: multi-season line chart
                    st.caption("Average regular season score per manager, by season.")
                    _trend_df = pd.DataFrame(_trend_data)
                    _fig_trend = go.Figure()
                    for _mgr_t in sorted(_trend_df["Manager"].unique()):
                        _d_t = _trend_df[_trend_df["Manager"] == _mgr_t].sort_values("Season")
                        _fig_trend.add_trace(go.Scatter(
                            x=_d_t["Season"],
                            y=_d_t["Avg Score"],
                            name=_mgr_t,
                            mode="lines+markers",
                            hovertemplate="%{fullData.name}<br>%{x}: %{y:.2f} pts<extra></extra>",
                        ))
                    _fig_trend.update_layout(
                        height=450,
                        xaxis_title="Season",
                        yaxis_title="Avg Weekly Score",
                        template="plotly_dark",
                        legend_title="Manager",
                        hovermode="x unified",
                    )
                    st.plotly_chart(_fig_trend, width="stretch")



# ══════════════════════════════════════════════════════════════════════════════
# TAB 7: HELP & GUIDE
# ══════════════════════════════════════════════════════════════════════════════
