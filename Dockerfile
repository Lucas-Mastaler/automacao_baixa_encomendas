FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    chromium \
    chromium-driver \
    fonts-liberation \
    ca-certificates \
    curl \
    unzip \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app

RUN mkdir -p /app/logs /app/creds /app/downloads /app/chrome-profile

ENV PYTHONUNBUFFERED=1 \
    CHROME_BIN=/usr/bin/chromium \
    GOOGLE_SA_JSON_PATH=/app/creds/service-account.json \
    LOGS_DIR=/app/logs \
    DOWNLOAD_DIR=/app/downloads

CMD ["python","-u","app/automacao_baixa_encomendas.py"]
