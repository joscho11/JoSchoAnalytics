"""DATE PROVENANCE — honest uncertainty for every source date.

An eligibility gate is only as good as the dates feeding it. Encoding an uncertain date as the first
day of its month or year manufactures precision that does not exist, and in this project it twice
manufactured it in the direction that granted FALSE preseason eligibility:

  yardbarker2021  placeholder 2021-01-01  ->  audited byline "Updated October 18, 2021"  POST-CUTOFF
  espn2025        inferred    2025-08-01  ->  audited byline "Sep 9, 2025, 06:00 AM ET"  POST-CUTOFF

Every source therefore carries a precision class and a CONSERVATIVE UPPER BOUND. Eligibility is
decided on the upper bound, never on a midpoint or a fabricated day:

  exact_day  eligible iff date            <= cutoff
  month      eligible iff last day of month <= cutoff
  year       eligible iff Dec 31 of year    <= cutoff
  missing    NEVER eligible without separate dated evidence
  inferred   NEVER eligible from the inferred value alone

`source_date` (publication) is NOT the same thing as `fact_known_date` (when the identity became
publicly knowable). A retrospective article can establish historical attribution while establishing
nothing about preseason knowability. Where a later article cites an earlier announcement, the
earlier announcement is captured as its own source with its own date -- the later article is never
backdated.
"""
import calendar
import datetime as _dt

EXACT, MONTH, YEAR, MISSING, INFERRED = "exact_day", "month", "year", "missing", "inferred"
BYLINE, PAGEMETA, ARCHIVE, CITED, INFERRED_PROV = (
    "page_byline", "page_metadata", "archive_metadata", "cited_announcement", "inferred")

# Sources whose stored date was NOT traceable to a byline or page metadata when first entered.
# Each was re-audited 2026-07-28; the outcome is recorded verbatim.
AUDIT = {
    "yardbarker2021": dict(
        raw="Updated October 18, 2021", date="2021-10-18", precision=EXACT, provenance=BYLINE,
        note="CORRECTED from a fabricated placeholder 2021-01-01 that was entered when the first "
             "fetch returned no date. The placeholder falsely implied preseason eligibility."),
    "espn2023": dict(
        raw="Aug 23, 2023, 06:32 AM ET", date="2023-08-23", precision=EXACT, provenance=BYLINE,
        note="CORRECTED from an inferred 2023-08-01. Eligibility verdict unchanged (pre-cutoff)."),
    "espn2024": dict(
        raw="Aug 30, 2024, 06:00 AM ET", date="2024-08-30", precision=EXACT, provenance=BYLINE,
        note="CORRECTED from an inferred 2024-08-01. Eligibility verdict unchanged (pre-cutoff)."),
    "espn2025": dict(
        raw="NFL Nation Sep 9, 2025, 06:00 AM ET", date="2025-09-09", precision=EXACT,
        provenance=BYLINE,
        note="CORRECTED from an inferred 2025-08-01. Verdict CHANGED: the real byline is AFTER the "
             "2025 cutoff (2025-09-03), so this source cannot establish preseason eligibility."),
    "cbs2022phi": dict(
        raw=None, date=None, precision=MISSING, provenance=INFERRED_PROV,
        note="Stored 2022-01-01 was an inferred placeholder; no byline was ever captured. Treated "
             "as MISSING -> never eligible without separate dated evidence. It remains valid as "
             "historical attribution evidence (it is a CONFLICT marker, not an attribution)."),
    "fox2015gb": dict(
        raw=None, date=None, precision=MISSING, provenance=INFERRED_PROV,
        note="Stored 2015-01-01 was an inferred placeholder (article date not captured)."),
    "nfl2016gb": dict(
        raw=None, date=None, precision=MISSING, provenance=INFERRED_PROV,
        note="Stored 2016-08-01 was an inferred placeholder (article date not captured)."),
}

# Any stored date matching these patterns is treated as an inferred placeholder unless AUDIT
# overrides it, because they are the values a human types when the real date is unknown.
PLACEHOLDER_SUFFIXES = ("-01-01", "-08-01")


def classify(source_key, stored_date):
    """Return the provenance record for a source's date."""
    if source_key in AUDIT:
        a = AUDIT[source_key]
        return dict(source_date_raw=a["raw"], source_date=a["date"],
                    source_date_precision=a["precision"],
                    source_date_provenance=a["provenance"], source_date_note=a["note"])
    if not stored_date:
        return dict(source_date_raw=None, source_date=None, source_date_precision=MISSING,
                    source_date_provenance=INFERRED_PROV,
                    source_date_note="no date recorded for this source")
    if any(str(stored_date).endswith(sfx) for sfx in PLACEHOLDER_SUFFIXES):
        return dict(source_date_raw=str(stored_date), source_date=None,
                    source_date_precision=INFERRED, source_date_provenance=INFERRED_PROV,
                    source_date_note="stored value matches a placeholder pattern and was not "
                                     "traced to a byline; treated as inferred -> never eligible")
    return dict(source_date_raw=str(stored_date), source_date=str(stored_date),
                source_date_precision=EXACT, source_date_provenance=BYLINE,
                source_date_note="full date established from the article byline or page metadata "
                                 "at the time the source was read")


def bounds(date_str, precision):
    """Conservative [lower, upper] window. Eligibility uses the UPPER bound."""
    if not date_str or precision in (MISSING, INFERRED):
        return None, None
    d = _dt.date.fromisoformat(str(date_str)[:10])
    if precision == EXACT:
        return d.isoformat(), d.isoformat()
    if precision == MONTH:
        last = calendar.monthrange(d.year, d.month)[1]
        return d.replace(day=1).isoformat(), d.replace(day=last).isoformat()
    if precision == YEAR:
        return _dt.date(d.year, 1, 1).isoformat(), _dt.date(d.year, 12, 31).isoformat()
    return None, None


def eligible_at(upper_bound, cutoff):
    """Eligible only when the conservative UPPER bound is on or before the cutoff."""
    if not upper_bound or not cutoff:
        return False
    return _dt.date.fromisoformat(str(upper_bound)[:10]) <= _dt.date.fromisoformat(str(cutoff)[:10])
