FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements files
COPY requirements.txt /app/
COPY shaketune/webservice/requirements.txt /app/webservice-requirements.txt

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt -r webservice-requirements.txt

# Copy the shaketune directory
COPY shaketune/ /app/shaketune/

# Set working directory to webservice
WORKDIR /app/shaketune/webservice

# Run with gunicorn
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "app:app"]
