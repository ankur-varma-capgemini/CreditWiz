"""Knowledge pillar API.

    GET /api/knowledge/sources   the systems and document types that will feed Nexus
"""

from fastapi import APIRouter

from .models import KnowledgeSources
from .store import load

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


@router.get("/sources", response_model=KnowledgeSources)
def sources() -> KnowledgeSources:
    return load()
