"""Survey configuration schemas and question definitions."""

from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field

QuestionType = Literal[
    "rating_scale",
    "single_choice",
    "multiple_choice",
    "text",
    "numeric",
]

GatingOperator = Literal[
    "openjev_matches",
    "equals",
    "greater_than",
    "less_than",
    "contains",
]


class QuestionGatingRule(BaseModel):
    """
    Client-evaluated gating condition attached to a survey question.
    Stored and served by the backend; evaluated on-device by the mobile client.
    """
    model_config = ConfigDict(extra="ignore")

    source_question_id: str = Field(..., description="ID of the parent question whose answer determines visibility")
    operator: GatingOperator = Field("openjev_matches", description="Evaluation operator ('openjev_matches' for semantic model)")
    natural_language_condition: Optional[str] = Field(None, description="Hypothesis predicate for OpenJev")
    threshold: float = Field(0.55, description="Confidence threshold (0.0 to 1.0)")


class RatingScaleValidation(BaseModel):
    """Validation rules for rating scale questions."""
    model_config = ConfigDict(extra="ignore")

    min_value: int = Field(1, description="Minimum rating value")
    max_value: int = Field(10, description="Maximum rating value")
    step: int = Field(1, description="Step increment")
    min_label: Optional[str] = Field(None, description="Label for minimum value")
    max_label: Optional[str] = Field(None, description="Label for maximum value")


class SingleChoiceValidation(BaseModel):
    """Validation rules for single choice questions."""
    model_config = ConfigDict(extra="ignore")

    options: List[str] = Field(..., description="Available choice options")


class MultipleChoiceValidation(BaseModel):
    """Validation rules for multiple choice questions."""
    model_config = ConfigDict(extra="ignore")

    options: List[str] = Field(..., description="Available choice options")
    min_selections: Optional[int] = Field(None, description="Minimum number of selections")
    max_selections: Optional[int] = Field(None, description="Maximum number of selections")


class TextValidation(BaseModel):
    """Validation rules for text questions."""
    model_config = ConfigDict(extra="ignore")

    min_length: Optional[int] = Field(None, description="Minimum character length")
    max_length: Optional[int] = Field(None, description="Maximum character length")
    placeholder: Optional[str] = Field(None, description="Placeholder text hint")


class NumericValidation(BaseModel):
    """Validation rules for numeric questions."""
    model_config = ConfigDict(extra="ignore")

    min_value: Optional[float] = Field(None, description="Minimum numeric value")
    max_value: Optional[float] = Field(None, description="Maximum numeric value")
    allow_decimals: Optional[bool] = Field(False, description="Whether decimal values are allowed")


class QuestionConfig(BaseModel):
    """Definition for a single survey question."""
    model_config = ConfigDict(extra="ignore")

    question_id: str = Field(..., description="Unique question identifier within the survey")
    prompt: str = Field(..., description="Question prompt displayed to the participant")
    type: QuestionType = Field(..., description="Type of question")
    is_required: bool = Field(True, description="Whether an answer is mandatory")
    validation_rules: Optional[Dict[str, Any]] = Field(None, description="Type-specific validation rules")
    gating_rule: Optional[QuestionGatingRule] = Field(
        None,
        description="Optional client-evaluated gating condition"
    )


class AdaptiveFollowUpConfig(BaseModel):
    """Configuration attached to SurveyConfig to control LLM follow-ups."""
    model_config = ConfigDict(extra="ignore")

    enabled: bool = Field(False, description="Whether to trigger an LLM follow-up round")
    max_questions_per_round: int = Field(1, ge=1, le=3, description="Maximum follow-up questions generated per round")
    max_followup_rounds: int = Field(1, ge=1, le=5, description="Maximum number of conversational follow-up rounds allowed")
    researcher_prompt: Optional[str] = Field(
        None,
        description="Custom system instructions framing the researcher's focus (e.g., 'Probe on coping mechanisms')."
    )


class SurveyNotificationPrompt(BaseModel):
    """Notification copy dispatched for this survey."""
    model_config = ConfigDict(extra="ignore")

    title: str = Field(..., description="Notification title")
    body: str = Field(..., description="Notification body message")


class SurveyConfigBase(BaseModel):
    """Base survey definition fields."""
    model_config = ConfigDict(extra="ignore")

    survey_id: str = Field(..., description="Unique survey identifier")
    title: str = Field(..., description="Human-readable survey title")
    description: Optional[str] = Field(None, description="Survey description and instructions")
    notification_prompt: SurveyNotificationPrompt = Field(..., description="Notification copy")
    weight: float = Field(1.0, description="Sampling weight for randomized selection pools")
    is_active: bool = Field(True, description="Whether survey is active for sampling")
    questions: List[QuestionConfig] = Field(default_factory=list, description="Survey questions")
    adaptive_followup: Optional[AdaptiveFollowUpConfig] = Field(
        None,
        description="Optional adaptive follow-up configuration"
    )


class SurveyConfigCreate(SurveyConfigBase):
    """Payload for creating a new survey."""
    pass


class SurveyConfigUpdate(BaseModel):
    """Payload for updating an existing survey."""
    model_config = ConfigDict(extra="ignore")

    title: Optional[str] = Field(None, description="Human-readable survey title")
    description: Optional[str] = Field(None, description="Survey description")
    notification_prompt: Optional[SurveyNotificationPrompt] = Field(None, description="Notification copy")
    weight: Optional[float] = Field(None, description="Sampling weight")
    is_active: Optional[bool] = Field(None, description="Active status")
    questions: Optional[List[QuestionConfig]] = Field(None, description="Survey questions")
    adaptive_followup: Optional[AdaptiveFollowUpConfig] = Field(
        None,
        description="Optional adaptive follow-up configuration"
    )


class SurveyConfig(SurveyConfigBase):
    """Complete survey configuration model."""
    pass


class SurveyDeleteResponse(BaseModel):
    """Acknowledgement returned on survey deletion."""
    model_config = ConfigDict(extra="ignore")

    status: str = Field("deleted", description="Deletion status")
    survey_id: str = Field(..., description="Deleted survey identifier")
    message: str = Field(..., description="Confirmation message")
    responses_deleted: bool = Field(False, description="Whether associated responses were purged")
    schedule_references_cleaned: bool = Field(
        False,
        description="Whether sampling rules are clean (True if removed or none existed, False if an error occurred)"
    )
