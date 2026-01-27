FROM python:3.11-slim

# Install system dependencies required for WeasyPrint and compilation
RUN apt-get update && apt-get install -y \
    build-essential \
    python3-dev \
    python3-cffi \
    python3-brotli \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libharfbuzz-subset0 \
    libjpeg-dev \
    libopenjp2-7-dev \
    libffi-dev \
    shared-mime-info \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements first to leverage Docker cache
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# Create directories for data persistence and logs
RUN mkdir -p /app/Games /app/Output /app/uploads /app/instance

# Make entrypoint executable
RUN chmod +x entrypoint.sh

# Expose the application port
EXPOSE 8080

# Use the entrypoint script to run migrations and start the server
CMD ["./entrypoint.sh"]
