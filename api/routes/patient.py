"""Patient endpoints for creating and retrieving patient records."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from api.schemas import MessageResponse, PatientCreateRequest, PatientResponse
from db.connection import get_redis_client
from models.patient import Patient
from pipeline.read import get_patient
from pipeline.write import patient_key, write_patient


router = APIRouter(tags=["patient"])


@router.post("/patient", response_model=MessageResponse, status_code=status.HTTP_201_CREATED)
def create_patient(payload: PatientCreateRequest) -> MessageResponse:
	"""Create a patient record if it does not already exist."""
	client = get_redis_client()
	if client.exists(patient_key(payload.patient_id)):
		raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Patient {payload.patient_id} already exists")

	patient = Patient(**payload.model_dump())
	write_patient(patient)
	return MessageResponse(message=f"Patient {payload.patient_id} created successfully")


@router.get("/patient/{patient_id}", response_model=PatientResponse)
def read_patient(patient_id: str) -> PatientResponse:
	"""Fetch a patient record by patient ID."""
	patient_data = get_patient(patient_id)
	if not patient_data:
		raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")
	return PatientResponse(**patient_data)