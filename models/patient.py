"""Patient model and Redis serialization helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone


def _utc_now_iso() -> str:
	return datetime.now(timezone.utc).isoformat()


@dataclass
class Patient:
	patient_id: str
	name: str
	dob: str
	gender: str
	blood_type: str
	contact: str
	address: str
	created_at: str | None = None

	def __post_init__(self) -> None:
		if self.created_at is None:
			self.created_at = _utc_now_iso()

	def to_redis_dict(self) -> dict[str, str]:
		return {
			"patient_id": str(self.patient_id),
			"name": str(self.name),
			"dob": str(self.dob),
			"gender": str(self.gender),
			"blood_type": str(self.blood_type),
			"contact": str(self.contact),
			"address": str(self.address),
			"created_at": str(self.created_at or _utc_now_iso()),
		}
