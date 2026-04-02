"""Pydantic schemas for the Medical Consultation API."""

from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PatientCreateRequest(BaseModel):
    patient_id: str
    name: str
    dob: str
    gender: str
    blood_type: str
    contact: str
    address: str


class ConsultationCreateRequest(BaseModel):
    patient_id: str
    chief_complaint: str
    visit_date: str = ""
    doctor_id: str
    questions: str
    symptoms_observed: str
    medications: str
    follow_up_date: str
    follow_up_instruction: str

    @field_validator("chief_complaint")
    @classmethod
    def validate_chief_complaint(cls, value: str) -> str:
        cleaned = value.strip()
        if len(cleaned) < 3:
            raise ValueError("chief_complaint must be at least 3 characters")
        return cleaned

    @field_validator("visit_date", mode="before")
    @classmethod
    def validate_visit_date(cls, value: str | None) -> str:
        if value is None or (isinstance(value, str) and value.strip() == ""):
            return date.today().isoformat()
        if not isinstance(value, str):
            raise ValueError("visit_date must be a string in YYYY-MM-DD format")
        try:
            date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError("visit_date must be in YYYY-MM-DD format") from exc
        return value

    @field_validator("follow_up_date")
    @classmethod
    def validate_follow_up_date(cls, value: str) -> str:
        try:
            date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError("follow_up_date must be in YYYY-MM-DD format") from exc
        return value


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


class ConsultationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

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
    follow_up_history: list[dict[str, Any]] = Field(default_factory=list)


class ConsultationListResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    consultations: list[ConsultationResponse]
    total_count: int


class MessageResponse(BaseModel):
    message: str