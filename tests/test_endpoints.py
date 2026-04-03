from __future__ import annotations

import uuid

from fastapi.testclient import TestClient


def _create_consultation(client: TestClient, payload: dict[str, object]):
	return client.post("/api/v1/consultation", json=payload, headers={"Content-Type": "application/json"})


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


# Proves a valid consultation can be stored and returns the full consultation shape.
def test_store_valid_consultation_returns_201_and_full_payload(client: TestClient, sample_consultation_payload: dict[str, object]) -> None:
	response = _create_consultation(client, sample_consultation_payload)
	assert response.status_code == 201
	body = response.json()
	assert body["consultation_id"].startswith(f"{sample_consultation_payload['patient_id']}-high-fever-")
	assert isinstance(body["chief_complaints"], list)
	assert isinstance(body["vitals"], dict)
	assert isinstance(body["key_questions"], list)
	assert isinstance(body["diagnoses"], list)
	assert isinstance(body["investigations"], list)
	assert isinstance(body["medications"], list)
	assert isinstance(body["procedures"], list)


# Proves consultation creation fails with HTTP 404 when the patient does not exist.
def test_store_consultation_for_nonexistent_patient_returns_404(client: TestClient, sample_consultation_payload: dict[str, object]) -> None:
	payload = dict(sample_consultation_payload)
	payload["patient_id"] = "missing-patient"
	response = _create_consultation(client, payload)
	assert response.status_code == 404


# Proves schema validation rejects missing required consultation fields with HTTP 422.
def test_store_consultation_with_missing_required_field_returns_422(client: TestClient, sample_consultation_payload: dict[str, object]) -> None:
	payload = dict(sample_consultation_payload)
	del payload["doctor_id"]
	response = _create_consultation(client, payload)
	assert response.status_code == 422


# Proves complaint validation rejects entries shorter than three characters.
def test_store_consultation_with_complaint_shorter_than_three_characters_returns_422(client: TestClient, sample_consultation_payload: dict[str, object]) -> None:
	payload = dict(sample_consultation_payload)
	payload["chief_complaints"] = ["ab"]
	response = _create_consultation(client, payload)
	assert response.status_code == 422


# Proves date validation rejects non-ISO visit dates.
def test_store_consultation_with_invalid_date_format_returns_422(client: TestClient, sample_consultation_payload: dict[str, object]) -> None:
	payload = dict(sample_consultation_payload)
	payload["visit_date"] = "02-04-2026"
	response = _create_consultation(client, payload)
	assert response.status_code == 422


# Proves complaints that collapse to an empty slug are rejected by the consultation route.
def test_store_consultation_with_invalid_slug_from_bad_complaint_returns_422(client: TestClient, sample_consultation_payload: dict[str, object]) -> None:
	payload = dict(sample_consultation_payload)
	payload["chief_complaints"] = ["!!!"]
	response = _create_consultation(client, payload)
	assert response.status_code == 422



# Proves backend-generated idempotency replays the same request body with HTTP 200 and same consultation ID.
def test_post_same_consultation_twice_without_header_returns_200_and_same_consultation_id(client: TestClient, sample_consultation_payload: dict[str, object]) -> None:
	first_response = _create_consultation(client, sample_consultation_payload)
	second_response = _create_consultation(client, sample_consultation_payload)
	first_id = first_response.json()["consultation_id"]
	second_id = second_response.json()["consultation_id"]
	assert first_response.status_code == 201
	assert second_response.status_code == 200
	assert first_id == second_id


# Proves different visit_date values produce different backend idempotency keys and new consultations.
def test_post_consultations_with_different_visit_dates_return_201_and_different_consultation_ids(client: TestClient, sample_consultation_payload: dict[str, object]) -> None:
	first_payload = dict(sample_consultation_payload)
	first_payload["visit_date"] = "2026-04-03"
	second_payload = dict(sample_consultation_payload)
	second_payload["visit_date"] = "2026-04-04"
	first_response = _create_consultation(client, first_payload)
	second_response = _create_consultation(client, second_payload)
	assert first_response.status_code == 201
	assert second_response.status_code == 201
	assert first_response.json()["consultation_id"] != second_response.json()["consultation_id"]


# Proves the all-consultations endpoint returns consultation objects for an existing patient.
def test_get_all_consultations_returns_200_and_results_list(client: TestClient, sample_consultation_payload: dict[str, object]) -> None:
	first_payload = dict(sample_consultation_payload)
	first_payload["visit_date"] = "2026-04-03"
	_ = _create_consultation(client, first_payload)
	second_payload = dict(sample_consultation_payload)
	second_payload["visit_date"] = "2026-04-04"
	second_payload["advice"] = "Continue hydration"
	_ = _create_consultation(client, second_payload)
	patient_id = sample_consultation_payload["patient_id"]
	response = client.get(f"/api/v1/patient/{patient_id}/consultations")
	assert response.status_code == 200
	body = response.json()
	assert isinstance(body, list)
	assert len(body) == 2


# Proves limit and offset paging return the expected slice of consultation history.
def test_get_all_consultations_with_pagination_limit_and_offset_work_correctly(client: TestClient, sample_consultation_payload: dict[str, object]) -> None:
	created_ids: list[str] = []
	for index in range(3):
		payload = dict(sample_consultation_payload)
		payload["visit_date"] = f"2026-04-0{index + 3}"
		payload["advice_ai_notes"] = f"Advice note {index}"
		response = _create_consultation(client, payload)
		created_ids.append(response.json()["consultation_id"])
	patient_id = sample_consultation_payload["patient_id"]
	response = client.get(f"/api/v1/patient/{patient_id}/consultations", params={"limit": 2, "offset": 1})
	assert response.status_code == 200
	body = response.json()
	returned_ids = [item["consultation_id"] for item in body]
	assert returned_ids == [created_ids[1], created_ids[0]]


# Proves an existing complaint chain is returned in visit order with the correct records.
def test_get_complaint_chain_for_existing_complaint_returns_200_and_correct_chain(client: TestClient, sample_consultation_payload: dict[str, object]) -> None:
	first_payload = dict(sample_consultation_payload)
	first_payload["visit_date"] = "2026-04-03"
	first = _create_consultation(client, first_payload)
	second_payload = dict(sample_consultation_payload)
	second_payload["visit_date"] = "2026-04-04"
	second_payload["advice"] = "Continue medication and hydrate well"
	second = _create_consultation(client, second_payload)
	patient_id = sample_consultation_payload["patient_id"]
	response = client.get(f"/api/v1/patient/{patient_id}/complaint", params={"complaint": "High Fever"})
	assert response.status_code == 200
	body = response.json()
	assert len(body) == 2
	returned_ids = [item["consultation_id"] for item in body]
	assert returned_ids == [first.json()["consultation_id"], second.json()["consultation_id"]]


# Proves a missing complaint chain returns HTTP 404 instead of an empty success response.
def test_get_complaint_chain_for_nonexistent_complaint_returns_404(client: TestClient, sample_consultation_payload: dict[str, object]) -> None:
	response = client.get(
		f"/api/v1/patient/{sample_consultation_payload['patient_id']}/complaint",
		params={"complaint": "Unmatched Complaint"},
	)
	assert response.status_code == 404


# Proves the latest consultation endpoint includes prior visit history for the complaint chain.
def test_get_latest_consultation_for_complaint_returns_200_and_embedded_full_history(client: TestClient, sample_consultation_payload: dict[str, object]) -> None:
	first = _create_consultation(client, sample_consultation_payload)
	second_payload = dict(sample_consultation_payload)
	second_payload["visit_date"] = "2026-04-10"
	second_payload["vitals"] = {
		"height_cm": 170,
		"weight_kg": 65,
		"head_circ_cm": 54,
		"temp_celsius": 100,
		"bp_mmhg": "118/78",
	}
	second_payload["key_questions"] = [{"question": "Fever since?", "answer": "3 days now"}]
	second_payload["diagnoses"] = [{"name": "Influenza", "selected": True, "is_custom": False}]
	second = _create_consultation(client, second_payload)
	patient_id = sample_consultation_payload["patient_id"]
	response = client.get(f"/api/v1/patient/{patient_id}/complaint/latest", params={"complaint": "High Fever"})
	assert response.status_code == 200
	body = response.json()
	assert body["consultation_id"] == second.json()["consultation_id"]
	assert len(body["follow_up_history"]) == 1
	first_snapshot = body["follow_up_history"][0]
	assert first_snapshot["consultation_id"] == first.json()["consultation_id"]
	assert first_snapshot["doctor_id"] == sample_consultation_payload["doctor_id"]
	assert isinstance(first_snapshot["chief_complaints"], list)
	assert isinstance(first_snapshot["vitals"], dict)
	assert isinstance(first_snapshot["key_questions"], list)
	assert isinstance(first_snapshot["diagnoses"], list)
	assert isinstance(first_snapshot["investigations"], list)
	assert isinstance(first_snapshot["medications"], list)
	assert isinstance(first_snapshot["procedures"], list)


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
