FROM python:3.11-slim

LABEL org.opencontainers.image.source="https://github.com/JamesDimonaco/composure"
LABEL org.opencontainers.image.description="Docker-Compose optimizer and TUI dashboard"
LABEL org.opencontainers.image.licenses="MIT"

WORKDIR /app

# Install dependencies first (better caching)
COPY pyproject.toml uv.lock ./
COPY src ./src

# Install uv and the package
RUN pip install --no-cache-dir uv && \
    uv sync --frozen --no-dev

# Run composure
ENTRYPOINT ["uv", "run", "composure"]
