# literature

Part of the AI-RxOS platform. This service implements the Prompt 6 Literature
Intelligence pipeline using the existing connector factory, stage-based
orchestration, retry/backoff, metrics, parser, NLP, KG integration, and OKF
wiki integration boundaries. Runs on port **8082**.

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8082
```

This service supports optional spaCy-powered NER. The default configuration uses `en_core_web_sm` when available and automatically falls back to the built-in rule-based extractor if spaCy or the model is unavailable.

The Docker container has been validated with `docker compose build literature` and `docker compose up -d literature`, and the local health endpoint responds on `http://127.0.0.1:8082/healthz`.

To install the optional spaCy model:

```bash
python -m spacy download en_core_web_sm
```

Additional service docs:
- `ARCHITECTURE.md`
- `API_CONTRACT.md`
- `DATABASE_SCHEMA.md`
- `INTEGRATION_MAP.md`
- `IMPLEMENTATION.md`
- `TESTING.md`
- `DEPLOYMENT.md`
- `PRODUCTION_CHECKLIST.md`
