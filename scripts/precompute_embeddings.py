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

try:
    from dotenv import load_dotenv  # type: ignore
except ImportError:  # pragma: no cover
    load_dotenv = None

try:
    from src.gridgpt.embedding_provider import OpenAIEmbeddingProvider  # type: ignore
except ImportError as imp_err:  # pragma: no cover
    print("[precompute] Import error:", imp_err, file=sys.stderr)
    print("[precompute] Did you run 'pip install -e .' or 'make develop'?", file=sys.stderr)
    raise


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Precompute word embeddings cache")
    p.add_argument("--model", default="text-embedding-3-small", help="Embedding model name")
    p.add_argument(
        "--data-dir",
        default="data/02_intermediary/word_database",
        help="Directory containing/for word list & embedding cache",
    )
    p.add_argument(
        "--word-list",
        default="word_list_with_frequencies.json",
        help="Word list JSON (frequency map) filename",
    )
    p.add_argument(
        "--embeddings-file",
        default="word_embeddings_fp16.npy",
        help="Output embeddings matrix filename (fp16)",
    )
    p.add_argument(
        "--index-file",
        default="word_index.json",
        help="Word index metadata JSON filename",
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
    args = parse_args()
    _load_env(args.env_file, args.verbose)

    api_key = os.getenv("OPENAI_API_KEY")
    if args.verbose:
        preview = (api_key[:6] + "..." + api_key[-4:]) if api_key else None
        print(f"[precompute] Model={args.model} API key present={bool(api_key)} preview={preview}")

    if not api_key:
        print("[precompute] FAILED: OPENAI_API_KEY not set (export it or add to .env)", file=sys.stderr)
        return 1

    embeddings_path = os.path.join(args.data_dir, args.embeddings_file)
    index_path = os.path.join(args.data_dir, args.index_file)

    if not args.force and os.path.exists(embeddings_path) and os.path.exists(index_path):
        if args.verbose:
            print("[precompute] Cache already present – nothing to do.")
        return 0

    start = time.time()
    try:
        provider = OpenAIEmbeddingProvider(
            model=args.model,
            data_dir=args.data_dir,
            word_list_filename=args.word_list,
            embeddings_filename=args.embeddings_file,
            index_filename=args.index_file,
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
