FROM python:3.13-slim AS base

# System dependencies for psycopg (libpq) and trimesh
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY . .

# Make entrypoint executable
RUN chmod +x entrypoint.sh

EXPOSE 8000

# Default: run the API via the entrypoint (which migrates first)
ENTRYPOINT ["./entrypoint.sh"]
CMD ["api"]
