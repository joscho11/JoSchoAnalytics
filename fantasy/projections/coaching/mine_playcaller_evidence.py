"""Mine the cached Wikipedia team-season articles for EXPLICIT play-calling statements.

Read-only over `data/wikipedia_team_season_cache.json` (448 articles already fetched). Makes no
network calls. Emits candidate evidence sentences for human adjudication -- it decides NOTHING on
its own, because the prereg forbids inferring the play-caller.

Output: data/playcaller_evidence_candidates.csv, one row per candidate sentence, with the article
it came from so every downstream assignment carries a citation.
"""
import json
import re
import sys
from pathlib import Path

import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
CACHE = DATA / "wikipedia_team_season_cache.json"

# Deliberately broad: recall matters here, precision is supplied by human adjudication.
PAT = re.compile(
    r"[^.\n]{0,240}?"
    r"(play[-\s]?call\w*|call(?:ed|ing|s)?\s+(?:the\s+)?(?:offensive\s+)?plays|play\s+caller)"
    r"[^.\n]{0,240}\.", re.I)


def clean(s):
    s = re.sub(r"<ref[^>]*>.*?</ref>", "", s, flags=re.S)
    s = re.sub(r"<ref[^>]*/>", "", s)
    s = re.sub(r"\{\{[^}]*\}\}", "", s)
    s = re.sub(r"\[\[(?:[^\]|]*\|)?([^\]]*)\]\]", r"\1", s)
    s = re.sub(r"'{2,}", "", s)
    s = re.sub(r"<[^>]+>", "", s)
    return " ".join(s.split())


def main():
    cache = json.loads(CACHE.read_text(encoding="utf-8"))
    rows = []
    for title, wtxt in cache.items():
        if not wtxt or wtxt.startswith("__ERR__"):
            continue
        m = re.match(r"^(\d{4})\s+(.*?)\s+season$", title)
        if not m:
            continue
        season, team_name = int(m.group(1)), m.group(2)
        for hit in PAT.finditer(wtxt):
            sent = clean(hit.group(0))
            if len(sent) < 40:
                continue
            rows.append(dict(season=season, team_name=team_name, evidence=sent,
                             source_url="https://en.wikipedia.org/wiki/"
                                        + title.replace(" ", "_")))
    ev = pd.DataFrame(rows).drop_duplicates(subset=["season", "team_name", "evidence"])
    ev.to_csv(DATA / "playcaller_evidence_candidates.csv", index=False)

    print("=" * 78)
    print("PLAY-CALLING EVIDENCE MINED FROM CACHED TEAM-SEASON ARTICLES")
    print("=" * 78)
    print(f"articles scanned : {sum(1 for v in cache.values() if v and not v.startswith('__ERR__'))}")
    print(f"candidate sentences: {len(ev)}")
    if len(ev):
        ts = ev.groupby(['season', 'team_name']).size()
        print(f"team-seasons with >=1 candidate: {len(ts)} of 448 "
              f"({100*len(ts)/448:.1f}%)")
        print("\nby season:")
        print(ev.groupby('season').apply(
            lambda d: len(d.groupby('team_name')), include_groups=False).to_string())
        print("\n--- sample candidates ---")
        for _, r in ev.head(25).iterrows():
            print(f"  [{r.season} {r.team_name}] {r.evidence[:200]}")
    print(f"\nwrote {DATA/'playcaller_evidence_candidates.csv'}")


if __name__ == "__main__":
    main()
