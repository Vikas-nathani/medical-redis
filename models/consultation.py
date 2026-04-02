"""Consultation model and Redis serialization helpers."""

from __future__ import annotations

import json
from dataclasses import dataclass, field

@dataclass
class Consultation:
	consultation_id: str
	patient_id: str
	chief_complaint: str
	complaint_slug: str
	visit_number: int
	visit_date: str
	doctor_id: str
	questions: str
	symptoms_observed: str
	medications: str
	follow_up_date: str
	follow_up_instruction: str
	prev_consultation_id: str
	follow_up_history: list[dict] = field(default_factory=list)

	def to_redis_dict(self) -> dict[str, str]:
		return {
			"consultation_id": str(self.consultation_id),
			"patient_id": str(self.patient_id),
			"chief_complaint": str(self.chief_complaint),
			"complaint_slug": str(self.complaint_slug),
			"visit_number": str(self.visit_number),
			"visit_date": str(self.visit_date),
			"doctor_id": str(self.doctor_id),
			"questions": str(self.questions),
			"symptoms_observed": str(self.symptoms_observed),
			"medications": str(self.medications),
			"follow_up_date": str(self.follow_up_date),
			"follow_up_instruction": str(self.follow_up_instruction),
			"prev_consultation_id": str(self.prev_consultation_id),
			"follow_up_history": json.dumps(self.follow_up_history),
		}

	@classmethod
	def from_redis_dict(cls, data: dict[str, str]) -> "Consultation":
		follow_up_history_raw = data.get("follow_up_history", "[]")
		if follow_up_history_raw in (None, ""):
			follow_up_history: list[dict] = []
		else:
			follow_up_history = json.loads(follow_up_history_raw)

		return cls(
			consultation_id=data.get("consultation_id", ""),
			patient_id=data.get("patient_id", ""),
			chief_complaint=data.get("chief_complaint", ""),
			complaint_slug=data.get("complaint_slug", ""),
			visit_number=int(data.get("visit_number", 0)),
			visit_date=data.get("visit_date", ""),
			doctor_id=data.get("doctor_id", ""),
			questions=data.get("questions", ""),
			symptoms_observed=data.get("symptoms_observed", ""),
			medications=data.get("medications", ""),
			follow_up_date=data.get("follow_up_date", ""),
			follow_up_instruction=data.get("follow_up_instruction", ""),
			prev_consultation_id=data.get("prev_consultation_id", ""),
			follow_up_history=follow_up_history,
		)
