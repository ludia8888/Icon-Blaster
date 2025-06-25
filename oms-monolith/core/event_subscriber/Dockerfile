FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements file
COPY requirements-minimal.txt ./requirements.txt

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY . .

# Set Python path to help with module resolution
ENV PYTHONPATH=/app:/app/services:/app/shared

# Change to service directory
WORKDIR /app/services/event-subscriber

# Run the service
CMD ["python", "main_simple.py"]