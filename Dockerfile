# STAGE 1: Rust Builder
FROM rust:1.80-slim-bullseye AS rust-builder

RUN apt-get update && apt-get install -y \
    python3-dev \
    python3-pip \
    python3-venv \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY basketball_stats_rust ./basketball_stats_rust

# Install maturin to build the python wheel
RUN pip3 install maturin

# Build the Rust library into a Python wheel
RUN cd basketball_stats_rust && \
    maturin build --release --out ../dist

# STAGE 2: Final Image
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

# Copy requirements first
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy and install the Rust wheel from the builder stage
COPY --from=rust-builder /build/dist/*.whl /tmp/
RUN pip install /tmp/*.whl && rm -rf /tmp/*.whl

# Copy the rest of the application
COPY . .

# Create directories for data persistence and logs
RUN mkdir -p /app/Games /app/Output /app/uploads /app/instance

# Make entrypoint executable
RUN chmod +x entrypoint.sh

# Set the FLASK_APP environment variable explicitly
ENV FLASK_APP=run.py

# Expose the application port
EXPOSE 8080

# Use the entrypoint script to run migrations and start the server
CMD ["./entrypoint.sh"]
