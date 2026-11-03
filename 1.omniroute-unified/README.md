# OmniRoute Unified Stack

A flexible, multi-environment OmniRoute deployment that supports **self-hosted models**, **cloud providers**, or **both** — from a single codebase.

---

## 📁 Project Structure

```
omniroute-unified/
├── docker-compose.yml           # Base services (OmniRoute, Open WebUI, MCP, Health Monitor)
├── docker-compose.local.yml     # Self-hosted models only (Ollama, vLLM, llama.cpp)
├── docker-compose.cloud.yml     # Cloud providers only (Nvidia, OpenAI, Anthropic, etc.)
├── docker-compose.hybrid.yml    # Self-hosted + Cloud (production)
├── env.local.example            # Environment template for local models
├── env.cloud.example            # Environment template for cloud providers
├── env.hybrid.example           # Environment template for hybrid
├── combos/
│   ├── local-combos.json        # Pre-defined local model combos
│   ├── cloud-combos.json        # Pre-defined cloud combos
│   └── hybrid-combos.json       # Pre-defined hybrid combos
├── omnroute-mcp/
│   ├── Dockerfile               # MCP server container
│   ├── requirements.txt         # Python dependencies
│   └── server.py                # MCP tools (probe_model, probe_combo, etc.)
└── health-monitor/
    ├── Dockerfile               # Health monitor container
    └── monitor.py               # Auto-probing + HTTP health endpoints
```

---

## 🚀 Quick Start

### 1. Choose Your Mode

| Mode | Use Case | Command |
|------|----------|---------|
| **Local** | Ollama/LM Studio/vLLM on your machine | `docker compose -f docker-compose.yml -f docker-compose.local.yml --env-file .env up -d` |
| **Cloud** | Nvidia, OpenAI, Anthropic, etc. | `docker compose -f docker-compose.yml -f docker-compose.cloud.yml --env-file .env up -d` |
| **Hybrid** | Local first, cloud fallback (prod) | `docker compose -f docker-compose.yml -f docker-compose.hybrid.yml --env-file .env up -d` |

### 2. Create Your `.env` File

```bash
# Copy the appropriate template
cp env.local.example .env      # For local models
cp env.cloud.example .env      # For cloud providers
cp env.hybrid.example .env     # For hybrid

# Edit .env and add your OMNIROUTE_API_KEY
# Generate one at http://localhost:20128 after first start
```

### 3. Start the Stack

```bash
# Example: Hybrid mode
cp env.hybrid.example .env
# Edit .env with your keys

# Start
 docker compose -f docker-compose.yml -f docker-compose.hybrid.yml --env-file .env up -d

# Watch logs
 docker compose -f docker-compose.yml -f docker-compose.hybrid.yml logs -f omnroute
```

### 4. Configure Providers & Combos

1. Open **OmniRoute UI**: http://localhost:20128
2. **Add Providers**:
   - **Local**: Ollama → `http://host.docker.internal:11434`
   - **Local**: vLLM → `http://vllm:8000/v1` (if running in Docker)
   - **Cloud**: Nvidia/OpenAI/Anthropic → paste API key
3. **Create Combos** (or import from `combos/*.json`):
   - Go to Combos → Create Combo
   - Use `provider/model` format: `ollama/codellama:34b`, `nvidia/nemotron-3-ultra`
4. **Install OmniSkills** (Settings → OmniSkills):
   - `function-calling`, `structured-output`, `code-execution`, `web-search`

---

## 🛠️ Local Model Server Options

### Option 1: Ollama (Recommended for GGUF)
```bash
# Run on host (simplest)
 ollama serve
 ollama pull codellama:34b
 ollama pull llama3.2

# Or in Docker (uncomment in docker-compose.local.yml)
# services:
#   ollama:
#     image: ollama/ollama:latest
#     volumes:
#       - ollama-data:/root/.ollama
#     deploy:
#       resources:
#         reservations:
#           devices:
#             - driver: nvidia
#               count: 1
#               capabilities: [gpu]
```

### Option 2: vLLM (High-throughput, OpenAI-compatible)
```bash
# In Docker (uncomment in docker-compose.hybrid.yml)
# services:
#   vllm:
#     image: vllm/vllm-openai:latest
#     command: --model meta-llama/Llama-3.2-3B-Instruct --dtype auto
#     deploy:
#       resources:
#         reservations:
#           devices:
#             - driver: nvidia
#               count: 1
#               capabilities: [gpu]
```

### Option 3: llama.cpp Server (CPU-friendly)
```bash
# In Docker (uncomment in docker-compose.hybrid.yml)
# services:
#   llamacpp:
#     image: ghcr.io/ggerganov/llama.cpp:server
#     command: -m /models/llama-3.2-3b-instruct-q4_k_m.gguf -c 8192
#     volumes:
#       - llamacpp-models:/models
```

---

## 🔧 MCP Tools (Programmatic Control)

The MCP server exposes these tools at `http://localhost:8000/mcp`:

| Tool | Description |
|------|-------------|
| `probe_model(model_id)` | Check health/latency of a single model |
| `probe_combo(combo_id)` | Probe all models in a combo, get ranked order |
| `set_combo_priority(combo_id, model_order)` | Reorder models in a combo |
| `list_models()` | List all available models |
| `list_combos()` | List all combo names |
| `health_check()` | Verify OmniRoute connectivity |

### Example Usage
```bash
# Health check
 curl -X POST http://localhost:8000/mcp \
   -H "Content-Type: application/json" \
   -d '{"jsonrpc":"2.0","method":"tools/call","params":{"name":"health_check"},"id":1}'

# Probe a local combo
 curl -X POST http://localhost:8000/mcp \
   -H "Content-Type: application/json" \
   -d '{"jsonrpc":"2.0","method":"tools/call","params":{"name":"probe_combo","arguments":{"combo_id":"Local-Coding-Stack"}},"id":1}'

# Reorder combo priorities
 curl -X POST http://localhost:8000/mcp \
   -H "Content-Type: application/json" \
   -d '{"jsonrpc":"2.0","method":"tools/call","params":{"name":"set_combo_priority","arguments":{"combo_id":"Local-Coding-Stack","model_order":["ollama/codellama:34b","ollama/llama3.2"]}},"id":1}'
```

---

## 📊 Health Monitor Endpoints

The health monitor runs on `http://localhost:8081`:

| Endpoint | Purpose |
|----------|---------|
| `GET /health` | Full status of all monitored combos |
| `GET /health/live` | Liveness probe (for Docker/K8s) |
| `GET /health/ready` | Readiness probe (true after first successful probe) |
| `GET /health/<combo_name>` | Status for specific combo |

```bash
# Check all combos
 curl http://localhost:8081/health

# Kubernetes-style probes
 curl http://localhost:8081/health/live
 curl http://localhost:8081/health/ready
```

---

## 📥 Importing Pre-defined Combos

```bash
# Import local combos
 curl -X POST http://localhost:20128/api/combos \
   -H "Authorization: Bearer $OMNIROUTE_API_KEY" \
   -H "Content-Type: application/json" \
   -d @combos/local-combos.json

# Import cloud combos
 curl -X POST http://localhost:20128/api/combos \
   -H "Authorization: Bearer $OMNIROUTE_API_KEY" \
   -H "Content-Type: application/json" \
   -d @combos/cloud-combos.json

# Import hybrid combos
 curl -X POST http://localhost:20128/api/combos \
   -H "Authorization: Bearer $OMNIROUTE_API_KEY" \
   -H "Content-Type: application/json" \
   -d @combos/hybrid-combos.json
```

---

## 🎯 VS Code (Continue Extension) Config

```json
{
  "models": [
    {
      "name": "OmniRoute Local",
      "provider": "openai",
      "model": "Local-Coding-Stack",
      "apiBase": "http://127.0.0.1:20128/v1",
      "apiKey": "sk-your-api-key"
    },
    {
      "name": "OmniRoute Hybrid",
      "provider": "openai",
      "model": "Hybrid-Best-of-Both",
      "apiBase": "http://127.0.0.1:20128/v1",
      "apiKey": "sk-your-api-key"
    }
  ]
}
```

---

## 🧹 Cleanup

```bash
# Stop and remove containers
 docker compose -f docker-compose.yml -f docker-compose.hybrid.yml down

# Remove volumes (fresh start)
 docker volume rm omniroute-unified_open-webui
 docker volume rm omniroute-unified_omniroute-data
 # If using local model servers:
 docker volume rm omniroute-unified_ollama-data
 docker volume rm omniroute-unified_vllm-cache
```

---

## 📋 Model Naming Convention

**Always use `provider/model` format in combos:**

| ✅ Correct | ❌ Wrong |
|------------|----------|
| `ollama/codellama:34b` | `local-codellama` |
| `vllm/meta-llama/Llama-3.2-3B-Instruct` | `vllm-model-1` |
| `nvidia/nvidia-nemotron-3-ultra-550b-a55b` | `nvidia-free-stack-model-1` |
| `openai/gpt-4o-mini` | `gpt-4o-mini` |
| `llamacpp/llama-3.2-3b-instruct-q4_k_m` | `my-gguf-model` |

Using internal names causes `HTTP_400: Unable to determine provider` errors.

---

## 🔐 Security Notes

- **Never commit `.env`** — add to `.gitignore`
- OmniRoute binds to `127.0.0.1` only (not exposed to LAN)
- Generate strong API keys via OmniRoute UI
- Rotate keys quarterly

---

## 📚 Related

- [OmniRoute Documentation](https://github.com/diegosouzapw/omniroute)
- [Open WebUI](https://github.com/open-webui/open-webui)
- [MCP Specification](https://modelcontextprotocol.io/)
- [Ollama](https://ollama.com/)
- [vLLM](https://github.com/vllm-project/vllm)
- [llama.cpp](https://github.com/ggerganov/llama.cpp)
