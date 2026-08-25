import asyncio
import json
import os
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
import redis.asyncio as redis


@pytest.mark.skipif(
    os.getenv("AI_RXOS_LIVE_WORKER_TESTS") != "1"
    or not os.getenv("EXECUTION_PAYLOAD_KEY"),
    reason="set AI_RXOS_LIVE_WORKER_TESTS=1 and EXECUTION_PAYLOAD_KEY to enable",
)
@pytest.mark.asyncio
async def test_real_worker_process_crash_and_reclaim():
    redis_url = os.getenv("AI_RXOS_REDIS_URL", "redis://localhost:6379/0")
    payload_key = os.environ["EXECUTION_PAYLOAD_KEY"]
    suffix = uuid.uuid4().hex
    task_id = f"live-task-{suffix}"
    stream = f"agents:jobs:live:{suffix}"
    group = f"agents-workers:live:{suffix}"
    model_port = _start_deterministic_model_server()
    client = redis.from_url(redis_url, decode_responses=True)
    env = {
        **os.environ,
        "PYTHONPATH": os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")),
        "ENVIRONMENT": "test",
        "REDIS_URL": redis_url,
        "EXECUTION_PAYLOAD_KEY": payload_key,
        "AGENT_JOB_STREAM": stream,
        "AGENT_JOB_GROUP": group,
        "MODEL_REGISTRY_JSON": json.dumps(
            {
                "primary_model": "live",
                "models": {
                    "live": {
                        "name": "deterministic",
                        "provider": "open_source",
                        "base_url": f"http://127.0.0.1:{model_port}",
                        "max_retries": 0,
                    }
                },
            }
        ),
        "AGENT_WORKER_RECLAIM_IDLE_SECONDS": "0.2",
        "AGENT_WORKER_EXECUTION_TIMEOUT_SECONDS": "3",
        "AGENT_WORKER_LOCK_TTL_SECONDS": "4",
    }
    metadata_key = f"agents:task:{task_id}"
    payload_store_key = f"agents:task-payloads:live-org:live-workspace:{task_id}"
    worker_a = None
    worker_b = None
    try:
        from app.security.payloads import RedisExecutionPayloadStore

        payloads = RedisExecutionPayloadStore(
            client, key=payload_key, prefix="agents:task-payloads"
        )
        await payloads.put(
            tenant_id="live-org",
            workspace_id="live-workspace",
            payload_id=task_id,
            payload={"input": {"prompt": "private live input"}, "result": None},
        )
        await client.set(
            metadata_key,
            json.dumps(
                {
                    "id": task_id,
                    "agentType": "default",
                    "status": "queued",
                    "tenant": {
                        "organization_id": "live-org",
                        "workspace_id": "live-workspace",
                        "user_id": "live-user",
                    },
                    "retry_count": 0,
                    "retry_allowed": True,
                    "execution_id": f"execution-{suffix}",
                    "payload_reference": task_id,
                    "checkpoint_reference": task_id,
                }
            ),
        )
        queue = __import__("app.jobs.queue", fromlist=["RedisJobQueue"]).RedisJobQueue(
            client, stream=stream, group=group
        )
        await queue.enqueue(task_id)
        worker_a = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "app.jobs.worker",
            cwd=os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")),
            env=env,
        )
        await _wait_for_status(client, metadata_key, "running")
        worker_a.kill()
        await asyncio.wait_for(worker_a.wait(), timeout=10)
        pending = await client.xpending(stream, group)
        assert pending["pending"] == 1

        worker_b = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "app.jobs.worker",
            cwd=os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")),
            env=env,
        )
        await _wait_for_status(client, metadata_key, "succeeded", timeout=30)
        await client.xgroup_delconsumer(stream, group, "worker-a")
        pending = await client.xpending(stream, group)
        assert pending["pending"] == 0
        worker_b.terminate()
        await asyncio.wait_for(worker_b.wait(), timeout=10)

        operational = await client.get(metadata_key)
        assert "private live input" not in (operational or "")
        assert await client.exists(payload_store_key)
    finally:
        for worker in (worker_a, worker_b):
            if worker is not None and worker.returncode is None:
                worker.kill()
                await asyncio.wait_for(worker.wait(), timeout=10)
        await client.xgroup_destroy(stream, group)
        await client.delete(metadata_key, payload_store_key, stream)
        await client.aclose()


async def _wait_for_status(client, key: str, expected: str, timeout: float = 15) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        raw = await client.get(key)
        if raw and json.loads(raw).get("status") == expected:
            return
        await asyncio.sleep(0.1)
    raise AssertionError(f"task did not reach status {expected}")


def _start_deterministic_model_server() -> int:
    class Handler(BaseHTTPRequestHandler):
        calls = 0

        def do_POST(self):
            Handler.calls += 1
            if Handler.calls == 1:
                time.sleep(10)
            body = json.dumps({"generated_text": "ok"}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server.server_port
