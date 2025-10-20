# =========================================
# Sessão 0.0 – Parâmetros Google Drive
# =========================================

CAMINHO_JSON = r"C:\Users\Lebebe Home Office\Desktop\AUTOMATIZAÇÕES\DOWLOAD NF MATIC\JSON ACESSO AO DRIVE\automatizacao-google-drive-xml-matic.json"
ID_PASTA_GOOGLE_DRIVE = "1tCYuAqkvgqkFyPJreuInc_Erd-Z1pSJV"  # Pegue na URL da pasta do Drive
PASTA_LOCAL = r"C:\Users\Lebebe Home Office\Desktop\AUTOMATIZAÇÕES\DOWLOAD NF MATIC\XML"

# =========================================
# Sessão 1.0 – Importação de Bibliotecas
# =========================================
import time
import logging
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
from webdriver_manager.chrome import ChromeDriverManager
# Google Drive API imports
import os
from googleapiclient.discovery import build
from google.oauth2 import service_account

# =========================================
# Sessão 1.1 – Função para baixar XMLs do Google Drive
# =========================================

def baixar_xmls_drive():
    # Cria a pasta local se não existir
    if not os.path.exists(PASTA_LOCAL):
        os.makedirs(PASTA_LOCAL)
    
    # Configura credencial
    SCOPES = ['https://www.googleapis.com/auth/drive']
    creds = service_account.Credentials.from_service_account_file(
        CAMINHO_JSON, scopes=SCOPES)
    service = build('drive', 'v3', credentials=creds)

    # Busca todos arquivos .xml da pasta no Drive
    query = f"'{ID_PASTA_GOOGLE_DRIVE}' in parents and trashed=false and mimeType != 'application/vnd.google-apps.folder' and name contains '.xml'"
    results = service.files().list(q=query, fields="files(id, name)").execute()
    files = results.get('files', [])

    logging.info(f"Encontrados {len(files)} arquivos XML na pasta do Drive.")

    for file in files:
        file_id = file['id']
        file_name = file['name']
        
        # Não baixar se já existir o arquivo (com ou sem '(FEITO)')
        local_file_path = os.path.join(PASTA_LOCAL, file_name)
        local_file_feito = os.path.join(PASTA_LOCAL, file_name.replace('.xml', '(FEITO).xml'))
        if os.path.exists(local_file_path) or os.path.exists(local_file_feito):
            logging.info(f"Arquivo já baixado: {file_name}")
            continue

        # Baixa o arquivo XML
        request = service.files().get_media(fileId=file_id)
        with open(local_file_path, "wb") as fh:
            fh.write(request.execute())
        logging.info(f"✅ Baixado: {file_name}")

    logging.info("Todos arquivos XML da pasta do Drive foram baixados para a pasta local.")

# =========================================
# Sessão 1.2 – Executar a função de baixar XMLs
# =========================================

if __name__ == "__main__":
    baixar_xmls_drive()
    # importar_xml_erp()  # Só descomentar quando quiser rodar a parte do ERP em sequência
