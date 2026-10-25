FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.5.11 /uv /usr/local/bin/uv
WORKDIR /app
COPY backend/pyproject.toml backend/uv.lock backend/
RUN cd backend && uv sync --frozen --no-dev --no-install-project
COPY backend backend
COPY ontology ontology
COPY knowledge-graphs/manifests knowledge-graphs/manifests
COPY knowledge-graphs/queries knowledge-graphs/queries
RUN cd backend && uv sync --frozen --no-dev
ENV JAZARI_REPO_ROOT=/app
EXPOSE 8000
CMD ["sh", "-c", "cd backend && uv run --no-dev jazari fetch && uv run --no-dev jazari build && uv run --no-dev jazari validate; uv run --no-dev uvicorn jazari.api.app:app --host 0.0.0.0 --port 8000"]
