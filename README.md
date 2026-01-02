# fastapi-poetry

FastAPI project initialized with Poetry.

## Requirements

- Python 3.11+
- Poetry

## Install

```bash
poetry install
```

## Run (dev)

```bash
poetry run uvicorn app.main:app --reload
```

Open:

- Docs: http://127.0.0.1:8000/docs
- OpenAPI JSON: http://127.0.0.1:8000/openapi.json

## Endpoints

- `GET /health` -> basic health check
