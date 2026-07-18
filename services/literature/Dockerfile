FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1     PYTHONUNBUFFERED=1     PIP_NO_CACHE_DIR=1
WORKDIR /app

FROM base AS deps
COPY services/literature/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

FROM deps AS runtime
RUN useradd --create-home --uid 1000 rxos
COPY services/literature/app ./app
USER rxos
EXPOSE 8082
ENV PORT=8082
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
