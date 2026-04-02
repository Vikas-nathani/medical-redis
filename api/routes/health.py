"""Health and readiness endpoints for service and Redis dependency status."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from db.connection import get_redis_client


router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> JSONResponse:
	try:
		client = get_redis_client()
		client.ping()
		return JSONResponse(
			status_code=200,
			content={"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()},
		)
	except Exception:
		return JSONResponse(
			status_code=503,
			content={"status": "degraded", "reason": "redis unavailable"},
		)