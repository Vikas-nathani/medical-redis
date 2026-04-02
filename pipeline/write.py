"""Redis write pipeline for patients and consultations."""

from __future__ import annotations

import json
import time

from api.exceptions import handle_redis_error
from core.logging import get_logger
from db.connection import get_redis_client
from models.consultation import Consultation
from models.patient import Patient


MAX_HISTORY_SNAPSHOTS = 10  # Cap embedded history so consultation payloads do not grow without bound.
logger = get_logger(__name__)


ATOMIC_CONSULTATION_WRITE_LUA = """
local complaint_key = KEYS[1]
local global_zset = KEYS[2]

local patient_id = ARGV[1]
local complaint_slug = ARGV[2]
local chief_complaint = ARGV[3]
local visit_date = ARGV[4]
local doctor_id = ARGV[5]
local questions = ARGV[6]
local symptoms_observed = ARGV[7]
local medications = ARGV[8]
local follow_up_date = ARGV[9]
local follow_up_instruction = ARGV[10]
local timestamp_score = tonumber(ARGV[11])
local max_history_snapshots = tonumber(ARGV[12])

local counter_key = "counter:" .. patient_id .. ":" .. complaint_slug
local visit_num = redis.call("INCR", counter_key)
local consultation_id = string.format("cons_%s_%03d", complaint_slug, visit_num)
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

		local previous_history_raw = previous_map["follow_up_history"] or "[]"
		local ok, previous_history = pcall(cjson.decode, previous_history_raw)
		if ok and type(previous_history) == "table" then
			local keep_count = max_history_snapshots - 1
			if keep_count < 0 then
				keep_count = 0
			end
			local start_index = 1
			if #previous_history > keep_count then
				start_index = #previous_history - keep_count + 1
			end
			for i = start_index, #previous_history do
				table.insert(follow_up_history, previous_history[i])
			end
		end

		local previous_snapshot = {
			consultation_id = previous_map["consultation_id"] or previous_consultation_id,
			visit_number = tonumber(previous_map["visit_number"] or "0"),
			visit_date = previous_map["visit_date"] or "",
			doctor_id = previous_map["doctor_id"] or "",
			questions = previous_map["questions"] or "",
			symptoms_observed = previous_map["symptoms_observed"] or "",
			medications = previous_map["medications"] or "",
			follow_up_date = previous_map["follow_up_date"] or "",
			follow_up_instruction = previous_map["follow_up_instruction"] or ""
		}
		table.insert(follow_up_history, previous_snapshot)
	end
end

local follow_up_history_json = "[]"  -- Preserve JSON array shape for first visits.
if #follow_up_history > 0 then
	follow_up_history_json = cjson.encode(follow_up_history)
end

redis.call(
	"HSET",
	consultation_hash_key,
	"consultation_id", consultation_id,
	"patient_id", patient_id,
	"chief_complaint", chief_complaint,
	"complaint_slug", complaint_slug,
	"visit_number", tostring(visit_num),
	"visit_date", visit_date,
	"doctor_id", doctor_id,
	"questions", questions,
	"symptoms_observed", symptoms_observed,
	"medications", medications,
	"follow_up_date", follow_up_date,
	"follow_up_instruction", follow_up_instruction,
	"prev_consultation_id", previous_consultation_id,
	"follow_up_history", follow_up_history_json
)

redis.call("ZADD", global_zset, timestamp_score, consultation_id)
redis.call("RPUSH", complaint_key, consultation_id)

return cjson.encode({
	consultation_id = consultation_id,
	visit_number = visit_num,
	prev_consultation_id = previous_consultation_id,
	follow_up_history = follow_up_history
})
"""

_redis_client = get_redis_client()  # Load the Lua script once so Redis can cache it by SHA for reuse.
_atomic_write_script = _redis_client.register_script(ATOMIC_CONSULTATION_WRITE_LUA)  # Use a registered script handle instead of per-call EVAL.


def patient_key(patient_id: str) -> str:
	return f"patient:{patient_id}"


def consultation_key(patient_id: str, consultation_id: str) -> str:
	return f"consultation:{patient_id}:{consultation_id}"


def global_zset_key(patient_id: str) -> str:
	return f"patient:{patient_id}:consultations"


def complaint_list_key(patient_id: str, complaint_slug: str) -> str:
	return f"patient:{patient_id}:complaint:{complaint_slug}"


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
		handle_redis_error(exc, "write_patient")  # Convert Redis failures into HTTP errors at the API boundary.


def write_consultation(consultation: Consultation) -> str:
	try:
		timestamp_score = int(time.time() * 1_000_000)  # Use microseconds so ZSET ordering stays stable during bursts.

		result_raw = _atomic_write_script(  # Call the pre-registered Lua script by SHA instead of ad hoc EVAL.
			keys=[
				complaint_list_key(consultation.patient_id, consultation.complaint_slug),
				global_zset_key(consultation.patient_id),
			],
			args=[
				consultation.patient_id,
				consultation.complaint_slug,
				consultation.chief_complaint,
				consultation.visit_date,
				consultation.doctor_id,
				consultation.questions,
				consultation.symptoms_observed,
				consultation.medications,
				consultation.follow_up_date,
				consultation.follow_up_instruction,
				str(timestamp_score),
				str(MAX_HISTORY_SNAPSHOTS),
			],
		)
		result = json.loads(result_raw)
		consultation.consultation_id = str(result["consultation_id"])
		consultation.visit_number = int(result["visit_number"])
		consultation.prev_consultation_id = str(result.get("prev_consultation_id", ""))
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
		handle_redis_error(exc, "write_consultation")  # Surface Redis-side failures as HTTP errors instead of generic 500s.
		raise


def get_idempotency_consultation_id(idempotency_key: str) -> str | None:
	try:
		client = get_redis_client()
		value = client.get(f"idempotency:{idempotency_key}")
		return str(value) if value else None
	except Exception as exc:
		handle_redis_error(exc, "get_idempotency_consultation_id")
		raise


def set_idempotency_consultation_id(idempotency_key: str, consultation_id: str, ttl_seconds: int = 86400) -> None:
	try:
		client = get_redis_client()
		client.set(f"idempotency:{idempotency_key}", consultation_id, ex=ttl_seconds)
	except Exception as exc:
		handle_redis_error(exc, "set_idempotency_consultation_id")
		raise
