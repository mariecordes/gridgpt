"""Benchmark crossword grid generation.

Two modes:

1. Fill benchmark (default, no --themes): measures the fill algorithm directly,
   with no LLM or embedding calls, reporting fill success rate, generation time
   (mean, p50, p95), and validity violations (should always be zero). Themes are
   simulated with fixed *seed entries* (a real word pinned into a slot) to stress
   the fill. This is the mode used to compare fill algorithms (legacy vs current).

2. Theme benchmark (--themes): evaluates the *theme-weighting feature* on the
   current fill algorithm (no algorithm comparison). For each theme it scores every
   word against the theme (one embedding call) and runs generation with weighting
   off vs on, reporting how on-theme the filled words are (mean themeness and the
   count of on-theme words) next to success and time. Use this to judge and tune the
   theme feature. Needs OPENAI_API_KEY.

Usage:
    # Fill benchmark (offline): stress the fill / compare algorithms
    python -m scripts.evaluate_generation --runs 30
    python -m scripts.evaluate_generation --algorithm both --seeds APPLE MUSIC OCEAN

    # Theme benchmark (needs OPENAI_API_KEY): evaluate the theme feature only
    python -m scripts.evaluate_generation --themes food space music
"""

from __future__ import annotations

import argparse
import logging
import os
import statistics
import sys
import time
from typing import Callable, Dict, List, Optional, Tuple

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.gridgpt.crossword_generator import (  # noqa: E402
    generate_themed_crossword,
    normalized_themeness,
    DEFAULT_THEME_BOOST,
    DEFAULT_SIM_LOW,
    DEFAULT_SIM_HIGH,
)
from src.gridgpt.crossword_generator_legacy import generate_themed_crossword_legacy  # noqa: E402
from src.gridgpt.template_manager import load_templates  # noqa: E402
from src.gridgpt.theme_manager import ThemeManager  # noqa: E402
from src.gridgpt.word_database_manager import WordDatabaseManager  # noqa: E402

VISIBLE_THEMENESS = 0.6  # normalized themeness at/above which a filled word is "on-theme"

TEMPLATE_IDS = ["5x5_blocked_corners", "5x5_bottom_pillars", "5x5_diagonal_cut"]

GenerateFn = Callable[[Dict, Optional[str]], Optional[Dict]]


def validate_crossword(crossword: Optional[Dict], template: Dict, word_db) -> Tuple[bool, str]:
    """Return (is_valid, reason). A valid grid fills every slot with a distinct
    database word and has consistent letters at every intersection."""
    if crossword is None:
        return False, "no crossword produced"

    filled = crossword.get("filled_slots", {})
    if len(filled) != len(template["slots"]):
        return False, "not all slots filled"

    words = list(filled.values())
    if len(words) != len(set(words)):
        return False, "duplicate words"

    grid = crossword["grid"]
    for slot in template["slots"]:
        word = filled.get(slot["id"])
        if word is None:
            return False, f"slot {slot['id']} unfilled"
        if word not in word_db.word_list_with_frequencies:
            return False, f"'{word}' not in database"
        for i, (row, col) in enumerate(slot["cells"]):
            if grid[row][col] != word[i]:
                return False, f"intersection mismatch at {(row, col)}"
    return True, "ok"


def run_config(
    template: Dict, seed_entry: Optional[str], runs: int, generate_fn: GenerateFn, word_db
) -> Dict[str, float]:
    """Run one (template, seed) configuration `runs` times and collect stats."""
    times_ms: List[float] = []
    successes = 0
    first_violation = ""

    for _ in range(runs):
        start = time.perf_counter()
        try:
            crossword = generate_fn(template, seed_entry)
        except Exception as e:  # a failed generation should not raise, but guard the benchmark
            crossword = None
            if not first_violation:
                first_violation = f"exception: {e}"
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        times_ms.append(elapsed_ms)

        valid, reason = validate_crossword(crossword, template, word_db)
        if valid:
            successes += 1
        elif not first_violation:
            first_violation = reason

    times_ms.sort()
    return {
        "runs": runs,
        "success_rate": successes / runs,
        "mean_ms": statistics.mean(times_ms),
        "p50_ms": _percentile(times_ms, 50),
        "p95_ms": _percentile(times_ms, 95),
        "first_violation": first_violation,
    }


def _percentile(sorted_values: List[float], pct: float) -> float:
    if not sorted_values:
        return 0.0
    k = max(0, min(len(sorted_values) - 1, int(round((pct / 100.0) * (len(sorted_values) - 1)))))
    return sorted_values[k]


def pick_default_seeds(word_db, count: int = 3) -> List[str]:
    """Deterministically pick a few 5-letter database words to use as seeds."""
    five = sorted(word_db.words_by_length.get(5, []), key=lambda wf: (-wf[1], wf[0]))
    return [w for w, _ in five[:count]]


def build_generate_fn(algorithm: str, word_db, legacy_outer: int, legacy_inner: int) -> GenerateFn:
    """Return a `generate_fn(template, seed)` for the chosen algorithm.

    The legacy filler is given a bounded attempt budget so infeasible configs
    fail in a reasonable time instead of thrashing for ~50s at its 100x100
    default. The backtracking filler uses its own config in parameters.yml.
    """
    if algorithm == "legacy":
        return lambda template, seed: generate_themed_crossword_legacy(
            template, seed, max_attempts=legacy_outer,
            backtracking_max_attempts=legacy_inner, word_db_manager=word_db,
        )
    return lambda template, seed: generate_themed_crossword(
        template, seed, word_db_manager=word_db
    )


def run_benchmark(algorithm: str, args, word_db, templates_by_id, seeds) -> float:
    """Run all configs for one algorithm, print a table, return overall success."""
    generate_fn = build_generate_fn(algorithm, word_db, args.legacy_outer, args.legacy_inner)
    budget = f" (budget {args.legacy_outer}x{args.legacy_inner})" if algorithm == "legacy" else ""
    print(f"\n### {algorithm}{budget}  ({args.runs} runs per config)\n")
    header = f"| {'template':<22} | {'seed':<8} | {'success':>7} | {'mean ms':>8} | {'p50 ms':>7} | {'p95 ms':>7} |"
    sep = "|" + "-" * 24 + "|" + "-" * 10 + "|" + "-" * 9 + "|" + "-" * 10 + "|" + "-" * 9 + "|" + "-" * 9 + "|"
    print(header)
    print(sep)

    all_success: List[float] = []
    for template_id in args.templates:
        template = templates_by_id[template_id]
        for seed in seeds:
            stats = run_config(template, seed, args.runs, generate_fn, word_db)
            all_success.append(stats["success_rate"])
            seed_label = seed if seed else "(none)"
            print(
                f"| {template_id:<22} | {seed_label:<8} | {stats['success_rate']*100:>6.0f}% "
                f"| {stats['mean_ms']:>8.1f} | {stats['p50_ms']:>7.1f} | {stats['p95_ms']:>7.1f} |"
            )
            if stats["first_violation"] and stats["success_rate"] < 1.0:
                print(f"    ^ first failure: {stats['first_violation']}")

    overall = statistics.mean(all_success) * 100
    print(f"\n{algorithm} overall success rate: {overall:.1f}%")
    return overall


def run_themed_benchmark(args, word_db) -> None:
    """Compare theme-weighted fill OFF vs ON: fill success, time, and how on-theme
    the filled words are. Makes one theme-embedding call per theme (cached); the
    themeness of filled words is measured independently via the embedding provider."""
    templates_by_id = {t["id"]: t for t in load_templates()["templates"]}
    print(f"\n### themed fill: weighting off vs on ({args.runs} runs per config)\n")
    header = (
        f"| {'theme':<10} | {'template':<22} | {'weight':<3} | {'success':>7} "
        f"| {'mean ms':>8} | {'mean themeness':>14} | {'theme words':>11} |"
    )
    print(header)
    print("|" + "-" * 12 + "|" + "-" * 24 + "|" + "-" * 5 + "|" + "-" * 9
          + "|" + "-" * 10 + "|" + "-" * 16 + "|" + "-" * 13 + "|")

    for theme in args.themes:
        theme_manager = ThemeManager(theme, word_db)
        seed_entry, similarities = theme_manager.prepare_theme(
            threshold=0.35, weigh_similarity=True, min_chars=5, max_chars=5, min_frequency=1,
        )
        if not similarities:
            print(f"| {theme:<10} | (no embeddings available) |")
            continue

        for template_id in args.templates:
            template = templates_by_id[template_id]
            for weighting in (False, True):
                times_ms, successes, themeness_means, visible_counts = [], 0, [], []
                for _ in range(args.runs):
                    start = time.perf_counter()
                    crossword = generate_themed_crossword(
                        template, seed_entry,
                        theme_similarities=similarities if weighting else None,
                        theme_boost=DEFAULT_THEME_BOOST, sim_low=DEFAULT_SIM_LOW, sim_high=DEFAULT_SIM_HIGH,
                        word_db_manager=word_db,
                    )
                    times_ms.append((time.perf_counter() - start) * 1000.0)
                    if crossword is not None:
                        successes += 1
                        themeness = [
                            normalized_themeness(similarities.get(w), DEFAULT_SIM_LOW, DEFAULT_SIM_HIGH)
                            for w in crossword["filled_slots"].values()
                        ]
                        themeness_means.append(statistics.mean(themeness))
                        visible_counts.append(sum(1 for t in themeness if t >= VISIBLE_THEMENESS))

                mean_themeness = statistics.mean(themeness_means) if themeness_means else 0.0
                mean_visible = statistics.mean(visible_counts) if visible_counts else 0.0
                print(
                    f"| {theme:<10} | {template_id:<22} | {'on' if weighting else 'off':<3} "
                    f"| {successes/args.runs*100:>6.0f}% | {statistics.mean(times_ms):>8.1f} "
                    f"| {mean_themeness:>14.3f} | {mean_visible:>11.1f} |"
                )
    print()


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark crossword grid generation")
    parser.add_argument("--runs", type=int, default=30, help="Runs per configuration")
    parser.add_argument("--seeds", nargs="*", default=None, help="Seed entries (5-letter words)")
    parser.add_argument("--templates", nargs="*", default=TEMPLATE_IDS, help="Template ids")
    parser.add_argument(
        "--algorithm", choices=["legacy", "backtracking", "both"], default="backtracking",
        help="Which fill algorithm to benchmark",
    )
    parser.add_argument("--legacy-outer", type=int, default=20, help="Legacy outer attempt cap")
    parser.add_argument("--legacy-inner", type=int, default=50, help="Legacy inner attempt cap")
    parser.add_argument(
        "--themes", nargs="*", default=None,
        help="Real themes to evaluate theme-weighted fill (off vs on). Makes embedding calls.",
    )
    parser.add_argument("--rng-seed", type=int, default=0, help="Global RNG seed for reproducibility")
    args = parser.parse_args()

    # Keep the fill logs quiet so timing output stays readable.
    logging.getLogger().setLevel(logging.ERROR)

    # Themed mode needs the OpenAI key for theme embeddings; load it from .env.
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    import random

    random.seed(args.rng_seed)

    word_db = WordDatabaseManager()

    # Themed mode: measure the theme-weighting lift (needs embeddings).
    if args.themes:
        print(f"\nThemed fill benchmark (rng-seed={args.rng_seed})")
        run_themed_benchmark(args, word_db)
        return 0

    # Default mode: pure fill timing/success, no LLM or embedding calls.
    templates_by_id = {t["id"]: t for t in load_templates()["templates"]}
    seeds: List[Optional[str]] = [None] + (args.seeds or pick_default_seeds(word_db))

    print(f"\nGrid generation benchmark (rng-seed={args.rng_seed})")
    algorithms = ["legacy", "backtracking"] if args.algorithm == "both" else [args.algorithm]
    for algorithm in algorithms:
        run_benchmark(algorithm, args, word_db, templates_by_id, seeds)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
