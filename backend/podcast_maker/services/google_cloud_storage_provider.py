import datetime

from google.cloud import storage

from podcast_maker.core.paths import BACKEND_ROOT
from podcast_maker.services.storage_provider import StorageProvider


class GoogleCloudStorageProvider(StorageProvider):
    def __init__(self, bucket_name):
        self.client = storage.Client() # Assumes credentials are set in environment
        self.bucket = self.client.bucket(bucket_name)

    def save_file(self, local_path: str, file_name: str) -> str:
        blob = self.bucket.blob(file_name)
        blob.upload_from_filename(local_path)
        
        # Create a Signed URL (valid for 1 hour)
        url = blob.generate_signed_url(
            version="v4",
            expiration=datetime.timedelta(hours=1),
            method="GET"
        )
        return url
    
if __name__ == "__main__":
    from dotenv import load_dotenv
    import os
    # 1. Load the .env file (make sure your JSON path is defined there)
    load_dotenv(dotenv_path=BACKEND_ROOT / ".env")
    
    name = os.getenv("BUCKET_NAME")
    # 2. Check if the credential variable is set
    creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if not creds_path:
        print("Error: GOOGLE_APPLICATION_CREDENTIALS not found in environment.")
    else:
        print(f"Using credentials from: {creds_path}")

    # 3. Initialize provider (Change bucket_name if yours is different)
    provider = GoogleCloudStorageProvider(bucket_name=name)

    # 4. Create a dummy test file
    test_file_path = "test_upload.txt"
    with open(test_file_path, "w") as f:
        f.write("This is a test upload to Google Cloud Storage!")

    print(f"Attempting to upload to bucket: {name}...")

    try:
        # 5. Try to upload
        # We'll save it under a 'test/' folder in the bucket
        signed_url = provider.save_file(test_file_path, "test/test_file.txt")
        
        print("\n--- Success! ---")
        print(f"File uploaded successfully.")
        print(f"Click the link to download (valid for 1 hour):")
        print(signed_url)
        print("----------------\n")

    except Exception as e:
        print("\n--- Upload Failed ---")
        print(f"Error details: {e}")
        print("Check if your bucket name is correct and service account has 'Storage Object Admin' role.")
    
    finally:
        # 6. Cleanup local test file
        if os.path.exists(test_file_path):
            os.remove(test_file_path)