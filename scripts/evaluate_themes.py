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
"""

from __future__ import annotations

import argparse
import logging
import os
import random
import statistics
import sys
import time
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
from src.gridgpt.theme_manager import ThemeManager  # noqa: E402
from src.gridgpt.word_database_manager import WordDatabaseManager  # noqa: E402

DEFAULT_THEMES = ["food", "space", "music"]
TEMPLATE_IDS = ["5x5_blocked_corners", "5x5_bottom_pillars", "5x5_diagonal_cut"]

# theme -> (seed_entry, {WORD: cosine})
PreparedThemes = Dict[str, Tuple[Optional[str], Dict[str, float]]]


def prepare_themes(themes: List[str], word_db, threshold: float = 0.35) -> PreparedThemes:
    """Score every word against each theme (one embedding call per theme).
    Returns {theme: (seed_entry, {WORD: cosine})}."""
    prepared: PreparedThemes = {}
    for theme in themes:
        seed_entry, similarities = ThemeManager(theme, word_db).prepare_theme(
            threshold=threshold, weigh_similarity=True, min_chars=5, max_chars=5, min_frequency=1,
        )
        prepared[theme] = (seed_entry, similarities)
    return prepared


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
    prepared = prepare_themes(args.themes, word_db)

    if args.tune:
        print(f"\nTheme parameter tuning (rng-seed={args.rng_seed})")
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
