"# OmniRoute MCP Server & Health Monitor - Usage Guide

## Overview

The stack includes two key components:

1. **MCP Server** (`mcp-server` on port 8000) - Model Context Protocol server exposing OmniRoute management tools
2. **Health Monitor** (`health-monitor` on port 8081) - Automatic combo probing with HTTP status endpoints

---

## 🔌 MCP Server (Port 8000)

### Base URL
```
http://localhost:8000/mcp
```

### Available Tools

| Tool | Description | Parameters |
|------|-------------|------------|
| `probe_model` | Probe a single model | `model_id` (string), `timeout_s` (float, optional) |
| `probe_combo` | Probe all models in a combo | `combo_id` (string), `timeout_s` (float, optional) |
| `set_combo_priority` | Reorder models in a combo | `combo_id` (string), `model_order` (string[]) |
| `list_models` | List all models in OmniRoute | none |
| `list_combos` | List all combo names | none |
| `health_check` | Check OmniRoute connectivity | none |

---

### MCP Usage Examples

#### Initialize Session (Required First)
```bash
curl -s http://localhost:8000/mcp \
  -H "Content-Type: application/json" \
  -X POST \
  -d '{"jsonrpc":"2.0","method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}},"id":1}'
```

#### Health Check
```bash
curl -s http://localhost:8000/mcp \
  -H "Content-Type: application/json" \
  -X POST \
  -d '{"jsonrpc":"2.0","method":"tools/call","params":{"name":"health_check","arguments":{}},"id":1}'
```

#### List All Combos
```bash
curl -s http://localhost:8000/mcp \
  -H "Content-Type: application/json" \
  -X POST \
  -d '{"jsonrpc":"2.0","method":"tools/call","params":{"name":"list_combos","arguments":{}},"id":1}'
```

#### List All Models
```bash
curl -s http://localhost:8000/mcp \
  -H "Content-Type: application/json" \
  -X POST \
  -d '{"jsonrpc":"2.0","method":"tools/call","params":{"name":"list_models","arguments":{}},"id":1}'
```

#### Probe a Single Model
```bash
curl -s http://localhost:8000/mcp \
  -H "Content-Type: application/json" \
  -X POST \
  -d '{"jsonrpc":"2.0","method":"tools/call","params":{"name":"probe_model","arguments":{"model_id":"nvidia/nvidia-nemotron-3-ultra-550b-a55b"}},"id":1}'
```

#### Probe Entire Combo
```bash
curl -s http://localhost:8000/mcp \
  -H "Content-Type: application/json" \
  -X POST \
  -d '{"jsonrpc":"2.0","method":"tools/call","params":{"name":"probe_combo","arguments":{"combo_id":"Nvidia-Free-Stack"}},"id":1}'
```

#### Apply Recommended Priority Order
```bash
curl -s http://localhost:8000/mcp \
  -H "Content-Type: application/json" \
  -X POST \
  -d '{"jsonrpc":"2.0","method":"tools/call","params":{"name":"set_combo_priority","arguments":{"combo_id":"Nvidia-Free-Stack","model_order":["model-a","model-b","model-c"]}},"id":1}'
```

---

## 🏥 Health Monitor (Port 8081)

The health monitor automatically:
- Discovers all combos from OmniRoute (or uses `COMBO_ID` env var)
- Probes each combo every 5 minutes (configurable)
- Handles MCP session lifecycle automatically
- Exposes HTTP endpoints for status

### Base URL
```
http://localhost:8081
```

### Endpoints

| Endpoint | Description | Response |
|----------|-------------|----------|
| `GET /health` | All combos status | JSON object with all combo probe results |
| `GET /health/{combo_name}` | Single combo status | JSON with probe details for one combo |
| `GET /health/live` | Liveness probe | `{\"status\":\"alive\"}` |
| `GET /health/ready` | Readiness probe | `{\"status\":\"ready\"}` or `{\"status\":\"not_ready\"}` |

---

### Health Monitor Usage Examples

#### Get All Combo Status
```bash
curl -s http://localhost:8081/health
```

#### Get Specific Combo Status
```bash
curl -s http://localhost:8081/health/Nvidia-Free-Stack
```

#### Liveness Check (Docker/K8s)
```bash
curl -s http://localhost:8081/health/live
# {"status": "alive"}
```

#### Readiness Check (Docker/K8s)
```bash
curl -s http://localhost:8081/health/ready
# {"status": "ready"}  (after first successful probe)
# {"status": "not_ready"}  (before first probe)
```

---

## 📋 Response Format

### Probe Response (`/health` or `probe_combo`)
```json
{
  "timestamp": 1791920425.0927022,
  "timestamp_iso": "2026-10-13T19:40:25",
  "combo": "Nvidia-Free-Stack",
  "recommended_order": [
    "model-id-1",
    "model-id-2",
    "model-id-3"
  ],
  "details": [
    {
      "model": "model-id-1",
      "status": "UP",
      "latency_ms": 45,
      "detail": null
    },
    {
      "model": "model-id-2",
      "status": "HTTP_400",
      "latency_ms": 32,
      "detail": "{\"error\":{\"message\":\"...\"}}"
    }
  ],
  "error": null
}
```

### Status Values
| Status | Meaning |
|--------|---------|
| `UP` | Model responded successfully |
| `RATE_LIMITED` | HTTP 429 - rate limited |
| `UNAUTH` | HTTP 401 - unauthorized |
| `FORBIDDEN` | HTTP 403 - forbidden |
| `NOT_FOUND` | HTTP 404 - model not found |
| `HTTP_XXX` | Other HTTP error codes |
| `TIMEOUT` | Request timed out |
| `DOWN` | Connection failed |

---

## ⚙️ Configuration

### Health Monitor Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `MCP_URL` | `http://mcp-server:8000/mcp` | MCP server URL |
| `COMBO_ID` | (empty = auto-discover) | Comma-separated combo names, or empty for auto-discovery |
| `INTERVAL_SEC` | `300` | Probe interval in seconds |
| `AUTO_APPLY` | `false` | Auto-apply recommended priority order |
| `HEALTH_PORT` | `8080` | Internal HTTP port (mapped to 8081) |

### Docker Compose Example
```yaml
health-monitor:
  build: ./health-monitor
  environment:
    - MCP_URL=http://mcp-server:8000/mcp
    - COMBO_ID=Nvidia-Free-Stack,AMD-Stack
    - INTERVAL_SEC=300
    - AUTO_APPLY=false
    - HEALTH_PORT=8080
  ports:
    - \"127.0.0.1:8081:8080\"
```

---

## 🔄 Auto-Discovery

When `COMBO_ID` is empty or not set:
1. Health monitor calls `list_combos` tool on startup
2. Gets all combo names from OmniRoute
3. Probes each discovered combo every interval
4. Automatically picks up new combos added to OmniRoute

---

## 🐳 Docker Operations

### View Logs
```bash
# Health monitor
docker logs omniroute-health-monitor -f

# MCP server
docker logs omnroute-mcp -f
```

### Restart Services
```bash
docker compose restart health-monitor mcp-server
```

### Rebuild After Code Changes
```bash
docker compose up -d --no-deps --build health-monitor
docker compose up -d --no-deps --build mcp-server
```

---

## 🛠️ Troubleshooting

### Health Monitor Returns Empty `{}`
- Check if MCP session initialized: `docker logs omniroute-health-monitor`
- Verify `list_combos` tool works via MCP directly

### Probe Shows All `HTTP_400`
- Models in combo use internal names not resolvable by OmniRoute
- Fix combo config in OmniRoute with valid provider/model IDs

### Session Errors (404/400)
- Health monitor auto-recovers, but check logs for patterns
- Ensure MCP server is healthy: `curl localhost:8000/mcp` with initialize

### Port Conflicts
- Health monitor: 8081 (host) → 8080 (container)
- MCP server: 8000 (host) → 8000 (container)

---

## 📚 Quick Reference

```bash
# Full stack status
curl -s http://localhost:8081/health | jq

# Single combo
curl -s http://localhost:8081/health/Nvidia-Free-Stack | jq

# MCP direct probe
curl -s http://localhost:8000/mcp -X POST -H 'Content-Type: application/json' \
  -d '{\"jsonrpc\":\"2.0\",\"method\":\"tools/call\",\"params\":{\"name\":\"probe_combo\",\"arguments\":{\"combo_id\":\"Nvidia-Free-Stack\"}},\"id\":1}' | jq

# Liveness/Readiness for orchestration
curl -sf http://localhost:8081/health/live && echo \"alive\"
curl -sf http://localhost:8081/health/ready && echo \"ready\"
```"