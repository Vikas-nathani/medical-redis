# Medical Consultation System

[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Redis](https://img.shields.io/badge/Redis-5+-DC382D?logo=redis&logoColor=white)](https://redis.io/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

## Project Overview

Medical Consultation System is a FastAPI + Redis backend for storing structured medical consultation records. It is used by doctors and clinic staff through a frontend form, by the frontend team that consumes the REST API, and by a future AI/RAG pipeline that will retrieve consultation history for natural-language medical questions. Redis was chosen instead of a traditional database because the access patterns are simple, repetitive, and latency-sensitive: fast patient lookup, complaint-specific visit chains, and newest-first timelines. The design is intentionally different from a normal CRUD app because each consultation embeds capped prior history for AI retrieval, while the write path is atomic so concurrent submissions do not corrupt visit numbering or chain state.

## 1. Project Description

This backend stores patient demographics and consultation records in Redis with a schema designed for both operational lookups and downstream RAG usage. Doctors fill out a form on the frontend, the API validates and normalizes the payload, then writes the patient and consultation data into Redis using atomic Lua-based writes and indexed structures. The result is a backend that supports fast retrieval by patient, by complaint chain, and by time order, while also exposing a single consultation record with embedded prior context for AI systems.

## 2. High Level Design

### Architecture Diagram

```text
                         +----------------------+
                         |   Frontend (UI)      |
                         |  doctors / staff     |
                         +----------+-----------+
                                    |
                                    | HTTPS REST
                                    v
                    +----------------------------------+
                    |   GCP VM Boundary                |
                    |                                  |
                    |   +--------------------------+   |
                    |   | FastAPI Application      |   |
                    |   | - routing                |   |
                    |   | - validation             |   |
                    |   | - error handling         |   |
                    |   | - Lua script invocation  |   |
                    |   +------------+-------------+   |
                    |                |                 |
                    |                | Redis client    |
                    |                v                 |
                    |   +--------------------------+   |
                    |   | Redis in Docker          |   |
                    |   | - Hashes                |   |
                    |   | - Lists                 |   |
                    |   | - Sorted Sets           |   |
                    |   | - Atomic Lua scripts    |   |
                    |   +--------------------------+   |
                    |                                  |
                    +----------------------------------+

         Future RAG Pipeline
                  |
                  | natural-language query / retrieval
                  v
         +----------------------+
         | FastAPI Read Endpoints|
         +----------+-----------+
                    |
                    v
                  Redis
```

### Components

| Component | Role |
|---|---|
| FastAPI | REST API layer; handles routing, request validation, response formatting, and HTTP errors. |
| Redis | Primary data store; runs in Docker on the same GCP VM. |
| Pydantic | Validates request and response payloads and enforces field rules. |
| Lua Script | Executes the consultation write flow atomically inside Redis. |
| ConnectionPool | Provides thread-safe Redis access with shared pooled connections. |

## 3. Low Level Design

### 3a. Redis Data Structures

| Structure | Key Format | Fields / Members | Purpose |
|---|---|---|---|
| Patient Hash | `patient:{patient_id}` | `patient_id`, `name`, `dob`, `gender`, `blood_type`, `contact`, `address`, `created_at` | Stores patient demographics and registration metadata. Written once on patient registration. |
| Consultation Hash | `consultation:{patient_id}:{consultation_id}` | `consultation_id`, `patient_id`, `chief_complaint`, `complaint_slug`, `visit_number`, `visit_date`, `doctor_id`, `questions`, `symptoms_observed`, `medications`, `follow_up_date`, `follow_up_instruction`, `prev_consultation_id`, `follow_up_history` | Stores the full clinical record for each visit. Includes embedded history for the same complaint, capped at 10 snapshots. |
| Global Sorted Set | `patient:{patient_id}:consultations` | Member = consultation_id, Score = Unix timestamp in microseconds | Orders all consultations for a patient by time. Used for newest-first retrieval with pagination. |
| Complaint List | `patient:{patient_id}:complaint:{complaint_slug}` | Ordered consultation IDs | Tracks one complaint chain independently, such as the full fever chain or back-pain chain. |
| INCR Counter | `counter:{patient_id}:{complaint_slug}` | Integer counter | Guarantees unique sequential visit numbers even under concurrent requests. |

### 3b. Atomic Write Pipeline

The consultation write path is implemented as a Lua script so all Redis mutations happen atomically in a single server-side operation. That removes the race window that existed when the app previously read state in Python and then wrote state separately.

#### Why Lua

- Redis executes the script as one atomic unit.
- No other request can interleave between the read and write steps inside the script.
- The script keeps visit numbering, history construction, and indexing consistent.

#### The 7 atomic steps

1. `INCR` the per-patient/per-complaint counter.
2. Derive `consultation_id` as `cons_{complaint_slug}_{visit_num:03d}`.
3. `LINDEX` the complaint list tail to find the previous consultation ID.
4. `HGETALL` the previous consultation hash.
5. Build `follow_up_history` by appending the previous snapshot to the capped prior history.
6. `HSET` the new consultation record.
7. `ZADD` the global sorted set and `RPUSH` the complaint list.

#### Why `INCR` not `LLEN`

`LLEN` is only a snapshot of current list size. Two concurrent writers can both see the same length and compute the same next number. `INCR` is atomic inside Redis and guarantees a unique sequential integer, which is exactly what visit numbering needs.

#### History cap

`MAX_HISTORY_SNAPSHOTS = 10` limits embedded history growth. The oldest embedded snapshots are dropped first, while the full clinical records still remain in Redis as individual consultation hashes.

### 3c. Project File Structure

```text
medical-redis/
├── main.py                    - FastAPI app entry point, uvicorn config
├── requirements.txt           - Python dependencies
├── README.md                  - Project documentation
├── api/
│   ├── __init__.py
│   ├── exceptions.py          - Redis error handler, HTTP error mapping
│   ├── schemas.py             - Pydantic request/response models
│   └── routes/
│       ├── __init__.py
│       ├── consultation.py    - Consultation endpoints + slug generator
│       └── patient.py         - Patient registration endpoint
├── core/
│   └── logging.py             - Structured JSON logging setup
├── config/
│   └── settings.py            - Environment-based Redis settings
├── db/
│   └── connection.py         - Redis ConnectionPool, get_redis_client()
├── models/
│   ├── consultation.py        - Consultation domain model
│   └── patient.py             - Patient domain model
├── pipeline/
│   ├── read.py                - Redis read helpers with pagination
│   └── write.py               - Lua script + write functions
└── tests/
    └── test_write.py          - Integration-style write verification
```

### Folder Breakdown

| Folder / File | Responsibility |
|---|---|
| `main.py` | Creates the FastAPI app, registers routers, and starts uvicorn. |
| `requirements.txt` | Lists Python packages needed to run the service. |
| `api/exceptions.py` | Maps Redis failures to consistent HTTP responses. |
| `api/schemas.py` | Defines request and response models using Pydantic. |
| `api/routes/consultation.py` | Consultation endpoints plus slug generation and pagination. |
| `api/routes/patient.py` | Patient registration and patient lookup endpoints. |
| `core/logging.py` | Configures structured JSON logs using python-json-logger. |
| `config/settings.py` | Loads Redis host, port, DB, and log level from environment variables. |
| `db/connection.py` | Provides a shared Redis ConnectionPool and client factory. |
| `models/patient.py` | Patient domain model and Redis serialization helpers. |
| `models/consultation.py` | Consultation domain model and JSON serialization helpers. |
| `pipeline/read.py` | Redis read helpers for patient, consultation chain, and latest record queries. |
| `pipeline/write.py` | Atomic consultation writes and patient registration logic. |
| `tests/test_write.py` | Integration test that verifies complaint chains, history, and indexing behavior. |

### 3d. Key Design Decisions

| Decision | Why It Was Made |
|---|---|
| Every visit gets a new consultation ID even for the same illness | Each encounter is a distinct clinical event and must remain addressable independently. |
| `follow_up_history` embeds prior visit snapshots | A single consultation record can serve AI/RAG retrieval without extra joins or follow-up lookups. |
| History is capped at 10 entries | Prevents unbounded payload growth while preserving recent context. |
| Two parallel indexes are used | The global ZSET supports time-based patient timelines; the complaint List supports independent illness chains. |
| Different complaints never mix | Fever and back-pain are separate clinical threads and must remain independent for retrieval and analytics. |
| Lua script for atomic writes | Prevents race conditions and partial state updates under concurrent requests. |
| INCR counter for visit numbering | Guarantees uniqueness under concurrency; LLEN cannot do that safely. |
| ConnectionPool for thread safety | Multiple threads share a pool, but each request gets its own safe Redis connection handle. |
| Slug generation from `chief_complaint` | The frontend does not need to know Redis key naming rules; the backend derives clean key-safe slugs. |

## 4. API Endpoints

### Endpoint Summary

| Method | Path | Description | Request Body / Params | Response |
|---|---|---|---|---|
| POST | `/api/v1/patient` | Register a patient if the patient does not already exist. | JSON body: `patient_id`, `name`, `dob`, `gender`, `blood_type`, `contact`, `address` | `MessageResponse` with success message. |
| POST | `/api/v1/consultation` | Create a consultation, derive complaint slug, and store the record atomically. | JSON body: `patient_id`, `chief_complaint`, `visit_date` (optional), `doctor_id`, `questions`, `symptoms_observed`, `medications`, `follow_up_date`, `follow_up_instruction` | `MessageResponse` with generated consultation ID. |
| GET | `/api/v1/patient/{patient_id}` | Return one patient record. | Path param: `patient_id` | `PatientResponse`. |
| GET | `/api/v1/patient/{patient_id}/consultations` | Return a patient’s consultations newest-first with pagination. | Path param `patient_id`; query params `limit=20`, `offset=0` | `ConsultationListResponse` including `total_count`. |
| GET | `/api/v1/patient/{patient_id}/complaint/{slug}` | Return one complaint chain oldest-first with pagination. | Path params `patient_id`, `slug`; query params `limit=20`, `offset=0` | `ConsultationListResponse` including `total_count`. |
| GET | `/api/v1/patient/{patient_id}/complaint/{slug}/latest` | Return the latest consultation for one complaint chain. | Path params `patient_id`, `slug` | `ConsultationResponse`. |

### POST /api/v1/consultation Request Body

```json
{
  "patient_id": "P001",
  "chief_complaint": "Fever",
  "visit_date": "",
  "doctor_id": "D01",
  "questions": "Since when is the fever present?",
  "symptoms_observed": "Temperature 101 F, chills, body ache",
  "medications": "Paracetamol 500 mg",
  "follow_up_date": "2026-04-05",
  "follow_up_instruction": "Drink fluids and return if fever worsens"
}
```

### Validation Rules

| Field | Rule |
|---|---|
| `chief_complaint` | Minimum 3 characters after trimming. Must produce a non-empty valid slug. |
| `visit_date` | Must be `YYYY-MM-DD`. If empty, it is auto-set to today’s date. |
| `follow_up_date` | Must be `YYYY-MM-DD` and is required. |

## 5. Error Responses

| Status Code | Meaning | Typical Cause |
|---|---|---|
| 404 | Patient not found / Complaint not found | Missing patient record or empty complaint chain. |
| 422 | Validation error | Short complaint, invalid date, invalid slug. |
| 503 | Redis unavailable | Redis connection failure. |
| 504 | Redis timeout | Redis command timeout. |
| 500 | Redis operation failed / Internal error | Redis response error or unexpected failure. |

## 6. Installation and Setup

### 6a. Prerequisites

- Python 3.10+
- Docker
- pip
- git

### 6b. Clone and Install

```bash
git clone <repo-url>
cd medical-redis
pip install -r requirements.txt
```

### 6c. Start Redis in Docker

```bash
docker run -d --name redis-medical -p 6379:6379 redis:latest
```

### 6d. Environment Variables

| Variable | Default | Purpose |
|---|---|---|
| `REDIS_HOST` | `localhost` | Redis hostname or IP address. |
| `REDIS_PORT` | `6379` | Redis TCP port. |
| `REDIS_DB` | `0` | Redis logical database index. |
| `LOG_LEVEL` | `INFO` | Logging verbosity. |

Set them like this:

```bash
export REDIS_HOST=localhost
export REDIS_PORT=6379
export REDIS_DB=0
export LOG_LEVEL=INFO
```

### 6e. Run the Server

```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

For production, keep a single worker unless the Redis client setup is redesigned for multi-process safety:

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 1
```

### 6f. Access API Documentation

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## 7. Usage Examples

### 7.1 Create a Patient

```bash
curl -X POST http://localhost:8000/api/v1/patient \
  -H "Content-Type: application/json" \
  -d '{
    "patient_id": "P001",
    "name": "Arjun Mehta",
    "dob": "1988-04-12",
    "gender": "male",
    "blood_type": "O+",
    "contact": "9999999999",
    "address": "Hyderabad"
  }'
```

### 7.2 Create a Consultation

```bash
curl -X POST http://localhost:8000/api/v1/consultation \
  -H "Content-Type: application/json" \
  -d '{
    "patient_id": "P001",
    "chief_complaint": "Fever",
    "visit_date": "",
    "doctor_id": "D01",
    "questions": "Since when is the fever present? Any chills?",
    "symptoms_observed": "Temperature 101 F, body ache, chills",
    "medications": "Paracetamol 500 mg",
    "follow_up_date": "2026-04-05",
    "follow_up_instruction": "Hydrate well and return if symptoms worsen"
  }'
```

### 7.3 Get a Patient

```bash
curl http://localhost:8000/api/v1/patient/P001
```

### 7.4 Get All Consultations for a Patient

```bash
curl "http://localhost:8000/api/v1/patient/P001/consultations?limit=20&offset=0"
```

### 7.5 Get a Complaint Chain

```bash
curl "http://localhost:8000/api/v1/patient/P001/complaint/fever?limit=20&offset=0"
```

### 7.6 Get the Latest Consultation for a Complaint

```bash
curl http://localhost:8000/api/v1/patient/P001/complaint/fever/latest
```

## 8. Roadmap

| Item | Status | Notes |
|---|---|---|
| GCP Firewall | PENDING | Open port 8000 so the frontend can reach the VM. |
| Systemd service | PENDING | Run FastAPI as a background service that survives terminal closure. |
| Redis persistence | PENDING | Enable RDB snapshots or AOF so data survives VM restarts. |
| Authentication | PENDING | Add API key or JWT before frontend access. |
| RAG Pipeline | PENDING | Embed consultation records into a vector database and connect an LLM for natural-language queries. |
| Multi-worker support | PENDING | Current setup requires `workers=1`; process-safe Redis handling is needed before horizontal scaling. |

## 9. Known Limitations

- `workers=1` is required today because the registered Lua script handle is process-local and the current Redis client setup is not designed for multi-process sharing.
- Redis is the only data store, so there is no SQL-backed audit layer or relational reporting store.
- Authentication is not implemented yet, so deployment should be behind a firewall or VPN.
- Embedded history is capped at 10 snapshots, so older snapshots are dropped from the consultation hash even though the full consultation records still remain in Redis.

## 10. Tech Stack

| Component | Technology | Version | Purpose |
|---|---|---|---|
| Language | Python | 3.10+ | Backend application runtime. |
| Web Framework | FastAPI | 0.110+ | REST API layer and request validation. |
| Data Store | Redis | 5+ | Primary storage and indexing engine. |
| Redis Client | redis-py | 5+ | Python client library for Redis access. |
| Validation | Pydantic | 2+ | Request and response schema validation. |
| Server | Uvicorn | 0.29+ | ASGI server for running FastAPI. |
| Logging | python-json-logger | 2.0.7+ | Structured JSON logging output. |
| Containerization | Docker | Latest | Runs Redis locally on the same VM. |

## Operational Notes

- Start Redis before launching the API server.
- Keep the API behind a firewall or private network until authentication is added.
- Use the provided pagination parameters for list endpoints once consultation volume grows.
- If you change the Lua script, restart the app process so the registered script handle is recreated cleanly.

## Summary

This system is optimized for fast retrieval, deterministic clinical chains, and AI-friendly consultation context. Its Redis schema is intentionally specialized: hashes store the records, lists preserve complaint-specific order, and a sorted set supports global patient timelines. The atomic Lua write path is the key correctness mechanism that protects the system from concurrency bugs and data corruption.