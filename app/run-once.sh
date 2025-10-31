#!/usr/bin/env bash
set -euo pipefail

# Garante que os imports "app...." funcionem
export PYTHONUNBUFFERED=1
export PYTHONPATH=/app

# Opcional: se preferir, também força estar no /app
cd /app

# Executa a automação
python -u -m app.automacao_baixa_encomendas
