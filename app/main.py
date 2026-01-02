from fastapi import FastAPI

from app.routers import line_router

app = FastAPI(title="Scanper API - LINE OCR Bot", version="0.1.0")

# Include routers
app.include_router(line_router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


def dev() -> None:
    import uvicorn

    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
