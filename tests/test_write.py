"""Repeatable integration-style test for Redis write behavior."""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from db.connection import get_redis_client
from models.consultation import Consultation
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

	fever_visit_1 = Consultation(
		consultation_id="cons_fever_001",
		patient_id=patient_id,
		chief_complaint="Fever",
		complaint_slug="fever",
		visit_number=1,
		visit_date="2026-04-01",
		doctor_id="dr_sen",
		questions="Duration of fever? Any chills? Any travel history?",
		symptoms_observed="Temperature 101.3 F, body ache, mild headache",
		medications="Paracetamol 500 mg as needed",
		follow_up_date="2026-04-03",
		follow_up_instruction="Hydrate well, monitor temperature, return if fever persists",
		prev_consultation_id="",
		follow_up_history=[],
	)
	write_consultation(fever_visit_1)

	fever_visit_2 = Consultation(
		consultation_id="cons_fever_002",
		patient_id=patient_id,
		chief_complaint="Fever",
		complaint_slug="fever",
		visit_number=1,
		visit_date="2026-04-02",
		doctor_id="dr_sen",
		questions="Any improvement since last visit? Any rash or cough?",
		symptoms_observed="Temperature down to 99.8 F, improved body ache",
		medications="Continue paracetamol if needed, ORS",
		follow_up_date="2026-04-05",
		follow_up_instruction="Continue observation, follow up if symptoms worsen",
		prev_consultation_id="",
		follow_up_history=[],
	)
	write_consultation(fever_visit_2)

	back_pain_visit_1 = Consultation(
		consultation_id="cons_backpain_001",
		patient_id=patient_id,
		chief_complaint="Back pain",
		complaint_slug="back-pain",
		visit_number=1,
		visit_date="2026-04-02",
		doctor_id="dr_rao",
		questions="Is the pain radiating? Any lifting injury?",
		symptoms_observed="Lower back tenderness, no neurological deficit",
		medications="Ibuprofen after meals for 3 days",
		follow_up_date="2026-04-06",
		follow_up_instruction="Rest, use warm compress, return if numbness develops",
		prev_consultation_id="",
		follow_up_history=[],
	)
	write_consultation(back_pain_visit_1)

	patient_hash = client.hgetall(patient_key(patient_id))
	assert patient_hash, "patient:1 hash should exist"
	assert patient_hash["name"] == "Arjun Mehta"

	assert client.zcard(global_zset_key(patient_id)) == 3
	assert client.llen(complaint_list_key(patient_id, "fever")) == 2
	assert client.llen(complaint_list_key(patient_id, "back-pain")) == 1

	fever_two = client.hgetall(consultation_key(patient_id, "cons_fever_002"))
	assert fever_two, "cons_fever_002 should exist"
	follow_up_history = fever_two["follow_up_history"]
	assert follow_up_history != ""
	assert len(json.loads(follow_up_history)) == 1
	assert json.loads(follow_up_history)[0]["consultation_id"] == "cons_fever_001"

	backpain_one = client.hgetall(consultation_key(patient_id, "cons_backpain_001"))
	assert backpain_one, "cons_backpain_001 should exist"
	assert json.loads(backpain_one["follow_up_history"]) == []

	print("[test] all assertions passed")


if __name__ == "__main__":
	run()
