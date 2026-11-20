"""Survey response submission and retrieval endpoints."""

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Tuple
from fastapi import APIRouter, HTTPException, Query, Request, Response, status
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from starlette.datastructures import UploadFile

from app.config import settings
from app.crud.base import BaseStorageRepository
from app.crud.file_storage import format_filename_timestamp
from app.dependencies import LLMServiceDep, SchedulerServiceDep, StorageRepoDep
from app.schemas.common import ImageMetadata
from app.schemas.survey_config import SurveyConfig
from app.schemas.survey_response import (
    ResponseDeleteResponse,
    SurveyResponseCreate,
    SurveyResponseRecord,
    SurveyResponseSubmissionResult,
    FollowUpSurveyPayload,
)
from app.services.llm.service import LLMService

router = APIRouter(prefix="/responses", tags=["Responses"])


@router.get("", response_model=List[SurveyResponseRecord])
async def list_responses(
    storage_repo: StorageRepoDep,
    survey_id: Optional[str] = Query(None, description="Optional survey_id filter"),
) -> List[SurveyResponseRecord]:
    """
    Retrieve persisted response records.
    If survey_id filter is provided, verifies that the survey exists.
    """
    if survey_id is not None:
        survey = await storage_repo.get_survey(survey_id)
        if not survey:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Survey '{survey_id}' does not exist.",
            )
    return await storage_repo.list_responses(survey_id=survey_id)


@router.get("/{survey_id}/{response_id}", response_model=SurveyResponseRecord)
async def get_response(
    survey_id: str,
    response_id: str,
    storage_repo: StorageRepoDep,
) -> SurveyResponseRecord:
    """Retrieve a specific response record."""
    record = await storage_repo.get_response(survey_id, response_id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Response '{response_id}' for survey '{survey_id}' not found.",
        )
    return record


@router.delete("/{survey_id}/{response_id}", response_model=ResponseDeleteResponse)
async def delete_response(
    survey_id: str,
    response_id: str,
    storage_repo: StorageRepoDep,
    delete_image: bool = Query(
        True,
        description="Whether to also delete any associated uploaded photo",
    ),
) -> ResponseDeleteResponse:
    """
    Delete a specific survey response record and optionally its associated photo.
    """
    survey = await storage_repo.get_survey(survey_id)
    if not survey:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Survey '{survey_id}' does not exist.",
        )

    record = await storage_repo.get_response(survey_id, response_id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Response '{response_id}' for survey '{survey_id}' not found.",
        )

    had_image = bool(record.image and record.image.has_image and record.image.image_filename)
    deleted = await storage_repo.delete_response(survey_id, response_id, delete_image=delete_image)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Response '{response_id}' for survey '{survey_id}' not found.",
        )

    return ResponseDeleteResponse(
        status="deleted",
        survey_id=survey_id,
        response_id=response_id,
        message=f"Response '{response_id}' for survey '{survey_id}' deleted successfully.",
        image_deleted=had_image and delete_image,
    )


@router.get("/{survey_id}/images/{filename}")
async def get_response_image(
    survey_id: str,
    filename: str,
    storage_repo: StorageRepoDep,
) -> Response:
    """Download an uploaded survey response photo directly in-memory."""
    image_data = await storage_repo.get_image(survey_id, filename)
    if not image_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Image '{filename}' not found for survey '{survey_id}'.",
        )
    image_bytes, media_type = image_data
    return Response(content=image_bytes, media_type=media_type)


@router.post("", response_model=SurveyResponseSubmissionResult)
async def submit_response(
    request: Request,
    storage_repo: StorageRepoDep,
    scheduler_service: SchedulerServiceDep,
    llm_service: LLMServiceDep,
) -> JSONResponse:
    """
    Ingests anonymous survey response data with optional camera photo.
    Evaluates submission against the configured time_to_complete_minutes window.
    Supports adaptive ESM follow-up question synthesis via local server LLM.
    Supports both multipart/form-data (with JSON string + file) and application/json.
    """
    submission, uploaded_image = await _parse_submission_request(request)

    survey = await storage_repo.get_survey(submission.survey_id)
    if not survey:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Survey '{submission.survey_id}' does not exist.",
        )

    response_id, current_round = _resolve_response_identity(submission)
    received_at = datetime.now(timezone.utc)

    schedule_config = await storage_repo.get_schedule_config()
    time_limit_minutes = (
        schedule_config.time_to_complete_minutes
        if schedule_config
        else settings.time_to_complete_minutes
    )

    res_status, status_message, is_expired, temporal_markers = (
        scheduler_service.evaluate_response_expiration(
            submission=submission,
            time_to_complete_limit_minutes=time_limit_minutes,
            received_at=received_at,
        )
    )

    anchor_dt = submission.completed_at or received_at
    timestamp_str = format_filename_timestamp(anchor_dt)

    if is_expired:
        image_metadata = ImageMetadata(has_image=False)
        image_stored = False
        stored_img_filename = None
        image_bytes = None
    else:
        image_metadata, image_stored, stored_img_filename, image_bytes = (
            await _process_submission_media(
                storage_repo=storage_repo,
                survey_id=submission.survey_id,
                response_id=response_id,
                timestamp_str=timestamp_str,
                uploaded_image=uploaded_image,
                parent_response_id=submission.parent_response_id,
            )
        )

    record = SurveyResponseRecord(
        response_id=response_id,
        survey_id=submission.survey_id,
        parent_response_id=submission.parent_response_id,
        status=res_status,
        status_message=status_message,
        temporal_markers=temporal_markers,
        location=submission.location,
        image=image_metadata,
        researcher_message=submission.researcher_message,
        answers=[] if is_expired else submission.answers,
    )
    await storage_repo.save_response(record, timestamp_str=timestamp_str)

    if is_expired:
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=SurveyResponseSubmissionResult(
                response_id=response_id,
                survey_id=submission.survey_id,
                status="EXPIRED",
                status_message=status_message,
                message=status_message,
                image_stored=False,
                image_filename=None,
                received_at=received_at,
                followup_survey=None,
            ).model_dump(mode="json"),
        )

    followup_survey = await _evaluate_adaptive_followup(
        llm_service=llm_service,
        survey=survey,
        record=record,
        current_round=current_round,
        image_bytes=image_bytes,
    )

    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content=SurveyResponseSubmissionResult(
            response_id=response_id,
            survey_id=submission.survey_id,
            status="COMPLETED",
            status_message=status_message,
            message=status_message,
            image_stored=image_stored,
            image_filename=stored_img_filename,
            received_at=received_at,
            followup_survey=followup_survey,
        ).model_dump(mode="json"),
    )


async def _parse_submission_request(
    request: Request,
) -> Tuple[SurveyResponseCreate, Optional[UploadFile]]:
    """
    Extracts survey response payload and optional image from request.
    Supports both multipart/form-data and application/json.
    """
    content_type = request.headers.get("content-type", "")

    if "multipart/form-data" in content_type:
        form = await request.form()
        data_field = form.get("data")
        if not data_field:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Multipart form-data submission requires 'data' field containing survey JSON.",
            )
        try:
            parsed_data = json.loads(data_field) if isinstance(data_field, str) else data_field
            submission = SurveyResponseCreate.model_validate(parsed_data)
        except (json.JSONDecodeError, ValidationError) as e:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid JSON in 'data' field: {e}",
            )

        uploaded_image = None
        img_field = form.get("image")
        if hasattr(img_field, "filename") and bool(getattr(img_field, "filename", None)):
            uploaded_image = img_field
        return submission, uploaded_image

    try:
        body = await request.json()
        submission = SurveyResponseCreate.model_validate(body)
        return submission, None
    except (json.JSONDecodeError, ValidationError) as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid JSON request body: {e}",
        )


def _resolve_response_identity(submission: SurveyResponseCreate) -> Tuple[str, int]:
    """
    Determines response_id and current round index k.
    Initial response: resp_{id} (k=0)
    Follow-up response: resp_{id}_follow-up_{k} (k >= 1)
    """
    if submission.response_id:
        response_id = submission.response_id
        match = re.search(r"_follow-up_(\d+)$", response_id)
        current_round = int(match.group(1)) if match else 0
        return response_id, current_round

    if submission.parent_response_id:
        parent_id = submission.parent_response_id
        match = re.search(r"_follow-up_(\d+)$", parent_id)
        if match:
            current_round = int(match.group(1)) + 1
            base_id = parent_id[:match.start()]
            return f"{base_id}_follow-up_{current_round}", current_round
        return f"{parent_id}_follow-up_1", 1

    return f"resp_{uuid.uuid4().hex[:8]}", 0


async def _process_submission_media(
    storage_repo: BaseStorageRepository,
    survey_id: str,
    response_id: str,
    timestamp_str: str,
    uploaded_image: Optional[UploadFile],
    parent_response_id: Optional[str],
) -> Tuple[ImageMetadata, bool, Optional[str], Optional[bytes]]:
    """
    Persists uploaded photo or retrieves parent photo for multimodal context.
    Returns: (image_metadata, image_stored, stored_img_filename, image_bytes)
    """
    image_metadata = ImageMetadata(has_image=False)
    image_stored = False
    stored_img_filename: Optional[str] = None
    image_bytes: Optional[bytes] = None

    if uploaded_image:
        image_bytes = await uploaded_image.read()
        if image_bytes:
            ext = Path(uploaded_image.filename).suffix.lstrip(".") or "jpg"
            stored_img_filename = await storage_repo.save_image(
                survey_id=survey_id,
                response_id=response_id,
                timestamp_str=timestamp_str,
                image_bytes=image_bytes,
                extension=ext,
            )

            img_id = "img_" + response_id[5:] if response_id.startswith("resp_") else f"img_{response_id}"
            image_metadata = ImageMetadata(
                has_image=True,
                image_id=img_id,
                image_filename=stored_img_filename,
                relative_path=f"images/{stored_img_filename}",
            )
            image_stored = True

    # If follow-up round without new image, pull parent photo for multimodal context
    if not image_bytes and parent_response_id:
        try:
            base_id = re.sub(r"_follow-up_\d+$", "", parent_response_id)
            parent_record = await storage_repo.get_response(survey_id, base_id)
            if parent_record and parent_record.image and parent_record.image.image_filename:
                parent_img = await storage_repo.get_image(survey_id, parent_record.image.image_filename)
                if parent_img:
                    image_bytes, _ = parent_img
        except Exception:
            pass

    return image_metadata, image_stored, stored_img_filename, image_bytes


async def _evaluate_adaptive_followup(
    llm_service: LLMService,
    survey: SurveyConfig,
    record: SurveyResponseRecord,
    current_round: int,
    image_bytes: Optional[bytes],
) -> Optional[FollowUpSurveyPayload]:
    """Evaluates and generates adaptive follow-up questions if enabled and within round limits."""
    if not (
        survey.adaptive_followup
        and survey.adaptive_followup.enabled
        and current_round < survey.adaptive_followup.max_followup_rounds
    ):
        return None

    return await llm_service.generate_adaptive_followup(
        survey=survey,
        response_record=record,
        round_number=current_round + 1,
        photo_bytes=image_bytes,
    )
