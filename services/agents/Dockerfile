FROM python:3.12-slim AS base

WORKDIR /app

FROM base AS deps

COPY services/agents/requirements.txt .

RUN pip install \
    --upgrade pip \
    --default-timeout=1000 \
    --retries=20 \
    --no-cache-dir \
    -r requirements.txt

FROM deps AS runtime

COPY services/agents .

EXPOSE 8085

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8085"]