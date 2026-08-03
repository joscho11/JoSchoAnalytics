# PROPOSED Amendment 1 — archived market lines without book attribution

> **STATUS: ACCEPTED by Joseph on 2026-08-03 — superseded by `PREREGISTRATION.md` §10 Amendment 1.**
>
> This file is retained as the **proposal of record**: the reasoning, the conditions C-1…C-7, and
> the arguments *against* acceptance in §5. It is no longer the operative document. What is in force
> is **§10 Amendment 1** of `futures/PREREGISTRATION.md`, which was appended (never edited in place)
> and which governs where this file and it differ.
>
> Joseph's ratification, in his terms: keep the Covers dataset, use it for an archived
> market-consensus baseline, unlock **descriptive / Tier-B MAE comparison only**, treat Covers as an
> archive and never as a sportsbook, keep Tier C — sides, EV, confidence, profitability — locked,
> record that exact closing timestamps are unavailable, and freeze the amendment **before** opening
> notebooks `02`–`05`. All five conditions are carried into Amendment 1 verbatim in substance,
> including the gate-shopping disclosure in §5.1 below (Amendment A1.6).
>
> §6's recommendation ("do not accept yet; prefer a book-attributed source") was read and overruled
> on the stated grounds that a transparent feasibility amendment, frozen before fitting and limited
> to Tier B, is defensible. The preference for a timestamped, named-book source is **not** discarded:
> it remains the only route to Tier C, and 2026 lines are to be collected prospectively.
>
> Drafted 2026-08-03 by Claude, after the acquisition run recorded in
> `futures/artifacts/win_totals_acquisition.json`.

---

## 1. What went wrong, precisely

`futures/01_acquire_win_totals.ipynb` acquired **352 team-seasons across 11 seasons (2014–2025)** of
preseason NFL win totals with both prices, from Covers Sports Odds History, reproducibly and with
full provenance. The data is clean. It fails the preregistration on **two independent provenance
grounds**:

**Blocker 1 — no sportsbook identity (§2.2, gate G3).**
The archive publishes the number and both prices but never names the book that posted them. `book`
is null on all 352 rows. Filling it with "Covers" would be inventing provenance — an archive is not
a sportsbook — so the audit correctly invalidates every row, and G1/G2 read 0 as a consequence.

**Blocker 2 — date-granularity timing, mostly on kickoff day (§2.2, gate G1).**
Only **2014–2018** carry an `As of` date strictly before Week 1. Six further seasons (2019–2022,
2024, 2025) are dated *on* the Week 1 date with no clock, and 2012/2013/2023 carry no date at all
(2023 states only *"Closing odds prior to each teams' first game"*). Even if Blocker 1 were solved,
**5 demonstrably-preseason seasons falls short of G1's threshold of 8.**

Both must be addressed for anything to change. Solving one alone leaves the verdict NO-GO.

---

## 2. What this proposal would and would not permit

The preregistration's §7 gates run A (descriptive) → B (beats the market on accuracy) → C (beats it
at the posted price, unlocking side-taking language). This proposal touches **only the evidence
admissible for B**, and it *tightens* C rather than relaxing it.

| | Tier B — accuracy vs an archived market line | Tier C — anything priced |
|---|---|---|
| **Question** | Was the projection closer to the realized win count than the market number was? | Would taking a side at the posted price have been profitable / is P(OVER) calibrated against it? |
| **Needs** | A number, a date, and a source | A number, **a price**, **a named book**, and a timestamp |
| **Under this proposal** | **Admissible** with a book-less archived line, under §3's conditions | **Not admissible.** Unchanged from the frozen preregistration |
| **Permitted language** | "the projection was closer to the result than the archived market number over N seasons, in aggregate" | side, probability-vs-line, confidence tier, edge, value, bet, ROI, profitability — **all still forbidden** |

**The hard rule this proposal must never weaken:** *no side, probability-against-a-line, confidence,
edge, or profitability claim may be made from a line whose sportsbook and price provenance is not
established.* An archived consensus number with an unattributed price is a description of where the
market sat. It is not a transactable price, and a backtest against it is not a P&L.

---

## 3. Proposed conditions (all required, none severable)

Were this accepted, admitting a book-less archived line for **Tier B only** would require:

**C-1 — Named archive, null book.** `market_source` must name the archive; `book` must remain
**null**. Writing the archive's name into `book` is forbidden and is asserted against in the
acquisition notebook.

**C-2 — A published capture date per season**, compared against Week 1 from this repository's own
schedule snapshot, with every row carrying an explicit `point_in_time_status`.

**C-3 — Kickoff-day clause.** A capture dated *on* the Week 1 date may count as preseason **only**
when the source states, on the page or in its documentation, that the numbers are pre-kickoff
closing values — and that statement is quoted verbatim in the acquisition artifact. Rows admitted
this way stay tagged `same_day_as_week1_kickoff` and are reported separately in every result table,
never pooled silently with strictly-dated rows.
*Applied to today's data: this admits 2019–2022, 2024, 2025 on the strength of the 2023 page's
"Closing odds prior to each teams' first game" statement — 11 seasons, clearing G1's 8.*
*It does **not** admit 2012, 2013 or 2023 themselves: no date, no admission.*

**C-4 — Sensitivity is mandatory, not optional.** Every headline B result must be reported twice:
once on strictly-dated seasons only (2014–2018, n=160) and once on the full admitted set (n=352). If
the two disagree in sign, **the strict subset governs** and the difference is reported as the
finding. A result that exists only on the same-day rows is a result about the kickoff-day clause,
not about the model.

**C-5 — Underpowering is still underpowering.** §3's minimum (5 folds / 160 evaluation rows) applies
to the *strict* subset as well as the pooled one. The strict subset yields 5 seasons → 4 folds
after the earliest is reserved for training, which is **below** the §3 minimum. So under this
proposal the strict subset alone remains formally underpowered and can only ever be a sensitivity,
never the headline.

**C-6 — The label travels.** Any surface showing a B result must state that the market comparison
uses an archived line of unattributed sportsbook origin. It may not say "the sportsbook line" or
"Vegas".

**C-7 — C stays shut.** Gate C remains defined exactly as in the frozen §7 and is unreachable from
archive data. Reopening it requires book-attributed, timestamped prices and a fresh amendment.

---

## 4. What acceptance would and would not change

**Would change:** G3's book requirement would be split into a Tier-B path (C-1…C-6) and a Tier-C
path (unchanged). With the kickoff-day clause, 11 seasons / 352 rows would become admissible and G1
would pass at 11 ≥ 8, G2 at 32/32 every season.

**Would not change:** §2.1 (target and settlement), §2.3 (feature availability), §3 (expanding-season
folds, no random CV, minimum sizes), §4 (metrics and baselines — the archived line still serves as
B0), §6 (model families), §7 gates A and C, the language fence, and the one-shot rule. The
no-reconstruction rule in §2.2 stays absolute: this proposal admits a *differently-provenanced*
observed line, never a derived one.

---

## 5. Honest arguments against accepting this

Stated deliberately, because a proposal that only argues its own case is advocacy:

1. **The book requirement was not an accident.** It was written to stop exactly this: a number that
   looks like a market line, is treated like one, and turns out to be a consensus of unknown origin.
   Accepting the amendment because the free data happens to fail it is gate-shopping — choosing the
   rule after seeing which rule the data fails. That is the specific failure mode
   `cowork-research-methodology`'s Amendment-4 discipline exists to prevent, and the fact that the
   proposal was drafted *after* the acquisition run is a real strike against it.
2. **Archive accuracy is unverified.** Nothing here confirms Covers transcribed real posted markets
   correctly, and there is no second source to check against. A transcription error is
   indistinguishable from a market view.
3. **"Closing at kickoff" is the strongest possible market.** Beating a closing number is much harder
   than beating an opener, so a null result under this amendment would be weaker evidence against
   the model than it appears — and a positive result correspondingly more surprising, which should
   raise suspicion of a data artifact rather than lower it.
4. **The strict subset is underpowered on its own** (C-5). So the amendment's real effect is to make
   the *same-day* rows load-bearing, and the whole conclusion would then rest on a clause about a
   sentence on a 2023 web page.
5. **Doing nothing is cheap.** The dataset, the notebook and the raw cache all persist. Acquiring a
   book-attributed source later costs one acquisition notebook and resolves both blockers cleanly,
   with no amendment at all.

---

## 6. Recommendation

**Do not accept this amendment yet.** Prefer, in order:

1. **Acquire a book-attributed, timestamped source** (a historical odds API or a book's own archive).
   That satisfies the frozen preregistration as written, needs no amendment, and is the only route
   that could ever reach gate C.
2. **If no such source is obtainable**, then consider accepting this amendment — but only with C-1
   through C-7 intact, and with the gate-shopping objection in §5.1 recorded alongside the decision
   in the §10 ledger, so any future reader sees that the rule was changed after the data was seen.
3. **Meanwhile**, the honest public statement is the one already true: *the projection question
   cannot be answered against the market with the data this repository owns, and the reason is
   provenance, not modelling.*

---

## 7. If accepted

Append to `futures/PREREGISTRATION.md` §10 as **Amendment 1**, dated, quoting §§2–3 of this file
verbatim and recording:

* the date, that Joseph accepted it, and the acquisition run's `csv_sha256` in force at the time;
* the gate-shopping disclosure from §5.1;
* the fold set the amendment produces, frozen by re-running
  `futures/season_team_totals/00_data_audit.ipynb` — which would itself need a mode implementing
  C-1…C-3, since it currently requires a named book and would keep returning NO-GO regardless of
  what this document says.

**Nothing above is in force. The audit's answer today is NO-GO.**
