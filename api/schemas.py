"""Pydantic schemas for the Medical Consultation API."""

from __future__ import annotations

from datetime import date
from typing import Optional

from pydantic import BaseModel, ConfigDict, field_validator


class PatientCreateRequest(BaseModel):
    patient_id: str
    name: str
    dob: str
    gender: str
    blood_type: str
    contact: str
    address: str


class PatientResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    patient_id: str
    name: str
    dob: str
    gender: str
    blood_type: str
    contact: str
    address: str
    created_at: str


class VitalsSchema(BaseModel):
    height_cm: Optional[float] = None
    weight_kg: Optional[float] = None
    head_circ_cm: Optional[float] = None
    temp_celsius: Optional[float] = None
    bp_mmhg: Optional[str] = None


class KeyQuestionSchema(BaseModel):
    question: str
    answer: str


class DiagnosisItemSchema(BaseModel):
    name: str
    selected: bool = True
    is_custom: bool = False


class InvestigationItemSchema(BaseModel):
    name: str
    selected: bool = True
    is_custom: bool = False


class MedicationItemSchema(BaseModel):
    name: str
    selected: bool = True
    is_custom: bool = False


class ProcedureItemSchema(BaseModel):
    name: str
    selected: bool = True
    is_custom: bool = False


class ConsultationRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    patient_id: str
    complaint_chain: str
    visit_date: Optional[str] = ""

    chief_complaints: list[str]

    vitals: Optional[VitalsSchema] = None

    key_questions: Optional[list[KeyQuestionSchema]] = []
    key_questions_ai_notes: Optional[str] = ""

    diagnoses: Optional[list[DiagnosisItemSchema]] = []
    diagnoses_ai_notes: Optional[str] = ""

    investigations: Optional[list[InvestigationItemSchema]] = []
    investigations_ai_notes: Optional[str] = ""

    medications: Optional[list[MedicationItemSchema]] = []
    medications_ai_notes: Optional[str] = ""

    procedures: Optional[list[ProcedureItemSchema]] = []
    procedures_ai_notes: Optional[str] = ""

    advice: Optional[str] = ""
    follow_up_date: Optional[str] = ""
    advice_ai_notes: Optional[str] = ""

    @field_validator("complaint_chain")
    @classmethod
    def validate_complaint_chain(cls, v: str) -> str:
        v = v.strip().lower()
        if not v:
            raise ValueError("complaint_chain must not be empty")
        if " " in v:
            raise ValueError(
                "complaint_chain must be a slug (e.g. 'fever' or "
                "'high-fever'), not raw text with spaces"
            )
        return v

    @field_validator("chief_complaints")
    @classmethod
    def validate_complaints(cls, v: list[str]) -> list[str]:
        if not v or len(v) == 0:
            raise ValueError("At least one chief complaint is required")
        for c in v:
            if len(c.strip()) < 3:
                raise ValueError(f"Each complaint must be at least 3 characters: '{c}'")
        return v

    @field_validator("visit_date", "follow_up_date", mode="before")
    @classmethod
    def validate_dates(cls, v: str | None) -> str:
        if not v:
            return ""
        try:
            date.fromisoformat(v)
        except ValueError as exc:
            raise ValueError("Date must be in YYYY-MM-DD format") from exc
        return v


class FollowUpHistoryEntrySchema(BaseModel):
    consultation_id: str
    visit_number: int
    visit_date: str
    chief_complaints: list[str] = []
    vitals: Optional[VitalsSchema] = None
    key_questions: list[KeyQuestionSchema] = []
    key_questions_ai_notes: str = ""
    diagnoses: list[DiagnosisItemSchema] = []
    diagnoses_ai_notes: str = ""
    investigations: list[InvestigationItemSchema] = []
    investigations_ai_notes: str = ""
    medications: list[MedicationItemSchema] = []
    medications_ai_notes: str = ""
    procedures: list[ProcedureItemSchema] = []
    procedures_ai_notes: str = ""
    advice: str = ""
    follow_up_date: str = ""
    advice_ai_notes: str = ""


class ConsultationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    consultation_id: str
    patient_id: str
    visit_date: str
    visit_number: int
    chief_complaints: list[str] = []
    vitals: Optional[VitalsSchema] = None
    key_questions: list[KeyQuestionSchema] = []
    key_questions_ai_notes: str = ""
    diagnoses: list[DiagnosisItemSchema] = []
    diagnoses_ai_notes: str = ""
    investigations: list[InvestigationItemSchema] = []
    investigations_ai_notes: str = ""
    medications: list[MedicationItemSchema] = []
    medications_ai_notes: str = ""
    procedures: list[ProcedureItemSchema] = []
    procedures_ai_notes: str = ""
    advice: str = ""
    follow_up_date: str = ""
    advice_ai_notes: str = ""
    follow_up_history: list[FollowUpHistoryEntrySchema] = []


class MessageResponse(BaseModel):
    message: str
