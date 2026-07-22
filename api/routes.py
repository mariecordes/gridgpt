from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, List, Any
import sys
import os

# Add the project root to the path so we can import our modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.gridgpt.crossword_generator import CrosswordGenerator, generate_themed_crossword
from src.gridgpt.theme_manager import generate_theme_entry, ThemeManager
from src.gridgpt.theme_anchor import ThemeAnchorSelector
from src.gridgpt.template_manager import select_template, load_templates
from src.gridgpt.clue_manager import retrieve_existing_clues, generate_clues
from src.gridgpt.utils import load_parameters
from src.gridgpt.word_database_manager import WordDatabaseManager

router = APIRouter()
params = load_parameters()

# Create a shared WordDatabaseManager instance to reuse across requests
# This avoids reloading the database for every request
word_db_manager = WordDatabaseManager()

# Pydantic models for request/response
class GenerateRequest(BaseModel):
    template: Optional[str] = None
    theme: Optional[str] = None
    themeEntry: Optional[str] = None
    difficulty: Optional[str] = "easy"
    clueType: Optional[str] = 'existing'

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

# @router.post("/validate-theme-entry")
# async def validate_theme_entry(theme_entry: str):
#     """Validate a theme entry."""
#     try:
#         generator = CrosswordGenerator()
#         is_valid, message = generator.validate_theme_entry(theme_entry)
        
#         return ValidationResponse(valid=is_valid, message=message)
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=f"Validation error: {str(e)}")

@router.post("/generate-crossword")
async def generate_crossword(request: GenerateRequest):
    """Generate a themed crossword puzzle."""
    try:
        # XXX: in case template choice should become optional
        # # Select template
        # if request.template:
        #     template = select_template(template_id=request.template)
        # elif request.difficulty:
        #     template = select_template(difficulty=request.difficulty)
        # else:
        #     template = select_template()  # Random template
        
        # Select template
        template = select_template(template_id=request.template)
        
        # Manage theme and theme anchors
        theme_similarities = None
        theme_entries = None
        if request.theme:
            theme = request.theme
            anchor_cfg = params["theme_anchors"]

            # One ThemeManager (shared theme embedding, single API call): score
            # every word for the fill weighting, and pull a candidate pool for the
            # anchor selector.
            theme_manager = ThemeManager(theme, word_db_manager)
            theme_similarities = theme_manager.score_all_words()
            candidates = theme_manager.get_anchor_candidates(
                pool_size=anchor_cfg["candidate_pool"],
                min_chars=anchor_cfg["min_chars"],
                max_chars=anchor_cfg["max_chars"],
            )
            # An LLM vets the candidates into a few genuinely on-theme anchor words
            # (falls back to cosine order when no LLM is available).
            theme_entries = ThemeAnchorSelector().select_anchors(
                theme, candidates, word_db_manager,
                max_words=anchor_cfg["vetted_pool"],
                allow_llm_words=anchor_cfg["allow_llm_words"],
                min_zipf=anchor_cfg["min_zipf"],
                min_chars=anchor_cfg["min_chars"],
                max_chars=anchor_cfg["max_chars"],
            )
        
        else:
            # No theme: None flows through to clue generation, where the prompt
            # is told to ignore a None theme and write theme-agnostic clues.
            theme = None

        # # Validate theme entry if provided
        # if request.themeEntry:
        #     generator = CrosswordGenerator()
        #     is_valid, message = generator.validate_theme_entry(request.themeEntry)
        #     if not is_valid:
        #         raise HTTPException(status_code=400, detail=f"Invalid theme entry: {message}")
        
        # Generate crossword: theme_entries pins on-theme anchors (best-effort),
        # theme_similarities biases the rest of the fill toward on-theme words.
        crossword = generate_themed_crossword(
            template,
            node_budget=params["crossword_generator"]["node_budget"],
            restart_count=params["crossword_generator"]["restart_count"],
            theme_similarities=theme_similarities,
            theme_boost=params["theme_fill"]["boost"],
            sim_low=params["theme_fill"]["sim_low"],
            sim_high=params["theme_fill"]["sim_high"],
            visible_threshold=params["theme_fill"]["visible_threshold"],
            word_db_manager=word_db_manager,
            theme_entries=theme_entries,
            max_anchors=params["theme_anchors"]["max_anchors"],
            anchor_attempts=params["theme_anchors"]["anchor_attempts"],
        )

        # Return friendly error if generation fails
        if crossword is None:
            raise HTTPException(
                status_code=503,
                detail="Could not build a puzzle for this theme. Please try again.",
            )

        # Generate clues based on clue type
        if request.clueType == "generate":
            clues = generate_clues(crossword, theme, word_db_manager)
        else:
            clues = retrieve_existing_clues(crossword, word_db_manager)
        
        # Ensure clues are added to the crossword response
        crossword["clues"] = clues
        
        # Create response with template info
        response_data = {
            "grid": crossword["grid"],
            "filled_slots": crossword["filled_slots"],
            "clues": crossword["clues"],
            "seed_entries": crossword.get("seed_entries", {}),
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
        template = select_template(template_id='5x5_blocked_corners')
        generator = CrosswordGenerator(word_db_manager)
        
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
