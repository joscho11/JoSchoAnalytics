# Utility script: prints every cell of BettingEdge_v2.ipynb to stdout.
# Useful for inspecting the notebook structure without opening Jupyter.
# Run from the project root: python check_v2_pipeline.py
import json, sys
with open("betting/BettingEdge_v2.ipynb", encoding="utf-8", errors="replace") as f:
    nb = json.load(f)
print("Total cells:", len(nb["cells"]))
for i, c in enumerate(nb["cells"]):
    src = "".join(c["source"])
    print("\n=== Cell %d [%s] ===" % (i, c["cell_type"]))
    sys.stdout.buffer.write((src[:1500] + "\n").encode("utf-8", errors="replace"))
