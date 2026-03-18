FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libmagic1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Non-root user for security
RUN useradd -m -u 1000 -s /bin/bash aurascript

# Install Python deps before copying code (layer cache optimisation).
# requirements.txt lives inside the aurascript/ package directory.
COPY aurascript/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the entire aurascript package and supporting project files.
COPY --chown=aurascript:aurascript aurascript/ ./aurascript/
COPY --chown=aurascript:aurascript logging.json .

# Create temp directories with correct ownership.
RUN mkdir -p /tmp/aurascript/uploads /tmp/aurascript/chunks \
    && chown -R aurascript:aurascript /tmp/aurascript

USER aurascript

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
  CMD curl -f http://localhost:8080/health || exit 1

# aurascript.main:app — fully-qualified because main.py lives inside
# the aurascript package and all internal imports use from aurascript.x
CMD ["uvicorn", "aurascript.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8080", \
     "--workers", "1", \
     "--loop", "uvloop", \
     "--http", "httptools", \
     "--log-config", "logging.json"]
