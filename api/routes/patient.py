"""Patient endpoints for creating and retrieving patient records."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from api.exceptions import handle_redis_error
from api.schemas import MessageResponse, PatientCreateRequest, PatientResponse
from core.logging import get_logger
from db.connection import get_redis_client
from models.patient import Patient
from pipeline.read import get_patient
from pipeline.write import patient_key, write_patient


router = APIRouter(tags=["patient"])
logger = get_logger(__name__)


@router.post("/patient", response_model=MessageResponse, status_code=status.HTTP_201_CREATED)
def create_patient(payload: PatientCreateRequest) -> MessageResponse:
	"""Create a patient record if it does not already exist."""
	try:
		client = get_redis_client()
		if client.exists(patient_key(payload.patient_id)):
			raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Patient {payload.patient_id} already exists")

		patient = Patient(**payload.model_dump())
		write_patient(patient)
		logger.info(
			"patient_created",
			extra={"operation": "patient_register", "patient_id": payload.patient_id},
		)
		return MessageResponse(message=f"Patient {payload.patient_id} created successfully")
	except HTTPException:
		raise
	except Exception as exc:
		handle_redis_error(exc, "create_patient")
		raise


@router.get("/patient/{patient_id}", response_model=PatientResponse)
def read_patient(patient_id: str) -> PatientResponse:
	"""Fetch a patient record by patient ID."""
	try:
		patient_data = get_patient(patient_id)
		if not patient_data:
			raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")
		logger.info(
			"patient_read",
			extra={"operation": "patient_read", "patient_id": patient_id},
		)
		return PatientResponse(**patient_data)
	except HTTPException:
		raise
	except Exception as exc:
		handle_redis_error(exc, "read_patient")
		raise