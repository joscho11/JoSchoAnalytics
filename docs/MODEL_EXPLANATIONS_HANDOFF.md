# Model-explanations handoff — **STATUS: COMPLETE (2026-07-24)**

> **This is a finished record, not a pending task.** The Help & Guide "What Drives the Models"
> section shipped. **No model artifact changed during the update**, so every MD5 recorded below
> as "pre-update" is still the *current* production hash. Re-verified 2026-07-27: all **8**
> `SHAP_SNAPSHOTS` entries in `model_explanations.py` hash-match the artifacts on disk — 8 match,
> 0 mismatch, 0 missing. The section fails closed: if a pinned artifact ever moves, the
> explanation is withheld rather than shown against a model that no longer exists.
>
> Keep this file as the specification of that hash-pinning contract. **Re-open it only if a
> production pkl is retrained** — in which case the SHAP snapshots must be regenerated and
> re-pinned in the same change.

The block below is the original instruction text, preserved verbatim for the record.

```text
I need you to finish the Help & Guide model-explanations work after your current
model updates are complete. Read this entire handoff before acting.

== YOUR ROLE ==

You are the coding agent working directly in:
C:\Users\josep\Desktop\random_stuff\cowork_OS\BettingEdgeContinued

Inspect the repo before changing anything. If the repo disagrees with this
handoff, the repo wins; report the discrepancy before acting. Preserve unrelated
dirty-worktree changes. Joseph performs all git operations: never commit, never
suggest a commit message, and do not describe anything as commit-ready.

Use the applicable workspace skills before work:
- bettingedge-architecture-and-operations
- cowork-change-control
- cowork-validation-and-qa
- cowork-docs-and-writing
- betting-domain-reference if interpreting spread/odds features

== GOAL ==

Complete the new “What Drives the Models” section in Help & Guide using the
FINAL production model artifacts produced by this session. The section must
cover every production prediction model surfaced by the website while excluding
retired, held, experimental research-only, and superseded artifacts.

The implementation already exists. Do not rebuild it from scratch:
- site_pages/page_help.py renders the section.
- model_explanations.py owns labels, importance data, model-artifact
  fingerprints, and HTML chart rendering.
- tests/test_model_explanations.py protects coverage and fingerprint freshness.
- tests/test_help_page.py checks the offline Streamlit render.

== CURRENT IMPLEMENTATION ==

Coverage is 22 production artifacts:
- Seven season-total models: QB veteran; RB/WR/TE veteran and rookie.
- Twelve weekly fantasy models: four fantasy-point models plus eight supporting
  displayed-stat models.
- The spread ensemble’s 75% XGBoost component.
- Totals XGBoost and totals Ridge.

Methods are deliberately distinct and must stay labeled honestly:
- Seasonal and spread charts: mean absolute Tree SHAP.
- Weekly fantasy and totals XGBoost: normalized XGBoost gain, derived directly
  from the current pickle.
- Totals Ridge: absolute standardized-coefficient share, derived directly from
  the current pickle.

Do not call gain or Ridge coefficients “SHAP.” Do not describe any importance
as causal or as evidence of model accuracy.

The seasonal and spread SHAP entries in model_explanations.SHAP_SNAPSHOTS are
bound to exact MD5 hashes. If a model pickle changes, shap_models() withholds
that card and site_pages/page_help.py shows a stale-model warning. This fail-closed behavior
is intentional and must remain.

At the time this handoff was written (2026-07-24), the recorded seasonal model
MD5s were:
- qb_veteran_model.pkl: 7632549f95995b9702baefdf016d7271
- rb_veteran_model.pkl: 167aca71a8511afcced37c0abc846004
- rb_rookie_model.pkl: da230ee66575ca574f02cbc2139e1a80
- wr_veteran_model.pkl: 17dfbcf01054bdd5ce032f2b55df9ad2
- wr_rookie_model.pkl: 6c9a3f3ed02ce32c53594f383aade882
- te_veteran_model.pkl: 5a2f0b504d4cc6fc9a2e04453fd76a44
- te_rookie_model.pkl: f79dad0ab26af5cb4e06a9f1723328cd

The recorded spread ensemble MD5 was:
- betting/models/ensemble_prod_model.pkl:
  42a61911f6600852d9dcb094896735f0

Those hashes describe the pre-update artifacts. Do not preserve them merely to
make tests pass. Recompute explanations and replace hashes only for production
artifacts that genuinely changed.

== REQUIRED PROCEDURE ==

1. Finish and validate the model updates first. Do not refresh explanations
   against intermediate artifacts.

2. Run:
   git status --short
   Then calculate MD5s for the seven files under
   fantasy/projections/models/ and the spread
   betting/models/ensemble_prod_model.pkl. Identify exactly which artifacts
   changed relative to the hashes above.

3. Recompute seasonal SHAP for every changed seasonal artifact:
   - Use the final saved model bundle and the exact final 2026 deployment matrix
     used to produce the public projection CSV.
   - Use the matching veteran/rookie feature_cols stored in the bundle.
   - For LightGBM, request contribution values from the saved model/booster with
     pred_contrib=True.
   - Exclude the final expected-value/bias column.
   - For each feature, calculate mean(abs(SHAP)) over the full 2026 deploy
     population, then divide by the sum across features and multiply by 100.
   - Sort descending and retain exactly five features.
   - Record the exact deploy row count.

4. Reconciliation is mandatory before publishing a seasonal chart:
   - Ordinary predictions from the same model and matrix must reconcile to the
     corresponding public results CSV after its documented clipping/rounding.
   - Player coverage must reconcile row-for-row with the public projection
     surface for that model arm.
   - Assert no duplicate player identity within an arm.
   - If any reconciliation fails, STOP. Do not update the snapshot or weaken the
     assertion.

5. Update only the affected entries in
   model_explanations.SHAP_SNAPSHOTS:
   - new MD5
   - new n
   - new top-five feature names
   - new normalized percentage shares
   Keep all unchanged entries byte-for-byte where practical.

6. Spread handling:
   - If ensemble_prod_model.pkl did not change, leave its SHAP entry untouched.
   - If it changed, rebuild the exact production feature matrix without
     retraining or overwriting any pickle. Use the feature-construction sections
     of betting/model_comparison.ipynb through the completed feature/injury
     matrix only; do NOT execute the production-retraining section.
   - Load ensemble_prod_model.pkl and use its stored feature_cols.
   - Calculate XGBoost pred_contribs over all completed 2014–2024 production
     training games, exclude the bias column, take mean absolute contributions,
     normalize across features, and keep five.
   - Assert the ensemble package still identifies XGBoost weight 0.75 unless the
     model update explicitly and validly changed the production architecture.
     If the architecture changed, update the Help copy and tests rather than
     silently retaining the “75% component” claim.
   - Update the spread snapshot’s MD5, n, features, and percentages only after
     those checks.

7. Weekly fantasy and totals:
   - native_models() derives these charts directly from current artifacts.
   - Verify the expected production artifact inventory still matches the
     website. If a displayed stat model was added/removed/renamed, update the
     inventory test and public labels to match production reality.
   - Do not add research or unused pickle files merely because they exist.

8. Public-copy requirements:
   - Keep the global/non-causal/not-an-accuracy-ranking disclosure.
   - Keep the note that the displayed top five generally do not sum to 100%.
   - Keep method labels visible on every card.
   - If the spread architecture changed, correct all relevant Help & Guide prose,
     not only the chart caption.

9. Validation:
   Use the project’s working isolated interpreter if present:
   .\.venv-test\Scripts\python.exe

   Run explicitly from the BettingEdgeContinued root:
   & .\.venv-test\Scripts\python.exe -m pytest `
     tests/test_model_explanations.py `
     tests/test_help_page.py `
     tests/test_app_draft_board.py `
     betting\test_features.py -q

   Do not run bare pytest at the repo root; research scripts match pytest-like
   names. Require zero failures. Existing warnings may be reported but must not
   be represented as failures.

10. Documentation:
   - Update the existing 2026-07-24 Help & Guide entry in
     memory/daily/2026-07-24.md with the FINAL hashes/counts/top features if they
     changed. Edit superseded facts in place rather than stacking contradictory
     numbers.
   - Update the newest matching entry in memory/completed-work-log.md.
   - Do not modify preregistration outcomes or research verdicts; this is a
     descriptive production-explanation refresh, not a model experiment.

== FENCES ==

- Never change a model, feature set, projection, or public ranking merely to make
  an explanation chart look intuitive.
- Never update an expected MD5 without recomputing and reconciling the associated
  SHAP values.
- Never display stale SHAP values under a new model hash.
- Never substitute gain importance for the seasonal/spread SHAP snapshot without
  changing the public method label and receiving Joseph’s approval.
- Do not execute one-shot seasonal research harnesses or reopen retired H5/H4
  paths. Seasons 2008–2015 remain sealed.
- Do not overwrite or delete unrelated dirty-worktree files.
- Do not commit.

== ACCEPTANCE CRITERIA ==

Done means:
- Every website-surfaced production model has one correctly labeled top-five
  chart.
- Every changed seasonal/spread artifact has freshly recomputed, reconciled SHAP
  values and the correct final MD5.
- No stale warning appears for final production artifacts.
- Retired/held/research-only artifacts remain excluded.
- The explicit 22-test command (or its correctly updated equivalent if the model
  inventory changed) passes.
- No model or projection artifact is modified by the explanation-refresh work.
- Final response reports changed files, final coverage count, SHAP sample counts,
  artifact hashes updated, and exact test results. Do not mention commits.

Start by reading the applicable skills and current git status, then report which
production model artifacts your preceding work changed before editing the
explanation snapshots.
```

