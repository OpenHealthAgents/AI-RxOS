FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1     PYTHONUNBUFFERED=1     PIP_NO_CACHE_DIR=1
WORKDIR /app

FROM base AS deps
COPY services/agents/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

FROM deps AS runtime
RUN useradd --create-home --uid 1000 rxos
COPY services/agents/app ./app
USER rxos
EXPOSE 8085
ENV PORT=8085
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
