import sys
import os

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from word_database.worddb import WordDBProcessor
from gridgpt.utils import load_catalog


def main():
    """
    This script processes scraped NYT Mini crossword data from WordDB.com
    and creates a comprehensive word database for crossword generation.

    Usage:
        python scripts/create_worddb_database.py
        python scripts/create_worddb_database.py --input custom_input.json --output custom_output.json

    Output Files Created:
    - word_database.json: Complete word database with all details
    - words_by_length.json: Words organized by length with frequencies
    - high_frequency_words.json: Only words that appear 2+ times
    - simple_word_list.json: Simple word -> frequency mapping
    """
    
    catalog = load_catalog()

    input_file_path = catalog['scraped_data']['worddb_com']['file_path']
    output_file_path = catalog['word_database']['full']['file_path']

    # Check if input file exists
    if not os.path.exists(input_file_path):
        print(f"Error: Input file not found: {input_file_path}")
        print(f"Make sure to run the WordDB scraper first:")
        print(f"  python scripts/scrape_worddb.py --start-date YYYY-MM-DD --end-date YYYY-MM-DD")
        return 1
    
    # Show file info
    input_size = os.path.getsize(input_file_path) / 1024 / 1024  # MB
    print(f"Input file: {input_file_path} ({input_size:.1f} MB)")
    print(f"Output file: {output_file_path}")

    # Process the data
    processor = WordDBProcessor()
    try:
        print("\nProcessing scraped data...")
        word_database = processor.process_file(input_file_path, output_file_path)
        
        print(f"\n{'='*60}")
        print("PROCESSING COMPLETED SUCCESSFULLY!")
        print(f"{'='*60}")
        print(f"Main database: {output_file_path}")
        
        return 0
        
    except KeyboardInterrupt:
        print("\nProcessing interrupted by user")
        return 1
    except Exception as e:
        print(f"Error processing data: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
