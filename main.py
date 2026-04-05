"""FastAPI entrypoint for the Medical Consultation API."""

from __future__ import annotations

import uuid

from fastapi import FastAPI
from fastapi import Request
from prometheus_client import Counter
from prometheus_fastapi_instrumentator import Instrumentator

from api.routes.consultation import router as consultation_router
from api.routes.health import router as health_router
from api.routes.patient import router as patient_router
from core.logging import reset_request_id, set_request_id

app = FastAPI(title="Medical Consultation API")

http_request_errors_total = Counter(
	"http_request_errors_total",
	"Total number of HTTP error responses",
	["method", "path", "status"],
)


from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten this once you know the frontend origin
    allow_methods=["*"],
    allow_headers=["*"],
)
@app.middleware("http")
async def add_request_id(request: Request, call_next):
	request_id = str(uuid.uuid4())
	request.state.request_id = request_id
	token = set_request_id(request_id)
	try:
		response = await call_next(request)
		if response.status_code >= 400:
			http_request_errors_total.labels(
				method=request.method,
				path=request.url.path,
				status=str(response.status_code),
			).inc()
		response.headers["X-Request-ID"] = request_id
		return response
	finally:
		reset_request_id(token)

app.include_router(patient_router, prefix="/api/v1")
app.include_router(consultation_router, prefix="/api/v1")
app.include_router(health_router)

Instrumentator().instrument(app).expose(app, endpoint="/metrics")

@app.get("/")
def root() -> dict[str, str]:
	"""Return a simple health check for the API."""
	return {"status": "ok", "message": "Medical Consultation API is running"}


def main() -> None:
	import uvicorn

	uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False, workers=1)  # Keep a single worker until process-safety is proven.


if __name__ == "__main__":
	main()
