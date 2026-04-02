"""Redis read helpers for the medical consultation system."""

from __future__ import annotations

import json

from db.connection import get_redis_client
from models.consultation import Consultation
from pipeline.write import complaint_list_key, consultation_key, global_zset_key, patient_key


def _decode_consultation(data: dict[str, str]) -> dict[str, object]:
	consultation = Consultation.from_redis_dict(data)
	return {
		"consultation_id": consultation.consultation_id,
		"patient_id": consultation.patient_id,
		"chief_complaint": consultation.chief_complaint,
		"complaint_slug": consultation.complaint_slug,
		"visit_number": consultation.visit_number,
		"visit_date": consultation.visit_date,
		"doctor_id": consultation.doctor_id,
		"questions": consultation.questions,
		"symptoms_observed": consultation.symptoms_observed,
		"medications": consultation.medications,
		"follow_up_date": consultation.follow_up_date,
		"follow_up_instruction": consultation.follow_up_instruction,
		"prev_consultation_id": consultation.prev_consultation_id,
		"follow_up_history": consultation.follow_up_history,
	}


def get_patient(patient_id: str) -> dict[str, str] | None:
	client = get_redis_client()
	patient_data = client.hgetall(patient_key(patient_id))
	return patient_data or None


def get_all_consultations(patient_id: str) -> list[dict[str, object]]:
	client = get_redis_client()
	consultation_ids = client.zrevrange(global_zset_key(patient_id), 0, -1)
	results: list[dict[str, object]] = []
	for consultation_id in consultation_ids:
		consultation_data = client.hgetall(consultation_key(patient_id, consultation_id))
		if consultation_data:
			results.append(_decode_consultation(consultation_data))
	return results


def get_complaint_chain(patient_id: str, complaint_slug: str) -> list[dict[str, object]]:
	client = get_redis_client()
	consultation_ids = client.lrange(complaint_list_key(patient_id, complaint_slug), 0, -1)
	results: list[dict[str, object]] = []
	for consultation_id in consultation_ids:
		consultation_data = client.hgetall(consultation_key(patient_id, consultation_id))
		if consultation_data:
			results.append(_decode_consultation(consultation_data))
	return results


def get_latest_consultation(patient_id: str, complaint_slug: str) -> dict[str, object] | None:
	client = get_redis_client()
	latest_consultation_id = client.lindex(complaint_list_key(patient_id, complaint_slug), -1)
	if not latest_consultation_id:
		return None
	consultation_data = client.hgetall(consultation_key(patient_id, latest_consultation_id))
	if not consultation_data:
		return None
	return _decode_consultation(consultation_data)


def get_consultation(patient_id: str, consultation_id: str) -> Consultation | None:
	client = get_redis_client()
	consultation_data = client.hgetall(consultation_key(patient_id, consultation_id))
	if not consultation_data:
		return None
	return Consultation.from_redis_dict(consultation_data)


def get_patient_consultations(patient_id: str) -> list[str]:
	client = get_redis_client()
	return client.zrange(global_zset_key(patient_id), 0, -1)
