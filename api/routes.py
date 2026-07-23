from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, List, Any
import sys
import os

# Add the project root to the path so we can import our modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.gridgpt.crossword_builder import CrosswordBuilder
from src.gridgpt.template_manager import load_templates

router = APIRouter()

# One builder per process. It owns the shared word database and the generation
# pipeline, so this module only deals with HTTP.
builder = CrosswordBuilder()

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

@router.get("/templates")
async def get_templates():
    """Get all available crossword templates."""
    try:
        templates_data = load_templates()
        return {"templates": templates_data["templates"]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load templates: {str(e)}")

@router.post("/generate-crossword")
async def generate_crossword(request: GenerateRequest):
    """Generate a themed crossword puzzle."""
    try:
        built = builder.build(
            template_id=request.template,
            theme=request.theme,
            clue_type=request.clueType,
        )

        # Return friendly error if generation fails
        if built is None:
            raise HTTPException(
                status_code=503,
                detail="Could not build a puzzle for this theme. Please try again.",
            )

        template, crossword = built
        return {
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

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate crossword: {str(e)}")
