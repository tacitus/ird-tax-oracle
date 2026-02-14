FROM python:3.12-slim

WORKDIR /app

# System deps for psycopg2 and pymupdf
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps (including dev tools)
COPY pyproject.toml .
RUN pip install --no-cache-dir ".[dev]"

# Copy application
COPY . .

EXPOSE 8000
CMD ["uvicorn", "src.api.app:create_app", "--host", "0.0.0.0", "--port", "8000", "--factory"]
