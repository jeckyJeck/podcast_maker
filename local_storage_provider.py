import shutil
import os
from pathlib import Path
from storage_provider import StorageProvider

class LocalStorageProvider(StorageProvider):
    def __init__(self, base_dir="output"):
        self.base_dir = base_dir
        os.makedirs(base_dir, exist_ok=True)

    def save_file(self, local_path: str, file_name: str) -> str:
        dest = os.path.join(self.base_dir, file_name)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.copy(local_path, dest)
        return dest