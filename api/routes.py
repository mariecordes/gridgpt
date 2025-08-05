from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, List, Any
import sys
import os

# Add the project root to the path so we can import our modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.gridgpt.crossword_generator import CrosswordGenerator, generate_themed_crossword
from src.gridgpt.template_manager import select_template, load_templates
from src.gridgpt.clue_generator import generate_mixed_clues

router = APIRouter()

# Pydantic models for request/response
class GenerateRequest(BaseModel):
    template: Optional[str] = None
    theme: Optional[str] = "general knowledge"
    themeEntry: Optional[str] = None
    difficulty: Optional[str] = "easy"

class CrosswordResponse(BaseModel):
    grid: List[List[str]]
    filled_slots: Dict[str, str]
    clues: Dict[str, str]
    theme_entries: Dict[str, str]
    slots: List[Dict[str, Any]]
    template_info: Dict[str, Any]

class ValidationResponse(BaseModel):
    valid: bool
    message: str

class CheckSolutionRequest(BaseModel):
    puzzle: Dict[str, Any]
    user_solution: Dict[str, str]

class CheckSolutionResponse(BaseModel):
    correct: bool
    errors: List[str]
    score: int
    total: int

@router.get("/templates")
async def get_templates():
    """Get all available crossword templates."""
    try:
        templates_data = load_templates()
        return {"templates": templates_data["templates"]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load templates: {str(e)}")

@router.post("/validate-theme-entry")
async def validate_theme_entry(theme_entry: str):
    """Validate a theme entry."""
    try:
        generator = CrosswordGenerator()
        is_valid, message = generator.validate_theme_entry(theme_entry)
        
        return ValidationResponse(valid=is_valid, message=message)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Validation error: {str(e)}")

@router.post("/generate-crossword")
async def generate_crossword(request: GenerateRequest):
    """Generate a themed crossword puzzle."""
    try:
        # Select template
        if request.template:
            template = select_template(template_id=request.template)
        elif request.difficulty:
            template = select_template(difficulty=request.difficulty)
        else:
            template = select_template()  # Random template
        
        # Validate theme entry if provided
        if request.themeEntry:
            generator = CrosswordGenerator()
            is_valid, message = generator.validate_theme_entry(request.themeEntry)
            if not is_valid:
                raise HTTPException(status_code=400, detail=f"Invalid theme entry: {message}")
        
        # Generate crossword
        crossword = generate_themed_crossword(template, request.themeEntry)
        
        # Generate clues
        # XXX: This is a placeholder for clue generation logic to limit API usage.
        # theme = request.theme or "general knowledge"
        # clues = generate_mixed_clues(crossword, theme)
        clues = {
            '1A': 'Aloof or distant in manner',
            '1D': 'Insect or to annoy someone',
            '2D': 'A name often associated with music',
            '3D': 'Departed or went away from a place',
            '4A': 'Crafts of coffee or beer, depending on your preference',
            '4D': 'Minor injuries or bruises',
            '5D': 'Abbreviation for "short-term memory',
            '6A': 'Not suitable or appropriate',
            '7A': 'Catch or seize them',
            '8A': 'Least Squares Sum'
        }
        
        # Ensure clues are added to the crossword response
        crossword["clues"] = clues
        
        # Create response with template info
        response_data = {
            "grid": crossword["grid"],
            "filled_slots": crossword["filled_slots"],
            "clues": crossword["clues"],
            "theme_entries": crossword.get("theme_entries", {}),
            "slots": crossword.get("slots", []),
            "template_info": {
                "id": template.get("id"),
                "name": template.get("name"),
                "difficulty": template.get("difficulty"),
                "description": template.get("description")
            }
        }
        
        return response_data
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate crossword: {str(e)}")

@router.post("/check-solution")
async def check_solution(request: CheckSolutionRequest):
    """Check user's solution against the correct answers."""
    try:
        puzzle = request.puzzle
        user_solution = request.user_solution
        
        errors = []
        correct_count = 0
        total_count = len(puzzle["filled_slots"])
        
        # Check each slot
        for slot_id, correct_answer in puzzle["filled_slots"].items():
            user_answer = user_solution.get(slot_id, "").strip().upper()
            
            if user_answer == correct_answer:
                correct_count += 1
            else:
                if user_answer:
                    errors.append(f"{slot_id}: Expected '{correct_answer}', got '{user_answer}'")
                else:
                    errors.append(f"{slot_id}: No answer provided (expected '{correct_answer}')")
        
        is_correct = correct_count == total_count
        
        return CheckSolutionResponse(
            correct=is_correct,
            errors=errors,
            score=correct_count,
            total=total_count
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to check solution: {str(e)}")

@router.get("/test")
async def test_endpoint():
    """Test endpoint to verify the API is working."""
    try:
        # Test basic functionality
        template = select_template(template_id='5x5_basic')
        generator = CrosswordGenerator()
        
        return {
            "status": "success",
            "message": "API is working correctly",
            "template_loaded": template["name"] if template else None,
            "generator_initialized": generator is not None
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"API test failed: {str(e)}"
        }
