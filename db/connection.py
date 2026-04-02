"""Redis connection factory with a shared module-level connection pool."""

from __future__ import annotations

from redis import ConnectionPool, Redis

from config.settings import REDIS_DB, REDIS_HOST, REDIS_PORT


_pool = ConnectionPool(  # Share one pool across threads so each request gets a safe connection handle.
	host=REDIS_HOST,
	port=REDIS_PORT,
	db=REDIS_DB,
	decode_responses=True,
	max_connections=20,
)


def get_redis_client() -> Redis:
	return Redis(connection_pool=_pool)  # Return a client bound to the shared pool instead of a singleton socket.
