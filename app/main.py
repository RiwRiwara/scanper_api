import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import line_router, liff_router
from app.database import lifespan

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

app = FastAPI(
    title="Scanper API - LINE OCR Bot",
    version="0.1.0",
    lifespan=lifespan,  # Database lifecycle management
)

# CORS middleware for LIFF frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://liff.line.me",  # LINE LIFF
        "http://localhost:3000",  # Local development
        "http://localhost:5173",  # Vite dev server
        "https://scanper-frontend.vercel.app",  # Production frontend
    ],
    allow_origin_regex=r"https://.*\.vercel\.app",  # All Vercel preview deployments
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(line_router)
app.include_router(liff_router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


def dev() -> None:
    import uvicorn

    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
