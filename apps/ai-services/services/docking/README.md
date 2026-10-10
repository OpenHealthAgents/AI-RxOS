# docking

Part of the AI-RxOS platform. See `/architecture` at the repo root for the
full service contract this implements. Runs on port **8088**.

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8088
```
