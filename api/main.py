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

DEFAULT_ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "https://gridgpt.vercel.app",
]

extra_origins = os.getenv("EXTRA_CORS_ORIGINS", "")
if extra_origins:
    DEFAULT_ALLOWED_ORIGINS.extend([o.strip() for o in extra_origins.split(",") if o.strip()])

allow_all = os.getenv("ALLOW_ALL_CORS", "false").lower() in {"1", "true", "yes"}

cors_args = dict(
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if allow_all:
    app.add_middleware(CORSMiddleware, allow_origins=["*"], **cors_args)
else:
    app.add_middleware(CORSMiddleware, allow_origins=DEFAULT_ALLOWED_ORIGINS, **cors_args)

# Include API routes
app.include_router(router, prefix="/api")

@app.get("/")
async def root():
    return {"message": "GridGPT API is running"}

@app.get("/health")
async def health_check():
    return {"status": "healthy"}