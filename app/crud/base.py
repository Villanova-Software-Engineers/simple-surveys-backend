"""Abstract base class for survey and response storage repositories."""

from abc import ABC, abstractmethod
from typing import List, Optional, Tuple
from app.schemas.notification_config import DeviceRegistration, SamplingRules
from app.schemas.survey_config import SurveyConfig
from app.schemas.survey_response import SurveyResponseRecord


class BaseStorageRepository(ABC):
    """Abstract interface defining storage operations for Simple Surveys."""

    # Survey definitions
    @abstractmethod
    async def save_survey(self, survey: SurveyConfig) -> SurveyConfig:
        """Persist a survey definition."""
        pass

    @abstractmethod
    async def get_survey(self, survey_id: str) -> Optional[SurveyConfig]:
        """Retrieve a survey definition by unique ID."""
        pass

    @abstractmethod
    async def list_surveys(self, active_only: bool = False) -> List[SurveyConfig]:
        """List all stored survey definitions."""
        pass

    @abstractmethod
    async def delete_survey(self, survey_id: str, delete_responses: bool = False) -> bool:
        """
        Delete a survey definition by unique ID.
        Optionally deletes associated responses and media.
        Returns True if deleted, False if not found.
        """
        pass

    # Responses
    @abstractmethod
    async def save_response(
        self,
        response: SurveyResponseRecord,
        timestamp_str: Optional[str] = None
    ) -> SurveyResponseRecord:
        """Persist a survey response record."""
        pass

    @abstractmethod
    async def get_response(
        self,
        survey_id: str,
        response_id: str
    ) -> Optional[SurveyResponseRecord]:
        """Retrieve a single response record by survey_id and response_id."""
        pass

    @abstractmethod
    async def list_responses(
        self,
        survey_id: Optional[str] = None
    ) -> List[SurveyResponseRecord]:
        """
        List response records.
        If survey_id is provided, filters to that survey.
        """
        pass

    @abstractmethod
    async def delete_response(
        self,
        survey_id: str,
        response_id: str,
        delete_image: bool = True
    ) -> bool:
        """
        Delete a response record by survey_id and response_id.
        Optionally deletes the associated image file/blob.
        Returns True if deleted, False if not found.
        """
        pass

    # Media / Images
    @abstractmethod
    async def save_image(
        self,
        survey_id: str,
        response_id: str,
        timestamp_str: str,
        image_bytes: bytes,
        extension: str = "jpg"
    ) -> str:
        """Save an image file with matched timestamp and ID prefix."""
        pass

    @abstractmethod
    async def get_image(self, survey_id: str, filename: str) -> Optional[Tuple[bytes, str]]:
        """Retrieve image raw bytes and media_type (content-type) directly from storage."""
        pass

    # Schedule Configuration
    @abstractmethod
    async def get_schedule_config(self) -> Optional[SamplingRules]:
        """Retrieve the current sampling rules configuration, or None if not configured."""
        pass

    @abstractmethod
    async def save_schedule_config(self, config: SamplingRules) -> SamplingRules:
        """Persist updated sampling rules configuration."""
        pass

    # Device Registrations
    @abstractmethod
    async def save_device(self, device: DeviceRegistration) -> DeviceRegistration:
        """Save a registered device token."""
        pass

    @abstractmethod
    async def list_devices(self) -> List[DeviceRegistration]:
        """List all registered devices."""
        pass

    @abstractmethod
    async def get_device(self, device_token: str) -> Optional[DeviceRegistration]:
        """Retrieve a registered device by token."""
        pass

    @abstractmethod
    async def delete_device(self, device_token: str) -> bool:
        """
        Delete a registered device by token.
        Returns True if deleted, False if not found.
        """
        pass
