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


def _get_combo_by_name(combo_name: str):
    """Fetch all combos and find one by name. Returns the combo dict with its UUID."""
    data = _req("GET", "/api/combos")
    for combo in data.get("combos", []):
        if combo.get("name") == combo_name:
            return combo
    raise ValueError(f"Combo '{combo_name}' not found")


def _normalize_member(member):
    if isinstance(member, str):
        return member

    if isinstance(member, dict):
        # Priority: real provider model ID first, then fallbacks
        for k in ("model", "model_id", "id", "name"):
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

    combo_data = _get_combo_by_name(combo_id)

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
    """Change the model priority order for an OmniRoute combo.
    
    Args:
        combo_id: The name of the combo (e.g., "Nvidia-Free-Stack")
        model_order: List of model IDs in the desired priority order
    """

    # Get the combo to find its UUID
    combo_data = _get_combo_by_name(combo_id)
    combo_uuid = combo_data.get("id")
    
    # Build the models array in the new order
    # We need to preserve the full model objects but reorder them
    existing_models = combo_data.get("models", [])
    model_map = {m.get("model"): m for m in existing_models}
    
    new_models = []
    for model_name in model_order:
        if model_name in model_map:
            new_models.append(model_map[model_name])
    
    # Add any models not in the new order (they'll go to the end)
    for model_name, model_obj in model_map.items():
        if model_name not in model_order:
            new_models.append(model_obj)
    
    payload = {
        "name": combo_id,
        "models": new_models,
        "strategy": combo_data.get("strategy", "priority"),
    }

    data = _req(
        "PATCH",
        f"/api/combos/{combo_uuid}",
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
def list_combos() -> str:
    """List all combo names available in OmniRoute."""
    data = _req("GET", "/api/combos")
    names = [combo.get("name", "") for combo in data.get("combos", [])]
    return "\n".join(names)


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
    )


