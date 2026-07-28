# U1 fantasy/talent — Lens A (correctness/data integrity)

- U1A-1 - composite.py:17,68 - norm_simple fallback vs _utils.norm_name primary
  (build_rookie_score.py:26) - TWO NAME NORMALIZERS in one join family; the fallback
  fires only when season_dataset lacks a player's norm_name - LOW - SMELL -
  invariant-screened: T9 (joins exact-name by design, no substring) - action:
  unify only as a GATED change (pipe-join behavior path).
- U1A-2 - facets.py brk() merge (prc<->psw on gsis/season/week) - cardinality safe
  today (PFR weekly rows unique per player-week) - LOW - RISK - screened T1/T9 -
  action: duplicate-key assert if ever touched (GATED neighborhood).
- Artifact-write scan: only stage_emit/write_artifact write CSVs, both under
  fantasy/talent/; NO code path writes a frozen artifact, tracker, or pkl. Verified.

Coverage: 11/11 unit files read or taxonomy-grepped. NO FINDINGS of severity >= HIGH.
