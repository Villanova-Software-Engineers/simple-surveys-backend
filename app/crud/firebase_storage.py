"""Firebase and Google Cloud Firestore Storage Repository.

Persists surveys, responses, sampling rules, and device tokens in Cloud Firestore (NoSQL).
Persists uploaded response photos directly in Google Cloud Storage.
This repository is 100% cloud-native and performs zero local filesystem operations.
Conforms strictly to BaseStorageRepository for drop-in polymorphic swapping.
"""

import asyncio
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import firebase_admin
from firebase_admin import credentials, storage
from google.cloud.firestore_v1.async_client import AsyncClient
from google.cloud.firestore_v1.base_query import FieldFilter
from google.oauth2 import service_account

from app.config import settings
from app.crud.base import BaseStorageRepository
from app.crud.file_storage import sanitize_filename
from app.schemas.notification_config import DeviceRegistration, SamplingRules
from app.schemas.survey_config import SurveyConfig
from app.schemas.survey_response import SurveyResponseRecord

logger = logging.getLogger("simple_surveys.storage.firebase")


class FirebaseStorageRepository(BaseStorageRepository):
    """
    Storage repository utilizing Google Cloud Firestore for JSON documents
    and Cloud Storage for media assets. Operates purely in the cloud with zero
    local filesystem dependencies.
    """

    def __init__(
        self,
        credentials_path: Optional[str] = None,
        credentials_json: Optional[str] = None,
        project_id: Optional[str] = None,
        storage_bucket: Optional[str] = None,
        database: Optional[str] = None,
    ):
        self.credentials_path = credentials_path or settings.firebase_credentials_path
        self.credentials_json = credentials_json or settings.firebase_credentials_json
        self.project_id = project_id or settings.firebase_project_id
        self.storage_bucket_name = storage_bucket or settings.firebase_storage_bucket
        self.database = database or settings.firestore_database

        self._firebase_app: Optional[firebase_admin.App] = None
        self._async_db: Optional[AsyncClient] = None
        self._storage_bucket: Optional[Any] = None

        self._initialize_clients()

    def _initialize_clients(self) -> None:
        """Initialize Firebase Admin app and Async Firestore client."""
        cred = None
        google_creds = None
        parsed_info: Optional[Dict[str, Any]] = None

        if self.credentials_json:
            try:
                parsed_info = json.loads(self.credentials_json)
                cred = credentials.Certificate(parsed_info)
                google_creds = service_account.Credentials.from_service_account_info(parsed_info)
                if not self.project_id and "project_id" in parsed_info:
                    self.project_id = parsed_info["project_id"]
            except Exception as e:
                logger.error("Failed to parse FIREBASE_CREDENTIALS_JSON: %s", e)

        if not cred and self.credentials_path:
            creds_file = Path(self.credentials_path)
            if creds_file.exists():
                try:
                    cred = credentials.Certificate(str(creds_file))
                    google_creds = service_account.Credentials.from_service_account_file(str(creds_file))
                    with open(creds_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        if not self.project_id and "project_id" in data:
                            self.project_id = data["project_id"]
                except Exception as e:
                    logger.error("Failed to load Firebase credentials from '%s': %s", creds_file, e)

        # Fallback to Application Default Credentials
        if not cred:
            logger.info("Using Google Application Default Credentials for Firebase...")
            try:
                cred = credentials.ApplicationDefault()
            except Exception as e:
                logger.warning("Could not obtain Application Default Credentials: %s", e)

        # Initialize firebase_admin default app if not already initialized
        try:
            if not firebase_admin._apps:
                app_options = {}
                if self.storage_bucket_name:
                    app_options["storageBucket"] = self.storage_bucket_name
                if self.project_id:
                    app_options["projectId"] = self.project_id

                if cred:
                    self._firebase_app = firebase_admin.initialize_app(cred, app_options)
                else:
                    self._firebase_app = firebase_admin.initialize_app(options=app_options)
            else:
                self._firebase_app = firebase_admin.get_app()
        except Exception as e:
            logger.warning("Firebase Admin app initialization notice: %s", e)

        # Initialize Async Firestore Client
        try:
            client_kwargs = {
                "project": self.project_id,
                "credentials": google_creds,
            }
            if self.database:
                client_kwargs["database"] = self.database

            self._async_db = AsyncClient(**client_kwargs)
        except Exception as e:
            logger.error("Failed to initialize AsyncClient for Firestore: %s", e)

        # Initialize Cloud Storage bucket reference
        if self._firebase_app and self.storage_bucket_name:
            try:
                self._storage_bucket = storage.bucket(
                    name=self.storage_bucket_name,
                    app=self._firebase_app,
                )
            except Exception as e:
                logger.warning("Could not bind Cloud Storage bucket '%s': %s", self.storage_bucket_name, e)

    @property
    def db(self) -> AsyncClient:
        """Provide active AsyncClient for Firestore."""
        if self._async_db is None:
            raise RuntimeError(
                "Firestore AsyncClient is not initialized. Ensure valid Google Cloud / Firebase credentials."
            )
        return self._async_db

    # ---------------- Survey Operations (Firestore) ----------------

    async def save_survey(self, survey: SurveyConfig) -> SurveyConfig:
        """Persist a survey definition in Firestore."""
        doc_id = sanitize_filename(survey.survey_id)
        doc_ref = self.db.collection("surveys").document(doc_id)
        payload = survey.model_dump(mode="json")
        await doc_ref.set(payload)
        return survey

    async def get_survey(self, survey_id: str) -> Optional[SurveyConfig]:
        """Retrieve a survey definition by unique ID from Firestore."""
        doc_id = sanitize_filename(survey_id)
        doc_ref = self.db.collection("surveys").document(doc_id)
        snapshot = await doc_ref.get()
        if not snapshot.exists:
            return None
        return SurveyConfig.model_validate(snapshot.to_dict())

    async def list_surveys(self, active_only: bool = False) -> List[SurveyConfig]:
        """List stored survey definitions from Firestore."""
        surveys: List[SurveyConfig] = []
        query = self.db.collection("surveys")
        if active_only:
            query = query.where(filter=FieldFilter("is_active", "==", True))

        async for doc in query.stream():
            try:
                surveys.append(SurveyConfig.model_validate(doc.to_dict()))
            except Exception as e:
                logger.warning("Error parsing survey doc '%s': %s", doc.id, e)
                continue

        surveys.sort(key=lambda s: s.survey_id)
        return surveys

    async def delete_survey(self, survey_id: str, delete_responses: bool = False) -> bool:
        """
        Delete a survey definition by ID from Firestore.
        Optionally deletes associated responses and Cloud Storage images.
        """
        doc_id = sanitize_filename(survey_id)
        doc_ref = self.db.collection("surveys").document(doc_id)
        snapshot = await doc_ref.get()
        if not snapshot.exists:
            return False

        await doc_ref.delete()

        if delete_responses:
            resp_query = self.db.collection("responses").where(filter=FieldFilter("survey_id", "==", survey_id))
            async for r_doc in resp_query.stream():
                data = r_doc.to_dict() or {}
                img_data = data.get("image") or {}
                filename = img_data.get("image_filename")
                if filename:
                    await self._delete_image_blob(survey_id, filename)
                await r_doc.reference.delete()

        return True

    # ---------------- Response Operations (Firestore) ----------------

    async def save_response(
        self,
        record: SurveyResponseRecord,
        timestamp_str: Optional[str] = None,
    ) -> SurveyResponseRecord:
        """Save a response record in Firestore."""
        doc_id = sanitize_filename(record.response_id)
        doc_ref = self.db.collection("responses").document(doc_id)
        payload = record.model_dump(mode="json")
        if timestamp_str:
            payload["_timestamp_str"] = timestamp_str
        await doc_ref.set(payload)
        return record

    async def get_response(self, survey_id: str, response_id: str) -> Optional[SurveyResponseRecord]:
        """Retrieve a specific response record from Firestore."""
        doc_id = sanitize_filename(response_id)
        doc_ref = self.db.collection("responses").document(doc_id)
        snapshot = await doc_ref.get()
        if not snapshot.exists:
            return None
        data = snapshot.to_dict() or {}
        if data.get("survey_id") != survey_id:
            return None
        data.pop("_timestamp_str", None)
        return SurveyResponseRecord.model_validate(data)

    async def list_responses(self, survey_id: Optional[str] = None) -> List[SurveyResponseRecord]:
        """List response records, optionally filtered by survey_id from Firestore."""
        results: List[SurveyResponseRecord] = []
        query = self.db.collection("responses")
        if survey_id:
            query = query.where(filter=FieldFilter("survey_id", "==", survey_id))

        async for doc in query.stream():
            try:
                data = doc.to_dict() or {}
                data.pop("_timestamp_str", None)
                results.append(SurveyResponseRecord.model_validate(data))
            except Exception as e:
                logger.warning("Error parsing response doc '%s': %s", doc.id, e)
                continue

        return results

    async def delete_response(
        self,
        survey_id: str,
        response_id: str,
        delete_image: bool = True,
    ) -> bool:
        """
        Delete a response record from Firestore and optionally its photo from Cloud Storage.
        """
        doc_id = sanitize_filename(response_id)
        doc_ref = self.db.collection("responses").document(doc_id)
        snapshot = await doc_ref.get()
        if not snapshot.exists:
            return False

        data = snapshot.to_dict() or {}
        if data.get("survey_id") != survey_id:
            return False

        if delete_image:
            img_data = data.get("image") or {}
            filename = img_data.get("image_filename")
            if filename:
                await self._delete_image_blob(survey_id, filename)

        await doc_ref.delete()
        return True

    # ---------------- Media / Images (Cloud Storage Only) ----------------

    async def save_image(
        self,
        survey_id: str,
        response_id: str,
        timestamp_str: str,
        image_bytes: bytes,
        extension: str = "jpg",
    ) -> str:
        """
        Upload an image directly into Cloud Storage (zero local disk writes).
        """
        if self._storage_bucket is None:
            raise RuntimeError("Cloud Storage bucket is not configured.")

        clean_ext = extension.lstrip(".").lower() or "jpg"
        if response_id.startswith("resp_"):
            img_id = "img_" + response_id[5:]
        else:
            img_id = f"img_{response_id}"

        clean_img_id = sanitize_filename(img_id)
        filename = f"{timestamp_str}_{clean_img_id}.{clean_ext}"

        content_type = "image/png" if clean_ext == "png" else "image/jpeg"
        blob_path = f"responses/{survey_id}/images/{filename}"

        def _upload() -> None:
            blob = self._storage_bucket.blob(blob_path)
            blob.upload_from_string(image_bytes, content_type=content_type)

        await asyncio.to_thread(_upload)
        return filename

    async def get_image(self, survey_id: str, filename: str) -> Optional[Tuple[bytes, str]]:
        """
        Fetch image bytes and content-type directly from Cloud Storage into memory.
        Zero files are ever created locally.
        """
        if self._storage_bucket is None:
            return None

        blob_path = f"responses/{survey_id}/images/{filename}"

        def _download() -> Optional[Tuple[bytes, str]]:
            blob = self._storage_bucket.blob(blob_path)
            if not blob.exists():
                return None
            data = blob.download_as_bytes()
            content_type = blob.content_type or ("image/png" if filename.lower().endswith(".png") else "image/jpeg")
            return data, content_type

        return await asyncio.to_thread(_download)

    async def _delete_image_blob(self, survey_id: str, filename: str) -> None:
        """Remove image blob directly from Cloud Storage."""
        if self._storage_bucket is None:
            return

        blob_path = f"responses/{survey_id}/images/{filename}"

        def _delete() -> None:
            blob = self._storage_bucket.blob(blob_path)
            if blob.exists():
                blob.delete()

        try:
            await asyncio.to_thread(_delete)
        except Exception as e:
            logger.warning("Could not delete blob '%s' from Cloud Storage: %s", blob_path, e)

    # ---------------- Schedule Configuration (Firestore) ----------------

    async def get_schedule_config(self) -> Optional[SamplingRules]:
        """Retrieve the current sampling rules configuration from Firestore."""
        doc_ref = self.db.collection("config").document("sampling_rules")
        snapshot = await doc_ref.get()
        if not snapshot.exists:
            return None
        return SamplingRules.model_validate(snapshot.to_dict())

    async def save_schedule_config(self, config: SamplingRules) -> SamplingRules:
        """Persist updated sampling rules configuration in Firestore."""
        doc_ref = self.db.collection("config").document("sampling_rules")
        await doc_ref.set(config.model_dump(mode="json"))
        return config

    # ---------------- Device Registrations (Firestore) ----------------

    async def save_device(self, device: DeviceRegistration) -> DeviceRegistration:
        """Save a registered device token in Firestore."""
        clean_token = sanitize_filename(device.device_token)
        doc_ref = self.db.collection("devices").document(clean_token)
        await doc_ref.set(device.model_dump(mode="json"))
        return device

    async def list_devices(self) -> List[DeviceRegistration]:
        """List all registered devices in Firestore."""
        devices: List[DeviceRegistration] = []
        async for doc in self.db.collection("devices").stream():
            try:
                devices.append(DeviceRegistration.model_validate(doc.to_dict()))
            except Exception as e:
                logger.warning("Error parsing device doc '%s': %s", doc.id, e)
                continue
        return devices

    async def get_device(self, device_token: str) -> Optional[DeviceRegistration]:
        """Retrieve a registered device by token from Firestore."""
        clean_token = sanitize_filename(device_token)
        doc_ref = self.db.collection("devices").document(clean_token)
        snapshot = await doc_ref.get()
        if not snapshot.exists:
            return None
        return DeviceRegistration.model_validate(snapshot.to_dict())

    async def delete_device(self, device_token: str) -> bool:
        """Delete a registered device by token from Firestore."""
        clean_token = sanitize_filename(device_token)
        doc_ref = self.db.collection("devices").document(clean_token)
        snapshot = await doc_ref.get()
        if not snapshot.exists:
            return False
        await doc_ref.delete()
        return True
