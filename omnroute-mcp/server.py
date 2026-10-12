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
