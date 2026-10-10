FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1     PYTHONUNBUFFERED=1     PIP_NO_CACHE_DIR=1
WORKDIR /app

FROM base AS deps
COPY services/reports/requirements.txt .
RUN pip install \
    --upgrade pip \
    --default-timeout=1000 \
    --retries=20 \
    -r requirements.txt

FROM deps AS runtime
RUN useradd --create-home --uid 1000 rxos
COPY services/reports/app ./app
USER rxos
EXPOSE 8087
ENV PORT=8087
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
