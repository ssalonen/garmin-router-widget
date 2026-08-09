FROM python:3.14-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev
COPY . .

# Persist the garth token blob outside the container filesystem so /setup
# survives restarts. Mount a volume at /data.
ENV GARMIN_TOKEN_FILE=/data/garmin_tokens.blob
VOLUME ["/data"]

EXPOSE 8000
# IMPORTANT: keep a single worker. The MFA continuation and the cached Garmin
# session are in-memory, per-process — with --workers > 1 the MFA code POST can
# hit a different worker than the login POST and fail intermittently.
CMD ["uv", "run", "--no-dev", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
