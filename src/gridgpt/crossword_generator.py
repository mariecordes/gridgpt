import json
import os
import random
from typing import Dict, List, Set, Tuple, Optional, Any
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class CrosswordGenerator:
    def __init__(self, word_database_path: str = "data/02_intermediary/word_database/word_database_filtered_list.json"):
        """Initialize the crossword generator with a word database."""
        self.word_database = self.load_word_database(word_database_path)
        self.words_by_length = self.organize_words_by_length()
        
    def load_word_database(self, path: str) -> List[str]:
        """Load the word database from a JSON file."""
        try:
            with open(path, 'r', encoding='utf-8') as f:
                words = json.load(f)
            logger.info(f"Loaded {len(words)} words from database")
            return words
        except Exception as e:
            logger.error(f"Error loading word database from {path}: {e}")
            return []
            
    def organize_words_by_length(self) -> Dict[int, List[str]]:
        """Organize words by length for faster lookup."""
        words_by_length = {}
        for word in self.word_database:
            length = len(word)
            if length not in words_by_length:
                words_by_length[length] = []
            words_by_length[length].append(word.upper())  # Store words in uppercase
        return words_by_length
    
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
        
        # Check length constraints
        if len(theme_entry) < min_length:
            return False, f"Theme entry too short. Minimum length is {min_length} characters."
        
        if len(theme_entry) > max_length:
            return False, f"Theme entry too long. Maximum length is {max_length} characters."
        
        # Check for special characters
        if not theme_entry.isalpha():
            return False, "Theme entry must contain only letters (A-Z)."
        
        # Check if word exists in our database
        if theme_entry not in self.word_database and theme_entry.lower() not in self.word_database:
            # Allow multi-word theme entries even if they're not in the database
            if " " in theme_entry:
                # Just check if all individual words exist
                individual_words = theme_entry.split()
                all_valid = all(word in self.word_database or word.lower() in self.word_database 
                               for word in individual_words)
                if not all_valid:
                    return False, "Theme entry contains words not in our database."
            else:
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
            # Find closest matching slots
            candidate_slots.sort(key=lambda s: abs(s["length"] - entry_length))
            closest_length = candidate_slots[0]["length"]
            logger.info(f"Closest available slot length is {closest_length}")
        
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
        direction = chosen_slot["direction"]
        
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
        intersections = []
        
        # Find the target slot
        target_slot = None
        for slot in template["slots"]:
            if slot["id"] == slot_id:
                target_slot = slot
                break
        
        if not target_slot:
            return []
        
        # Get cells of the target slot
        target_cells = target_slot["cells"]
        
        # Check each other slot for intersections
        for slot in template["slots"]:
            if slot["id"] == slot_id:
                continue  # Skip the slot itself
            
            # Check for cell intersections
            for i, target_cell in enumerate(target_cells):
                try:
                    j = slot["cells"].index(target_cell)
                    intersections.append((slot["id"], i, j))
                except ValueError:
                    continue  # Cell not in this slot
        
        return intersections
    
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
    
    def get_possible_words(self, template: Dict, slot: Dict, fixed_letters: Dict[int, str]) -> List[str]:
        """
        Get all possible words for a slot given the fixed letters.
        
        Args:
            template: The crossword template
            slot: The slot to fill
            fixed_letters: Dictionary mapping positions to fixed letters
            
        Returns:
            List of possible words that match the constraints
        """
        length = slot["length"]
        
        # Get all words of the right length
        all_words = self.words_by_length.get(length, [])
        
        # Filter for words that match the fixed letters
        valid_words = []
        
        for word in all_words:
            matches = True
            for pos, letter in fixed_letters.items():
                if 0 <= pos < len(word) and word[pos] != letter:
                    matches = False
                    break
            if matches:
                valid_words.append(word)
        
        return valid_words
    
    def fill_grid_with_constraints(self, template_with_theme: Dict) -> Dict:
        """
        Fill the grid using constraint satisfaction.
        
        Args:
            template_with_theme: Template with theme entry already placed
            
        Returns:
            Completed crossword grid
        """
        # Start with a copy of the template
        result = template_with_theme.copy()
        result["grid"] = [row.copy() for row in template_with_theme["grid"]]
        result["filled_slots"] = template_with_theme.get("filled_slots", {}).copy()
        
        # Get all slots
        all_slots = result["slots"]
        
        # Sort slots by number of intersections (most constrained first)
        slot_intersections = {}
        for slot in all_slots:
            slot_id = slot["id"]
            if slot_id in result["filled_slots"]:
                continue  # Skip already filled slots
            
            intersections = self.get_intersecting_slots(result, slot_id)
            slot_intersections[slot_id] = len(intersections)
        
        # Sort slots by number of intersections (most constrained first)
        sorted_slots = sorted(
            [s for s in all_slots if s["id"] not in result["filled_slots"]], 
            key=lambda s: slot_intersections[s["id"]], 
            reverse=True
        )
        
        # Now fill slots one by one
        for slot in sorted_slots:
            slot_id = slot["id"]
            
            # Get constraints from intersecting slots
            fixed_letters = {}
            
            for other_slot_id, pos_in_slot, pos_in_other in self.get_intersecting_slots(result, slot_id):
                if other_slot_id in result["filled_slots"]:
                    # Get letter from the already filled slot
                    letter = self.get_letter_at_position(result, other_slot_id, pos_in_other)
                    if letter:
                        fixed_letters[pos_in_slot] = letter
            
            # Get possible words for this slot
            possible_words = self.get_possible_words(result, slot, fixed_letters)
            
            if not possible_words:
                logger.warning(f"No words available for slot {slot_id} with constraints {fixed_letters}")
                return None  # Backtracking needed
            
            # Choose a random word (or use a more sophisticated selection)
            chosen_word = random.choice(possible_words)
            
            # Place the word in the grid
            cells = slot["cells"]
            for i, cell in enumerate(cells):
                row, col = cell
                result["grid"][row][col] = chosen_word[i]
            
            # Add to filled slots
            result["filled_slots"][slot_id] = chosen_word
            
            logger.debug(f"Filled slot {slot_id} with '{chosen_word}'")
        
        logger.info(f"Grid filled successfully with {len(result['filled_slots'])} words")
        return result
    
    def backtracking_fill(self, template_with_theme: Dict, max_attempts: int = 20) -> Dict:
        """
        Try to fill the grid with backtracking if simple constraint satisfaction fails.
        
        Args:
            template_with_theme: Template with theme entry already placed
            max_attempts: Maximum number of attempts before giving up
            
        Returns:
            Completed crossword grid or None if failed
        """
        for attempt in range(max_attempts):
            logger.info(f"Attempt {attempt+1}/{max_attempts} to fill the grid")
            
            filled_grid = self.fill_grid_with_constraints(template_with_theme)
            if filled_grid:
                return filled_grid
        
        logger.error("Failed to fill the grid after multiple attempts")
        return None
    
    def generate_crossword(self, template: Dict, theme_entry: str = None) -> Dict:
        """
        Generate a complete crossword puzzle.
        
        Args:
            template: The crossword template
            theme_entry: Optional user-provided theme entry
            
        Returns:
            Completed crossword puzzle
        """
        # Validate theme entry if provided
        if theme_entry:
            is_valid, message = self.validate_theme_entry(theme_entry)
            if not is_valid:
                raise ValueError(message)
            
            # Place theme entry
            template_with_theme = self.place_theme_entry(template, theme_entry)
        else:
            # No theme entry provided
            template_with_theme = template.copy()
            template_with_theme["filled_slots"] = {}
            template_with_theme["theme_entries"] = {}
        
        # Fill the grid
        filled_crossword = self.backtracking_fill(template_with_theme)
        
        return filled_crossword

def print_grid(grid: List[List[str]]):
    """Print a grid in a readable format."""
    horizontal_line = "+---" * len(grid[0]) + "+"
    
    print(horizontal_line)
    for row in grid:
        print("| " + " | ".join(cell if cell != "#" else " " for cell in row) + " |")
        print(horizontal_line)

def generate_themed_crossword(template: Dict, theme_entry: str = None, max_attempts: int = 20) -> Dict:
    """
    Generate a themed crossword puzzle.
    
    Args:
        template: The crossword template to use
        theme_entry: Optional user-provided theme entry
        
    Returns:
        Generated crossword puzzle
    """
    generator = CrosswordGenerator()
    
    if theme_entry:
        logger.info(f"Generating crossword with theme entry: '{theme_entry}'")
    else:
        logger.info("Generating crossword without theme entry")
    
    # Generate the crossword
    for attempt in range(max_attempts):
        logger.info(f"Attempt {attempt + 1}/{max_attempts} to generate crossword")
        
        try:
            crossword = generator.generate_crossword(template, theme_entry)
            if crossword:
                logger.info("Crossword generated successfully")
                break
        except Exception as e:
            logger.error(f"Error generating crossword: {e}")
            if attempt == max_attempts - 1:
                raise
    # crossword = generator.generate_crossword(template, theme_entry)
    
    # Print the result
    print("\nGenerated Crossword:")
    print_grid(crossword["grid"])
    
    print("\nFilled Slots:")
    for slot_id, word in sorted(crossword["filled_slots"].items()):
        is_theme = slot_id in crossword.get("theme_entries", {})
        theme_marker = "🌟 " if is_theme else ""
        print(f"{theme_marker}{slot_id}: {word}")
    
    return crossword