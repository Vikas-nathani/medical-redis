from __future__ import annotations

import re
import uuid

from fastapi.testclient import TestClient


def _extract_consultation_id(message: str) -> str:
	match = re.search(r"(cons_[a-z0-9-]+_\d{3})", message)
	assert match is not None
	return match.group(1)


def _create_consultation(client: TestClient, payload: dict[str, str], idempotency_key: str | None = None):
	headers = {"Content-Type": "application/json"}
	if idempotency_key:
		headers["Idempotency-Key"] = idempotency_key
	return client.post("/api/v1/consultation", json=payload, headers=headers)


# Proves a new patient can be registered successfully and the response includes the patient ID.
def test_register_new_patient_returns_201_and_patient_id_in_response(client: TestClient) -> None:
	patient_id = f"patient-{uuid.uuid4().hex}"
	response = client.post(
		"/api/v1/patient",
		json={
			"patient_id": patient_id,
			"name": "New Patient",
			"dob": "1991-02-03",
			"gender": "female",
			"blood_type": "A+",
			"contact": "8888888888",
			"address": "Bengaluru",
		},
	)
	assert response.status_code == 201
	assert patient_id in response.json()["message"]


# Proves duplicate patient registration is blocked with HTTP 409.
def test_register_duplicate_patient_returns_409(client: TestClient, registered_patient: dict[str, str]) -> None:
	response = client.post("/api/v1/patient", json=registered_patient)
	assert response.status_code == 409


# Proves an existing patient can be retrieved with the expected fields.
def test_get_existing_patient_returns_200_and_correct_fields(client: TestClient, registered_patient: dict[str, str]) -> None:
	response = client.get(f"/api/v1/patient/{registered_patient['patient_id']}")
	assert response.status_code == 200
	body = response.json()
	assert body["patient_id"] == registered_patient["patient_id"]
	assert body["name"] == registered_patient["name"]
	assert body["gender"] == registered_patient["gender"]


# Proves a missing patient returns HTTP 404 instead of an empty payload.
def test_get_nonexistent_patient_returns_404(client: TestClient) -> None:
	response = client.get("/api/v1/patient/patient-does-not-exist")
	assert response.status_code == 404


# Proves a valid consultation can be stored and returns a consultation ID in the response.
def test_store_valid_consultation_returns_201_and_consultation_id_in_response(client: TestClient, sample_consultation_payload: dict[str, str]) -> None:
	response = _create_consultation(client, sample_consultation_payload)
	assert response.status_code == 201
	assert _extract_consultation_id(response.json()["message"])


# Proves consultation creation fails with HTTP 404 when the patient does not exist.
def test_store_consultation_for_nonexistent_patient_returns_404(client: TestClient, sample_consultation_payload: dict[str, str]) -> None:
	payload = dict(sample_consultation_payload)
	payload["patient_id"] = "missing-patient"
	response = _create_consultation(client, payload)
	assert response.status_code == 404


# Proves schema validation rejects missing required consultation fields with HTTP 422.
def test_store_consultation_with_missing_required_field_returns_422(client: TestClient, sample_consultation_payload: dict[str, str]) -> None:
	payload = dict(sample_consultation_payload)
	del payload["doctor_id"]
	response = _create_consultation(client, payload)
	assert response.status_code == 422


# Proves complaint validation rejects strings shorter than three characters.
def test_store_consultation_with_complaint_shorter_than_three_characters_returns_422(client: TestClient, sample_consultation_payload: dict[str, str]) -> None:
	payload = dict(sample_consultation_payload)
	payload["chief_complaint"] = "ab"
	response = _create_consultation(client, payload)
	assert response.status_code == 422


# Proves date validation rejects non-ISO visit dates.
def test_store_consultation_with_invalid_date_format_returns_422(client: TestClient, sample_consultation_payload: dict[str, str]) -> None:
	payload = dict(sample_consultation_payload)
	payload["visit_date"] = "02-04-2026"
	response = _create_consultation(client, payload)
	assert response.status_code == 422


# Proves complaints that collapse to an empty slug are rejected by the consultation route.
def test_store_consultation_with_invalid_slug_from_bad_complaint_returns_422(client: TestClient, sample_consultation_payload: dict[str, str]) -> None:
	payload = dict(sample_consultation_payload)
	payload["chief_complaint"] = "!!!"
	response = _create_consultation(client, payload)
	assert response.status_code == 422


# Proves the same Idempotency-Key returns the same consultation ID on the second request.
def test_post_consultation_with_same_idempotency_key_returns_same_consultation_id(client: TestClient, sample_consultation_payload: dict[str, str], unique_idempotency_key: str) -> None:
	first_response = _create_consultation(client, sample_consultation_payload, unique_idempotency_key)
	second_response = _create_consultation(client, sample_consultation_payload, unique_idempotency_key)
	first_id = _extract_consultation_id(first_response.json()["message"])
	second_id = _extract_consultation_id(second_response.json()["message"])
	assert first_response.status_code == 201
	assert second_response.status_code == 200
	assert first_id == second_id


# Proves the second Idempotency-Key replay is served as a 200 response instead of a second create.
def test_post_consultation_with_same_idempotency_key_returns_200_not_201_on_replay(client: TestClient, sample_consultation_payload: dict[str, str], unique_idempotency_key: str) -> None:
	_ = _create_consultation(client, sample_consultation_payload, unique_idempotency_key)
	response = _create_consultation(client, sample_consultation_payload, unique_idempotency_key)
	assert response.status_code == 200


# Proves consultation creation still works normally when no Idempotency-Key header is sent.
def test_post_consultation_without_idempotency_key_returns_201(client: TestClient, sample_consultation_payload: dict[str, str]) -> None:
	response = _create_consultation(client, sample_consultation_payload)
	assert response.status_code == 201


# Proves the all-consultations endpoint returns a list payload for an existing patient.
def test_get_all_consultations_returns_200_and_results_list(client: TestClient, sample_consultation_payload: dict[str, str]) -> None:
	first = _create_consultation(client, sample_consultation_payload)
	second_payload = dict(sample_consultation_payload)
	second_payload["questions"] = "Any improvement after the first visit?"
	second_response = _create_consultation(client, second_payload)
	patient_id = sample_consultation_payload["patient_id"]
	response = client.get(f"/api/v1/patient/{patient_id}/consultations")
	assert response.status_code == 200
	body = response.json()
	assert isinstance(body["consultations"], list)
	assert body["total_count"] == 2
	assert _extract_consultation_id(first.json()["message"])
	assert _extract_consultation_id(second_response.json()["message"])


# Proves limit and offset paging return the expected slice of consultation history.
def test_get_all_consultations_with_pagination_limit_and_offset_work_correctly(client: TestClient, sample_consultation_payload: dict[str, str]) -> None:
	created_ids: list[str] = []
	for index in range(3):
		payload = dict(sample_consultation_payload)
		payload["questions"] = f"Question batch {index}"
		payload["follow_up_instruction"] = f"Instruction batch {index}"
		response = _create_consultation(client, payload)
		created_ids.append(_extract_consultation_id(response.json()["message"]))
	patient_id = sample_consultation_payload["patient_id"]
	response = client.get(f"/api/v1/patient/{patient_id}/consultations", params={"limit": 2, "offset": 1})
	assert response.status_code == 200
	body = response.json()
	returned_ids = [item["consultation_id"] for item in body["consultations"]]
	assert body["total_count"] == 3
	assert returned_ids == [created_ids[1], created_ids[0]]


# Proves an existing complaint chain is returned in visit order with the correct records.
def test_get_complaint_chain_for_existing_complaint_returns_200_and_correct_chain(client: TestClient, sample_consultation_payload: dict[str, str]) -> None:
	first = _create_consultation(client, sample_consultation_payload)
	second_payload = dict(sample_consultation_payload)
	second_payload["questions"] = "Any headache and chills now?"
	second_payload["symptoms_observed"] = "Fever with chills, headache"
	second_payload["follow_up_instruction"] = "Continue medication and hydrate well"
	second = _create_consultation(client, second_payload)
	patient_id = sample_consultation_payload["patient_id"]
	response = client.get(f"/api/v1/patient/{patient_id}/complaint", params={"complaint": "High Fever"})
	assert response.status_code == 200
	body = response.json()
	assert body["total_count"] == 2
	returned_ids = [item["consultation_id"] for item in body["consultations"]]
	assert returned_ids == [
		_extract_consultation_id(first.json()["message"]),
		_extract_consultation_id(second.json()["message"]),
	]


# Proves a missing complaint chain returns HTTP 404 instead of an empty success response.
def test_get_complaint_chain_for_nonexistent_complaint_returns_404(client: TestClient, sample_consultation_payload: dict[str, str]) -> None:
	response = client.get(
		f"/api/v1/patient/{sample_consultation_payload['patient_id']}/complaint",
		params={"complaint": "Unmatched Complaint"},
	)
	assert response.status_code == 404


# Proves the latest consultation endpoint includes prior visit history for the complaint chain.
def test_get_latest_consultation_for_complaint_returns_200_and_embedded_history(client: TestClient, sample_consultation_payload: dict[str, str]) -> None:
	first = _create_consultation(client, sample_consultation_payload)
	second_payload = dict(sample_consultation_payload)
	second_payload["questions"] = "Are the symptoms improving?"
	second_payload["symptoms_observed"] = "Reduced fever"
	second = _create_consultation(client, second_payload)
	patient_id = sample_consultation_payload["patient_id"]
	response = client.get(f"/api/v1/patient/{patient_id}/complaint/latest", params={"complaint": "High Fever"})
	assert response.status_code == 200
	body = response.json()
	assert body["consultation_id"] == _extract_consultation_id(second.json()["message"])
	assert body["follow_up_history"]
	assert body["follow_up_history"][0]["consultation_id"] == _extract_consultation_id(first.json()["message"])


# Proves the request middleware adds an X-Request-ID header on ordinary responses.
def test_any_request_includes_x_request_id_header(client: TestClient) -> None:
	response = client.get("/")
	assert response.status_code == 200
	assert response.headers["X-Request-ID"]


# Proves two separate requests receive different UUID request IDs.
def test_two_different_requests_return_different_x_request_id_values(client: TestClient) -> None:
	first_response = client.get("/")
	second_response = client.get("/")
	first_id = first_response.headers["X-Request-ID"]
	second_id = second_response.headers["X-Request-ID"]
	uuid.UUID(first_id)
	uuid.UUID(second_id)
	assert first_id != second_id


# Proves /health reports OK when Redis is reachable.
def test_health_endpoint_returns_200_and_status_ok_when_redis_is_up(client: TestClient) -> None:
	response = client.get("/health")
	assert response.status_code == 200
	assert response.json()["status"] == "ok"


# Proves /metrics exposes the standard HTTP request counter family.
def test_metrics_endpoint_returns_200_and_http_requests_total_is_present(client: TestClient) -> None:
	response = client.get("/metrics")
	assert response.status_code == 200
	assert "http_requests_total" in response.text


# Proves a real 404 request causes the Prometheus error counter family to appear in metrics.
def test_metrics_endpoint_after_triggering_a_404_includes_http_request_errors_total(client: TestClient) -> None:
	client.get("/api/v1/this-route-does-not-exist")
	response = client.get("/metrics")
	assert response.status_code == 200
	assert "http_request_errors_total" in response.text