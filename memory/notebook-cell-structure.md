---
name: notebook-cell-structure
description: Required cell structure for every notebook in a pipeline — intro, explain→code→interpret triples, conclusion
metadata:
  type: feedback
---

Every notebook I create in this repo — and every notebook of a pipeline whenever
Joseph asks for a "notebook pipeline" — must have this structure. He should never
have to ask for it again.

**1. Intro cell (markdown, first cell).** What this notebook is for, where it sits
in the pipeline, what it reads, what it writes, how to run it (papermill line), and
what gates it.

**2. Every code cell is wrapped in a markdown sandwich:**

- **Explanation cell ABOVE** — what this cell is about to do and *why*, in prose.
  Section header lives here.
- **The code cell.**
- **Interpretation cell BELOW** — reads the output the cell just produced and
  *analyzes* it: what the numbers mean, what a healthy result looks like, what would
  be a red flag, what it implies for the next section. Not a restatement of the code.

This applies to **inline test cells too** — an explanation of what the assertions
guard (and why each one exists) above, and a reading of the pass line below.

So a section is six cells:

```
md   ## Section N — <name>          (what + why)
code <the work>
md   ### Interpreting the output    (analysis of the result)
md   ### What these tests guard     (why each assertion exists)
code if RUN_TESTS: ...
md   ### Reading the test result    (what a pass proves, what it does NOT prove)
```

**3. Conclusion / next steps cell (markdown, last cell).** What the notebook
decided, what it wrote, what is now true, and the explicit next step — including the
condition under which the *next* notebook may run.

**Why:** Joseph reviews notebooks by reading them top to bottom, and a bare code cell
with a number under it makes him reconstruct the reasoning himself. Interpretation is
the part he actually wants; the code is evidence for it. Stated 2026-08-02: "make sure
every coding cell has a corresponding explain cell above the code that explains what
the coding cell is doing and an interpretation cell that explains the results and
analyzes them... so I don't have to explain it every time."

**How to apply:**
- Interpretation cells cite the numbers from the recorded run, dated, so a stale
  interpretation is visible rather than silently wrong.
- Say what a result does NOT prove as well as what it does — a passing test cell
  proves the assertion held, not that the design is right.
- Keep the same headings across notebooks so the structure is scannable.

Related: [[prefer-ipynb-not-py]] (new shared code goes in .ipynb, markdown → code →
inline-test), and the repo's CLAUDE.md cell-structure tables.
