"""Survey response schemas and record models."""

from datetime import datetime
from typing import Any, List, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field
from app.schemas.common import ImageMetadata, LocationCoordinates, TemporalMarkers
from app.schemas.survey_config import QuestionConfig

ResponseStatus = Literal["COMPLETED", "EXPIRED"]


class AnswerItem(BaseModel):
    """A single answered question item."""
    model_config = ConfigDict(extra="ignore")

    question_id: str = Field(..., description="Target question identifier")
    value: Any = Field(..., description="Answer value (number, string, list, etc.)")


class SurveyResponseCreate(BaseModel):
    """Payload incoming from participant device for survey submission."""
    model_config = ConfigDict(extra="ignore")

    survey_id: str = Field(..., description="Identifier of the survey answered")
    notification_sent_at: datetime = Field(..., description="Timestamp when notification prompt was dispatched")
    started_at: Optional[datetime] = Field(None, description="Timestamp when user began answering")
    completed_at: Optional[datetime] = Field(None, description="Timestamp when survey was completed")
    location: Optional[LocationCoordinates] = Field(None, description="Geographic location details")
    answers: List[AnswerItem] = Field(default_factory=list, description="Answered survey questions")
    response_id: Optional[str] = Field(None, description="Optional client-generated response ID")
    parent_response_id: Optional[str] = Field(None, description="Parent response ID if submitting a follow-up round")


class SurveyResponseRecord(BaseModel):
    """Full persisted response record saved to data/responses/{survey_id}/data/."""
    model_config = ConfigDict(extra="ignore")

    response_id: str = Field(..., description="Unique response identifier (resp_{id})")
    survey_id: str = Field(..., description="Identifier of the survey answered")
    status: ResponseStatus = Field(..., description="Completion or expiration status")
    status_message: str = Field(..., description="Descriptive status note")
    temporal_markers: TemporalMarkers = Field(..., description="Audit markers for dispatch, latency, and duration")
    location: Optional[LocationCoordinates] = Field(None, description="Participant location coordinates")
    image: ImageMetadata = Field(default_factory=ImageMetadata, description="Associated captured photo metadata")
    answers: List[AnswerItem] = Field(default_factory=list, description="Submitted answers (empty if EXPIRED)")
    parent_response_id: Optional[str] = Field(None, description="Parent response ID if this is a follow-up record")


class FollowUpSurveyPayload(BaseModel):
    """Dynamic follow-up survey returned in response to initial survey completion."""
    model_config = ConfigDict(extra="ignore")

    parent_response_id: str = Field(..., description="Response ID of the parent survey submission")
    survey_id: str = Field(..., description="Survey identifier")
    round_number: int = Field(1, description="Current follow-up round index (1 to max_followup_rounds)")
    title: str = Field("Follow-up Questions", description="Title for follow-up survey")
    researcher_message: Optional[str] = Field(
        None,
        description="A brief personalized message from the researcher acknowledging the participant's situation"
    )
    questions: List[QuestionConfig] = Field(
        ...,
        description="Questions adhering strictly to app.schemas.survey_config.QuestionConfig"
    )


class SurveyResponseSubmissionResult(BaseModel):
    """HTTP response returned to the client upon submitting a survey."""
    model_config = ConfigDict(extra="ignore")

    response_id: str = Field(..., description="Unique response identifier")
    survey_id: str = Field(..., description="Identifier of the submitted survey")
    status: ResponseStatus = Field(..., description="COMPLETED or EXPIRED")
    status_message: Optional[str] = Field(None, description="Status detail message")
    message: Optional[str] = Field(None, description="Alias for status detail message")
    image_stored: bool = Field(False, description="Whether an uploaded image was persisted")
    image_filename: Optional[str] = Field(None, description="Persisted image filename if stored")
    received_at: datetime = Field(..., description="Timestamp when server received submission")
    followup_survey: Optional[FollowUpSurveyPayload] = Field(
        None,
        description="Populated if the completed survey triggered an adaptive follow-up round."
    )


class ResponseDeleteResponse(BaseModel):
    """Acknowledgement returned on response deletion."""
    model_config = ConfigDict(extra="ignore")

    status: str = Field("deleted", description="Deletion status")
    survey_id: str = Field(..., description="Survey identifier")
    response_id: str = Field(..., description="Deleted response identifier")
    message: str = Field(..., description="Confirmation message")
    image_deleted: bool = Field(False, description="Whether associated image was also deleted")
