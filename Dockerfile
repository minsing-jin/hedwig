# syntax=docker/dockerfile:1
FROM python:3.12-slim

WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast pip
RUN pip install --no-cache-dir uv

# Copy project
COPY pyproject.toml ./
COPY hedwig ./hedwig
COPY migrations ./migrations
COPY README.md ./

# Install
RUN uv pip install --system -e .

ENV PYTHONUNBUFFERED=1
ENV PORT=8765

EXPOSE 8765

CMD ["python", "-m", "hedwig", "--dashboard", "--saas", "--port", "8765"]
