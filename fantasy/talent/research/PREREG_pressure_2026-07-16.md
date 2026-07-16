# PRE-REGISTRATION — QB pressure-facet screen (2026-07-16)

Written to disk BEFORE any screening computation runs. One screen, one report.
This file is the decision rule; results are appended below it afterward and the
rules above the results line are never edited.

## Blindness disclosure

This screen is blind BY CONSTRUCTION: no benchmark card is computed, read, or
referenced anywhere in the arc; no output names a player; facet-level statistics
only. The candidate family comes from the LEDGER (the sackAvoid HOLD and the QB
construct-gap list recorded before any of this session's results existed), not
from any player's standing on any board. The author has seen the R29 card (ARC A,
this session) — mitigation: the screen's gates and constructs below are inherited
verbatim from the standing six-gate convention and the ledger's HOLD note; no
numeric choice in this prereg is new.

## Motivation (from the record)

The ledger names the QB construct gaps as pressure performance, off-script
creation, and pre-snap work. sackAvoid (sacks/dropback) passed gates in the
prototype hunt but was HELD as line-confounded: "the clean construct is
sacks-per-pressure, needing a pbp-sacks <-> PFR-pressure join. Unbuilt." This
screen builds that join and tests that family.

## Candidate facets (exactly these three; no additions, substitutions, or variants)

- **F1 sacks-per-pressure (inv)** — sacks / times_pressured, inverted: pocket
  management given pressure. Numerator: nflfastR PBP sack outcomes attributed to
  the passer (gsis). Denominator: PFR advstats season pressure counts. Join: gsis
  identity crosswalk ONLY.
- **F2 pressure-rate-allowed (inv)** — times_pressured / dropbacks, inverted.
  DECLARED SUSPECT in advance: heavily line-confounded and QB has no gamma to
  strip situation. Expected to fail the construct check; screened for
  completeness. CONSTRUCT CHECK (declared now): persistence split
  movers-vs-stayers — QBs whose team changes between adjacent seasons vs those
  who stay. A line-owned stat persists for stayers and collapses for movers; a
  QB-owned stat persists for both. A movers' persistence collapse (relative gap
  > half the stayers' value, with the n's printed) = construct FAIL.
- **F3 pocket_time (PFR)** — if season-level coverage exists. EXPLORATORY: if
  coverage fails Gate 1 it dies there without substitution.

## The six gates (the pass bar; verbatim from the standing convention)

1. **Coverage MEASURED** per player on the R4 complete-case universe (n=145),
   differential coverage checked by dropback-volume tier; corr(coverage, w)
   printed. The RYOE precedent (differential coverage by player type) is the
   failure shape.
2. **Per-opportunity**, never volume.
3. **Persistence**: rho_obs >= 0.10 AND rho_true >= 0.30, reliability evaluated
   at the pairs' OWN n. Season-grain reliability for the F-family is estimated
   binomially (declared now): rel = var_between / (var_between + mean(p(1-p)/n_press)).
   If disattenuation breaks (|rho_true| > 1 — five prior breaks: 1.08, 2.53,
   1.38, PBP, college screen): DIAGNOSE, never clip, and UNMEASURABLE IS NOT
   PASSED.
4. **Redundancy**: |rho| < 0.70 vs ALL FIVE incumbent QB facets AND vs each
   other, SCORED universe (R7 convention), raw values, Pearson, n + 95% CI per
   cell; a CI straddling 0.70 is reported indeterminate.
5. **Retention ratio**: reported as a workload map only — RETIRED as a gate.
6. **KSS-equivalent**: MoM split-half sigma^2_alpha > 0 at NS=60 (per-facet
   isolated child streams, root seed 20260716); quartet reported — median, mean,
   cs.std (sigma^2 scale), CV (denominator = mean, sigma^2 scale), %<=0 with
   binomial SE, split count.

## Committed consequence

A facet passing ALL gates is reported **ADMISSIBLE** — admission itself is the
owner's ruling, with a weight he sets on football logic; nothing is wired into
the composite by this screen. A facet failing ANY gate is **OUT**, reported with
the failing gate and its number. No re-screening, no threshold adjustment, no
variant substitution after seeing results. One screen, one report.
