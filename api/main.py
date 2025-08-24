from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
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
    allow_origins=ALLOWED_ORIGINS,
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