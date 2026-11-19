"""Ollama LLM Provider communicating with server-hosted local Ollama runner."""

import base64
import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple
import httpx

from app.config import settings
from app.schemas.survey_config import QuestionConfig
from app.schemas.survey_response import SurveyResponseRecord
from app.services.llm.base import BaseLLMProvider
from app.services.llm.prompts import (
    DEFAULT_RESEARCHER_SYSTEM_PROMPT,
    format_user_prompt,
)

logger = logging.getLogger("simple_surveys.llm.ollama")


class OllamaProvider(BaseLLMProvider):
    """
    Client for server-hosted local Ollama LLM runner.
    """

    def __init__(
        self,
        base_url: str,
        model_name: str,
        timeout_seconds: float
    ):
        self.base_url = base_url
        self.model_name = model_name
        self.timeout_seconds = timeout_seconds

    async def generate_followup_questions(
        self,
        survey_title: str,
        response_record: SurveyResponseRecord,
        photo_bytes: Optional[bytes] = None,
        max_questions: int = 1,
        system_instruction: Optional[str] = None,
    ) -> Tuple[Optional[str], List[QuestionConfig]]:
        """
        Queries Ollama to generate schema-constrained follow-up questions.
        """
        system_prompt = system_instruction or DEFAULT_RESEARCHER_SYSTEM_PROMPT
        has_photo = bool(photo_bytes)
        user_prompt = format_user_prompt(
            survey_title=survey_title,
            response_record=response_record,
            max_questions=max_questions,
            has_photo=has_photo,
        )

        raw_json_str = await self._call_ollama_api(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            photo_bytes=photo_bytes,
        )

        if not raw_json_str:
            return None, []

        return self._parse_and_validate_response(raw_json_str, max_questions=max_questions)

    async def _call_ollama_api(
        self,
        system_prompt: str,
        user_prompt: str,
        photo_bytes: Optional[bytes] = None,
    ) -> Optional[str]:
        """Calls Ollama /api/chat endpoint with JSON format enforcement and image support."""
        endpoint = f"{self.base_url}/api/chat"

        user_message: Dict[str, Any] = {
            "role": "user",
            "content": user_prompt,
        }

        if photo_bytes:
            b64_img = base64.b64encode(photo_bytes).decode("utf-8")
            user_message["images"] = [b64_img]

        payload = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                user_message,
            ],
            "format": "json",
            "stream": False,
            "options": {
                "temperature": 0.2,
            },
        }

        timeout = httpx.Timeout(self.timeout_seconds)
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(endpoint, json=payload)
                if response.status_code != 200:
                    logger.warning(
                        "Ollama responded with HTTP %d: %s",
                        response.status_code,
                        response.text,
                    )
                    return None

                data = response.json()
                return data.get("message", {}).get("content")
        except httpx.TimeoutException:
            logger.warning(
                "Ollama call timed out after %.2fs at %s",
                self.timeout_seconds,
                self.base_url,
            )
            return None
        except Exception as e:
            logger.warning("Ollama request failed at %s: %s", self.base_url, e)
            return None

    def _parse_and_validate_response(
        self,
        raw_content: str,
        max_questions: int = 1,
    ) -> Tuple[Optional[str], List[QuestionConfig]]:
        """Parses LLM JSON output, strips fences if needed, and validates QuestionConfig objects."""
        clean_content = raw_content.strip()

        if clean_content.startswith("```"):
            clean_content = re.sub(r"^```(?:json)?\s*", "", clean_content)
            clean_content = re.sub(r"\s*```$", "", clean_content).strip()

        try:
            parsed = json.loads(clean_content)
        except json.JSONDecodeError as e:
            logger.warning("Failed to decode JSON from LLM: %s. Raw: %s", e, clean_content[:200])
            return None, []

        researcher_message: Optional[str] = None
        raw_questions: List[Any] = []

        if isinstance(parsed, dict):
            researcher_message = parsed.get("researcher_message")
            raw_questions = parsed.get("questions", [])
            if not isinstance(raw_questions, list):
                raw_questions = [raw_questions]
        elif isinstance(parsed, list):
            raw_questions = parsed

        validated_questions: List[QuestionConfig] = []
        for item in raw_questions:
            if not isinstance(item, dict):
                continue
            try:
                qc = QuestionConfig.model_validate(item)
                # Enforce valid question types
                if qc.type in ["rating_scale", "single_choice", "multiple_choice", "text", "numeric"]:
                    # Ensure choices have options
                    if qc.type in ["single_choice", "multiple_choice"]:
                        rules = qc.validation_rules or {}
                        options = rules.get("options", [])
                        if not options or not isinstance(options, list):
                            qc.validation_rules = {"options": ["Yes", "No", "Uncertain"]}
                    validated_questions.append(qc)
                    if len(validated_questions) >= max_questions:
                        break
            except Exception as e:
                logger.warning("Skipping invalid question generated by LLM: %s. Error: %s", item, e)
                continue

        return researcher_message, validated_questions
