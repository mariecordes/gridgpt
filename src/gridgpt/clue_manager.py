import os
import json
import re
import random
import logging
from typing import Dict, List

from .word_database_manager import WordDatabaseManager, is_reference_clue
from .llm_connection import LLMConnection
from .utils import load_prompts

logger = logging.getLogger(__name__)


def slot_sort_key(slot_id: str):
    """Sort key for slot ids like '2A' or '10D' by (number, direction).

    Plain string sorting orders '10A' before '2A'; this keeps numeric order.
    """
    match = re.match(r"(\d+)([A-Za-z]*)", slot_id)
    if match:
        return (int(match.group(1)), match.group(2))
    return (0, slot_id)


# Numerals a clue might use to stand in for a spelled-out answer (e.g. "1:00
# a.m." for ONEAM). Used only for reveal-checking, so a modest map is enough.
_NUMBER_WORDS = {
    0: "zero", 1: "one", 2: "two", 3: "three", 4: "four", 5: "five",
    6: "six", 7: "seven", 8: "eight", 9: "nine", 10: "ten", 11: "eleven",
    12: "twelve", 13: "thirteen", 14: "fourteen", 15: "fifteen", 16: "sixteen",
    17: "seventeen", 18: "eighteen", 19: "nineteen", 20: "twenty", 30: "thirty",
    40: "forty", 50: "fifty", 60: "sixty", 70: "seventy", 80: "eighty",
    90: "ninety", 100: "hundred",
}


def _strip_non_alnum(text: str) -> str:
    """Lowercase and drop everything but letters and digits."""
    return re.sub(r"[^a-z0-9]", "", text.lower())


def _numerals_to_words(text: str) -> str:
    """Rewrite numerals in a clue as words, so a numeric clue can be checked
    against a spelled-out answer. Clock times collapse to their hour first
    ("1:00" -> "1"), then known integers become words ("1" -> "one")."""
    text = re.sub(r"\b(\d{1,2}):\d{2}\b", r"\1", text.lower())
    return re.sub(r"\d+", lambda m: _NUMBER_WORDS.get(int(m.group()), m.group()), text)


class ClueRetriever():
    def __init__(self, word_db_manager: WordDatabaseManager = None):
        """Initialize the clue retriever with a word database manager."""
        if word_db_manager is None:
            self.word_db_manager = WordDatabaseManager()
        else:
            self.word_db_manager = word_db_manager
    
    
    def retrieve_existing_clues(self, crossword: Dict) -> Dict[str, str]:
        """
        Retrieve clues for the entire crossword from the word database.
        
        Args:
            crossword: The completed crossword with filled slots
            
        Returns:
            Dictionary of {slot_id: clue} pairs
        """
        clues = {}
        filled_slots = crossword.get("filled_slots", {})
        
        logger.info(f"Retrieving clues for {len(filled_slots)} words")
        
        # Retrieve clues for each word
        for slot_id, word in filled_slots.items():
            clues[slot_id] = self.retrieve_clue(word)
        
        # Order keys by slot ID
        clues = {k: clues[k] for k in sorted(clues.keys(), key=slot_sort_key)}
        
        # Add the clues to the crossword
        crossword["clues"] = clues
        
        return clues
    
    
    def retrieve_clue(self, word: str):
        available_clues = self.get_available_clues(word)
        selected_clue = self.select_random_clue(available_clues)
        return selected_clue if selected_clue else f"Clue could not be retrieved. The answer is {word.upper()}"
    
    
    def get_available_clues(self, word: str):
        available_clues = self.word_db_manager.word_database_full.get(word, {}).get("clues", [])

        # Remove cross-reference clues (e.g. "See 5-Across")
        available_clues = [clue for clue in available_clues if not is_reference_clue(clue)]
        return available_clues
    
    
    def select_random_clue(self, clues: List):
        if not clues:
            return None
        return random.choice(clues) if len(clues) > 1 else clues[0]
    
    
class ClueGenerator(LLMConnection, ClueRetriever):
    def __init__(self, word_db_manager: WordDatabaseManager = None):
        """Initialize clue generator with LLM connection and prompts."""
        LLMConnection.__init__(self)  # Initialize LLM connection
        ClueRetriever.__init__(self, word_db_manager)  # Initialize ClueRetriever with word database manager
        
        prompts_library = load_prompts()
        self.prompt = prompts_library['clue_generator']
        self.batch_prompt = prompts_library['clue_generator_batch']


    def generate_clue(self, word: str, theme: str) -> str:
        """
        Generate a clue for a theme word using the LLM.
        
        Args:
            word: The theme word to generate a clue for
            theme: The overall crossword theme
            
        Returns:
            Generated clue
        """
        if not self.llm_connection_success:
            logger.warning(f"No LLM connection, retrieving clue for word '{word}' instead of generating it.")
            return self.retrieve_clue(word)
        
        try:
            model_override = os.environ.get("OPENAI_CLUE_MODEL")  # optional override
            
            # Retrieve existing clues for reference
            reference_clues = self.get_available_clues(word)
            reference_clues = reference_clues if len(reference_clues) > 0 else "No reference clues available."
            
            # Insert word, theme and reference clues into prompt
            formatted_prompt = self.prompt['user_prompt'].format(
                word=word, theme=theme, reference_clues=reference_clues
            )

            response = self.llm.chat.completions.create(
                model=model_override or self.model_name,
                messages=[
                    {"role": "system", "content": self.prompt['system_prompt']},
                    {"role": "user", "content": formatted_prompt}
                ],
                temperature=0.7,
            )
            
            # Extract the clue from the response
            clue = response.choices[0].message.content.strip()
                
            logger.info(f"Generated clue for '{word}': '{clue}'")
            return clue
            
        except Exception as e:
            logger.error(f"Error generating theme clue for '{word}': {e}")
            return self.retrieve_clue(word)
    
    
    def generate_clues(self, crossword: Dict, theme: str) -> Dict[str, str]:
        """
        Generate clues for the entire crossword.
        
        Args:
            crossword: The completed crossword with filled slots
            theme: The overall crossword theme
            
        Returns:
            Dictionary of {slot_id: clue} pairs
        """
        clues = {}
        filled_slots = crossword.get("filled_slots", {})
        
        logger.info(f"Generating clues for {len(filled_slots)} words")
        
        # Generate clues for each word
        for slot_id, word in filled_slots.items():
            clues[slot_id] = self.generate_clue(word, theme)
        
        # Order keys by slot ID
        clues = {k: clues[k] for k in sorted(clues.keys(), key=slot_sort_key)}

        # Add the clues to the crossword
        crossword["clues"] = clues

        return clues


    def _finalize_clues(self, crossword: Dict, clues: Dict[str, str]) -> Dict[str, str]:
        """Order clues by slot id and attach them to the crossword."""
        clues = {k: clues[k] for k in sorted(clues.keys(), key=slot_sort_key)}
        crossword["clues"] = clues
        return clues


    @staticmethod
    def _clue_reveals_answer(word: str, clue: str) -> bool:
        """True if the clue gives away its own answer, allowing for punctuation,
        spacing and numerals. Catches plain substrings ("a cat" for CAT),
        punctuation-split reveals ("a.m." for AM) and numeral reveals ("1:00
        a.m." for ONEAM). The whole answer is matched against the (rewritten)
        clue, never the reverse, so a number word merely embedded in the answer
        (e.g. "one" in STONE) does not cause a false positive."""
        answer = _strip_non_alnum(word)
        if not answer:
            return False
        if answer in _strip_non_alnum(clue):
            return True
        if answer in _strip_non_alnum(_numerals_to_words(clue)):
            return True
        return False

    @staticmethod
    def _is_valid_clue(word: str, clue) -> bool:
        """A batch clue is usable only if it is a non-empty string that does not
        give away its own answer (directly, or via punctuation or numerals),
        per the fairness rules."""
        if not isinstance(clue, str) or not clue.strip():
            return False
        if ClueGenerator._clue_reveals_answer(word, clue):
            return False
        return True


    def _format_batch_entries(self, ordered_slots: List) -> str:
        """Build the answer list block for the batch prompt: one line per slot
        with the answer word and up to 3 sampled reference clues for context."""
        lines = []
        for slot_id, word in ordered_slots:
            refs = self.get_available_clues(word)
            if refs:
                sampled = random.sample(refs, min(3, len(refs)))
                ref_str = "; ".join(sampled)
            else:
                ref_str = "none available"
            lines.append(f"- {slot_id} = {word} (reference clues: {ref_str})")
        return "\n".join(lines)


    def _request_batch_clues(self, ordered_slots: List, theme: str) -> Dict:
        """Make a single LLM call returning a JSON object of {slot_id: clue}."""
        model_override = os.environ.get("OPENAI_CLUE_MODEL")  # optional override
        entries = self._format_batch_entries(ordered_slots)
        user_prompt = self.batch_prompt['user_prompt'].format(theme=theme, entries=entries)

        response = self.llm.chat.completions.create(
            model=model_override or self.model_name,
            messages=[
                {"role": "system", "content": self.batch_prompt['system_prompt']},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.7,
            response_format={"type": "json_object"},
        )
        data = json.loads(response.choices[0].message.content)
        if not isinstance(data, dict):
            raise ValueError("Batch clue response was not a JSON object")
        return data


    def generate_clues_batch(self, crossword: Dict, theme: str) -> Dict[str, str]:
        """
        Generate clues for the whole crossword in a single LLM call.

        One request returns a clue per slot, which lets the model keep the set
        coherent (consistent voice, varied angles). Any slot whose clue is
        missing or fails validation (empty, or contains its own answer) falls
        back to the per-word generator, which in turn falls back to retrieval.
        With no LLM connection, all clues are retrieved from the database.

        Args:
            crossword: The completed crossword with filled slots
            theme: The overall crossword theme (None if no theme)

        Returns:
            Dictionary of {slot_id: clue} pairs
        """
        filled_slots = crossword.get("filled_slots", {})
        if not filled_slots:
            return self._finalize_clues(crossword, {})

        if not self.llm_connection_success:
            logger.warning("No LLM connection, retrieving clues instead of generating them.")
            return self._finalize_clues(
                crossword,
                {slot_id: self.retrieve_clue(word) for slot_id, word in filled_slots.items()},
            )

        ordered_slots = sorted(filled_slots.items(), key=lambda kv: slot_sort_key(kv[0]))
        logger.info(f"Generating clues for {len(ordered_slots)} words in a single batch call")

        try:
            raw_clues = self._request_batch_clues(ordered_slots, theme)
        except Exception as e:
            logger.error(f"Batch clue generation failed ({e}); falling back to per-word generation.")
            return self.generate_clues(crossword, theme)

        clues = {}
        for slot_id, word in ordered_slots:
            candidate = raw_clues.get(slot_id)
            if self._is_valid_clue(word, candidate):
                clues[slot_id] = candidate.strip()
            else:
                logger.info(f"Batch clue for {slot_id} ('{word}') missing or invalid; regenerating individually.")
                clues[slot_id] = self.generate_clue(word, theme)

        return self._finalize_clues(crossword, clues)


# Helper function for use in main script
def generate_clues(filled_grid: Dict, theme: str = None, word_db_manager: WordDatabaseManager = None) -> Dict[str, str]:
    """Generate clues for the crossword in one batched LLM call (per-word fallback)."""
    generator = ClueGenerator(word_db_manager=word_db_manager)
    return generator.generate_clues_batch(filled_grid, theme)

def retrieve_existing_clues(filled_grid: Dict, word_db_manager: WordDatabaseManager = None) -> Dict[str, str]:
    """Retrieve existing clues for the crossword."""
    retriever = ClueRetriever(word_db_manager)
    return retriever.retrieve_existing_clues(filled_grid)