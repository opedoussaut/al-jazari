# Deployment

## Local (default)

See the [README quick start](../../README.md#quick-start-windows-macos-linux). Everything
runs on the user's machine: Ollama, the FastAPI backend on `127.0.0.1:8000`, and the Vite
dev server on `localhost:5173`. No cloud account is needed.

## Local with Docker Compose

`docker-compose.yml` builds the backend (Python 3.12, uv) and serves the built frontend
with nginx, which proxies `/api` to the backend. Ollama stays on the host:

```bash
docker compose up --build
```

The compose file sets `JAZARI_OLLAMA_URL=http://host.docker.internal:11434`. The
`jazari-data` volume keeps fetched sources and generated graphs. On first start the
backend runs `jazari fetch && jazari build && jazari validate`.

> Status: written but **not yet tested**. The Docker daemon was not running on the
> development machine during M2.

## Public hosting (design, not yet implemented)

GitHub Pages can host only the static frontend. A working public chat needs an
inference backend somewhere else. Recommended shape:

```
Browser ─► CDN/static (frontend) ─► API gateway (TLS, auth, rate limit) ─► JAZARI backend (read-only)
                                                                         └─► private Ollama / GPU host (never public)
```

Requirements before going public:

- Separate config profile (`.env.public`): restricted `JAZARI_CORS_ORIGINS`, fallback
  disabled or rate-limited, model timeout and request size caps.
- Authentication (API keys or OAuth) and per-key rate limits at the gateway.
- Ollama bound to a private network only. Never expose `:11434`.
- Graph stays read-only: the API has no update endpoints, and SPARQL Update and `SERVICE`
  are refused in `GraphStore.select`.
- Session memory is in-process and capped (200 sessions). Use an external store if you
  run several replicas.
- Logs must not store user questions longer than needed. Publish a privacy note.
