# OmniRoute Docker Setup for Windows

A ready‑to‑run Docker‑Compose stack that includes:

*   **OmniRoute** – the local model‑routing proxy (listens on port 20128)
    
*   **Open WebUI** – a web UI that talks to OmniRoute via Docker Desktop's `host.docker.internal`
    
*   **MCP health‑probe server** – a Python MCP server that lets you probe models, reorder combo priorities, and keep your setup healthy
    
*   **Health Monitor** – automatic combo probing with HTTP status endpoints (port 8081)

* * *
# OmniRoute Docker Setup for Windows

## What is OmniRoute?

**OmniRoute** is a lightweight, local model-routing proxy that sits between your AI clients (Open WebUI, VS Code extensions, custom scripts, etc.) and dozens of upstream LLM providers (Ollama, LM Studio, OpenAI-compatible APIs, cloud endpoints, etc.). It lets you:

- **Combine multiple models into \"combos\"** with automatic fall-back, priority ordering, and health-based routing.
- **Expose a single OpenAI-compatible endpoint** (`http://localhost:20128/v1`) so any OpenAI-client code works unchanged.
- **Manage API keys, timeouts, and retries centrally**—no need to update every client when a provider changes.
- **Run 100 % locally** (no data leaves your machine unless you explicitly point a combo at a cloud provider).

---


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
├─ omnroute-mcp/               # <-- optional, only needed for the MCP health‑probe server
│  ├─ Dockerfile
│  ├─ requirements.txt
│  └─ server.py
│
└─ health-monitor/             # <-- health monitor for auto-probing combos
   ├─ Dockerfile
   └─ monitor.py
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
networks:
  # Custom bridge network so containers can talk to each other without exposing OmniRoute to the whole host
  omnroute-net:
    driver: bridge

services:
  # -------------------------------------------------
  # 1️⃣ OmniRoute – the routing proxy
  # -------------------------------------------------
  omnroute:
    image: ghcr.io/diegosouzapw/omniroute:3.8.51   # official image, auto‑updates
    container_name: omnroute
    restart: unless-stopped
    environment:
      - OMNIROUTE_API_KEY=${OMNIROUTE_API_KEY}
      - DATA_DIR=/app/data          # make the data location explicit
    # Bind only to localhost inside the container; Docker Desktop forwards it to the host
    ports:
      - "127.0.0.1:20128:20128"
    networks:
      - omnroute-net
    volumes:
      - ./data/omnroute:/app/data   # persistent config, providers, combos

  # -------------------------------------------------
  # 2️⃣ Open WebUI – UI that talks to OmniRoute
  # -------------------------------------------------
  open-webui:
    image: ghcr.io/open-webui/open-webui:main
    container_name: open-webui
    restart: unless-stopped
    ports:
      - \"3000:8080\"                 # UI reachable at http://localhost:3000
    environment:
      # Docker Desktop on Windows resolves this hostname to the host machine
      - OPENAI_API_BASE_URL=http://host.docker.internal:20128/v1
      - OPENAI_API_KEY=${OMNIROUTE_API_KEY}
    networks:
      - omnroute-net
    volumes:
      - open-webui:/app/backend/data   # persist chat history / models

  # -------------------------------------------------
  # 4️⃣ Health Monitor – periodic combo probe + optional auto-reorder
  # -------------------------------------------------
  health-monitor:
    build: ./health-monitor
    container_name: omniroute-health-monitor
    restart: unless-stopped
    environment:
      - OMNIROUTE_API_KEY=${OMNIROUTE_API_KEY}
      - MCP_URL=http://mcp-server:8000/mcp
      - COMBO_ID=Nvidia-Free-Stack
      - INTERVAL_SEC=300          # 5 minutes
      - AUTO_APPLY=false          # set to \"true\" to auto-reorder
      - HEALTH_PORT=8080
    ports:
      - \"127.0.0.1:8081:8080\"             # Health endpoint (http://localhost:8081/health)
    networks:
      - omnroute-net
    depends_on:
      - mcp-server

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
      - \"127.0.0.1:8000:8000\"             # MCP HTTP endpoint (any agent can reach it)
    networks:
      - omnroute-net
    depends_on:
      - omnroute

# -------------------------------------------------
# Named volumes (Docker creates them automatically)
# -------------------------------------------------
volumes:
  open-webui:
  omniroute-data:
```

### What each service does

| Service | Purpose |
| --- | --- |
| **omnroute** | Runs the OmniRoute binary, exposing port 20128 only on `127.0.0.1` (so only the host can reach it). |
| **open-webui** | Web UI accessible at `http://localhost:3000`. It forwards API calls to `http://host.docker.internal:20128/v1` (the OmniRoute service). |
| **mcp-server** | Exposes a standard MCP HTTP API on `localhost:8000`. It contains tools like `probe_model`, `probe_combo`, `set_combo_priority`, `list_combos`, `list_models`, `health_check`. |
| **health-monitor** | Auto-discovers combos, probes each every 5 min, exposes HTTP status at `localhost:8081/health`. |

* * *

## 6️⃣ MCP server files (optional but highly recommended)

If you want the health‑probe tools (`probe_model`, `probe_combo`, `set_combo_priority`, …) you need to add the MCP server. Create the folder `omnroute-mcp` inside `omniroute-stack` and add the three files below.

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

CMD [\"python\", \"server.py\"]
```

### `omnroute-mcp/server.py`

```python
import json
import os
import time

import requests
from mcp.server.mcpserver import MCPServer

# -------------------------------------------------
# Configuration
# -------------------------------------------------

OMNIROUTE_URL = os.getenv(\"OMNIROUTE_URL\", \"http://omnroute:20128\")
API_KEY = os.getenv(\"OMNIROUTE_API_KEY\")

mcp = MCPServer(\"OmniRoute MCP\")

# -------------------------------------------------
# OmniRoute helpers
# -------------------------------------------------

def _req(method: str, path: str, json_body=None):
    headers = {
        \"Authorization\": f\"Bearer {API_KEY}\",
        \"Content-Type\": \"application/json\",
    }

    url = f\"{OMNIROUTE_URL}{path}\"

    resp = requests.request(
        method,
        url,
        json=json_body,
        headers=headers,
        timeout=30,
    )

    resp.raise_for_status()
    return resp.json()


def _get_combo_by_name(combo_name: str):
    \"\"\"Fetch all combos and find one by name. Returns the combo dict with its UUID.\"\"\"
    data = _req(\"GET\", \"/api/combos\")
    for combo in data.get(\"combos\", []):
        if combo.get(\"name\") == combo_name:
            return combo
    raise ValueError(f\"Combo '{combo_name}' not found\")


def _normalize_member(member):
    if isinstance(member, str):
        return member

    if isinstance(member, dict):
        for k in (\"id\", \"name\", \"model\", \"model_id\"):
            if member.get(k):
                return str(member[k])

    return None


def _get_model_ids(data):
    items = (
        data
        if isinstance(data, list)
        else (data.get(\"models\") or data.get(\"items\") or [])
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
        \"model\": model_id,
        \"messages\": [
            {
                \"role\": \"user\",
                \"content\": \"ok\",
            }
        ],
        \"max_tokens\": 8,
        \"temperature\": 0.0,
    }

    try:
        resp = requests.post(
            f\"{OMNIROUTE_URL}/v1/chat/completions\",
            json=payload,
            headers={
                \"Authorization\": f\"Bearer {API_KEY}\",
                \"Content-Type\": \"application/json\",
            },
            timeout=timeout_s,
        )

        latency_ms = int((time.time() - start) * 1000)

        if resp.status_code == 200:
            return {
                \"model\": model_id,
                \"status\": \"UP\",
                \"latency_ms\": latency_ms,
            }

        kinds = {
            \"429\": \"RATE_LIMITED\",
            \"401\": \"UNAUTH\",
            \"403\": \"FORBIDDEN\",
            \"404\": \"NOT_FOUND\",
        }

        return {
            \"model\": model_id,
            \"status\": kinds.get(
                str(resp.status_code),
                f\"HTTP_{resp.status_code}\",
            ),
            \"latency_ms\": latency_ms,
            \"detail\": resp.text[:120],
        }

    except requests.exceptions.Timeout:
        return {
            \"model\": model_id,
            \"status\": \"TIMEOUT\",
            \"detail\": f\"no response in {timeout_s}s\",
        }

    except requests.exceptions.ConnectionError:
        return {
            \"model\": model_id,
            \"status\": \"DOWN\",
            \"detail\": \"connection failed\",
        }


# -------------------------------------------------
# MCP tools
# -------------------------------------------------

@mcp.tool()
def probe_model(
    model_id: str,
    timeout_s: float = 8.0,
) -> str:
    \"\"\"Probe an OmniRoute model and report its health and latency.\"\"\"

    return json.dumps(
        _probe_one(model_id, timeout_s)
    )


@mcp.tool()
def probe_combo(
    combo_id: str,
    timeout_s: float = 8.0,
) -> str:
    \"\"\"Probe all models in an OmniRoute combo and rank them by health and latency.\"\"\"

    combo_data = _get_combo_by_name(combo_id)

    model_ids = _get_model_ids(combo_data)

    results = [
        _probe_one(mid, timeout_s)
        for mid in model_ids
    ]

    def score(r):
        base = {
            \"UP\": 0,
            \"RATE_LIMITED\": 1,
            \"TIMEOUT\": 2,
            \"DOWN\": 3,
        }.get(
            r[\"status\"],
            4,
        )

        return (
            base,
            r.get(\"latency_ms\", 0),
        )

    ranked = sorted(
        results,
        key=score,
    )

    return json.dumps(
        {
            \"combo\": combo_id,
            \"recommended_order\": [
                r[\"model\"]
                for r in ranked
            ],
            \"details\": ranked,
        }
    )


@mcp.tool()
def set_combo_priority(
    combo_id: str,
    model_order: list[str],
) -> str:
    \"\"\"Change the model priority order for an OmniRoute combo.
    
    Args:
        combo_id: The name of the combo (e.g., \"Nvidia-Free-Stack\")
        model_order: List of model IDs in the desired priority order
    \"\"\"

    # Get the combo to find its UUID
    combo_data = _get_combo_by_name(combo_id)
    combo_uuid = combo_data.get(\"id\")
    
    # Build the models array in the new order
    # We need to preserve the full model objects but reorder them
    existing_models = combo_data.get(\"models\", [])
    model_map = {m.get(\"model\"): m for m in existing_models}
    
    new_models = []
    for model_name in model_order:
        if model_name in model_map:
            new_models.append(model_map[model_name])
    
    # Add any models not in the new order (they'll go to the end)
    for model_name, model_obj in model_map.items():
        if model_name not in model_order:
            new_models.append(model_obj)
    
    payload = {
        \"name\": combo_id,
        \"models\": new_models,
        \"strategy\": combo_data.get(\"strategy\", \"priority\"),
    }

    data = _req(
        \"PATCH\",
        f\"/api/combos/{combo_uuid}\",
        payload,
    )

    return json.dumps(data)


@mcp.tool()
def list_models() -> str:
    \"\"\"List the models currently available through OmniRoute.\"\"\"

    data = _req(
        \"GET\",
        \"/v1/models\",
    )

    ids = [
        m[\"id\"]
        for m in data[\"data\"]
    ]

    return \"\\n\".join(ids)


@mcp.tool()
def list_combos() -> str:
    \"\"\"List all combo names available in OmniRoute.\"\"\"
    data = _req(\"GET\", \"/api/combos\")
    names = [combo.get(\"name\", \"\") for combo in data.get(\"combos\", [])]
    return \"\\n\".join(names)


@mcp.tool()
def health_check() -> str:
    \"\"\"Check whether OmniRoute is reachable and authenticated.\"\"\"
    try:
        data = _req(\"GET\", \"/v1/models\")
        count = len(data.get(\"data\", []))
        return f\"healthy: OmniRoute reachable, {count} models available\"
    except Exception as exc:
        return f\"unhealthy: {exc}\"


# -------------------------------------------------
# Start MCP HTTP server
# -------------------------------------------------

if __name__ == \"__main__\":
    mcp.run(
        transport=\"streamable-http\",
        json_response=True,
        host=\"0.0.0.0\",
    )
```

* * *

## 7️⃣ Health Monitor files

Create the folder `health-monitor` inside `omniroute-stack` and add the two files below.

### `health-monitor/Dockerfile`

```Dockerfile
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1
RUN pip install --no-cache-dir requests
WORKDIR /app
COPY monitor.py /app/monitor.py
CMD [\"python\", \"-u\", \"monitor.py\"]
```

### `health-monitor/monitor.py`

```python
import json
import os
import time
import requests
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

MCP_URL = os.getenv(\"MCP_URL\", \"http://localhost:8000/mcp\")
# COMBO_ID can be:
# - empty/unset: auto-discover all combos
# - single combo name: \"Nvidia-Free-Stack\"
# - comma-separated: \"Nvidia-Free-Stack,AMD-Stack\"
COMBO_ID = os.getenv(\"COMBO_ID\", \"\").strip()
INTERVAL_SEC = int(os.getenv(\"INTERVAL_SEC\", \"300\"))  # 5 min default
AUTO_APPLY = os.getenv(\"AUTO_APPLY\", \"false\").lower() == \"true\"
HEALTH_PORT = int(os.getenv(\"HEALTH_PORT\", \"8080\"))

SESSION_ID = None
LATEST_PROBES = {}  # combo_name -> probe data
LATEST_PROBES_LOCK = threading.Lock()

def initialize_session():
    \"\"\"Initialize MCP session by calling initialize method.\"\"\"
    global SESSION_ID
    payload = {
        \"jsonrpc\": \"2.0\",
        \"method\": \"initialize\",
        \"params\": {
            \"protocolVersion\": \"2024-11-05\",
            \"capabilities\": {},
            \"clientInfo\": {\"name\": \"health-monitor\", \"version\": \"1.0\"}
        },
        \"id\": 1
    }
    try:
        resp = requests.post(MCP_URL, json=payload, timeout=30)
        resp.raise_for_status()
        # Update session ID from response header if present
        session_id_header = resp.headers.get(\"mcp-session-id\") or resp.headers.get(\"Mcp-Session-ID\")
        if session_id_header:
            SESSION_ID = session_id_header
            print(f\"[{time.ctime()}] MCP session initialized: {SESSION_ID[:8]}...\")
        else:
            print(f\"[{time.ctime()}] Warning: No session ID in initialize response\")
        return True
    except Exception as e:
        print(f\"[{time.ctime()}] Failed to initialize MCP session: {e}\")
        return False

def call_mcp(method: str, params: dict):
    global SESSION_ID
    payload = {\"jsonrpc\": \"2.0\", \"method\": method, \"params\": params, \"id\": 1}
    headers = {}
    if SESSION_ID:
        headers[\"mcp-session-id\"] = SESSION_ID
    
    try:
        resp = requests.post(MCP_URL, json=payload, headers=headers, timeout=30)
        resp.raise_for_status()
        # Update session ID from response header if present
        session_id_header = resp.headers.get(\"mcp-session-id\") or resp.headers.get(\"Mcp-Session-ID\")
        if session_id_header:
            SESSION_ID = session_id_header
        return resp.json()
    except requests.exceptions.HTTPError as e:
        if resp.status_code == 400:
            # Check if the error is about missing session ID
            try:
                error_data = resp.json()
                if error_data.get(\"error\", {}).get(\"message\") == \"Bad Request: Missing session ID\":
                    # Get session ID from response header
                    session_id_header = resp.headers.get(\"mcp-session-id\") or resp.headers.get(\"Mcp-Session-ID\")
                    if session_id_header:
                        SESSION_ID = session_id_header
                        # Retry the request with the session ID
                        headers[\"mcp-session-id\"] = SESSION_ID
                        resp = requests.post(MCP_URL, json=payload, headers=headers, timeout=30)
                        resp.raise_for_status()
                        # Update session ID again from response (should be same)
                        session_id_header = resp.headers.get(\"mcp-session-id\") or resp.headers.get(\"Mcp-Session-ID\")
                        if session_id_header:
                            SESSION_ID = session_id_header
                        return resp.json()
            except Exception:
                pass
        elif resp.status_code == 404:
            # Session not found - need to re-initialize
            try:
                error_data = resp.json()
                if error_data.get(\"error\", {}).get(\"message\") == \"Session not found\":
                    print(f\"[{time.ctime()}] Session expired, re-initializing...\")
                    SESSION_ID = None
                    if initialize_session():
                        # Retry with new session
                        headers[\"mcp-session-id\"] = SESSION_ID
                        resp = requests.post(MCP_URL, json=payload, headers=headers, timeout=30)
                        resp.raise_for_status()
                        session_id_header = resp.headers.get(\"mcp-session-id\") or resp.headers.get(\"Mcp-Session-ID\")
                        if session_id_header:
                            SESSION_ID = session_id_header
                        return resp.json()
            except Exception:
                pass
        # If we get here, re-raise the original exception
        raise

def get_target_combos():
    \"\"\"Get list of combos to monitor based on COMBO_ID env var.\"\"\"
    if not COMBO_ID:
        # Auto-discover: call MCP to get all combos via list_combos tool
        try:
            result = call_mcp(\"tools/call\", {
                \"name\": \"list_combos\",
                \"arguments\": {}
            })
            # Parse result - list_combos returns newline-separated combo names
            result_data = result.get(\"result\", {})
            content = result_data.get(\"content\", [])
            if content and isinstance(content, list) and len(content) > 0:
                text_content = content[0].get(\"text\", \"\")
                if text_content:
                    combos = [c.strip() for c in text_content.split(\"\\n\") if c.strip()]
                    if combos:
                        print(f\"[{time.ctime()}] Auto-discovered combos: {combos}\")
                        return combos
            print(f\"[{time.ctime()}] Auto-discover returned empty, using default\")
        except Exception as e:
            print(f\"[{time.ctime()}] Auto-discover failed, using default: {e}\")
        return [\"Nvidia-Free-Stack\"]  # fallback
    return [c.strip() for c in COMBO_ID.split(\",\") if c.strip()]

def probe_combo(combo_name):
    \"\"\"Probe a single combo and update global state.\"\"\"
    global LATEST_PROBES
    print(f\"[{time.ctime()}] Probing combo: {combo_name}\")
    result = call_mcp(\"tools/call\", {
        \"name\": \"probe_combo\",
        \"arguments\": {\"combo_id\": combo_name}
    })
    
    # Parse the nested JSON response
    try:
        result_data = result.get(\"result\", {})
        content = result_data.get(\"content\", [])
        if content and isinstance(content, list) and len(content) > 0:
            text_content = content[0].get(\"text\", \"\")
            if text_content:
                data = json.loads(text_content)
            else:
                data = {}
        else:
            data = {}
        recommended = data.get(\"recommended_order\", [])
        details = data.get(\"details\", [])
        
        # Update global state
        with LATEST_PROBES_LOCK:
            LATEST_PROBES[combo_name] = {
                \"timestamp\": time.time(),
                \"combo\": combo_name,
                \"recommended_order\": recommended,
                \"details\": details,
                \"error\": None
            }
        
        print(f\"  Recommended order: {recommended}\")
        for d in details:
            print(f\"    {d['model']}: {d['status']} ({d.get('latency_ms', '?')}ms)\")
        
        if AUTO_APPLY and recommended:
            print(f\"  Auto-applying new priority order...\")
            apply_result = call_mcp(\"tools/call\", {
                \"name\": \"set_combo_priority\",
                \"arguments\": {\"combo_id\": combo_name, \"model_order\": recommended}
            })
            print(f\"  Applied: {apply_result}\")
    except Exception as e:
        error_msg = str(e)
        print(f\"  Error parsing probe result: {error_msg}\")
        with LATEST_PROBES_LOCK:
            LATEST_PROBES[combo_name] = {
                \"timestamp\": time.time(),
                \"combo\": combo_name,
                \"recommended_order\": [],
                \"details\": [],
                \"error\": error_msg
            }
            
def probe_and_maybe_apply():
    \"\"\"Probe all target combos.\"\"\"
    target_combos = get_target_combos()
    for combo_name in target_combos:
        try:
            probe_combo(combo_name)
        except Exception as e:
            print(f\"[{time.ctime()}] Probe failed for {combo_name}: {e}\")

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == '/health/live':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'status': 'alive'}).encode())
        elif parsed.path == '/health/ready':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            with LATEST_PROBES_LOCK:
                ready = len(LATEST_PROBES) > 0 and all(p.get('timestamp') is not None for p in LATEST_PROBES.values())
            self.wfile.write(json.dumps({'status': 'ready' if ready else 'not_ready'}).encode())
        elif parsed.path == '/health':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            with LATEST_PROBES_LOCK:
                response = {}
                for combo_name, probe in LATEST_PROBES.items():
                    p = dict(probe)
                    if p.get('timestamp'):
                        p['timestamp_iso'] = time.strftime('%Y-%m-%dT%H:%M:%S', time.localtime(p['timestamp']))
                    response[combo_name] = p
            self.wfile.write(json.dumps(response).encode())
        elif parsed.path.startswith('/health/'):
            combo_name = parsed.path.split('/health/', 1)[1]
            if not combo_name:
                self.send_response(400)
                self.end_headers()
                return
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            with LATEST_PROBES_LOCK:
                if combo_name in LATEST_PROBES:
                    response = dict(LATEST_PROBES[combo_name])
                    if response.get('timestamp'):
                        response['timestamp_iso'] = time.strftime('%Y-%m-%dT%H:%M:%S', time.localtime(response['timestamp']))
                else:
                    response = {\"error\": \"Combo not found\", \"combo\": combo_name}
            self.wfile.write(json.dumps(response).encode())
        else:
            self.send_response(404)
            self.end_headers()
    
    def log_message(self, format, *args):
        # Suppress default log messages
        pass

def run_health_server():
    server = HTTPServer(('0.0.0.0', HEALTH_PORT), HealthHandler)
    print(f\"[{time.ctime()}] Health endpoint server started on port {HEALTH_PORT}\")
    server.serve_forever()

if __name__ == \"__main__\":
    print(f\"Starting health monitor (auto-discover combos) every {INTERVAL_SEC}s (AUTO_APPLY={AUTO_APPLY})\")
    
    # Start health endpoint server in background thread
    health_thread = threading.Thread(target=run_health_server, daemon=True)
    health_thread.start()
    
    # Initialize MCP session first
    while not initialize_session():
        print(f\"[{time.ctime()}] Retrying session initialization in 10s...\")
        time.sleep(10)
    
    # Now that session is ready, discover combos
    target_combos = get_target_combos()
    print(f\"[{time.ctime()}] Monitoring combos: {target_combos}\")
    
    while True:
        try:
            probe_and_maybe_apply()
        except Exception as e:
            print(f\"[{time.ctime()}] Probe failed: {e}\")
        time.sleep(INTERVAL_SEC)
```

* * *

## 8️⃣ How to start the stack

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
docker compose logs -f health-monitor
```

* * *

## 9️⃣ Verify the setup

1.  **Open WebUI** – go to `http://localhost:3000` in your browser.  
    Log in (or create a new account) and you should see the list of models that OmniRoute knows about.
    
2.  **Check the MCP health endpoint** (optional):
    
    ```powershell
    curl http://localhost:8000/mcp -X POST -d '{\"jsonrpc\":\"2.0\",\"method\":\"tools/call\",\"params\":{\"name\":\"health_check\"},\"id\":1}'
    ```
    
    You should see `\"healthy\"`.
    
3.  **Test a probe** (optional):
    
    ```powershell
    curl http://localhost:8000/mcp \
      -H \"Content-Type: application/json\" \
      -X POST -d '{\"jsonrpc\":\"2.0\",\"method\":\"tools/call\",\"params\":{\"name\":\"probe_combo\",\"arguments\":{\"combo_id\":\"Nvidia-Free-Stack\"}},\"id\":1}'
    ```
    
    The response will be a JSON object containing the status of each model and a recommended priority order.

4. **Check Health Monitor** (optional):
    
    ```powershell
    curl http://localhost:8081/health
    curl http://localhost:8081/health/live
    curl http://localhost:8081/health/ready
    ```

* * *

## 🔑 Creating Combos in OmniRoute (CRITICAL)

**Register on any free model provider platform. In this case is used NVidia Free models. Go to [NVidia Developer Platform](https://developer.nvidia.com/), register and create API Key**

**Combos must be created in OmniRoute before the stack can route to them.** The health monitor and MCP tools only work with existing combos.

### Method 1: Via OmniRoute Web UI (Recommended)

1. Open `http://localhost:20128` in your browser (OmniRoute admin UI)
2. Add NVidia provider → **Providers, search for NVidia NIM in API Key Providers section and add a connection using the created NVidia API Key**
3. Go to **Combos** → **Create Combo**
4. Fill in:
   - **Name**: e.g., `Nvidia-Free-Stack`
   - **Strategy**: `priority` (default) or `round-robin`
   - **Models**: Add models using their **provider/model** format:
     - `nvidia/nvidia-nemotron-3-ultra-550b-a55b`
     - `nvidia/google-gemma-4-31b-it`
     - `ollama/glm-5.2`
     - `openai/gpt-4o-mini`
     - `anthropic/claude-3-haiku`
5. Save the combo

### Method 2: Via API (Scriptable)

```powershell
# Get your API key from .env
$apiKey = (Get-Content .env | Select-String 'OMNIROUTE_API_KEY=').Line.Split('=')[1]

# Create a combo
curl.exe -X POST http://localhost:20128/api/combos \
  -H \"Authorization: Bearer $apiKey\" \
  -H \"Content-Type: application/json\" \
  -d '{
    \"name\": \"Nvidia-Free-Stack\",
    \"strategy\": \"priority\",
    \"models\": [
      {\"model\": \"nvidia/nvidia-nemotron-3-ultra-550b-a55b\"},
      {\"model\": \"nvidia/google-gemma-4-31b-it\"},
      {\"model\": \"ollama/glm-5.2\"}
    ]
  }'
```

### Method 3: Import from JSON

```powershell
# Export existing combos from another OmniRoute instance
curl.exe -H \"Authorization: Bearer $apiKey\" http://localhost:20128/api/combos > combos-backup.json

# Import into new instance
$combos = Get-Content combos-backup.json -Raw | ConvertFrom-Json
foreach ($combo in $combos.combos) {
    # Remove id field before import
    $combo.PSObject.Properties.Remove('id')
    $json = $combo | ConvertTo-Json -Depth 10
    curl.exe -X POST http://localhost:20128/api/combos \
      -H \"Authorization: Bearer $apiKey\" \
      -H \"Content-Type: application/json\" \
      -d $json
}
```

### ⚠️ Model Naming Convention

**Use `provider/model` format, NOT internal names like `nvidia-free-stack-model-1-...`**

| ❌ Wrong | ✅ Correct |
|----------|------------|
| `nvidia-free-stack-model-4-ollama-cloud-glm-5-2` | `ollama/glm-5.2` |
| `nvidia-free-stack-model-1-nvidia-nemotron-3-ultra` | `nvidia/nvidia-nemotron-3-ultra-550b-a55b` |
| `my-custom-name` | `provider/actual-model-id` |

The health monitor will show `HTTP_400: Unable to determine provider` if you use internal names.

* * *

## 🧠 Installing OmniSkills (CRITICAL)

**OmniSkills** are specialized model configurations that OmniRoute can route to. They enable features like function calling, structured output, etc.

### Installing OmniSkills

1. Register on platform for skill [Skillsmp](https://skillsmp.com/) and create API Key
   
2. **Via OmniRoute UI** (Settings → OmniSkills → Install):
   - Go to OmniRoute UI under Settings → OmniSkills and set Skillsmp API Key
   - Browse available skills on marketplace tab
   - Click Install on desired skills

3. **Via CLI** (if available):
   ```bash
   omnroute skills install <skill-name>
   ```

4. **Popular OmniSkills to install**:
   - `function-calling` - enables function/tool calling
   - `structured-output` - JSON schema enforcement
   - `code-execution` - sandboxed code execution
   - `web-search` - web search capabilities
   - `file-operations` - file read/write tools

### Adding OmniSkills to Combos

After installing skills, add them to your combos:

```json
{
  "name": "Nvidia-Free-Stack",
  "strategy": "priority",
  "models": [
    {"model": "nvidia/nvidia/nemotron-3-ultra-550b-a55b"},
    {"model": "nvidia/nvidia/nemotron-3-super-120b-a12b"}
    {"model": "zcode/glm-5.3"},
    {"model": "omniskill:function-calling"},
    {"model": "omniskill:structured-output"},
    {"model": "omniskill:devops-helper"},
    {"model": "omniskill:file-reader"},
    {"model": "omniskill:web-search"},
    {"model": "omniskill:docs-assistant"},
    {"model": "omniskill:obra-superpowers-brainstorming"},
    {"model": "omniskill:obra-superpowers-receiving-code-review"}, 
    {"model": "omniskill:obra-superpowers-systematic-debugging"},
    {"model": "omniskill:grill-with-docs"},
    {"model": "omniskill:implement-spec"}
  ]
}
```

* * *

## ⚡ Good Practices & Critical Activities

### ✅ Before First Run
1. **Create `.env` with valid API key** - Stack won't start without it
2. **Create at least one combo in OmniRoute** - Health monitor needs combos to probe
3. **Install relevant OmniSkills** - Enable advanced features before adding to combos
4. **Test OmniRoute connectivity**: `curl http://localhost:20128/v1/models` with auth

### 🔄 Ongoing Maintenance
| Activity | Frequency | How |
|----------|-----------|-----|
| Check combo health | Continuous | Health monitor does this automatically (port 8081) |
| Review model latencies | Weekly | `GET /health` → check `latency_ms` trends |
| Update OmniRoute image | Monthly | `docker compose pull && docker compose up -d` |
| Rotate API keys | Quarterly | Update `.env` and restart stack |
| Backup combo configs | Before changes | `curl /api/combos > combos-backup.json` |

### 📊 Monitoring Best Practices
1. **Use `/health/ready` for Docker/K8s health checks** - Only returns ready after first successful probe
2. **Set `AUTO_APPLY=true` cautiously** - Test manually first, then enable for production
3. **Alert on `DOWN`/`TIMEOUT` statuses** - Indicates provider issues
4. **Track latency trends** - Rising latency = provider degradation

### 🛡️ Security
- **Never commit `.env`** - Add to `.gitignore`
- **Bind OmniRoute to `127.0.0.1` only** - Don't expose to LAN without auth
- **Use strong API keys** - Generate via OmniRoute UI
- **Regular updates** - Keep Docker images current

### 🐛 Troubleshooting Quick Reference
| Symptom | Likely Cause | Fix |
|---------|--------------|-----|
| Health monitor returns `{}` | No combos exist / session not ready | Create combo, check logs |
| All models `HTTP_400` | Wrong model naming format | Use `provider/model` format |
| `Session not found` errors | MCP session expired | Health monitor auto-recovers |
| Open WebUI shows no models | Combo empty or wrong API base | Verify combo has models, check `OPENAI_API_BASE_URL` |

* * *

## Connect VSCode to use configured combos in OmniRoute and Open WebUI

### Install Continue extension in VSCode - https://continue.dev/
### Configure Continue extension in VSCode to connect to Open WebUI container and use OmniRoute combo

Configure continue config.json

```JSON
{
  \"name\": \"Main Config\",
  \"version\": \"1.0.0\",
  \"schema\": \"v1\",
  \"models\": [
    {
      \"name\": \"Open WebUI Nvidia-Free-Stack\",
      \"provider\": \"openai\",
      \"model\": \"Nvidia-Free-Stack\",
      \"apiKey\": \"sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx\",
      \"apiBase\": \"http://localhost:3000/api\",
      \"roles\": [\"chat\", \"edit\", \"apply\"],
      \"defaultCompletionOptions\": {
        \"contextLength\": 1047576,
        \"maxTokens\": 32768
      },
      \"useLegacyCompletionsEndpoint\": false
    },
    {
      \"name\": \"OmniRoute Nvidia-Free-Stack\",
      \"provider\": \"openai\",
      \"model\": \"Nvidia-Free-Stack\",
      \"apiBase\": \"http://127.0.0.1:20128/v1\",
      \"apiKey\": \"sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx\",
      \"roles\": [\"chat\", \"edit\", \"apply\"],
      \"defaultCompletionOptions\": {
        \"contextLength\": 128000,
        \"maxTokens\": 32768
      },
      \"useLegacyCompletionsEndpoint\": false
    },
    {
      \"name\": \"Open WebUI auto-coding\",
      \"provider\": \"openai\",
      \"model\": \"auto/best-coding\",
      \"apiKey\": \"sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx\",
      \"apiBase\": \"http://localhost:3000/api\",
      \"roles\": [\"chat\", \"edit\", \"apply\"],
      \"defaultCompletionOptions\": {
        \"contextLength\": 1047576,
        \"maxTokens\": 32768
      },
      \"useLegacyCompletionsEndpoint\": false
    },
    {
      \"name\": \"Open WebUI auto-reasoning\",
      \"provider\": \"openai\",
      \"model\": \"auto/best-reasoning\",
      \"apiKey\": \"sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx\",
      \"apiBase\": \"http://localhost:3000/api\",
      \"roles\": [\"chat\", \"edit\", \"apply\"],
      \"defaultCompletionOptions\": {
        \"contextLength\": 1047576,
        \"maxTokens\": 32768
      },
      \"useLegacyCompletionsEndpoint\": false
    }
  ]
}
```

* * *

## 🧹 Clean‑up

When you're done, stop and remove the stack:

```powershell
docker compose down
```

The volumes (`open-webui` and `omnroute`) will remain on disk. Delete them manually if you want a completely fresh start:

```powershell
docker volume rm omniroute-stack_open-webui
docker volume rm omniroute-stack_data_omnroute
```

* * *

## 📋 TL;DR – One‑liner to launch everything

```powershell
# 1️⃣ Ensure .env exists with your API key
# 2️⃣ Create combos in OmniRoute UI (http://localhost:20128)
# 3️⃣ Install OmniSkills in OmniRoute UI (Settings → OmniSkills)
# 4️⃣ Run:
docker compose up -d
# 5️⃣ Open http://localhost:3000 in a browser and start using the UI.
# 6️⃣ Monitor health at http://localhost:8081/health
```

You now have a **fully isolated, easy‑to‑manage** OmniRoute environment on Windows, with a built‑in health‑probe MCP server and automatic health monitor that keeps your model combo healthy. Enjoy! 🎉

* * *

# Quick “one‑liner” to migrate an existing local OmniRoute

If you currently have OmniRoute running outside Docker and want to move it straight into the compose setup:

| What you want | API endpoint | Example command |
|---------------|--------------|-----------------|
| List all models | `GET /v1/models` | `curl -H \"Authorization: Bearer sk-xxxxxxxxxxxxxxx-xxxxxxx-xxxxxxxx\" http://localhost:20128/v1/models > models.json` |
| List all combos | `GET /api/combos` | `curl -H \"Authorization: Bearer sk-xxxxxxxxxxxxxxx-xxxxxxx-xxxxxxxx\" http://localhost:20128/api/combos > combos.json` |
| Export a single combo | `GET /api/combos/{combo_id}` | `curl -H \"Authorization: Bearer sk-xxxxxxxxxxxxxxx-xxxxxxx-xxxxxxxx\" http://localhost:20128/api/combos/nvidia-free-stack > nvidia-free-stack.json` |

```bash
# 1️⃣ Dump the current combos
curl -s http://localhost:20128/api/combos \
    -H \"Authorization: Bearer $(cat .env | grep OMNIROUTE_API_KEY= | cut -d= -f2)\" \
    > combos-export.json

# 2️⃣ Copy the dump into the Docker data folder
mkdir -p ~/Desktop/omniroute-stack/data/omnroute
cp combos-export.json ~/Desktop/omniroute-stack/data/omnroute/

# 3️⃣ Add the volume mount to your compose file (already there) and start
cd ~/Desktop/omniroute-stack
docker compose up -d
```

After the container starts, open the Open‑WebUI UI (http://localhost:3000) and you'll see the same combos you had locally.
