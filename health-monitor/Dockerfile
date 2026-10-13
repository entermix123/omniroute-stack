# health-monitor/Dockerfile
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1
RUN pip install --no-cache-dir requests
WORKDIR /app
COPY monitor.py /app/monitor.py
CMD ["python", "-u", "monitor.py"]