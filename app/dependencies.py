"""Dependency injection providers for FastAPI."""

from functools import lru_cache
from typing import Annotated
from fastapi import Depends

from app.config import settings
from app.crud.base import BaseStorageRepository
lazy from app.crud.file_storage import FileStorageRepository
lazy from app.crud.firebase_storage import FirebaseStorageRepository
lazy from app.crud.ms_graph_storage import MSGraphStorageRepository
from app.services.dispatchers.base import BaseNotificationDispatcher
from app.services.dispatchers.push_dispatcher import PushNotificationDispatcher
from app.services.scheduler_service import SchedulerService


@lru_cache()
def get_storage_repository() -> BaseStorageRepository:
    """Provides singleton persistence repository according to configuration."""
    if settings.storage_backend == "firebase":
        return FirebaseStorageRepository(
            credentials_path=settings.firebase_credentials_path,
            credentials_json=settings.firebase_credentials_json,
            project_id=settings.firebase_project_id,
            storage_bucket=settings.firebase_storage_bucket,
            database=settings.firestore_database,
        )
    if settings.storage_backend == "ms_graph":
        return MSGraphStorageRepository()
    return FileStorageRepository(data_dir=settings.data_dir)


@lru_cache()
def get_notification_dispatcher() -> BaseNotificationDispatcher:
    """Provides singleton notification delivery dispatcher."""
    return PushNotificationDispatcher()


@lru_cache()
def get_scheduler_service() -> SchedulerService:
    """Provides singleton scheduler and validation service."""
    repo = get_storage_repository()
    dispatcher = get_notification_dispatcher()
    return SchedulerService(
        repository=repo,
        dispatcher=dispatcher,
        tz_name=settings.scheduler_timezone,
    )


StorageRepoDep = Annotated[BaseStorageRepository, Depends(get_storage_repository)]
DispatcherDep = Annotated[BaseNotificationDispatcher, Depends(get_notification_dispatcher)]
SchedulerServiceDep = Annotated[SchedulerService, Depends(get_scheduler_service)]
