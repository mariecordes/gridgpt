import json
import os
import re
import logging
from collections import defaultdict
from typing import Dict

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class WordDBProcessor:
    def __init__(self):
        """
        Initialize the WordDB processor.

        This module processes scraped NYT Mini crossword data from WordDB.com
        and creates a comprehensive word database for crossword generation.

        The database is word-based with the following structure:
        {
            "WORD": {
                "length": 4,
                "frequency": 12,
                "clues": ["First clue", "Second clue", ...],
                "dates": ["2025-01-01", "2025-01-02", ...]
            }
        }
        """
        self.word_database = defaultdict(lambda: {
            'length': 0,
            'frequency': 0,
            'clues': [],
            'dates': []
        })
    
    
    def normalize_word(self, word: str) -> str:
        """
        Normalize a word by removing spaces, symbols, and converting to uppercase.
        
        Examples:
            "JELL-O" -> "JELLO"
            "BAND AID" -> "BANDAID"
            "chem lab" -> "CHEMLAB"
        """
        if not word:
            return ""
        
        # Convert to uppercase and remove all non-alphabetic characters
        normalized = re.sub(r'[^A-Z]', '', word.upper())
        return normalized
    
    
    def load_scraped_data(self, input_file: str) -> Dict:
        """Load the scraped data from the WordDB scraper output."""
        try:
            with open(input_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            logger.info(f"Loaded scraped data from {input_file}")
            return data
        except FileNotFoundError:
            logger.error(f"Input file not found: {input_file}")
            raise
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in {input_file}: {e}")
            raise
    
    
    def process_scraped_data(self, scraped_data: Dict) -> Dict:
        """
        Process the scraped data and build the word database.
        
        Args:
            scraped_data: Dictionary with dates as keys and word-clue pairs as values
            
        Returns:
            Word database dictionary
        """
        logger.info("Processing scraped data to build word database...")
        
        for date, word_clue_pairs in scraped_data.items():
            if not word_clue_pairs:  # Skip empty dates
                continue
                
            logger.debug(f"Processing {len(word_clue_pairs)} words for date {date}")
            
            for raw_word, clue in word_clue_pairs.items():
                # Normalize the word
                normalized_word = self.normalize_word(raw_word)
                
                if not normalized_word:  # Skip empty words
                    logger.warning(f"Skipping empty word from '{raw_word}' on {date}")
                    continue
                
                # Update word entry
                word_entry = self.word_database[normalized_word]
                
                # Set length (should be consistent)
                word_entry['length'] = len(normalized_word)
                
                # Add clue if unique
                if clue and clue not in word_entry['clues']:
                    word_entry['clues'].append(clue)
                
                # Add date if unique
                if date not in word_entry['dates']:
                    word_entry['dates'].append(date)
        
        # Calculate frequencies and sort dates/clues
        for word, entry in self.word_database.items():
            entry['frequency'] = len(entry['dates'])
            entry['dates'].sort()  # Sort dates chronologically
            entry['clues'].sort()  # Sort clues alphabetically
        
        # Convert defaultdict to regular dict
        final_database = dict(self.word_database)
        
        logger.info(f"Created database with {len(final_database)} unique words")
        return final_database
    
    
    def get_statistics(self, word_database: Dict) -> Dict:
        """Get statistics about the word database."""
        if not word_database:
            return {}
        
        total_words = len(word_database)
        total_appearances = sum(entry['frequency'] for entry in word_database.values())
        total_unique_clues = sum(len(entry['clues']) for entry in word_database.values())
        
        # Length distribution
        length_distribution = defaultdict(int)
        for entry in word_database.values():
            length_distribution[entry['length']] += 1
        
        # Frequency distribution
        frequencies = [entry['frequency'] for entry in word_database.values()]
        avg_frequency = sum(frequencies) / len(frequencies) if frequencies else 0
        max_frequency = max(frequencies) if frequencies else 0
        min_frequency = min(frequencies) if frequencies else 0
        
        # Most frequent words
        most_frequent = sorted(
            word_database.items(), 
            key=lambda x: x[1]['frequency'], 
            reverse=True
        )[:10]
        
        # Words with most clues
        most_clues = sorted(
            word_database.items(),
            key=lambda x: len(x[1]['clues']),
            reverse=True
        )[:10]
        
        return {
            'total_words': total_words,
            'total_appearances': total_appearances,
            'total_unique_clues': total_unique_clues,
            'average_frequency': round(avg_frequency, 2),
            'max_frequency': max_frequency,
            'min_frequency': min_frequency,
            'length_distribution': dict(length_distribution),
            'most_frequent_words': [(word, data['frequency']) for word, data in most_frequent],
            'words_with_most_clues': [(word, len(data['clues'])) for word, data in most_clues]
        }
    
    
    def save_database(self, word_database: Dict, output_file: str):
        """Save the word database to a JSON file."""
        # Create output directory if it doesn't exist
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(word_database, f, indent=2, ensure_ascii=False)
            logger.info(f"Word database saved to {output_file}")
        except Exception as e:
            logger.error(f"Error saving database to {output_file}: {e}")
            raise
    
    
    def process_file(self, input_file: str, output_file: str = None) -> Dict:
        """
        Main processing function that reads scraped data and creates word database.
        
        Args:
            input_file: Path to the scraped data JSON file
            output_file: Path for the output word database (optional)
            
        Returns:
            The created word database
        """
        if output_file is None:
            output_file = "data/02_intermediary/word_database/word_database_full.json"
        
        # Load scraped data
        scraped_data = self.load_scraped_data(input_file)
        
        # Process the data
        word_database = self.process_scraped_data(scraped_data)
        
        # Save the database
        self.save_database(word_database, output_file)
        
        # Create filtered versions
        output_dir = os.path.dirname(output_file)
        self.create_filtered_databases(word_database, output_dir)
        
        # Print statistics
        stats = self.get_statistics(word_database)
        self.print_statistics(stats)
        
        return word_database
    
    
    def create_frequencyfiltered_databases(self, word_database: Dict, output_dir: str):
        """Create additional filtered versions of the database."""
        os.makedirs(output_dir, exist_ok=True)
        
        # 1. Words by length
        words_by_length = defaultdict(list)
        for word, data in word_database.items():
            words_by_length[data['length']].append((word, data['frequency']))
        
        # Sort by frequency within each length
        for length in words_by_length:
            words_by_length[length].sort(key=lambda x: x[1], reverse=True)
        
        length_file = os.path.join(output_dir, "words_by_length.json")
        with open(length_file, 'w', encoding='utf-8') as f:
            json.dump(dict(words_by_length), f, indent=2)
        logger.info(f"Words by length saved to {length_file}")
        
        # 2. High-frequency words only (frequency >= 2)
        high_freq_words = {
            word: data for word, data in word_database.items() 
            if data['frequency'] >= 2
        }
        
        high_freq_file = os.path.join(output_dir, "high_frequency_words.json")
        with open(high_freq_file, 'w', encoding='utf-8') as f:
            json.dump(high_freq_words, f, indent=2)
        logger.info(f"High frequency words saved to {high_freq_file}")
        
        # 3. Simple word list (just words and frequencies)
        simple_word_list = {
            word: data['frequency'] for word, data in word_database.items()
        }
        
        simple_file = os.path.join(output_dir, "simple_word_list.json")
        with open(simple_file, 'w', encoding='utf-8') as f:
            json.dump(simple_word_list, f, indent=2)
        logger.info(f"Simple word list saved to {simple_file}")
    
    
    def print_statistics(self, stats: Dict):
        """Print database statistics to console."""
        print("\n" + "="*60)
        print("WORD DATABASE STATISTICS")
        print("="*60)
        print(f"Total unique words: {stats['total_words']:,}")
        print(f"Total word appearances: {stats['total_appearances']:,}")
        print(f"Total unique clues: {stats['total_unique_clues']:,}")
        print(f"Average frequency per word: {stats['average_frequency']}")
        print(f"Max frequency: {stats['max_frequency']}")
        print(f"Min frequency: {stats['min_frequency']}")
        
        print(f"\nLength distribution:")
        for length, count in sorted(stats['length_distribution'].items()):
            print(f"  {length} letters: {count:,} words")
        
        print(f"\nMost frequent words:")
        for word, freq in stats['most_frequent_words']:
            print(f"  {word}: {freq} appearances")
        
        print(f"\nWords with most clues:")
        for word, clue_count in stats['words_with_most_clues']:
            print(f"  {word}: {clue_count} different clues")
