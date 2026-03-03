FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8080

# Use watchdog or simple uvicorn reload for hot-reloading skills/
CMD ["python", "server.py"]
