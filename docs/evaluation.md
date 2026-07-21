# Evaluation

This document records evaluations of GridGPT's generation pipeline: what was measured, the headline results, and how to reproduce them. It is a living document that grows as more of the pipeline is measured.

## Grid fill: greedy restart vs backtracking

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

