"""Application settings for Redis connectivity."""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


load_dotenv()


def _get_int_env(name: str, default: int) -> int:
	raw_value = os.getenv(name)
	if raw_value is None or raw_value == "":
		return default
	return int(raw_value)


@dataclass(frozen=True)
class RedisSettings:
	redis_host: str
	redis_port: int
	redis_db: int


def get_settings() -> RedisSettings:
	return RedisSettings(
		redis_host=os.getenv("REDIS_HOST", "localhost"),
		redis_port=_get_int_env("REDIS_PORT", 6379),
		redis_db=_get_int_env("REDIS_DB", 0),
	)


settings = get_settings()

REDIS_HOST = settings.redis_host
REDIS_PORT = settings.redis_port
REDIS_DB = settings.redis_db
