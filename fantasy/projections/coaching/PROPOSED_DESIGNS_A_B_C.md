# Proposed designs A / B / C — DRAFTED, NOT EXECUTED

**Nothing here is authorized.** No arm below has been fit. Each requires Joseph's approval; design C
additionally requires a separate PREFIT prereg amendment before it may touch any model.

The governing constraint stands: **a diluted or null caller arm must not be interpreted as evidence
that coaching lacks signal.** Telling "no signal" apart from "no identity" is the entire reason A, B
and C are run as a set rather than A alone.

---

## Design A — ARCHIVE-VERIFIABLE POINT-IN-TIME BACKTEST

**Question.** Does play-caller identity improve player-level season-total projections, *restricted to
identities the surviving cited archive can currently prove were publicly available before the
season began*?

**What this is NOT.** It is **not** a measure of live deployment coverage, and it is not "the
deployable headline". It measures **what the surviving cited archive can currently prove**, which is
a property of archive retrievability in 2026, not of what a 2019 or 2020 analyst could actually have
known. Two distinct limitations are folded into its coverage number:

1. genuinely unknowable-at-the-time identities, and
2. identities that *were* public at the time but whose evidence is now paywalled, unindexed, or
   deleted.

A cannot separate those. **The live 2026 snapshot has 100% caller coverage**, which is direct
evidence that present-day play-caller identity is fully available at projection time — the coverage
shortfall below is a historical-archive artifact, not a statement about deploying this today.

**Identity source.** `preseason_staff_snapshot.csv` ONLY. `expected_opening_caller_id` where
`eligible_at_cutoff`; otherwise UNKNOWN.

**UNKNOWN routing** (prereg v3.6 — NEUTRAL; the v3.3 rule is WITHDRAWN): no pooled "unknown person"
identity. On an unknown-caller row **neither identity block activates** — the caller effect sits at
the league prior AND the non-calling-HC-context identity also routes to the league prior. We do not
assume the head coach delegated, and we do not assume he called the plays. He retains ordinary HC
résumé / change / tenure features, which do not depend on who called plays. `caller_known_share` and
`unknown_caller_share` are carried so the dilution stays visible; `assumes_delegation` is 0.

> **Superseded history.** v3.3 froze `ctx_mask = ~same`, which granted the head coach HC-context
> exposure on unknown-caller games and called that conservative. It is not: it assigns offensive
> residuals to a head coach with no evidence of delegation. Andy Reid entering 2026 reported 245
> "delegated" games of which only **5** were verified delegated; **240** were unknown-caller games
> from 1999–2013. Withdrawn in v3.6.

**Binding interpretation rules.**
- A null is **jointly** a test of coaching signal AND of archive retrievability. It cannot separate
  them; say so.
- Report power as effective n = rows with an eligible identity, and break it out by season, since
  coverage is 0% in some outer seasons.
- No season may be dropped to raise coverage; the outer window stays 2018–2025.

---

## Design B — ORACLE OPENING-IDENTITY SENSITIVITY — NON-DEPLOYABLE

**Question.** *If* opening identity were supplied correctly, do caller-quality features carry signal?

**Identity source.** `retrospective_staff_transitions.csv` — the verified actual opening caller
(95.3% outer coverage). This is **retrospective information that did not exist at the cutoff.**

**Why it is worth running.** It is the only way to distinguish:
- caller quality carries no signal → A and B both null
- caller quality carries signal the archive cannot currently deliver → B positive, A null

**No result direction is currently supported.** Neither outcome is predicted, expected, or more
likely than the other. Nothing has been fit and no outer outcome has been examined.

**Mandatory labelling on every reported B number.** "ORACLE IDENTITY — uses information unavailable
at the projection cutoff. NOT achievable in deployment. NOT evidence of real preseason performance."
A B result may never be the headline, never be compared to Sleeper or a production baseline as if
deployable, and never justify shipping anything.

**Status:** diagnostic. Runs alongside A, never instead of it, never alone.

---

## Design C — Continuity-imputation sensitivity (NOT AUTHORIZED)

**Proposed rule (not adopted).** Where no qualifying pre-cutoff evidence names the caller, impute the
identity that ENDED season Y−1, conditioned on pre-cutoff-eligible facts (person still employed at
the cutoff; HC unchanged; no pre-cutoff announcement naming someone else).

**Why it is not simply allowed.** Continuity-from-silence is the complement-inference the prereg
forbids. It is proposed as an explicitly labelled *imputation*, never as evidence.

### C-VALIDATION PROTOCOL (drafted for approval; do not run yet)

**Validation sample — corrected.** The 119 evidence-backed rows are **NOT an adequate sole
validation sample**: they are selection-biased toward seasons that happen to have accessible
league-wide preseason sources (2018/2023/2024 near-full; 2017/2025 zero). Validating on them would
measure the rule where the archive is richest and say nothing about where it is actually needed.

Validate instead against **all retrospectively resolved outer-season opening callers — up to
244/256** — using the retrospective opener **solely as the validation label**.

**Rules.**
1. The retrospective opener is a LABEL ONLY. It never becomes a predictor, and never enters the
   imputation rule's input set.
2. **Every predictor the rule uses must be genuinely pre-cutoff** and must pass the same eligibility
   gate as any other preseason feature — including employment status and HC identity, which must
   themselves be established by pre-cutoff evidence, not assumed.
3. **Season-blocked validation.** Never pool rows across seasons into a single shuffled estimate;
   accuracy is reported per season and aggregated across season blocks.
4. Report **exact-match accuracy and sample size** for every cell below — no cell reported without
   its n.
5. Report accuracy **by season**.
6. Report **HC-stable vs HC-change** separately. The rule is expected to fail precisely where the
   coaching staff changed, which is where any coaching signal would live.
7. Report **previous caller still employed vs departed** separately.
8. **The accuracy floor is pre-registered BEFORE any accuracy is computed.** It may not be chosen,
   adjusted, or rationalized after seeing results.
9. Report how much of any coverage gain comes from rows the rule gets **wrong**.

**Accuracy floor — the ≥70% HC-change proposal is WITHDRAWN (Joseph, 2026-07-29).** The continuity
rule was conditioned on HC stability in the first place, so a cell permitting a **30% identity-error
rate cannot authorize categorical caller imputation** — at that error rate the imputed identities
would inject more noise than the coverage is worth, and the errors would concentrate exactly where
coaching signal would live.

**No replacement floor is proposed here.** A continuity-validation protocol is to be drafted
separately once Phase 1C is correct. Nothing is to be calculated and no projection fit until that
protocol exists and Joseph approves it.

**Gate.** No projection use without (a) this validation executed, (b) a separate PREFIT amendment
recording the rule and its pre-registered floor, and (c) Joseph's explicit approval. If C is ever
used, it is a third labelled arm — never merged into A.

---

## Preserved: fully point-in-time HC-only experiment

**Expected HC identity is 100% point-in-time covered in every outer season.** The head-coach channel
therefore supports a clean confirmatory experiment at full power — no imputation, no oracle
information, no coverage caveat. It is a first-class arm, not a fallback.

**Scope, stated accurately — these are three different things and must not be conflated:**

- **HC résumé / change / tenure features apply to ALL head coaches**, including those who call their
  own plays. Career win%, tenure, and entering-change flags are properties of the person in the head
  -coach job and are defined for every team-season.
- **The adjusted non-calling-HC context effect applies ONLY to games where the HC delegated
  play-calling.** Per prereg v3.3 §1 it is the head coach's contribution to a *delegated* offense and
  must never be read as a universal head-coach effect.
- **McVay-style offensive-mind effects remain in the CALLER channel.** When the head coach calls the
  plays, that game routes to the portable caller block and contributes nothing to HC-context. So an
  HC-only experiment does **not** capture offensive-minded head coaches' play-calling contribution —
  that lives in A/B/C and is subject to their coverage limits.

---

## Recommended order

1. **HC-only point-in-time arm** — full power, fully honest, no coverage caveat.
2. **A** — archive-verifiable backtest, reported at its effective n with the archive caveat attached.
3. **B** — run only to interpret A.
4. **C** — only if Joseph wants it, only after the validation protocol above, only under a new
   amendment.
