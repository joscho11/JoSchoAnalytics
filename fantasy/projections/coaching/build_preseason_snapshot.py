"""PHASE 1C — split the retrospective ledger from the point-in-time snapshot.

Two PHYSICALLY SEPARATE artifacts, because one file holding both invites leakage by autocomplete:

  retrospective_staff_transitions.csv   historical attribution ONLY. Actual opening/closing caller,
                                       actual within-season changes, realized exposures. Never a
                                       season-Y feature source.

  preseason_staff_snapshot.csv         ONLY what was knowable at season Y's projection cutoff.
                                       Contains no closing identity, no eventual primary caller, no
                                       realized change, no realized exposure share.

PROJECTION CUTOFF (frozen, prereg v3.4). The production projection builders record NO as-of date --
verified by grepping `as_of|asof|cutoff|snapshot_date|projection_date` across all four position
builders and build_season_dataset.py, which returns nothing. The frozen rule is therefore the
maximal-preseason fallback: **the day before season Y's first regular-season game**, computed from
the schedule, not a hand-typed September 1. (Sept 1 was only ever a diagnostic probe.) For the live
2026 deployment the actual production timestamp is used instead of a future Week-1 date.

ELIGIBILITY. A retrospective article can establish that X called plays in year Y while establishing
nothing about whether that was knowable BEFORE Y. So publication date and fact-known date are
tracked separately:

  - `source_date` is when the attributing article was published.
  - `fact_known_date` is when the identity became publicly established, taken from a preseason
    announcement when one has been researched.

A later article that CITES an earlier announcement does not backdate itself; the earlier
announcement is entered as its own source with its own date. Eligibility uses the CONSERVATIVE
UPPER BOUND of whichever qualifying evidence is earliest, so month-only and year-only dates can
only ever qualify when their LAST possible day still precedes the cutoff.
"""
import hashlib
import pathlib

import numpy as np
import pandas as pd

import date_provenance as DP
import playcaller_sources as SRC
try:
    import preseason_evidence as PE
except ImportError:                                        # evidence file optional
    class PE:                                              # noqa: D101
        PRESEASON_EVIDENCE = {}

HERE = pathlib.Path(__file__).resolve().parent
DATA = HERE / "data"

# Fields that may NEVER appear in the preseason snapshot. Asserted, not merely documented.
FORBIDDEN_IN_SNAPSHOT = [
    "closing_caller_id", "closing_hc_id", "historical_primary_caller_id",
    "pc_within_season_change", "hc_within_season_change",
    "caller_exposure", "realized_exposure", "n_games_attributed", "caller_known_share",
    # v3.5: the retrospective opener and the after-the-fact accuracy flag are AUDIT fields. They
    # live in the evidence ledger, never in the frame projection assembly consumes -- otherwise the
    # eventual answer is one join away from any feature builder.
    "retrospective_opening_caller_id", "expectation_matched_actual",
]


def projection_cutoffs():
    """Day before season Y's first REG game. 2026 uses the real production as-of date."""
    import nflreadpy as nfl
    s = nfl.load_schedules().to_pandas()
    s = s[s.game_type == "REG"].copy()
    s["gameday"] = pd.to_datetime(s["gameday"], errors="coerce")
    first = s.groupby("season")["gameday"].min()
    cut = (first - pd.Timedelta(days=1)).dt.date.astype(str).to_dict()
    # Live deployment: 2026 projections were produced 2026-07-21, well before Week 1.
    cut[2026] = "2026-07-21"
    return cut


def _source_dates():
    """source_url -> (key, upper_bound, precision).

    The canonical table carries `source_url`, not `source_key`, so provenance is joined by URL.
    Keying this by `source_key` silently matched nothing and reported 0% coverage for every season
    including ones whose audited byline clears the cutoff -- an artifact, not a finding.
    """
    out = {}
    for key, meta in {**SRC.SOURCES, **SRC.PARTIAL_SOURCES}.items():
        prov = DP.classify(key, meta.get("date"))
        _lo, hi = DP.bounds(prov["source_date"], prov["source_date_precision"])
        out[meta.get("url")] = (key, hi, prov["source_date_precision"])
    return out


AMBIGUOUS_PREFIX = "AMBIGUOUS"


def build_evidence_ledger(tbl, cutoffs):
    """TRUE AS-OF RULE (prereg v3.5). What did the model KNOW at the cutoff?

    The previous implementation was itself look-ahead leakage on two counts, both corrected here:

    1. It REJECTED qualifying pre-cutoff evidence naming caller A whenever the retrospective opener
       turned out to be B. That filters the snapshot down to expectations that later proved correct
       -- an oracle-filtered subset. At the cutoff, A *was* the information the model possessed.
    2. It could not assign an expected caller at all when retrospective attribution was unresolved,
       even where a pre-cutoff source explicitly named the expected caller.

    It also picked the EARLIEST eligible evidence, which is backwards for an as-of snapshot: the
    model knows the LATEST information published before the cutoff.

    The retrospective opener is now an AUDIT/VALIDATION field only. It never determines eligibility.
    `expectation_matched_actual` records whether the expectation later proved right; it is measured
    after the fact and is forbidden from the feature-eligible snapshot.
    """
    sd = _source_dates()
    tbl = tbl.copy()
    tbl["week_start"] = pd.to_numeric(tbl["week_start"], errors="coerce").fillna(1)
    openers = tbl.sort_values("week_start").groupby(["season", "team"], as_index=False).first()

    rows = []
    for _, r in openers.iterrows():
        season, team = int(r["season"]), r["team"]
        cutoff = cutoffs.get(season)
        actual = r["person_id"] if pd.notna(r["person_id"]) else None

        # ---- assemble the FULL pre-cutoff evidence pool -------------------------------------
        pool = []

        # (a) the attributing source, IF it was published before the cutoff. A pre-cutoff source
        #     that happens to name the eventual opener is legitimate preseason evidence.
        surl = r.get("source_url")
        skey, att_ub, att_prec = sd.get(surl, (None, None, "missing"))
        att_ok = DP.eligible_at(att_ub, cutoff)
        if att_ok and actual:
            pool.append(dict(person_id=actual, upper=att_ub, url=surl,
                             publisher=r.get("source_publisher"), raw_date=att_ub,
                             date=att_ub, precision=att_prec, source_class="attributing_source",
                             statement="Attributing source, published before the cutoff."))

        # (b) separately researched preseason evidence
        for it in [e for e in getattr(PE, "EVIDENCE", [])
                   if e["season"] == season and e["team"] == team]:
            _lo, hi = DP.bounds(it.get("date"), it.get("precision", "exact_day"))
            if DP.eligible_at(hi, cutoff):
                pool.append(dict(person_id=it.get("person_id"), upper=hi, url=it.get("url"),
                                 publisher=it.get("publisher"), raw_date=it.get("raw_date"),
                                 date=it.get("date"), precision=it.get("precision", "exact_day"),
                                 source_class=it.get("source_class"),
                                 statement=it.get("statement")))

        # ---- LATEST-INFORMATION RULE ---------------------------------------------------------
        expected, chosen, conflict = None, None, "none"
        if pool:
            latest = max(p["upper"] for p in pool)
            newest = [p for p in pool if p["upper"] == latest]
            names = {p["person_id"] for p in newest}
            if any(str(n).startswith(AMBIGUOUS_PREFIX) for n in names):
                conflict = "ambiguous_pre_cutoff_source"       # e.g. "Daboll/Kafka"
                chosen = newest[0]
            elif len(names) > 1:
                conflict = ("contemporaneous_pre_cutoff_disagreement: "
                            + "/".join(sorted(str(n) for n in names)))
                chosen = newest[0]
            else:
                chosen = newest[0]
                expected = chosen["person_id"]                  # later info SUPERSEDES earlier

        eligible = expected is not None
        # AUDIT ONLY. Never a feature. NA when the actual opener is unresolved.
        matched = (None if (actual is None or not eligible) else bool(expected == actual))

        if eligible:
            reason = None
        elif conflict != "none":
            reason = "pre_cutoff_ambiguity"
        elif actual is None and not pool:
            reason = "unresolved_historical_attribution"
        elif att_prec in ("inferred", "missing") and not pool:
            reason = "missing_or_uncertain_date"
        else:
            reason = "post_cutoff_evidence_only"

        rows.append(dict(
            season=season, team=team, projection_cutoff=cutoff,
            # ---- feature-eligible
            expected_opening_caller_id=expected,
            eligible_at_cutoff=eligible, unknown_reason=reason,
            # ---- evidence provenance
            fact_known_date=(chosen or {}).get("upper"),
            evidence_source_url=(chosen or {}).get("url"),
            evidence_publisher=(chosen or {}).get("publisher"),
            evidence_source_raw_date=(chosen or {}).get("raw_date"),
            evidence_source_date=(chosen or {}).get("date"),
            evidence_source_precision=(chosen or {}).get("precision"),
            evidence_source_upper_bound=(chosen or {}).get("upper"),
            evidence_source_class=(chosen or {}).get("source_class"),
            evidence_statement=(chosen or {}).get("statement"),
            conflict_status=conflict, n_evidence_items=len(pool),
            attributing_source_key=skey, attributing_source_upper_bound=att_ub,
            attributing_source_precision=att_prec, attributing_source_clears_cutoff=att_ok,
            recovered_by_targeted_research=bool(
                eligible and (chosen or {}).get("source_class") != "attributing_source"),
            # ---- research completeness (2019 pass)
            research_status=_research_status(season, team, eligible),
            research_complete=_research_complete(season, team, eligible),
            # ---- AUDIT / VALIDATION ONLY -- forbidden in the feature snapshot
            retrospective_opening_caller_id=actual,
            expectation_matched_actual=matched))
    return pd.DataFrame(rows).sort_values(["season", "team"]).reset_index(drop=True)


def _ra2019():
    try:
        import research_attempts_2019 as RA
        return RA
    except ImportError:
        return None


def _research_status(season, team, eligible):
    """Explicit disposition. 2019 rows carry a recorded one; elsewhere it is derived."""
    ra = _ra2019()
    if season == 2019 and ra and team in ra.DISPOSITIONS:
        return ra.DISPOSITIONS[team]["disposition"]
    return "recovered_eligible" if eligible else "not_individually_researched"


def _research_complete(season, team, eligible):
    ra = _ra2019()
    if season == 2019 and ra:
        return team in ra.DISPOSITIONS
    return bool(eligible)


def build_snapshot(ev, hc_openers):
    """Cutoff-eligible fields ONLY. Emits NA -- never 0 -- when identity is unavailable."""
    snap = ev[["season", "team", "projection_cutoff", "expected_opening_caller_id",
               "eligible_at_cutoff", "unknown_reason"]].copy()
    snap = snap.merge(hc_openers, on=["season", "team"], how="left")

    # Change flags compare season Y's ELIGIBLE expected opener against the identity that ended Y-1.
    # Y-1 is a COMPLETED season at the cutoff, so its closing identity is legitimately knowable.
    snap = snap.sort_values(["team", "season"])
    snap["prev_closing_caller_id"] = snap.groupby("team")["prev_season_closing_caller_id"].transform(
        lambda s: s)
    snap["pc_changed_entering"] = np.where(
        snap.expected_opening_caller_id.isna() | snap.prev_closing_caller_id.isna(),
        np.nan,
        (snap.expected_opening_caller_id != snap.prev_closing_caller_id).astype(float))
    snap["hc_changed_entering"] = np.where(
        snap.expected_opening_hc_id.isna() | snap.prev_closing_hc_id.isna(),
        np.nan,
        (snap.expected_opening_hc_id != snap.prev_closing_hc_id).astype(float))
    snap["caller_identity_unknown"] = snap.expected_opening_caller_id.isna().astype(int)
    snap["hc_identity_unknown"] = snap.expected_opening_hc_id.isna().astype(int)

    for c in FORBIDDEN_IN_SNAPSHOT:
        assert c not in snap.columns, f"LEAK: {c} must never reach the preseason snapshot"
    return snap.sort_values(["season", "team"]).reset_index(drop=True)


def md5(p):
    return hashlib.md5(pathlib.Path(p).read_bytes()).hexdigest()


def build():
    import build_exposure as BE

    tbl = pd.read_csv(DATA / "actual_play_caller.csv")
    hc = pd.read_csv(DATA / "head_coach_games.csv")
    gl = BE.game_level_identity(hc, tbl)
    cutoffs = projection_cutoffs()

    # ---------- A. RETROSPECTIVE (historical attribution only) ----------
    retro = BE.preseason_snapshot(gl)          # the old all-in-one frame
    retro.to_csv(DATA / "retrospective_staff_transitions.csv", index=False)

    # HC opener + the identities that ENDED the prior season (legitimately knowable at cutoff)
    hc_open = retro[["season", "team", "opening_hc_id", "closing_caller_id", "closing_hc_id"]].copy()
    hc_open = hc_open.rename(columns={"opening_hc_id": "expected_opening_hc_id"})
    hc_open = hc_open.sort_values(["team", "season"])
    hc_open["prev_season_closing_caller_id"] = hc_open.groupby("team")["closing_caller_id"].shift(1)
    hc_open["prev_closing_hc_id"] = hc_open.groupby("team")["closing_hc_id"].shift(1)
    hc_open = hc_open.drop(columns=["closing_caller_id", "closing_hc_id"])

    # ---------- B. EVIDENCE LEDGER + POINT-IN-TIME SNAPSHOT ----------
    ev = build_evidence_ledger(tbl, cutoffs)
    ev.to_csv(DATA / "preseason_evidence_ledger.csv", index=False)

    snap = build_snapshot(ev, hc_open)
    snap.to_csv(DATA / "preseason_staff_snapshot.csv", index=False)

    report(ev, snap)
    print(f"\nretrospective_staff_transitions.csv  md5 {md5(DATA/'retrospective_staff_transitions.csv')}")
    print(f"preseason_evidence_ledger.csv        md5 {md5(DATA/'preseason_evidence_ledger.csv')}")
    print(f"preseason_staff_snapshot.csv         md5 {md5(DATA/'preseason_staff_snapshot.csv')}")
    return ev, snap


def report(ev, snap):
    """POINT-IN-TIME coverage. This is NOT T0 -- T0 measures historical attribution only."""
    games = pd.read_csv(DATA / "head_coach_games.csv")
    gpt = games.groupby(["season", "team"])["game_id"].nunique().rename("team_games").reset_index()
    e = ev.merge(gpt, on=["season", "team"], how="left")

    print("=" * 96)
    print("POINT-IN-TIME COVERAGE AT THE FROZEN PROJECTION CUTOFF")
    print("(day before season Y's first regular-season game; 2026 = production as-of 2026-07-21)")
    print("NOT comparable to T0, which measures RETROSPECTIVE historical attribution.")
    print("=" * 96)

    rows = []
    for season, g in e.groupby("season"):
        n = len(g)
        elig = int(g.eligible_at_cutoff.sum())
        gm = int(g.loc[g.eligible_at_cutoff, "team_games"].sum())
        tot = int(g.team_games.sum())
        vc = g.unknown_reason.value_counts()
        rows.append(dict(
            season=int(season), team_seasons=n, eligible_caller=elig,
            row_cov_pct=round(100 * elig / n, 1),
            game_cov_pct=round(100 * gm / tot, 1) if tot else np.nan,
            unk_unresolved=int(vc.get("unresolved_historical_attribution", 0)),
            unk_post_cutoff=int(vc.get("post_cutoff_evidence_only", 0)),
            unk_bad_date=int(vc.get("missing_or_uncertain_date", 0)),
            recovered=int(g.recovered_by_targeted_research.sum())))
    rep = pd.DataFrame(rows)
    print(rep.to_string(index=False))

    outer = e[e.season.between(2018, 2025)]
    print(f"\nOUTER 2018-2025 point-in-time caller coverage: "
          f"{int(outer.eligible_at_cutoff.sum())}/{len(outer)} rows "
          f"({100*outer.eligible_at_cutoff.mean():.1f}%)")
    print("UNKNOWN reasons (outer):")
    print(outer.unknown_reason.value_counts(dropna=False).to_string())
    hc_ok = snap[snap.season.between(2018, 2025)].expected_opening_hc_id.notna().mean()
    print(f"\nexpected HC identity available (outer): {100*hc_ok:.1f}%")
    print(f"recovered by targeted pre-cutoff research: {int(e.recovered_by_targeted_research.sum())}")
    rep.to_csv(DATA / "point_in_time_coverage.csv", index=False)
    return rep


if __name__ == "__main__":
    build()
