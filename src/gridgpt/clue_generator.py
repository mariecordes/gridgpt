import os
import json
import random
import logging
from typing import Dict, List, Tuple, Optional, Any
import requests

from .llm_connection import LLMConnection

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class ClueGenerator(LLMConnection):
    def __init__(self, clue_database_path: str = "data/02_intermediary/crossword_clues.json"):
        """Initialize clue generator with a clue database if available."""
        super().__init__()  # Initialize LLM connection
        self.clue_database = self.load_clue_database(clue_database_path)
        
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
    
    def generate_theme_clue(self, word: str, theme: str) -> str:
        """
        Generate a clue for a theme word using the LLM.
        
        Args:
            word: The theme word to generate a clue for
            theme: The overall crossword theme
            
        Returns:
            Generated clue
        """
        if not self.llm_connection_success:
            return self.generate_standard_clue(word)
        
        try:
            # Create the prompt
            prompt = f"""Generate a creative crossword clue for the word "{word}" related to the theme "{theme}".
            The clue should be clever, concise (10 words or less), and appropriate for a crossword puzzle.
            Return only the clue text without quotes or explanations."""
            
            # Call the LLM - Azure requires deployment name instead of model name
            # Assuming deployment name is "gpt-4o-mini" but can be changed in environment variables
            deployment_name = os.environ.get("AZURE_GPT4_DEPLOYMENT", "gpt-4o-mini")
            
            response = self.llm.chat.completions.create(
                model=deployment_name,
                messages=[
                    {"role": "system", "content": "You are a helpful crossword clue generator."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=50,
                temperature=0.7
            )
            
            # Extract the clue from the response
            clue = response.choices[0].message.content.strip()
            
            # Clean up the response (remove quotes, etc.)
            clue = clue.strip('"\'')
            if clue.endswith('.'):
                clue = clue[:-1]
                
            logger.info(f"Generated theme clue for '{word}': '{clue}'")
            return clue
            
        except Exception as e:
            logger.error(f"Error generating theme clue for '{word}': {e}")
            return self.generate_standard_clue(word)
    
    def generate_standard_clue(self, word: str) -> str:
        """
        Generate a standard clue for a non-theme word.
        
        Args:
            word: The word to generate a clue for
            
        Returns:
            Generated clue
        """
        # Check if we have clues for this word in our database
        word_upper = word.upper()
        if word_upper in self.clue_database and self.clue_database[word_upper]:
            clue = random.choice(self.clue_database[word_upper])
            logger.debug(f"Using database clue for '{word}': '{clue}'")
            return clue
            
        # If no database clue is available, generate a simple definition
        if not self.llm:
            success = self.init_llm_connection()
            if not success:
                return f"Definition of {word}"  # Fallback
        
        try:
            # Create the prompt
            prompt = f"""Generate a straightforward crossword clue for the word "{word}".
            The clue should be a simple definition or synonym, concise (7 words or less), 
            and suitable for a standard crossword puzzle.
            Return only the clue text without quotes or explanations."""
            
            # Call the LLM - Azure requires deployment name instead of model name
            # Assuming deployment name is "gpt-35-turbo" but can be changed in environment variables
            deployment_name = os.environ.get("AZURE_GPT4_DEPLOYMENT", "gpt-4o-mini")

            response = self.llm.chat.completions.create(
                model=deployment_name,  # Use cheaper model for standard clues
                messages=[
                    {"role": "system", "content": "You are a helpful crossword clue generator."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=30,
                temperature=0.5
            )
            
            # Extract the clue
            clue = response.choices[0].message.content.strip()
            
            # Clean up
            clue = clue.strip('"\'')
            if clue.endswith('.'):
                clue = clue[:-1]
                
            logger.debug(f"Generated standard clue for '{word}': '{clue}'")
            return clue
            
        except Exception as e:
            logger.error(f"Error generating standard clue for '{word}': {e}")
            return f"Definition of {word}"  # Fallback
    
    def generate_mixed_clues(self, crossword: Dict, theme: str) -> Dict[str, str]:
        """
        Generate clues for the entire crossword, using theme-specific
        clues for theme words and standard clues for others.
        
        Args:
            crossword: The completed crossword with filled slots
            theme: The overall crossword theme
            
        Returns:
            Dictionary of {slot_id: clue} pairs
        """
        clues = {}
        filled_slots = crossword.get("filled_slots", {})
        theme_entries = crossword.get("theme_entries", {})
        
        logger.info(f"Generating clues for {len(filled_slots)} words ({len(theme_entries)} theme entries)")
        
        # Generate clues for each word
        for slot_id, word in filled_slots.items():
            if slot_id in theme_entries:
                # Generate theme-specific clue
                clues[slot_id] = self.generate_theme_clue(word, theme)
            else:
                # Generate standard clue
                clues[slot_id] = self.generate_standard_clue(word)
        
        # Add the clues to the crossword
        crossword["clues"] = clues
        
        return clues

# Helper function for use in main script
def generate_mixed_clues(filled_grid: Dict, theme: str = None) -> Dict[str, str]:
    """Generate mixed clues for the crossword."""
    generator = ClueGenerator()
    return generator.generate_mixed_clues(filled_grid, theme)