"""Evaluate the theme-weighting feature on the current fill algorithm.

Unlike scripts/evaluate_generation.py (which compares fill algorithms), this
script isolates the *theme* layer: for each theme it scores every word once (one
embedding call) and measures how on-theme the generated grids are. Needs
OPENAI_API_KEY.

It can do two things:

1. off-vs-on benchmark (default): generation with theme-weighting off vs on,
   reporting fill success, time, mean themeness of the filled words, and the
   count of on-theme words.
2. parameter tuning (--tune): a `boost` sweep (does favoring on-theme words
   harder actually change what gets chosen?) and a `visible_threshold` analysis
   (how many filled words get labeled on-theme at each cutoff).

The measurement functions (`theme_benchmark`, `boost_sweep`, `threshold_analysis`)
are importable so the walkthrough notebook can call them without reimplementing
the logic.

Usage:
    python -m scripts.evaluate_themes --themes food space music
    python -m scripts.evaluate_themes --tune --themes food music planets sports plants
    python -m scripts.evaluate_themes --anchors --themes food planets sports music
"""

from __future__ import annotations

import argparse
import logging
import os
import random
import statistics
import sys
import time
from collections import Counter
from typing import Dict, List, Optional, Tuple

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.gridgpt.crossword_generator import (  # noqa: E402
    generate_themed_crossword,
    normalized_themeness,
    DEFAULT_THEME_BOOST,
    DEFAULT_SIM_LOW,
    DEFAULT_SIM_HIGH,
    DEFAULT_VISIBLE_THRESHOLD,
)
from src.gridgpt.template_manager import load_templates, select_template  # noqa: E402
from src.gridgpt.theme_anchor import ThemeAnchorSelector  # noqa: E402
from src.gridgpt.theme_manager import ThemeManager  # noqa: E402
from src.gridgpt.utils import load_parameters  # noqa: E402
from src.gridgpt.word_database_manager import WordDatabaseManager  # noqa: E402

ANCHOR_TEMPLATE = "5x5_diagonal_cut"  # fixed template for anchor/diversity runs (3-to-5 letter slots)

DEFAULT_THEMES = ["food", "space", "music"]
TEMPLATE_IDS = ["5x5_blocked_corners", "5x5_bottom_pillars", "5x5_diagonal_cut"]

# theme -> (seed_entry, {WORD: cosine})
PreparedThemes = Dict[str, Tuple[Optional[str], Dict[str, float]]]


def prepare_themes(themes: List[str], word_db, threshold: float = 0.35, model: str = None) -> PreparedThemes:
    """Score every word against each theme (one embedding call per theme).
    `model` overrides the active embedding model from parameters.yml (for the
    small-vs-large A/B). Returns {theme: (seed_entry, {WORD: cosine})}."""
    prepared: PreparedThemes = {}
    for theme in themes:
        seed_entry, similarities = ThemeManager(theme, word_db, embedding_model=model).prepare_theme(
            threshold=threshold, weigh_similarity=True, min_chars=5, max_chars=5, min_frequency=1,
        )
        prepared[theme] = (seed_entry, similarities)
    return prepared


def top_theme_words(prepared: PreparedThemes, k: int = 15) -> Dict[str, List[str]]:
    """Top-k most similar DB words per theme: a qualitative on-theme / wrong-sense
    check (does the model rank genuinely on-theme words above noise?)."""
    return {
        theme: sorted(sims, key=sims.get, reverse=True)[:k]
        for theme, (_seed, sims) in prepared.items()
        if sims
    }


def theme_benchmark(
    prepared: PreparedThemes,
    templates: List[Dict],
    word_db,
    runs: int = 30,
    sim_low: float = DEFAULT_SIM_LOW,
    sim_high: float = DEFAULT_SIM_HIGH,
    visible_threshold: float = DEFAULT_VISIBLE_THRESHOLD,
    boost: float = DEFAULT_THEME_BOOST,
) -> List[Dict]:
    """Theme-weighting OFF vs ON per (theme, template).

    Returns one row dict per (theme, template, weight) with success, mean_ms,
    mean_themeness of the filled words, and the count of on-theme words.
    """
    rows: List[Dict] = []
    for theme, (seed_entry, similarities) in prepared.items():
        if not similarities:
            continue
        for template in templates:
            for weighting in (False, True):
                times_ms, successes, themeness_means, visible_counts = [], 0, [], []
                for _ in range(runs):
                    start = time.perf_counter()
                    crossword = generate_themed_crossword(
                        template, seed_entry,
                        theme_similarities=similarities if weighting else None,
                        theme_boost=boost, sim_low=sim_low, sim_high=sim_high,
                        word_db_manager=word_db,
                    )
                    times_ms.append((time.perf_counter() - start) * 1000.0)
                    if crossword is not None:
                        successes += 1
                        themeness = [
                            normalized_themeness(similarities.get(w), sim_low, sim_high)
                            for w in crossword["filled_slots"].values()
                        ]
                        themeness_means.append(statistics.mean(themeness))
                        visible_counts.append(sum(1 for t in themeness if t >= visible_threshold))
                rows.append({
                    "theme": theme,
                    "template": template["id"],
                    "weight": "on" if weighting else "off",
                    "success": successes / runs,
                    "mean_ms": statistics.mean(times_ms),
                    "mean_themeness": statistics.mean(themeness_means) if themeness_means else 0.0,
                    "on_theme_words": statistics.mean(visible_counts) if visible_counts else 0.0,
                })
    return rows


def boost_sweep(
    prepared: PreparedThemes,
    templates: List[Dict],
    word_db,
    boosts: Tuple[float, ...] = (0, 2, 4, 8, 16),
    runs: int = 15,
) -> List[Dict]:
    """Selection lever: mean raw cosine of the filled words per theme, across
    `boost` values (band-independent). Row per theme: {theme, 'boost=0': .., ...}."""
    rows: List[Dict] = []
    for theme, (seed_entry, similarities) in prepared.items():
        if not similarities:
            continue
        row = {"theme": theme}
        for boost in boosts:
            random.seed(1)  # same stream across boosts for a fair comparison
            cosines: List[float] = []
            for template in templates:
                for _ in range(runs):
                    crossword = generate_themed_crossword(
                        template, seed_entry, theme_similarities=similarities,
                        theme_boost=boost, word_db_manager=word_db,
                    )
                    cosines += [similarities[w] for w in crossword["filled_slots"].values() if w in similarities]
            row[f"boost={boost}"] = round(statistics.mean(cosines), 3)
        rows.append(row)
    return rows


def threshold_analysis(
    prepared: PreparedThemes,
    templates: List[Dict],
    word_db,
    thresholds: Tuple[float, ...] = (0.3, 0.4, 0.5, 0.6),
    runs: int = 15,
    sim_low: float = DEFAULT_SIM_LOW,
    sim_high: float = DEFAULT_SIM_HIGH,
    boost: float = DEFAULT_THEME_BOOST,
) -> Tuple[List[Dict], Dict[str, List[str]]]:
    """Labeling lever: average on-theme words per puzzle at each `visible_threshold`.

    Returns (rows, band_words): rows are {theme, 'vt=0.3': .., ...}; band_words maps
    each theme to the words that land in the 0.4-0.6 themeness band (the ones a
    threshold of 0.4 surfaces that 0.6 would miss).
    """
    rows: List[Dict] = []
    band_words: Dict[str, List[str]] = {}
    for theme, (seed_entry, similarities) in prepared.items():
        if not similarities:
            continue
        random.seed(2)
        counts = {vt: [] for vt in thresholds}
        in_band = set()
        for template in templates:
            for _ in range(runs):
                crossword = generate_themed_crossword(
                    template, seed_entry, theme_similarities=similarities,
                    theme_boost=boost, word_db_manager=word_db,
                )
                scored = [
                    (w, normalized_themeness(similarities.get(w), sim_low, sim_high))
                    for w in crossword["filled_slots"].values()
                ]
                for vt in thresholds:
                    counts[vt].append(sum(1 for _, t in scored if t >= vt))
                in_band |= {w for w, t in scored if 0.4 <= t < 0.6}
        rows.append({"theme": theme, **{f"vt={vt}": round(statistics.mean(counts[vt]), 1) for vt in thresholds}})
        band_words[theme] = sorted(in_band)
    return rows, band_words


def build_theme_pool(
    theme: str, word_db, candidate_pool: int, vetted_pool: int,
    allow_llm_words: bool, min_zipf: float, min_chars: int, max_chars: int,
) -> Tuple[List[str], List[str], Dict[str, float]]:
    """One LLM call per theme: cosine candidates -> vetted on-theme pool.
    Returns (pool, cosine_candidates, similarities)."""
    manager = ThemeManager(theme, word_db)
    similarities = manager.score_all_words()
    candidates = manager.get_anchor_candidates(
        pool_size=candidate_pool, min_chars=min_chars, max_chars=max_chars,
    )
    pool = ThemeAnchorSelector().select_anchors(
        theme, candidates, word_db, max_words=vetted_pool, allow_llm_words=allow_llm_words,
        min_zipf=min_zipf, min_chars=min_chars, max_chars=max_chars,
    )
    return pool, candidates, similarities


def anchor_benchmark(
    themes: List[str],
    word_db,
    template: Dict,
    runs: int = 30,
    candidate_pool: int = 60,
    vetted_pool: int = 30,
    max_anchors: int = 3,
    anchor_attempts: int = 25,
    allow_llm_words: bool = False,
    min_zipf: float = 2.5,
    min_chars: int = 3,
    max_chars: int = 5,
) -> Tuple[List[Dict], Dict[str, Dict]]:
    """Theme presence and puzzle variety, single seed vs vetted pool.

    For each theme, generates `runs` puzzles on one fixed template in two modes:

    - `single`: the legacy path, one fixed seed entry (`theme_entry`), which is
      what produced the same theme words every time.
    - `pool`: anchors sampled at random from the vetted pool (`theme_entries`).

    Per mode it reports how many theme words land, and how much the puzzles vary:
    distinct anchor sets is the key number (the fill is randomised either way, so
    distinct grids alone would flatter the single-seed baseline).

    Returns (rows, details) where details carries the pool, the candidates the LLM
    rejected, and the most repeated anchor words.
    """
    rows: List[Dict] = []
    details: Dict[str, Dict] = {}

    for theme in themes:
        pool, candidates, similarities = build_theme_pool(
            theme, word_db, candidate_pool, vetted_pool,
            allow_llm_words, min_zipf, min_chars, max_chars,
        )
        if not pool:
            continue
        # The legacy baseline pins one fixed DB word, mimicking the old behaviour.
        # It must be a word the legacy path can actually place: `place_theme_entry`
        # only uses the template's `theme_slots` whitelist, which holds 5-letter
        # slots only. (The multi-anchor path deliberately ignores that whitelist so
        # 3-to-5 letter anchors can land, which is what makes several fit.)
        theme_slot_ids = template.get("theme_slots", [])
        legacy_lengths = {
            slot["length"] for slot in template["slots"]
            if not theme_slot_ids or slot["id"] in theme_slot_ids
        }
        db_words = [
            w for w in pool
            if w in word_db.word_list_with_frequencies and len(w) in legacy_lengths
        ]
        baseline_seed = db_words[0] if db_words else None

        for mode in ("single", "pool"):
            if mode == "single" and baseline_seed is None:
                continue
            anchor_sets, grids, counts, times, successes = [], set(), Counter(), [], 0
            for run in range(runs):
                random.seed(run)  # same RNG stream for both modes
                start = time.perf_counter()
                if mode == "single":
                    crossword = generate_themed_crossword(
                        template, baseline_seed, theme_similarities=similarities,
                        word_db_manager=word_db,
                    )
                else:
                    crossword = generate_themed_crossword(
                        template, theme_entries=pool, theme_similarities=similarities,
                        word_db_manager=word_db, max_anchors=max_anchors,
                        anchor_attempts=anchor_attempts,
                    )
                times.append((time.perf_counter() - start) * 1000.0)
                if crossword is None:
                    continue
                successes += 1
                placed = sorted(crossword["seed_entries"].values())
                anchor_sets.append(frozenset(placed))
                counts.update(placed)
                grids.add(tuple(tuple(row) for row in crossword["grid"]))

            used = len(counts)
            rows.append({
                "theme": theme,
                "mode": mode,
                "pool": len(pool),
                "anchors": round(statistics.mean(len(s) for s in anchor_sets), 2) if anchor_sets else 0.0,
                "anchor_sets": f"{len(set(anchor_sets))}/{runs}",
                "words_used": used,
                "coverage": f"{used / len(pool):.0%}",
                "grids": f"{len(grids)}/{runs}",
                "success": f"{successes / runs:.0%}",
                "mean_ms": round(statistics.mean(times), 1) if times else 0.0,
            })
            if mode == "pool":
                details[theme] = {
                    "pool": pool,
                    "rejected": [c for c in candidates if c not in set(pool)],
                    "most_repeated": counts.most_common(3),
                }

    return rows, details


# ------------------------------ CLI printing ------------------------------ #

def _print_table(rows: List[Dict]) -> None:
    """Print a list of uniform row dicts as an aligned markdown-ish table."""
    if not rows:
        print("(no rows)")
        return
    cols = list(rows[0].keys())
    widths = {c: max(len(c), *(len(str(r[c])) for r in rows)) for c in cols}
    print("| " + " | ".join(f"{c:<{widths[c]}}" for c in cols) + " |")
    print("|" + "|".join("-" * (widths[c] + 2) for c in cols) + "|")
    for r in rows:
        print("| " + " | ".join(f"{str(r[c]):<{widths[c]}}" for c in cols) + " |")


def _print_theme_benchmark(rows: List[Dict]) -> None:
    header = (
        f"| {'theme':<10} | {'template':<22} | {'weight':<3} | {'success':>7} "
        f"| {'mean ms':>8} | {'mean themeness':>14} | {'theme words':>11} |"
    )
    print(header)
    print("|" + "-" * 12 + "|" + "-" * 24 + "|" + "-" * 5 + "|" + "-" * 9
          + "|" + "-" * 10 + "|" + "-" * 16 + "|" + "-" * 13 + "|")
    for r in rows:
        print(
            f"| {r['theme']:<10} | {r['template']:<22} | {r['weight']:<3} "
            f"| {r['success']*100:>6.0f}% | {r['mean_ms']:>8.1f} "
            f"| {r['mean_themeness']:>14.3f} | {r['on_theme_words']:>11.1f} |"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate the theme-weighting feature")
    parser.add_argument("--themes", nargs="*", default=DEFAULT_THEMES, help="Themes to evaluate")
    parser.add_argument("--templates", nargs="*", default=TEMPLATE_IDS, help="Template ids")
    parser.add_argument("--runs", type=int, default=30, help="Runs per configuration")
    parser.add_argument("--tune", action="store_true", help="Run the boost + visible-threshold sweeps instead of the off-vs-on benchmark")
    parser.add_argument("--anchors", action="store_true", help="Run the theme-anchor benchmark (theme words landed + puzzle variety)")
    parser.add_argument("--model", default=None, help="Embedding model override for the A/B (default: parameters.yml)")
    parser.add_argument("--rng-seed", type=int, default=0, help="Global RNG seed for reproducibility")
    args = parser.parse_args()

    logging.getLogger().setLevel(logging.ERROR)
    try:  # theme embeddings need the OpenAI key
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass
    random.seed(args.rng_seed)

    word_db = WordDatabaseManager()
    templates = [select_template(template_id=tid) for tid in args.templates]
    print(f"\nEmbedding model: {args.model or '(parameters.yml default)'}")

    if args.anchors:
        cfg = load_parameters()["theme_anchors"]
        template = select_template(template_id=ANCHOR_TEMPLATE)
        print(f"\nTheme anchors: words landed + puzzle variety "
              f"({args.runs} runs per mode, template {ANCHOR_TEMPLATE})\n")
        rows, details = anchor_benchmark(
            args.themes, word_db, template, runs=args.runs,
            candidate_pool=cfg["candidate_pool"], vetted_pool=cfg["vetted_pool"],
            max_anchors=cfg["max_anchors"], anchor_attempts=cfg["anchor_attempts"],
            allow_llm_words=cfg["allow_llm_words"], min_zipf=cfg["min_zipf"],
            min_chars=cfg["min_chars"], max_chars=cfg["max_chars"],
        )
        _print_table(rows)
        for theme, info in details.items():
            print(f"\n{theme}:")
            print(f"  vetted pool ({len(info['pool'])}): {info['pool']}")
            print(f"  rejected by the LLM (first 12 of {len(info['rejected'])}): {info['rejected'][:12]}")
            print(f"  most repeated anchors: {info['most_repeated']}")
        print()
        return 0

    prepared = prepare_themes(args.themes, word_db, model=args.model)

    if args.tune:
        print(f"\nTheme parameter tuning (rng-seed={args.rng_seed})")
        print("\n### top on-theme words per theme (most similar in the DB)\n")
        for theme, words in top_theme_words(prepared).items():
            print(f"  {theme:<9}: {words}")
        print("\n### boost sweep: mean raw cosine of filled words (band-independent)\n")
        _print_table(boost_sweep(prepared, templates, word_db))
        print("\n### visible_threshold: avg on-theme words per puzzle at each cutoff\n")
        rows, band_words = threshold_analysis(prepared, templates, word_db)
        _print_table(rows)
        print("\nwords in the 0.4-0.6 themeness band (surfaced at vt=0.4 but not vt=0.6):")
        for theme in prepared:
            if theme in band_words:
                print(f"  {theme:<9}: {band_words[theme][:12]}")
        print()
        return 0

    print(f"\nThemed fill benchmark: weighting off vs on ({args.runs} runs per config)\n")
    _print_theme_benchmark(theme_benchmark(prepared, templates, word_db, runs=args.runs))
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
