"""Abstract base class for LLM providers."""

from abc import ABC, abstractmethod
from typing import List, Optional, Tuple
from app.schemas.survey_config import QuestionConfig
from app.schemas.survey_response import SurveyResponseRecord


class BaseLLMProvider(ABC):
    """Abstract interface for server-side LLM question generation."""

    @abstractmethod
    async def generate_followup_questions(
        self,
        survey_title: str,
        response_record: SurveyResponseRecord,
        photo_bytes: Optional[bytes] = None,
        max_questions: int = 1,
        system_instruction: Optional[str] = None,
    ) -> Tuple[Optional[str], List[QuestionConfig]]:
        """
        Takes the full participant submission context and returns:
        (researcher_message, list_of_followup_questions).

        Guarantees that each returned question adheres to QuestionConfig schema.
        """
        pass
