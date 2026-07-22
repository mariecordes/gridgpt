import os
import json
import time
import logging
import threading
import numpy as np
from typing import List, Dict, Any

from openai import OpenAI

logger = logging.getLogger(__name__)


class EmbeddingProvider:
    """Interface-like base class for embedding providers."""

    def embed(self, texts: List[str]) -> np.ndarray:  # pragma: no cover - interface
        raise NotImplementedError


class OpenAIEmbeddingProvider(EmbeddingProvider):
    """Embedding provider that uses OpenAI API and caches word embeddings on disk.

    Strategy:
    - At startup, ensure precomputed embeddings file exists; if not, create it.
    - Expose an embed() method for theme strings (usually single item) producing a float32 vector.
    - Word embeddings are loaded from disk and exposed via get_word_embeddings().
    """

    def __init__(
        self,
        model: str = "text-embedding-3-small",
        data_dir: str = "data/02_intermediary/word_database",
        word_list_filename: str = "word_list_with_frequencies.json",
        embeddings_filename: str = "word_embeddings_fp16.npy",
        index_filename: str = "word_index.json",
        batch_size: int = 1000,
        api_key_env: str = "OPENAI_API_KEY",
        create_if_missing: bool = True,
        dimension: int = None,
    ):
        self.model = model
        self.data_dir = data_dir
        self.word_list_path = os.path.join(data_dir, word_list_filename)
        self.embeddings_path = os.path.join(data_dir, embeddings_filename)
        self.index_path = os.path.join(data_dir, index_filename)
        self.batch_size = batch_size
        self.api_key_env = api_key_env
        self._config_dimension = dimension
        # Internal state
        self._client = None  # lazy OpenAI client
        self._word_embeddings = None  # type: ignore
        self._word_list = None  # type: ignore
        self._lock = threading.Lock()
        self._loading = False

        if create_if_missing:
            self._ensure_embeddings_exist()

    @classmethod
    def from_config(cls, model: str = None, params: dict = None, create_if_missing: bool = True):
        """Build a provider from the `embeddings` block in parameters.yml.

        `model` overrides the active model in config (used for the small-vs-large
        A/B). Each model has its own cache files, so switching models never
        overwrites another model's cache.
        """
        from .utils import load_parameters

        params = params if params is not None else load_parameters()
        emb = params["embeddings"]
        model = model or emb["model"]
        spec = emb["models"][model]
        return cls(
            model=model,
            data_dir=emb.get("data_dir", "data/02_intermediary/word_database"),
            embeddings_filename=spec["embeddings_file"],
            index_filename=spec["index_file"],
            dimension=spec.get("dimension"),
            create_if_missing=create_if_missing,
        )

    # ----------------------------- Public API ----------------------------- #
    def embed(self, texts: List[str]) -> np.ndarray:
        """Return embeddings for given texts (float32)."""
        client = self._get_client()
        # OpenAI API expects a list; handle empty gracefully
        if not texts:
            return np.zeros((0, self.dimension), dtype=np.float32)
        response = client.embeddings.create(model=self.model, input=texts)
        vectors = [d.embedding for d in response.data]
        return np.array(vectors, dtype=np.float32)

    @property
    def dimension(self) -> int:
        # Infer from the loaded matrix, else the configured dimension, else the
        # text-embedding-3-small default.
        if self._word_embeddings is not None:
            return self._word_embeddings.shape[1]
        if self._config_dimension:
            return self._config_dimension
        return 1536

    def get_word_embeddings(self) -> np.ndarray:
        if self._word_embeddings is None:
            with self._lock:
                if self._word_embeddings is None:
                    self._load_embeddings()
        return self._word_embeddings  # type: ignore

    def get_word_list(self) -> List[str]:
        if self._word_list is None:
            # The word list must stay aligned with the embedding matrix rows, so
            # read the index the matrix was built from (word_index.json), not the
            # frequency file which is regenerated on every startup and can drift
            # out of sync (a longer list would index past the matrix -> crash).
            with open(self.index_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            # Store uppercase to match usage elsewhere
            self._word_list = [w.upper() for w in data.get("words", [])]
        return self._word_list

    # ---------------------------- Internal logic -------------------------- #
    def _get_client(self) -> Any:
        if self._client is None:
            api_key = os.getenv(self.api_key_env)
            if not api_key:
                raise RuntimeError(f"Missing OpenAI API key in env var {self.api_key_env}")
            self._client = OpenAI(api_key=api_key)
        return self._client

    def _ensure_embeddings_exist(self):
        if os.path.exists(self.embeddings_path) and os.path.exists(self.index_path):
            return
        # Build embeddings file
        self._build_word_embeddings()

    def _build_word_embeddings(self):
        if not os.path.isfile(self.word_list_path):
            raise FileNotFoundError(f"Word list file not found: {self.word_list_path}")
        with open(self.word_list_path, "r", encoding="utf-8") as f:
            freq_map: Dict[str, int] = json.load(f)
        words = list(freq_map.keys())
        # Keep original case for reference; we will store uppercase companion file
        total = len(words)
        client = self._get_client()
        vectors: List[np.ndarray] = []
        for start in range(0, total, self.batch_size):
            batch = words[start : start + self.batch_size]
            resp = client.embeddings.create(model=self.model, input=batch)
            batch_vecs = [np.array(d.embedding, dtype=np.float32) for d in resp.data]
            vectors.append(np.stack(batch_vecs, axis=0))
            # Simple throttling safety
            time.sleep(0.2)
        matrix = np.vstack(vectors)
        # Convert to float16 to save space
        matrix_fp16 = matrix.astype(np.float16)
        os.makedirs(self.data_dir, exist_ok=True)
        np.save(self.embeddings_path, matrix_fp16)
        with open(self.index_path, "w", encoding="utf-8") as f:
            json.dump({"words": words}, f)

    def _load_embeddings(self):
        if not os.path.exists(self.embeddings_path):
            raise FileNotFoundError(
                f"Embeddings file not found: {self.embeddings_path}. Set create_if_missing=True or run precompute script."
            )
        matrix_fp16 = np.load(self.embeddings_path, mmap_mode="r")
        # Keep fp16 internally; cast to float32 on demand if needed
        self._word_embeddings = matrix_fp16  # type: ignore
        # Load word index (for alignment/validation if needed)
        if os.path.exists(self.index_path):
            with open(self.index_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            stored_words = data.get("words", [])
            # Basic sanity check
            if len(stored_words) != self._word_embeddings.shape[0]:  # type: ignore
                raise ValueError("Word count and embedding rows mismatch")
            # Warn (never rebuild) if the cache has drifted from the current word
            # list, so a stale cache after a DB change is visible in the logs.
            try:
                if os.path.exists(self.word_list_path):
                    with open(self.word_list_path, "r", encoding="utf-8") as wf:
                        current = {w.upper() for w in json.load(wf).keys()}
                    cached = {w.upper() for w in stored_words}
                    if current != cached:
                        logger.warning(
                            "Embedding cache is out of sync with the word list "
                            "(%d cached vs %d current words). Run `make refresh-db` to rebuild.",
                            len(cached), len(current),
                        )
            except Exception:  # a diagnostic check must never break loading
                pass

    # ------------------------- Similarity Utilities ------------------------ #
    @staticmethod
    def cosine_similarity_batch(matrix: np.ndarray, vector: np.ndarray) -> np.ndarray:
        # matrix: (N, D), vector: (D,)
        # Ensure float32 for stability in cosine computation
        if matrix.dtype != np.float32:
            matrix = matrix.astype(np.float32)
        if vector.dtype != np.float32:
            vector = vector.astype(np.float32)
        denom = (np.linalg.norm(matrix, axis=1) * np.linalg.norm(vector) + 1e-12)
        return (matrix @ vector) / denom
