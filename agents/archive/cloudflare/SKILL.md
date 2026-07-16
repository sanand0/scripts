---
name: cloudflare
description: For CloudFlare development, deployment, e.g. Python CloudFlare Workers
---

## General

- Modifying code while `wrangler dev` is running slows it down. Stop, edit, then restart.

## Python Cloudflare Workers

Sample `wrangler.toml`:

```toml
name = "..."
main = "..."
compatibility_date = "..."
compatibility_flags = ["python_workers"]

[observability]
enabled = true
```

Sample `entry.py`:

```python
from workers import Response, WorkerEntrypoint

class Default(WorkerEntrypoint):
    async def fetch(self, request, env) -> Response:
        return Response('{"x": 1}', headers={"content-type": "application/json"})
```

To integrate a FastAPI app:

```python
from workers import WorkerEntrypoint
from my_fastapi_app import app
import asgi

class Default(WorkerEntrypoint):
   async def fetch(self, request):
       return await asgi.fetch(app, request.js_object, self.env)
```

Usage notes:

- Ensure there's a `pyproject.toml` with dependencies.
- Prep env: `uv add --dev workers-py workers-runtime-sdk`
- Vendor deps (if any): `uv run pywrangler sync` (uses `python_modules`).
- Dev: `uv run pywrangler dev` then hit http://localhost:8787.
- Deploy: `uv run pywrangler deploy`.
- Verify: `curl https://<worker-name>.<account>.workers.dev`.
