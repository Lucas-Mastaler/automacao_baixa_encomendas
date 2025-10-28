# -*- coding: utf-8 -*-
"""
google_sheets_auth.py

Helper central para autenticação com Google Sheets usando Service Account.
Suporta credenciais via:
- GOOGLE_SA_JSON (JSON direto como string)
- GOOGLE_SA_JSON_B64 (JSON em base64)
- GOOGLE_SA_JSON_PATH (caminho para arquivo JSON, padrão: /app/creds/service-account.json)
"""

import os
import json
import base64
from google.oauth2 import service_account
from googleapiclient.discovery import build


def load_sa_credentials(scopes: list[str]):
    """
    Carrega credenciais do Service Account a partir de variáveis de ambiente.
    
    Ordem de prioridade:
    1. GOOGLE_SA_JSON - JSON direto como string
    2. GOOGLE_SA_JSON_B64 - JSON codificado em base64
    3. GOOGLE_SA_JSON_PATH - caminho para arquivo (padrão: /app/creds/service-account.json)
    
    Args:
        scopes: Lista de escopos do Google API (ex: ["https://www.googleapis.com/auth/spreadsheets"])
    
    Returns:
        service_account.Credentials configuradas com os escopos solicitados
    """
    # Opção 1: JSON direto
    raw = os.environ.get("GOOGLE_SA_JSON")
    if raw:
        info = json.loads(raw)
        return service_account.Credentials.from_service_account_info(info, scopes=scopes)

    # Opção 2: JSON em base64
    b64 = os.environ.get("GOOGLE_SA_JSON_B64")
    if b64:
        info = json.loads(base64.b64decode(b64).decode("utf-8"))
        return service_account.Credentials.from_service_account_info(info, scopes=scopes)

    # Opção 3: Arquivo (padrão)
    path = os.environ.get("GOOGLE_SA_JSON_PATH", "/app/creds/service-account.json")
    return service_account.Credentials.from_service_account_file(path, scopes=scopes)


def values_api(creds):
    """
    Retorna a API values() do Google Sheets com cache_discovery=False
    para eliminar o warning "file_cache is only supported with oauth2client<4.0.0".
    
    Args:
        creds: Credenciais do Service Account
    
    Returns:
        spreadsheets().values() resource
    """
    return build("sheets", "v4", credentials=creds, cache_discovery=False).spreadsheets().values()


def sheets_api(creds):
    """
    Retorna a API spreadsheets() do Google Sheets com cache_discovery=False.
    
    Args:
        creds: Credenciais do Service Account
    
    Returns:
        spreadsheets() resource
    """
    return build("sheets", "v4", credentials=creds, cache_discovery=False).spreadsheets()
