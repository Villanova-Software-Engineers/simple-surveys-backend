# Simple Surveys Backend

A high-performance, asynchronous persistent backend service built with Python and FastAPI for experience sampling surveys (ESM), notification scheduling, anonymous response ingestion with optional photo attachments, and server-side adaptive LLM follow-up generation.

---

## Core Features

- **Anonymous Submissions & Strict Privacy**: Zero participant tracking, device fingerprinting, or profiling. Every submission is an independent event with strict privacy guarantees.
- **Persistent Server Architecture**: Runs on a dedicated server process with in-process background scheduling (`APScheduler`) and async I/O.
- **Adaptive LLM Follow-Ups (Server-Side Ollama)**:
  - Generates dynamic, context-aware follow-up check-ins post-submission using open-weights models hosted locally via **Ollama** (e.g. `llama3.2:3b`, `llava`).
  - **100% On-Premise Privacy**: No external cloud LLM APIs; survey text, coordinates, and photos remain strictly inside the server boundary.
  - **Zero PII**: Anonymity filter removes all device tokens, participant identifiers, and network addresses prior to prompt synthesis.
  - **Personalized Researcher Message**: Synthesizes an empathetic note (`researcher_message`) from the researcher persona acknowledging the participant's situation or state, presented before follow-up questions.
  - **Multi-Round Lifecycle**: Governed by `max_followup_rounds` and `max_questions_per_round`. Submissions track ancestry via `parent_response_id` and follow-up round index ($k \ge 1$), automatically linking records (`resp_{id}_follow-up_{k}`) and gracefully halting when limits are reached.
  - **Multimodal Visual Context & Fallback**: Forwards uploaded camera photo bytes directly to Ollama for visual context synthesis. If the active model does not support multimodal inputs, the backend automatically retries in text-only mode. For subsequent follow-up rounds without a new image, the backend automatically retrieves parent photos to maintain visual context.
  - **Self-Describing Responses (`question_prompt`)**: Every answer in `answers` includes `question_id`, `question_prompt`, and `value`. This guarantees that both static initial survey questions and dynamically generated adaptive follow-up questions are self-describing in stored records without requiring server-side dictionary lookups.
  - **Independent Expiration Latency**: Expiration for follow-up rounds is measured against the round's own presentation timestamp (`notification_sent_at`), ensuring follow-up rounds are evaluated independently without being penalized by earlier survey duration.
  - **Schema-Constrained Generation**: Generated questions strictly conform to the `QuestionConfig` Pydantic schema (`rating_scale`, `single_choice`, `multiple_choice`, `text`, `numeric`) with fallback defaults for missing choice options.
  - **Resilience & Graceful Degradation**: Configurable timeout (`LLM_TIMEOUT_SECONDS`, e.g. 45s). In the event of a model timeout or error, response ingestion succeeds normally with HTTP 201 Created without blocking the participant session.
- **Client-Side Question Gating Support**:
  - Passive storage and serving of `QuestionGatingRule` definitions attached to questions (supporting conditions, operators, target question IDs, and confidence thresholds) allowing mobile clients to dynamically unhide questions on-device with zero server latency.
- **Separation of Concerns**: Surveys, sampling schedules, and adaptive follow-up rules are completely decoupled. Surveys define questions, weights, notification copy, and adaptive follow-up rules; schedule configurations define windows and dispatch timing.
- **Fixed & Randomized Notification Dispatching**:
  - Fixed surveys (`first`, `last`) randomize within dedicated morning/night windows (e.g. 08:00–09:30, 20:30–22:00) or adhere to explicit scheduled times.
  - Intraday prompts are stratified and randomized with configurable minimum intervals.
  - Survey selection uses dynamic weights declared in each survey's definition.
- **Expiration Window ("Time to Complete")**:
  - Global `time_to_complete_minutes` window (e.g. 5 minutes) validates completion latency against notification dispatch time.
  - Expired submissions are still persisted for audit (`status: "EXPIRED"`), but answers are autofilled empty (`[]`) with an audit reason message, and adaptive follow-ups are omitted.
- **Paired Response & Image Storage**:
  - JSON submission: `data/responses/{survey_id}/data/{timestamp}_resp_{id}.json`
  - Image photo: `data/responses/{survey_id}/images/{timestamp}_img_{id}.jpg`
- **Pluggable Storage Repositories**:
  - Local server filesystem persistence (`FileStorageRepository`).
  - Google Cloud Firestore & Cloud Storage integration (`FirebaseStorageRepository`).
  - Drop-in scaffold prepared for Microsoft Graph API OneDrive/SharePoint integration (`MSGraphStorageRepository`).
- **Containerized & Production Ready**: Fully containerized with a production `Dockerfile` (Python 3.15, non-root user, built-in health checks) and `docker-compose.yml` with named persistent volumes.

---

## Directory Structure

```text
Simple-Surveys-Backend/
├── app/
│   ├── api/                     # FastAPI route handlers
│   │   ├── health.py            # Health check endpoint
│   │   ├── surveys.py           # Survey definition CRUD
│   │   ├── responses.py         # Response ingestion & adaptive follow-up evaluation
│   │   └── notifications.py     # Notification schedule & device registration
│   ├── crud/                    # Pluggable persistence layer
│   │   ├── base.py              # BaseStorageRepository interface
│   │   ├── file_storage.py      # Local JSON file & image storage
│   │   ├── firebase_storage.py  # Google Cloud Firestore & Cloud Storage
│   │   └── ms_graph_storage.py  # Microsoft Graph OneDrive/SharePoint scaffold
│   ├── schemas/                 # Pydantic DTO models
│   │   ├── common.py            # LocationCoordinates, TemporalMarkers, ImageMetadata
│   │   ├── survey_config.py     # SurveyConfig, QuestionConfig, AdaptiveFollowUpConfig, QuestionGatingRule
│   │   ├── survey_response.py   # SurveyResponseCreate, SurveyResponseRecord, AnswerItem, FollowUpSurveyPayload
│   │   └── notification_config.py # SamplingRules, DeviceRegistration
│   ├── services/                # Business logic
│   │   ├── dispatchers/         # Notification delivery (PushNotificationDispatcher)
│   │   ├── llm/                 # Adaptive LLM orchestration
│   │   │   ├── providers/       # LLM provider drivers (OllamaProvider)
│   │   │   ├── base.py          # BaseLLMProvider interface
│   │   │   ├── prompts.py       # Prompt engineering & strict anonymity context filters
│   │   │   └── service.py       # LLMService orchestration & error resilience
│   │   ├── scheduler_service.py # APScheduler daily dispatch planner & expiration evaluator
│   │   └── survey_selector.py   # Weighted sampling selector
│   ├── config.py                # Pydantic BaseSettings & environment configuration
│   ├── dependencies.py          # FastAPI dependency injection (storage repo, LLM service)
│   └── main.py                  # FastAPI application entrypoint & lifecycle management
├── data/
│   ├── surveys/                 # Survey definition JSON files (e.g., daily_wellbeing_adaptive.json)
│   ├── schedule_config/         # Notification & sampling rules JSON (sampling_rules.json)
│   ├── responses/               # Organized JSON submissions and paired photos
│   └── devices/                 # Registered push notification device tokens
├── .dockerignore
├── .env.example
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── README.md
```

---

## Setup & Running

### 1. Prerequisites
- Python 3.15+ (or Docker)
- [Ollama](https://ollama.com/) installed and running locally (for adaptive ESM follow-up questions)

### 2. Local LLM Setup (Ollama)
Ensure Ollama is installed, running, and has the required model pulled:
```bash
# Pull the default adaptive follow-up model
ollama pull llama3.2:3b

# Optional: Pull a multimodal vision model for photo-grounded follow-ups
ollama pull llava

# Ensure Ollama is running (default port 11434)
ollama serve
```

### 3. Environment Configuration
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```

Review and adjust settings in `.env` as needed:

| Variable | Default | Description |
|---|---|---|
| `HOST` | `0.0.0.0` | Host address to bind |
| `PORT` | `8000` | Port to listen on |
| `DEBUG` | `false` | Enable debug logging |
| `ALLOWED_ORIGINS` | `["*"]` | Allowed CORS origins (JSON array) |
| `STORAGE_BACKEND` | `file_storage` | Storage engine (`file_storage`, `firebase`, or `ms_graph`) |
| `DATA_DIR` | `data` | Base directory for local file storage |
| `FIREBASE_CREDENTIALS_PATH` | `serviceAccountKey.json` | Path to Google Cloud / Firebase service account key JSON |
| `FIREBASE_CREDENTIALS_JSON` | _None_ | Optional raw JSON string for credentials (useful in cloud/Docker deployments) |
| `FIREBASE_PROJECT_ID` | _None_ | Google Cloud / Firebase project ID |
| `FIREBASE_STORAGE_BUCKET` | _None_ | Google Cloud Storage bucket for response photos |
| `FIRESTORE_DATABASE` | `(default)` | Firestore database ID (e.g. `simple-surveys-db`) |
| `TIME_TO_COMPLETE_MINUTES` | `5` | Expiration window in minutes |
| `SCHEDULER_TIMEZONE` | `America/New_York` | Timezone for dispatch windows and daily scheduler |
| `LLM_PROVIDER` | `ollama` | Provider backend (`ollama`) |
| `LLM_MODEL_NAME` | `llama3.2:3b` | Local Ollama model tag (`llama3.2:3b`, `llava`, etc.) |
| `LOCAL_LLM_URL` | `http://localhost:11434` | Server-local Ollama API base URL |
| `LLM_TIMEOUT_SECONDS` | `45` | Timeout limit in seconds for LLM generation before graceful fallback |

---

### 4. Running Option A: Bare-Metal (Python Virtual Environment)

```bash
# Create and activate virtual environment
python -m venv env
# On macOS/Linux:
source env/bin/activate
# On Windows:
.\env\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run server with Uvicorn
python -m app.main
```

---

### 5. Running Option B: Docker & Docker Compose

Run the backend in a containerized environment with health checks and persistent volume storage:

```bash
# Build and start container in the background
docker compose up -d --build

# View real-time container logs
docker compose logs -f

# Stop the container
docker compose down
```

Once running:
- **API Base**: `http://localhost:8000/api`
- **Interactive Swagger Docs**: `http://localhost:8000/docs`
- **ReDoc**: `http://localhost:8000/redoc`

---

## API Endpoints

### System Health
- `GET /api/health`: Health status, storage backend name, and active survey count.

### Survey Definitions
- `GET /api/surveys`: Retrieve surveys (`?active_only=true|false`).
- `GET /api/surveys/{survey_id}`: Retrieve a specific survey definition.
- `POST /api/surveys`: Create and persist a new survey definition (`201 Created`).
- `PATCH /api/surveys/{survey_id}`: Update an existing survey definition (`200 OK`).
- `DELETE /api/surveys/{survey_id}`: Delete a survey definition (`200 OK`). Supports optional query parameters:
  - `delete_responses=true|false`: Also delete all collected response records and images.
  - `clean_schedule_references=true|false`: Remove survey references from sampling rules.

### Response Ingestion & Adaptive Follow-Ups
- `POST /api/responses`: Ingest survey answers and optional camera photo.
  - Supports both `multipart/form-data` (form fields `data` and `image`) and `application/json`.
  - Self-describing answers: each item in `answers` contains `question_id`, `question_prompt`, and `value`.
  - For active surveys with `adaptive_followup.enabled: true`, synchronously queries Ollama and includes `followup_survey` (containing `researcher_message` and generated questions) in the `201 Created` payload.
  - Multi-round follow-up submissions: pass `parent_response_id` and the client's current presentation `notification_sent_at`. Follow-up records are linked (`resp_{id}_follow-up_{k}`) and automatically stop once `max_followup_rounds` is reached.
  - Returns `200 OK` with status `\"EXPIRED\"` and empty answers if submitted beyond `time_to_complete_minutes`.
- `GET /api/responses`: Retrieve persisted response records (`?survey_id={id}`).
- `GET /api/responses/{survey_id}/{response_id}`: Retrieve a specific response.
- `DELETE /api/responses/{survey_id}/{response_id}`: Delete a response record (`?delete_image=true|false`).
- `GET /api/responses/{survey_id}/images/{filename}`: Download an uploaded response photo.

### Notification Scheduling & Devices
- `GET /api/notifications/schedule`: Retrieve active sampling rules (`sampling_rules.json`).
- `POST /api/notifications/schedule`: Upsert sampling rules and refresh daily schedule.
- `GET /api/notifications/devices`: List registered push notification device tokens.
- `POST /api/notifications/devices`: Register an anonymous device push notification token.
- `DELETE /api/notifications/devices/{device_token}`: Unregister and delete a device token.

---

## Schema & Data Models

### 1. Survey Definition with Adaptive Follow-Up & Gating (`SurveyConfig`)

Surveys are stored under `data/surveys/{survey_id}.json` or the Firestore `surveys` collection:

```json
{
  "survey_id": "daily_wellbeing_adaptive",
  "title": "Daily Well-being & Environment Check-in",
  "description": "Adaptive check-in that conditionally reveals questions on-device and generates researcher follow-ups post-submission.",
  "notification_prompt": {
    "title": "Daily Well-being Check-in",
    "body": "Please take a moment to record your current well-being and surroundings."
  },
  "weight": 1.0,
  "is_active": true,
  "adaptive_followup": {
    "enabled": true,
    "max_questions_per_round": 1,
    "max_followup_rounds": 2,
    "researcher_prompt": "You are an empathetic behavioral health researcher. Based on the participant's stress score, free-text mood explanation, and current surroundings photo, formulate exactly ONE thoughtful follow-up question to probe what environmental or interpersonal factors contributed most to their current state."
  },
  "questions": [
    {
      "question_id": "q_stress_scale",
      "prompt": "On a scale from 1 (completely calm) to 10 (extremely stressed), how stressed do you feel?",
      "type": "rating_scale",
      "is_required": true,
      "validation_rules": {
        "min_value": 1,
        "max_value": 10,
        "step": 1,
        "min_label": "Completely Calm",
        "max_label": "Extremely Stressed"
      }
    },
    {
      "question_id": "q_current_feeling_text",
      "prompt": "In your own words, how do you feel at the moment?",
      "type": "text",
      "is_required": true
    },
    {
      "question_id": "q_stress_coping_gated",
      "prompt": "What strategy or support are you currently using to navigate this feeling?",
      "type": "text",
      "is_required": false,
      "gating_rule": {
        "source_question_id": "q_current_feeling_text",
        "operator": "condition_matches",
        "natural_language_condition": "The participant feels stressed or anxious",
        "threshold": 0.55
      }
    }
  ]
}
```

### 2. Initial Survey Submission & Stored Record (`SurveyResponseRecord`)

Initial responses are assigned an ID like `resp_8f4a1c9e` and stored at `data/responses/{survey_id}/data/{timestamp}_resp_{id}.json`:

```json
{
  "response_id": "resp_8f4a1c9e",
  "survey_id": "daily_wellbeing_adaptive",
  "parent_response_id": null,
  "status": "COMPLETED",
  "status_message": "Survey completed successfully within allowed window.",
  "researcher_message": null,
  "temporal_markers": {
    "notification_sent_at": "2026-11-20T20:00:00Z",
    "started_at": "2026-11-20T20:00:05Z",
    "completed_at": "2026-11-20T20:01:45Z",
    "received_at": "2026-11-20T20:01:46Z",
    "latency_seconds": 106.0,
    "completion_duration_seconds": 100.0,
    "time_to_complete_limit_minutes": 5
  },
  "location": {
    "latitude": 40.0379,
    "longitude": -75.3438,
    "accuracy_meters": 5.0
  },
  "image": {
    "has_image": true,
    "image_filename": "2026-11-20T20-01-45_img_8f4a1c9e.jpg"
  },
  "answers": [
    {
      "question_id": "q_stress_scale",
      "question_prompt": "On a scale from 1 (completely calm) to 10 (extremely stressed), how stressed do you feel?",
      "value": 8
    },
    {
      "question_id": "q_current_feeling_text",
      "question_prompt": "In your own words, how do you feel at the moment?",
      "value": "High workload pressure and looming project deadlines."
    }
  ]
}
```

### 3. Generated Follow-Up Payload (`FollowUpSurveyPayload`)

When an adaptive survey is completed within the expiration window, the `POST /api/responses` HTTP response returns:

```json
{
  "response_id": "resp_8f4a1c9e",
  "survey_id": "daily_wellbeing_adaptive",
  "status": "COMPLETED",
  "status_message": "Survey completed successfully within allowed window.",
  "image_stored": true,
  "image_filename": "2026-11-20T20-01-45_img_8f4a1c9e.jpg",
  "received_at": "2026-11-20T20:01:46Z",
  "followup_survey": {
    "parent_response_id": "resp_8f4a1c9e",
    "survey_id": "daily_wellbeing_adaptive",
    "round_number": 1,
    "title": "Follow-up Questions",
    "researcher_message": "Thank you for sharing your thoughts with us. Given your report of elevated workload stress, could you share what specific task is causing the most pressure right now?",
    "questions": [
      {
        "question_id": "followup_stressor_text",
        "prompt": "What specific deadline or assignment is currently contributing most to your stress?",
        "type": "text",
        "is_required": true
      }
    ]
  }
}
```

### 4. Persisted Follow-Up Submission (`resp_8f4a1c9e_follow-up_1`)

When the mobile client submits answers to the follow-up questions, the record is linked and saved with the suffix `_follow-up_1`:

```json
{
  "response_id": "resp_8f4a1c9e_follow-up_1",
  "survey_id": "daily_wellbeing_adaptive",
  "parent_response_id": "resp_8f4a1c9e",
  "status": "COMPLETED",
  "status_message": "Survey completed successfully within allowed window.",
  "researcher_message": "Thank you for sharing your thoughts with us. Given your report of elevated workload stress, could you share what specific task is causing the most pressure right now?",
  "temporal_markers": {
    "notification_sent_at": "2026-11-20T20:01:50Z",
    "started_at": "2026-11-20T20:01:52Z",
    "completed_at": "2026-11-20T20:02:40Z",
    "received_at": "2026-11-20T20:02:41Z",
    "latency_seconds": 51.0,
    "completion_duration_seconds": 48.0,
    "time_to_complete_limit_minutes": 5
  },
  "answers": [
    {
      "question_id": "followup_stressor_text",
      "question_prompt": "What specific deadline or assignment is currently contributing most to your stress?",
      "value": "The software architecture deliverable due tomorrow morning."
    }
  ]
}
```
