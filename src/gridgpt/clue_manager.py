import os
import json
import random
import logging
from typing import Dict, List

from .word_database_manager import WordDatabaseManager
from .llm_connection import LLMConnection
from .utils import load_prompts

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


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
        clues = {k: clues[k] for k in sorted(clues.keys())}
        
        # Add the clues to the crossword
        crossword["clues"] = clues
        
        return clues
    
    
    def retrieve_clue(self, word: str):
        available_clues = self.get_available_clues(word)
        selected_clue = self.select_random_clue(available_clues)
        return selected_clue if selected_clue else f"Clue could not be retrieved. The answer is {word.upper()}"
    
    
    def get_available_clues(self, word: str):
        available_clues = self.word_db_manager.word_database_full.get(word, {}).get("clues", {})
        
        # Remove any clues relating to other entries (not suitable for new crossword)
        available_clues = [clue for clue in available_clues if "Across" not in clue and "Down" not in clue]
        return available_clues
    
    
    def select_random_clue(self, clues: List):
        if not clues:
            return None
        return random.choice(clues) if len(clues) > 1 else clues[0]
    
    
class ClueGenerator(LLMConnection, ClueRetriever):
    def __init__(self, clue_database_path: str = "data/02_intermediary/crossword_clues.json", word_db_manager: WordDatabaseManager = None):
        """Initialize clue generator with a clue database if available."""
        LLMConnection.__init__(self)  # Initialize LLM connection
        ClueRetriever.__init__(self, word_db_manager)  # Initialize ClueRetriever with word database manager
        self.clue_database = self.load_clue_database(clue_database_path)
        
        prompts_library = load_prompts()
        self.prompt = prompts_library['clue_generator']
    
    
    def load_clue_database(self, path: str) -> Dict[str, List[str]]:
        """Load clue database from JSON file if it exists."""
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Error loading clue database from {path}: {e}")
        
        logger.info(f"No clue database found at {path}, will generate all clues")
        return {}
    
    
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
            deployment_name = os.environ.get("AZURE_GPT4_DEPLOYMENT", "gpt-4o-mini")
            
            # Retrieve existing clues for reference
            reference_clues = self.get_available_clues(word)
            reference_clues = reference_clues if len(reference_clues) > 0 else "No reference clues available."
            
            # Insert word, theme and reference clues into prompt
            formatted_prompt = self.prompt['user_prompt'].format(
                word=word, theme=theme, reference_clues=reference_clues
            )

            response = self.llm.chat.completions.create(
                model=deployment_name,
                messages=[
                    {"role": "system", "content": self.prompt['system_prompt']},
                    {"role": "user", "content": formatted_prompt}
                ],
                max_tokens=50,
                temperature=0.7
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
        clues = {k: clues[k] for k in sorted(clues.keys())}
        
        # Add the clues to the crossword
        crossword["clues"] = clues
        
        return clues


# Helper function for use in main script
def generate_clues(filled_grid: Dict, theme: str = None) -> Dict[str, str]:
    """Generate clues for the crossword."""
    generator = ClueGenerator()
    return generator.generate_clues(filled_grid, theme)

def retrieve_existing_clues(filled_grid: Dict, word_db_manager: WordDatabaseManager = None) -> Dict[str, str]:
    """Retrieve existing clues for the crossword."""
    retriever = ClueRetriever(word_db_manager)
    return retriever.retrieve_existing_clues(filled_grid)