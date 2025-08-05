import argparse
import logging
import random
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Tuple, Dict, Optional
from threading import Lock
from functools import lru_cache
from collections import defaultdict
from rich.progress import Progress, TaskID
from rich.console import Console
from rich.table import Table
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough
from langchain_openai import ChatOpenAI

# --- Import config ---
from config import Config, DEFAULT_BEAM_WIDTH, DEFAULT_MAX_BACKTRACK, DEFAULT_GRID_WIDTH, DEFAULT_GRID_HEIGHT, DEFAULT_BLACK_SQUARE_RATIO, DEFAULT_LM_STUDIO_URL, DEFAULT_WORDS_FILE, DEFAULT_OUTPUT_FILENAME, DEFAULT_MAX_ATTEMPTS, DEFAULT_TIMEOUT, DEFAULT_LLM_TIMEOUT, DEFAULT_LLM_MAX_TOKENS, DEFAULT_LANGUAGE, DEFAULT_MODEL, DEFAULT_DIFFICULTY, DEFAULT_MAX_GRID_ITERATIONS  # Import the Config class

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# --- Compiled Regex Patterns ---
WORD_CLEAN_RE = re.compile(r"[^A-Z]")  # Only keep uppercase letters
DEFINITION_CLEAN_RE = re.compile(r"^\d+\.\s*") # Remove leading numbers
NON_ALPHANUMERIC_RE = re.compile(r"^[^\w]+|[^\w]+$") # trim non-alphanumeric

# --- Global Variables ---
cache_lock = Lock()
placement_cache: Dict[str, bool] = {}
definition_cache: Dict[str, str] = {}
word_index: Dict[Tuple[int, str], List[str]] = defaultdict(list)
llm = None  # Global LLM object
slot_attempts_count: Dict[Tuple[int, int, str], int] = {}  # Track attempts per slot


# --- Utility Functions ---
def print_grid(grid: List[List[str]], placed_words: List[Tuple[str, int, int, str]] = None,
               console: Optional[Console] = None) -> None:
    """Prints the grid with highlighting."""
    if console is None:
        console = Console()

    table = Table(show_header=False, show_edge=False, padding=0)

    if placed_words is not None:
        placed_coords = set()
        for word, row, col, direction in placed_words:
            for i in range(len(word)):
                if direction == "across":
                    placed_coords.add((row, col + i))
                else:
                    placed_coords.add((row + i, col))

    for r_idx, row in enumerate(grid):
        row_display = []
        for c_idx, cell in enumerate(row):
            if cell == "#":
                row_display.append("[white on black]  [/]")  # Black square
            elif placed_words is not None and (r_idx, c_idx) in placed_coords:
                row_display.append(f"[black on green]{cell.center(2)}[/]")
            else:
                row_display.append(f"[black on white]{cell.center(2)}[/]")
        table.add_row(*row_display)

    console.print(table)


def calculate_word_frequency(word: str, word_frequencies: Dict[str, float]) -> float:
    """Calculates word score (lower is more common)."""
    return word_frequencies.get(word.lower(), 1e-6) # Default very low


def create_pattern(word: str) -> str:
    """Creates regex pattern, '.' for unknown."""
    return ''.join('.' if c == '.' else c for c in word)

def load_words(filepath: str, min_word_count: int = 3, config: Config = None) -> Tuple[Dict[int, List[str]], Dict[str, float]]:
    """Loads, preprocesses, and filters words."""
    words_by_length: Dict[int, List[str]] = defaultdict(list)
    word_counts: Dict[str, int] = defaultdict(int)
    total_count = 0
    filtered_words = set()

    try:
        with open(filepath, "r", encoding="utf-8") as file:
            for line in file:
                word = line.strip().upper()
                word = WORD_CLEAN_RE.sub("", word)
                if len(word) >= (config.min_word_length if config else 3):  # Use config.min_word_length if available
                    word_counts[word] += 1
                    total_count += 1

        word_frequencies: Dict[str, float] = {}
        for word, count in word_counts.items():
            freq = count / total_count
            word_frequencies[word] = freq  # Store with uppercase key
            if count >= min_word_count:
                filtered_words.add(word)

        for word in filtered_words:
            words_by_length[len(word)].append(word)

        return words_by_length, word_frequencies

    except FileNotFoundError:
        logging.error(f"Word file not found: {filepath}")
        sys.exit(1)
    except Exception as e:
        logging.error(f"Error loading words: {e}")
        sys.exit(1)


def build_word_index(words_by_length: Dict[int, List[str]]):
    """Builds the word index for efficient lookups with improved pattern matching."""
    global word_index
    word_index.clear()

    for length, words in words_by_length.items():
        # Add empty pattern for initial placement
        empty_pattern = "." * length
        word_index[(length, empty_pattern)].extend(words)  # Add all words for the empty pattern

        for word in words:
            # Add full word pattern
            word_index[(length, word)].append(word)
            # Add partial patterns
            for i in range(length):
                for j in range(i + 1, length + 1):
                    pattern = list(empty_pattern)
                    for k in range(i, j):
                        pattern[k] = word[k]
                    pattern_str = "".join(pattern)
                    word_index[(length, pattern_str)].append(word)

        logging.info(f"Built index for length {length}: {len(words)} words, {len(word_index)} patterns")


# --- LangChain and LLM Setup ---
def setup_langchain_llm(config: Config) -> ChatOpenAI:  # Pass config
    """Initializes the LangChain LLM."""
    global llm
    try:
        llm = ChatOpenAI(
            base_url=config.lm_studio_url,
            api_key="NA",  # Not needed for local models
            model=config.model,
            temperature=0.7,
            max_tokens=config.llm_max_tokens,
            timeout=config.llm_timeout,
        )
        return llm
    except Exception as e:
        logging.error(f"Failed to initialize LLM: {e}")
        sys.exit(1)


@lru_cache(maxsize=512)
def generate_definition_langchain(word: str, language: str, config: Config) -> str:  # Pass config
    """Generates clues, with retries and filtering."""
    if word in definition_cache:
        return definition_cache[word]

    prompt_template = """Generate a short, concise crossword clue for: "{word}". Reply in {language}.
    Strict Rules:
    1. Absolutely NO part of the target word in the clue.
    2. Clue must be 10 words or less.
    3. Avoid obvious synonyms.
    4. No direct definitions.
    5. Focus on wordplay, double meanings, or indirect hints.
    Output: Only the clue text, nothing else."""

    prompt = PromptTemplate.from_template(prompt_template)
    output_parser = StrOutputParser()
    chain = (
            {"word": RunnablePassthrough(), "language": RunnablePassthrough()}
            | prompt
            | llm
            | output_parser
    )

    for attempt in range(config.max_definition_attempts): # Use config
        try:
            definition = chain.invoke({"word": word, "language": language})
            definition = definition.strip()

            # Cleaning and filtering
            definition = re.sub(r'(?i)definizione[:\s]*', '', definition)
            definition = re.sub(r'(?i)clue[:\s]*', '', definition)
            definition = re.sub(r'^\d+[\.\)]\s*', '', definition).strip()

            for pattern in config.forbidden_patterns:  # Use config
                if re.search(pattern(word), definition, re.IGNORECASE):
                    raise ValueError("Forbidden word/pattern used.")

            word_lower = word.lower()
            definition_lower = definition.lower()
            if any(word_lower[i:j] in definition_lower for i in range(len(word) - 2) for j in range(i + 3, len(word) + 1)):
                raise ValueError("Part of word used.")

            definition_cache[word] = definition
            return definition

        except Exception as e:
            logging.warning(f"Attempt {attempt + 1} for '{word}': {e}")
            if attempt < config.max_definition_attempts - 1:  # Use config
                time.sleep(config.definition_retry_delay)  # Use config

    logging.error(f"Failed to generate definition for '{word}'.")
    return "Definizione non disponibile"



# --- Grid Generation and Manipulation ---

def generate_grid_from_string(grid_string: str) -> Optional[List[List[str]]]:
    """Generates grid from string, with validation."""
    lines = grid_string.strip().split("\n")
    grid: List[List[str]] = []
    for line in lines:
        row = [char for char in line.strip() if char in (".", "#")]
        if len(row) != len(lines[0]):
            logging.error("Inconsistent row length in manual grid.")
            return None
        grid.append(row)

    if not grid or any(len(row) != len(grid[0]) for row in grid):
        logging.error("Invalid manual grid: empty or non-rectangular.")
        return None
    return grid


def generate_grid_from_file(filepath: str) -> Optional[List[List[str]]]:
    """Loads grid from file, with error handling."""
    try:
        with open(filepath, "r") as f:
            return generate_grid_from_string(f.read())
    except FileNotFoundError:
        logging.error(f"Grid file not found: {filepath}")
        return None
    except Exception as e:
        logging.error(f"Error reading grid file: {e}")
        return None

def is_valid_grid(grid: List[List[str]]) -> bool:
    """Checks if the grid is valid."""
    if not grid:
        return False
    width = len(grid[0])
    return all(len(row) == width and all(c in ('.', '#') for c in row) for row in grid)


def generate_grid_random(width: int, height: int, black_square_ratio: float) -> List[List[str]]:
    """Generates a random, symmetrical grid."""
    grid = [["." for _ in range(width)] for _ in range(height)]
    num_black_squares = int(width * height * black_square_ratio)

    def place_symmetrically(row: int, col: int):
        grid[row][col] = "#"
        grid[height - 1 - row][width - 1 - col] = "#"

    if width % 2 == 1 and height % 2 == 1:
        place_symmetrically(height // 2, width // 2)
        num_black_squares -= 1

    placed_count = 0
    attempts = 0
    max_attempts = width * height * 5

    while placed_count < num_black_squares and attempts < max_attempts:
        attempts += 1
        row, col = random.randint(0, height - 1), random.randint(0, width - 1)

        if grid[row][col] == ".":
            # Check for 2x2 blocks *before* placement
            if (row > 0 and col > 0 and grid[row - 1][col] == "#" and grid[row][col - 1] == "#" and grid[row - 1][col - 1] == "#") or \
               (row > 0 and col < width - 1 and grid[row - 1][col] == "#" and grid[row][col + 1] == "#" and grid[row - 1][col + 1] == "#") or \
               (row < height - 1 and col > 0 and grid[row + 1][col] == "#" and grid[row][col - 1] == "#" and grid[row + 1][col - 1] == "#") or \
               (row < height - 1 and col < width - 1 and grid[row + 1][col] == "#" and grid[row][col + 1] == "#" and grid[row + 1][col + 1] == "#"):
                continue

            # Check for isolated white squares (before placement)
            def is_isolated(r, c):
                if r > 0 and grid[r-1][c] == ".": return False
                if r < height - 1 and grid[r+1][c] == ".": return False
                if c > 0 and grid[r][c-1] == ".": return False
                if c < width - 1 and grid[r][c+1] == ".": return False
                return True

            if is_isolated(row,col):
              continue;

            place_symmetrically(row, col)
            placed_count += 2 if (row, col) != (height - 1 - row, width - 1 - col) else 1

    if placed_count < num_black_squares:
        logging.warning(f"Could only place {placed_count} of {num_black_squares} black squares.")
    return grid

def generate_grid(config: Config) -> List[List[str]]: # Pass config
    """Generates grid, handling manual, file, or random."""
    if config.manual_grid:
        grid = generate_grid_from_string(config.manual_grid)
        if grid: return grid
        logging.warning("Invalid manual grid. Using random.")

    if config.grid_file:
        grid = generate_grid_from_file(config.grid_file)
        if grid: return grid
        logging.warning("Invalid grid file. Using random.")

    return generate_grid_random(config.grid_width, config.grid_height, config.black_square_ratio)


def find_slots(grid: List[List[str]], config: Config) -> List[Tuple[int, int, str, int]]:  # Pass config
    """Identifies word slots (across and down)."""
    height, width = len(grid), len(grid[0])
    slots = []

    # Across
    for r in range(height):
        start = -1
        for c in range(width):
            if grid[r][c] == ".":
                if start == -1: start = c
            elif start != -1:
                length = c - start
                if length >= config.min_word_length:  # Use config.min_word_length
                    slots.append((r, start, "across", length))
                start = -1
        if start != -1 and width - start >= config.min_word_length:  # Use config.min_word_length
            slots.append((r, start, "across", width - start))

    # Down
    for c in range(width):
        start = -1
        for r in range(height):
            if grid[r][c] == ".":
                if start == -1: start = r
            elif start != -1:
                length = r - start
                if length >= config.min_word_length:  # Use config
                    slots.append((start, c, "down", length))
                start = -1
        if start != -1 and height - start >= config.min_word_length:  # Use config.min_word_length
            slots.append((start, c, "down", height - start))
    return slots


def is_valid_placement(grid: List[List[str]], word: str, row: int, col: int, direction: str) -> bool:
    """Checks placement using the index."""
    length = len(word)
    if direction == "across":
        if col + length > len(grid[0]): return False
        pattern = ''.join(grid[row][col + i] for i in range(length))
    else:  # down
        if row + length > len(grid): return False
        pattern = ''.join(grid[row + i][col] for i in range(length))

    key = (length, create_pattern(pattern))
    return word in word_index.get(key, [])

def _is_valid_cached(grid: List[List[str]], word: str, row: int, col: int, direction: str) -> bool:
    """Cached version of is_valid_placement."""
    key = f"{word}:{row}:{col}:{direction}"
    with cache_lock:
        if key not in placement_cache:
            placement_cache[key] = is_valid_placement(grid, word, row, col, direction)
        return placement_cache[key]

def place_word(grid: List[List[str]], word: str, row: int, col: int, direction: str) -> List[List[str]]:
    """Places a word onto a *copy* of the grid."""
    new_grid = [row[:] for row in grid]  # Deep copy
    for i, letter in enumerate(word):
        if direction == "across":
            new_grid[row][col + i] = letter
        else:
            new_grid[row + i][col] = letter
    return new_grid


def remove_word(grid: List[List[str]], word: str, row: int, col: int, direction: str) -> List[List[str]]:
    """Removes a word from a *copy* of the grid."""
    new_grid = [row[:] for row in grid]  # Deep copy
    for i in range(len(word)):
        if direction == "across":
            if new_grid[row][col + i] == word[i]:
                new_grid[row][col + i] = "."
        else:
            if new_grid[row + i][col] == word[i]:
                new_grid[row + i][col] = "."
    return new_grid

def check_all_letters_connected(grid: List[List[str]], placed_words: List[Tuple[str, int, int, str]]) -> bool:
    """Checks if all placed letters are connected."""
    if not placed_words: return True

    letter_positions = set()
    for word, row, col, direction in placed_words:
        for i in range(len(word)):
            if direction == "across":
                pos = (row, col + i)
                if grid[row][col + i] != word[i]: return False
            else:
                pos = (row + i, col)
                if grid[row + i][col] != word[i]: return False
            letter_positions.add(pos)

    for row, col in letter_positions:
        in_across = any(row == r and col >= c and col < c + len(w) for w, r, c, d in placed_words if d == "across")
        in_down = any(col == c and row >= r and row < r + len(w) for w, r, c, d in placed_words if d == "down")
        if not (in_across and in_down):
            return False

    return True

def _validate_remaining_slots(grid: List[List[str]], slots: List[Tuple[int, int, str, int]],
                              words_by_length: Dict[int, List[str]]) -> bool:
    """Checks if all slots have at least one valid word."""
    for row, col, direction, length in slots:
        if direction == "across":
            pattern_list = [grid[row][col + i] for i in range(length)]
        else:
            pattern_list = [grid[row+i][col] for i in range(length)]
        pattern = create_pattern("".join(pattern_list))
        if not word_index.get((length, pattern)):
            return False
    return True


def validate_placement(grid: List[List[str]], slot: Tuple[int, int, str, int],
                     word: str, remaining_slots: List[Tuple[int, int, str, int]],
                     words_by_length: Dict[int, List[str]]) -> bool:
    """Validates word placement with enhanced pattern matching."""
    row, col, direction, length = slot

    # Check if word fits in grid
    if direction == "across" and col + length > len(grid[0]):
        return False
    if direction == "down" and row + length > len(grid):
        return False

    # Check if placement conflicts with existing letters
    if direction == "across":
        for i, letter in enumerate(word):
            if grid[row][col + i] not in [".", letter]:
                return False
    else:
        for i, letter in enumerate(word):
            if grid[row + i][col] not in [".", letter]:
                return False

    # Create temporary grid with placement
    temp_grid = [row[:] for row in grid]
    if direction == "across":
        for i, letter in enumerate(word):
            temp_grid[row][col + i] = letter
    else:
        for i, letter in enumerate(word):
            temp_grid[row + i][col] = letter

    # Validate intersecting words
    for r, c, d, l in remaining_slots:
        if d == direction:
            continue

        # Get pattern for intersecting slot
        if d == "across":
            pattern = "".join(temp_grid[r][c:c + l])
        else:
            pattern = "".join(temp_grid[r + i][c] for i in range(l))

        # Check if pattern has any letters (constraints)
        if any(ch != "." for ch in pattern):
            pattern = create_pattern(pattern)
            if not word_index.get((l, pattern)):
                return False

    return True


def make_placement(grid: List[List[str]], slot: Tuple[int, int, str, int],
                   word: str, placed_words: List[Tuple[str, int, int, str]]) -> Tuple[
    List[List[str]], List[Tuple[str, int, int, str]]]:
    """Places a word and updates placed_words."""
    row, col, direction, _ = slot
    new_grid = place_word(grid, word, row, col, direction)
    new_placed_words = placed_words + [(word, row, col, direction)]
    stats.successful_placements += 1
    stats.words_tried += 1
    stats.slot_fill_order.append((row, col, direction))
    return new_grid, new_placed_words


def handle_backtrack(slot: Tuple[int, int, str, int]) -> None:
    """Handles statistics during backtracking."""
    stats.backtracks += 1
    stats.failed_placements += 1
    if stats.slot_fill_order:
        stats.slot_fill_order.pop()


def try_slot(grid: List[List[str]], slot: Tuple[int, int, str, int],
             word: str,
             remaining_slots: List[Tuple[int, int, str, int]],
             words_by_length: Dict[int, List[str]],
             word_frequencies: Dict[str, float],
             placed_words: List[Tuple[str, int, int, str]],
             progress: Progress, task: TaskID,
             config: Config,  # Pass config
             ) -> Tuple[Optional[List[List[str]]], Optional[List[Tuple[str, int, int, str]]]]:
    row, col, direction, length = slot
    stats.words_tried += 1

    # Check placement cache first
    cache_key = f"{word}_{row}_{col}_{direction}"
    with cache_lock:
        if cache_key in placement_cache:
            if not placement_cache[cache_key]:
                return None, None

    # Validate placement with enhanced constraints
    if not validate_placement(grid, slot, word, remaining_slots, words_by_length):
        with cache_lock:
            placement_cache[cache_key] = False
        return None, None

    # Make placement and update cache
    new_grid = [row[:] for row in grid]
    if direction == "across":
        for i, letter in enumerate(word):
            new_grid[row][col + i] = letter
    else:
        for i, letter in enumerate(word):
            new_grid[row + i][col] = letter

    new_placed_words = placed_words + [(word, row, col, direction)]
    with cache_lock:
        placement_cache[cache_key] = True

    # Early validation of remaining slots
    for next_slot in remaining_slots:
        r, c, d, l = next_slot
        pattern = create_pattern("".join(new_grid[r][c:c + l] if d == "across" else [new_grid[r + i][c] for i in range(l)]))
        valid_words = word_index.get((l, pattern), [])
        if not valid_words:
            return None, None

    # Try to solve remaining slots with optimized recursion
    result = select_words_recursive(new_grid, remaining_slots, words_by_length,
                                  word_frequencies, new_placed_words, progress,
                                  task, config)
    if result[0] is not None:
        stats.successful_placements += 1
        stats.slot_fill_order.append((row, col, direction))  # Track successful placement
        return result

    # Handle backtrack with improved statistics
    handle_backtrack(slot)
    stats.failed_placements += 1
    return None, None


def get_location_score(grid: List[List[str]], slot: Tuple[int, int, str, int]) -> float:
    """Calculates a score based on slot location and potential intersections."""
    row, col, direction, length = slot  # Now takes length
    height, width = len(grid), len(grid[0])

    # Center proximity bonus (words near center are preferred)
    center_row, center_col = height // 2, width // 2
    distance_to_center = abs(row - center_row) + abs(col - center_col)
    center_bonus = 1.0 - (distance_to_center / (height + width))

    # Length bonus (longer words create more intersection opportunities)
    length_bonus = length / max(height, width)

    # Intersection potential bonus
    crossing_slots = 0
    potential_intersections = 0
    if direction == "across":
        for i in range(length):
            # Count existing crossing points
            if any(grid[r][col + i] == "." for r in range(height)):
                crossing_slots += 1
            # Count potential future intersections
            empty_spaces = sum(1 for r in range(height) if grid[r][col + i] == ".")
            potential_intersections += empty_spaces
    else:
        for i in range(length):
            if any(grid[row + i][c] == "." for c in range(width)):
                crossing_slots += 1
            empty_spaces = sum(1 for c in range(width) if grid[row + i][c] == ".")
            potential_intersections += empty_spaces

    intersection_bonus = (crossing_slots + 0.5 * potential_intersections) / (length * 2)

    # Edge penalty (avoid placing words at edges unless necessary)
    edge_penalty = 0.0
    if row == 0 or row + (length if direction == "down" else 1) >= height:
        edge_penalty += 0.2
    if col == 0 or col + (length if direction == "across" else 1) >= width:
        edge_penalty += 0.2

    # Previous attempts penalty - avoid slots we've struggled with
    attempt_penalty = min(0.5, slot_attempts_count.get((row, col, direction), 0) * 0.02)

    return (center_bonus * 0.3 +
            length_bonus * 0.2 +
            intersection_bonus * 0.4 -
            edge_penalty * 0.1 -
            attempt_penalty)


def get_slot_length(grid: List[List[str]], row: int, col: int, direction: str) -> int:
    """Calculates maximum possible word length for a slot."""
    length = 0
    if direction == 'across':
        while col + length < len(grid[row]) and grid[row][col + length] != '#':
            length += 1
    else:  # down
        while row + length < len(grid) and grid[row + length][col] != '#':
            length += 1
    return length


def count_existing_letters(grid: List[List[str]], slot: Tuple[int, int, str, int]) -> int:
    """Counts pre-existing letters in a slot."""
    row, col, direction, _ = slot  # Unpack, ignore length
    count = 0
    length = get_slot_length(grid, row, col, direction)

    if direction == 'across':
        for i in range(length):
            if grid[row][col + i] != '.':
                count += 1
    else:
        for i in range(length):
            if grid[row + i][col] != '.':
                count += 1
    return count


def count_intersections(grid: List[List[str]], slot: Tuple[int, int, str, int], placed_words: List[Tuple[str, int, int, str]]) -> int:
    """Counts intersecting words from placed words list."""
    row, col, direction, _ = slot  # Unpack, ignore length
    intersections = 0

    for word_info in placed_words:
        w_row, w_col, w_dir = word_info[1], word_info[2], word_info[3]
        if w_dir == direction:
            continue  # Same direction can't intersect

        # Check for intersection points
        if direction == 'across':
            for i in range(get_slot_length(grid, row, col, direction)):
                check_row = row
                check_col = col + i
                if w_dir == 'down' and (check_row >= w_row and check_row < w_row + len(word_info[0])) and check_col == w_col:
                    intersections += 1
        else:
            for i in range(get_slot_length(grid, row, col, direction)):
                check_row = row + i
                check_col = col
                if w_dir == 'across' and (check_col >= w_col and check_col < w_col + len(word_info[0])) and check_row == w_row:
                    intersections += 1

    return intersections

def get_slot_score(grid: List[List[str]], slot: Tuple[int, int, str, int], words_by_length: Dict[int, List[str]], placed_words: List[Tuple[str, int, int, str]]) -> float:
    """Calculates priority score for a slot (higher = better to fill first)."""
    row, col, direction, length = slot # unpack also length
    #length = get_slot_length(grid, row, col, direction) # Not needed

    # Base score - prioritize longer words
    score = length * 10

    # Existing letters bonus
    existing_letters = count_existing_letters(grid, slot)
    score += existing_letters * 5

    # Intersection penalty - prefer slots with existing crosses
    intersections = count_intersections(grid, slot, placed_words)
    score += intersections * 3

    # Word availability adjustment - prefer slots with more word options
    pattern = create_pattern("".join(grid[row][col:col + length] if direction == "across" else [grid[row + i][col] for i in range(length)]))
    available = len(word_index.get((length, pattern), []))
    
    # Give higher score to slots with more available words
    if available == 0:
        score = 0  # No valid words - don't try this slot
    else:
        # Logarithmic scaling to avoid huge differences when the available words count varies greatly
        availability_score = min(30, 5 * (1 + (available / 100)))
        score += availability_score
    
    # Penalize slots that have been tried many times
    attempt_count = slot_attempts_count.get((row, col, direction), 0)
    if attempt_count > 0:
        score -= attempt_count * 2  # Progressive penalty for repeated attempts
    
    return score


def select_words_recursive(
        grid: List[List[str]],
        slots: List[Tuple[int, int, str, int]],
        words_by_length: Dict[int, List[str]],
        word_frequencies: Dict[str, float],
        placed_words: List[Tuple[str, int, int, str]],
        progress: Progress,
        task: TaskID,
        config: Config,
        executor: Optional[ThreadPoolExecutor] = None,
        depth: int = 0
) -> Tuple[Optional[List[List[str]]], Optional[List[Tuple[str, int, int, str]]]]:
    stats.attempts += 1
    stats.update_time()

    if depth > len(slots) * 3:
        return None, None

    if stats.time_spent > config.timeout:
        return None, None

    if not slots:
        if check_all_letters_connected(grid, placed_words):
            return grid, placed_words
        return None, None

    # Enhanced slot scoring with debug logging
    scored_slots = []
    for slot in slots:
        row, col, direction, length = slot
        # Create pattern correctly for empty slots
        if direction == "across":
            pattern = "." * length  # Use empty pattern for initial placement
        else:
            pattern = "." * length

        valid_words = word_index.get((length, pattern), [])
        if not valid_words and any(grid[row][col:col + length]) if direction == "across" else any(grid[row + i][col] for i in range(length)):
            # If slot has constraints, create pattern from grid
            pattern = create_pattern("".join(grid[row][col:col + length] if direction == "across" else [grid[row + i][col] for i in range(length)]))
            valid_words = word_index.get((length, pattern), [])

        base_score = get_slot_score(grid, slot, words_by_length, placed_words)
        location_bonus = get_location_score(grid, slot) * 2.0
        constraint_bonus = len(valid_words) / 100.0 if valid_words else 0
        total_score = base_score + location_bonus - constraint_bonus

        logging.info(f"Slot {slot}: pattern={pattern}, valid_words={len(valid_words)}, score={total_score}")
        scored_slots.append((total_score, slot))

    scored_slots.sort(key=lambda x: x[0], reverse=True)
    logging.info(f"Sorted slots: {[(score, slot) for score, slot in scored_slots]}")

    for score, slot in scored_slots:
        row, col, direction, length = slot
        remaining_slots = [s for s in slots if s != slot]

        # Track attempts for this slot
        slot_key = (row, col, direction)
        slot_attempts_count[slot_key] = slot_attempts_count.get(slot_key, 0) + 1
        attempts_for_slot = slot_attempts_count[slot_key]

        # Adaptively increase backtracking for difficult slots
        local_max_backtrack = stats.dynamic_max_backtrack
        if attempts_for_slot > 3:
            # Progressively increase the backtracking limit for difficult slots
            local_max_backtrack = min(10000, stats.dynamic_max_backtrack * (1 + (attempts_for_slot / 10)))
            logging.info(f"Increasing backtracking limit to {local_max_backtrack} for difficult slot {slot}")

        # Get valid words using empty pattern for initial placement
        pattern = "." * length
        valid_words = word_index.get((length, pattern), [])
        if not valid_words and any(grid[row][col:col + length]) if direction == "across" else any(grid[row + i][col] for i in range(length)):
            pattern = create_pattern("".join(grid[row][col:col + length] if direction == "across" else [grid[row + i][col] for i in range(length)]))
            valid_words = word_index.get((length, pattern), [])

        if not valid_words:
            logging.info(f"No valid words found for slot {slot} with pattern {pattern}")
            continue

        word_scores = []
        freq_weight = config.word_frequency_weights[config.difficulty]
        
        # Add randomization factor for diversity in attempts
        randomization_factor = 0.1 * (attempts_for_slot > 2)
        
        for word in valid_words:
            # No intersection score
            frequency_score = calculate_word_frequency(word, word_frequencies)
            word_score = frequency_score * freq_weight
            
            # Add small random factor to break ties and increase diversity for difficult slots
            if randomization_factor > 0:
                word_score += random.random() * randomization_factor
                
            word_scores.append((word_score, word))

        word_scores.sort(key=lambda x: x[0], reverse=True)  # sort by the score.
        logging.info(f"Trying slot {slot} with {len(word_scores)} words")

        if executor is not None:
            futures = []
            for _, word in word_scores[:int(local_max_backtrack)]:
                future = executor.submit(try_slot, grid, slot, word,
                                         remaining_slots, words_by_length,
                                         word_frequencies, placed_words,
                                         progress, task, config)
                futures.append(future)

            for future in as_completed(futures):
                try:
                    result = future.result()
                    if result[0] is not None:
                        stats.slot_fill_order.append((row, col, direction))
                        return result
                except Exception as e:
                    logging.warning(f"Error in thread: {e}")
        else:
            for _, word in word_scores[:int(local_max_backtrack)]:
                result = try_slot(grid, slot, word, remaining_slots,
                                  words_by_length, word_frequencies,
                                  placed_words, progress, task, config)
                if result[0] is not None:
                    stats.slot_fill_order.append((row, col, direction))
                    return result

    return None, None


def select_words(
        grid: List[List[str]],
        slots: List[Tuple[int, int, str, int]],
        words_by_length: Dict[int, List[str]],
        word_frequencies: Dict[str, float],
        progress: Progress,
        task: TaskID,
        config: Config  # Pass config
) -> Tuple[Optional[List[List[str]]], Optional[List[Tuple[str, int, int, str]]]]:
    """Initializes word selection."""
    global stats
    stats = CrosswordStats()  # Initialize stats here
    stats.start_time = time.time()
    initial_placed_words: List[Tuple[str, int, int, str]] = []

    with ThreadPoolExecutor(max_workers=config.max_thread_pool_size) as executor:  # Use config
        return select_words_recursive(grid, slots, words_by_length,
                                      word_frequencies, initial_placed_words,
                                      progress, task, config,  # Pass config
                                      executor)



# --- Definition and Crossword Generation ---

def order_cell_numbers(slots: List[Tuple[int, int, str, int]]) -> Dict[Tuple[int, int, str], int]:
    """Orders cell numbers for clues."""
    numbered_cells = set()
    cell_numbers: Dict[Tuple[int, int, str], int] = {}
    next_number = 1

    sorted_slots = sorted(slots, key=lambda x: (x[0], x[1], 0 if x[2] == "across" else 1))

    for row, col, direction, length in sorted_slots:
        if (row, col) not in numbered_cells:
            cell_numbers[(row, col, direction)] = next_number
            numbered_cells.add((row, col))
            next_number += 1

    return cell_numbers



def generate_definitions(placed_words: List[Tuple[str, int, int, str]], language: str, config: Config) -> Dict[str, Dict[int, str]]: # pass config
    """Generates definitions, with numbering."""
    definitions = {"across": {}, "down": {}}
    slots = [(row, col, direction, len(word)) for word, row, col, direction in placed_words]
    cell_numbers = order_cell_numbers(slots)

    with Progress() as progress:
        task = progress.add_task("[blue]Generating Definitions...", total=len(placed_words))
        with ThreadPoolExecutor() as executor:
            futures = []
            for word, row, col, direction in placed_words:
                future = executor.submit(generate_definition_langchain, word, language, config) # Pass Config
                futures.append((future, word, row, col, direction))

            for future, word, row, col, direction in futures:
                try:
                    definition = future.result()
                    number = cell_numbers.get((row, col, direction))
                    if number:
                        definitions[direction][f"{number}. {word}"] = definition
                except Exception as e:
                    stats.definition_failures += 1
                    logging.error(f"Error getting definition for {word}: {e}")
                progress.update(task, advance=1)
    return definitions



def create_html(grid: List[List[str]], placed_words: List[Tuple[str, int, int, str]],
                definitions: Dict[str, Dict[int, str]], output_filename: str):
    """Generates the interactive HTML."""
    try:
        with open("template.html", "r", encoding="utf-8") as template_file:
            template = template_file.read()

        grid_html = '<table class="crossword-grid">'
        for row_index, row in enumerate(grid):
            grid_html += "<tr>"
            for col_index, cell in enumerate(row):
                if cell == "#":
                    grid_html += '<td class="black"></td>'
                else:
                    word_info = None
                    for word, word_row, word_col, direction in placed_words:
                        if direction == "across" and row_index == word_row and word_col <= col_index < word_col + len(word):
                            word_info = (word, word_row, word_col, direction, col_index - word_col)
                            break
                        elif direction == "down" and col_index == word_col and word_row <= row_index < word_row + len(word):
                            word_info = (word, word_row, word_col, direction, row_index - word_row)
                            break

                    if word_info:
                        word, word_row, word_col, direction, index_in_word = word_info
                        cell_id = f"{word_row}-{word_col}-{direction}"
                        if index_in_word == 0:
                            slots = [(word, row, col, direction) for word, row, col, direction in placed_words]
                            cell_numbers = order_cell_numbers(slots)
                            number = cell_numbers.get((word_row, word_col, direction), "")
                            grid_html += (
                                f'<td class="white" id="{cell_id}">'
                                f'<div class="cell-container">'
                                f'<span class="number">{number}</span>'
                                f'<input type="text" maxlength="1" class="letter" data-row="{row_index}" data-col="{col_index}" data-direction="{direction}">'
                                f'</div>'
                                f"</td>"
                            )
                        else:
                            grid_html += (
                                f'<td class="white" id="{cell_id}-{index_in_word}">'
                                f'<div class="cell-container">'
                                f'<input type="text" maxlength="1" class="letter" data-row="{row_index}" data-col="{col_index}" data-direction="{direction}">'
                                f'</div>'
                                f"</td>"
                            )
                    else:
                        grid_html += '<td class="white"></td>'
            grid_html += "</tr>"
        grid_html += "</table>"

        definitions_html = '<div class="definitions">'
        for direction, clues in definitions.items():
            definitions_html += f'<h3>{direction.capitalize()}</h3><ol>'
            for clue, definition in clues.items():
                definitions_html += f'<li><span class="clue-number">{clue.split(".")[0]}.</span> {definition}</li>'
            definitions_html += '</ol>'
        definitions_html += '</div>'

        final_html = template.format(grid_html=grid_html, definitions_html=definitions_html)

        with open(output_filename, "w", encoding="utf-8") as output_file:
            output_file.write(final_html)

    except FileNotFoundError:
        logging.error("template.html not found.")
        sys.exit(1)
    except Exception as e:
        logging.error(f"Error generating HTML: {e}")
        sys.exit(1)



def main():
    """Main function to parse arguments and run."""
    parser = argparse.ArgumentParser(description="Generates a crossword.")
    parser.add_argument("--width", type=int, default=DEFAULT_GRID_WIDTH)
    parser.add_argument("--height", type=int, default=DEFAULT_GRID_HEIGHT)
    parser.add_argument("--black_squares", type=float, default=DEFAULT_BLACK_SQUARE_RATIO)
    parser.add_argument("--manual_grid", type=str, default=None)
    parser.add_argument("--grid_file", type=str, default=None)
    parser.add_argument("--lm_studio_url", type=str, default=DEFAULT_LM_STUDIO_URL)
    parser.add_argument("--words_file", type=str, default=DEFAULT_WORDS_FILE)
    parser.add_argument("--output_filename", type=str, default=DEFAULT_OUTPUT_FILENAME)
    parser.add_argument("--max_attempts", type=int, default=DEFAULT_MAX_ATTEMPTS)
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    parser.add_argument("--llm_timeout", type=int, default=DEFAULT_LLM_TIMEOUT)
    parser.add_argument("--llm_max_tokens", type=int, default=DEFAULT_LLM_MAX_TOKENS)
    parser.add_argument("--language", type=str, default=DEFAULT_LANGUAGE)
    parser.add_argument("--model", type=str, default=DEFAULT_MODEL)
    parser.add_argument("--max_grid_iterations", type=int, default=DEFAULT_MAX_GRID_ITERATIONS)
    parser.add_argument("--difficulty", type=str, default=DEFAULT_DIFFICULTY, choices=["easy", "medium", "hard"])

    args = parser.parse_args()

    if not all(isinstance(arg, int) and arg > 0 for arg in [args.width, args.height, args.max_attempts, args.timeout, args.llm_timeout, args.llm_max_tokens, args.max_grid_iterations]):
        logging.error("Positive integers required for numeric arguments.")
        sys.exit(1)
    if not 0.0 <= args.black_squares <= 1.0:
        logging.error("black_squares must be between 0.0 and 1.0.")
        sys.exit(1)
    if args.manual_grid and args.grid_file:
        logging.error("Specify either --manual_grid or --grid_file, not both.")
        sys.exit(1)

    # --- Configuration Initialization ---
    config = Config()
    config.update_from_args(args)


    words_by_length, word_frequencies = load_words(config.words_file, config.min_word_counts[config.difficulty]) # Pass Config

    if not words_by_length:
        logging.error("No valid words found. Check word file and difficulty.")
        sys.exit(1)

    max_dimension = max(config.grid_width, config.grid_height) # use Config
    for length in range(config.min_word_length, max_dimension + 1): # use Config
        if length not in words_by_length:
            logging.warning(f"No words of length {length} found.")

    build_word_index(words_by_length)

    llm_instance = setup_langchain_llm(config) #pass Config
    global llm
    llm = llm_instance

    console = Console()
    
    # Reset slot attempts tracking for fresh start
    global slot_attempts_count
    slot_attempts_count = {}
    
    # Keep track of black square ratio adjustments
    original_black_square_ratio = config.black_square_ratio
    
    for attempt in range(config.max_grid_iterations): # use Config
        console.print(f"\n[bold blue]Attempt {attempt + 1}/{config.max_grid_iterations}[/]") # use Config
        
        # After half the attempts, start adjusting the black square ratio
        if attempt > config.max_grid_iterations // 2 and config.black_square_ratio < 0.4:
            # Gradually increase black square ratio to make grid easier to fill
            config.black_square_ratio = min(0.4, original_black_square_ratio + (attempt / config.max_grid_iterations) * 0.15)
            console.print(f"[yellow]Adjusting black square ratio to {config.black_square_ratio:.2f} to make grid easier to fill[/]")
        
        grid = generate_grid(config) #pass Config

        if not is_valid_grid(grid):
            console.print("[red]Invalid grid. Retrying...")
            continue

        console.print("[green]Initial Grid:[/]")
        print_grid(grid, console=console)

        slots = find_slots(grid, config)  # Pass config
        if not slots:
            console.print("[red]No valid slots. Retrying...")
            continue

        with Progress() as progress:
            task = progress.add_task("[cyan]Selecting words...", total=None)
            filled_grid, placed_words = select_words(grid, slots, words_by_length, word_frequencies, progress, task, config)  # Pass config
            progress.update(task, completed=100)

        if filled_grid is not None:
            console.print("[green]Crossword filled![/]")
            print_grid(filled_grid, placed_words, console)
            definitions = generate_definitions(placed_words, config.language, config) #Pass config
            create_html(filled_grid, placed_words, definitions, config.output_filename) # use config
            console.print(f"[green]Saved to: {config.output_filename}[/]")# use config
            console.print(stats.get_summary())
            break
        else:
            console.print("[yellow]Failed to fill grid. Retrying...")
            console.print(stats.get_summary())
            
            # Increase dynamic backtracking limits progressively
            stats.dynamic_max_backtrack = min(10000, stats.dynamic_max_backtrack * 1.5)
            stats.dynamic_beam_width = min(3000, stats.dynamic_beam_width * 1.3)
            console.print(f"[blue]Increased backtracking limits: max_backtrack={stats.dynamic_max_backtrack}, beam_width={stats.dynamic_beam_width}[/]")

            # Last resort: try aggressive black cell filling if this is the last attempt
            if attempt == config.max_grid_iterations - 1:  # On the last attempt
                console.print("[cyan]Trying aggressive black cell filling as a last resort...")
                # Apply aggressive black cell filling
                modified_grid, modified_slots = final_fill_impossible_spaces(grid, slots, words_by_length, config)

                if modified_grid != grid:  # If the grid was modified
                    console.print("[green]Grid modified with aggressive black cell filling. Trying again...")
                    print_grid(modified_grid, console=console)
                    console.print(f"[blue]Slots reduced from {len(slots)} to {len(modified_slots)}[/]")

                    # Try filling the modified grid
                    with Progress() as progress:
                        task = progress.add_task("[cyan]Filling modified grid...", total=None)
                        filled_grid, placed_words = select_words(modified_grid, modified_slots, words_by_length,
                                                                 word_frequencies, progress, task, config)
                        progress.update(task, completed=100)

                    if filled_grid is not None:
                        console.print("[green]Crossword filled after aggressive black cell filling![/]")
                        print_grid(filled_grid, placed_words, console)
                        definitions = generate_definitions(placed_words, config.language, config)
                        create_html(filled_grid, placed_words, definitions, config.output_filename)
                        console.print(f"[green]Saved to: {config.output_filename}[/]")
                        console.print(stats.get_summary())
                        break
    else:
        console.print("[red]Failed to generate crossword after all attempts.")
        console.print("[yellow]Try adjusting parameters: increase --black_squares, decrease grid size, or use a different word list.[/]")


def fill_impossible_spaces(grid: List[List[str]], slots: List[Tuple[int, int, str, int]], words_by_length: Dict[int, List[str]]) -> Tuple[List[List[str]], List[Tuple[int, int, str, int]]]:
    new_grid = [row[:] for row in grid]
    impossible_slots = []

    for slot in slots:
        row, col, direction, length = slot
        if direction == "across":
            pattern = "".join(grid[row][col:col + length])
        else:
            pattern = "".join(grid[row + i][col] for i in range(length))

        pattern = create_pattern(pattern)
        valid_words = word_index.get((length, pattern), [])

        if not valid_words:
            impossible_slots.append(slot)
            if direction == "across":
                for i in range(length):
                    new_grid[row][col + i] = "#"
            else:
                for i in range(length):
                    new_grid[row + i][col] = "#"

    if impossible_slots:
        remaining_slots = [s for s in slots if s not in impossible_slots]
        return new_grid, remaining_slots
    return grid, slots


def final_fill_impossible_spaces(grid: List[List[str]], slots: List[Tuple[int, int, str, int]],
                                words_by_length: Dict[int, List[str]], config: Config) -> Tuple[List[List[str]], List[Tuple[int, int, str, int]]]:
    """More aggressive black cell filling for endgame situations."""
    new_grid = [row[:] for row in grid]
    impossible_slots = []
    difficult_slots = []
    
    # Identify slots with high attempt counts as potential problems
    high_attempt_slots = []
    for (row, col, direction), count in slot_attempts_count.items():
        if count > 5:
            matching_slot = next((s for s in slots if s[0] == row and s[1] == col and s[2] == direction), None)
            if matching_slot:
                high_attempt_slots.append((matching_slot, count))
                
    high_attempt_slots.sort(key=lambda x: x[1], reverse=True)
    
    # First process slots that have no valid words
    for slot in slots:
        row, col, direction, length = slot
        if direction == "across":
            pattern = "".join(grid[row][col:col + length])
        else:
            pattern = "".join(grid[row + i][col] for i in range(length))

        pattern = create_pattern(pattern)
        valid_words = word_index.get((length, pattern), [])

        if not valid_words:
            impossible_slots.append(slot)
            if direction == "across":
                for i in range(length):
                    new_grid[row][col + i] = "#"
            else:
                for i in range(length):
                    new_grid[row + i][col] = "#"
        elif len(valid_words) < 3:  # Consider slots with very few options as difficult
            difficult_slots.append((slot, len(valid_words)))

    # If no impossible slots but have high attempt slots, try to resolve them
    if not impossible_slots and high_attempt_slots:
        slot_info, _ = high_attempt_slots[0]  # Take the slot with highest attempt count
        row, col, direction = slot_info[0], slot_info[1], slot_info[2]
        for s in slots:
            if s[0] == row and s[1] == col and s[2] == direction:
                length = s[3]
                # For long slots, try splitting them by adding a black square in the middle
                if length > 4:
                    mid = length // 2
                    if direction == "across":
                        new_grid[row][col + mid] = "#"
                    else:
                        mid = length // 2
                        new_grid[row + mid][col] = "#"
                    impossible_slots.append(s)
                break

    # If still no resolution, try difficult slots
    if not impossible_slots and difficult_slots:
        difficult_slots.sort(key=lambda x: x[1])  # Sort by number of valid words
        slot, _ = difficult_slots[0]  # Take the most constrained slot
        row, col, direction, length = slot

        # Try filling part of the slot with black squares
        if length > 3:  # Only try for longer words
            if direction == "across":
                mid = length // 2
                new_grid[row][col + mid] = "#"
            else:
                mid = length // 2
                new_grid[row + mid][col] = "#"
            impossible_slots.append(slot)
    
    # If we're still stuck, try a more aggressive approach for very difficult grids
    if not impossible_slots and len(high_attempt_slots) > 2:
        # Try to break the grid in multiple places to force a solution
        modified = False
        for slot_info, _ in high_attempt_slots[:3]:  # Take top 3 problematic slots
            slot = next((s for s in slots if s[0] == slot_info[0] and s[1] == slot_info[1] and s[2] == slot_info[2]), None)
            if slot:
                row, col, direction, length = slot
                if length > 3:
                    # Add black squares to break difficult patterns
                    if direction == "across":
                        third = length // 3
                        new_grid[row][col + third] = "#"
                    else:
                        third = length // 3
                        new_grid[row + third][col] = "#"
                    impossible_slots.append(slot)
                    modified = True
        
        if modified:
            logging.info("Applied aggressive grid breaking to solve difficult pattern")

    if impossible_slots:
        remaining_slots = [s for s in slots if s not in impossible_slots]
        return new_grid, remaining_slots
    return grid, slots



# --- Statistics Tracking ---
class CrosswordStats:
    """Tracks crossword generation statistics."""
    def __init__(self):
        self.attempts = 0
        self.backtracks = 0
        self.words_tried = 0
        self.successful_placements = 0
        self.failed_placements = 0
        self.time_spent = 0.0
        self.start_time = time.time()
        self.slot_fill_order = []  # Initialize as empty list
        self.definition_failures = 0
        self.dynamic_beam_width = DEFAULT_BEAM_WIDTH
        self.dynamic_max_backtrack = DEFAULT_MAX_BACKTRACK
        self.difficult_slots = defaultdict(int)  # Track difficult slots

    def update_time(self):
        self.time_spent = time.time() - self.start_time

    def get_summary(self) -> str:
        self.update_time()
        
        # Get top difficult slots if any
        difficult_slots_info = ""
        if self.difficult_slots:
            top_difficult = sorted(self.difficult_slots.items(), key=lambda x: x[1], reverse=True)[:3]
            difficult_slots_info = "\n├── Most Difficult Slots: " + ", ".join([f"({r},{c},{d}): {count} attempts" for (r,c,d), count in top_difficult])
        
        slot_order = "\n└── Slots Filled Order: [" + ", ".join([f"({r},{c},{d})" for r,c,d in self.slot_fill_order]) + "]"
        
        return (
            "📊 Crossword Generation Stats:\n"
            f"├── Attempts: {self.attempts}\n"
            f"├── Backtracks: {self.backtracks}\n"
            f"├── Words Tried: {self.words_tried}\n"
            f"├── Successful Placements: {self.successful_placements}\n"
            f"├── Failed Placements: {self.failed_placements}\n"
            f"├── Definition Failures: {self.definition_failures}\n"
            f"├── Dynamic Beam Width: {self.dynamic_beam_width}\n"
            f"├── Dynamic Max Backtrack: {self.dynamic_max_backtrack}\n"
            f"├── Success Rate: {self.successful_placements / max(1, self.words_tried) * 100:.2f}%\n"
            f"├── Time Spent: {self.time_spent:.2f}s"
            f"{difficult_slots_info}"
            f"{slot_order}")

# Initialize global stats object
stats = CrosswordStats()

if __name__ == "__main__":
    main()