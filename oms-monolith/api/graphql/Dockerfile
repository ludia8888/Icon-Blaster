FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements file
COPY requirements.txt ./requirements.txt

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY . .

# Set Python path to help with module resolution
ENV PYTHONPATH=/app:/app/services:/app/shared

# Change to service directory
WORKDIR /app/services/graphql-service

# Expose port
EXPOSE 8004

# Run the service
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8004"]