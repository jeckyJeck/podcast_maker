import shutil
from pathlib import Path

from podcast_maker.core.paths import OUTPUT_DIR
from podcast_maker.services.storage_provider import StorageProvider

class LocalStorageProvider(StorageProvider):
    def __init__(self, base_dir: Path | str = OUTPUT_DIR):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def save_file(self, local_path: str, file_name: str) -> str:
        dest = self.base_dir / file_name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(local_path, dest)
        return str(dest)