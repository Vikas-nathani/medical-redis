"""Redis read helpers for the medical consultation system."""

from __future__ import annotations

import json

from api.exceptions import handle_redis_error
from core.logging import get_logger
from db.connection import get_redis_client
from pipeline.write import complaint_list_key, consultation_key, global_zset_key, patient_key


logger = get_logger(__name__)


def _load_json(raw: str | None, fallback):
	if raw in (None, ""):
		return fallback
	try:
		return json.loads(raw)
	except (TypeError, ValueError):
		return fallback


def ensure_list(value):
	if isinstance(value, list):
		return value
	if isinstance(value, dict) and len(value) == 0:
		return []
	return value if value else []


def _decode_history_entry(entry: dict[str, object]) -> dict[str, object]:
	decoded = dict(entry)

	for list_field in [
		"chief_complaints",
		"key_questions",
		"diagnoses",
		"investigations",
		"medications",
		"procedures",
	]:
		value = decoded.get(list_field)
		if isinstance(value, str):
			decoded[list_field] = ensure_list(_load_json(value, []))
		elif value is None:
			decoded[list_field] = []
		else:
			decoded[list_field] = ensure_list(value)

	vitals_value = decoded.get("vitals")
	if isinstance(vitals_value, str):
		decoded["vitals"] = _load_json(vitals_value, None)
	elif "vitals" not in decoded:
		decoded["vitals"] = None

	for text_field in [
		"consultation_id",
		"visit_date",
		"key_questions_ai_notes",
		"diagnoses_ai_notes",
		"investigations_ai_notes",
		"medications_ai_notes",
		"procedures_ai_notes",
		"advice",
		"follow_up_date",
		"advice_ai_notes",
	]:
		decoded[text_field] = str(decoded.get(text_field, ""))

	try:
		decoded["visit_number"] = int(decoded.get("visit_number", 0))
	except (TypeError, ValueError):
		decoded["visit_number"] = 0

	return decoded


def _decode_consultation(data: dict[str, str]) -> dict[str, object]:
	follow_up_history_raw = _load_json(data.get("follow_up_history"), [])
	if not isinstance(follow_up_history_raw, list):
		follow_up_history_raw = []

	decoded_history: list[dict[str, object]] = []
	for entry in follow_up_history_raw:
		if isinstance(entry, dict):
			decoded_history.append(_decode_history_entry(entry))

	try:
		visit_number = int(data.get("visit_number", "0"))
	except (TypeError, ValueError):
		visit_number = 0

	return {
		"consultation_id": data.get("consultation_id", ""),
		"patient_id": data.get("patient_id", ""),
		"visit_date": data.get("visit_date", ""),
		"visit_number": visit_number,
		"chief_complaints": ensure_list(_load_json(data.get("chief_complaints", "[]") or "[]", [])),
		"vitals": _load_json(data.get("vitals"), None),
		"key_questions": ensure_list(_load_json(data.get("key_questions", "[]") or "[]", [])),
		"key_questions_ai_notes": data.get("key_questions_ai_notes", ""),
		"diagnoses": ensure_list(_load_json(data.get("diagnoses", "[]") or "[]", [])),
		"diagnoses_ai_notes": data.get("diagnoses_ai_notes", ""),
		"investigations": ensure_list(_load_json(data.get("investigations", "[]") or "[]", [])),
		"investigations_ai_notes": data.get("investigations_ai_notes", ""),
		"medications": ensure_list(_load_json(data.get("medications", "[]") or "[]", [])),
		"medications_ai_notes": data.get("medications_ai_notes", ""),
		"procedures": ensure_list(_load_json(data.get("procedures", "[]") or "[]", [])),
		"procedures_ai_notes": data.get("procedures_ai_notes", ""),
		"advice": data.get("advice", ""),
		"follow_up_date": data.get("follow_up_date", ""),
		"advice_ai_notes": data.get("advice_ai_notes", ""),
		"follow_up_history": decoded_history,
	}


def get_patient(patient_id: str) -> dict[str, str] | None:
	try:
		client = get_redis_client()
		patient_data = client.hgetall(patient_key(patient_id))
		return patient_data or None
	except Exception as exc:
		handle_redis_error(exc, "get_patient")
		raise


def get_all_consultations(patient_id: str, limit: int = 20, offset: int = 0) -> tuple[list[dict[str, object]], int]:
	try:
		client = get_redis_client()
		zkey = global_zset_key(patient_id)
		total_count = client.zcard(zkey)
		end = offset + limit - 1
		consultation_ids = client.zrevrange(zkey, offset, end)
		results: list[dict[str, object]] = []
		for consultation_id in consultation_ids:
			consultation_data = client.hgetall(consultation_key(patient_id, consultation_id))
			if consultation_data:
				results.append(_decode_consultation(consultation_data))
		logger.info(
			"consultation_list_read",
			extra={"operation": "consultation_list_read", "patient_id": patient_id},
		)
		return results, total_count
	except Exception as exc:
		handle_redis_error(exc, "get_all_consultations")
		raise


def get_consultation(patient_id: str, consultation_id: str) -> dict[str, object] | None:
	try:
		client = get_redis_client()
		consultation_data = client.hgetall(consultation_key(patient_id, consultation_id))
		if not consultation_data:
			return None
		return _decode_consultation(consultation_data)
	except Exception as exc:
		handle_redis_error(exc, "get_consultation")
		raise


def get_patient_consultations(patient_id: str) -> list[dict[str, object]]:
	try:
		client = get_redis_client()
		consultation_ids = client.zrevrange(global_zset_key(patient_id), 0, -1)
		results: list[dict[str, object]] = []
		for consultation_id in consultation_ids:
			consultation_data = client.hgetall(consultation_key(patient_id, consultation_id))
			if consultation_data:
				results.append(_decode_consultation(consultation_data))
		return results
	except Exception as exc:
		handle_redis_error(exc, "get_patient_consultations")
		raise


def get_complaint_chain(
	patient_id: str,
	complaint_slug: str,
	limit: int = 20,
	offset: int = 0,
) -> tuple[list[dict[str, object]], int]:
	try:
		client = get_redis_client()
		list_key = complaint_list_key(patient_id, complaint_slug)
		total_count = client.llen(list_key)
		end = offset + limit - 1
		consultation_ids = client.lrange(list_key, offset, end)
		results: list[dict[str, object]] = []
		for consultation_id in consultation_ids:
			consultation_data = client.hgetall(consultation_key(patient_id, consultation_id))
			if consultation_data:
				results.append(_decode_consultation(consultation_data))
		logger.info(
			"complaint_chain_read",
			extra={"operation": "complaint_chain_read", "patient_id": patient_id},
		)
		return results, total_count
	except Exception as exc:
		handle_redis_error(exc, "get_complaint_chain")
		raise


def get_latest_complaint_consultation(patient_id: str, complaint_slug: str) -> dict[str, object] | None:
	try:
		client = get_redis_client()
		latest_consultation_id = client.lindex(complaint_list_key(patient_id, complaint_slug), -1)
		if not latest_consultation_id:
			return None
		consultation_data = client.hgetall(consultation_key(patient_id, latest_consultation_id))
		if not consultation_data:
			return None
		logger.info(
			"latest_consultation_read",
			extra={
				"operation": "latest_consultation_read",
				"patient_id": patient_id,
				"consultation_id": latest_consultation_id,
			},
		)
		return _decode_consultation(consultation_data)
	except Exception as exc:
		handle_redis_error(exc, "get_latest_complaint_consultation")
		raise


def get_latest_consultation(patient_id: str, complaint_slug: str) -> dict[str, object] | None:
	return get_latest_complaint_consultation(patient_id, complaint_slug)


def get_complaint_chains(patient_id: str) -> list[dict]:
	"""Return all complaint chains for a patient with visit counts.
	Powers the complaint dropdown in the frontend.
	"""
	try:
		client = get_redis_client()
		pattern = f"patient:{patient_id}:complaint:*"
		keys = client.keys(pattern)
		prefix = f"patient:{patient_id}:complaint:"
		results = []
		for key in keys:
			chain_slug = key[len(prefix):]
			if not chain_slug:
				continue
			visit_count = client.llen(key)
			display_name = chain_slug.replace("-", " ").title()
			results.append({
				"chain_slug": chain_slug,
				"display_name": display_name,
				"visit_count": visit_count,
			})
		results.sort(key=lambda x: x["visit_count"], reverse=True)
		return results
	except Exception as exc:
		handle_redis_error(exc, "get_complaint_chains")
		raise
