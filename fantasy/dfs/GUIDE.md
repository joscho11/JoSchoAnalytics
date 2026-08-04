# A guide to the DFS lineup optimizer

This is the plain-language tour of the daily-fantasy (DFS) lineup optimizer — the tool that builds
a DraftKings roster out of my weekly player projections. I built it, and I want to be clear up
front about what it is: a solid, correct optimization tool, not a proven money-maker. It's only as
good as the projections I feed it.

## What I'm trying to do

Daily fantasy is a contest where you pick a roster of NFL players under a salary cap, and your
lineup scores real fantasy points that weekend. On DraftKings' "Classic" format you fill nine
roster slots — one quarterback, at least two running backs, at least three receivers, at least one
tight end, one team defense, and a flexible slot — and every player has a salary, with the whole
roster capped at \$50,000.

The problem is a puzzle: out of hundreds of players, which nine give me the most projected points
while staying under the cap and filling every slot legally? Trying combinations by hand is
hopeless — there are far too many. And the obvious shortcut, "just pick the players with the most
projected points per dollar," quietly fails, because the salary cap and the slot rules tangle the
choices together: a bargain receiver might only fit if I also take an expensive quarterback, and
the last few hundred dollars of cap space can force a worse pick everywhere else. The pieces
interact, so the roster has to be solved as one whole, not chosen one player at a time.

So I hand the puzzle to a solver that finds the *provably* best answer for a given set of
projections — not a good-enough guess, but the mathematically highest-scoring legal roster there
is. That's the entire job of this tool: take my weekly projections and return the best legal
lineup.

One thing this tool does *not* do is decide whether the players are any good — that comes from the
weekly fantasy model (its own guide is in `fantasy/`). The optimizer just arranges the best legal
roster out of whatever projections it's given. Good projections in, good lineup out; the reverse
is just as true. This is worth stressing, because a slick optimizer can create a false sense of
confidence: the lineup it returns is optimal *for the projections*, and if the projections are off,
the lineup is confidently wrong.

A word on the two kinds of contests, because it shapes what this tool is for. In "cash" games you
roughly need to beat half the field, so a single strong, sensible lineup is the goal. In large
tournaments (often called GPPs) you're trying to beat thousands of people, which rewards building
many *different* lineups and deliberately choosing less-popular players so that when they hit, few
others share your score. This tool is built for the first kind — one strong lineup — and I'll come
back to that limit in the honest-results section.

## How it works, end to end

**The projections come in.** The optimizer reads the weekly projection CSV that the fantasy model
writes — each player's projected half-PPR points for the upcoming week. Those projected points are
the "value" the optimizer tries to maximize.

**The salaries come in.** Each week DraftKings publishes a CSV of every player's salary for that
slate. I load it and match those names to my projections. Name matching is fiddly and matters more
than it sounds: the two files come from different sources, so one might say "Michael Pittman" and
the other "Michael Pittman Jr.", or differ on punctuation, suffixes, or a nickname. If a match is
missed, that player simply falls out of the pool and can never be drafted — so a matching gap
silently shrinks the optimizer's choices. To avoid that I use fuzzy matching, which pairs names
that are close enough rather than demanding an exact, character-for-character string match, and I
keep the matching loose enough to catch the suffix and punctuation cases while staying tight enough
not to confuse two genuinely different players.

**The solver runs.** This is the heart of the tool. I write the roster problem as an integer linear
program — a precise mathematical statement of "maximize total projected points, subject to these
rules." Each player is a yes/no (in the lineup or not — that's the "integer" part, since you can't
draft half a player), and the rules become constraints the solver must respect:

- exactly the required slots: 1 quarterback, at least 2 running backs, at least 3 receivers, at
  least 1 tight end, 1 team defense, 9 players total;
- total salary at or under \$50,000;
- no more than 8 players from any single NFL team.

The "no more than 8 from one team" rule is DraftKings' own; I encode it so the solver can't return
a lineup the site would reject. The flexible slot fills itself — the solver is free to add one
extra running back, receiver, or tight end wherever it adds the most points, so I don't hard-code
which position lands there. A library called PuLP does the actual solving: it explores the space of
legal rosters the smart way (ruling out whole branches that can't beat the best roster found so
far) and returns the single best one for those projections and salaries. Because it's a real solver
and not a heuristic, the answer isn't "a good lineup" — it's *the* best lineup those numbers allow,
which also means any weakness in the result is a weakness in the projections, not in the search.

**The lineup goes out.** I export the result in the exact column layout DraftKings expects for a
Classic upload — one column per roster slot, in order — so it can be uploaded directly rather than
retyped.

## A map of the key files

| File | What it is |
|---|---|
| `fantasy/dfs/lineup_optimizer.py` | The optimizer itself — the constraints and the solve, written once. Both notebooks import it. |
| `fantasy/dfs/dfs_matching.py` | Links a DraftKings name to the right projected player, and converts to DraftKings scoring. |
| `fantasy/dfs/optimizer.ipynb` | Reference notebook: explains each constraint and exercises the module. It no longer contains the solver code. |
| `fantasy/dfs/dfs_pipeline.ipynb` | The weekly workflow: load projections and salaries, solve, export the DraftKings file. |
| `fantasy/dfs/test_lineup_optimizer.py` | Proof the solve is a real one: it checks the CBC program is installed, runs it on the kept week-10 slate, and measures every roster rule off the answer. |
| `fantasy/fantasy_projections/` | The weekly projections (written by the fantasy model) that the optimizer reads. |

## Honest results

There's no hit-rate to report here, and I won't invent one. The optimizer is a correctness tool,
not a prediction: given a set of projections and salaries, it returns the best legal lineup, and it
does that job reliably. Whether that lineup actually wins money depends almost entirely on the
projections feeding it — and those, as I explain in the fantasy guide, are a modest improvement
over a simple baseline, not a crystal ball.

It's also worth being honest about variance. A single nine-player lineup is a high-variance bet
even when every projection is good: football is noisy, one injury or blowout can sink a roster, and
a projection that's right *on average* across many players will still be badly wrong on a few of
them any given week. That's the nature of the game, not a flaw in the tool — but it's the reason I
treat a good lineup as a sensible starting point rather than a strong claim about that weekend.

There is one real weakness I want to name plainly: team defenses. My weekly model projects the
skill positions, but I don't have a dedicated defense projection yet, so the optimizer falls back
to a season-average number for defenses. That means the defense slot is the least-informed pick in
every lineup. It's on the list to fix.

The tool is also built for a single best lineup, not for large tournaments. Tournament play rewards
building many *different* lineups and picking less-popular players on purpose; this optimizer
doesn't do either of those yet. So it's genuinely useful for cash-style single-lineup play and as a
starting point, but it is not a tournament engine.

## The rules and fences, and why they exist

- **The optimizer is only as good as its projections.** It doesn't judge players — it arranges
  them. Every honest claim about lineup quality has to point back to the projection model, not to
  the solver.
- **The DraftKings export format is exact.** The upload has to be one column per roster slot in the
  right order, or DraftKings rejects it. This is worth guarding because a subtly wrong export looks
  fine and fails silently at upload time.
- **The projections come from `fantasy/fantasy_projections/` and nowhere else** — the same path the
  fantasy model writes to. The two tools are joined at that file.
- **The defense slot uses a season-average fallback,** and I say so rather than pretending it's
  modeled. Naming the weak spot is better than hiding it.
- **This is a single-lineup optimizer, not a tournament generator.** I don't claim tournament
  features (many diverse lineups, opponent-popularity leverage) that aren't built yet.

The short version: a correct, reliable tool that builds the best legal DraftKings lineup from my
projections — useful as far as the projections are, honest about the defense gap, and not yet a
tournament engine.
