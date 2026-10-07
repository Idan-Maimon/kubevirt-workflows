FROM python:3.12-slim

WORKDIR /app

# git binary is required by gitpython at runtime
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY shared/ ./shared/
COPY nodepool_manager/ ./nodepool_manager/

CMD ["python", "-u", "-m", "nodepool_manager.worker"]
