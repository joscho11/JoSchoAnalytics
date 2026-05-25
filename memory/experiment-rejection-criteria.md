---
name: experiment-rejection-criteria
description: When to declare a model-improvement experiment "doesn't work" and revert. Concrete thresholds, not gut calls.
metadata:
  type: project
---

After running several model-improvement experiments in May 2026 (weather features, ensemble re-weighting, consensus filter removal, ULTRA tier, all rejected), these are the concrete criteria the user wants applied to future experiments. Lock them in to keep discipline consistent across runs.

## Hard rules (must ALL be true to ship a change)

1. **Walk-forward CV mean ATS improves by at least +0.5pp on the primary direction-voter model (XGBoost cv).** Smaller gains are within the n=855 / 6-fold standard error (~1.9pp std) and not distinguishable from noise.
2. **At least 3 of 5 CV models show non-negative ATS movement.** A single model improving while the others get worse is a feature-architecture mismatch, not a real signal.
3. **Std deviation across folds does not increase by more than +0.3pp.** Adding noise that improves the mean but increases variance is a worse bet, not a better one.
4. **Pkl byte-equivalence is verified** for any "refactor only, no model change" claim. Snapshot md5s before, retrain, compare. The order-hash check in features.ipynb cell 8 enforces this for the most common failure mode (feature-list reorder), but the user verifies manually for any other behavior-preserving claim.

## Conflict resolution rules

5. **When test set (large n) and live data (small n) disagree, the conservative read wins for production.** The 855-game test set is statistically stronger in theory, but the live OOS sample is what the model actually faces in production. Don't ship a change that helped on the test set but hurt on live data, even if "within noise". See the consensus-filter experiment for the canonical example: test set said the filter added zero accuracy; live data showed -3pp on MEDIUM. We kept the filter.

## Usefulness rules

6. **A new tier or label must fire at least 5% of the time on live data.** The ULTRA tier (≥5pt edge) fired only 2 games in 7 weeks of live 2025 (about 1.7% of all games). Tier labels that fire <1 per week aren't actionable for staking decisions or UX. Reject.
7. **A new feature must beat baseline by more than its added inference cost.** Adding 2 features to a 35-feature model is +5.7% feature count. The signal needs to clearly justify the noise/overfitting risk that adds. See the weather-features experiment for an example where the cost was real and the benefit was zero.

## Process rules

8. **Snapshot pkl md5s before EVERY retrain experiment.** Save as `betting/_pkl_baseline_*.json` and back up the pkls themselves to `*.pkl.<experiment_name>_baseline`. The first weather retrain in the session caught the PROD_FEATURES_35 reorder bug because we had baseline md5s on disk to compare against.
9. **A "rejected experiment" must be fully reverted in the same session.** Don't leave half-reverted state across sessions. Restore pkls from backup, restore tracker, restore CLAUDE.md/README.md text. Keep only the analysis-cell evidence (so the work is documented) and any reusable artifacts (e.g., the weather CSV survives as a future-totals-model input, even though weather as a spread feature was rejected).
10. **Document the rejection in CLAUDE.md Completed Work AND in a memory note.** The Completed Work entry is the project-history record; the memory note is the don't-redo-this guardrail. Both required. See `[[bettingedge-model-experiments-2026-05]]` for the canonical format.

## When to break these rules

If you have a STRONG theoretical reason to believe a feature should help (e.g., a known market inefficiency the model doesn't see), you can run the experiment even if you expect to fail criterion 1 or 2. But ship gating remains the same: revert if it doesn't beat the bar.

## How to apply

- Before a model-changing experiment: snapshot baselines, write down the hypothesis + ship/reject criteria.
- During the experiment: run on walk-forward CV first (cheap, 6 folds), then live OOS data (small but realistic).
- After: compare against rules 1-7. If any fail, revert per rule 9 + document per rule 10.
- The 2026-05-24 session is the canonical example of this discipline applied to 3 experiments in a row (all rejected, all reverted, all documented).

Related: [[bettingedge-model-experiments-2026-05]] (the experiments themselves), [[feature-list-order-is-contract]] (one specific failure mode this discipline catches).
