from __future__ import annotations

import threading

from fastapi.testclient import TestClient


def _create_thread_client_consultation(app, payload: dict[str, str], barrier: threading.Barrier, results: list[tuple[int, str]], index: int) -> None:
	barrier.wait()
	with TestClient(app) as thread_client:
		response = thread_client.post("/api/v1/consultation", json=payload)
		message = response.json()["message"]
		consultation_id = message.split()[1]
		results[index] = (response.status_code, consultation_id)


# Proves concurrent same-patient consultation writes produce unique consultation IDs with no duplicate inserts.
def test_twenty_simultaneous_consultation_writes_generate_unique_ids(client: TestClient, sample_consultation_payload: dict[str, str], registered_patient: dict[str, str], capsys) -> None:
	from main import app

	thread_count = 20
	barrier = threading.Barrier(thread_count)
	results: list[tuple[int, str]] = [(0, "") for _ in range(thread_count)]
	threads: list[threading.Thread] = []

	for index in range(thread_count):
		payload = dict(sample_consultation_payload)
		payload["questions"] = f"Concurrent question {index}"
		payload["symptoms_observed"] = f"Concurrent symptoms {index}"
		thread = threading.Thread(
			target=_create_thread_client_consultation,
			args=(app, payload, barrier, results, index),
		)
		threads.append(thread)
		thread.start()

	for thread in threads:
		thread.join()

	status_codes = [status_code for status_code, _ in results]
	consultation_ids = [consultation_id for _, consultation_id in results]
	assert status_codes == [201] * thread_count
	assert len(set(consultation_ids)) == thread_count
	print(f"stress_summary threads={thread_count} unique_ids={len(set(consultation_ids))}")