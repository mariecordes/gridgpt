"""Precompute and cache word embeddings.

Usage (local):
    python scripts/precompute_embeddings.py \
        --model text-embedding-3-small \
        --data-dir data/02_intermediary/word_database \
        --word-list word_list_with_frequencies.json

Better (after `pip install -e .`):
    python -m scripts.precompute_embeddings --verbose

Environment:
    OPENAI_API_KEY must be set (or present in a .env file).

Exit codes:
    0 success / already up-to-date
    1 failure
"""

from __future__ import annotations

import argparse
import os
import sys
import time

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv  # type: ignore

from src.gridgpt.embedding_provider import OpenAIEmbeddingProvider  # type: ignore
from src.gridgpt.utils import init_logging  # type: ignore
from src.gridgpt.word_database_manager import WordDatabaseManager  # type: ignore


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Precompute word embeddings cache")
    # Model + cache filenames default to the `embeddings` block in parameters.yml
    # (single source of truth for runtime and build); pass --model to build a
    # specific model's cache (e.g. the large model for the A/B).
    p.add_argument("--model", default=None, help="Embedding model name (default: parameters.yml)")
    p.add_argument(
        "--data-dir",
        default=None,
        help="Directory containing/for word list & embedding cache (default: parameters.yml)",
    )
    p.add_argument(
        "--word-list",
        default=None,
        help="Word list JSON (frequency map) filename",
    )
    p.add_argument(
        "--embeddings-file",
        default=None,
        help="Output embeddings matrix filename (fp16; default: parameters.yml per model)",
    )
    p.add_argument(
        "--index-file",
        default=None,
        help="Word index metadata JSON filename (default: parameters.yml per model)",
    )
    p.add_argument(
        "--force",
        action="store_true",
        help="Rebuild even if existing files are present",
    )
    p.add_argument("--batch-size", type=int, default=1000, help="Batch size for embedding API calls")
    p.add_argument("--env-file", default=".env", help="Optional path to .env file to load")
    p.add_argument("--verbose", action="store_true", help="Verbose diagnostics")
    return p.parse_args()


def _load_env(env_file: str, verbose: bool):
    if load_dotenv and env_file and os.path.exists(env_file):
        load_dotenv(env_file)
        if verbose:
            print(f"[precompute] Loaded env file {env_file}")
    elif load_dotenv and env_file and not os.path.exists(env_file) and verbose:
        print(f"[precompute] No env file at {env_file} (continuing)")


def main() -> int:
    init_logging()
    args = parse_args()
    _load_env(args.env_file, args.verbose)

    # Resolve model + cache filenames from parameters.yml, letting CLI flags override.
    from src.gridgpt.utils import load_parameters  # type: ignore

    emb = load_parameters()["embeddings"]
    model = args.model or emb["model"]
    spec = emb["models"][model]
    data_dir = args.data_dir or emb.get("data_dir", "data/02_intermediary/word_database")
    word_list = args.word_list or "word_list_with_frequencies.json"
    embeddings_file = args.embeddings_file or spec["embeddings_file"]
    index_file = args.index_file or spec["index_file"]

    api_key = os.getenv("OPENAI_API_KEY")
    if args.verbose:
        preview = (api_key[:6] + "..." + api_key[-4:]) if api_key else None
        print(f"[precompute] Model={model} API key present={bool(api_key)} preview={preview}")

    if not api_key:
        print("[precompute] FAILED: OPENAI_API_KEY not set (export it or add to .env)", file=sys.stderr)
        return 1

    embeddings_path = os.path.join(data_dir, embeddings_file)
    index_path = os.path.join(data_dir, index_file)
    word_list_path = os.path.join(data_dir, word_list)

    # Ensure the word list (frequency map) exists; if missing, build via WordDatabaseManager
    if not os.path.exists(word_list_path):
        try:
            if args.verbose:
                print(f"[precompute] Word list missing at {word_list_path}; generating via WordDatabaseManager...")
            # Instantiate to trigger loading + filtering + frequency list creation (uses catalog paths)
            WordDatabaseManager()
            if not os.path.exists(word_list_path):
                # In case catalog path differs from expected -- attempt to copy/symlink if present elsewhere
                # The manager writes to catalog frequency path; ensure that's the same as requested path
                if args.verbose:
                    print("[precompute] WordDatabaseManager finished but expected word list still absent. Verify catalog path matches the word-list setting.")
                print(f"[precompute] FAILED: Word list still not found at {word_list_path}", file=sys.stderr)
                return 1
        except Exception as e:  # noqa: BLE001
            print(f"[precompute] FAILED generating word list: {e}", file=sys.stderr)
            return 1

    if not args.force and os.path.exists(embeddings_path) and os.path.exists(index_path):
        if args.verbose:
            print("[precompute] Cache already present – nothing to do.")
        return 0

    start = time.time()
    try:
        provider = OpenAIEmbeddingProvider(
            model=model,
            data_dir=data_dir,
            word_list_filename=word_list,
            embeddings_filename=embeddings_file,
            index_filename=index_file,
            batch_size=args.batch_size,
            create_if_missing=False,
        )
        provider._build_word_embeddings()  # pylint: disable=protected-access
        duration = time.time() - start
        print(f"[precompute] Done in {duration:.1f}s -> {embeddings_path}")
        return 0
    except Exception as e:  # noqa: BLE001
        print(f"[precompute] FAILED: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
