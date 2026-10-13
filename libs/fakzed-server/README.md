# fakzed-server

The fakzed platform server: register agents once, call them from anywhere.

- **Registry**: `register()` once, served over REST + SSE
- **Auth**: API-key auth per agent, optional admin bootstrap key
- **Multi-tenancy**: per-key tenancy with usage accounting
- **Persistence**: JSON file or any `Storage` backend
- **Observability**: `/health`, `/metrics` monitoring endpoints
- **Remote SDK**: `RemoteAgent` mirrors the local `Agent` interface

```bash
uv add fakzed-server   # or: pip install fakzed-server

# China users: add a mirror if direct PyPI access stalls (copy-paste ready)
uv add fakzed-server --index-url https://mirrors.cloud.tencent.com/pypi/simple

fakzed-server --host 0.0.0.0 --port 8000 --admin-key <bootstrap-key>
```

```python
import uvicorn

from fakzed import Agent
from fakzed_server import FakzedServer

server = FakzedServer(admin_api_key="admin", db_path="agents.json")
server.register(Agent(name="echo", model="deepseek:deepseek-chat"))
uvicorn.run(server.app, host="127.0.0.1", port=8000)  # blocking
```

```python
from fakzed import RemoteAgent

remote = RemoteAgent(base_url="http://127.0.0.1:8000", agent_name="echo", api_key="admin")
resp = remote.run("hello")
print(resp.content)
```

See the monorepo [README](../../README.md) and [platform docs](../../docs/platform.md).
