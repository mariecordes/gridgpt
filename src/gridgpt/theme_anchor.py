import json
import logging
from typing import List

from .llm_connection import LLMConnection
from .utils import load_prompts

logger = logging.getLogger(__name__)


class ThemeAnchorSelector(LLMConnection):
    """Select theme anchor words from a pool of cosine candidates.

    An LLM vets which candidates are genuinely on-theme (and, when
    `allow_llm_words` is on, may suggest its own words); a two-tier validation
    then keeps only real, fair words:

    - Tier 1 (both modes): a word in the word database passes. It is a real
      published crossword answer, so this also drops anything the LLM
      hallucinates while `allow_llm_words` is off.
    - Tier 2 (own words only): a word not in the database passes only when
      `allow_llm_words` is on and it is letters-only, in the usable length range,
      and common enough (wordfreq Zipf >= `min_zipf`).

    With no LLM connection, it falls back to the candidates' cosine order
    (DB-only, unvetted), mirroring how clue generation degrades to retrieval.
    """

    def __init__(self):
        LLMConnection.__init__(self)
        self.prompt = load_prompts()["theme_anchor_selector"]

    def select_anchors(
        self,
        theme: str,
        candidates: List[str],
        word_db_manager,
        max_words: int = 30,
        allow_llm_words: bool = False,
        min_zipf: float = 2.5,
        min_chars: int = 3,
        max_chars: int = 5,
    ) -> List[str]:
        """Return the validated pool of on-theme words (up to `max_words`).

        This is a *pool*, not a ranking: once a word is vetted as on-theme it is
        treated as exactly as good as any other in the pool, and the generator
        samples from it at random. That is what keeps repeated generations for the
        same theme from producing the same puzzle. How many of these actually get
        pinned into a grid is decided later by `max_anchors`.
        """
        candidates = [c.strip().upper() for c in candidates if c and c.strip()]

        # 1. LLM vetting, or fall back to the cosine candidates.
        if self.llm_connection_success and candidates:
            try:
                vetted = self._request_anchor_words(theme, candidates, max_words, allow_llm_words)
            except Exception as e:  # noqa: BLE001 - any LLM/parse failure degrades gracefully
                logger.error(f"Theme anchor selection failed ({e}); falling back to cosine order.")
                vetted = candidates
        else:
            vetted = candidates

        # 2. Two-tier validation, de-duping.
        word_list = word_db_manager.word_list_with_frequencies
        anchors: List[str] = []
        for word in vetted:
            w = word.strip().upper()
            if not w or w in anchors:
                continue
            if self._in_database(w, word_list):  # Tier 1
                anchors.append(w)
            elif allow_llm_words and self._is_valid_own_word(w, min_zipf, min_chars, max_chars):  # Tier 2
                anchors.append(w)
            if len(anchors) >= max_words:
                break
        return anchors

    def _request_anchor_words(
        self,
        theme: str,
        candidates: List[str],
        max_words: int,
        allow_llm_words: bool,
        min_chars: int = 3,
        max_chars: int = 5,
    ) -> List[str]:
        """One LLM call returning a {"words": [...]} list of on-theme words."""
        own_words_instruction = (
            self.prompt["own_words_instructions_llm_allowed"].format(
                min_chars=min_chars,
                max_chars=max_chars,
            )
            if allow_llm_words else
            self.prompt["own_words_instructions_llm_not_allowed"]
        )
        user_prompt = self.prompt["user_prompt"].format(
            theme=theme,
            candidates="\n".join(f"- {c}" for c in candidates),
            max_words=max_words,
            own_words_instruction=own_words_instruction,
        )
        response = self.llm.chat.completions.create(
            model=self.model_name,
            messages=[
                {"role": "system", "content": self.prompt["system_prompt"]},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.3,
            response_format={"type": "json_object"},
        )
        data = json.loads(response.choices[0].message.content)
        words = data.get("words", []) if isinstance(data, dict) else []
        if not isinstance(words, list):
            raise ValueError("Theme anchor response 'words' was not a list")
        return [str(w).strip().upper() for w in words if str(w).strip()]

    @staticmethod
    def _in_database(word: str, word_list) -> bool:
        return word in word_list or word.lower() in word_list

    @staticmethod
    def _is_valid_own_word(word: str, min_zipf: float, min_chars: int, max_chars: int) -> bool:
        """A non-DB word is acceptable only if it is a real, common English word of
        usable length (letters only, wordfreq Zipf >= `min_zipf`)."""
        if not word.isalpha() or not (min_chars <= len(word) <= max_chars):
            return False
        try:
            from wordfreq import zipf_frequency
        except ImportError:  # dictionary tier unavailable -> never admit a non-DB word
            logger.warning("wordfreq not installed; rejecting non-DB anchor '%s'.", word)
            return False
        return zipf_frequency(word, "en") >= min_zipf
