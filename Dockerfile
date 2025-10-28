FROM python:3.11-slim

# 1) Chrome + Chromedriver do sistema
RUN apt-get update && apt-get install -y --no-install-recommends \
    chromium \
    chromium-driver \
    fonts-liberation \
    ca-certificates \
    curl \
    unzip \
    cron \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 2) Dependências Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 3) Código
COPY app/ ./app

# 4) Pastas de trabalho
RUN mkdir -p /app/logs /app/creds /app/downloads /app/chrome-profile

# 5) Variáveis de ambiente padrão (as do EasyPanel sobrescrevem)
ENV PYTHONUNBUFFERED=1 \
    CHROME_BIN=/usr/bin/chromium \
    CHROMEDRIVER_BIN=/usr/bin/chromedriver \
    CHROME_USER_DIR_BASE=/app/chrome-profile \
    GOOGLE_SA_JSON_PATH=/app/creds/service-account.json \
    LOGS_DIR=/app/logs \
    DOWNLOAD_DIR=/app/downloads \
    TZ=America/Sao_Paulo

# 6) Cron job (07h–19h BRT, todo início de hora)
#    Usamos /etc/cron.d (formato: "<schedule> <user> <command>")
RUN printf "SHELL=/bin/bash\nPATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin\nTZ=America/Sao_Paulo\n\n" > /etc/cron.d/baixa-encomendas \
 && echo "*/30 7-19 * * * root flock -n /app/.lock /app/app/run-once.sh >> /app/logs/cron.log 2>&1" >> /etc/cron.d/baixa-encomendas\
 && chmod 0644 /etc/cron.d/baixa-encomendas

# 7) Mantenha o cron em foreground (precisa para container não encerrar)
CMD ["cron", "-f"]
