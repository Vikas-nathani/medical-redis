"""Consultation model objects used by read/write pipelines."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class VitalsModel:
	height_cm: Optional[float] = None
	weight_kg: Optional[float] = None
	head_circ_cm: Optional[float] = None
	temp_celsius: Optional[float] = None
	bp_mmhg: Optional[str] = None


@dataclass
class KeyQuestionModel:
	question: str = ""
	answer: str = ""


@dataclass
class DiagnosisItemModel:
	name: str = ""
	selected: bool = True
	is_custom: bool = False


@dataclass
class InvestigationItemModel:
	name: str = ""
	selected: bool = True
	is_custom: bool = False


@dataclass
class MedicationItemModel:
	name: str = ""
	selected: bool = True
	is_custom: bool = False


@dataclass
class ProcedureItemModel:
	name: str = ""
	selected: bool = True
	is_custom: bool = False


@dataclass
class ConsultationModel:
	consultation_id: str = ""
	patient_id: str = ""
	doctor_id: str = ""
	visit_date: str = ""
	visit_number: int = 1
	chief_complaints: list = field(default_factory=list)
	vitals: Optional[VitalsModel] = None
	key_questions: list = field(default_factory=list)
	key_questions_ai_notes: str = ""
	diagnoses: list = field(default_factory=list)
	diagnoses_ai_notes: str = ""
	investigations: list = field(default_factory=list)
	investigations_ai_notes: str = ""
	medications: list = field(default_factory=list)
	medications_ai_notes: str = ""
	procedures: list = field(default_factory=list)
	procedures_ai_notes: str = ""
	advice: str = ""
	follow_up_date: str = ""
	advice_ai_notes: str = ""
	follow_up_history: list = field(default_factory=list)


# Backward-compatible alias for existing imports.
Consultation = ConsultationModel
