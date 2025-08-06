#!/usr/bin/env python3
"""
Script to scrape NYT Mini crossword clues and answers from WordDB.com

Usage:
    python scripts/scrape_worddb.py --start-date 2023-01-01 --end-date 2023-12-31
    python scripts/scrape_worddb.py --start-date 2024-01-01 --end-date 2024-01-31 --output custom_output.json
"""

import argparse
import sys
import os
from datetime import datetime, timedelta

# Add the src directory to the path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from scraper.worddb import WordDBScraper


def parse_date(date_string):
    """Parse and validate date string."""
    try:
        return datetime.strptime(date_string, '%Y-%m-%d').strftime('%Y-%m-%d')
    except ValueError:
        raise argparse.ArgumentTypeError(f"Invalid date format: {date_string}. Use YYYY-MM-DD")


def main():
    parser = argparse.ArgumentParser(
        description="Scrape NYT Mini crossword clues and answers from WordDB.com",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Scrape the last 30 days
  python scripts/scrape_worddb.py --start-date 2024-07-01 --end-date 2024-07-31
  
  # Scrape a specific year
  python scripts/scrape_worddb.py --start-date 2023-01-01 --end-date 2023-12-31
        """
    )
    
    parser.add_argument(
        '--start-date',
        type=parse_date,
        required=True,
        help='Start date in YYYY-MM-DD format'
    )
    
    parser.add_argument(
        '--end-date',
        type=parse_date,
        required=True,
        help='End date in YYYY-MM-DD format'
    )
        
    args = parser.parse_args()
    
    # Validate date range
    start = datetime.strptime(args.start_date, '%Y-%m-%d')
    end = datetime.strptime(args.end_date, '%Y-%m-%d')
    
    if start > end:
        print("Error: Start date must be before or equal to end date")
        sys.exit(1)
    
    if end > datetime.now():
        print("Warning: End date is in the future")
    
    # Calculate number of days
    days = (end - start).days + 1
    print(f"Scraping {days} days from {args.start_date} to {args.end_date}")
    
    # Initialize scraper
    scraper = WordDBScraper()

    # Run scraper
    try:
        data = scraper.scrape_date_range(
            start_date=args.start_date,
            end_date=args.end_date
        )
        
        # Print statistics
        stats = scraper.get_statistics(data)
        print("\n" + "="*50)
        print("SCRAPING COMPLETED!")
        print("="*50)
        print(f"Total dates processed: {stats['total_dates']}")
        print(f"Successful dates: {stats['successful_dates']}")
        print(f"Failed dates: {stats['failed_dates']}")
        print(f"Total clue-answer pairs: {stats['total_clue_answer_pairs']}")
        print(f"Unique answers: {stats['unique_answers']}")
        print(f"Unique clues: {stats['unique_clues']}")
        print(f"Average clues per date: {stats['average_clues_per_date']:.1f}")
        
    except KeyboardInterrupt:
        print("\nScraping interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"Error during scraping: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
