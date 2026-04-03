"""Consultation endpoints for storing and retrieving consultation chains."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Response, status

from api.exceptions import handle_redis_error
from api.schemas import ConsultationRequest, ConsultationResponse
from core.logging import get_logger
from models.consultation import ConsultationModel
from pipeline.read import (
	get_all_consultations,
	get_complaint_chain,
	get_consultation,
	get_latest_complaint_consultation,
	get_patient,
)
from pipeline.write import generate_slug, get_idempotency_consultation_id, set_idempotency_consultation_id, write_consultation


router = APIRouter(tags=["consultation"])
logger = get_logger(__name__)


def normalize_consultation_dict(d: dict) -> dict:
	list_fields = ["key_questions", "diagnoses", "investigations", "medications", "procedures", "chief_complaints"]
	for field in list_fields:
		if not isinstance(d.get(field), list):
			d[field] = []
	history = d.get("follow_up_history", [])
	if not isinstance(history, list):
		history = []
	for entry in history:
		if not isinstance(entry, dict):
			continue
		for field in list_fields:
			if not isinstance(entry.get(field), list):
				entry[field] = []
	d["follow_up_history"] = history
	return d


@router.post("/consultation", response_model=ConsultationResponse, status_code=status.HTTP_201_CREATED)
def create_consultation(
	request: ConsultationRequest,
	response: Response,
) -> ConsultationResponse:
	"""Create a consultation and append it to the appropriate complaint chain."""
	try:
		if not get_patient(request.patient_id):
			raise HTTPException(
				status_code=status.HTTP_404_NOT_FOUND,
				detail=f"Patient {request.patient_id} not found. Create the patient first.",
			)

		complaint_slug = generate_slug(request.chief_complaints[0])
		if complaint_slug == "":
			raise HTTPException(
				status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
				detail="chief_complaints[0] produced an invalid slug",
			)

		visit_date = request.visit_date or ""
		existing_consultation_id = get_idempotency_consultation_id(
			request.patient_id,
			complaint_slug,
			visit_date,
		)
		if existing_consultation_id:
			existing = get_consultation(request.patient_id, existing_consultation_id)
			if not existing:
				raise HTTPException(
					status_code=status.HTTP_404_NOT_FOUND,
					detail=f"Consultation {existing_consultation_id} not found for idempotency replay",
				)
			existing = normalize_consultation_dict(existing)
			response.status_code = status.HTTP_200_OK
			return ConsultationResponse(**existing)

		logger.info(
			"consultation_slug_generated",
			extra={
				"operation": "consultation_write",
				"patient_id": request.patient_id,
				"consultation_id": "",
				"complaint_slug": complaint_slug,
			},
		)

		consultation = ConsultationModel(
			consultation_id="",
			patient_id=request.patient_id,
			visit_date=visit_date,
			visit_number=0,
			chief_complaints=request.chief_complaints,
			vitals=request.vitals.model_dump() if request.vitals else None,
			key_questions=[item.model_dump() for item in (request.key_questions or [])],
			key_questions_ai_notes=request.key_questions_ai_notes or "",
			diagnoses=[item.model_dump() for item in (request.diagnoses or [])],
			diagnoses_ai_notes=request.diagnoses_ai_notes or "",
			investigations=[item.model_dump() for item in (request.investigations or [])],
			investigations_ai_notes=request.investigations_ai_notes or "",
			medications=[item.model_dump() for item in (request.medications or [])],
			medications_ai_notes=request.medications_ai_notes or "",
			procedures=[item.model_dump() for item in (request.procedures or [])],
			procedures_ai_notes=request.procedures_ai_notes or "",
			advice=request.advice or "",
			follow_up_date=request.follow_up_date or "",
			advice_ai_notes=request.advice_ai_notes or "",
			follow_up_history=[],
		)

		consultation_id = write_consultation(consultation)
		set_idempotency_consultation_id(
			request.patient_id,
			complaint_slug,
			visit_date,
			consultation_id,
		)

		created = get_consultation(request.patient_id, consultation_id)
		if not created:
			raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Stored consultation not found")
		return ConsultationResponse(**created)
	except HTTPException:
		raise
	except Exception as exc:
		handle_redis_error(exc, "create_consultation")
		raise


@router.get("/patient/{patient_id}/consultations", response_model=list[ConsultationResponse])
def read_all_consultations(
	patient_id: str,
	limit: int = Query(default=20, ge=1),
	offset: int = Query(default=0, ge=0),
) -> list[ConsultationResponse]:
	"""Fetch all consultations for a patient, newest first."""
	try:
		if not get_patient(patient_id):
			raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")
		consultations_raw, _ = get_all_consultations(patient_id, limit=limit, offset=offset)
		return [ConsultationResponse(**consultation) for consultation in consultations_raw]
	except HTTPException:
		raise
	except Exception as exc:
		handle_redis_error(exc, "read_all_consultations")
		raise


@router.get("/patient/{patient_id}/complaint", response_model=list[ConsultationResponse])
def read_complaint_chain(
	patient_id: str,
	complaint: str = Query(..., min_length=3),
	limit: int = Query(default=20, ge=1),
	offset: int = Query(default=0, ge=0),
) -> list[ConsultationResponse]:
	"""Fetch a specific complaint chain in visit order, oldest first."""
	try:
		complaint_slug = generate_slug(complaint)
		if not complaint_slug:
			raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Complaint text produces an invalid slug")

		consultations_raw, _ = get_complaint_chain(patient_id, complaint_slug, limit=limit, offset=offset)
		if not consultations_raw:
			raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"No consultations found for complaint: {complaint}")
		return [ConsultationResponse(**consultation) for consultation in consultations_raw]
	except HTTPException:
		raise
	except Exception as exc:
		handle_redis_error(exc, "read_complaint_chain")
		raise


@router.get("/patient/{patient_id}/complaint/latest", response_model=ConsultationResponse)
def read_latest_consultation(
	patient_id: str,
	complaint: str = Query(..., min_length=3),
) -> ConsultationResponse:
	"""Fetch the latest consultation for a complaint chain for RAG chunking."""
	try:
		complaint_slug = generate_slug(complaint)
		if not complaint_slug:
			raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Complaint text produces an invalid slug")

		consultation = get_latest_complaint_consultation(patient_id, complaint_slug)
		if not consultation:
			raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"No consultations found for complaint: {complaint}")
		return ConsultationResponse(**consultation)
	except HTTPException:
		raise
	except Exception as exc:
		handle_redis_error(exc, "read_latest_consultation")
		raise
