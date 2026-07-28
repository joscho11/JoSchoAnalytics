# U6 weekly fantasy + dfs — Lens A

- Pipelines are notebook-based (papermill) with inline test cells (RUN_TESTS pattern);
  retrain_models.py writes fantasy pkls BY DESIGN (manual retrain path). No tracker or
  frozen-artifact writes. The PRACTICE_MAP drift class (playbook §6) remains the known
  silent-failure vector; mitigated by the documented assert-NaN-rate practice.

Coverage: retrain_models.py fully read; notebooks reviewed structurally via CLAUDE.md
cell tables + json-level spot-grep. NO FINDINGS of severity >= HIGH.
