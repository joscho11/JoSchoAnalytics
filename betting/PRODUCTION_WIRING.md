# Production wiring plan — CLV + line shopping + Kelly into the live loop

Everything below is **staged, not yet activated.** The new betting-execution
modules are standalone and tested; this doc is the single "go-live for Week 1"
checklist. Nothing here touches `app.py` or `.github/workflows/` until you say go.

## What's built (all in `betting/`, all offline-tested)

| Module | Role in the loop | Live-data status |
|--------|------------------|------------------|
| `odds_client.py` | pull multi-book NFL lines; snapshot `pick_line`/`closing_line`/`clv` | verified working 2026-06-18 against posted Week-1 lines; in the offseason it returns an empty slate — re-verify before Week 1 |
| `weekly_clv.py` | weekday-aware CLV snapshot driver (pick Tue–Thu, close Sun) | no-ops in offseason |
| `line_shopping.py` | best number per side across ~9 books | works now |
| `kelly_staking.py` | tier-weighted ¼-Kelly stake off the OOS edge | works now |
| `clv_backtest.py` + `experiments/walkforward_oos_preds.py` | historical validation: HIGH = **64.2% ATS-vs-open, 380/592, walk-forward OOS 2018–2025** OOS (de-confounded; model does NOT beat the close) | done |
| `props_scanner.py` | player-prop value vs fantasy projections | yardage props post near kickoff |

## The weekly sequence (once live)

1. **Tue/Thu** — after `predict_betting.ipynb` writes the tracker:
   `python betting/weekly_clv.py` → records `pick_line` for the week's games.
2. **Sun (pre-kickoff)** — `python betting/weekly_clv.py --which closing` → records
   `closing_line` + computes `clv`.
3. **For each HIGH-tier pick** — route to the best book via
   `line_shopping.best_for_pick(event, side)`, size via `kelly_staking` (HIGH ≈ 2%/bet).

## Go-live checklist (in order, each independently revertable)

- [ ] **1. Confirm the key in CI.** Add `ODDS_API_KEY` to the GitHub repo secrets
      (it's only in local `.env` today). The weekly workflow needs it as an env var.
- [ ] **2. Wire CLV into `.github/workflows/weekly_predictions.yml`.** Add one step
      after the predict step in each job (it already runs Tue/Thu/Sun):
      ```yaml
      - name: Snapshot CLV
        env: { ODDS_API_KEY: ${{ secrets.ODDS_API_KEY }} }
        run: python betting/weekly_clv.py        # weekday auto-selects pick/closing
        continue-on-error: true                   # never block the tracker commit
      ```
      Stage the `pick_line`/`closing_line`/`clv` columns in the existing commit step
      (they're already in the tracker schema).
- [ ] **3. Pilot Week 1 before trusting it.** Confirm `spread_line` actually moves
      intra-week on live data and that team-name matching is 100% (the alias map is
      current-roster only; watch for any unmatched game in the run log).
- [ ] **4. Dashboard surfacing (optional).** Add a CLV column in `site_pages/page_track_record.py`
      and a HIGH-tier Kelly stake chip on the game cards in `site_pages/page_weekly_predictions.py`
      (`app.py` is only the `st.navigation` entrypoint now and renders nothing) — **but** the last
      stake chip was removed at user request, so confirm the framing first. Keep it
      behind the same honest-disclosure styling as the totals badge.
- [ ] **5. Re-fit Kelly on the live record.** After ~1/2 season of forward CLV,
      re-run `kelly_staking.py` against actually-bet lines (not the vs-close floor) —
      this is where MEDIUM tier gets re-tested for a real stake.

## Guardrails / honest caveats baked in

- CLV snapshot is `continue-on-error` — an API hiccup must never block the tracker.
- Free tier ≈ 500 credits/month; the weekly CLV snapshots cost ~3 each → trivial.
  Props are event-level (1 credit/game) so scan props only for games you'll bet.
- The edge is **ATS skill, not CLV**: de-confounded OOS, the model does NOT beat
  the close (45% beat-close), but HIGH-tier picks cover the line you bet at 64%
  (64.2%, 380/592, 2018-2025, one opening-line source). Size off that ATS rate, not CLV.
  Forward 2026 results confirm whether it holds vs the lines you actually get.
- Nothing here changes the spread/totals models — execution only, by design
  (the models are at their documented ceiling).
