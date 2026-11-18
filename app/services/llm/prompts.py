"""Prompt engineering, anonymization context builders, and JSON schemas for LLM follow-up generation."""

import json
from typing import Any, Dict, List, Optional
from app.schemas.survey_response import SurveyResponseRecord

DEFAULT_RESEARCHER_SYSTEM_PROMPT = (
    "You are an empathetic, professional behavioral and experience sampling researcher conducting "
    "an anonymous check-in survey. Your role is to formulate thoughtful, context-aware follow-up "
    "questions based on the participant's recent submission.\n\n"
    "SAFETY AND ETHICAL GUARDRAILS:\n"
    "1. Anonymity: Never ask for identifying information (e.g., name, phone number, email, address, employer).\n"
    "2. Non-Diagnostic: Do not offer medical, psychiatric, or diagnostic advice or evaluations.\n"
    "3. Appropriateness: Strictly refrain from invasive, offensive, triggering, or coercive questions.\n"
    "4. Relevance: Keep follow-up questions directly anchored to the participant's stated context, mood, activity, or environment.\n"
    "5. Brevity: Formulate concise, easy-to-answer questions suitable for a mobile experience sampling questionnaire."
)

JSON_SCHEMA_INSTRUCTION = """
You MUST output your response strictly in valid JSON matching the following schema:
{
  "researcher_message": "A brief, empathetic 1-sentence note acknowledging the participant's situation or state (optional, can be null)",
  "questions": [
    {
      "question_id": "string (unique identifier, e.g. 'followup_coping_text')",
      "prompt": "string (the question prompt to show the participant)",
      "type": "rating_scale" | "single_choice" | "multiple_choice" | "text" | "numeric",
      "is_required": true | false,
      "validation_rules": {
        // Depending on type:
        // For "rating_scale": {"min_value": 1, "max_value": 10, "step": 1, "min_label": "...", "max_label": "..."}
        // For "single_choice": {"options": ["Option 1", "Option 2", ...]}
        // For "multiple_choice": {"options": ["Option 1", "Option 2", ...], "min_selections": 1, "max_selections": 3}
        // For "text": {"placeholder": "...", "max_length": 300}
        // For "numeric": {"min_value": 0, "max_value": 100, "allow_decimals": false}
      }
    }
  ]
}
Return ONLY this JSON object with no markdown fences, no explanatory preambles, and no trailing comments.
"""


def build_anonymized_context_summary(
    survey_title: str,
    response_record: SurveyResponseRecord,
    has_photo: bool = False,
) -> Dict[str, Any]:
    """
    Constructs a strictly anonymized representation of the submission context.
    Contains zero participant identifiers, device tokens, IP addresses, or permanent IDs.
    """
    context: Dict[str, Any] = {
        "survey_title": survey_title,
        "answers": [
            {"question_id": a.question_id, "value": a.value}
            for a in response_record.answers
        ],
    }

    if response_record.temporal_markers:
        tm = response_record.temporal_markers
        timing = {}
        if tm.completed_at:
            timing["completed_at"] = tm.completed_at.isoformat()
        if tm.completion_duration_seconds is not None:
            timing["completion_duration_seconds"] = tm.completion_duration_seconds
        if timing:
            context["timing"] = timing

    if response_record.location:
        loc = response_record.location
        context["location"] = {
            "latitude": loc.latitude,
            "longitude": loc.longitude,
            "accuracy_meters": loc.accuracy_meters,
            "altitude_meters": loc.altitude_meters,
        }

    context["photo_attached"] = has_photo
    return context


def format_user_prompt(
    survey_title: str,
    response_record: SurveyResponseRecord,
    max_questions: int = 1,
    has_photo: bool = False,
) -> str:
    """Formats the user prompt containing the survey submission context and generation instructions."""
    context = build_anonymized_context_summary(
        survey_title=survey_title,
        response_record=response_record,
        has_photo=has_photo,
    )
    context_json = json.dumps(context, indent=2)

    return (
        f"Participant Survey Submission Context:\n{context_json}\n\n"
        f"Generate at most {max_questions} targeted, context-aware follow-up question(s) "
        f"based on the participant's submitted data.\n"
        f"{JSON_SCHEMA_INSTRUCTION}"
    )
