#!/usr/bin/env python3
"""Refresh the word database and embedding cache end to end.

One command to bring GridGPT's data fully up to date:

1. detect the gap between the newest scraped NYT mini date and today,
2. scrape the missing dates (merged into the existing clues file),
3. rebuild the full word database,
4. regenerate the filtered word list,
5. force-rebuild the embedding cache so it matches the new word list.

This is the *only* command that should trigger embedding calls. Normal startup
and the dev servers never re-embed when the cache is already present, so running
the API does not cost anything or rebuild anything.

Usage:
    python -m scripts.refresh_database                 # auto-detect the gap and refresh
    python -m scripts.refresh_database --dry-run       # report the plan, change nothing
    python -m scripts.refresh_database --force         # rebuild embeddings even with no new data
    python -m scripts.refresh_database --start-date 2026-07-01 --end-date 2026-07-21
    python -m scripts.refresh_database --skip-embeddings

Needs OPENAI_API_KEY for the embedding step. After a real refresh, commit
`word_database_full.json` so the change reaches production: it is the one tracked
data artifact, and Railway rebuilds the word list + embeddings from it on deploy.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import date, datetime, timedelta
from typing import Optional, Tuple

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(REPO_ROOT)

from src.gridgpt.utils import init_logging, load_catalog  # noqa: E402

DATE_FMT = "%Y-%m-%d"


def _latest_scraped_date(clues_path: str) -> Optional[date]:
    """Newest date key in the merged clues file, or None if the file is missing
    or empty. Keys are `YYYY-MM-DD`; unparseable keys are skipped."""
    if not os.path.exists(clues_path):
        return None
    with open(clues_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    parsed = []
    for key in data:
        try:
            parsed.append(datetime.strptime(key, DATE_FMT).date())
        except (ValueError, TypeError):
            continue
    return max(parsed) if parsed else None


def _resolve_range(
    start_date: Optional[str], end_date: Optional[str], clues_path: str
) -> Optional[Tuple[str, str]]:
    """Return the (start, end) date strings to scrape, or None if nothing to do.

    Explicit --start-date/--end-date win. Otherwise scrape from the day after the
    newest scraped date through today.
    """
    if start_date and end_date:
        return start_date, end_date
    latest = _latest_scraped_date(clues_path)
    if latest is None:
        return None
    today = date.today()
    if latest >= today:
        return None
    return (latest + timedelta(days=1)).strftime(DATE_FMT), today.strftime(DATE_FMT)


def _scrape(start: str, end: str) -> None:
    from src.scraper.worddb import WordDBScraper

    scraper = WordDBScraper()
    data = scraper.scrape_date_range(start_date=start, end_date=end)
    stats = scraper.get_statistics(data)
    print(
        f"[refresh-db] Scrape done: {stats['total_dates']} dates in file, "
        f"{stats['unique_answers']} unique answers."
    )


def _build_full_db() -> None:
    from scripts.create_worddb_database import main as build_full_db

    rc = build_full_db()
    if rc:
        raise SystemExit(rc)


def _regenerate_word_list() -> None:
    # Instantiating the manager rewrites the filtered DB and the frequency word
    # list from the current full DB (see WordDatabaseManager.__init__).
    from src.gridgpt.word_database_manager import WordDatabaseManager

    WordDatabaseManager()


def _rebuild_embeddings() -> int:
    # Reuse the precompute script with --force so the cache is rebuilt from the
    # freshly regenerated word list (single source of the build logic).
    cmd = [sys.executable, "-m", "scripts.precompute_embeddings", "--force", "--verbose"]
    return subprocess.run(cmd, cwd=REPO_ROOT).returncode


def main() -> int:
    init_logging()
    parser = argparse.ArgumentParser(
        description="Refresh the word database and embedding cache end to end."
    )
    parser.add_argument("--start-date", help="Scrape start date (YYYY-MM-DD); use with --end-date")
    parser.add_argument("--end-date", help="Scrape end date (YYYY-MM-DD); use with --start-date")
    parser.add_argument(
        "--force", action="store_true",
        help="Rebuild the word list and embeddings even if no new data was scraped",
    )
    parser.add_argument("--skip-embeddings", action="store_true", help="Skip the embedding rebuild step")
    parser.add_argument("--dry-run", action="store_true", help="Report the plan and change nothing")
    args = parser.parse_args()

    if bool(args.start_date) != bool(args.end_date):
        print("[refresh-db] error: pass both --start-date and --end-date, or neither.", file=sys.stderr)
        return 1

    try:  # embeddings need the OpenAI key
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    catalog = load_catalog()
    clues_path = catalog["scraped_data"]["worddb_com"]["file_path"]
    latest = _latest_scraped_date(clues_path)
    rng = _resolve_range(args.start_date, args.end_date, clues_path)

    if args.dry_run:
        print(f"[refresh-db] dry run. Latest scraped date: {latest}; today: {date.today()}.")
        if rng:
            print(f"[refresh-db]   would scrape {rng[0]} .. {rng[1]}, rebuild full DB, word list, embeddings.")
        elif args.force:
            print("[refresh-db]   no new data, but --force: would rebuild word list and embeddings.")
        else:
            print("[refresh-db]   nothing to do (up to date; pass --force to rebuild embeddings anyway).")
        return 0

    data_changed = False
    if rng:
        start, end = rng
        print(f"[refresh-db] Scraping {start} .. {end} (merges into {clues_path}) ...")
        _scrape(start, end)
        print("[refresh-db] Rebuilding full word database ...")
        _build_full_db()
        data_changed = True
    elif latest is None and not (args.start_date and args.end_date):
        print(
            "[refresh-db] No clues file or dates found; pass --start-date and --end-date to scrape.",
            file=sys.stderr,
        )
    else:
        print(f"[refresh-db] Clues already up to date (latest {latest}, today {date.today()}).")

    if data_changed or args.force:
        print("[refresh-db] Regenerating filtered word list ...")
        _regenerate_word_list()
        if args.skip_embeddings:
            print("[refresh-db] Skipping embedding rebuild (--skip-embeddings).")
        else:
            print("[refresh-db] Rebuilding embedding cache (this makes OpenAI embedding calls) ...")
            rc = _rebuild_embeddings()
            if rc != 0:
                print("[refresh-db] Embedding rebuild failed.", file=sys.stderr)
                return rc
    else:
        print("[refresh-db] No data change and no --force; word list and embeddings left as is.")

    if data_changed:
        print(
            "[refresh-db] Done. Remember to commit "
            f"{catalog['word_database']['full']['file_path']} so the change reaches production."
        )
    else:
        print("[refresh-db] Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
