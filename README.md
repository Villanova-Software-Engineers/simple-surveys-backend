# Simple Surveys Backend

A high-performance, asynchronous persistent backend service built with Python and FastAPI for experience sampling surveys (ESM), notification scheduling, anonymous response ingestion with optional photo attachments, and server-side adaptive LLM follow-up generation.

## Core Features

- **Anonymous Submissions**: Zero participant tracking or profiling. Every submission is an independent event with strict privacy guarantees.
- **Persistent Server Architecture**: Runs on a dedicated server process with in-process background scheduling (`APScheduler`).
- **Adaptive LLM Follow-Ups (Server-Side Ollama)**:
  - Generates dynamic, context-aware follow-up check-ins post-submission using an open-weights model hosted locally via **Ollama** (e.g. `llama3.2:3b`).
  - **100% On-Premise Privacy**: No cloud LLM APIs; survey text, coordinates, and photos remain strictly inside the server boundary.
  - **Zero PII**: Anonymity filter removes all device tokens, participant IDs, or network addresses prior to prompt synthesis.
  - **Schema-Constrained Generation**: Generated questions strictly conform to the `QuestionConfig` Pydantic schema (`rating_scale`, `single_choice`, `multiple_choice`, `text`, `numeric`).
  - **Multimodal Visual Context**: Automatically forwards uploaded camera photo bytes directly to Ollama for visual context synthesis.
  - **Multi-Round Lifecycle**: Governed by `max_followup_rounds`; automatically halts further rounds when limits are reached without requiring model state management.
- **Client-Side Question Gating Support**:
  - Passive storage and serving of `QuestionGatingRule` (supporting semantic matching via `openjev_matches` with confidence thresholds) to allow mobile clients to dynamically unhide questions on-device with zero typing latency.
- **Separation of Concerns**: Surveys and sampling schedules are completely decoupled. Surveys define questions, weights, notification copy, and adaptive follow-up rules; schedule configurations define windows and dispatch timing.
- **Fixed & Randomized Notification Dispatching**:
  - Fixed surveys (`first`, `last`) randomize within dedicated morning/night windows (e.g. 08:00–09:30, 20:30–22:00) or adhere to explicit times.
  - Intraday prompts are stratified and randomized with configurable minimum intervals.
  - Survey selection uses dynamic weights declared in each survey's definition.
- **Expiration Window ("Time to Complete")**:
  - Global `time_to_complete_minutes` window (e.g., 5 minutes) validates completion latency against notification dispatch time.
  - Expired submissions are still persisted for audit, but answers are autofilled empty (`[]`) with an audit reason message, and adaptive follow-ups are omitted.
- **Paired Response & Image Storage**:
  - JSON submission: `data/responses/{survey_id}/data/{timestamp}_resp_{id}.json`
  - Image photo: `data/responses/{survey_id}/images/{timestamp}_img_{id}.jpg`
- **Pluggable Storage Repositories**:
  - Local server filesystem persistence (`FileStorageRepository`).
  - Google Cloud Firestore & Cloud Storage integration (`FirebaseStorageRepository`).
  - Drop-in scaffold prepared for Microsoft Graph API OneDrive/SharePoint integration (`MSGraphStorageRepository`).

---

## Directory Structure

```text
Simple-Surveys-Backend/
├── app/
│   ├── api/                     # API routers (health, surveys, responses, notifications)
│   ├── crud/                    # Persistence (FileStorageRepository, FirebaseStorageRepository, MSGraphStorageRepository)
│   ├── schemas/                 # Pydantic DTO models (survey_config, survey_response, notification_config, common)
│   ├── services/                # Business logic
│   │   ├── dispatchers/         # Notification delivery (PushNotificationDispatcher)
│   │   ├── llm/                 # Adaptive LLM orchestration
│   │   │   ├── providers/       # LLM provider drivers (OllamaProvider)
│   │   │   ├── base.py          # BaseLLMProvider interface
│   │   │   ├── prompts.py       # Prompt engineering & strict anonymity context filters
│   │   │   └── service.py       # LLMService orchestration & error resilience
│   │   ├── scheduler_service.py # APScheduler daily dispatch planner & expiration evaluator
│   │   └── survey_selector.py   # Weighted sampling selector
│   ├── config.py                # Pydantic BaseSettings
│   ├── dependencies.py          # FastAPI dependency injection 
│   └── main.py                  # FastAPI application entrypoint & lifecycle
├── data/
│   ├── surveys/                 # Survey definition JSON files (e.g., daily_wellbeing_adaptive.json)
│   ├── schedule_config/         # Notification & sampling rules JSON
│   ├── responses/               # Organized JSON submissions and paired images
│   └── devices/                 # Registered push notification device tokens
├── docs/
│   ├── BACKEND_IMPLEMENTATION_PLAN.md
│   ├── LLM_FEATURE_IMPLEMENTATION_PLAN.md
│   └── FRONTEND_GATING_IMPLEMENTATION_PLAN.md
├── .env.example
├── requirements.txt
└── README.md
```

---

## Setup & Running

### 1. Prerequisites
- Python 3.15+
- [Ollama](https://ollama.com/) installed and running locally (for adaptive ESM follow-up questions)

### 2. Installation
```bash
# Clone the repository
git clone <repo-url>
cd Simple-Surveys-Backend

# Create and activate virtual environment
python -m venv env
# On Windows:
.\env\Scripts\activate
# On Linux/macOS:
source env/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Local LLM Setup (Ollama)
Ensure Ollama is running and pull your model:
```bash
# Pull the default adaptive follow-up model
ollama pull llama3.2:3b

# Ensure Ollama is running (default port 11434)
ollama serve
```

### 4. Environment Configuration
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```

Configuration variables:

| Variable | Default | Description |
|---|---|---|
| `HOST` | `0.0.0.0` | Host address to bind |
| `PORT` | `8000` | Port to listen on |
| `DEBUG` | `false` | Enable debug logging |
| `ALLOWED_ORIGINS` | `["*"]` | Allowed CORS origins |
| `STORAGE_BACKEND` | `file_storage` | Storage engine (`file_storage`, `firebase`, or `ms_graph`) |
| `DATA_DIR` | `data` | Base directory for file storage |
| `TIME_TO_COMPLETE_MINUTES` | `5` | Expiration window in minutes |
| `SCHEDULER_TIMEZONE` | `America/New_York` | Timezone for dispatch windows |
| `LLM_PROVIDER` | `ollama` | Provider backend (`ollama`) |
| `LLM_MODEL_NAME` | `llama3.2:3b` | Local Ollama model tag (`llama3.2:3b`, `moondreamb`, etc.) |
| `LOCAL_LLM_URL` | `http://localhost:11434` | Server-local Ollama API base URL |
| `LLM_TIMEOUT_SECONDS` | `2.5` | Timeout limit for LLM generation before graceful fallback |

### 5. Running the Server
```bash
python -m app.main
```

Once running:
- **API Base**: `http://localhost:8000/api`
- **Interactive Swagger Docs**: `http://localhost:8000/docs`
- **ReDoc**: `http://localhost:8000/redoc`

---

## API Endpoints

### System Health
- `GET /api/health`: System health and active survey count.

### Survey Definitions
- `GET /api/surveys`: Retrieve all active surveys (`?active_only=true|false`).
- `GET /api/surveys/{survey_id}`: Retrieve a specific survey definition.
- `POST /api/surveys`: Create and persist a new survey definition (`201 Created`).
- `PATCH /api/surveys/{survey_id}`: Update an existing survey definition (`200 OK`).
- `DELETE /api/surveys/{survey_id}`: Delete a survey definition (`200 OK`). Supports optional `delete_responses=true|false` and `clean_schedule_references=true|false`.

### Response Ingestion & Adaptive Follow-Ups
- `POST /api/responses`: Submit survey answers and optional camera photo.
  - Supports both `multipart/form-data` (form fields `data` and `image`) and `application/json`.
  - For active surveys with `adaptive_followup.enabled: true`, synchronously queries Ollama and includes `followup_survey` in the `201 Created` payload.
  - For follow-up rounds ($k \ge 1$), pass `parent_response_id` in the submission payload. Follow-ups automatically link and halt once `max_followup_rounds` is reached.
  - Returns `200 OK` with status `"EXPIRED"` and empty answers if submitted beyond `time_to_complete_minutes`.
- `GET /api/responses`: Retrieve persisted response records (`?survey_id={id}`).
- `GET /api/responses/{survey_id}/{response_id}`: Retrieve a specific response.
- `DELETE /api/responses/{survey_id}/{response_id}`: Delete a response record and optionally its associated photo (`?delete_image=true|false`).
- `GET /api/responses/{survey_id}/images/{filename}`: Download an uploaded response image.

### Notification Scheduling & Devices
- `GET /api/notifications/schedule`: Retrieve active sampling rules (`sampling_rules.json`).
- `POST /api/notifications/schedule`: Create or update (upsert) daily sampling rules and refresh daily schedule.
- `POST /api/notifications/devices`: Register an anonymous device push notification token.
- `GET /api/notifications/devices`: List registered devices.
- `DELETE /api/notifications/devices/{device_token}`: Unregister and delete a device token, stopping future notifications.
