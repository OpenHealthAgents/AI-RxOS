# Commands

Common commands for development, validation, and deployment.

## Run locally

```bash
cd services/literature
python -m uvicorn app.main:app --host 0.0.0.0 --port 8082
```

## Run tests

```bash
cd services/literature
python -m pytest -q
```

## Static analysis

```bash
cd services/literature
python -m ruff check app
python -m ruff format --check app
python -m mypy app --ignore-missing-imports
```

## Docker

Build the image:

```bash
docker build -t ai-rxos-literature -f services/literature/Dockerfile services/literature
```

Run the container:

```bash
docker run -p 8082:8082 \
  -e DATABASE_URL="postgresql://user:password@postgres:5432/ai_rxos" \
  -e JWT_SECRET="<secure-secret>" \
  -e SEARCH_SERVICE_URL="http://search:8084" \
  -e KG_SERVICE_URL="http://kg:8083" \
  -e LLMWIKI_SERVICE_URL="http://llmwiki:8086" \
  ai-rxos-literature
```

## Readiness and health

```bash
curl http://localhost:8082/health
curl http://localhost:8082/ready
curl http://localhost:8082/metrics/prometheus
```

## JWT generation

This service expects HS256 JWT tokens signed with `JWT_SECRET`.
Use your preferred JWT tooling or helper library to create tokens for local testing.

## Troubleshooting logs

Inspect container logs or service terminal output for startup errors and lifecycle issues.
