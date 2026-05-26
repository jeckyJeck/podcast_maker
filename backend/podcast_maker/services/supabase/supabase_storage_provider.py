import os
from podcast_maker.services.storage_provider import StorageProvider
from podcast_maker.services.supabase.supabase_client import get_supabase_client
from podcast_maker.core.logging_config import get_logger
from podcast_maker.services.retry import retry_network_call

logger = get_logger()


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
        """Save file with retry logic and exponential backoff.
        
        Args:
            local_path: Path to local file
            file_name: Target path in storage
            
        Returns:
            Public URL of uploaded file
        """
        storage_path = self._build_storage_path(file_name)
        def upload() -> None:
            with open(local_path, "rb") as file_stream:
                self.client.storage.from_(self.bucket_name).upload(
                    storage_path,
                    file_stream,
                    {
                        "upsert": "true",
                    },
                )

        retry_network_call(f"supabase.storage.upload.{file_name}", upload)
        logger.info(f"File uploaded successfully file={file_name}")
        return self.client.storage.from_(self.bucket_name).get_public_url(storage_path)
