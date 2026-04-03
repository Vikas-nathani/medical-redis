from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from db.connection import get_redis_client
from main import app
from pipeline.write import complaint_list_key, consultation_key, global_zset_key, patient_key


SAMPLE_CONSULTATION = {
	"patient_id": "P001",
	"doctor_id": "D01",
	"visit_date": "2026-04-03",
	"chief_complaints": ["High Fever"],
	"vitals": {
		"height_cm": 170,
		"weight_kg": 65,
		"head_circ_cm": 54,
		"temp_celsius": 101,
		"bp_mmhg": "120/80",
	},
	"key_questions": [
		{"question": "Fever since?", "answer": "Gradual onset"},
		{"question": "Peak temperature?", "answer": "101C"},
		{"question": "Activity level?", "answer": "Moderate"},
		{"question": "Fever pattern?", "answer": "Intermittent"},
		{"question": "Chills present?", "answer": "Yes"},
	],
	"key_questions_ai_notes": "Patient presents with gradual onset fever...",
	"diagnoses": [
		{"name": "Viral Upper Respiratory Infection", "selected": True, "is_custom": False},
		{"name": "Influenza", "selected": True, "is_custom": False},
	],
	"diagnoses_ai_notes": "Most likely viral in origin...",
	"investigations": [
		{"name": "Complete Blood Count (CBC)", "selected": True, "is_custom": False},
		{"name": "C-Reactive Protein (CRP)", "selected": True, "is_custom": False},
	],
	"investigations_ai_notes": "CBC and CRP to assess infection...",
	"medications": [
		{"name": "Acetaminophen", "selected": True, "is_custom": False},
		{"name": "Ibuprofen", "selected": True, "is_custom": False},
	],
	"medications_ai_notes": "Antipyretics prescribed for fever management...",
	"procedures": [
		{"name": "Fever Management", "selected": True, "is_custom": False},
		{"name": "Hydration", "selected": True, "is_custom": False},
	],
	"procedures_ai_notes": "Fever management and hydration advised...",
	"advice": "Rest and hydrate well",
	"follow_up_date": "2026-04-11",
	"advice_ai_notes": "Follow up in 7 days if no improvement...",
}


@pytest.fixture
def client() -> TestClient:
	with TestClient(app) as test_client:
		yield test_client


@pytest.fixture
def redis_client():
	return get_redis_client()


def _delete_patient_keys(redis_client, patient_id: str) -> None:
	keys_to_delete: set[str] = set()
	patterns = [
		patient_key(patient_id),
		f"{patient_key(patient_id)}:*",
		consultation_key(patient_id, "*"),
		global_zset_key(patient_id),
		f"{global_zset_key(patient_id)}*",
		complaint_list_key(patient_id, "*"),
		f"counter:{patient_id}:*",
	]
	for pattern in patterns:
		for key in redis_client.scan_iter(match=pattern):
			keys_to_delete.add(key)
	if keys_to_delete:
		redis_client.delete(*sorted(keys_to_delete))


@pytest.fixture
def registered_patient(client: TestClient, redis_client):
	patient_id = f"patient-{uuid.uuid4().hex}"
	payload = {
		"patient_id": patient_id,
		"name": "Test Patient",
		"dob": "1990-01-01",
		"gender": "male",
		"blood_type": "O+",
		"contact": "9999999999",
		"address": "Hyderabad",
	}
	response = client.post("/api/v1/patient", json=payload)
	assert response.status_code == 201
	yield payload
	_delete_patient_keys(redis_client, patient_id)


@pytest.fixture
def sample_consultation_payload(registered_patient: dict[str, str]) -> dict[str, object]:
	payload = dict(SAMPLE_CONSULTATION)
	payload["patient_id"] = registered_patient["patient_id"]
	return payload


@pytest.fixture
def unique_idempotency_key() -> str:
	return str(uuid.uuid4())
