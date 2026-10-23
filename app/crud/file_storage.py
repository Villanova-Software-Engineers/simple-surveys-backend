"""Local filesystem storage repository implementation."""

import re
import shutil
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional
import aiofiles
import aiofiles.os

from app.config import settings
from app.crud.base import BaseStorageRepository
from app.schemas.notification_config import (
    DeviceRegistration,
    SamplingRules,
)
from app.schemas.survey_config import SurveyConfig
from app.schemas.survey_response import SurveyResponseRecord

logger = logging.getLogger("simple_surveys.storage.file")


def format_filename_timestamp(dt: Optional[datetime] = None) -> str:
    """Format datetime into filesystem-safe ISO string: YYYY-MM-DDTHH-MM-SS."""
    if dt is None:
        dt = datetime.now(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H-%M-%S")


def sanitize_filename(name: str) -> str:
    """Sanitize filename to prevent directory traversal and invalid characters."""
    return re.sub(r'[^a-zA-Z0-9_\-\.]', '_', name)


class FileStorageRepository(BaseStorageRepository):
    """Persists surveys, responses, images, and config to designated server directories."""

    def __init__(self, data_dir: Optional[Path] = None):
        self.data_dir = data_dir
        self.surveys_dir = settings.surveys_dir
        self.schedule_config_dir = settings.schedule_config_dir
        self.responses_dir = settings.responses_dir
        self.devices_dir = settings.devices_dir

        self._ensure_directories()

    def _ensure_directories(self) -> None:
        """Create baseline directories once during initialization."""
        for path in [
            self.surveys_dir,
            self.schedule_config_dir,
            self.responses_dir,
            self.devices_dir,
        ]:
            path.mkdir(parents=True, exist_ok=True)

    # ---------------- Survey Operations ----------------

    async def save_survey(self, survey: SurveyConfig) -> SurveyConfig:
        """Persist survey definition as JSON."""
        clean_id = sanitize_filename(survey.survey_id)
        file_path = self.surveys_dir / f"{clean_id}.json"
        file_path.parent.mkdir(parents=True, exist_ok=True)

        content = survey.model_dump_json(indent=2)
        async with aiofiles.open(file_path, "w", encoding="utf-8") as f:
            await f.write(content)
        return survey

    async def get_survey(self, survey_id: str) -> Optional[SurveyConfig]:
        """Load survey definition by ID."""
        clean_id = sanitize_filename(survey_id)
        file_path = self.surveys_dir / f"{clean_id}.json"
        if not file_path.exists():
            return None
        async with aiofiles.open(file_path, "r", encoding="utf-8") as f:
            raw = await f.read()
        return SurveyConfig.model_validate_json(raw)

    async def list_surveys(self, active_only: bool = False) -> List[SurveyConfig]:
        """List surveys in surveys directory."""
        surveys: List[SurveyConfig] = []
        if not self.surveys_dir.exists():
            return surveys

        for file_path in sorted(self.surveys_dir.glob("*.json")):
            try:
                async with aiofiles.open(file_path, "r", encoding="utf-8") as f:
                    raw = await f.read()
                survey = SurveyConfig.model_validate_json(raw)
                if not active_only or survey.is_active:
                    surveys.append(survey)
            except Exception:
                continue
        return surveys

    async def delete_survey(self, survey_id: str, delete_responses: bool = False) -> bool:
        """
        Delete a survey definition file and optionally its responses folder.
        Returns True if deleted, False if not found.
        """
        clean_id = sanitize_filename(survey_id)
        file_path = self.surveys_dir / f"{clean_id}.json"
        if not file_path.exists():
            return False

        await aiofiles.os.remove(file_path)

        if delete_responses:
            survey_resp_dir = self.responses_dir / clean_id
            if survey_resp_dir.exists():
                shutil.rmtree(survey_resp_dir, ignore_errors=True)

        return True

    # ---------------- Response Operations ----------------

    def _get_survey_data_dir(self, survey_id: str) -> Path:
        clean_id = sanitize_filename(survey_id)
        path = self.responses_dir / clean_id / "data"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _get_survey_images_dir(self, survey_id: str) -> Path:
        clean_id = sanitize_filename(survey_id)
        path = self.responses_dir / clean_id / "images"
        path.mkdir(parents=True, exist_ok=True)
        return path

    async def save_response(
        self,
        record: SurveyResponseRecord,
        timestamp_str: Optional[str] = None
    ) -> SurveyResponseRecord:
        """Save a response record as JSON in data/responses/{survey_id}/data/."""
        data_dir = self._get_survey_data_dir(record.survey_id)
        if not timestamp_str:
            dt = (
                record.temporal_markers.completed_at
                or record.temporal_markers.received_at
                or datetime.now(timezone.utc)
            )
            timestamp_str = format_filename_timestamp(dt)

        resp_clean_id = sanitize_filename(record.response_id)
        filename = f"{timestamp_str}_{resp_clean_id}.json"
        file_path = data_dir / filename

        content = record.model_dump_json(indent=2)
        async with aiofiles.open(file_path, "w", encoding="utf-8") as f:
            await f.write(content)

        return record

    async def get_response(self, survey_id: str, response_id: str) -> Optional[SurveyResponseRecord]:
        """Find a response record by response_id inside a survey's data folder."""
        data_dir = self._get_survey_data_dir(survey_id)
        clean_resp_id = sanitize_filename(response_id)
        pattern = f"*_{clean_resp_id}.json"
        matching_files = list(data_dir.glob(pattern))
        if not matching_files:
            # Fallback to direct check if response_id is full filename
            direct = data_dir / f"{clean_resp_id}.json"
            if direct.exists():
                matching_files = [direct]
            else:
                return None

        async with aiofiles.open(matching_files[0], "r", encoding="utf-8") as f:
            raw = await f.read()
        return SurveyResponseRecord.model_validate_json(raw)

    async def list_responses(self, survey_id: Optional[str] = None) -> List[SurveyResponseRecord]:
        """List responses for a specific survey or across all surveys."""
        results: List[SurveyResponseRecord] = []
        target_dirs: List[Path] = []

        if survey_id:
            target_dirs.append(self._get_survey_data_dir(survey_id))
        elif self.responses_dir.exists():
            for s_dir in self.responses_dir.iterdir():
                if s_dir.is_dir():
                    data_sub = s_dir / "data"
                    if data_sub.exists():
                        target_dirs.append(data_sub)

        for d in target_dirs:
            for file_path in sorted(d.glob("*.json")):
                try:
                    async with aiofiles.open(file_path, "r", encoding="utf-8") as f:
                        raw = await f.read()
                    results.append(SurveyResponseRecord.model_validate_json(raw))
                except Exception:
                    continue

        return results

    async def delete_response(
        self,
        survey_id: str,
        response_id: str,
        delete_image: bool = True
    ) -> bool:
        """
        Delete a response record and optionally its associated image.
        Returns True if deleted, False if not found.
        """
        data_dir = self._get_survey_data_dir(survey_id)
        clean_resp_id = sanitize_filename(response_id)
        pattern = f"*_{clean_resp_id}.json"
        matching_files = list(data_dir.glob(pattern))
        if not matching_files:
            direct = data_dir / f"{clean_resp_id}.json"
            if direct.exists():
                matching_files = [direct]
            else:
                return False

        if delete_image:
            try:
                async with aiofiles.open(matching_files[0], "r", encoding="utf-8") as f:
                    raw = await f.read()
                record = SurveyResponseRecord.model_validate_json(raw)
                if record.image and record.image.image_filename:
                    img_path = await self.get_image_path(survey_id, record.image.image_filename)
                    if img_path and img_path.exists():
                        await aiofiles.os.remove(img_path)
            except Exception:
                pass

        await aiofiles.os.remove(matching_files[0])
        return True

    # ---------------- Image Operations ----------------

    async def save_image(
        self,
        survey_id: str,
        response_id: str,
        timestamp_str: str,
        image_bytes: bytes,
        extension: str = "jpg"
    ) -> str:
        """
        Saves image with filename {timestamp}_img_{id}.jpg mirroring the response record.
        """
        images_dir = self._get_survey_images_dir(survey_id)
        clean_ext = extension.lstrip(".").lower()
        if not clean_ext:
            clean_ext = "jpg"

        if response_id.startswith("resp_"):
            img_id = "img_" + response_id[5:]
        else:
            img_id = f"img_{response_id}"

        clean_img_id = sanitize_filename(img_id)
        filename = f"{timestamp_str}_{clean_img_id}.{clean_ext}"
        file_path = images_dir / filename

        async with aiofiles.open(file_path, "wb") as f:
            await f.write(image_bytes)

        return filename

    async def get_image_path(self, survey_id: str, filename: str) -> Optional[Path]:
        """Retrieve path to stored image file."""
        images_dir = self._get_survey_images_dir(survey_id)
        clean_name = sanitize_filename(filename)
        file_path = images_dir / clean_name
        if file_path.exists():
            return file_path
        return None

    # ---------------- Schedule Configuration ----------------

    async def get_schedule_config(self) -> Optional[SamplingRules]:
        """
        Read schedule rules from data/schedule_config/sampling_rules.json.
        Returns None if not configured.
        """
        config_file = self.schedule_config_dir / "sampling_rules.json"
        if not config_file.exists():
            return None

        async with aiofiles.open(config_file, "r", encoding="utf-8") as f:
            raw = await f.read()
        return SamplingRules.model_validate_json(raw)

    async def save_schedule_config(self, config: SamplingRules) -> SamplingRules:
        """Save schedule rules to data/schedule_config/sampling_rules.json."""
        config_file = self.schedule_config_dir / "sampling_rules.json"
        config_file.parent.mkdir(parents=True, exist_ok=True)

        content = config.model_dump_json(indent=2)
        async with aiofiles.open(config_file, "w", encoding="utf-8") as f:
            await f.write(content)
        return config

    # ---------------- Device Registrations ----------------

    async def save_device(self, device: DeviceRegistration) -> DeviceRegistration:
        """Save registered device token."""
        clean_token = sanitize_filename(device.device_token)
        device_file = self.devices_dir / f"{clean_token}.json"
        device_file.parent.mkdir(parents=True, exist_ok=True)

        content = device.model_dump_json(indent=2)
        async with aiofiles.open(device_file, "w", encoding="utf-8") as f:
            await f.write(content)
        return device

    async def list_devices(self) -> List[DeviceRegistration]:
        """List registered device records."""
        devices: List[DeviceRegistration] = []
        if not self.devices_dir.exists():
            return devices

        for file_path in self.devices_dir.glob("*.json"):
            try:
                async with aiofiles.open(file_path, "r", encoding="utf-8") as f:
                    raw = await f.read()
                devices.append(DeviceRegistration.model_validate_json(raw))
            except Exception:
                continue
        return devices

    async def get_device(self, device_token: str) -> Optional[DeviceRegistration]:
        """Retrieve a registered device by token."""
        clean_token = sanitize_filename(device_token)
        device_file = self.devices_dir / f"{clean_token}.json"
        if not device_file.exists():
            return None
        async with aiofiles.open(device_file, "r", encoding="utf-8") as f:
            raw = await f.read()
        return DeviceRegistration.model_validate_json(raw)

    async def delete_device(self, device_token: str) -> bool:
        """
        Delete a registered device by token.
        Returns True if deleted, False if not found.
        """
        clean_token = sanitize_filename(device_token)
        device_file = self.devices_dir / f"{clean_token}.json"
        if not device_file.exists():
            return False

        await aiofiles.os.remove(device_file)
        return True
