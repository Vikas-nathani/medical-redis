"""Repeatable integration-style test for Redis write behavior."""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from db.connection import get_redis_client
from models.consultation import ConsultationModel
from models.patient import Patient
from pipeline.write import (
	complaint_list_key,
	consultation_key,
	global_zset_key,
	patient_key,
	write_consultation,
	write_patient,
)


def _delete_patient_keys(client, patient_id: str) -> None:
	keys_to_delete: set[str] = set()
	patterns = [
		patient_key(patient_id),
		f"{patient_key(patient_id)}:*",
		f"consultation:{patient_id}:*",
	]

	for pattern in patterns:
		for key in client.scan_iter(match=pattern):
			keys_to_delete.add(key)

	if keys_to_delete:
		client.delete(*sorted(keys_to_delete))

	print(f"[test] cleared {len(keys_to_delete)} keys for patient {patient_id}")


def run() -> None:
	client = get_redis_client()
	patient_id = "1"

	_delete_patient_keys(client, patient_id)

	patient = Patient(
		patient_id=patient_id,
		name="Arjun Mehta",
		dob="1988-04-12",
		gender="male",
		blood_type="O+",
		contact="+91-9876543210",
		address="12 Lake View Road, Pune, Maharashtra",
	)
	write_patient(patient)

	fever_visit_1 = ConsultationModel(
		patient_id=patient_id,
		visit_date="2026-04-01",
		chief_complaints=["Fever"],
		vitals={"height_cm": 170, "weight_kg": 65, "temp_celsius": 101, "bp_mmhg": "120/80"},
		key_questions=[{"question": "Duration?", "answer": "2 days"}],
		key_questions_ai_notes="Initial fever assessment",
		diagnoses=[{"name": "Viral Fever", "selected": True, "is_custom": False}],
		diagnoses_ai_notes="Likely viral etiology",
		investigations=[{"name": "CBC", "selected": True, "is_custom": False}],
		investigations_ai_notes="CBC baseline",
		medications=[{"name": "Paracetamol", "selected": True, "is_custom": False}],
		medications_ai_notes="Symptomatic treatment",
		procedures=[{"name": "Hydration", "selected": True, "is_custom": False}],
		procedures_ai_notes="Hydration advised",
		advice="Rest",
		follow_up_date="2026-04-03",
		advice_ai_notes="Review in 2 days",
	)
	first_id = write_consultation(fever_visit_1)

	fever_visit_2 = ConsultationModel(
		patient_id=patient_id,
		visit_date="2026-04-02",
		chief_complaints=["Fever"],
		vitals={"height_cm": 170, "weight_kg": 65, "temp_celsius": 99.8, "bp_mmhg": "118/78"},
		key_questions=[{"question": "Improvement?", "answer": "Yes"}],
		key_questions_ai_notes="Improving",
		diagnoses=[{"name": "Viral Fever", "selected": True, "is_custom": False}],
		diagnoses_ai_notes="Continue conservative management",
		investigations=[{"name": "CBC", "selected": True, "is_custom": False}],
		investigations_ai_notes="Stable",
		medications=[{"name": "Paracetamol", "selected": True, "is_custom": False}],
		medications_ai_notes="Continue",
		procedures=[{"name": "Hydration", "selected": True, "is_custom": False}],
		procedures_ai_notes="Continue",
		advice="Continue rest",
		follow_up_date="2026-04-05",
		advice_ai_notes="Return if worse",
	)
	second_id = write_consultation(fever_visit_2)

	back_pain_visit_1 = ConsultationModel(
		patient_id=patient_id,
		visit_date="2026-04-02",
		chief_complaints=["Back pain"],
		vitals=None,
		key_questions=[{"question": "Radiating pain?", "answer": "No"}],
		key_questions_ai_notes="Mechanical pain pattern",
		diagnoses=[{"name": "Lumbar strain", "selected": True, "is_custom": False}],
		diagnoses_ai_notes="Likely strain",
		investigations=[],
		investigations_ai_notes="",
		medications=[{"name": "Ibuprofen", "selected": True, "is_custom": False}],
		medications_ai_notes="After meals",
		procedures=[{"name": "Warm compress", "selected": True, "is_custom": False}],
		procedures_ai_notes="Conservative management",
		advice="Rest and avoid lifting",
		follow_up_date="2026-04-06",
		advice_ai_notes="Return if numbness develops",
	)
	back_pain_id = write_consultation(back_pain_visit_1)

	patient_hash = client.hgetall(patient_key(patient_id))
	assert patient_hash, "patient:1 hash should exist"
	assert patient_hash["name"] == "Arjun Mehta"

	assert client.zcard(global_zset_key(patient_id)) == 3
	assert client.llen(complaint_list_key(patient_id, "fever")) == 2
	assert client.llen(complaint_list_key(patient_id, "back-pain")) == 1

	fever_two = client.hgetall(consultation_key(patient_id, second_id))
	assert fever_two, "second fever consultation should exist"
	assert json.loads(fever_two["chief_complaints"]) == ["Fever"]
	assert isinstance(json.loads(fever_two["vitals"]), dict)
	assert isinstance(json.loads(fever_two["key_questions"]), list)
	assert isinstance(json.loads(fever_two["diagnoses"]), list)
	assert isinstance(json.loads(fever_two["investigations"]), list)
	assert isinstance(json.loads(fever_two["medications"]), list)
	assert isinstance(json.loads(fever_two["procedures"]), list)

	follow_up_history = json.loads(fever_two["follow_up_history"])
	assert len(follow_up_history) == 1
	assert follow_up_history[0]["consultation_id"] == first_id
	assert isinstance(follow_up_history[0]["chief_complaints"], list)
	assert isinstance(follow_up_history[0]["vitals"], dict)
	assert isinstance(follow_up_history[0]["key_questions"], list)
	assert isinstance(follow_up_history[0]["diagnoses"], list)
	assert isinstance(follow_up_history[0]["investigations"], list)
	assert isinstance(follow_up_history[0]["medications"], list)
	assert isinstance(follow_up_history[0]["procedures"], list)

	backpain_one = client.hgetall(consultation_key(patient_id, back_pain_id))
	assert backpain_one, "back-pain consultation should exist"
	assert json.loads(backpain_one["follow_up_history"]) == []

	print("[test] all assertions passed")


if __name__ == "__main__":
	run()
