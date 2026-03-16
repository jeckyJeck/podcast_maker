import os

from podcast_maker.services.storage_provider import StorageProvider
from podcast_maker.services.supabase.supabase_client import get_supabase_client


class SupabaseStorageProvider(StorageProvider):
    def __init__(self, path_prefix: str = ""):
        self.client = get_supabase_client()
        self.bucket_name = self.require_env("SUPABASE_STORAGE_BUCKET")
        if not self.bucket_name:
            raise RuntimeError("SUPABASE_STORAGE_BUCKET not set in environment.")
        
        self.path_prefix = path_prefix.strip("/")

    def _build_storage_path(self, file_name: str) -> str:
        normalized_path = file_name.replace("\\", "/")
        if self.path_prefix:
            return f"{self.path_prefix}/{normalized_path}"
        return normalized_path
    
    def require_env(self, key: str) -> str:
        value = os.getenv(key)
        if not value:
            raise RuntimeError(f"{key} not set in environment.")
        return value

    def save_file(self, local_path: str, file_name: str) -> str:
        storage_path = self._build_storage_path(file_name)
        with open(local_path, "rb") as file_stream:
            self.client.storage.from_(self.bucket_name).upload(
                storage_path,
                file_stream,
                {
                    "upsert": "true",
                },
            )

        return self.client.storage.from_(self.bucket_name).get_public_url(storage_path)
