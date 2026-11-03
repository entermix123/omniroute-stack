FROM python:3.12-slim

# Install MCP SDK (includes HTTP transport) and requests
RUN pip install --no-cache-dir mcp[http] requests

WORKDIR /app
COPY server.py /app/server.py

EXPOSE 8000

CMD ["python", "server.py"]
