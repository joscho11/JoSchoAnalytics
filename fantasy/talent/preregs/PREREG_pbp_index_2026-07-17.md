# PRE-REGISTRATION — version-pinned PBP college index vs NFL talent construct
**Date:** 2026-07-17 · **Status at commit: BLIND** (no college value has been related to any
NFL value; alpha-hat values are UNREAD until the fire). One-shot. Joseph has delegated
ratification; the commissioning prompt is the sign-off.

This is a **fresh pre-registration**, not a re-run. It exists because the registered PBP rho
(WR disatt 0.376, n=331; `rho_provenance.json`) was found **doubly defective**: (1) measured on
a mixed/unrecorded cfbfastR EP-model bake, and (2) on a panel where **127 of 331 WRs (38%) were
scored on wrong-window truncated careers** — `cfb_screen.py` `career()` never enforced the
final-season condition its stdout claimed. The 0.376 is retired as a benchmark; the **committed
bands** are the law.

## HYPOTHESIS
A version-pinned (cfbfastR 2.0.0), true-final-season, FBS-scoped college PBP index tracks the
NFL talent construct (alpha-hat) at a band-relevant level for RB, WR, and/or TE.

## INSTRUMENT (frozen)
`cfb_build_v2` facets from `scratchpad/cfbd_cache/` — cfbfastR 2.0.0, R 4.6.1, pinned.
- cache provenance: `scratchpad/cfbd_cache/provenance.json` md5 `1ba5cff696edf2f10dcab577f3488310`
- facet definitions IDENTICAL to frozen `cfb_build.py` L9-19 + `cfb_screen.py` L10-16 (copied
  with line-cited provenance in `cfb_build_v2.py`; smoke-tested .991-.999 vs the mirror on
  non-EPA facets, all 5 reference seasons).

## PANEL (frozen)
FBS-school players; **TRUE final college season 2016-2023**; full careers from the cache;
positions RB/WR/TE. Built value-free and frozen in `scratchpad/panel_fire.pkl` md5
`0c6f1e15a7bd534fa25c0bd10ab21c3e`.
- **n: RB 300 · WR 308 · TE 133.** (Diagnostic expectation RB~309/WR~320/TE~136; within 3-4%.)
- thresholds (`cfb_screen.py:13`): career **RB ≥40 carries · WR/TE ≥30 targets**.
- join: `_utils.norm_name` exact match to the alpha-hat artifact index.
- **QB: OUT OF SCOPE.** No QB rookie instrument ships; the passer "incomplete"-token artifact
  (2.6-4.1%, 2022-24) is documented; nothing here rules on QB.

## ALPHA-HAT ARTIFACT (values UNREAD until the fire)
`C:/tmp/S2.pkl` md5 `9b3d9df67ae88272f4eab0a0ae1cbb21` (== SPEC.md Class-B pin). Key: `gsis_id`.
Position source: nflverse modal position (`s2.py:32-33`). alpha-hat = unshrunk composite
`aw = Σ_f W[P][f]·zmed_f`; reliability `wt = Σ_f W[P][f]·wn_f / Σ W`, `wn = ne/(ne+knew)`,
`knew = kold·(sam/sad)²` — reproduced verbatim from `cfb_rho.py` L9-19. Membership (index+`ne`)
was read to build the panel; **no alpha value was read**.

## SCOPE RULES (registered)
- **FBS-school players only** (team ≥7 distinct games as pos_team in a single 2016-2021 cache
  season → 131 teams). FCS-school players EXCLUDED from pool and panel (listed in OUTCOMES).
- **FBS-vs-FCS games INCLUDED** (FBS production is real); FCS-vs-FCS excluded by the FBS filter.
- **2020 included as-is** (career pooling absorbs the short season; 2020-final players in-panel).
- **2024 finals excluded** from validation (one thin NFL season); detected via any 2024 college
  appearance (rusher/receiver clean at 100%/99.4% in 2024). **2025 excluded** (parser collapse,
  56.8%/57.9%; scoring-only later).
- **Passer "incomplete"-token rows are irrelevant here:** no RB/WR/TE facet consumes
  `passer_player_name` (RB=rusher, WR/TE=receiver — verified in `cfb_build_v2.game_agg`). Stated.

## Z-RULE (registered)
Pooled career z over the **scoped qualifying population** (FBS, true-final ≤2023, ≥MINV), one z
per career, per facet, equal-weight composite over the SEL set (`cfb_rho.py:22-26`):
RB = [EPA/rush, explosive]; WR/TE (REC) = [EPA/tgt, catch%, explosive_rec]. Scoped pool sizes:
RB 1569 · REC 2410 qualifying careers.

## MEASUREMENT (registered)
Per position, rho = corr(index, alpha-hat) over panel members with wt>0 and both non-null,
**disattenuated by the R8 estimator** `rc = raw_Pearson / sqrt(mean(wt))` (`cfb_rho.py:42`).
Raw Pearson and Spearman reported alongside, **NON-GATING**.

## BOTH INSTRUMENTS, ONE RUN
On this SAME panel, same join, same estimator, measure BOTH: (i) the fresh **PBP index**
(above); (ii) the **box-score index** exactly as `build_rookie_score.py` computes it with the
**R31 weights** (RB {dom_best .50, ypc .50} · WR {.80/.00/.20} · TE {equal}), from
`college_production_2014_2024.csv` md5 `a6068710b3122a222fbb0c165bbed871`, z within the panel.

## SUPERSESSION (registered in advance)
These same-panel numbers **REPLACE** the old-panel box baselines (RB .385 / WR .000 / TE .254)
for band placement. The old numbers came from the defective panel and retire with it. This puts
the shipping RB box-score pipe at risk — that is the point of measuring honestly.

## SHIP RULES (decided now, applied mechanically)
Bands (`rho_provenance.json:7`, pre-registered, this instrument family): **≥.50 ships clean /
.35-.50 ships weak-disclosed / <.35 dead.**
- **WR, TE** (box currently dead per R10): PBP ships at its band if ≥.35; if <.35 the position is
  dead-on-PBP and the box-score column stands or falls on its OWN same-panel band.
- **RB** (box currently shipping): **PBP REPLACES box only if PBP_disatt − BS_disatt ≥ +.05 AND
  PBP ≥ .35.** Otherwise the pipe stays box-score AT ITS SAME-PANEL BAND — including dead.

## ONE SHOT
One run. No metric substitutions, no panel re-cuts, no subgroup rescues, no second estimator
promoted after results. A crash is not a result; a completed run's numbers are final.
Fire script: `scratchpad/fire_pbp_rho.py` sha256 `acaabb2b43f05eb0985a9214c157f7aac771c0e6f6e3e88ac67a22d3d5cb3dd8`, run exactly once.

## BLINDNESS DISCLOSURE
Everything seen across sessions A + the diagnostics, none of which related a college value to an
NFL value: (a) parity Spearmans CFBD-vs-mirror on non-EPA facets (.991-.999) and EPA-derived
(.65-.97); (b) parser clean-rates per season/role; (c) qualifying-pool counts per season
(527→760 FCS jump); (d) census cardinalities (membership + names only); (e) the 207-vs-331
reconciliation (membership only); (f) value-level college-vs-college facet means/sds (2022). No
alpha-hat VALUE was read in any of it. **The blind is spent by THIS run only.**

## OUTCOMES (recorded after the fact; rules above were not modified)
Fired once, 2026-07-17, `fire_pbp_rho.py` sha256 acaabb2b… → `fire_results.pkl`.
Per position, both instruments, R8 disattenuated (`rc = rawPearson / sqrt(mean wt)`):

| pos | instr | n | rawPearson | Spearman | w-wt | DISATT | band |
|---|---|---|---|---|---|---|---|
| RB | PBP | 300 | +0.215 | +0.208 | +0.113 | **+0.474** | WEAK-DISCLOSED (.35-.50) |
| RB | BOX | 297 | +0.135 | +0.254 | +0.262 | **+0.298** | DEAD (<.35) |
| WR | PBP | 308 | +0.036 | +0.091 | +0.298 | **+0.086** | DEAD (<.35) |
| WR | BOX | 303 | +0.012 | −0.009 | +0.092 | **+0.028** | DEAD (<.35) |
| TE | PBP | 133 | +0.165 | +0.172 | +0.123 | **+0.312** | DEAD (<.35) |
| TE | BOX | 133 | +0.157 | +0.168 | +0.203 | **+0.295** | DEAD (<.35) |

SHIP VERDICTS (ship rules applied mechanically):
- **RB: PBP index SHIPS WEAK-DISCLOSED, REPLACING the box-score pipe** (PBP .474 ≥ .35 AND
  PBP−BOX = +0.176 ≥ +.05).
- **WR: DEAD on both** (PBP .086, BOX .028). PBP dead; box-score WR falls to its own same-panel
  band = DEAD.
- **TE: DEAD on both** (PBP .312, BOX .295). PBP dead; box-score TE falls to its own same-panel
  band = DEAD.

SUPERSESSION (as pre-registered): the old-panel box baselines are retired. Same-panel box:
RB .385→**.298 (DEAD)** · WR .000→**.028 (DEAD)** · TE .254→**.295 (DEAD)**. The shipping RB
box-score pipe did NOT survive its own clean re-measure; RB is carried by the PBP index instead.
DEPLOYMENT ASTERISK: no 2026-class scoring occurs here; RB deployment (rusher parse clean 2025)
is a future session; WR/TE remain dead and unchanged. One shot spent. Campaign result recorded.
