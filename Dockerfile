FROM node:22.23.2-bookworm-slim AS web-build
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --include=dev --include=optional
COPY frontend/ ./
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

FROM ghcr.io/astral-sh/uv:0.12.17 AS uv
FROM python:3.12.14-slim-bookworm AS runtime
ENV PYTHONUNBUFFERED=1 UV_PYTHON_DOWNLOADS=never \
    PLAYWRIGHT_BROWSERS_PATH=/opt/playwright NEXT_TELEMETRY_DISABLED=1 \
    NODE_ENV=production
WORKDIR /app
COPY --from=uv /uv /usr/local/bin/uv
COPY --from=web-build /usr/local/bin/node /usr/local/bin/node
COPY backend/ ./backend/
RUN uv sync --locked --no-dev --no-build --directory backend
COPY --from=web-build /app/frontend/ ./frontend/
RUN node frontend/node_modules/playwright/cli.js install --with-deps chromium --only-shell \
    && apt-get update && apt-get install -y --no-install-recommends fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*
COPY Design/ ./Design/
COPY scripts/run_deployed.py ./scripts/run_deployed.py
RUN useradd --create-home --uid 10001 dudri && chown -R dudri:dudri /app
ENV PATH="/app/backend/.venv/bin:${PATH}"
USER dudri
EXPOSE 10000
ENTRYPOINT ["python", "/app/scripts/run_deployed.py"]

FROM runtime AS validation
RUN uv sync --locked --no-build --directory backend
RUN DUDRI_ENVIRONMENT=test uv run --no-sync --directory backend pytest -q

FROM runtime AS production
