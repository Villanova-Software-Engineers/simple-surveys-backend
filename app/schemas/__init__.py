"""DTO schemas package for Simple Surveys."""

from app.schemas.common import ImageMetadata, LocationCoordinates, TemporalMarkers
from app.schemas.survey_config import (
    AdaptiveFollowUpConfig,
    GatingOperator,
    QuestionConfig,
    QuestionGatingRule,
    SurveyConfig,
    SurveyConfigCreate,
    SurveyConfigUpdate,
    SurveyDeleteResponse,
    SurveyNotificationPrompt,
)
from app.schemas.survey_response import (
    AnswerItem,
    ResponseDeleteResponse,
    SurveyResponseCreate,
    SurveyResponseRecord,
    SurveyResponseSubmissionResult,
    FollowUpSurveyPayload
)
from app.schemas.notification_config import (
    DailyScheduleWindows,
    DeviceDeleteResponse,
    DeviceRegistration,
    DeviceRegistrationResponse,
    FixedSurveyConfig,
    RandomizedSamplingConfig,
    SamplingRules,
    TimeWindow,
)

__all__ = [
    "ImageMetadata",
    "LocationCoordinates",
    "TemporalMarkers",
    "QuestionConfig",
    "QuestionGatingRule",
    "GatingOperator",
    "SurveyConfig",
    "SurveyConfigCreate",
    "SurveyConfigUpdate",
    "SurveyDeleteResponse",
    "SurveyNotificationPrompt",
    "AnswerItem",
    "ResponseDeleteResponse",
    "SurveyResponseCreate",
    "SurveyResponseRecord",
    "SurveyResponseSubmissionResult",
    "TimeWindow",
    "DailyScheduleWindows",
    "FixedSurveyConfig",
    "RandomizedSamplingConfig",
    "SamplingRules",
    "DeviceDeleteResponse",
    "DeviceRegistration",
    "DeviceRegistrationResponse",
    "AdaptiveFollowUpConfig",
    "FollowUpSurveyPayload",
]
