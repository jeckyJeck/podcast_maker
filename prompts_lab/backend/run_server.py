"""
Startup script for the FastAPI developer server.
"""

import os
import uvicorn

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    print(f"Starting Prompts Lab Backend on port {port}...")
    uvicorn.run("app.main:app", host="127.0.0.1", port=port, reload=True)
