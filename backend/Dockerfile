# Use a lightweight Python image
FROM python:3.11-slim

# Install system dependencies (like ffmpeg if your library uses it)
RUN apt-get update && apt-get install -y ffmpeg && rm -rf /var/lib/apt/lists/*

# Set the working directory inside the container
WORKDIR /app

# Copy your requirements file first (for better caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of your code
COPY . .

# Expose the port FastAPI runs on
EXPOSE 8080
# Set environment variable to ensure output is sent straight away
ENV PYTHONUNBUFFERED=1
# Command to run the server
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]