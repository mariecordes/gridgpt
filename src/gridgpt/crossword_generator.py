import random
from typing import Dict, List, Tuple, Optional, Callable
import logging

from .word_database_manager import WordDatabaseManager

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Defaults for the backtracking search (overridable via conf/base/parameters.yml).
DEFAULT_NODE_BUDGET = 20000
DEFAULT_RESTART_COUNT = 5

# Defaults for theme-weighted fill (overridable via conf/base/parameters.yml).
DEFAULT_THEME_BOOST = 4.0
DEFAULT_SIM_LOW = 0.20
DEFAULT_SIM_HIGH = 0.50


def normalized_themeness(similarity: Optional[float], sim_low: float, sim_high: float) -> float:
    """Map a raw cosine similarity to a 0..1 'themeness' by clipping to the
    [sim_low, sim_high] band. None (word not scored) maps to 0."""
    if similarity is None:
        return 0.0
    span = max(sim_high - sim_low, 1e-9)
    return min(1.0, max(0.0, (similarity - sim_low) / span))


def _build_theme_weight_fn(
    word_frequencies: Dict[str, int],
    theme_similarities: Dict[str, float],
    boost: float,
    sim_low: float,
    sim_high: float,
) -> Callable[[str], float]:
    """Selection weight blending frequency with theme similarity:
    weight = frequency * (1 + boost * themeness). Frequency stays the safety net;
    similarity is a bounded booster. Only reorders candidates, never removes them."""
    def weight(word: str) -> float:
        frequency = word_frequencies.get(word, 1)
        themeness = normalized_themeness(theme_similarities.get(word), sim_low, sim_high)
        return frequency * (1.0 + boost * themeness)
    return weight


class CrosswordGenerator:
    def __init__(self, word_db_manager: WordDatabaseManager = None):
        """Initialize the crossword generator with a word database manager."""
        if word_db_manager is None:
            self.word_db_manager = WordDatabaseManager()
        else:
            self.word_db_manager = word_db_manager
    
    def validate_theme_entry(self, theme_entry: str, min_length: int = 3, max_length: int = 15) -> Tuple[bool, str]:
        """
        Validate a user-provided theme entry.
        
        Args:
            theme_entry: The theme word or phrase to validate
            min_length: Minimum allowed word length
            max_length: Maximum allowed word length
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        # Convert to uppercase for consistency
        theme_entry = theme_entry.strip().upper()

        # Length is measured on the letters that fill the grid; spaces between
        # words are not placed, so validate against the space-free form.
        letters_only = theme_entry.replace(" ", "")

        # Check length constraints
        if len(letters_only) < min_length:
            return False, f"Theme entry too short. Minimum length is {min_length} characters."

        if len(letters_only) > max_length:
            return False, f"Theme entry too long. Maximum length is {max_length} characters."

        # Only letters (A-Z), optionally separated by spaces for multi-word entries
        if not letters_only.isalpha():
            return False, "Theme entry must contain only letters (A-Z)."

        word_list = self.word_db_manager.word_list_with_frequencies

        def in_database(word: str) -> bool:
            return word in word_list or word.lower() in word_list

        if " " in theme_entry:
            # Multi-word entry: accept if every individual word is in the database.
            if not all(in_database(word) for word in theme_entry.split()):
                return False, "Theme entry contains words not in our database."
        elif not in_database(theme_entry):
            return False, "Theme entry not found in our word database."

        return True, "Theme entry is valid."
    
    def find_suitable_slots(self, template: Dict, theme_entry: str) -> List[Dict]:
        """
        Find suitable slots for the theme entry.
        
        Args:
            template: The crossword template
            theme_entry: The validated theme entry
            
        Returns:
            List of slots that can accommodate the theme entry
        """
        theme_entry = theme_entry.strip().upper()
        entry_length = len(theme_entry)
        
        # Get all slots from the template
        all_slots = template.get("slots", [])
        
        # Filter by theme slots if specified
        theme_slot_ids = template.get("theme_slots", [])
        if theme_slot_ids:
            candidate_slots = [slot for slot in all_slots if slot["id"] in theme_slot_ids]
        else:
            # Otherwise use all slots
            candidate_slots = all_slots
        
        # Find slots with exactly the right length
        suitable_slots = [slot for slot in candidate_slots if slot["length"] == entry_length]
        
        if not suitable_slots:
            logger.warning(f"No suitable slots found for theme entry '{theme_entry}' with length {entry_length}")
            # Log the closest available slot length for debugging, if any slots exist
            if candidate_slots:
                closest = sorted(candidate_slots, key=lambda s: abs(s["length"] - entry_length))
                logger.info(f"Closest available slot length is {closest[0]['length']}")

        return suitable_slots
    
    def place_theme_entry(self, template: Dict, theme_entry: str) -> Dict:
        """
        Place theme entry into the template.
        
        Args:
            template: The crossword template
            theme_entry: The validated theme entry
            
        Returns:
            Updated template with theme entry placed
        """
        theme_entry = theme_entry.strip().upper()
        
        # Find suitable slots
        suitable_slots = self.find_suitable_slots(template, theme_entry)
        
        if not suitable_slots:
            raise ValueError(f"No suitable slots found for theme entry '{theme_entry}' with length {len(theme_entry)}")
        
        # Choose a random suitable slot
        chosen_slot = random.choice(suitable_slots)
        slot_id = chosen_slot["id"]
        
        logger.info(f"Placing theme entry '{theme_entry}' in slot {slot_id}")
        
        # Create a working copy of the template with the grid filled with placeholders
        working_template = template.copy()
        grid = [row.copy() for row in template["grid"]]
        
        # Place the theme entry in the grid
        cells = chosen_slot["cells"]

        for i, cell in enumerate(cells):
            row, col = cell
            grid[row][col] = theme_entry[i]
        
        working_template["grid"] = grid
        working_template["filled_slots"] = {slot_id: theme_entry}
        working_template["theme_entries"] = {slot_id: theme_entry}
        
        return working_template
    
    def get_intersecting_slots(self, template: Dict, slot_id: str) -> List[Tuple[str, int, int]]:
        """
        Find all slots that intersect with the given slot.
        
        Args:
            template: The crossword template
            slot_id: ID of the slot to find intersections for
            
        Returns:
            List of tuples (intersecting_slot_id, position_in_slot, position_in_intersecting_slot)
        """
        return self._build_intersection_map(template).get(slot_id, [])

    def get_slot_by_id(self, template: Dict, slot_id: str) -> Optional[Dict]:
        """Get a slot by its ID."""
        for slot in template["slots"]:
            if slot["id"] == slot_id:
                return slot
        return None

    def get_letter_at_position(self, template: Dict, slot_id: str, position: int) -> str:
        """Get the letter at a specific position in a filled slot."""
        filled_slots = template.get("filled_slots", {})
        if slot_id in filled_slots:
            word = filled_slots[slot_id]
            if 0 <= position < len(word):
                return word[position]
        return None

    # ----------------------------- Candidate lookup ----------------------------- #

    def get_possible_words(self, slot: Dict, fixed_letters: Dict[int, str], used_words: set = None) -> List[Tuple[str, int]]:
        """
        Get all possible (word, frequency) pairs for a slot given fixed letters,
        excluding already used words. Backed by the word-database index.
        """
        candidates = self._candidate_words(slot["length"], fixed_letters, used_words or set())
        frequencies = self.word_db_manager.word_frequencies
        return [(word, frequencies[word]) for word in candidates]

    def _candidate_words(self, length: int, fixed_letters: Dict[int, str], used_words: set) -> set:
        """Set of database words of the given length matching the fixed letters
        and not already used. Uses the precomputed (length, pos, letter) index,
        so this is a few set intersections rather than a scan of the word list."""
        db = self.word_db_manager
        if fixed_letters:
            index = db.letter_index.get(length, {})
            matching_sets = []
            for pos, letter in fixed_letters.items():
                matches = index.get(pos, {}).get(letter)
                if not matches:
                    return set()  # no word has this letter at this position
                matching_sets.append(matches)
            # Smallest set first keeps the intersection cheap.
            matching_sets.sort(key=len)
            candidates = set(matching_sets[0]).intersection(*matching_sets[1:])
        else:
            candidates = set(db.all_words_by_length.get(length, ()))

        if used_words:
            candidates -= used_words
        return candidates

    # ------------------------------ Backtracking ------------------------------ #

    def _build_intersection_map(self, template: Dict) -> Dict[str, List[Tuple[str, int, int]]]:
        """Map each slot to the slots it crosses: {slot_id: [(other_id,
        pos_in_slot, pos_in_other)]}. Computed once instead of rescanning."""
        cell_members: Dict[Tuple[int, int], List[Tuple[str, int]]] = {}
        for slot in template["slots"]:
            for pos, cell in enumerate(slot["cells"]):
                cell_members.setdefault(tuple(cell), []).append((slot["id"], pos))

        intersections: Dict[str, List[Tuple[str, int, int]]] = {slot["id"]: [] for slot in template["slots"]}
        for members in cell_members.values():
            if len(members) < 2:
                continue
            for slot_a, pos_a in members:
                for slot_b, pos_b in members:
                    if slot_a != slot_b:
                        intersections[slot_a].append((slot_b, pos_a, pos_b))
        return intersections

    @staticmethod
    def _fixed_letters(slot_id: str, assignment: Dict[str, str], intersections: Dict) -> Dict[int, str]:
        """Letters already forced on a slot by its filled crossing slots."""
        fixed: Dict[int, str] = {}
        for other_id, pos_in_slot, pos_in_other in intersections[slot_id]:
            if other_id in assignment:
                fixed[pos_in_slot] = assignment[other_id][pos_in_other]
        return fixed

    @staticmethod
    def _weighted_order(candidates: set, weight_fn: Callable[[str], float]) -> List[str]:
        """Weighted-random permutation (Efraimidis-Spirakis) of the candidates.

        Each word gets key = random()**(1/weight); sorting by key descending
        yields a random order biased toward higher weights. This keeps output
        varied across generations while trying likely words first. A future
        theme-weighting change can fold a theme boost into `weight_fn`."""
        keyed = []
        for word in candidates:
            weight = weight_fn(word)
            if weight <= 0:
                weight = 1e-9
            keyed.append((random.random() ** (1.0 / weight), word))
        keyed.sort(reverse=True)
        return [word for _, word in keyed]

    def _backtrack(
        self,
        assignment: Dict[str, str],
        unfilled: set,
        lengths: Dict[str, int],
        intersections: Dict,
        used_words: set,
        weight_fn: Callable[[str], float],
        node_budget: int,
        node_count: List[int],
    ) -> Optional[Dict[str, str]]:
        """Recursive backtracking with MRV ordering and forward checking."""
        if not unfilled:
            return dict(assignment)

        # MRV: expand the unfilled slot with the fewest current candidates.
        best_slot = None
        best_candidates = None
        for slot_id in unfilled:
            fixed = self._fixed_letters(slot_id, assignment, intersections)
            candidates = self._candidate_words(lengths[slot_id], fixed, used_words)
            if not candidates:
                return None  # dead end: some slot has no options
            if best_candidates is None or len(candidates) < len(best_candidates):
                best_slot, best_candidates = slot_id, candidates
                if len(candidates) == 1:
                    break

        remaining = unfilled - {best_slot}
        neighbors = [nid for nid, _, _ in intersections[best_slot] if nid in remaining]

        for word in self._weighted_order(best_candidates, weight_fn):
            node_count[0] += 1
            if node_count[0] > node_budget:
                return None

            assignment[best_slot] = word
            used_words.add(word)

            # Forward checking: every affected neighbor must keep >= 1 candidate.
            ok = True
            for neighbor_id in neighbors:
                fixed = self._fixed_letters(neighbor_id, assignment, intersections)
                if not self._candidate_words(lengths[neighbor_id], fixed, used_words):
                    ok = False
                    break

            if ok:
                result = self._backtrack(
                    assignment, remaining, lengths, intersections,
                    used_words, weight_fn, node_budget, node_count,
                )
                if result is not None:
                    return result

            del assignment[best_slot]
            used_words.discard(word)

        return None

    def fill(
        self,
        template: Dict,
        seed_assignment: Dict[str, str] = None,
        weight_fn: Callable[[str], float] = None,
        node_budget: int = DEFAULT_NODE_BUDGET,
    ) -> Optional[Dict[str, str]]:
        """Fill every slot via backtracking. Returns {slot_id: word} or None."""
        intersections = self._build_intersection_map(template)
        lengths = {slot["id"]: slot["length"] for slot in template["slots"]}
        assignment = dict(seed_assignment or {})
        used_words = set(assignment.values())
        unfilled = {slot["id"] for slot in template["slots"] if slot["id"] not in assignment}

        if weight_fn is None:
            frequencies = self.word_db_manager.word_frequencies
            weight_fn = lambda word: frequencies.get(word, 1)

        node_count = [0]
        return self._backtrack(
            assignment, unfilled, lengths, intersections,
            used_words, weight_fn, node_budget, node_count,
        )

    def _assemble_result(self, template: Dict, filled_slots: Dict[str, str], theme_entries: Dict[str, str]) -> Dict:
        """Build the crossword output dict (grid + slots) from a full assignment."""
        result = template.copy()
        grid = [row.copy() for row in template["grid"]]
        slots_by_id = {slot["id"]: slot for slot in template["slots"]}
        for slot_id, word in filled_slots.items():
            for i, (row, col) in enumerate(slots_by_id[slot_id]["cells"]):
                grid[row][col] = word[i]
        result["grid"] = grid
        result["filled_slots"] = filled_slots
        result["theme_entries"] = theme_entries
        return result

    def generate_crossword(
        self,
        template: Dict,
        theme_entry: str = None,
        node_budget: int = DEFAULT_NODE_BUDGET,
        restart_count: int = DEFAULT_RESTART_COUNT,
        theme_similarities: Dict[str, float] = None,
        theme_boost: float = DEFAULT_THEME_BOOST,
        sim_low: float = DEFAULT_SIM_LOW,
        sim_high: float = DEFAULT_SIM_HIGH,
    ) -> Optional[Dict]:
        """
        Generate a complete crossword puzzle.
        
        Args:
            template: The crossword template
            theme_entry: Optional pre-placed theme entry
            node_budget: Max word placements per attempt
            restart_count: Attempts with a different theme placement / random order
            theme_similarities: Optional {WORD: cosine} map; when given, fill is
                biased toward on-theme words (candidate order only, never feasibility)
            theme_boost, sim_low, sim_high: theme-weighting parameters

        Returns:
            Completed crossword dict, or None if no fill was found.
        """
        if theme_entry:
            is_valid, message = self.validate_theme_entry(theme_entry)
            if not is_valid:
                raise ValueError(message)

        # Build a theme-weighted selection function once (if a theme is provided);
        # otherwise fill() defaults to pure frequency weighting.
        weight_fn = None
        if theme_similarities:
            weight_fn = _build_theme_weight_fn(
                self.word_db_manager.word_frequencies,
                theme_similarities, theme_boost, sim_low, sim_high,
            )

        for _ in range(max(1, restart_count)):
            if theme_entry:
                try:
                    working = self.place_theme_entry(template, theme_entry)
                except ValueError:
                    return None  # theme entry does not fit any slot in this template
                seed = dict(working["filled_slots"])
                theme_entries = dict(working["theme_entries"])
            else:
                seed = {}
                theme_entries = {}

            solution = self.fill(template, seed_assignment=seed, weight_fn=weight_fn, node_budget=node_budget)
            if solution is not None:
                logger.info(f"Grid filled successfully with {len(solution)} unique words")
                return self._assemble_result(template, solution, theme_entries)

        return None


def print_grid(grid: List[List[str]]):
    """Print a grid in a readable format."""
    horizontal_line = "+---" * len(grid[0]) + "+"

    print(horizontal_line)
    for row in grid:
        print("| " + " | ".join(cell if cell != "#" else " " for cell in row) + " |")
        print(horizontal_line)


def generate_themed_crossword(
    template: Dict,
    theme_entry: str = None,
    node_budget: int = DEFAULT_NODE_BUDGET,
    restart_count: int = DEFAULT_RESTART_COUNT,
    theme_similarities: Dict[str, float] = None,
    theme_boost: float = DEFAULT_THEME_BOOST,
    sim_low: float = DEFAULT_SIM_LOW,
    sim_high: float = DEFAULT_SIM_HIGH,
    word_db_manager: WordDatabaseManager = None,
) -> Optional[Dict]:
    """
    Generate a themed crossword puzzle.

    Args:
        template: The crossword template to use
        theme_entry: Optional pre-placed theme entry
        node_budget: Max word placements per backtracking attempt
        restart_count: Number of restart attempts
        theme_similarities: Optional {WORD: cosine} map to bias the fill on-theme
        theme_boost, sim_low, sim_high: theme-weighting parameters
        word_db_manager: Optional WordDatabaseManager instance to reuse

    Returns:
        Generated crossword puzzle, or None if generation failed.
    """
    generator = CrosswordGenerator(word_db_manager)

    if theme_entry:
        logger.info(f"Generating crossword with theme entry: '{theme_entry}'")
    else:
        logger.info("Generating crossword without theme entry")

    crossword = generator.generate_crossword(
        template, theme_entry, node_budget=node_budget, restart_count=restart_count,
        theme_similarities=theme_similarities, theme_boost=theme_boost,
        sim_low=sim_low, sim_high=sim_high,
    )

    if crossword:
        logger.info("Crossword generated successfully")
        logger.debug(
            "Generated crossword filled slots: %s",
            {slot_id: word for slot_id, word in sorted(crossword["filled_slots"].items())},
        )
    else:
        logger.warning("Failed to generate a crossword after all restarts")

    return crossword