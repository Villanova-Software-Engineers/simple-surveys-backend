# Backend Implementation Plan: Follow-Up Response Persistence & Schemas

## 1. Executive Summary & Core Objectives
This document establishes the backend technical requirements, schema modifications, and persistence contracts for the **Simple Surveys Backend** to support **Adaptive LLM Follow-Up Responses**.

The objective of this backend specification is to keep the server persistence layer **lightweight, fast, and schema-driven**:
1. **Self-Describing Responses**: Update `AnswerItem` so that answers record both `question_id` and mandatory `question_prompt`.
2. **Follow-Up Attribution**: Update `SurveyResponseCreate` and `SurveyResponseRecord` to support `researcher_message` and `parent_response_id`.
3. **Zero Backend Mapping Overhead**: Eliminate complex backend dictionary lookups or prompt-enrichment loops. The backend simply validates and persists the structured answers supplied directly by the client.
4. **Independent Latency Evaluation**: Evaluate expiration against the submission's `notification_sent_at` timestamp without coupling follow-up rounds to the initial survey's timer.

---

## 2. Schema Specifications (`app/schemas/survey_response.py`)

### 2.1. Updated `AnswerItem`
`AnswerItem` requires `question_prompt`. The client always populates this for every answer, ensuring that both initial questions and dynamically generated follow-up questions are self-describing in stored files.

```python
class AnswerItem(BaseModel):
    """A single answered question item, paired with its prompt."""
    model_config = ConfigDict(extra="ignore")

    question_id: str = Field(..., description="Target question identifier")
    question_prompt: str = Field(
        ...,
        description="The prompt text of the question asked. Always populated by the client for both initial and follow-up questions."
    )
    value: Any = Field(..., description="Answer value (number, string, list, etc.)")
```

### 2.2. Updated `SurveyResponseCreate`
The ingress payload submitted by the mobile client:

```python
class SurveyResponseCreate(BaseModel):
    """Payload incoming from participant device for survey submission."""
    model_config = ConfigDict(extra="ignore")

    survey_id: str = Field(..., description="Identifier of the survey answered")
    notification_sent_at: datetime = Field(..., description="Timestamp when survey or follow-up round was presented to participant")
    started_at: Optional[datetime] = Field(None, description="Timestamp when user began answering this round")
    completed_at: Optional[datetime] = Field(None, description="Timestamp when user tapped submit on device")
    location: Optional[LocationCoordinates] = Field(None, description="Geographic location details")
    answers: List[AnswerItem] = Field(default_factory=list, description="Answered survey questions with prompts")
    response_id: Optional[str] = Field(None, description="Optional client-generated response ID")
    parent_response_id: Optional[str] = Field(None, description="Parent response ID if submitting a follow-up round")
    researcher_message: Optional[str] = Field(
        None,
        description="The researcher follow-up message shown to participant before these questions."
    )
```

### 2.3. Updated `SurveyResponseRecord`
The egress and persistence record stored in Firestore or local server disk:

```python
class SurveyResponseRecord(BaseModel):
    """Full persisted response record saved to storage."""
    model_config = ConfigDict(extra="ignore")

    response_id: str = Field(..., description="Unique response identifier (resp_{id} or resp_{id}_follow-up_{k})")
    survey_id: str = Field(..., description="Identifier of the survey answered")
    parent_response_id: Optional[str] = Field(None, description="Parent response ID if this is a follow-up record")
    status: ResponseStatus = Field(..., description="Completion or expiration status (COMPLETED or EXPIRED)")
    status_message: str = Field(..., description="Descriptive status note")
    temporal_markers: TemporalMarkers = Field(..., description="Audit markers for dispatch, latency, and duration")
    location: Optional[LocationCoordinates] = Field(None, description="Participant location coordinates")
    image: ImageMetadata = Field(default_factory=ImageMetadata, description="Associated captured photo metadata")
    researcher_message: Optional[str] = Field(None, description="Researcher follow-up message if applicable")
    answers: List[AnswerItem] = Field(default_factory=list, description="Submitted answers with prompt text included")
```

---

## 3. Backend Ingestion Logic (`app/api/responses.py`)

### 3.1. Elimination of Backend Enrichment
Because the mobile client always attaches `question_prompt` to each `AnswerItem`, the backend does **not** need to perform any dictionary lookups, question matching, or enrichment loops. 

The submission answers are passed straight to `SurveyResponseRecord`:

```python
    record = SurveyResponseRecord(
        response_id=response_id,
        survey_id=submission.survey_id,
        parent_response_id=submission.parent_response_id,
        status=res_status,
        status_message=status_message,
        temporal_markers=temporal_markers,
        location=submission.location,
        image=image_metadata,
        answers=[] if is_expired else submission.answers,
        researcher_message=submission.researcher_message,
    )
```

### 3.2. Response Identity & Naming Resolution
For follow-up submissions, the backend constructs the response ID based on the round number:
- Initial response: `resp_8f4a1c9e`
- Follow-up response: `resp_8f4a1c9e_follow-up_1`

Both JSON files are stored in the same survey response directory:
```
data/responses/{survey_id}/data/
├── 2026-11-19T20-00-00_resp_8f4a1c9e.json              <-- Initial submission
└── 2026-11-19T20-02-00_resp_8f4a1c9e_follow-up_1.json  <-- Follow-up submission
```

### 3.3. Independent Expiration Evaluation
The backend calculates latency solely based on the submitted `notification_sent_at`:
$$\text{latency\_seconds} = \text{received\_at} - \text{submission.notification\_sent\_at}$$

- For **Initial Surveys**: `notification_sent_at` reflects when the initial notification or check-in began.
- For **Follow-Up Surveys**: The client supplies `notification_sent_at` as the exact timestamp the follow-up round was presented on screen.
- The backend evaluates whether $\text{latency\_seconds} \le \text{time\_to\_complete\_minutes} \times 60$. Follow-up rounds are evaluated completely independently.

---

## 4. Sample Stored JSON Output

### 4.1. Initial Survey Submission (`resp_8f4a1c9e`)
```json
{
  "response_id": "resp_8f4a1c9e",
  "survey_id": "daily_wellbeing_adaptive",
  "parent_response_id": null,
  "status": "COMPLETED",
  "status_message": "Survey completed successfully within allowed window.",
  "researcher_message": null,
  "temporal_markers": {
    "notification_sent_at": "2026-11-19T20:00:00Z",
    "started_at": "2026-11-19T20:00:05Z",
    "completed_at": "2026-11-19T20:01:45Z",
    "received_at": "2026-11-19T20:01:46Z",
    "latency_seconds": 106.0,
    "completion_duration_seconds": 100.0,
    "time_to_complete_limit_minutes": 5
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
      "value": "High workload pressure and looming deadlines."
    }
  ]
}
```

### 4.2. Follow-Up Submission (`resp_8f4a1c9e_follow-up_1`)
```json
{
  "response_id": "resp_8f4a1c9e_follow-up_1",
  "survey_id": "daily_wellbeing_adaptive",
  "parent_response_id": "resp_8f4a1c9e",
  "status": "COMPLETED",
  "status_message": "Survey completed successfully within allowed window.",
  "researcher_message": "Thank you for sharing your thoughts. Given your report of elevated workload stress, could you share what specific task is causing the most pressure right now?",
  "temporal_markers": {
    "notification_sent_at": "2026-11-19T20:01:50Z",
    "started_at": "2026-11-19T20:01:52Z",
    "completed_at": "2026-11-19T20:02:40Z",
    "received_at": "2026-11-19T20:02:41Z",
    "latency_seconds": 51.0,
    "completion_duration_seconds": 48.0,
    "time_to_complete_limit_minutes": 5
  },
  "answers": [
    {
      "question_id": "followup_1",
      "question_prompt": "What specific deadline or assignment is currently contributing most to your stress?",
      "value": "The software architecture deliverable due tomorrow morning."
    }
  ]
}
```

---

## 5. Backend Implementation Checklist

- [x] **Schema Updates** (`app/schemas/survey_response.py`):
  - [x] Make `question_prompt: str = Field(...)` mandatory in `AnswerItem`.
  - [x] Add `researcher_message: Optional[str] = None` to `SurveyResponseCreate`.
  - [x] Add `researcher_message: Optional[str] = None` to `SurveyResponseRecord`.
- [x] **API Endpoint Verification** (`app/api/responses.py`):
  - [x] Verify `record` receives `submission.answers` directly without any lookup loops.
  - [x] Verify `record` receives `researcher_message=submission.researcher_message`.
- [x] **Integration Verification**:
  - [x] Submit an initial survey with prompts populated; verify JSON file structure on disk.
  - [x] Submit a follow-up survey with prompts and researcher message; verify JSON file structure on disk.
