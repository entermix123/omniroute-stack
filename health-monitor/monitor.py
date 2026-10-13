import json
import os
import time
import requests
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

MCP_URL = os.getenv("MCP_URL", "http://localhost:8000/mcp")
# COMBO_ID can be:
# - empty/unset: auto-discover all combos
# - single combo name: "Nvidia-Free-Stack"
# - comma-separated: "Nvidia-Free-Stack,AMD-Stack"
COMBO_ID = os.getenv("COMBO_ID", "").strip()
INTERVAL_SEC = int(os.getenv("INTERVAL_SEC", "300"))  # 5 min default
AUTO_APPLY = os.getenv("AUTO_APPLY", "false").lower() == "true"
HEALTH_PORT = int(os.getenv("HEALTH_PORT", "8080"))

SESSION_ID = None
LATEST_PROBES = {}  # combo_name -> probe data
LATEST_PROBES_LOCK = threading.Lock()

def initialize_session():
    """Initialize MCP session by calling initialize method."""
    global SESSION_ID
    payload = {
        "jsonrpc": "2.0",
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "health-monitor", "version": "1.0"}
        },
        "id": 1
    }
    try:
        resp = requests.post(MCP_URL, json=payload, timeout=30)
        resp.raise_for_status()
        # Update session ID from response header if present
        session_id_header = resp.headers.get("mcp-session-id") or resp.headers.get("Mcp-Session-ID")
        if session_id_header:
            SESSION_ID = session_id_header
            print(f"[{time.ctime()}] MCP session initialized: {SESSION_ID[:8]}...")
        else:
            print(f"[{time.ctime()}] Warning: No session ID in initialize response")
        return True
    except Exception as e:
        print(f"[{time.ctime()}] Failed to initialize MCP session: {e}")
        return False

def call_mcp(method: str, params: dict):
    global SESSION_ID
    payload = {"jsonrpc": "2.0", "method": method, "params": params, "id": 1}
    headers = {}
    if SESSION_ID:
        headers["mcp-session-id"] = SESSION_ID
    
    try:
        resp = requests.post(MCP_URL, json=payload, headers=headers, timeout=30)
        resp.raise_for_status()
        # Update session ID from response header if present
        session_id_header = resp.headers.get("mcp-session-id") or resp.headers.get("Mcp-Session-ID")
        if session_id_header:
            SESSION_ID = session_id_header
        return resp.json()
    except requests.exceptions.HTTPError as e:
        if resp.status_code == 400:
            # Check if the error is about missing session ID
            try:
                error_data = resp.json()
                if error_data.get("error", {}).get("message") == "Bad Request: Missing session ID":
                    # Get session ID from response header
                    session_id_header = resp.headers.get("mcp-session-id") or resp.headers.get("Mcp-Session-ID")
                    if session_id_header:
                        SESSION_ID = session_id_header
                        # Retry the request with the session ID
                        headers["mcp-session-id"] = SESSION_ID
                        resp = requests.post(MCP_URL, json=payload, headers=headers, timeout=30)
                        resp.raise_for_status()
                        # Update session ID again from response (should be same)
                        session_id_header = resp.headers.get("mcp-session-id") or resp.headers.get("Mcp-Session-ID")
                        if session_id_header:
                            SESSION_ID = session_id_header
                        return resp.json()
            except Exception:
                pass
        elif resp.status_code == 404:
            # Session not found - need to re-initialize
            try:
                error_data = resp.json()
                if error_data.get("error", {}).get("message") == "Session not found":
                    print(f"[{time.ctime()}] Session expired, re-initializing...")
                    SESSION_ID = None
                    if initialize_session():
                        # Retry with new session
                        headers["mcp-session-id"] = SESSION_ID
                        resp = requests.post(MCP_URL, json=payload, headers=headers, timeout=30)
                        resp.raise_for_status()
                        session_id_header = resp.headers.get("mcp-session-id") or resp.headers.get("Mcp-Session-ID")
                        if session_id_header:
                            SESSION_ID = session_id_header
                        return resp.json()
            except Exception:
                pass
        # If we get here, re-raise the original exception
        raise

def get_target_combos():
    """Get list of combos to monitor based on COMBO_ID env var."""
    if not COMBO_ID:
        # Auto-discover: call MCP to get all combos via list_combos tool
        try:
            result = call_mcp("tools/call", {
                "name": "list_combos",
                "arguments": {}
            })
            # Parse result - list_combos returns newline-separated combo names
            result_data = result.get("result", {})
            content = result_data.get("content", [])
            if content and isinstance(content, list) and len(content) > 0:
                text_content = content[0].get("text", "")
                if text_content:
                    combos = [c.strip() for c in text_content.split("\n") if c.strip()]
                    if combos:
                        print(f"[{time.ctime()}] Auto-discovered combos: {combos}")
                        return combos
            print(f"[{time.ctime()}] Auto-discover returned empty, using default")
        except Exception as e:
            print(f"[{time.ctime()}] Auto-discover failed, using default: {e}")
        return ["Nvidia-Free-Stack"]  # fallback
    return [c.strip() for c in COMBO_ID.split(",") if c.strip()]

def probe_combo(combo_name):
    """Probe a single combo and update global state."""
    global LATEST_PROBES
    print(f"[{time.ctime()}] Probing combo: {combo_name}")
    result = call_mcp("tools/call", {
        "name": "probe_combo",
        "arguments": {"combo_id": combo_name}
    })
    
    # Parse the nested JSON response
    try:
        result_data = result.get("result", {})
        content = result_data.get("content", [])
        if content and isinstance(content, list) and len(content) > 0:
            text_content = content[0].get("text", "")
            if text_content:
                data = json.loads(text_content)
            else:
                data = {}
        else:
            data = {}
        recommended = data.get("recommended_order", [])
        details = data.get("details", [])
        
        # Update global state
        with LATEST_PROBES_LOCK:
            LATEST_PROBES[combo_name] = {
                "timestamp": time.time(),
                "combo": combo_name,
                "recommended_order": recommended,
                "details": details,
                "error": None
            }
        
        print(f"  Recommended order: {recommended}")
        for d in details:
            print(f"    {d['model']}: {d['status']} ({d.get('latency_ms', '?')}ms)")
        
        if AUTO_APPLY and recommended:
            print(f"  Auto-applying new priority order...")
            apply_result = call_mcp("tools/call", {
                "name": "set_combo_priority",
                "arguments": {"combo_id": combo_name, "model_order": recommended}
            })
            print(f"  Applied: {apply_result}")
    except Exception as e:
        error_msg = str(e)
        print(f"  Error parsing probe result: {error_msg}")
        with LATEST_PROBES_LOCK:
            LATEST_PROBES[combo_name] = {
                "timestamp": time.time(),
                "combo": combo_name,
                "recommended_order": [],
                "details": [],
                "error": error_msg
            }
            
def probe_and_maybe_apply():
    """Probe all target combos."""
    target_combos = get_target_combos()
    for combo_name in target_combos:
        try:
            probe_combo(combo_name)
        except Exception as e:
            print(f"[{time.ctime()}] Probe failed for {combo_name}: {e}")

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
                    response = {"error": "Combo not found", "combo": combo_name}
            self.wfile.write(json.dumps(response).encode())
        else:
            self.send_response(404)
            self.end_headers()
    
    def log_message(self, format, *args):
        # Suppress default log messages
        pass

def run_health_server():
    server = HTTPServer(('0.0.0.0', HEALTH_PORT), HealthHandler)
    print(f"[{time.ctime()}] Health endpoint server started on port {HEALTH_PORT}")
    server.serve_forever()

if __name__ == "__main__":
    print(f"Starting health monitor (auto-discover combos) every {INTERVAL_SEC}s (AUTO_APPLY={AUTO_APPLY})")
    
    # Start health endpoint server in background thread
    health_thread = threading.Thread(target=run_health_server, daemon=True)
    health_thread.start()
    
    # Initialize MCP session first
    while not initialize_session():
        print(f"[{time.ctime()}] Retrying session initialization in 10s...")
        time.sleep(10)
    
    # Now that session is ready, discover combos
    target_combos = get_target_combos()
    print(f"[{time.ctime()}] Monitoring combos: {target_combos}")
    
    while True:
        try:
            probe_and_maybe_apply()
        except Exception as e:
            print(f"[{time.ctime()}] Probe failed: {e}")
        time.sleep(INTERVAL_SEC)