"""Pydantic schemas for the Medical Consultation API."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


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


class MessageResponse(BaseModel):
    message: str