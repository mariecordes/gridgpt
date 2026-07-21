# Evaluation

This document records evaluations of GridGPT's generation pipeline: what was measured, the headline results, and how to reproduce them. It is a living document that grows as more of the pipeline is measured.

## 1. Grid fill: greedy restart vs backtracking

**What it is.** The grid filler places real database words into a template so that every crossing letter agrees (a constraint satisfaction problem). The original implementation used greedy fill with full restarts (fill every slot in one pass, and on the first dead end discard the whole grid and start over). It was replaced with a backtracking search using most-constrained-variable ordering, forward checking, and an indexed word list.

For a step-by-step walkthrough of how each algorithm works internally (not just the metrics), see [`notebooks/03_algorithm_comparison.ipynb`](../notebooks/03_algorithm_comparison.ipynb).


**How it was measured.** [`scripts/evaluate_generation.py`](../scripts/evaluate_generation.py) runs each algorithm on the same tasks (all 3 templates, with and without a pinned seed word) and reports fill success rate and generation time. It uses no LLM or embedding calls, so it isolates the fill itself; a fixed seed word stresses the fill exactly like a real theme entry does. Numbers below are representative (30 runs per configuration); the legacy filler is given a bounded attempt budget so its failures resolve in seconds rather than thrashing for tens of seconds.

You can use the following commands to reproduce the evaluation:

```bash
# Side-by-side benchmark of both algorithms
python -m scripts.evaluate_generation --algorithm both

# Just the current filler, more runs
python -m scripts.evaluate_generation --runs 50
```

**Results**

| | greedy restart (legacy) | backtracking (current) |
|---|---|---|
| fill success rate | ~67% (even given ~1000 attempts) | 100% |
| mean generation time | ~4,000 ms | ~1-3 ms |
| p95 generation time | ~6 s | ~6 ms |

Roughly a **1000x speedup** and a **jump from partial to complete reliability**. At the legacy filler's real production default (100 x 100 attempts), a single infeasible seed can spin for ~50 seconds before giving up; the backtracking filler returns in a couple of milliseconds. As a side effect, the backend test suite dropped from ~65 s to ~2 s once the generation tests stopped thrashing.

**Why?** Greedy restart discards all progress the moment one slot runs out of options, re-solving the easy part of the grid over and over. Backtracking undoes only the last placement and tries the next candidate, keeping all the good work. Three components make it fast and reliable:

1. **most-constrained-variable ordering** (fill the slot with the fewest options first), 
2. **forward checking** (reject a word immediately if it empties a crossing slot's options), and
3. **an indexed word list** (candidate lookup by set intersection instead of a scan).

## 2. Theme similarity: does theme-weighting shape the puzzle?

**What it is.** When a theme is set, GridGPT scores every database word against the theme (cosine similarity between the theme's embedding and the precomputed word embeddings) and folds that similarity into the fill's word-selection weights (`weight = frequency * (1 + boost * themeness)`), so on-theme words are tried first. It only reorders candidates, never removes them, so a themed puzzle is exactly as valid and reliable as an unthemed one; the theme just biases which valid grid gets chosen.

For a step-by-step walkthrough (scoring words, turning similarity into a weight, biasing the fill), see [`notebooks/04_theme_weighted_fill.ipynb`](../notebooks/04_theme_weighted_fill.ipynb).

**How it was measured.** [`scripts/evaluate_generation.py`](../scripts/evaluate_generation.py) in its theme mode (`--themes`, function `run_themed_benchmark`) scores every word against each theme once (one embedding call), then for each template runs generation with theme-weighting **off vs on** and reports fill success, generation time, the **mean themeness** of the filled words, and the **count of on-theme words** (themeness >= 0.6). Themeness is computed independently via the embedding provider, not by the code under test. Numbers below are 30 runs per configuration, averaged across the 3 templates. This mode needs `OPENAI_API_KEY`.

You can reproduce the evaluation with:

```bash
# Evaluate the theme feature only (off vs on), needs OPENAI_API_KEY
python -m scripts.evaluate_generation --themes food space music
```

**Results**

| theme | mean themeness (off -> on) | on-theme words / puzzle (off -> on) |
|---|---|---|
| space | 0.40 -> 0.42 | 2.4 -> 2.5 |
| music | 0.16 -> 0.17 | 0.1 -> 0.2 |
| food  | 0.13 -> 0.13 | 0.1 -> 0.0 |

Fill success stayed **100%** and generation stayed **~1-3 ms** in every case, on and off: because the weighting only reorders candidates, it never costs reliability or speed. The on-theme lift, though, is **small and highly theme-dependent**. "space" nudges up consistently; "music" barely moves; "food" is flat or within noise (the on-theme count even ticks down, which at this scale is just run-to-run variance).

**Why the ceiling is low.** The bottleneck is not the algorithm, it is the raw material. A 5x5 needs 3-to-5-letter words, and for most themes a ~10k-word database simply does not contain many short words that are strongly related to the theme. Even perfect selection can only choose from what is there: "space" happens to have enough near-theme short words to draw on, "food" does not. So the honest ceiling is "one to three extra on-theme words on a good theme", not a fully themed grid. Two knobs in `conf/base/parameters.yml` under `theme_fill` tune the strength: `boost` (how hard on-theme words are favored) and `sim_low` / `sim_high` (the cosine band that maps to themeness; lowering `sim_low` lets more loosely-related words count).

**A subtler limit: the numbers can label the wrong sense of the theme.** Cosine similarity measures semantic proximity, not what the user actually pictured, and short common words are often ambiguous. Ask for "space" and a person imagines STARS, MOON, SUN, EARTH; but the embedding also scores words tied to space-as-in-room, like AREA, FLOOR or METER, as highly related. Those come out labeled on-theme by the metric while missing the intended meaning, so a grid can be "on-theme" by the numbers yet feel off-theme to a solver. This is a qualitative, creative mismatch that a similarity threshold cannot see and that is hard to detect automatically. A stronger or more sense-aware embedding would help disambiguate, but the gap between literal semantic proximity and an intended theme is real regardless.

**Ways to push it further.** Themes are genuinely hard in this little space, and the most promising improvements attack the raw material rather than the selector:

- **Larger grids / longer entries** (7x7 and up): more slots and longer words, and longer words tend to be more distinctive and easier to relate to a theme.
- **A stronger embedding model** (e.g. `text-embedding-3-large`) or one better suited to single short words: the current signal on 3-to-5-letter words is weak and noisy, so a sharper similarity would make the boost actually bite.
- **LLM-suggested theme words**: ask an LLM for genuinely on-theme words (that exist in the database, or that we add to it), rather than trusting noisy cosine, so a themed puzzle is guaranteed some real theme entries.
- **A curated theme / category tagging of the word database**, turning "on-theme" into a verified lookup instead of a similarity guess.
- **Guaranteed multiple seeded theme entries**: pin two or three verified on-theme words as hard anchors so every themed puzzle has a few real theme words regardless of what the fill finds (a heavier placement constraint, deferred for now).

