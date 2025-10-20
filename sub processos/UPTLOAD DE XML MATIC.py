# =========================================
# Sessão 0.0 – Parâmetros Google Drive
# =========================================
CAMINHO_JSON = r"C:\Users\Lebebe Home Office\Desktop\AUTOMATIZAÇÕES\DOWLOAD NF MATIC\JSON ACESSO AO DRIVE\automatizacao-google-drive-xml-matic.json"
ID_PASTA_GOOGLE_DRIVE = "1tCYuAqkvgqkFyPJreuInc_Erd-Z1pSJV"
PASTA_LOCAL = r"C:\Users\Lebebe Home Office\Desktop\AUTOMATIZAÇÕES\DOWLOAD NF MATIC\XML"

# =========================================
# Sessão 1.0 – Importação de Bibliotecas
# =========================================
import time
import logging
import os
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
from webdriver_manager.chrome import ChromeDriverManager
from googleapiclient.discovery import build
from google.oauth2 import service_account
import datetime
import re

# =========================================
# Sessão 0.1 – Configurar Logging para arquivo único por execução
# =========================================
LOGS_DIR = r"C:\Users\Lebebe Home Office\Desktop\AUTOMATIZAÇÕES\DOWLOAD NF MATIC\LOGS"
if not os.path.exists(LOGS_DIR):
    os.makedirs(LOGS_DIR)

agora = datetime.datetime.now()
nome_arquivo_log = agora.strftime("log_%Y-%m-%d_%H-%M-%S.txt")
CAMINHO_LOG = os.path.join(LOGS_DIR, nome_arquivo_log)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(CAMINHO_LOG, encoding='utf-8'),
        logging.StreamHandler()
    ]
)

# =========================================
# Sessão 2.0 – Baixar XMLs do Google Drive para o PC
# =========================================
def baixar_xmls_drive():
    if not os.path.exists(PASTA_LOCAL):
        os.makedirs(PASTA_LOCAL)
    SCOPES = ['https://www.googleapis.com/auth/drive']
    creds = service_account.Credentials.from_service_account_file(
        CAMINHO_JSON, scopes=SCOPES)
    service = build('drive', 'v3', credentials=creds)

    query = f"'{ID_PASTA_GOOGLE_DRIVE}' in parents and trashed=false and mimeType != 'application/vnd.google-apps.folder' and name contains '.xml'"
    results = service.files().list(q=query, fields="files(id, name)").execute()
    files = results.get('files', [])
    logging.info(f"Encontrados {len(files)} arquivos XML na pasta do Drive.")

    for file in files:
        file_id = file['id']
        file_name = file['name']
        local_file_path = os.path.join(PASTA_LOCAL, file_name)
        local_file_feito = os.path.join(PASTA_LOCAL, file_name.replace('.xml', '(FEITO).xml'))
        if os.path.exists(local_file_path) or os.path.exists(local_file_feito):
            logging.info(f"Arquivo já baixado: {file_name}")
            continue
        request = service.files().get_media(fileId=file_id)
        with open(local_file_path, "wb") as fh:
            fh.write(request.execute())
        logging.info(f"✅ Baixado: {file_name}")
    logging.info("Todos arquivos XML da pasta do Drive foram baixados para a pasta local.")

# =========================================
# Sessão 3.0 – Login e Importação de XMLs no ERP
# =========================================
def login_sgi(driver, usuario, senha):
    driver.get("https://smart.sgisistemas.com.br/")
    wait = WebDriverWait(driver, 20)
    wait.until(EC.presence_of_element_located((By.ID, "usuario")))
    driver.find_element(By.ID, "usuario").send_keys(usuario)
    driver.find_element(By.NAME, "senha").send_keys(senha)
    driver.find_element(By.NAME, "senha").send_keys(Keys.RETURN)
    wait.until(EC.presence_of_element_located((By.ID, "filial_id")))
    filial_select = Select(driver.find_element(By.ID, "filial_id"))
    filial_select.select_by_visible_text("LEBEBE DEPÓSITO (CD)")
    driver.find_element(By.ID, "botao_prosseguir_informa_local_trabalho").click()
    wait.until(EC.url_to_be("https://smart.sgisistemas.com.br/home"))
    logging.info("✅ Login realizado e filial selecionada.")

def importar_xmls_em_lote(driver, arquivos_xml):
    logging.info("▶️ Iniciando automação de importação de TODOS os XMLs da pasta...")
    nfs_importadas = []
    wait = WebDriverWait(driver, 20)
    try:
        for arquivo in arquivos_xml:
            caminho_xml = os.path.join(PASTA_LOCAL, arquivo)
            logging.info(f"===> Importando arquivo: {arquivo}")
            numero_nf = os.path.splitext(os.path.basename(arquivo))[0]

            driver.get("https://smart.sgisistemas.com.br/importacoes_xml_nfe")
            time.sleep(2)
            botao_buscar = driver.find_element(By.ID, "novo_xml_nfe")
            botao_buscar.click()
            time.sleep(1)
            iframe = driver.find_element(By.ID, "iframe_modal")
            driver.switch_to.frame(iframe)
            time.sleep(1)

            try:
                botao_escolher = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((By.CLASS_NAME, "botao-upload-arquivo"))
                )
                botao_escolher.click()
                time.sleep(1)
            except Exception as e:
                logging.warning("Não achou o botão 'Escolher'. Erro: " + str(e))

            try:
                input_file = WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.ID, "file_field_arquivo"))
                )
                input_file.send_keys(caminho_xml)
                logging.info(f"✅ Arquivo enviado: {caminho_xml}")
            except Exception as e:
                logging.error("Não encontrou o input para upload.")
                driver.save_screenshot("erro_upload_xml.png")
                raise e

            # Modal CNPJ diferente (se aparecer)
            try:
                botao_sim = WebDriverWait(driver, 5).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, 'button[data-bb-handler="confirm"]'))
                )
                botao_sim.click()
                time.sleep(1)
            except Exception:
                pass

            botao_importar = WebDriverWait(driver, 15).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, 'button.btn.btn-success[type="submit"]'))
            )
            botao_importar.click()
            logging.info("✅ Cliquei em 'Importar'.")
            time.sleep(2)

            erro_já_importado = False
            try:
                alerta = driver.find_element(By.CSS_SELECTOR, ".alert-danger")
                if "Chave de Acesso já está em uso" in alerta.text:
                    erro_já_importado = True
                    logging.warning("⚠️ XML já havia sido importado!")
            except Exception:
                pass

            driver.switch_to.default_content()
            novo_nome = caminho_xml.replace('.xml', '(FEITO).xml')
            os.rename(caminho_xml, novo_nome)
            logging.info(f"Arquivo renomeado para: {novo_nome}")

            if not erro_já_importado:
                nfs_importadas.append(numero_nf)
            time.sleep(2)

        logging.info("✅ Todos os XMLs foram processados (importados ou já existiam).")
    except Exception as e:
        logging.error(f"Erro durante o processo: {e}")
        driver.save_screenshot("erro_upload_xml.png")
    return nfs_importadas

# =========================================
# Sessão 3.1 – Vincular produtos das NFs
# =========================================
def codigos_equivalentes(ref, codigo_final):
    if ref == codigo_final:
        return True
    if ref.lstrip('0') == codigo_final.lstrip('0') and 0 < len(ref) - len(ref.lstrip('0')) <= 2:
        return True
    if codigo_final.lstrip('0') == ref.lstrip('0') and 0 < len(codigo_final) - len(codigo_final.lstrip('0')) <= 2:
        return True
    return False

def esperar_vinculo(linha):
    try:
        WebDriverWait(linha, 3).until(
            EC.presence_of_element_located(
                (By.XPATH, './/span[contains(@class,"vincular-desvincular-glyphicon-check")]')
            )
        )
    except:
        pass

def vincular_produtos(driver):
    wait = WebDriverWait(driver, 10)
    tabela = wait.until(EC.presence_of_element_located((By.ID, "lista_itens_importacao_xml_nfe")))
    linhas = tabela.find_elements(By.XPATH, ".//tbody/tr[starts-with(@id, 'xml_nfe_')]")
    for linha in linhas:
        ref = linha.find_element(By.XPATH, './td[@data-title="Referência Fornecedor"]').text.strip()
        produto_td = linha.find_element(By.XPATH, './td[contains(@class, "coluna-produto")]')
        try:
            produto_nome = produto_td.find_element(By.XPATH, ".//strong").text.strip()
        except:
            produto_nome = produto_td.text.strip()
        match_codigo = re.search(r'\((\d+)\)\s*$', produto_nome)
        codigo_final = match_codigo.group(1) if match_codigo else ""
        if produto_nome.startswith("*(Sugestão)") and ref and codigos_equivalentes(ref, codigo_final):
            try:
                botao_caneta = linha.find_element(
                    By.XPATH, './/span[contains(@class,"vincular-desvincular-glyphicon-edit") and contains(@class,"novo-produto-vincular")]'
                )
                botao_caneta.click()
                logging.info(f"✅ Vinculando item {ref}")
                esperar_vinculo(linha)
            except Exception as e:
                logging.warning(f"❌ Erro ao tentar vincular item {ref}: {e}")
        else:
            logging.info(f"⏩ Item {ref} não precisa de vínculo automático.")

def processar_todas_nfs(driver):
    wait = WebDriverWait(driver, 20)
    driver.get("https://smart.sgisistemas.com.br/importacoes_xml_nfe")
    time.sleep(2)
    nfs_ja_processadas = set()
    while True:
        linhas_nf = driver.find_elements(
            By.XPATH,
            '//table//tr['
            'td[@data-title="Status" and contains(text(),"Não Gerada Entrada")] '
            'and td[@data-title="Fornecedor" and contains(translate(text(), "matic", "MATIC"), "MATIC ")]'
            ']'
        )
        linhas_nf = [linha for linha in linhas_nf if
            linha.find_element(By.XPATH, './td[@data-title="Número NF-e"]/a').text.strip() not in nfs_ja_processadas
        ]
        if not linhas_nf:
            logging.info("✅ Não há NFs MATIC pendentes para vincular.")
            break
        logging.info(f"🔍 Encontradas {len(linhas_nf)} NFs MATIC para vincular.")
        linha_nf = linhas_nf[0]
        numero_nf = linha_nf.find_element(By.XPATH, './td[@data-title="Número NF-e"]/a').text.strip()
        logging.info(f"➡️ Processando NF {numero_nf}")
        nfs_ja_processadas.add(numero_nf)
        link_nf = linha_nf.find_element(By.XPATH, './td[@data-title="Número NF-e"]/a')
        driver.execute_script("arguments[0].click();", link_nf)
        try:
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located(
                    (By.XPATH, '//table[@id="lista_itens_importacao_xml_nfe"]//tr[starts-with(@id, "xml_nfe_")]')
                )
            )
        except Exception as e:
            logging.warning("❌ Tabela de produtos não carregou! Tentando próximo...")
        vincular_produtos(driver)
        driver.get("https://smart.sgisistemas.com.br/importacoes_xml_nfe")
        time.sleep(2)

def processar_entradas_nfs(driver):
    nfs_ok = []
    mensagens_erro = []
    nfs_com_erro = []
    wait = WebDriverWait(driver, 15)
    while True:
        driver.get("https://smart.sgisistemas.com.br/importacoes_xml_nfe")
        try:
            wait.until(EC.presence_of_element_located((By.TAG_NAME, "table")))
        except Exception as e:
            print("Não encontrou a tabela de importações. Erro:", e)
            break

        linhas_nf = driver.find_elements(
            By.XPATH,
            '//table//tr[td[@data-title="Status" and contains(text(),"Não Gerada Entrada")] '
            'and td[@data-title="Fornecedor" and contains(translate(text(), "matic", "MATIC"), "MATIC ")]'
            ']'
        )

        if not linhas_nf:
            print("✅ Não há mais NFs MATIC pendentes para entrada.")
            break

        encontrou_nf_para_processar = False
        for linha_nf in linhas_nf:
            numero_nf = linha_nf.find_element(By.XPATH, './td[@data-title="Número NF-e"]/a').text.strip()
            if numero_nf in nfs_com_erro:
                print(f"Pulando NF {numero_nf} pois já deu erro antes.")
                continue

            encontrou_nf_para_processar = True
            print(f"\n➡️ Processando NF {numero_nf}")
            link_nf = linha_nf.find_element(By.XPATH, './td[@data-title="Número NF-e"]/a')
            driver.execute_script("arguments[0].click();", link_nf)
            try:
                gerar_entrada_na_nf(driver)
                preencher_quantidades_deposito_cd(driver)
                tem_desconto = verificar_se_tem_desconto(driver)
                preencher_outros_acrescimos(driver, tem_desconto)
                selecionar_forma_pagamento_boleto(driver)

                current_url = driver.current_url
                if "numero_lancamento=" in current_url:
                    numero_lancamento = current_url.split("numero_lancamento=")[-1]
                    link_entrada = f"https://smart.sgisistemas.com.br/entrada?numero_lancamento={numero_lancamento}"
                    nfs_ok.append((numero_nf, link_entrada))
                    print(f"NF {numero_nf} processada com sucesso! Link: {link_entrada}")
                else:
                    mensagens_erro.append(f"- NF Nº {numero_nf} DEU ERRO - Não chegou na tela de lançamento!")
                    nfs_com_erro.append(numero_nf)
            except Exception as e:
                msg_erro = str(e)
                print(f"⚠️ Erro inesperado ao processar NF {numero_nf}: {msg_erro}")
                mensagens_erro.append(f"- NF Nº {numero_nf} DEU ERRO - \"{msg_erro}\"")
                nfs_com_erro.append(numero_nf)
            driver.get("https://smart.sgisistemas.com.br/importacoes_xml_nfe")
            time.sleep(1)
            break  # Processa uma nota por vez

        if not encontrou_nf_para_processar:
            print("Todas as NFs pendentes já foram tentadas e deram erro.")
            break

    return nfs_ok, mensagens_erro


# =========================================
# Sessão 4.0 – Renomear arquivos no Google Drive para (FEITO)
# =========================================
def renomear_feitos_no_drive():
    SCOPES = ['https://www.googleapis.com/auth/drive']
    creds = service_account.Credentials.from_service_account_file(
        CAMINHO_JSON, scopes=SCOPES)
    service = build('drive', 'v3', credentials=creds)
    arquivos_feitos = [
        f for f in os.listdir(PASTA_LOCAL)
        if f.lower().endswith('(feito).xml')
    ]
    for nome_feito in arquivos_feitos:
        nome_original = nome_feito.replace('(FEITO)', '').replace('  ', ' ').strip()
        nome_no_drive = nome_original
        nome_novo_drive = nome_original.replace('.xml', '(FEITO).xml')
        query = f"'{ID_PASTA_GOOGLE_DRIVE}' in parents and trashed=false and name = '{nome_no_drive}'"
        result = service.files().list(q=query, fields="files(id, name)").execute()
        files = result.get('files', [])
        if files:
            file_id = files[0]['id']
            service.files().update(
                fileId=file_id,
                body={'name': nome_novo_drive}
            ).execute()
            print(f"✅ Arquivo {nome_no_drive} renomeado para {nome_novo_drive} no Drive.")
        else:
            print(f"⏩ Arquivo {nome_no_drive} não encontrado no Drive, pode já estar renomeado.")
    print("Todos os arquivos (FEITO) foram renomeados no Google Drive.")

# =========================================
# Sessão 5.0 – Notificar Whatsapp
# =========================================
def enviar_whatsapp(numeros_nf, chrome_user_dir):
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.support.ui import WebDriverWait
    import time

    if not numeros_nf:
        print("Nenhuma NF para enviar no WhatsApp. Pulando envio.")
        return

    options = webdriver.ChromeOptions()
    options.add_argument(f"--user-data-dir={chrome_user_dir}")
    options.add_argument("--start-maximized")
    driver = webdriver.Chrome(options=options)
    try:
        driver.get("https://web.whatsapp.com/")
        print("Aguardando WhatsApp Web carregar (escaneie o QR se necessário)...")

        tentativas = 0
        carregou = False

        while tentativas < 50:
            time.sleep(10)
            tentativas += 1
            try:
                driver.find_element(By.XPATH, '//div[@role="textbox" and @contenteditable="true"]')
                carregou = True
                print("WhatsApp Web carregado!")
                break
            except:
                try:
                    carregando = driver.find_element(By.XPATH, "//*[contains(text(),'Carregando conversas')]")
                    print(f"Tentativa {tentativas}: WhatsApp ainda carregando conversas...")
                except:
                    print(f"Tentativa {tentativas}: WhatsApp carregando, mas texto padrão não encontrado...")
        if not carregou:
            print("TELA DE CARREGANDO MENSAGENS DEMOROU DEMAIS")
            driver.save_screenshot("erro_carregando_conversas.png")
            driver.quit()
            return

        caixa_pesquisa = driver.find_element(By.XPATH, '//div[@role="textbox" and @contenteditable="true"]')
        caixa_pesquisa.click()
        time.sleep(1)
        caixa_pesquisa.send_keys("AVISO/GRUPO - POS VENDA")
        time.sleep(2)
        caixa_pesquisa.send_keys(Keys.ENTER)
        time.sleep(2)

        mensagem = "*MATIC XML IMPORTADA!*\n"
        for nf in numeros_nf:
            mensagem += f"- XML {nf}\n"

        caixa_msg = driver.find_element(By.XPATH, '//footer//div[contains(@contenteditable,"true")]')
        caixa_msg.click()
        caixa_msg.send_keys(mensagem)
        caixa_msg.send_keys(Keys.ENTER)
        print("Mensagem enviada com sucesso para o grupo AVISO/GRUPO - POS VENDA!")
        time.sleep(2)
    except Exception as e:
        print(f"Erro ao enviar mensagem no WhatsApp: {e}")
        driver.save_screenshot("erro_whatsapp.png")
    finally:
        driver.quit()

# =========================================
# Sessão 6.0 – EXECUÇÃO DO FLUXO COMPLETO
# =========================================
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    baixar_xmls_drive()
    arquivos_xml = [
        f for f in os.listdir(PASTA_LOCAL)
        if f.lower().endswith('.xml') and '(feito)' not in f.lower()
    ]
    if not arquivos_xml:
        print("Nenhum XML novo para importar. Encerrando processo.")
    else:
        options = webdriver.ChromeOptions()
        options.add_argument("--start-maximized")
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        try:
            login_sgi(driver, "AUTOMACOES.lebebe", "automacoes")
            nfs_importadas = importar_xmls_em_lote(driver, arquivos_xml)
            processar_todas_nfs(driver)  # VINCULA PRODUTOS
            nfs_ok, mensagens_erro = processar_entradas_nfs(driver)  # DÁ ENTRADA NAS NF E PEGA LINKS E ERROS
        finally:
            driver.quit()
        renomear_feitos_no_drive()

        # Monta mensagem do WhatsApp
        if nfs_ok or mensagens_erro:
            mensagem = "*MATIC XML - IMPORTADA!*\n"
            for numero_nf, link in nfs_ok:
                mensagem += f"- XML NF {numero_nf} - LINK DA ENTRADA: {link}\n"
            if mensagens_erro:
                mensagem += "\n*AVISOS!*\n"
                for aviso in mensagens_erro:
                    mensagem += f"{aviso}\n"
            print("Mensagem para WhatsApp:\n", mensagem)
            chrome_user_dir = r"C:\Users\Lebebe Home Office\Desktop\AUTOMATIZAÇÕES\CHROME_WPP_AUTOMATION"
            enviar_whatsapp([mensagem], chrome_user_dir)
        print("🚀 Processo de importação, vinculação e entrada concluído!")
        
        