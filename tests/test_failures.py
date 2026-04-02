from __future__ import annotations

from unittest.mock import Mock, patch

from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import TimeoutError as RedisTimeoutError


# Proves a Redis connection failure on consultation creation returns HTTP 503.
def test_post_consultation_returns_503_when_redis_is_completely_down(client, sample_consultation_payload) -> None:
	with patch("pipeline.read.get_redis_client", side_effect=RedisConnectionError("down")):
		response = client.post("/api/v1/consultation", json=sample_consultation_payload)
	assert response.status_code == 503


# Proves a Redis timeout on consultation creation returns HTTP 504.
def test_post_consultation_returns_504_when_redis_times_out(client, sample_consultation_payload) -> None:
	with patch("pipeline.read.get_redis_client", side_effect=RedisTimeoutError("timeout")):
		response = client.post("/api/v1/consultation", json=sample_consultation_payload)
	assert response.status_code == 504


# Proves patient reads fail with HTTP 503 when Redis is unavailable.
def test_get_patient_returns_503_when_redis_is_completely_down(client, registered_patient) -> None:
	with patch("pipeline.read.get_redis_client", side_effect=RedisConnectionError("down")):
		response = client.get(f"/api/v1/patient/{registered_patient['patient_id']}")
	assert response.status_code == 503


# Proves the health endpoint returns degraded status when Redis ping fails.
def test_get_health_returns_503_and_degraded_status_when_redis_is_down(client) -> None:
	mock_client = Mock()
	mock_client.ping.side_effect = RedisConnectionError("down")
	with patch("api.routes.health.get_redis_client", return_value=mock_client):
		response = client.get("/health")
	assert response.status_code == 503
	assert response.json()["status"] == "degraded"


# Proves a missing consultation hash is handled as a graceful 404 instead of a crash.
def test_latest_consultation_returns_404_when_redis_read_returns_none(client, sample_consultation_payload) -> None:
	mock_client = Mock()
	mock_client.lindex.return_value = None
	with patch("pipeline.read.get_redis_client", return_value=mock_client):
		response = client.get(
			f"/api/v1/patient/{sample_consultation_payload['patient_id']}/complaint/latest",
			params={"complaint": "High Fever"},
		)
	assert response.status_code == 404


# Proves an idempotency lookup failure returns HTTP 503 instead of silently creating a duplicate.
def test_post_consultation_returns_503_when_idempotency_check_redis_is_down(client, sample_consultation_payload, unique_idempotency_key, redis_client) -> None:
	with patch("pipeline.write.get_redis_client", side_effect=RedisConnectionError("down")):
		response = client.post(
			"/api/v1/consultation",
			json=sample_consultation_payload,
			headers={"Idempotency-Key": unique_idempotency_key},
		)
	assert response.status_code == 503