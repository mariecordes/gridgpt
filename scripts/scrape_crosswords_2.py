import sys
import os

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.gridgpt.crossword_scraper import scrape_specific_letters, scrape_all_letters_full

def main():
    """Command line interface for scraping."""
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python scripts/scrape_crosswords.py test          # Test with letter A")
        print("  python scripts/scrape_crosswords.py letters A B C  # Scrape specific letters")
        print("  python scripts/scrape_crosswords.py all           # Scrape all letters A-Z")
        return
    
    mode = sys.argv[1].lower()
    
    if mode == "test":
        from src.gridgpt.crossword_scraper import main
        main()
    
    elif mode == "letters":
        if len(sys.argv) < 3:
            print("Please specify letters to scrape: python scripts/scrape_crosswords.py letters A B C")
            return
        letters = [letter.upper() for letter in sys.argv[2:]]
        scrape_specific_letters(letters)
    
    elif mode == "all":
        print("Warning: This will scrape all letters A-Z and may take several hours.")
        response = input("Continue? (y/N): ")
        if response.lower() == 'y':
            scrape_all_letters_full()
        else:
            print("Cancelled.")
    
    else:
        print(f"Unknown mode: {mode}")

if __name__ == "__main__":
    main()