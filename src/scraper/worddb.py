import os
import requests
import json
import re
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Tuple
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class WordDBScraper:
    def __init__(self, base_url: str = "https://www.worddb.com", delay: float = 1.0):
        self.base_url = base_url
        # self.delay = delay  # Delay between requests to be respectful
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
    
    def get_page(self, url: str) -> BeautifulSoup:
        """Fetch and parse a webpage."""
        try:
            response = self.session.get(url)
            response.raise_for_status()
            # time.sleep(self.delay)  # Be respectful to the server
            return BeautifulSoup(response.content, 'html.parser')
        except requests.RequestException as e:
            logger.error(f"Error fetching {url}: {e}")
            return None
    
    def extract_clues_and_answers(self, soup: BeautifulSoup) -> Dict[str, str]:
        """Extract clue-answer pairs from a WordDB crossword page."""
        clue_answer_pairs = {}
        
        if not soup:
            return clue_answer_pairs
        
        # Find the table with crossword data
        table = soup.find('table', class_='table')
        if not table:
            logger.warning("No crossword table found on page")
            return clue_answer_pairs
        
        tbody = table.find('tbody')
        if not tbody:
            logger.warning("No tbody found in crossword table")
            return clue_answer_pairs
        
        rows = tbody.find_all('tr')
        
        for row in rows:
            try:
                # Extract clue from the second column (col-7)
                clue_cell = row.find('td', class_='col-7')
                if not clue_cell:
                    continue
                
                clue_link = clue_cell.find('a')
                if clue_link:
                    clue = clue_link.text.strip()
                else:
                    clue = clue_cell.text.strip()
                
                # Extract answer from the third column (col-3)
                answer_cell = row.find('td', class_='col-3')
                if not answer_cell:
                    continue
                
                # Answer is in a button with data-word attribute or text content
                answer_button = answer_cell.find('button', class_='word')
                if answer_button:
                    answer = answer_button.get('data-word', '').strip().upper()
                    if not answer:
                        answer = answer_button.text.strip().upper()
                else:
                    # Fallback to cell text
                    answer = answer_cell.text.strip().upper()
                
                if clue and answer:
                    clue_answer_pairs[answer] = clue
                    logger.debug(f"Found: {answer} -> {clue}")
                
            except Exception as e:
                logger.warning(f"Error processing row: {e}")
                continue
        
        return clue_answer_pairs
    
    def scrape_date(self, date: str) -> Dict[str, str]:
        """Scrape clues and answers for a specific date (YYYY-MM-DD format)."""
        url = f"{self.base_url}/crossword/answers/new_york_times_mini/{date}"
        logger.info(f"Scraping date: {date} from {url}")
        
        soup = self.get_page(url)
        if not soup:
            logger.error(f"Failed to fetch page for date: {date}")
            return {}
        
        clue_answer_pairs = self.extract_clues_and_answers(soup)
        logger.info(f"Found {len(clue_answer_pairs)} clue-answer pairs for {date}")
        
        return clue_answer_pairs
    
    def generate_date_range(self, start_date: str, end_date: str) -> List[str]:
        """Generate a list of dates between start_date and end_date (inclusive)."""
        start = datetime.strptime(start_date, '%Y-%m-%d')
        end = datetime.strptime(end_date, '%Y-%m-%d')
        
        dates = []
        current = start
        while current <= end:
            dates.append(current.strftime('%Y-%m-%d'))
            current += timedelta(days=1)
        
        return dates
    
    def scrape_date_range(self, start_date: str, end_date: str, output_file: str = None) -> Dict[str, Dict[str, str]]:
        """
        Scrape clues and answers for a range of dates.
        
        Args:
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format
            output_file: Path to JSON file to save/load progress
            
        Returns:
            Dictionary with dates as keys and clue-answer dictionaries as values
        """
        if output_file is None:
            # output_file = f"data/01_raw/worddb_com/nyt_mini_clues_{start_date}_to_{end_date}.json"
            output_file = f"data/01_raw/worddb_com/nyt_mini_clues.json"
        
        # Create directory if it doesn't exist
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        
        # Load existing data if file exists
        all_data = {}
        if os.path.exists(output_file):
            try:
                with open(output_file, 'r', encoding='utf-8') as f:
                    all_data = json.load(f)
                logger.info(f"Loaded existing data from {output_file} with {len(all_data)} dates")
            except Exception as e:
                logger.warning(f"Could not load existing file {output_file}: {e}")
        
        dates = self.generate_date_range(start_date, end_date)
        logger.info(f"Scraping {len(dates)} dates from {start_date} to {end_date}")
        
        save_counter = 0
        save_interval = 50  # Save progress every 50 pages
        
        for i, date in enumerate(dates, 1):
            # Skip if already scraped
            if date in all_data and all_data[date]:
                logger.info(f"Skipping {date} - already scraped ({i}/{len(dates)})")
                continue
            
            logger.info(f"Processing {date} ({i}/{len(dates)})")
            
            try:
                clue_answer_pairs = self.scrape_date(date)
                all_data[date] = clue_answer_pairs
                save_counter += 1
                
                # Save progress every save_interval pages
                if save_counter >= save_interval or i == len(dates):
                    self.save_data(all_data, output_file)
                    logger.info(f"Saved progress to {output_file} (processed {i}/{len(dates)} dates)")
                    save_counter = 0
                    
            except Exception as e:
                logger.error(f"Error processing date {date}: {e}")
                all_data[date] = {}  # Mark as attempted but failed
                continue
        
        # Final save
        self.save_data(all_data, output_file)
        logger.info(f"Completed scraping. Total dates processed: {len(all_data)}")
        
        return all_data
    
    def save_data(self, data: Dict[str, Dict[str, str]], output_file: str):
        """Save data to JSON file."""
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            logger.debug(f"Data saved to {output_file}")
        except Exception as e:
            logger.error(f"Error saving data to {output_file}: {e}")
    
    def get_statistics(self, data: Dict[str, Dict[str, str]]) -> Dict:
        """Get statistics about the scraped data."""
        total_dates = len(data)
        successful_dates = len([d for d in data.values() if d])
        total_clues = sum(len(d) for d in data.values())
        
        # Get unique answers and clues
        all_answers = set()
        all_clues = set()
        
        for date_data in data.values():
            all_answers.update(date_data.keys())
            all_clues.update(date_data.values())
        
        return {
            'total_dates': total_dates,
            'successful_dates': successful_dates,
            'failed_dates': total_dates - successful_dates,
            'total_clue_answer_pairs': total_clues,
            'unique_answers': len(all_answers),
            'unique_clues': len(all_clues),
            'average_clues_per_date': total_clues / max(successful_dates, 1)
        }


def main():
    """Example usage of the WordDB scraper."""
    scraper = WordDBScraper(delay=1.0)
    
    # Example: scrape the last 30 days
    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
    
    logger.info(f"Starting WordDB scrape from {start_date} to {end_date}")
    
    data = scraper.scrape_date_range(start_date, end_date)
    stats = scraper.get_statistics(data)
    
    logger.info("Scraping completed!")
    logger.info(f"Statistics: {stats}")


if __name__ == "__main__":
    main()
