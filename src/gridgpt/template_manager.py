import json
import random
from typing import Dict, List

def load_templates(template_file: str = "data/03_templates/grid_templates.json") -> Dict:
    """Load crossword templates from JSON file."""
    with open(template_file, 'r', encoding='utf-8') as f:
        return json.load(f)

def select_template(template_id: str = None, difficulty: str = None) -> Dict:
    """
    Select a template structure from examples.
    
    Args:
        template_id: Specific template ID to select
        difficulty: Filter by difficulty level ('easy', 'medium', 'hard')
    
    Returns:
        Template dictionary with grid structure and slot information
    """
    templates_data = load_templates()
    templates = templates_data["templates"]
    
    # Filter by difficulty if specified
    if difficulty:
        templates = [t for t in templates if t.get("difficulty") == difficulty]
    
    # Select specific template or random
    if template_id:
        template = next((t for t in templates if t["id"] == template_id), None)
        if not template:
            raise ValueError(f"Template '{template_id}' not found")
    else:
        template = random.choice(templates)
    
    print(f"Selected template: {template['name']} ({template['id']})")
    print(f"Description: {template['description']}")
    
    return template

def identify_theme_slots(template: Dict) -> List[Dict]:
    """
    Identify theme slots from template.
    
    Args:
        template: Template dictionary
        
    Returns:
        List of slot dictionaries designated for theme entries
    """
    theme_slot_ids = template.get("theme_slots", [])
    all_slots = template["slots"]
    
    theme_slots = [slot for slot in all_slots if slot["id"] in theme_slot_ids]
    
    print(f"Theme slots identified: {[slot['id'] for slot in theme_slots]}")
    
    return theme_slots

def print_template_grid(template: Dict):
    """Print a visual representation of the template grid."""
    grid = template["grid"]
    print(f"\nTemplate: {template['name']}")
    print("=" * (len(grid[0]) * 2 + 1))
    
    for row in grid:
        print("|" + "|".join(f"{cell:1}" for cell in row) + "|")
    
    print("=" * (len(grid[0]) * 2 + 1))
    print(f"Theme slots: {', '.join(template.get('theme_slots', []))}")

# Usage example
if __name__ == "__main__":
    # Test the template system
    template = select_template(difficulty="easy")
    print_template_grid(template)
    
    theme_slots = identify_theme_slots(template)
    for slot in theme_slots:
        print(f"Theme slot {slot['id']}: {slot['length']} letters, {slot['direction']}")