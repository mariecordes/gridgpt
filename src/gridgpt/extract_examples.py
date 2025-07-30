from bs4 import BeautifulSoup
import re

def extract_crossword_data(html_content):
    """
    Extract grid and clues from crossword HTML content.
    
    Args:
        html_content (str): HTML content of the crossword page
        
    Returns:
        dict: Dictionary containing 'across_grid', 'down_grid', 'across_clues', and 'down_clues'
    """
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Extract grid
    across_grid = extract_grid(soup)
    
    # Create down_grid by transposing the across_grid
    down_grid = []
    if across_grid:
        num_cols = len(across_grid[0]) if across_grid else 0
        for col in range(num_cols):
            down_column = []
            for row in range(len(across_grid)):
                down_column.append(across_grid[row][col])
            down_grid.append(down_column)
    
    # Extract clues
    across_clues, down_clues = extract_clues(soup)
    
    return {
        'across_grid': across_grid,
        'down_grid': down_grid,
        'across_clues': across_clues,
        'down_clues': down_clues
    }

def extract_grid(soup):
    """
    Extract the crossword grid from the SVG elements.
    
    Args:
        soup: BeautifulSoup object
        
    Returns:
        list: 2D list representing the crossword grid
    """
    # Find all cell groups
    cell_groups = soup.find_all('g', {'class': 'xwd__cell'})
    
    # Dictionary to store cell positions and values
    cells = {}
    
    for cell_group in cell_groups:
        rect = cell_group.find('rect')
        if not rect:
            continue
            
        # Get position from rect attributes
        x = float(rect.get('x', 0))
        y = float(rect.get('y', 0))
        
        # Convert position to grid coordinates (assuming 100px cell size)
        col = int(x // 100)
        row = int(y // 100)
        
        # Check if it's a blocked cell
        if 'xwd__cell--block' in rect.get('class', []):
            cells[(row, col)] = '#'
        else:
            # Find the text content
            text_elements = cell_group.find_all('text')
            letter = ''
            for text_elem in text_elements:
                # Look for the letter (larger font size)
                if text_elem.get('font-size') == '66.67':
                    hidden_text = text_elem.find('text', {'class': 'xwd__cell--hidden'})
                    if hidden_text and hidden_text.text.strip():
                        letter = hidden_text.text.strip()
                        break
            cells[(row, col)] = letter if letter else ' '
    
    # Determine grid size
    if not cells:
        return []
        
    max_row = max(pos[0] for pos in cells.keys())
    max_col = max(pos[1] for pos in cells.keys())
    
    # Create 2D grid
    grid = []
    for row in range(max_row + 1):
        grid_row = []
        for col in range(max_col + 1):
            grid_row.append(cells.get((row, col), ' '))
        grid.append(grid_row)
    
    return grid

def extract_clues(soup):
    """
    Extract across and down clues from the HTML.
    
    Args:
        soup: BeautifulSoup object
        
    Returns:
        tuple: (across_clues, down_clues) - dictionaries mapping clue numbers to clue text
    """
    across_clues = {}
    down_clues = {}
    
    # Find clue list sections
    clue_sections = soup.find_all('div', {'class': 'xwd__clue-list--wrapper'})
    
    for section in clue_sections:
        # Determine if this is Across or Down
        title = section.find('h3', {'class': 'xwd__clue-list--title'})
        if not title:
            continue
            
        is_across = 'Across' in title.text
        is_down = 'Down' in title.text
        
        if not (is_across or is_down):
            continue
            
        # Find all clue items
        clue_items = section.find_all('li', {'class': 'xwd__clue--li'})
        
        for item in clue_items:
            # Extract clue number
            label_elem = item.find('span', {'class': 'xwd__clue--label'})
            if not label_elem:
                continue
                
            clue_number = label_elem.text.strip()
            
            # Extract clue text
            text_elem = item.find('span', {'class': 'xwd__clue--text'})
            if not text_elem:
                continue
                
            clue_text = text_elem.text.strip()
            
            # Store in appropriate dictionary
            if is_across:
                across_clues[f"{clue_number}A"] = clue_text
            elif is_down:
                down_clues[f"{clue_number}D"] = clue_text
    
    return across_clues, down_clues

def format_output(crossword_data):
    """
    Format the extracted crossword data for display.
    
    Args:
        crossword_data (dict): Dictionary containing grids and clues
        
    Returns:
        str: Formatted string representation
    """
    output = []
    
    # Format across grid
    output.append("[Across Grid]")
    for row in crossword_data['across_grid']:
        formatted_row = "[" + ", ".join(cell if cell.strip() else ' ' for cell in row) + "]"
        output.append(formatted_row)
    
    output.append("")
    
    # Format down grid
    output.append("[Down Grid]")
    for col in crossword_data['down_grid']:
        formatted_col = "[" + ", ".join(cell if cell.strip() else ' ' for cell in col) + "]"
        output.append(formatted_col)
    
    output.append("")
    
    # Format across clues
    output.append("[Across]")
    for clue_num, clue_text in sorted(crossword_data['across_clues'].items()):
        output.append(f"{clue_num}: {clue_text}")
    
    output.append("")
    
    # Format down clues
    output.append("[Down]")
    for clue_num, clue_text in sorted(crossword_data['down_clues'].items()):
        output.append(f"{clue_num}: {clue_text}")
    
    return "\n".join(output)


# Example usage
def process_crossword_file(file_path, return_formatted_output=True):
    """
    Process a crossword HTML file and return formatted output.
    
    Args:
        file_path (str): Path to the HTML file
        
    Returns:
        str: Formatted crossword data
    """
    with open(file_path, 'r', encoding='utf-8') as file:
        html_content = file.read()
    
    crossword_data = extract_crossword_data(html_content)
    
    if return_formatted_output == True:
        crossword_data = format_output(crossword_data)
        
    return crossword_data

# Test with your example file
if __name__ == "__main__":
    # Replace with your actual file path
    file_path = "/Users/Marie_Cordes/code/mariecordes/gridgpt/data/01_raw/example_grids/example_1.html"
    
    try:
        result = process_crossword_file(file_path)
        print(result)
    except FileNotFoundError:
        print("File not found. Please check the path.")
    except Exception as e:
        print(f"Error processing file: {e}")