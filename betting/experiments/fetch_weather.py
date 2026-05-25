"""Fetch kickoff-time weather for every outdoor NFL game 2014-present and write
betting/nfl_weather_2014_<latest>.csv.

This solves a real data problem: nflreadpy's schedules.temp / .wind columns
have ~50% missing data for outdoor games in 2022 and ~22% for 2023 — they
were originally removed from the production feature set because of this.
This script pulls the same underlying weather from Meteostat (NOAA-backed,
free, no API key) and writes a complete CSV that the feature pipeline can
merge in.

Run once per year after the season ends to refresh.

Usage:
    python betting/experiments/fetch_weather.py            # 2014-current
    python betting/experiments/fetch_weather.py --since 2024   # only fresh seasons

Outputs (CSV, one row per outdoor game):
    game_id, stadium_id, kickoff_utc, station_id, station_name,
    temp_f, wind_mph, precip_in, humidity_pct, source

Indoor/dome games are skipped — they have no kickoff-time weather to record.
"""
from __future__ import annotations

import argparse
import io
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Windows console defaults to cp1252; force UTF-8 so the unicode arrows render.
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

import pandas as pd
import pytz
from meteostat import hourly, stations

import nflreadpy as nfl


# ─── Stadium coordinates (lat, lon, IANA timezone) ──────────────────────────
# Every outdoor stadium that hosted a REG-season game 2014-present.
# Closed-roof / dome stadiums are intentionally absent — they're skipped.
# Format: stadium_id -> (lat, lon, IANA timezone, "human label")
STADIUM_COORDS: dict[str, tuple[float, float, str, str]] = {
    # ─ AFC East ─
    "BOS00": (42.0909, -71.2643, "America/New_York",  "Gillette Stadium (Foxborough, MA)"),
    "BUF00": (42.7738, -78.7869, "America/New_York",  "Highmark Stadium (Orchard Park, NY)"),
    "MIA00": (25.9580, -80.2389, "America/New_York",  "Hard Rock Stadium (Miami Gardens, FL)"),
    "NYC01": (40.8128, -74.0742, "America/New_York",  "MetLife Stadium (East Rutherford, NJ)"),
    # ─ AFC North ─
    "BAL00": (39.2780, -76.6228, "America/New_York",  "M&T Bank Stadium (Baltimore, MD)"),
    "CIN00": (39.0954, -84.5160, "America/New_York",  "Paycor Stadium (Cincinnati, OH)"),
    "CLE00": (41.5061, -81.6995, "America/New_York",  "Cleveland Browns Stadium (Cleveland, OH)"),
    "PIT00": (40.4467, -80.0156, "America/New_York",  "Acrisure Stadium (Pittsburgh, PA)"),
    # ─ AFC South ─
    "JAX00": (30.3239, -81.6373, "America/New_York",  "EverBank Stadium (Jacksonville, FL)"),
    "NAS00": (36.1665, -86.7713, "America/Chicago",   "Nissan Stadium (Nashville, TN)"),
    # ─ AFC West ─
    "DEN00": (39.7439, -105.0201, "America/Denver",   "Empower Field at Mile High (Denver, CO)"),
    "KAN00": (39.0489, -94.4839, "America/Chicago",   "Arrowhead Stadium (Kansas City, MO)"),
    "OAK00": (37.7516, -122.2008, "America/Los_Angeles", "Oakland Coliseum (Oakland, CA)"),  # retired 2019
    "SDG00": (32.7831, -117.1196, "America/Los_Angeles", "Qualcomm Stadium (San Diego, CA)"),  # retired 2016
    "LAX97": (33.8644, -118.2611, "America/Los_Angeles", "Dignity Health Sports Park (Carson, CA)"),  # LAC 2017-19
    # ─ NFC East ─
    "DAL00": (32.7473, -97.0945, "America/Chicago",   "AT&T Stadium (Arlington, TX) [retractable]"),
    "PHI00": (39.9008, -75.1675, "America/New_York",  "Lincoln Financial Field (Philadelphia, PA)"),
    "WAS00": (38.9077, -76.8645, "America/New_York",  "Northwest Stadium (Landover, MD)"),
    # ─ NFC North ─
    "CHI98": (41.8623, -87.6167, "America/Chicago",   "Soldier Field (Chicago, IL)"),
    "GNB00": (44.5013, -88.0622, "America/Chicago",   "Lambeau Field (Green Bay, WI)"),
    "MIN98": (44.9764, -93.2244, "America/Chicago",   "TCF Bank Stadium (Minneapolis, MN)"),  # 2014-15 only
    # ─ NFC South ─
    "CAR00": (35.2258, -80.8528, "America/New_York",  "Bank of America Stadium (Charlotte, NC)"),
    "TAM00": (27.9759, -82.5033, "America/New_York",  "Raymond James Stadium (Tampa, FL)"),
    # ─ NFC West ─
    "LAX99": (34.0141, -118.2879, "America/Los_Angeles", "LA Memorial Coliseum (Los Angeles, CA)"),  # LA Rams 2016-19
    "SEA00": (47.5952, -122.3316, "America/Los_Angeles", "Lumen Field (Seattle, WA)"),
    "SFO01": (37.4032, -121.9694, "America/Los_Angeles", "Levi's Stadium (Santa Clara, CA)"),
    # ─ Retractable roofs that may show as 'outdoors' when open ─
    "ATL97": (33.7553, -84.4006, "America/New_York",  "Mercedes-Benz Stadium (Atlanta, GA) [retractable]"),
    "HOU00": (29.6847, -95.4107, "America/Chicago",   "NRG Stadium (Houston, TX) [retractable]"),
    "IND00": (39.7601, -86.1639, "America/New_York",  "Lucas Oil Stadium (Indianapolis, IN) [retractable]"),
    "PHO00": (33.5276, -112.2626, "America/Phoenix",  "State Farm Stadium (Glendale, AZ) [retractable]"),
    # ─ International ─
    "LON00": (51.5560,  -0.2796, "Europe/London",     "Wembley Stadium (London, UK)"),
    "LON01": (51.4561,  -0.3415, "Europe/London",     "Twickenham Stadium (London, UK)"),  # 2016-17 only
    "LON02": (51.6043,  -0.0664, "Europe/London",     "Tottenham Stadium (London, UK)"),
    "MEX00": (19.3029, -99.1505, "America/Mexico_City", "Estadio Azteca (Mexico City, MX)"),
    "GER00": (48.2188,  11.6248, "Europe/Berlin",     "Allianz Arena (Munich, DE)"),
    "FRA00": (50.0689,   8.6453, "Europe/Berlin",     "Deutsche Bank Park (Frankfurt, DE)"),
    "SAO00": (-23.5453, -46.4742, "America/Sao_Paulo", "Arena Corinthians (São Paulo, BR)"),
}


def find_station_candidates(lat: float, lon: float) -> list[tuple[str, str]]:
    """Return up to 5 ranked station candidates for a lat/lon — each one
    pre-validated to have data at both 2015 and 2024 representative dates.

    The first candidate is the primary station. Later candidates are fallbacks
    used per-game when the primary returns no data for that specific kickoff
    hour (e.g. Denver in 2017 had sparse hour-level coverage despite passing
    the summer probe).
    """
    from meteostat import Point
    nearby = stations.nearby(Point(lat, lon), limit=15)
    if len(nearby) == 0:
        raise RuntimeError(f"No weather station found near ({lat}, {lon})")
    probes = [
        (datetime(2015, 7, 1, 12, 0), datetime(2015, 7, 1, 14, 0)),
        (datetime(2024, 7, 1, 12, 0), datetime(2024, 7, 1, 14, 0)),
    ]
    accepted: list[tuple[str, str]] = []
    for sid, row in nearby.iterrows():
        try:
            ok_both_eras = True
            for pstart, pend in probes:
                ts = hourly(sid, pstart, pend)
                df = ts.fetch()
                if df is None or len(df) == 0 or not df["temp"].notna().any():
                    ok_both_eras = False
                    break
            if ok_both_eras:
                accepted.append((sid, row["name"]))
                if len(accepted) >= 5:
                    break
        except Exception:
            continue
    if not accepted:
        # Last resort: nearest station even if probes failed (better than crashing)
        accepted.append((nearby.index[0], nearby.iloc[0]["name"]))
    return accepted


def find_station(lat: float, lon: float) -> tuple[str, str]:
    """Backward-compat wrapper returning just the primary candidate."""
    return find_station_candidates(lat, lon)[0]


def kickoff_to_utc(gameday: str, gametime: str) -> datetime | None:
    """Convert (gameday, gametime) — assumed to be US Eastern broadcast time — to UTC."""
    if not gametime or pd.isna(gametime):
        return None
    try:
        local = datetime.strptime(f"{gameday} {gametime}", "%Y-%m-%d %H:%M")
        et = pytz.timezone("America/New_York")
        local_et = et.localize(local)
        return local_et.astimezone(pytz.UTC).replace(tzinfo=None)
    except Exception:
        return None


def fetch_weather(station_id: str, kickoff_utc: datetime) -> dict | None:
    """Pull the meteostat hourly row matching the kickoff hour (UTC).
    Returns None if no data is available for that station/time."""
    start = kickoff_utc.replace(minute=0, second=0, microsecond=0)
    end = start + timedelta(hours=1, minutes=30)
    try:
        ts = hourly(station_id, start, end)
        df = ts.fetch()
    except Exception as e:
        print(f"  meteostat error for {station_id} @ {kickoff_utc}: {e}", file=sys.stderr)
        return None
    if df is None or df.empty:
        return None
    row = df.iloc[0]  # the kickoff hour
    return {
        "temp_c":   row.get("temp"),
        "wspd_kmh": row.get("wspd"),
        "prcp_mm":  row.get("prcp"),
        "rhum":     row.get("rhum"),
    }


def c_to_f(c):       return None if pd.isna(c) else round(c * 9 / 5 + 32, 1)
def kmh_to_mph(k):   return None if pd.isna(k) else round(k * 0.621371, 1)
def mm_to_in(mm):    return None if pd.isna(mm) else round(mm * 0.0393701, 2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", type=int, default=2014, help="Earliest season to fetch (default 2014)")
    ap.add_argument("--until", type=int, default=None, help="Latest season (default: current schedule's max)")
    ap.add_argument("--out", default=None, help="Output CSV path (default: betting/nfl_weather_<since>_<until>.csv)")
    args = ap.parse_args()

    out_dir = Path(__file__).resolve().parent.parent  # betting/

    # ─── Load schedules, filter to outdoor REG-season games ────────────────
    print(f"Loading schedules {args.since}-{args.until or 'current'}...")
    all_seasons = list(range(args.since, (args.until or 2026) + 1))
    sched = nfl.load_schedules(all_seasons).to_pandas()
    sched = sched[(sched["game_type"] == "REG") & (sched["roof"].isin(["outdoors", "open"]))].copy()
    # Exclude games that haven't been played yet (future schedule rows have NaN result).
    # Weather data only exists for past games; skip the future to avoid noisy "no-data" warnings.
    sched = sched[sched["result"].notna()].copy()
    if args.until is None:
        args.until = int(sched["season"].max())
    print(f"  {len(sched):,} played outdoor REG games ({args.since}-{args.until})")

    # ─── One-time station lookup per stadium ───────────────────────────────
    unique_sids = sorted(sched["stadium_id"].dropna().unique())
    print(f"\nResolving weather stations for {len(unique_sids)} stadiums...")
    candidates_for: dict[str, list[tuple[str, str]]] = {}  # stadium_id -> list of (station_id, name)
    missing_stadiums = []
    for sid in unique_sids:
        coord = STADIUM_COORDS.get(sid)
        if coord is None:
            missing_stadiums.append(sid)
            continue
        lat, lon, tz, label = coord
        try:
            cands = find_station_candidates(lat, lon)
            candidates_for[sid] = cands
            primary_id, primary_name = cands[0]
            print(f"  {sid} → {primary_id} ({primary_name[:48]:48}) | {len(cands)} candidates | {label}")
        except Exception as e:
            print(f"  {sid} → ERROR: {e}")
    if missing_stadiums:
        print(f"\n  ⚠️ Stadium IDs missing from STADIUM_COORDS: {missing_stadiums}")
        print("     Add them to STADIUM_COORDS and re-run.")

    # ─── Fetch per-game weather ────────────────────────────────────────────
    rows = []
    n_total = len(sched)
    n_skipped = 0
    n_no_station = 0
    n_no_data = 0
    n_no_time = 0
    print(f"\nFetching weather for {n_total} games...")
    n_fallback = 0
    for i, g in enumerate(sched.itertuples(index=False), 1):
        if i % 200 == 0:
            print(f"  [{i}/{n_total}] ...")
        sid = g.stadium_id
        if sid not in candidates_for:
            n_no_station += 1
            continue
        kickoff_utc = kickoff_to_utc(g.gameday, g.gametime)
        if kickoff_utc is None:
            n_no_time += 1
            continue
        # Try primary station, then fallbacks in order. Most games hit on the first.
        wx = None
        station_id = None
        station_name = None
        for cand_idx, (cand_id, cand_name) in enumerate(candidates_for[sid]):
            wx = fetch_weather(cand_id, kickoff_utc)
            if wx is not None:
                station_id, station_name = cand_id, cand_name
                if cand_idx > 0:
                    n_fallback += 1
                break
        if wx is None:
            n_no_data += 1
            continue
        rows.append({
            "game_id":      g.game_id,
            "stadium_id":   sid,
            "kickoff_utc":  kickoff_utc.isoformat(),
            "station_id":   station_id,
            "station_name": station_name,
            "temp_f":       c_to_f(wx["temp_c"]),
            "wind_mph":     kmh_to_mph(wx["wspd_kmh"]),
            "precip_in":    mm_to_in(wx["prcp_mm"]),
            "humidity_pct": wx["rhum"] if not pd.isna(wx["rhum"]) else None,
            "source":       "meteostat",
        })

    # ─── Write CSV ─────────────────────────────────────────────────────────
    df = pd.DataFrame(rows)
    if args.out:
        out_path = Path(args.out)
    else:
        out_path = out_dir / f"nfl_weather_{args.since}_{args.until}.csv"
    df.to_csv(out_path, index=False)
    print(f"\nWrote {len(df):,} rows → {out_path}")
    print(f"Summary: total={n_total}, kept={len(df)}, "
          f"skipped no-station={n_no_station}, no-time={n_no_time}, no-meteostat-data={n_no_data}, "
          f"fallback-station-used={n_fallback}")


if __name__ == "__main__":
    main()
