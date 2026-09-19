from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import catalog, checklists, dashboard, health, leads, reviews
from app.core.config import get_settings

settings = get_settings()

app = FastAPI(
    title="CIMET QA Gate",
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

app.include_router(health.router)
app.include_router(dashboard.router)
app.include_router(catalog.router)
app.include_router(checklists.router)
app.include_router(leads.router)
app.include_router(reviews.router)
