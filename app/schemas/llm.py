"""Adaptive LLM survey schemas and contracts."""

from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field
from app.schemas.survey_config import AdaptiveFollowUpConfig, QuestionConfig


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
