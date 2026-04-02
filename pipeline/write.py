"""Redis write pipeline for patients and consultations."""

from __future__ import annotations

import time
from typing import Any

from db.connection import get_redis_client
from models.consultation import Consultation
from models.patient import Patient


def patient_key(patient_id: str) -> str:
	return f"patient:{patient_id}"


def consultation_key(patient_id: str, consultation_id: str) -> str:
	return f"consultation:{patient_id}:{consultation_id}"


def global_zset_key(patient_id: str) -> str:
	return f"patient:{patient_id}:consultations"


def complaint_list_key(patient_id: str, complaint_slug: str) -> str:
	return f"patient:{patient_id}:complaint:{complaint_slug}"


def _consultation_snapshot(data: dict[str, str]) -> dict[str, Any]:
	return {
		"consultation_id": data.get("consultation_id", ""),
		"visit_number": int(data.get("visit_number", 0)),
		"visit_date": data.get("visit_date", ""),
		"doctor_id": data.get("doctor_id", ""),
		"questions": data.get("questions", ""),
		"symptoms_observed": data.get("symptoms_observed", ""),
		"medications": data.get("medications", ""),
		"follow_up_date": data.get("follow_up_date", ""),
		"follow_up_instruction": data.get("follow_up_instruction", ""),
	}


def write_patient(patient: Patient) -> None:
	client = get_redis_client()
	key = patient_key(patient.patient_id)

	if client.exists(key):
		print(f"[patient] skipped existing hash for {key}")
		return

	client.hset(key, mapping=patient.to_redis_dict())
	print(f"[patient] wrote hash for {key}")


def write_consultation(consultation: Consultation) -> None:
	client = get_redis_client()

	complaint_key = complaint_list_key(consultation.patient_id, consultation.complaint_slug)
	consultation_hash_key = consultation_key(consultation.patient_id, consultation.consultation_id)

	previous_consultation_id = client.lindex(complaint_key, -1)
	follow_up_history: list[dict[str, Any]] = []
	prev_consultation_id = ""
	visit_number = 1

	if previous_consultation_id:
		previous_hash = client.hgetall(consultation_key(consultation.patient_id, previous_consultation_id))
		if previous_hash:
			previous_consultation = Consultation.from_redis_dict(previous_hash)
			follow_up_history = list(previous_consultation.follow_up_history)
			follow_up_history.append(_consultation_snapshot(previous_hash))
			prev_consultation_id = previous_consultation.consultation_id
			visit_number = previous_consultation.visit_number + 1

	consultation.prev_consultation_id = prev_consultation_id
	consultation.visit_number = visit_number
	consultation.follow_up_history = follow_up_history

	print(
		f"[consultation] step1 resolved previous chain for {consultation.consultation_id} "
		f"(prev={prev_consultation_id or 'none'}, visit_number={visit_number})"
	)

	with client.pipeline() as pipeline:
		pipeline.hset(consultation_hash_key, mapping=consultation.to_redis_dict())
		pipeline.zadd(global_zset_key(consultation.patient_id), {consultation.consultation_id: time.time()})
		pipeline.rpush(complaint_key, consultation.consultation_id)
		pipeline.execute()

	print(f"[consultation] wrote hash, zset entry, and complaint list for {consultation.consultation_id}")
