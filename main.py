"""FastAPI entrypoint for the Medical Consultation API."""

from __future__ import annotations

from fastapi import FastAPI

from api.routes.consultation import router as consultation_router
from api.routes.patient import router as patient_router


app = FastAPI(title="Medical Consultation API")

app.include_router(patient_router, prefix="/api/v1")
app.include_router(consultation_router, prefix="/api/v1")


@app.get("/")
def root() -> dict[str, str]:
	"""Return a simple health check for the API."""
	return {"status": "ok", "message": "Medical Consultation API is running"}


def main() -> None:
	import uvicorn

	uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False, workers=1)  # Keep a single worker until process-safety is proven.


if __name__ == "__main__":
	main()
