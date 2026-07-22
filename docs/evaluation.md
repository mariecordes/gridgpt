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

### 2.1 Theme vs no theme evaluation

The first question is simply whether the feature does anything: does turning theme-weighting on actually pull more on-theme words into the grid, and does it cost any fill success or speed? To answer it we generate the same puzzles with weighting off and on and compare how on-theme the filled words are.

**How it was measured.** [`scripts/evaluate_themes.py`](../scripts/evaluate_themes.py) (function `theme_benchmark`) scores every word against each theme once (one embedding call), then for each template runs generation with theme-weighting **off vs on** and reports fill success, generation time, the **mean themeness** of the filled words, and the **count of on-theme words** (themeness >= 0.6). Themeness is computed independently via the embedding provider, not by the code under test. Numbers below are 30 runs per configuration, averaged across the 3 templates. This mode needs `OPENAI_API_KEY`.

You can reproduce the evaluation with:

```bash
# Evaluate the theme feature only (off vs on), needs OPENAI_API_KEY
python -m scripts.evaluate_themes --themes food space music
```

**Results**

| theme | mean themeness (off -> on) | on-theme words / puzzle (off -> on) |
|---|---|---|
| space | 0.40 -> 0.42 | 2.4 -> 2.5 |
| music | 0.16 -> 0.17 | 0.1 -> 0.2 |
| food  | 0.13 -> 0.13 | 0.1 -> 0.0 |

Fill success stayed **100%** and generation stayed **~1-3 ms** in every case, on and off: because the weighting only reorders candidates, it never costs reliability or speed. The on-theme lift, though, is **small and highly theme-dependent**. "space" nudges up consistently; "music" barely moves; "food" is flat or within noise (the on-theme count even ticks down, which at this scale is just run-to-run variance).

**Assessment**

Why is the ceiling this low? The bottleneck is not the algorithm, it is the raw material. A 5x5 needs 3-to-5-letter words, and for most themes a ~10k-word database simply does not contain many short words that are strongly related to the theme. Even perfect selection can only choose from what is there: "space" happens to have enough near-theme short words to draw on, "food" does not. So the honest ceiling is "one to three extra on-theme words on a good theme", not a fully themed grid. Two knobs in `conf/base/parameters.yml` under `theme_fill` tune the strength: `boost` (how hard on-theme words are favored) and `sim_low` / `sim_high` (the cosine band that maps to themeness; lowering `sim_low` lets more loosely-related words count).

### 2.2 Tuning the theme selection

The theme behavior has two levers: 
1. *selection* (`boost`, and the `sim_low` / `sim_high` band), which changes which words the fill prefers, and
2. *labeling* (`visible_threshold`), which changes only which filled words get reported as on-theme. 

A sweep across five themes (`python -m scripts.evaluate_themes --tune --themes food music planets sports plants`; walkthrough in [`notebooks/04_theme_weighted_fill.ipynb`](../notebooks/04_theme_weighted_fill.ipynb)) shows where each helps.

**Results & Assessment**

`boost` barely moves selection: the mean raw cosine of the filled words is nearly flat from `boost=0` to `boost=16`.

| theme | boost=0 | boost=2 | boost=4 | boost=8 | boost=16 |
|---|---|---|---|---|---|
| food | 0.223 | 0.227 | 0.225 | 0.233 | 0.233 |
| music | 0.250 | 0.252 | 0.253 | 0.254 | 0.253 |
| planets | 0.224 | 0.224 | 0.223 | 0.229 | 0.233 |
| sports | 0.265 | 0.270 | 0.276 | 0.272 | 0.272 |
| plants | 0.201 | 0.210 | 0.207 | 0.203 | 0.206 |

That is the vocabulary ceiling again: favoring on-theme words harder cannot help when there are barely any to favor. `boost=4` is fine; cranking it is not worth it.

`visible_threshold` is the knob that actually matters for what the solver sees. Because themeness is the raw cosine clipped to `[sim_low, sim_high]`, each threshold maps to a raw-cosine cutoff (with the 0.20/0.50 band: 0.6 -> 0.38, 0.5 -> 0.35, 0.4 -> 0.32). At the default 0.6 several themes label almost nothing; dropping to 0.4 roughly doubles the labeled words, showing the average on-theme words per puzzle:

| theme | vt=0.3 | vt=0.4 | vt=0.5 | vt=0.6 |
|---|---|---|---|---|
| food | 1.7 | 1.2 | 1.1 | 0.0 |
| music | 2.4 | 1.6 | 1.2 | 0.1 |
| planets | 1.3 | 1.1 | 1.0 | 1.0 |
| sports | 3.2 | 2.2 | 1.7 | 1.3 |
| plants | 1.2 | 1.1 | 1.0 | 1.0 |

The words 0.4 surfaces are a mix of genuinely related (BEETS, SALAD, CHEFS for food; DRAMA, IMAGE for music; SUN for planets; ARENA, ASICS for sports; GREEN for plants) and noise (FOR, MSN, ASS, and assorted short abbreviations). Given a preference for showing a few theme words over none, **`visible_threshold = 0.4`** is the better default here; 0.5 is a cleaner middle ground. `boost` and the `sim_low` / `sim_high` band are best left at their defaults (4, and 0.20 / 0.50).

### 2.3 Embedding model: small vs large

`text-embedding-3-small` (1536-dim) was the original model. We rebuilt the word cache with `text-embedding-3-large` (3072-dim) and compared them on the same six themes. The active model lives in `conf/base/parameters.yml` (`embeddings.model`), and each model keeps its own cache files, so both coexist and switching never overwrites the other.

**How it was compared.** `python -m scripts.evaluate_themes --tune --model text-embedding-3-large` (vs `--model text-embedding-3-small`). The decisive view is the **top on-theme words** each model ranks highest in the database per theme, a direct read on the "wrong sense" problem. The numeric sweeps (boost, visible_threshold) are per-model and are **not** directly comparable across models: the raw-cosine scale and the `[sim_low, sim_high]` band differ between the two embedding spaces, so treat those tables as within-model tuning, not cross-model scores.

**Result: large ranks genuinely on-theme words higher, especially where small was fooled by spelling.** 

Representative top matches:

| theme | small (top matches) | large (top matches) |
|---|---|---|
| planets | PLUTO, EARTH, VENUS, MARS, but also **PLANA, PLANS, PLATO** | PLUTO, VENUS, EARTH, ORBIT, **STARS, SOLAR, SKIES, SUNS, COSMO** |
| plants | PLANT, SEEDS, BULBS, TREE, but also **PLY, RAFT** | PLANT, **FERNS, HERBS, FLORA, WEEDS, SHRUB, CROPS, CACTI, FUNGI** |
| food | FOOD, BREAD, MEALS, MEAT, FEED/FEEDS | FOOD, **PIZZA, SUSHI, SNACK, LUNCH**, CHOW, DIET |

For "planets" and "plants" the win is clear: small surfaces spelling-similar noise (PLANA / PLANS / PLATO from "plan...", PLY / RAFT), while large replaces it with real astronomy (STARS, SOLAR, SUNS) and botany (FERNS, HERBS, FLORA). "food", "music", and "sports" are comparable, with large leaning toward more concrete, varied words.

**What large does not fix: genuinely ambiguous one-word themes.** Ask for "space" and both models rank the room/area sense (SPAN, PLACE, AREA, SPA) above the outer-space sense; neither surfaces STARS or GALAXY at the top. That ambiguity is in the query, not the model, and a sharper embedding cannot resolve it without more context (the same limit described in 2.4).

**Cost.** Large is 3072-dim, so the cache roughly doubles (~31 MB to ~62 MB) and is rebuilt on each deploy; the one-time build was ~49 s and a fraction of a cent, and the per-request cost is unchanged (still one theme phrase embedded).

**Action taken: switched the default from `text-embedding-3-small` to `text-embedding-3-large`.** The cleaner on-theme ranking directly serves the goal of surfacing real theme words, and the extra storage and build time are negligible for a hobby project. The active model is set in `conf/base/parameters.yml` (`embeddings.model`), and the small cache is kept on disk so the switch is reversible without a rebuild. The `[sim_low, sim_high]` band was left at the small-calibrated 0.20 / 0.50; a light re-tune for large's distribution remains a possible follow-up, since the visible-threshold behavior is similar in magnitude.

### 2.4 Further analysis and potential improvements

**A subtler limit: the numbers can label the wrong sense of the theme.** Cosine similarity measures semantic proximity, not what the user actually pictured, and short common words are often ambiguous. Ask for "space" and a person imagines STARS, MOON, SUN, EARTH; but the embedding also scores words tied to space-as-in-room, like AREA, FLOOR or METER, as highly related. Those come out labeled on-theme by the metric while missing the intended meaning, so a grid can be "on-theme" by the numbers yet feel off-theme to a solver. This is a qualitative, creative mismatch that a similarity threshold cannot see and that is hard to detect automatically. A stronger or more sense-aware embedding would help disambiguate, but the gap between literal semantic proximity and an intended theme is real regardless.

**Ways to push it further.** Themes are genuinely hard in this little space, and the most promising improvements attack the raw material rather than the selector:

- **Larger grids / longer entries** (7x7 and up): more slots and longer words, and longer words tend to be more distinctive and easier to relate to a theme.
- **A stronger embedding model:** `text-embedding-3-large` was tested and adopted (see 2.3); it sharpens the on-theme ranking but does not resolve ambiguous one-word themes. An embedding purpose-built for single short words could help further.
- **LLM-suggested theme words**: ask an LLM for genuinely on-theme words (that exist in the database, or that we add to it), rather than trusting noisy cosine, so a themed puzzle is guaranteed some real theme entries.
- **A curated theme / category tagging of the word database**, turning "on-theme" into a verified lookup instead of a similarity guess.
- **Guaranteed multiple seeded theme entries**: pin two or three verified on-theme words as hard anchors so every themed puzzle has a few real theme words regardless of what the fill finds (a heavier placement constraint, deferred for now).

## 3. Theme anchors: how many theme words, and how varied are the puzzles?

**What it is.** Weighting alone (section 2) left every themed puzzle with exactly **one** guaranteed theme word, the single pinned seed, and any extra on-theme word was incidental and often weak (for "food", FUN). Theme anchors replace that with a four-step pipeline: score every database word against the theme (cosine), have an LLM vet the top candidates down to genuinely on-theme words, draw a few of those at random, and pin them into the grid before filling around them.

Three separate sizes in `conf/base/parameters.yml` under `theme_anchors` control it, and keeping them separate is the whole point:

| setting | meaning | default |
|---|---|---|
| `candidate_pool` | how many cosine-ranked words the LLM is shown | 60 |
| `vetted_pool` | how many on-theme words the LLM may return (the pool to draw from) | 30 |
| `max_anchors` | how many anchors are actually pinned into one grid | 3 |
| `anchor_attempts` | random draws tried per anchor count before using fewer | 25 |

The vetted pool is deliberately large and **unranked**: once the LLM certifies a word as on-theme it counts exactly as much as any other, so the generator samples from the pool at random. When these were a single number, the LLM returned only three words and the generator walked them in a fixed best-first order, so one theme always produced the same puzzle.

For a step-by-step walkthrough of the pipeline (including the actual LLM prompt and the validation guardrails), see [`notebooks/05_multi_anchor_theme_entries.ipynb`](../notebooks/05_multi_anchor_theme_entries.ipynb).

**How it was measured.** [`scripts/evaluate_themes.py`](../scripts/evaluate_themes.py) (function `anchor_benchmark`) generates 30 puzzles per theme on one fixed template (`5x5_diagonal_cut`, which has 3-, 4- and 5-letter slots) in two modes: `single` is the legacy path with one fixed seed entry, and `pool` is the current path sampling anchors from the vetted pool. Both share the same RNG stream. Reproduce with:

```bash
python -m scripts.evaluate_themes --anchors --themes food planets sports music
```

**Results**

| theme | mode | pool | anchors | anchor sets | words used | coverage | grids | success | mean ms |
|---|---|---|---|---|---|---|---|---|---|
| food | single | 30 | 1.00 | 1/30 | 1 | 3% | 27/30 | 100% | 1.2 |
| food | pool | 30 | 2.33 | 29/30 | 24 | 80% | 30/30 | 100% | 1.7 |
| planets | single | 29 | 1.00 | 1/30 | 1 | 3% | 30/30 | 100% | 1.2 |
| planets | pool | 29 | 2.53 | 30/30 | 24 | 83% | 30/30 | 100% | 1.3 |
| sports | single | 30 | 1.00 | 1/30 | 1 | 3% | 30/30 | 100% | 1.1 |
| sports | pool | 30 | 2.53 | 30/30 | 26 | 87% | 30/30 | 100% | 1.7 |
| music | single | 30 | 1.00 | 1/30 | 1 | 3% | 30/30 | 100% | 1.3 |
| music | pool | 30 | 2.17 | 30/30 | 23 | 77% | 30/30 | 100% | 1.4 |

- `mode` states if only a `single` theme word was placed as a seed entry or if a `pool` of theme words was tried
- `pool` is the number of theme words available to be used as theme entries upon grid generation
- `anchors` is the mean number of successfully pinned theme words per generated puzzle
- `anchor sets` counts distinct anchor combinations (combinations of successfully pinned theme entries) across the 30 runs
- `words used` and `coverage` show how much of the vetted theme entry candidate pool actually gets exercised.

**Assessment**

**Theme presence roughly doubled**, from exactly 1 word per puzzle to **2.2-2.5**, and three anchors do land when a drawn trio happens to co-fill.

**Variety went from none to near-total.** Distinct anchor sets went from **1/30 to 29-30/30**, and pool coverage from 3% to **77-87%**, so a theme now draws on roughly two dozen different words across runs instead of the same one.

**The `grids` column is why "distinct grids" is the wrong headline metric.** The single-seed baseline already scored 27-30/30 distinct grids, because the fill is randomised regardless. Judged on grids alone the old behaviour looks fine; it is `anchor sets` (1/30) that exposes the real problem, since the *theme words* never changed. That is the number to watch.

**It costs nothing.** Fill success stays 100% and generation stays 1-2 ms in both modes: the extra work is a handful of cheap redraws, and a draw that cannot fill is simply replaced.

**The LLM is doing real filtering.** From the "food" candidates it rejected FUN, along with GOODS, FAST, STUFF and SPORT, while keeping PIZZA, SUSHI, BREAD, PASTA, SALAD and CHEF. That judgement is what cosine alone could not provide.

**A deliberate divergence worth noting:** every template's `theme_slots` whitelist contains only 5-letter slots (`5x5_diagonal_cut` has just two). The legacy path honours that whitelist, which is why it can only ever pin one 5-letter seed. Multi-anchor placement ignores it and uses any slot of matching length, which is precisely what lets 3- and 4-letter anchors land and several fit at once. If `theme_slots` is later meant to encode design intent about where theme entries belong, that intent is currently not applied to anchors.

**Limits.** Three anchors are not guaranteed; two is the typical outcome, because pinning three words in a 5x5 often leaves a crossing no database word can complete. Coverage is bounded by `vetted_pool`, and the pools include foreign-language database entries (ESSEN, CARNE, MONDE) that are genuinely on-theme but may read as obscure to a solver.

