"""Redis connection factory with singleton behavior."""

from __future__ import annotations

from threading import Lock

from redis import Redis

from config.settings import REDIS_DB, REDIS_HOST, REDIS_PORT


_redis_client: Redis | None = None
_client_lock = Lock()


def get_redis_client() -> Redis:
	global _redis_client

	if _redis_client is not None:
		return _redis_client

	with _client_lock:
		if _redis_client is None:
			client = Redis(
				host=REDIS_HOST,
				port=REDIS_PORT,
				db=REDIS_DB,
				decode_responses=True,
			)
			client.ping()
			_redis_client = client

	return _redis_client
