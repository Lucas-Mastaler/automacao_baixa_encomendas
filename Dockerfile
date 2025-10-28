FROM python:3.11-slim

# 1) Chrome + Chromedriver do sistema (mesma versão)
RUN apt-get update && apt-get install -y --no-install-recommends \
    chromium \
    chromium-driver \
    fonts-liberation \
    ca-certificates \
    curl \
    unzip \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 2) Dependências Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 3) Copie SOMENTE o pacote app/ (evita arquivo duplicado na raiz)
COPY app/ ./app

# 4) Pastas de trabalho
RUN mkdir -p /app/logs /app/creds /app/downloads /app/chrome-profiles

# 5) Variáveis de ambiente (use o chromedriver do sistema; perfil base único por execução)
ENV PYTHONUNBUFFERED=1 \
    CHROME_BIN=/usr/bin/chromium \
    CHROMEDRIVER_BIN=/usr/bin/chromedriver \
    CHROME_USER_DIR_BASE=/app/chrome-profiles \
    GOOGLE_SA_JSON_PATH=/app/creds/service-account.json \
    LOGS_DIR=/app/logs \
    DOWNLOAD_DIR=/app/downloads

# 6) Rode como módulo (evita ambiguidade de caminho)
CMD ["python", "-u", "-m", "app.automacao_baixa_encomendas"]
