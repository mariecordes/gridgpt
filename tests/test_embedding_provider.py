import json

import numpy as np

from src.gridgpt.embedding_provider import OpenAIEmbeddingProvider


def test_word_list_stays_aligned_with_matrix(tmp_path):
    """get_word_list() must align with the embedding matrix rows even when the
    frequency file has drifted longer (the stale-cache bug that caused an
    IndexError -> 500 when the word database grew without a cache rebuild)."""
    # 3-row matrix + a matching 3-word index...
    matrix = np.zeros((3, 4), dtype=np.float16)
    np.save(tmp_path / "word_embeddings_fp16.npy", matrix)
    (tmp_path / "word_index.json").write_text(json.dumps({"words": ["AAA", "BBB", "CCC"]}))
    # ...but a deliberately LONGER frequency file, simulating DB growth.
    (tmp_path / "word_list_with_frequencies.json").write_text(
        json.dumps({"AAA": 1, "BBB": 1, "CCC": 1, "DDD": 1, "EEE": 1})
    )

    provider = OpenAIEmbeddingProvider(data_dir=str(tmp_path), create_if_missing=False)

    words = provider.get_word_list()
    # Aligns with the matrix (3), not the frequency file (5).
    assert words == ["AAA", "BBB", "CCC"]
    assert len(provider.get_word_list()) == provider.get_word_embeddings().shape[0]
