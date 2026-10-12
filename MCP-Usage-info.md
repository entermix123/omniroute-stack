
### 6️⃣ Verify the setup
Open WebUI – go to http://localhost:3000 in your browser.
Log in (or create a new account) and you should see the list of models that OmniRoute knows about.

### Check the MCP health endpoint (optional):
curl http://localhost:8000/mcp -X POST -d '{"jsonrpc":"2.0","method":"tools/call","params":{"name":"health_check"}}'

You should see "healthy".

### Test a probe (optional):
curl http://localhost:8000/mcp -H "Content-Type: application/json" -X POST -d '{"jsonrpc":"2.0","method":"tools/call","params":{"name":"probe_combo","arguments":{"combo_id":"nvidia-free-stack"}}}'

The response will be a JSON object containing the status of each model and a recommended priority order.

### 1️⃣ Check health of a single model
curl -s http://localhost:8000/mcp -H "Content-Type: application/json" -X POST -d '{"jsonrpc":"2.0","method":"tools/call","params":{"name":"probe_model","arguments":{"model_id":"nvidia-free-stack"}}}'

### 2️⃣ Probe the whole combo and get a recommended order
curl -s http://localhost:8000/mcp -H "Content-Type: application/json" -X POST -d '{"jsonrpc":"2.0","method":"tools/call","params":{"name":"probe_combo","arguments":{"combo_id":"nvidia-free-stack"}}}'

### 3️⃣ Apply the recommended order (replace with the order you got)
curl -s http://localhost:8000/mcp -H "Content-Type: application/json" -X POST -d '{"jsonrpc":"2.0","method":"tools/call","params":{"name":"set_combo_priority","arguments":{"combo_id":"nvidia-free-stack","model_order":["phi-2","codellama-7b","nvidia-free-stack"]}}}'

**Quick cheat‑sheet**

| Action | Command (run on Windows PowerShell) |
|--------|--------------------------------------|
| Export combos | `curl -s http://localhost:20128/v1/combos -H "Authorization: Bearer (Get-Content .\ .env | Select-String -Pattern 'API_KEY' | ForEach-Object {$_.Line.Split('=')[1]})" > combos.json` |
| Export models | `curl -s http://localhost:20128/v1/models -H "Authorization: Bearer (Get-Content .\ .env | Select-String -Pattern 'API_KEY' | ForEach-Object {$_.Line.Split('=')[1])}" > models.json` |
| Backup everything (tar) | `docker exec omnroute tar czf /tmp/omnroute-data.tar -C /data .` <br> `docker cp omnroute:/tmp/omnroute-data.tar .\omnroute-data-backup.tar` |
| Copy export into Docker volume | `copy combos-export.json .\data\omnroute\combos.json` |
| Restart stack | `docker compose down && docker compose up -d` |