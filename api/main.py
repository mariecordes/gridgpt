from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os
import sys

# Ensure root in path for util import BEFORE other imports that log
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.append(ROOT_DIR)

from src.gridgpt.utils import init_logging  # type: ignore

# Initialize logging (append mode) before importing router
init_logging(overwrite=False)

from .routes import router

app = FastAPI(
    title="GridGPT API",
    description="AI-powered crossword generator backend",
    version="1.0.0"
)

ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "https://gridgpt.vercel.app",
]

# Add CORS middleware to allow frontend to connect
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # allow everything
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(router, prefix="/api")

@app.get("/")
async def root():
    return {"message": "GridGPT API is running"}

@app.get("/health")
async def health_check():
    return {"status": "healthy"}