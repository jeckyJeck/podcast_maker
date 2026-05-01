from abc import ABC, abstractmethod

class StorageProvider(ABC):
    @abstractmethod
    def save_file(self, local_path: str, file_name: str) -> str:
        """Saves a file and returns the public URL or local path"""
        pass