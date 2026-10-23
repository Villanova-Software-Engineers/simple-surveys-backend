"""Storage repositories package."""

from app.crud.base import BaseStorageRepository
from app.crud.file_storage import FileStorageRepository
from app.crud.firebase_storage import FirebaseStorageRepository
from app.crud.ms_graph_storage import MSGraphStorageRepository

__all__ = [
    "BaseStorageRepository",
    "FileStorageRepository",
    "FirebaseStorageRepository",
    "MSGraphStorageRepository",
]
