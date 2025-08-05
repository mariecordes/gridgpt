import sys
import os
import argparse

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.gridgpt.word_database import combine_and_filter_words, save_word_database_formats

INPUT_DIR = "data/01_raw/crossword_tracker"
OUTPUT_DIR = "data/02_intermediary/word_database"
OUTPUT_FILE_ALL = os.path.join(OUTPUT_DIR, "word_database_all.json")
OUTPUT_FILE_ADDITIONAL = f"{OUTPUT_DIR}/word_database_filtered"

def main():
    """Command line interface for creating word database."""
    parser = argparse.ArgumentParser(
        description="Create a filtered crossword word database from individual letter files",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    
    parser.add_argument(
        '--min-frequency',
        type=int,
        default=5,
        help='Minimum frequency threshold for words'
    )
    
    parser.add_argument(
        '--min-length',
        type=int,
        default=3,
        help='Minimum word length (characters)'
    )
    
    parser.add_argument(
        '--max-length',
        type=int,
        default=15,
        help='Maximum word length (characters)'
    )
    
    args = parser.parse_args()
    
    # Show configuration
    print("=== Word Database Creation Configuration ===")
    print(f"Input directory: {INPUT_DIR}")
    print(f"Output directory: {OUTPUT_DIR}")
    print(f"Min frequency: {args.min_frequency}")
    print(f"Length range: {args.min_length}-{args.max_length} characters")
    print()
    
    # Create the combined word database
    words = combine_and_filter_words(
        input_dir=INPUT_DIR,
        output_file=OUTPUT_FILE_ALL,
        min_frequency=args.min_frequency,
        min_length=args.min_length,
        max_length=args.max_length,
        exclude_special_chars=True
    )
    
    # Save the word database in multiple formats
    file_paths = save_word_database_formats(words, OUTPUT_FILE_ADDITIONAL)
    
    print(f"\n=== Files Created ===")
    for format_name, path in file_paths.items():
        print(f"{format_name}: {path}")
    
    print(f"\n✅ Word database creation complete!")
    print(f"Total words in database: {len(words)}")

if __name__ == "__main__":
    main()