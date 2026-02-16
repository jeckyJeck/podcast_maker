from fastapi import FastAPI, BackgroundTasks
from podcast_maker_orchestrator import PodcastMakerOrchestrator
from google_cloud_storage_provider import GoogleCloudStorageProvider
from dotenv import load_dotenv
import os
import uuid

load_dotenv()
BUCKET_NAME = os.getenv("BUCKET_NAME")
app = FastAPI()

@app.post("/create-podcast/")
async def create_podcast(topic: str, background_tasks: BackgroundTasks):
    task_id = str(uuid.uuid4())
    
    # We use BackgroundTasks because a 60-min audio will take time
    background_tasks.add_task(run_orchestrator, topic, task_id)
    
    return {"status": "processing", "task_id": task_id, "message": "Check back later for the link"}

@app.get("/")
def health_check():
    return {"status": "alive"}

def run_orchestrator(topic: str, task_id: str):
    storage_provider = GoogleCloudStorageProvider(bucket_name=BUCKET_NAME)
    orchestrator = PodcastMakerOrchestrator(topic, storage_provider)
    # Inside process_topic, you should modify it to upload to S3/GCS
    # instead of just saving it to a local folder.
    output_url = orchestrator.process_topic(topic)
    print(f"Task {task_id} finished. URL: {output_url}")