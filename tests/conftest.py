from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from db.connection import get_redis_client
from main import app
from pipeline.write import complaint_list_key, consultation_key, global_zset_key, patient_key


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
def sample_consultation_payload(registered_patient: dict[str, str]) -> dict[str, str]:
	return {
		"patient_id": registered_patient["patient_id"],
		"chief_complaint": "High Fever",
		"visit_date": "2026-04-02",
		"doctor_id": "D01",
		"questions": "How many days of fever?",
		"symptoms_observed": "Fever with chills",
		"medications": "Paracetamol 500mg",
		"follow_up_date": "2026-04-05",
		"follow_up_instruction": "Hydrate and rest",
	}


@pytest.fixture
def unique_idempotency_key() -> str:
	return str(uuid.uuid4())