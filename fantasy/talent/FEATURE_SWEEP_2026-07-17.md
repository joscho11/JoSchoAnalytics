# FEATURE SWEEP — athletic / age / breakout / age-adjusted production vs alpha-hat
**Run 2026-07-18** (file keeps the commissioned name). Exploratory measurement sweep —
**ships nothing, ratifies nothing, pre-registers nothing.** A search maximum is a hypothesis;
confirming one requires its own pre-registered one-shot. No draft capital, draft round, or any
market-derived feature appears in any model (Joseph's ruling). Harness:
`scratchpad/sweep.py` → `sweep_results.pkl`; target = alpha-hat from `C:/tmp/S2.pkl`
(md5 `9b3d9df67ae88272f4eab0a0ae1cbb21`), R8 disattenuation (`rc = rawPearson/√mean(wt)`),
same estimator as the fired PREREG_pbp_index numbers — directly comparable to .474/.086/.312.

## The anti-mining design (what the three numbers mean)
- **NAIVE-MAX** — best candidate's in-sample disatt: the mining ceiling, reference only.
- **HONEST** — nested CV, leave-one-final-season-out (8 outer folds); ALL selection (combo,
  transform, penalty) happens inside each outer fold on training seasons only; the headline is
  the pooled out-of-fold disatt. **This is the number to decide on.**
- **NOISE-FLOOR** — the IDENTICAL search run on 20 target-shuffled copies, reported as the mean
  of the shuffled searches' naive-maxima: what this search manufactures from pure noise. It is a
  deliberately harsh bar (an in-sample max over ~700-850 candidates); only the mean was stored
  (as registered) — a margin of a few hundredths over it is NOT "clearly beyond noise."

Search space (frozen; identical for the shuffles): all size-1..3 subsets of the pool as
sign-primed equal-weight z-composites (~700-850 combos/position) + ridge + lasso on the full
pool with inner-CV penalties. Sign priors (composites only): forty, sack%, final_age,
breakout_age negated.

## Feature families + coverage (per clean panel)
- **Existing facets** (the baseline to beat): PBP career rates (RB EPA/rush·success·explosive;
  WR/TE EPA/tgt·success·catch%·explosive_rec; QB EPA/db·success·sack%·comp% + rushEPA·rush_expl
  ≥20 carries) + box (dom_best, recshare, ypr, ypc). ~97-100% coverage.
- **Athletic** (nflverse combine, 2017-2024, name-join, 21/2,742 duplicate keys dropped-first):
  matched 77-80%; forty 60-64%, vertical 62-64%, broad 57-63%, wt/ht 76-80%. **cone/shuttle/
  bench EXCLUDED — 34-48% coverage** (a result on a third of a panel is uninterpretable).
  Derived: speed_score, burst (vert+broad), ht_in. **~20-23% of every panel has ZERO athletic
  data**; missingness indicators are NOT features (combine invitation ≈ market opinion).
- **Age** (nflverse players birth_date, gsis-exact join): **100% coverage**, all positions.
  final_age = age at Sept-1 of final college season.
- **Breakout age**: first college season with dominator ≥ 0.20 (QB: first season ≥150
  dropbacks); never-broke-out → encoded 25.0 (declared semantic encoding, both runs).
- **Age-adjusted production**: dom_best minus final-age-cohort mean (within panel).

Two runs per position: **headline = full panel, athletic mean-imputed** (declared; imputation
dilutes athletic effects toward zero) and **complete-cases** (forty+vert+broad+wt+ht present —
~50-60% of panel, combine-invited subset = range-restricted and selection-biased; neither run
is unambiguously "more honest," so both are reported).

## RB (n=300; CC n=158; 1/√meanw = 2.20)
| NAIVE-MAX | HONEST | NOISE-FLOOR |
|---|---|---|
| +0.621 | **+0.266** (raw +0.121, Spearman +0.168) | +0.515 |
CC: HONEST +0.327 (n=158), CC floor +0.552. Fold winners: 7 distinct combos in 8 folds
(success+ypc+burst ×2, rest singletons) — **unstable, not a finding**.
**VERDICT: NO SIGNAL — HONEST is deep inside the noise floor,** and far below the shipping
PBP-index baseline (.474 disatt, pre-specified, fired). New families add nothing at RB.

## WR (n=308; CC n=187; 1/√meanw = 2.40)
| NAIVE-MAX | HONEST | NOISE-FLOOR |
|---|---|---|
| +0.666 | **+0.001** (raw +0.000, Spearman +0.085) | +0.522 |
CC: HONEST +0.208 (n=187), CC floor +0.580. Fold winners: catch%+dom_best+vertical ×3,
Ridge ×2, catch%+vertical ×2 — moderately repetitive, but the OOF value is zero.
**VERDICT: NO SIGNAL.** No honest combination beat the prior WR best (.086); the WR
college→NFL-talent link stays dead (now across box-score, PBP, athletic, age, and breakout
families — the fourth and fifth feature families to die at WR).

## TE (n=133; CC n=76; 1/√meanw = 1.89)
| NAIVE-MAX | HONEST | NOISE-FLOOR |
|---|---|---|
| +0.761 | **+0.204** (raw +0.108, Spearman +0.060) | +0.583 |
CC: HONEST +0.112 (n=76), CC floor +0.732. Fold winners: explosive_rec+speed_score+ht_in ×3,
variants otherwise. **VERDICT: NO SIGNAL** — below the prior TE best (.312) and deep inside
the floor. Small-n TE noise-floors (~.58-.73) mean almost nothing could clear them at n=133.

## QB (n=88; CC n=43; 1/√meanw = 1.50) — the QB blind's one pass, spent here
QB alpha-hat: S2 `W["QB"]` {cpoe .35, bad .25, qsucc .25, q10 .15}, per-facet reliability =
the frames' stored MoM `w` (S2 QB frames carry `w` directly; QU has no QB entries — declared
before any QB value was read). Passer "incomplete"-token rows dropped (~2.6-4.1%, 2022-24).
**MDE at n=88: raw r ≈ .302 → disatt ≈ .454 (80% power)** — a null below that is
"no large effect," not "no effect."
| NAIVE-MAX | HONEST | NOISE-FLOOR |
|---|---|---|
| +0.908 | **+0.525** (raw +0.349, Spearman +0.382) | +0.494 |
CC: HONEST +0.232 (n=43), CC floor +0.681. Fold winners: **rushEPA+final_age variants in 7/8
folds** (rushEPA+forty+final_age ×3, rushEPA+final_age ×2, rushEPA+speed_score+final_age ×2) —
the most stable selection of the sweep: *college rushing efficiency + younger final age*.
**VERDICT: NOT clearly beyond noise — hypothesis-grade only.** HONEST sits +0.031 above the
noise-floor MEAN; the floor is a mean of maxima with substantial shuffle-to-shuffle spread, so
this margin does not meet "clearly exceeds." Points against: CC collapses to +0.232; n=88 with
MDE ≈ .454 disatt means the whole read is fragile; QB alpha-hat is the UNADJUSTED estimand (no
team/opponent correction — one starter per team). Points for: fold-stable winner with a
plausible mechanism (mobile, young QBs), raw Pearson .349 > MDE .302. **If Joseph wants to
pursue QB, the registered path is a fresh pre-registered one-shot of the SPECIFIC frozen
composite (rushEPA + final_age, equal-weight z) — not a re-search.** A 2026-class QB score
could not ship regardless: 2025 passer parse is 57.9% clean; the 2026 rookie-QB scored
universe is 2 players (Mendoza, Simpson — R31 build log).

## Summary — highest HONEST per position vs prior best
| pos | prior best (instrument) | sweep HONEST | Δ | vs bands | verdict |
|---|---|---|---|---|---|
| RB | **.474** (PBP SEL, fired) | .266 | −.208 | below .35 | NO SIGNAL; keep PBP index |
| WR | .086 (PBP, fired) | .001 (CC .208) | −.085 | below .35 | NO SIGNAL; WR stays dead |
| TE | .312 (PBP, fired) | .204 | −.108 | below .35 | NO SIGNAL; TE stays dead |
| QB | — (none) | .525 | — | nominally ≥.50 — but a SEARCHED value at the noise floor; bands apply to pre-specified instruments, not search maxima | hypothesis-grade; needs its own one-shot |

**No position's honest value beat its prior best.** The new families (athletic, age, breakout,
age-adjusted production) added nothing over the existing facets at RB/WR/TE; at QB the
stable winner is dominated by an EXISTING facet (rushEPA) plus age. **The mining tax
(NAIVE-MAX − HONEST): RB −.355, WR −.665, TE −.557, QB −.383** — this search fabricates
in-sample disatts of .5-.9 from pure noise (the floors), which is exactly why no naive number
here may ever be quoted as a result.
