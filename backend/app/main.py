import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import OperationalError

from app.api import catalog, checklists, dashboard, demo, health, leads, reviews, transcription
from app.core.config import get_settings

settings = get_settings()

app = FastAPI(
    title="CIMET QA SaleGuard",
    description=(
        "Evidence-backed QA scoring for sales calls. Checks are configured in the database, "
        "evidence is tied to real transcript segments, and the APPROVED / HOLD / HUMAN_REVIEW "
        "gate is computed by deterministic application code -- never by a language model."
    ),
    version="0.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

logger = logging.getLogger("uvicorn.error")


@app.exception_handler(OperationalError)
def database_unavailable(request: Request, exc: OperationalError) -> JSONResponse:
    """The database is down or unreachable: say so plainly instead of a 500 and a stack trace."""
    logger.error("Database unavailable for %s %s: %s", request.method, request.url.path, type(exc.orig).__name__)
    return JSONResponse(
        status_code=503,
        content={
            "detail": (
                "The database is not reachable. Start PostgreSQL (Docker Desktop, then "
                "`docker start cimet-qa-postgres`) and retry."
            )
        },
    )


app.include_router(health.router)
app.include_router(dashboard.router)
app.include_router(catalog.router)
app.include_router(checklists.router)
app.include_router(leads.router)
app.include_router(transcription.router)
app.include_router(demo.router)
app.include_router(reviews.router)
