"""Orchestrates a single crossword end to end.

The API route owns the HTTP concerns (validation, status codes, response shape);
this owns the generation pipeline, in one place:

    template -> theme scoring -> vetted anchors -> grid fill -> clues

Keeping it here means the pipeline can be read (and reused, e.g. from a notebook
or a script) without going through FastAPI.
"""

import logging
from typing import Dict, List, Optional, Tuple

from .clue_manager import generate_clues, retrieve_existing_clues
from .crossword_generator import generate_themed_crossword
from .template_manager import select_template
from .theme_anchor import ThemeAnchorSelector
from .theme_manager import ThemeManager
from .utils import load_parameters
from .word_database_manager import WordDatabaseManager

logger = logging.getLogger(__name__)


class CrosswordBuilder:
    """Builds one finished crossword (grid + clues) from the frontend's inputs."""

    def __init__(self, word_db_manager: WordDatabaseManager = None, params: Dict = None):
        self.word_db_manager = word_db_manager or WordDatabaseManager()
        self.params = params if params is not None else load_parameters()

    def build(
        self,
        template_id: str = None,
        theme: str = None,
        clue_type: str = "existing",
    ) -> Optional[Tuple[Dict, Dict]]:
        """Build a crossword.

        Returns (template, crossword) with clues attached, or None when no grid
        could be filled (the caller decides how to surface that).
        """
        template = select_template(template_id=template_id)
        theme = theme or None  # an empty theme string means "no theme"

        theme_similarities, theme_entries = self._select_theme_anchors(theme)
        crossword = self._fill_grid(template, theme_similarities, theme_entries)
        if crossword is None:
            return None

        crossword["clues"] = self._build_clues(crossword, theme, clue_type)
        return template, crossword

    def _select_theme_anchors(
        self, theme: Optional[str]
    ) -> Tuple[Optional[Dict[str, float]], Optional[List[str]]]:
        """Score every word against the theme and vet a pool of on-theme anchors.

        Returns (similarities, anchor_pool), or (None, None) when there is no
        theme: that None flows through to clue generation, where the prompt is
        told to ignore it and write theme-agnostic clues.
        """
        if not theme:
            return None, None

        cfg = self.params["theme_anchors"]
        # One ThemeManager (shared theme embedding, single API call): score every
        # word for the fill weighting, and pull a candidate pool for the selector.
        theme_manager = ThemeManager(theme, self.word_db_manager)
        similarities = theme_manager.score_all_words()
        candidates = theme_manager.get_anchor_candidates(
            pool_size=cfg["candidate_pool"],
            min_chars=cfg["min_chars"],
            max_chars=cfg["max_chars"],
        )
        # An LLM vets the candidates into a pool of genuinely on-theme words
        # (falls back to cosine order when no LLM is available).
        anchors = ThemeAnchorSelector().select_anchors(
            theme, candidates, self.word_db_manager,
            max_words=cfg["vetted_pool"],
            allow_llm_words=cfg["allow_llm_words"],
            min_zipf=cfg["min_zipf"],
            min_chars=cfg["min_chars"],
            max_chars=cfg["max_chars"],
        )
        return similarities, anchors

    def _fill_grid(
        self,
        template: Dict,
        theme_similarities: Optional[Dict[str, float]],
        theme_entries: Optional[List[str]],
    ) -> Optional[Dict]:
        """Fill the grid: `theme_entries` pins on-theme anchors (best-effort) and
        `theme_similarities` biases the rest of the fill toward on-theme words."""
        generator_cfg = self.params["crossword_generator"]
        fill_cfg = self.params["theme_fill"]
        anchor_cfg = self.params["theme_anchors"]
        return generate_themed_crossword(
            template,
            node_budget=generator_cfg["node_budget"],
            restart_count=generator_cfg["restart_count"],
            theme_similarities=theme_similarities,
            theme_boost=fill_cfg["boost"],
            sim_low=fill_cfg["sim_low"],
            sim_high=fill_cfg["sim_high"],
            visible_threshold=fill_cfg["visible_threshold"],
            word_db_manager=self.word_db_manager,
            theme_entries=theme_entries,
            max_anchors=anchor_cfg["max_anchors"],
            anchor_attempts=anchor_cfg["anchor_attempts"],
        )

    def _build_clues(self, crossword: Dict, theme: Optional[str], clue_type: str) -> Dict[str, str]:
        """Generated clues cost an LLM call; retrieved clues come from the database."""
        if clue_type == "generate":
            return generate_clues(crossword, theme, self.word_db_manager)
        return retrieve_existing_clues(crossword, self.word_db_manager)
