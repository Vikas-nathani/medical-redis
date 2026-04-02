"""Consultation endpoints for storing and retrieving consultation chains."""

from __future__ import annotations

import re
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, status

from api.schemas import ConsultationCreateRequest, ConsultationListResponse, ConsultationResponse, MessageResponse
from db.connection import get_redis_client
from models.consultation import Consultation
from pipeline.read import get_all_consultations, get_complaint_chain, get_latest_consultation, get_patient
from pipeline.write import complaint_list_key, write_consultation


router = APIRouter(tags=["consultation"])


def generate_slug(text: str) -> str:
	"""
	Converts free text chief_complaint to a lowercase hyphenated slug.
	Examples:
	  "Fever and body ache"  -> "fever-and-body-ache"
	  "High Fever"           -> "high-fever"
	  "FEVER"                -> "fever"
	  "Back Pain"            -> "back-pain"
	  "Fever, chills & rash" -> "fever-chills-rash"
	"""
	text = text.lower().strip()
	text = re.sub(r"[^a-z0-9\s]", "", text) 
	text = re.sub(r"\s+", "-", text)
	text = re.sub(r"-+", "-", text)
	return text.strip("-")


def _utc_now_iso() -> str:
	return datetime.now(timezone.utc).isoformat()


def _to_response(payload: dict[str, object]) -> ConsultationResponse:
	return ConsultationResponse(**payload)


@router.post("/consultation", response_model=MessageResponse, status_code=status.HTTP_201_CREATED)
def create_consultation(request: ConsultationCreateRequest) -> MessageResponse:
	"""Create a consultation and append it to the appropriate complaint chain."""
	if not get_patient(request.patient_id):
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail=f"Patient {request.patient_id} not found. Create the patient first.",
		)

	complaint_slug = generate_slug(request.chief_complaint)
	print(
		f"[consultation] generated slug '{complaint_slug}' "
		f"from chief_complaint '{request.chief_complaint}'"
	)

	client = get_redis_client()
	current_visits = client.llen(complaint_list_key(request.patient_id, complaint_slug))
	next_visit_number = current_visits + 1
	consultation_id = f"cons_{complaint_slug}_{next_visit_number:03d}"
	visit_date = request.visit_date or _utc_now_iso()

	consultation = Consultation(
		consultation_id=consultation_id,
		patient_id=request.patient_id,
		chief_complaint=request.chief_complaint,
		complaint_slug=complaint_slug,
		visit_number=next_visit_number,
		visit_date=visit_date,
		doctor_id=request.doctor_id,
		questions=request.questions,
		symptoms_observed=request.symptoms_observed,
		medications=request.medications,
		follow_up_date=request.follow_up_date,
		follow_up_instruction=request.follow_up_instruction,
		prev_consultation_id="",
		follow_up_history=[],
	)
	write_consultation(consultation)
	return MessageResponse(message=f"Consultation {consultation_id} stored for patient {request.patient_id}")


@router.get("/patient/{patient_id}/consultations", response_model=ConsultationListResponse)
def read_all_consultations(patient_id: str) -> ConsultationListResponse:
	"""Fetch all consultations for a patient, newest first."""
	if not get_patient(patient_id):
		raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")
	consultations = [
		_to_response(consultation).model_dump()
		for consultation in get_all_consultations(patient_id)
	]
	return ConsultationListResponse(consultations=consultations)


@router.get("/patient/{patient_id}/complaint/{complaint_slug}", response_model=ConsultationListResponse)
def read_complaint_chain(patient_id: str, complaint_slug: str) -> ConsultationListResponse:
	"""Fetch a specific complaint chain in visit order, oldest first."""
	consultations_raw = get_complaint_chain(patient_id, complaint_slug)
	if not consultations_raw:
		raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"No visits found for complaint {complaint_slug}")
	consultations = [_to_response(consultation).model_dump() for consultation in consultations_raw]
	return ConsultationListResponse(consultations=consultations)


@router.get("/patient/{patient_id}/complaint/{complaint_slug}/latest", response_model=ConsultationResponse)
def read_latest_consultation(patient_id: str, complaint_slug: str) -> ConsultationResponse:
	"""Fetch the latest consultation for a complaint chain for RAG chunking."""
	consultation = get_latest_consultation(patient_id, complaint_slug)
	if not consultation:
		raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"No visits found for complaint {complaint_slug}")
	return ConsultationResponse(**consultation)