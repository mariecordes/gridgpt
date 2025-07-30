import os
import json
import glob
import sys

INPUT_DIR = "data/01_raw/example_grids"
OUTPUT_FILE = "data/02_intermediary/example_grids.json"

# Add the project root to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.gridgpt.extract_examples import process_crossword_file

def extract_all_examples():
    """Extract all HTML files and combine into single JSON."""
    
    # Find all HTML files
    html_files = glob.glob(os.path.join(INPUT_DIR, "*.html"))

    if not html_files:
        print(f"No HTML files found in {INPUT_DIR}")
        return
    
    combined_data = {}
    
    for file_path in html_files:
        # Get filename without extension for the key
        filename = os.path.splitext(os.path.basename(file_path))[0]
        
        try:
            print(f"Processing {filename}...")
            # Extract data in JSON format (not formatted string)
            result = process_crossword_file(file_path, return_formatted_output=False)
            combined_data[filename] = result
            print(f"✓ Successfully processed {filename}")
            
        except Exception as e:
            print(f"✗ Error processing {filename}: {e}")
            combined_data[filename] = {"error": str(e)}
    
    # Save combined data to JSON file
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(combined_data, f, indent=2, ensure_ascii=False)
    
    print(f"\n✓ Combined data saved to {OUTPUT_FILE}")
    print(f"Processed {len(combined_data)} files")
    
    # Print summary
    successful = sum(1 for v in combined_data.values() if "error" not in v)
    failed = len(combined_data) - successful
    print(f"Successful: {successful}, Failed: {failed}")

if __name__ == "__main__":
    extract_all_examples()