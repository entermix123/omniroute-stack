# OmniRoute Docker Setup for Windows

A ready‑to‑run Docker‑Compose stack that includes:

*   **OmniRoute** – the local model‑routing proxy (listens on port 20128)
    
*   **Open WebUI** – a web UI that talks to OmniRoute via Docker Desktop’s `host.docker.internal`
    
*   **MCP health‑probe server** – a Python MCP server that lets you probe models, reorder combo priorities, and keep your setup healthy
    

* * *

## 1️⃣ Prerequisites

1.  **Docker Desktop** installed on Windows (latest stable version).  
    Make sure the Docker daemon is running.
    
2.  A **free OmniRoute API key** (you can generate one from the OmniRoute UI or CLI).
    
3.  (Optional) If you want the MCP health‑probe tools, you need the Python MCP code – see the _MCP server_ section below.
    

* * *

## 2️⃣ Folder layout

Create a folder on your Desktop (or anywhere you like) called `omniroute-stack` and place the following files inside:

```
omniroute-stack/
│
├─ docker-compose.yml          # <-- the main compose file (see below)
├─ .env                        # <-- your secret key (never commit this!)
│
└─ omnroute-mcp/               # <-- optional, only needed for the MCP health‑probe server
   ├─ Dockerfile
   ├─ requirements.txt
   └─ server.py
```

> **Tip:** Keep the whole `omniroute-stack` folder together – Docker Compose will resolve relative paths correctly.

* * *

## 5️⃣ The `.env` file (keep it secret!)

Create a file named `.env` in the root of `omniroute-stack` and add only this line:

```text
OMNIROUTE_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxx
```

_Never commit this file to version control._  
Docker‑Compose automatically reads it and injects the key into the containers.

* * *

## 5️⃣ `docker-compose.yml`

Copy the entire block below into a file named `docker-compose.yml` inside `omniroute-stack`.

```yaml
version: "3.9"

networks:
  # Custom bridge network so containers can talk to each other without exposing OmniRoute to the whole host
  omnroute-net:
    driver: bridge

services:
  # -------------------------------------------------
  # 1️⃣ OmniRoute – the routing proxy
  # -------------------------------------------------
  omnroute:
    image: ghcr.io/diegosouzapw/omniroute   # official image, auto‑updates
    container_name: omnroute
    restart: unless-stopped
    environment:
      - OMNIROUTE_API_KEY=${OMNIROUTE_API_KEY}
    # Bind only to localhost inside the container; Docker Desktop forwards it to the host
    ports:
      - "127.0.0.1:20128:20128"
    networks:
      - omnroute-net
    volumes:
      - ./data/omnroute:/data   # optional persistence for combos / logs

  # -------------------------------------------------
  # 2️⃣ Open WebUI – UI that talks to OmniRoute
  # -------------------------------------------------
  open-webui:
    image: ghcr.io/open-webui/open-webui:main
    container_name: open-webui
    restart: unless-stopped
    ports:
      - "3000:8080"                 # UI reachable at http://localhost:3000
    environment:
      # Docker Desktop on Windows resolves this hostname to the host machine
      - OPENAI_API_BASE_URL=http://host.docker.internal:20128/v1
      - OPENAI_API_KEY=${OMNIROUTE_API_KEY}
    networks:
      - omnroute-net
    volumes:
      - open-webui:/app/backend/data   # persist chat history / models

  # -------------------------------------------------
  # 3️⃣ MCP health‑probe server (Python)
  # -------------------------------------------------
  mcp-server:
    build: ./omnroute-mcp      # points to the folder with Dockerfile & server.py
    container_name: omnroute-mcp
    restart: unless-stopped
    environment:
      - OMNIROUTE_API_KEY=${OMNIROUTE_API_KEY}
      - OMNIROUTE_URL=http://omnroute:20128   # internal Docker DNS name
    ports:
      - "127.0.0.1:8000:8000"             # MCP HTTP endpoint (any agent can reach it)
    networks:
      - omnroute-net
    depends_on:
      - omnroute

# -------------------------------------------------
# Named volumes (Docker creates them automatically)
# -------------------------------------------------
volumes:
  open-webui:
```

### What each service does

| Service | Purpose |
| --- | --- |
| **omnroute** | Runs the OmniRoute binary, exposing port 20128 only on `127.0.0.1` (so only the host can reach it). |
| **open-webui** | Web UI accessible at `http://localhost:3000`. It forwards API calls to `http://host.docker.internal:20128/v1` (the OmniRoute service). |
| **mcp-server** | Exposes a standard MCP HTTP API on `localhost:8000`. It contains tools like `probe_model`, `probe_combo`, and `set_combo_priority` that let you keep the combo healthy. |

* * *

## 6️⃣ MCP server files (optional but highly recommended)

If you want the health‑probe tools (`probe_model`, `probe_combo`, `set_combo_priority`, …) you need to add the MCP server. Create the folder `omniroute-mcp` inside `omniroute-stack` and add the three files below.

### `omnroute-mcp/requirements.txt`

```text
mcp[http]
requests
```

### `omnroute-mcp/Dockerfile`

```Dockerfile
FROM python:3.12-slim

# Install MCP SDK (includes HTTP transport) and requests
RUN pip install --no-cache-dir mcp[http] requests

WORKDIR /app
COPY server.py /app/server.py

EXPOSE 8000

CMD ["python", "server.py"]
```

### `omnroute-mcp/server.py`

import json
import os
import time

import requests
from mcp.server.mcpserver import MCPServer

# -------------------------------------------------
# Configuration
# -------------------------------------------------

OMNIROUTE_URL = os.getenv("OMNIROUTE_URL", "http://omnroute:20128")
API_KEY = os.getenv("OMNIROUTE_API_KEY")

mcp = MCPServer("OmniRoute MCP")


# -------------------------------------------------
# OmniRoute helpers
# -------------------------------------------------

def _req(method: str, path: str, json_body=None):
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }

    url = f"{OMNIROUTE_URL}{path}"

    resp = requests.request(
        method,
        url,
        json=json_body,
        headers=headers,
        timeout=30,
    )

    resp.raise_for_status()
    return resp.json()


def _normalize_member(member):
    if isinstance(member, str):
        return member

    if isinstance(member, dict):
        for k in ("id", "name", "model", "model_id"):
            if member.get(k):
                return str(member[k])

    return None


def _get_model_ids(data):
    items = (
        data
        if isinstance(data, list)
        else (data.get("models") or data.get("items") or [])
    )

    ids = []

    for m in items:
        mid = _normalize_member(m)

        if mid:
            ids.append(mid)

    if not ids and isinstance(data, dict):
        mid = _normalize_member(data)

        if mid:
            ids = [mid]

    return ids


def _probe_one(model_id, timeout_s: float = 8.0):
    start = time.time()

    payload = {
        "model": model_id,
        "messages": [
            {
                "role": "user",
                "content": "ok",
            }
        ],
        "max_tokens": 8,
        "temperature": 0.0,
    }

    try:
        resp = requests.post(
            f"{OMNIROUTE_URL}/v1/chat/completions",
            json=payload,
            headers={
                "Authorization": f"Bearer {API_KEY}",
                "Content-Type": "application/json",
            },
            timeout=timeout_s,
        )

        latency_ms = int((time.time() - start) * 1000)

        if resp.status_code == 200:
            return {
                "model": model_id,
                "status": "UP",
                "latency_ms": latency_ms,
            }

        kinds = {
            "429": "RATE_LIMITED",
            "401": "UNAUTH",
            "403": "FORBIDDEN",
            "404": "NOT_FOUND",
        }

        return {
            "model": model_id,
            "status": kinds.get(
                str(resp.status_code),
                f"HTTP_{resp.status_code}",
            ),
            "latency_ms": latency_ms,
            "detail": resp.text[:120],
        }

    except requests.exceptions.Timeout:
        return {
            "model": model_id,
            "status": "TIMEOUT",
            "detail": f"no response in {timeout_s}s",
        }

    except requests.exceptions.ConnectionError:
        return {
            "model": model_id,
            "status": "DOWN",
            "detail": "connection failed",
        }


# -------------------------------------------------
# MCP tools
# -------------------------------------------------

@mcp.tool()
def probe_model(
    model_id: str,
    timeout_s: float = 8.0,
) -> str:
    """Probe an OmniRoute model and report its health and latency."""

    return json.dumps(
        _probe_one(model_id, timeout_s)
    )


@mcp.tool()
def probe_combo(
    combo_id: str,
    timeout_s: float = 8.0,
) -> str:
    """Probe all models in an OmniRoute combo and rank them by health and latency."""

    combo_data = _req(
        "GET",
        f"/v1/combos/{combo_id}",
    )

    model_ids = _get_model_ids(combo_data)

    results = [
        _probe_one(mid, timeout_s)
        for mid in model_ids
    ]

    def score(r):
        base = {
            "UP": 0,
            "RATE_LIMITED": 1,
            "TIMEOUT": 2,
            "DOWN": 3,
        }.get(
            r["status"],
            4,
        )

        return (
            base,
            r.get("latency_ms", 0),
        )

    ranked = sorted(
        results,
        key=score,
    )

    return json.dumps(
        {
            "combo": combo_id,
            "recommended_order": [
                r["model"]
                for r in ranked
            ],
            "details": ranked,
        }
    )


@mcp.tool()
def set_combo_priority(
    combo_id: str,
    model_order: list[str],
) -> str:
    """Change the model priority order for an OmniRoute combo."""

    payload = {
        "model_order": model_order,
    }

    data = _req(
        "PATCH",
        f"/v1/combos/{combo_id}/priority",
        payload,
    )

    return json.dumps(data)


@mcp.tool()
def list_models() -> str:
    """List the models currently available through OmniRoute."""

    data = _req(
        "GET",
        "/v1/models",
    )

    ids = [
        m["id"]
        for m in data["data"]
    ]

    return "\n".join(ids)


@mcp.tool()
def health_check() -> str:
    """Check whether OmniRoute is reachable and authenticated."""
    try:
        data = _req("GET", "/v1/models")
        count = len(data.get("data", []))
        return f"healthy: OmniRoute reachable, {count} models available"
    except Exception as exc:
        return f"unhealthy: {exc}"


# -------------------------------------------------
# Start MCP HTTP server
# -------------------------------------------------

if __name__ == "__main__":
    mcp.run(
        transport="streamable-http",
        json_response=True,
        host="0.0.0.0",
        port=8000,
    )

```

* * *

## 7️⃣ How to start the stack

```powershell
# From the folder that contains docker-compose.yml
docker compose up -d
```

Docker will pull the images (OmniRoute, Open WebUI) and start the three containers.
You can watch the logs with:

```powershell
docker compose logs -f omnroute
docker compose logs -f open-webui
docker compose logs -f mcp-server
```

* * *

## 6️⃣ Verify the setup

1.  **Open WebUI** – go to `http://localhost:3000` in your browser.  
    Log in (or create a new account) and you should see the list of models that OmniRoute knows about.
    
2.  **Check the MCP health endpoint** (optional):
    
    ```powershell
    curl http://localhost:8000/mcp -X POST -d '{"jsonrpc":"2.0","method":"tools/call","params":{"name":"health_check"}}'
    ```
    
    You should see `"healthy"`.
    
3.  **Test a probe** (optional):
    
    ```powershell
    curl http://localhost:8000/mcp \
      -H "Content-Type: application/json" \
      -X POST -d '{"jsonrpc":"2.0","method":"tools/call","params":{"name":"probe_combo","arguments":{"combo_id":"nvidia-free-stack"}}}'
    ```
    
    The response will be a JSON object containing the status of each model and a recommended priority order.
    

## Connect VSCode to use configured combos in Omniroute and Open WebUI

### Install Continue extension in VSCode - https://continue.dev/
### Configure Continue extension in VSCode to connect to Open WebUI container and use omniroute combo

Configure continue config.json

```json
name: Main Config
version: 1.0.0
schema: v1
models:
  # --- THIS IS YOUR NEW OPEN WEBUI CONNECTION ---
  - name: Open WebUI Nvidia-Free-Stack
    provider: openai
    model: Nvidia-Free-Stack  # <--- MUST match the exact model name in Open WebUI
    apiKey: sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx # <--- Your Open WebUI API Key
    apiBase: http://localhost:3000/api # <--- CHANGE THIS to your Open WebUI URL (usually ends in /api)
    roles:
      - chat
      - edit
      - apply
    defaultCompletionOptions:
      contextLength: 1047576
      maxTokens: 32768
    useLegacyCompletionsEndpoint: false

  - name: OmniRoute Nvidia-Free-Stack
    provider: openai
    model: Nvidia-Free-Stack
    apiBase: http://127.0.0.1:20128/v1
    apiKey: sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
    roles:
      - chat
      - edit
      - apply
    defaultCompletionOptions:
      contextLength: 128000
      maxTokens: 32768
    useLegacyCompletionsEndpoint: false

  - name: Open WebUI auto-coding
    provider: openai
    model: auto/best-coding  # <--- MUST match the exact model name in Open WebUI
    apiKey: sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx # <--- Your Open WebUI API Key
    apiBase: http://localhost:3000/api # <--- CHANGE THIS to your Open WebUI URL (usually ends in /api)
    roles:
      - chat
      - edit
      - apply
    defaultCompletionOptions:
      contextLength: 1047576
      maxTokens: 32768
    useLegacyCompletionsEndpoint: false
    
  - name: Open WebUI auto-reasoning
    provider: openai
    model: auto/best-reasoning  # <--- MUST match the exact model name in Open WebUI
    apiKey: sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx # <--- Your Open WebUI API Key
    apiBase: http://localhost:3000/api # <--- CHANGE THIS to your Open WebUI URL (usually ends in /api)
    roles:
      - chat
      - edit
      - apply
    defaultCompletionOptions:
      contextLength: 1047576
      maxTokens: 32768
    useLegacyCompletionsEndpoint: false
```

* * *

## 7️⃣ Keeping the combo healthy during work hours

1.  **Run the probe regularly** – you can schedule a simple task in Windows Task Scheduler or a cron‑like loop:
    
    ```powershell
    # Example PowerShell loop (run in a separate PowerShell window)
    while ($true) {
        curl -s http://localhost:8000/mcp \
          -H "Content-Type: application/json" \
          -X POST -d '{"jsonrpc":"2.0","method":"tools/call","params":{"name":"probe_combo","arguments":{"combo_id":"nvidia-free-stack"}}}' \
          >> C:\omniroute-probe.log 2>&1
        Start-Sleep -Seconds 300   # every 5 minutes
    }
    ```
    
    The `probe_combo` response tells you which models are healthy and fast; you can then re‑order the combo if needed.
    
2.  **Apply a new order** (once you have the recommended order):
    
    ```powershell
    # Example: put "phi-2" first, then "codellama-7b", then "nvidia-free-stack"
    curl -s http://localhost:8000/mcp \
      -X POST -d '{"jsonrpc":"2.0","method":"tools/call","params":{"name":"set_combo_priority","arguments":{"combo_id":"nvidia-free-stack","model_order":["phi-2","codellama-7b","nvidia-free-stack"]}}}'
    ```
    
3.  **Set a timeout** in OmniRoute (if you have access to its UI) – e.g., 15 s per model – so that a hung request fails quickly and the combo can fall back to the next model.
    

* * *

## 8️⃣ Clean‑up

When you’re done, stop and remove the stack:

```powershell
docker compose down
```

The volumes (`open-webui` and `omnroute`) will remain on disk. Delete them manually if you want a completely fresh start:

```powershell
docker volume rm omniroute-stack_open-webui
docker volume rm omniroute-stack_data_omnroute
```

* * *

## 8️⃣ TL;DR – One‑liner to launch everything

```powershell
# 1️⃣ Ensure .env exists with your API key
# 2️⃣ Run:
docker compose up -d
# 3️⃣ Open http://localhost:3000 in a browser and start using the UI.
```

You now have a **fully isolated, easy‑to‑manage** OmniRoute environment on Windows, with a built‑in health‑probe MCP server that keeps your model combo from hanging during work. Enjoy! 🎉

* * *

# Quick “one‑liner” to migrate an existing local OmniRoute

If you currently have OmniRoute running outside Docker and want to move it straight into the compose setup:

| What you want | API endpoint | Example command |
|---------------|--------------|-----------------|
| List all models | `GET /v1/models` | `curl -H "Authorization: Bearer sk-xxxxxxxxxxxxxxx-xxxxxxx-xxxxxxxx" http://localhost:20128/v1/models > models.json` |
| List all combos | `GET /v1/combos` | `curl -H "Authorization: Bearer sk-xxxxxxxxxxxxxxx-xxxxxxx-xxxxxxxx" http://localhost:20128/v1/combos > combos.json` |
| Export a single combo | `GET /v1/combos/{combo_id}` | `curl -H "Authorization: Bearer sk-xxxxxxxxxxxxxxx-xxxxxxx-xxxxxxxx" http://localhost:20128/v1/combos/nvidia-free-stack > nvidia-free-stack.json` |


```bash
# 1️⃣ Dump the current combos
curl -s http://localhost:20128/v1/combos \
    -H "Authorization: Bearer $(cat .env | grep OMNIROUTE_API_KEY= | cut -d= -f2)" \
    > combos-export.json

# 2️⃣ Copy the dump into the Docker data folder
mkdir -p ~/Desktop/omniroute-stack/data/omnroute
cp combos-export.json ~/Desktop/omniroute-stack/data/omnroute/

# 3️⃣ Add the volume mount to your compose file (already there) and start
cd ~/Desktop/omniroute-stack
docker compose up -d
```

After the container starts, open the Open‑WebUI UI (http://localhost:3000) and you’ll see the same combos you had locally.
