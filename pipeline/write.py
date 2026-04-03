"""Redis write pipeline for patients and consultations."""

from __future__ import annotations

import hashlib
import json
import re
import time
from datetime import date

from api.exceptions import handle_redis_error
from core.logging import get_logger
from db.connection import get_redis_client
from models.consultation import ConsultationModel
from models.patient import Patient


MAX_HISTORY_SNAPSHOTS = 10
logger = get_logger(__name__)


ATOMIC_CONSULTATION_WRITE_LUA = """
local complaint_key = KEYS[1]
local global_zset = KEYS[2]

local patient_id = ARGV[1]
local complaint_slug = ARGV[2]
local doctor_id = ARGV[3]
local visit_date = ARGV[4]
local chief_complaints_json = ARGV[5]
local vitals_json = ARGV[6]
local key_questions_json = ARGV[7]
local key_questions_ai_notes = ARGV[8]
local diagnoses_json = ARGV[9]
local diagnoses_ai_notes = ARGV[10]
local investigations_json = ARGV[11]
local investigations_ai_notes = ARGV[12]
local medications_json = ARGV[13]
local medications_ai_notes = ARGV[14]
local procedures_json = ARGV[15]
local procedures_ai_notes = ARGV[16]
local advice = ARGV[17]
local follow_up_date = ARGV[18]
local advice_ai_notes = ARGV[19]
local timestamp_score = tonumber(ARGV[20])
local created_at = ARGV[21]
local max_history_snapshots = tonumber(ARGV[22])

local function decode_json_array(raw)
	if not raw or raw == "" then
		return {}
	end
	local ok, decoded = pcall(cjson.decode, raw)
	if ok and type(decoded) == "table" then
		return decoded
	end
	return {}
end

local function decode_json_object(raw)
	if not raw or raw == "" or raw == "null" then
		return nil
	end
	local ok, decoded = pcall(cjson.decode, raw)
	if ok and type(decoded) == "table" then
		return decoded
	end
	return nil
end

local counter_key = "counter:" .. patient_id .. ":" .. complaint_slug
local visit_num = redis.call("INCR", counter_key)
local consultation_id = patient_id .. "-" .. complaint_slug .. "-" .. tostring(visit_num)
local consultation_hash_key = "consultation:" .. patient_id .. ":" .. consultation_id

local previous_consultation_id = redis.call("LINDEX", complaint_key, -1)
if not previous_consultation_id then
	previous_consultation_id = ""
end

local follow_up_history = {}
if previous_consultation_id ~= "" then
	local previous_hash_key = "consultation:" .. patient_id .. ":" .. previous_consultation_id
	local previous_hash_raw = redis.call("HGETALL", previous_hash_key)
	if next(previous_hash_raw) ~= nil then
		local previous_map = {}
		for i = 1, #previous_hash_raw, 2 do
			previous_map[previous_hash_raw[i]] = previous_hash_raw[i + 1]
		end

		local previous_history = decode_json_array(previous_map["follow_up_history"] or "[]")
		for i = 1, #previous_history do
			table.insert(follow_up_history, previous_history[i])
		end

		local previous_snapshot = {
			consultation_id = previous_map["consultation_id"] or previous_consultation_id,
			visit_number = tonumber(previous_map["visit_number"] or "0"),
			visit_date = previous_map["visit_date"] or "",
			doctor_id = previous_map["doctor_id"] or "",
			chief_complaints = decode_json_array(previous_map["chief_complaints"] or "[]"),
			vitals = decode_json_object(previous_map["vitals"] or "null"),
			key_questions = decode_json_array(previous_map["key_questions"] or "[]"),
			key_questions_ai_notes = previous_map["key_questions_ai_notes"] or "",
			diagnoses = decode_json_array(previous_map["diagnoses"] or "[]"),
			diagnoses_ai_notes = previous_map["diagnoses_ai_notes"] or "",
			investigations = decode_json_array(previous_map["investigations"] or "[]"),
			investigations_ai_notes = previous_map["investigations_ai_notes"] or "",
			medications = decode_json_array(previous_map["medications"] or "[]"),
			medications_ai_notes = previous_map["medications_ai_notes"] or "",
			procedures = decode_json_array(previous_map["procedures"] or "[]"),
			procedures_ai_notes = previous_map["procedures_ai_notes"] or "",
			advice = previous_map["advice"] or "",
			follow_up_date = previous_map["follow_up_date"] or "",
			advice_ai_notes = previous_map["advice_ai_notes"] or ""
		}
		table.insert(follow_up_history, previous_snapshot)
	end
end

if max_history_snapshots > 0 and #follow_up_history > max_history_snapshots then
	local start_index = #follow_up_history - max_history_snapshots + 1
	local trimmed = {}
	for i = start_index, #follow_up_history do
		table.insert(trimmed, follow_up_history[i])
	end
	follow_up_history = trimmed
end

local follow_up_history_json = "[]"
if #follow_up_history > 0 then
	follow_up_history_json = cjson.encode(follow_up_history)
end

redis.call(
	"HSET",
	consultation_hash_key,
	"consultation_id", consultation_id,
	"patient_id", patient_id,
	"doctor_id", doctor_id,
	"visit_date", visit_date,
	"visit_number", tostring(visit_num),
	"chief_complaints", chief_complaints_json,
	"vitals", vitals_json,
	"key_questions", key_questions_json,
	"key_questions_ai_notes", key_questions_ai_notes,
	"diagnoses", diagnoses_json,
	"diagnoses_ai_notes", diagnoses_ai_notes,
	"investigations", investigations_json,
	"investigations_ai_notes", investigations_ai_notes,
	"medications", medications_json,
	"medications_ai_notes", medications_ai_notes,
	"procedures", procedures_json,
	"procedures_ai_notes", procedures_ai_notes,
	"advice", advice,
	"follow_up_date", follow_up_date,
	"advice_ai_notes", advice_ai_notes,
	"follow_up_history", follow_up_history_json,
	"created_at", created_at
)

redis.call("ZADD", global_zset, timestamp_score, consultation_id)
redis.call("RPUSH", complaint_key, consultation_id)

return cjson.encode({
	consultation_id = consultation_id,
	visit_number = visit_num,
	follow_up_history = follow_up_history
})
"""

_redis_client = get_redis_client()
_atomic_write_script = _redis_client.register_script(ATOMIC_CONSULTATION_WRITE_LUA)


def patient_key(patient_id: str) -> str:
	return f"patient:{patient_id}"


def consultation_key(patient_id: str, consultation_id: str) -> str:
	return f"consultation:{patient_id}:{consultation_id}"


def global_zset_key(patient_id: str) -> str:
	return f"patient:{patient_id}:consultations"


def complaint_list_key(patient_id: str, complaint_slug: str) -> str:
	return f"patient:{patient_id}:complaint:{complaint_slug}"


def generate_slug(text: str) -> str:
	text = text.lower().strip()
	text = re.sub(r"[^a-z0-9\s]", "", text)
	text = re.sub(r"\s+", "-", text)
	text = re.sub(r"-+", "-", text)
	return text.strip("-")


def generate_idempotency_key(patient_id: str, complaint_slug: str, visit_date: str, doctor_id: str) -> str:
	raw = f"{patient_id}:{complaint_slug}:{visit_date}:{doctor_id}"
	return hashlib.sha256(raw.encode()).hexdigest()


def safe_json_list(value) -> str:
	if not value:
		return "[]"
	if isinstance(value, list):
		return json.dumps(value)
	return "[]"


def normalize_history_entries_for_lists(history: list) -> list:
	list_fields = ["investigations", "procedures", "medications", "diagnoses", "key_questions", "chief_complaints"]
	normalized: list = []
	for entry in history:
		if not isinstance(entry, dict):
			continue
		snapshot = dict(entry)
		for field in list_fields:
			value = snapshot.get(field)
			if isinstance(value, list):
				snapshot[field] = value
			elif isinstance(value, dict) and len(value) == 0:
				snapshot[field] = []
			elif not value:
				snapshot[field] = []
			else:
				snapshot[field] = []
		normalized.append(snapshot)
	return normalized


def write_patient(patient: Patient) -> None:
	try:
		client = get_redis_client()
		key = patient_key(patient.patient_id)

		if client.exists(key):
			logger.info(
				"patient_exists_skip",
				extra={"operation": "patient_register", "patient_id": patient.patient_id},
			)
			return

		client.hset(key, mapping=patient.to_redis_dict())
		logger.info(
			"patient_written",
			extra={"operation": "patient_register", "patient_id": patient.patient_id},
		)
	except Exception as exc:
		handle_redis_error(exc, "write_patient")


def write_consultation(consultation: ConsultationModel) -> str:
	try:
		complaints = consultation.chief_complaints or []
		if not complaints:
			raise ValueError("At least one chief complaint is required")

		complaint_slug = generate_slug(str(complaints[0]))
		if not complaint_slug:
			raise ValueError("chief_complaints[0] produced an invalid slug")

		timestamp_score = int(time.time() * 1_000_000)
		created_at = date.today().isoformat()
		visit_date = consultation.visit_date or ""
		consultation.follow_up_history = normalize_history_entries_for_lists(consultation.follow_up_history or [])

		result_raw = _atomic_write_script(
			keys=[
				complaint_list_key(consultation.patient_id, complaint_slug),
				global_zset_key(consultation.patient_id),
			],
			args=[
				consultation.patient_id,
				complaint_slug,
				consultation.doctor_id,
				visit_date,
				safe_json_list(consultation.chief_complaints),
				json.dumps(consultation.vitals),
				safe_json_list(consultation.key_questions),
				consultation.key_questions_ai_notes or "",
				safe_json_list(consultation.diagnoses),
				consultation.diagnoses_ai_notes or "",
				safe_json_list(consultation.investigations),
				consultation.investigations_ai_notes or "",
				safe_json_list(consultation.medications),
				consultation.medications_ai_notes or "",
				safe_json_list(consultation.procedures),
				consultation.procedures_ai_notes or "",
				consultation.advice or "",
				consultation.follow_up_date or "",
				consultation.advice_ai_notes or "",
				str(timestamp_score),
				created_at,
				str(MAX_HISTORY_SNAPSHOTS),
			],
		)
		result = json.loads(result_raw)
		consultation.consultation_id = str(result["consultation_id"])
		consultation.visit_number = int(result["visit_number"])
		consultation.follow_up_history = list(result.get("follow_up_history", []))

		logger.info(
			"consultation_written",
			extra={
				"operation": "consultation_write",
				"patient_id": consultation.patient_id,
				"consultation_id": consultation.consultation_id,
			},
		)
		return consultation.consultation_id
	except Exception as exc:
		handle_redis_error(exc, "write_consultation")
		raise


def get_idempotency_consultation_id(patient_id: str, complaint_slug: str, visit_date: str, doctor_id: str) -> str | None:
	try:
		client = get_redis_client()
		idempotency_key = generate_idempotency_key(patient_id, complaint_slug, visit_date, doctor_id)
		value = client.get(f"idempotency:{idempotency_key}")
		return str(value) if value else None
	except Exception as exc:
		handle_redis_error(exc, "get_idempotency_consultation_id")
		raise


def set_idempotency_consultation_id(patient_id: str, complaint_slug: str, visit_date: str, doctor_id: str, consultation_id: str) -> None:
	try:
		client = get_redis_client()
		idempotency_key = generate_idempotency_key(patient_id, complaint_slug, visit_date, doctor_id)
		client.set(f"idempotency:{idempotency_key}", consultation_id)
	except Exception as exc:
		handle_redis_error(exc, "set_idempotency_consultation_id")
		raise
