import os
import requests
import json
import re
import logging
from typing import Dict, List
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class CrosswordTrackerScraper:
    def __init__(self, base_url: str = "http://crosswordtracker.com"):# , delay: float = 1.0):
        self.base_url = base_url
        # self.delay = delay  # Delay between requests to be respectful
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
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
    
    def extract_words_from_browse_page(self, soup: BeautifulSoup) -> List[str]:
        """Extract word list from a browse page."""
        words = []
        
        # Find all word links in browse_box divs
        browse_boxes = soup.find_all('div', class_='browse_box')
        
        for box in browse_boxes:
            word_links = box.find_all('a', class_='answer')
            for link in word_links:
                word = link.text.strip()
                if word and word not in words:  # Avoid duplicates
                    words.append(word)
        
        return words
    
    def get_word_frequency(self, word: str) -> int:
        """Get the frequency count for a specific word."""
        # Skip words with special characters that cause 404s
        if any(char in word for char in ['*', '?', '/', '\\', '<', '>', ':', '"', '|']):
            logger.debug(f"Skipping word with special characters: {word}")
            return 0
        
        word_url = f"{self.base_url}/answer/{word.lower()}/"
        soup = self.get_page(word_url)
        
        if not soup:
            return 0
        
        # Look for the frequency information
        # Pattern: "spotted over X times" or "spotted X times"
        frequency_text = soup.get_text()
        
        # Try different patterns
        patterns = [
            r'we have spotted (\d+) time[s]?\.',  # "we have spotted 1 time." or "we have spotted 7 times."
            r'spotted (\d+) time[s]?\.',          # "spotted 1 time." or "spotted 7 times."
            r'spotted over (\d+) time[s]?\.',     # "spotted over 20 times."
            r'we have spotted over (\d+) time[s]?\.',  # "we have spotted over 20 times."
            r'answer that we have spotted (\d+) time[s]?\.',  # Full phrase match
            r'answer that we have spotted over (\d+) time[s]?\.'  # Full phrase with "over"
        ]
        
        for pattern in patterns:
            match = re.search(pattern, frequency_text, re.IGNORECASE)
            if match:
                frequency = int(match.group(1))
                logger.debug(f"Found frequency for {word}: {frequency}")
                return frequency
        
        # If no pattern matches, try to find any number followed by "time"
        fallback_match = re.search(r'(\d+)\s+time[s]?', frequency_text, re.IGNORECASE)
        if fallback_match:
            frequency = int(fallback_match.group(1))
            logger.debug(f"Found frequency (fallback) for {word}: {frequency}")
            return frequency
        
        # If still no match, log the actual text for debugging
        logger.warning(f"Could not find frequency for word: {word}")
        logger.debug(f"Page text snippet: {frequency_text[:200]}...")
        return 0
    
    def get_max_pages_for_letter(self, letter: str) -> int:
        """Determine the maximum number of pages for a given letter."""
        first_page_url = f"{self.base_url}/browse/answers-starting-with-{letter.lower()}/"
        soup = self.get_page(first_page_url)
        
        if not soup:
            return 1
        
        # Find pagination info
        paginator_divs = soup.find_all('div', class_='paginator')
        max_page = 1
        
        for div in paginator_divs:
            if div.find('a'):
                link = div.find('a')
                if link and 'page=' in link.get('href', ''):
                    try:
                        page_num = int(re.search(r'page=(\d+)', link.get('href')).group(1))
                        max_page = max(max_page, page_num)
                    except (AttributeError, ValueError):
                        continue
        
        logger.info(f"Letter {letter}: Found {max_page} pages")
        return max_page
    
    def scrape_letter(self, letter: str, get_frequency=True) -> Dict[str, int]:
        """Scrape all words and their frequencies for a given letter."""
        logger.info(f"Starting to scrape letter: {letter}")
        
        words_data = {}
        max_pages = self.get_max_pages_for_letter(letter)
        
        for page in range(1, max_pages + 1):
            logger.info(f"Processing {letter} - Page {page}/{max_pages}")
            
            page_url = f"{self.base_url}/browse/answers-starting-with-{letter.lower()}/?page={page}"
            soup = self.get_page(page_url)
            
            if not soup:
                continue
            
            words = self.extract_words_from_browse_page(soup)
            logger.info(f"Found {len(words)} words on page {page}")
            
            # Process words with progress tracking
            for i, word in enumerate(words, 1):
                if word not in words_data:  # Skip if already processed
                    if get_frequency:
                        frequency = self.get_word_frequency(word)
                    else:
                        frequency = 999 # Placeholder for testing without frequency
                    
                    words_data[word] = frequency
                        
                    # Log progress every 10 words or for words with frequency > 0
                    if i % 10 == 0 or frequency > 0:
                        logger.info(f"  Progress: {i}/{len(words)} - {word}: {frequency}")
                    else:
                        logger.debug(f"Word: {word}, Frequency: {frequency}")
            
            # Summary for the page
            page_words_with_freq = sum(1 for freq in words_data.values() if freq > 0)
            logger.info(f"Page {page} complete. Total words so far: {len(words_data)}, "
                    f"with frequency > 0: {page_words_with_freq}")
        
        # Final summary
        final_words_with_freq = sum(1 for freq in words_data.values() if freq > 0)
        logger.info(f"Completed letter {letter}: {len(words_data)} total words, "
                f"{final_words_with_freq} with frequency > 0")
        
        return words_data
    
    def scrape_all_letters(self, letters: List[str] = None) -> Dict[str, Dict[str, int]]:
        """Scrape all letters or a subset."""
        if letters is None:
            letters = [chr(i) for i in range(ord('A'), ord('Z') + 1)]
        
        all_data = {}
        
        for letter in letters:
            try:
                letter_data = self.scrape_letter(letter)
                all_data[letter] = letter_data
                
                # Save intermediate results
                self.save_data(all_data, f"crossword_words_partial_{letter}.json")
                
            except Exception as e:
                logger.error(f"Error processing letter {letter}: {e}")
                continue
        
        return all_data
    
    def save_data(self, data: Dict, filename: str):
        """Save data to JSON file."""
        os.makedirs("data/01_raw/crossword_tracker", exist_ok=True)
        filepath = os.path.join("data/01_raw/crossword_tracker", filename)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Data saved to {filepath}")
    
    def filter_words_by_frequency(self, data: Dict[str, Dict[str, int]], min_frequency: int = 1) -> Dict[str, Dict[str, int]]:
        """Filter words by minimum frequency."""
        filtered_data = {}
        
        for letter, words in data.items():
            filtered_words = {word: freq for word, freq in words.items() if freq >= min_frequency}
            if filtered_words:
                filtered_data[letter] = filtered_words
        
        return filtered_data

def main():
    """Main function to run the scraper."""
    # scraper = CrosswordTrackerScraper(delay=1.5)  # 1.5 second delay between requests
    scraper = CrosswordTrackerScraper()
    
    # Test with a single letter first
    test_letter = 'A'
    logger.info(f"Testing with letter: {test_letter}")
    
    # Scrape just letter A for testing
    letter_data = scraper.scrape_letter(test_letter)
    
    # Save test results
    scraper.save_data({test_letter: letter_data}, f"crossword_words_{test_letter}.json")
    
    # Print some statistics
    total_words = len(letter_data)
    high_freq_words = {word: freq for word, freq in letter_data.items() if freq >= 10}
    
    print(f"\n=== Results for letter {test_letter} ===")
    print(f"Total words: {total_words}")
    print(f"High frequency words (≥10): {len(high_freq_words)}")
    print(f"\nTop 10 most frequent words:")
    
    sorted_words = sorted(letter_data.items(), key=lambda x: x[1], reverse=True)[:10]
    for word, freq in sorted_words:
        print(f"  {word}: {freq}")

def scrape_specific_letters(letters: List[str]):
    """Scrape specific letters."""
    # scraper = CrosswordTrackerScraper(delay=1.5)
    scraper = CrosswordTrackerScraper()
    
    for letter in letters:
        logger.info(f"Scraping letter: {letter}")
        letter_data = scraper.scrape_letter(letter)
        scraper.save_data({letter: letter_data}, f"crossword_words_{letter}.json")

def scrape_all_letters_full():
    """Scrape all letters A-Z."""
    # scraper = CrosswordTrackerScraper(delay=2.0)  # Longer delay for full scrape
    scraper = CrosswordTrackerScraper()
    
    all_data = scraper.scrape_all_letters()
    
    # Save complete data
    scraper.save_data(all_data, "crossword_words_complete.json")
    
    # Save filtered version (frequency >= 5)
    filtered_data = scraper.filter_words_by_frequency(all_data, min_frequency=5)
    scraper.save_data(filtered_data, "crossword_words_filtered.json")
    
    # Print summary statistics
    total_words = sum(len(words) for words in all_data.values())
    filtered_words = sum(len(words) for words in filtered_data.values())
    
    print(f"\n=== Summary ===")
    print(f"Total words scraped: {total_words}")
    print(f"Words with frequency ≥ 5: {filtered_words}")

if __name__ == "__main__":
    main()