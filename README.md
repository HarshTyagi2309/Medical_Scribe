# Medical Scribe AI

AI-powered medical scribe application that converts doctor-patient audio conversations into structured clinical records.

The project combines audio transcription, clinical information extraction, encrypted storage, authentication, audit logging, consultation history, and Langfuse observability in one end-to-end workflow.

> This project implements HIPAA-aware security safeguards, but it should not be described as HIPAA compliant without the required production infrastructure, policies, BAAs, risk assessment, operational controls, and legal/compliance review.

---

## Project Workflow

```text
Doctor / Patient Audio
        ↓
Audio Validation
        ↓
Speech-to-Text Transcription
        ↓
Transcript Formatting
        ↓
Clinical Information Extraction
        ↓
Encrypted Audio + Encrypted Clinical Data
        ↓
SQLite Database
        ↓
Consultation History / Edit / Delete
        ↓
Langfuse Observability
```

---

## Main Features

- Doctor login using username/password authentication
- JWT-based protected API access
- Doctor and Admin role-based access control
- Audio upload and recording support
- Supported audio formats: WAV, MP3, M4A, OGG, WEBM
- Maximum audio size validation: 25 MB
- Duplicate consultation detection using SHA-256 hashing
- Groq-based primary transcription
- Transcription fallback models
- Transcript cleanup and formatting
- AI-based structured clinical extraction
- Strict no-invention clinical extraction rules
- Automatic consultation saving
- Encrypted clinical data storage
- Encrypted audio storage
- Consultation history and search
- Doctor correction/edit workflow
- Doctor-only record deletion
- PHI-safe audit logging
- Langfuse tracing for the AI pipeline
- Provider/model latency, token and cost tracking where available
- Security headers and restricted CORS configuration
- Generic error responses for safer failure handling

---

## Clinical Data Extracted

The system can extract the following information when it is explicitly present in the consultation:

- Patient name
- Chief complaint
- Symptoms
- Blood pressure
- Heart rate
- Temperature
- Oxygen saturation
- Diagnosis
- Medications
  - Name
  - Dosage
  - Frequency
  - Duration
  - Route
- Recommended tests
- Doctor instructions
- Follow-up information

The extraction prompt is designed to avoid inventing clinical information. Missing information is returned as empty/null instead of being guessed.

---

## Technology Stack

### Backend

- Python
- FastAPI
- Uvicorn
- SQLAlchemy
- SQLite

### Frontend

- Streamlit

### AI / LLM

- Groq API
- Whisper transcription models
- GPT-OSS / Qwen models through Groq
- OpenAI emergency fallback support

### Authentication & Security

- JWT
- PyJWT
- Argon2 password hashing through `pwdlib`
- Encrypted stored clinical data
- Encrypted stored audio
- Role-based authorization
- Audit logging

### Observability

- Langfuse

---

## AI Model Strategy

### Transcription

Primary:

```text
whisper-large-v3
```

Groq fallback:

```text
whisper-large-v3-turbo
```

Emergency OpenAI fallback:

```text
gpt-transcribe
```

### Clinical Extraction

Primary:

```text
openai/gpt-oss-20b
```

Groq fallback:

```text
qwen/qwen3.6-27b
```

Emergency OpenAI fallback:

```text
gpt-4.1-mini
```

---

## Role-Based Access

| Action | Doctor | Admin |
|---|---:|---:|
| Login | ✅ | ✅ |
| Process consultation | ✅ | ❌ |
| View records | ✅ | ✅ |
| Open record | ✅ | ✅ |
| Edit record | ✅ | ❌ |
| Delete record | ✅ | ❌ |

Admin access is intentionally read-only.

---

## API Endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/` | API home |
| GET | `/health` | Health check |
| POST | `/auth/login` | User login |
| POST | `/transcribe` | Audio transcription |
| POST | `/extract` | Clinical extraction |
| POST | `/process-consultation` | Full consultation pipeline |
| GET | `/records` | Consultation history/search |
| GET | `/records/{id}` | Open consultation |
| PUT | `/records/{id}` | Doctor correction |
| DELETE | `/records/{id}` | Doctor-only deletion |

---

## Project Structure

```text
Medical_Scribe/
│
├── backend/
│   ├── audit_service.py
│   ├── clinical_extractor.py
│   ├── database.py
│   ├── langfuse_service.py
│   ├── login_service.py
│   ├── main.py
│   ├── models.py
│   ├── security.py
│   ├── transcription.py
│   ├── user_auth.py
│   └── __init__.py
│
├── frontend/
│   ├── app.py
│   └── handsfree_recorder.py
│
├── data/
├── recordings/
├── .env.example
├── .gitignore
├── requirements.txt
└── README.md
```

Runtime clinical data, recordings, audit logs, database files, and secrets are intentionally excluded from version control where configured.

---

## Local Setup

### 1. Clone the repository

```bash
git clone https://github.com/HarshTyagi2309/Medical_Scribe.git
cd Medical_Scribe
```

### 2. Create a virtual environment

Windows:

```powershell
python -m venv venv
.\venv\Scripts\activate
```

### 3. Install dependencies

```powershell
pip install -r requirements.txt
```

### 4. Configure environment variables

Copy `.env.example` to `.env` and configure the required credentials locally.

Typical configuration includes:

```env
GROQ_API_KEY=
OPENAI_API_KEY=

LANGFUSE_PUBLIC_KEY=
LANGFUSE_SECRET_KEY=
LANGFUSE_BASE_URL=https://cloud.langfuse.com
LANGFUSE_CAPTURE_CLINICAL_DATA=false

FASTAPI_URL=http://127.0.0.1:8001

DOCTOR_USERNAME=
DOCTOR_PASSWORD=
ADMIN_USERNAME=
ADMIN_PASSWORD=

JWT_SECRET_KEY=
DATA_ENCRYPTION_KEY=

DATA_RETENTION_DAYS=0
```

Never commit `.env` or real API keys to GitHub.

---

## Run the Application

### Start FastAPI

From the project root:

```powershell
.\venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8001
```

FastAPI will be available at:

```text
http://127.0.0.1:8001
```

API documentation:

```text
http://127.0.0.1:8001/docs
```

### Start Streamlit

Open another terminal:

```powershell
.\venv\Scripts\python.exe -m streamlit run frontend\app.py
```

Then open the Streamlit URL shown in the terminal.

---

## Langfuse Observability

The application sends PHI-safe observability metadata to Langfuse when configured.

A normal consultation trace contains observations such as:

```text
medical-consultation
├── audio-transcription-primary
├── transcript-formatting
└── clinical-extraction-primary
```

Langfuse can be used to inspect:

- Model usage
- Latency
- Token usage
- Cost metadata
- Errors
- Fallback usage
- Consultation pipeline traces

For safer defaults:

```env
LANGFUSE_CAPTURE_CLINICAL_DATA=false
```

This prevents intentionally sending clinical transcript/content through the application's Langfuse metadata configuration.

---

## Security Safeguards

The project currently includes application-level safeguards such as:

- JWT authentication
- Argon2 password hashing
- Role-based authorization
- Encrypted data storage
- Encrypted audio files
- PHI-safe audit events
- Restricted CORS methods and headers
- Security response headers
- API error sanitization
- Audio type and size validation
- Duplicate detection
- `.env` exclusion from Git

Production healthcare deployment would additionally require controls such as HTTPS/TLS, secure cloud configuration, access management, backup strategy, key management, monitoring, retention policies, incident response, BAAs where required, and formal compliance/risk review.

---

## Current Status

The local end-to-end application is implemented with:

- Authentication ✅
- JWT authorization ✅
- Audio transcription ✅
- Transcript formatting ✅
- Clinical extraction ✅
- Automatic encrypted storage ✅
- Consultation history ✅
- Doctor correction ✅
- Doctor-only delete ✅
- Audit logging ✅
- Langfuse tracing ✅
- Failure handling tests ✅

Public cloud deployment is not included in the current local project state.

---

## Author

**Harsh Tyagi**

AI Engineer | Generative AI | LLM Applications | FastAPI | Langfuse
