"""Consultation endpoints for storing and retrieving consultation chains."""

from __future__ import annotations

import re

from fastapi import APIRouter, HTTPException, Query, status

from api.exceptions import handle_redis_error
from api.schemas import ConsultationCreateRequest, ConsultationListResponse, ConsultationResponse, MessageResponse
from core.logging import get_logger
from models.consultation import Consultation
from pipeline.read import get_all_consultations, get_complaint_chain, get_latest_consultation, get_patient
from pipeline.write import write_consultation


router = APIRouter(tags=["consultation"])
logger = get_logger(__name__)


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


def _to_response(payload: dict[str, object]) -> ConsultationResponse:
	return ConsultationResponse(**payload)


@router.post("/consultation", response_model=MessageResponse, status_code=status.HTTP_201_CREATED)
def create_consultation(request: ConsultationCreateRequest) -> MessageResponse:
	"""Create a consultation and append it to the appropriate complaint chain."""
	try:
		if not get_patient(request.patient_id):
			raise HTTPException(
				status_code=status.HTTP_404_NOT_FOUND,
				detail=f"Patient {request.patient_id} not found. Create the patient first.",
			)

		complaint_slug = generate_slug(request.chief_complaint)
		if complaint_slug == "" or re.fullmatch(r"[-_]+", complaint_slug):
			raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="chief_complaint produced an invalid slug")

		logger.info(
			"consultation_slug_generated",
			extra={
				"operation": "consultation_write",
				"patient_id": request.patient_id,
				"consultation_id": "",
				"complaint_slug": complaint_slug,
			},
		)

		consultation = Consultation(
			consultation_id="",
			patient_id=request.patient_id,
			chief_complaint=request.chief_complaint,
			complaint_slug=complaint_slug,
			visit_number=0,
			visit_date=request.visit_date,
			doctor_id=request.doctor_id,
			questions=request.questions,
			symptoms_observed=request.symptoms_observed,
			medications=request.medications,
			follow_up_date=request.follow_up_date,
			follow_up_instruction=request.follow_up_instruction,
			prev_consultation_id="",
			follow_up_history=[],
		)
		consultation_id = write_consultation(consultation)
		return MessageResponse(message=f"Consultation {consultation_id} stored for patient {request.patient_id}")
	except HTTPException:
		raise
	except Exception as exc:
		handle_redis_error(exc, "create_consultation")
		raise


@router.get("/patient/{patient_id}/consultations", response_model=ConsultationListResponse)
def read_all_consultations(
	patient_id: str,
	limit: int = Query(default=20, ge=1),
	offset: int = Query(default=0, ge=0),
) -> ConsultationListResponse:
	"""Fetch all consultations for a patient, newest first."""
	try:
		if not get_patient(patient_id):
			raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")
		consultations_raw, total_count = get_all_consultations(patient_id, limit=limit, offset=offset)
		consultations = [_to_response(consultation).model_dump() for consultation in consultations_raw]
		return ConsultationListResponse(consultations=consultations, total_count=total_count)
	except HTTPException:
		raise
	except Exception as exc:
		handle_redis_error(exc, "read_all_consultations")
		raise


@router.get("/patient/{patient_id}/complaint/{complaint_slug}", response_model=ConsultationListResponse)
def read_complaint_chain(
	patient_id: str,
	complaint_slug: str,
	limit: int = Query(default=20, ge=1),
	offset: int = Query(default=0, ge=0),
) -> ConsultationListResponse:
	"""Fetch a specific complaint chain in visit order, oldest first."""
	try:
		consultations_raw, total_count = get_complaint_chain(patient_id, complaint_slug, limit=limit, offset=offset)
		if not consultations_raw:
			raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"No visits found for complaint {complaint_slug}")
		consultations = [_to_response(consultation).model_dump() for consultation in consultations_raw]
		return ConsultationListResponse(consultations=consultations, total_count=total_count)
	except HTTPException:
		raise
	except Exception as exc:
		handle_redis_error(exc, "read_complaint_chain")
		raise


@router.get("/patient/{patient_id}/complaint/{complaint_slug}/latest", response_model=ConsultationResponse)
def read_latest_consultation(patient_id: str, complaint_slug: str) -> ConsultationResponse:
	"""Fetch the latest consultation for a complaint chain for RAG chunking."""
	try:
		consultation = get_latest_consultation(patient_id, complaint_slug)
		if not consultation:
			raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"No visits found for complaint {complaint_slug}")
		return ConsultationResponse(**consultation)
	except HTTPException:
		raise
	except Exception as exc:
		handle_redis_error(exc, "read_latest_consultation")
		raise