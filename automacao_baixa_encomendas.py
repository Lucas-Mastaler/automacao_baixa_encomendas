# -*- coding: utf-8 -*-
"""
automacao_baixa_encomendas.py

Fluxo completo:

1. Lê a planilha “PROCESSO ENTRADA” no Google Sheets.
2. Seleciona as NFs que precisam de tratamento.
3. Abre o SGI, faz login e visita cada link de lançamento da NF.
4. Se existir, clica em “Finalizar Entrada” e confirma.
5. Extrai da tela de Entrada todos os códigos de produto e quantidades recebidas.
6. Para cada código:
      • Vai à tela /reservas_produtos,
      • Garante que o multiselect “Situação” fique SOMENTE em Pendente,
      • Filtra pelo código,
      • Decide se há itens a baixar:
          – se não houver → próximo código;
          – se houver mais itens do que quantidade recebida → baixa em ordem de entrega
            (data mais próxima primeiro);
          – se houver mesma ou menor quantidade → baixa todos.
      • Baixa = abrir link da encomenda, clicar no X preto (desvincular) se existir,
        depois no X vermelho (cancelar item); confirma modais.
7. Volta à tela de Reservas e continua até acabar a NF.
"""

# --------------------------------------------------------------------------- #
# IMPORTS
# --------------------------------------------------------------------------- #
import re, time, unicodedata
import pandas as pd
import traceback
from functools import wraps
from datetime import datetime
from google.oauth2 import service_account
from googleapiclient.discovery import build
from functools import wraps
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.wait import WebDriverWait as _WDW
from selenium.common.exceptions import (
    TimeoutException,
    NoSuchElementException,
    ElementClickInterceptedException,
    ElementNotInteractableException,
    StaleElementReferenceException
)
import logging

# --- LOGS EM ARQUIVO + CONSOLE ---
import os
from datetime import datetime as dt

LOGS_DIR = r"C:\Users\Lebebe Home Office\Desktop\AUTOMATIZAÇÕES\ENTRADA MATIC\LOGS"  # ajuste se quiser
os.makedirs(LOGS_DIR, exist_ok=True)

LOG_FILE = os.path.join(
    LOGS_DIR,
    dt.now().strftime("baixas_encomendas_%Y-%m-%d_%H-%M-%S.log")
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(),                        # console
        logging.FileHandler(LOG_FILE, encoding="utf-8") # arquivo
    ]
)

logging.info("▶️ Iniciando automação de BAIXA DE ENCOMENDAS")
logging.info(f"Log em arquivo: {LOG_FILE}")



# =========================================
# Sessão 1.0 – Notificar WhatsApp 
# =========================================
def enviar_whatsapp_texto(mensagem, chrome_user_dir):
    """
    Envia 'mensagem' para o grupo AVISOS/GRUPO - POS VENDA no WhatsApp Web,
    usando o perfil persistente do Chrome (chrome_user_dir).
    Mantém o loop de verificação “Carregando conversas…” e screenshot de erro.
    """
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.support.ui import WebDriverWait
    import time

    options = webdriver.ChromeOptions()
    options.add_argument(f"--user-data-dir={chrome_user_dir}")
    options.add_argument("--start-maximized")
    driver = webdriver.Chrome(options=options)

    try:
        driver.get("https://web.whatsapp.com/")
        logging.info("Aguardando WhatsApp Web carregar (escaneie o QR se necessário)…")

        tentativas, carregou = 0, False
        while tentativas < 50:         # 50 × 10 s = ~8 min
            time.sleep(10)
            tentativas += 1
            try:
                driver.find_element(By.XPATH, '//div[@role="textbox" and @contenteditable="true"]')
                carregou = True
                logging.info("WhatsApp Web carregado!")
                break
            except:
                try:
                    driver.find_element(By.XPATH, "//*[contains(text(),'Carregando conversas')]")
                    logging.info(f"Tentativa {tentativas}: ainda carregando conversas…")
                except:
                    logging.info(f"Tentativa {tentativas}: aguardando interface…")

        if not carregou:
            logging.error("WhatsApp não carregou a tempo.")
            driver.save_screenshot(os.path.join(LOGS_DIR, "erro_whatsapp.png"))
            return

        # -------- procurar o grupo --------
        caixa_pesq = driver.find_element(By.XPATH, '//div[@role="textbox" and @contenteditable="true"]')
        caixa_pesq.clear()
        caixa_pesq.click()
        time.sleep(1)
        caixa_pesq.send_keys("AVISOS/GRUPO - POS VENDA")
        time.sleep(2)
        caixa_pesq.send_keys(Keys.ENTER)
        time.sleep(2)

        # -------- enviar a mensagem --------
        caixa_msg = driver.find_element(By.XPATH, '//footer//div[@contenteditable="true"]')
        caixa_msg.click()
        for linha in mensagem.strip().splitlines():
            caixa_msg.send_keys(linha)
            caixa_msg.send_keys(Keys.SHIFT, Keys.ENTER)
        caixa_msg.send_keys(Keys.ENTER)

        logging.info("Mensagem de relatório enviada com sucesso.")
        time.sleep(2)

    except Exception as e:
        logging.error(f"Erro ao enviar mensagem no WhatsApp: {e}")
        driver.save_screenshot(os.path.join(LOGS_DIR, "erro_whatsapp_loading.png"))
    finally:
        driver.quit()

# --------------------------------------------------------------------------- #
# CONFIGURAÇÕES GERAIS
# --------------------------------------------------------------------------- #
CAMINHO_JSON = r"C:\Users\Lebebe Home Office\Desktop\AUTOMATIZAÇÕES\DOWLOAD NF MATIC\JSON ACESSO AO DRIVE\automatizacao-google-drive-xml-matic.json"
PLANILHA_ID  = "1Xs-z_LDbB1E-kp9DK-x4-dFkU58xKpYhz038NNrTb54"

ABA_PROCESSO = "PROCESSO ENTRADA"   # <-- era ABA_PROCESSO antes
ABA_LOGS     = "LOGS ENTRADA"       # <-- nova aba para logs

USUARIO_SGI  = "AUTOMACOES.lebebe"
SENHA_SGI    = "automacoes"

URL_SGI      = "https://smart.sgisistemas.com.br"
URL_RESERVAS = f"{URL_SGI}/reservas_produtos"

WAIT = 20   # timeout padrão para WebDriverWait

# --------------------------------------------------------------------------- #
# PLANILHA GOOGLE SHEETS
# --------------------------------------------------------------------------- #
def ler_tabela_processo_entrada() -> pd.DataFrame:
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    creds  = service_account.Credentials.from_service_account_file(CAMINHO_JSON, scopes=scopes)
    sheets = build("sheets", "v4", credentials=creds, cache_discovery=False).spreadsheets()
    # Amplia o range para não “cortar” colunas:
    values = (
        sheets.values()
        .get(spreadsheetId=PLANILHA_ID, range=f"'{ABA_PROCESSO}'!A1:ZZ")
        .execute()
        .get("values", [])
    )
    if not values:
        return pd.DataFrame()
    # Linha 1 = header
    df = pd.DataFrame(values[1:], columns=values[0])
    return df

# ----------------- NORMALIZAÇÃO E BUSCA DE COLUNAS -----------------
def _norm_text(s: str) -> str:
    """Normaliza texto: sem acentos, minúsculo, remove símbolos comuns, colapsa espaços."""
    if s is None:
        return ""
    s = str(s)
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))  # remove acentos
    s = s.lower()
    s = re.sub(r"[/()\-–—_\[\]:]+", " ", s)  # troca separadores por espaço
    s = re.sub(r"\s+", " ", s).strip()
    return s

def _find_col(headers, required_parts: list[str]) -> str | None:
    """
    Retorna o NOME REAL da coluna cujo cabeçalho (normalizado) contém TODOS os 'required_parts'.
    Ex.: required_parts = ['data','emissao','nf']
    """
    headers_norm = {h: _norm_text(h) for h in headers}
    req = [ _norm_text(p) for p in required_parts ]
    for original, hnorm in headers_norm.items():
        if all(p in hnorm for p in req):
            return original
    return None

def _get(row, required_parts: list[str], default=None, log_label: str | None = None):
    """
    Busca 'a melhor coluna' por padrões. Se não achar, registra log (aba LOGS) e retorna default.
    """
    col = _find_col(row.index, required_parts)
    if col is None:
        msg = f"Coluna não encontrada: {' + '.join(required_parts)}. Headers: {list(row.index)}"
        append_log_sheets(log_label or "COLUNA AUSENTE", msg)
        return default
    return row[col]


def marcar_baixa_concluida(num_nf: str):
    """
    Escreve TRUE na coluna I (checkbox) da linha onde está a NF - num_nf.
    """
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    creds  = service_account.Credentials.from_service_account_file(CAMINHO_JSON, scopes=scopes)
    sheets = build("sheets", "v4", credentials=creds, cache_discovery=False).spreadsheets()

    # 1) pega apenas a coluna A (número NF) para localizar a linha
    col_nf = (
        sheets.values()
        .get(spreadsheetId=PLANILHA_ID, range=f"'{ABA_PROCESSO}'!A2:A")
        .execute()
        .get("values", [])
    )
    for idx, val in enumerate(col_nf, start=2):          # começa na linha 2
        if val and val[0].strip() == str(num_nf):
            linha_alvo = idx
            break
    else:
        print(f"⚠️  NF {num_nf}: não localizada na planilha para marcar coluna I.")
        return

    # 2) coluna I == coluna 9 → índice 8 (A=1, …, I=9)
    range_alvo = f"'{ABA_PROCESSO}'!I{linha_alvo}"
    body = {"values": [["TRUE"]]}
    sheets.values().update(
        spreadsheetId=PLANILHA_ID,
        range=range_alvo,
        valueInputOption="USER_ENTERED",
        body=body
    ).execute()
    print(f"  • NF {num_nf}: coluna I marcada como TRUE.")

def pode_dar_entrada(row) -> bool:
    """
    Critérios:
    - NÃO pode quando já tiver XML ENTRADA/ENCOMENDA SGI = TRUE
    - Pode quando RECEBIDO MATIC DEPÓSITO (FORMULÁRIO ENVIADO) = TRUE
      OU quando dias desde DATA EMISSÃO NF > 7
    Tudo com busca robusta por cabeçalhos “parecidos”.
    """
    # Pega os campos por padrões de cabeçalho
    recebido_val = _get(row, ["recebido", "matic", "deposito"], default="", log_label="FALTA RECEBIDO")
    entrada_encomenda_val = _get(row, ["xml", "entrada", "encomenda", "sgi"], default="", log_label="FALTA XML ENTRADA/ENCOMENDA")
    data_emissao_str = _get(row, ["data", "emissao", "nf"], default="", log_label="FALTA DATA EMISSAO")

    recebido_form = str(recebido_val).strip().upper() == "TRUE"
    entrada_encomenda = str(entrada_encomenda_val).strip().upper() == "TRUE"

    # data emissão
    dias_desde_emissao = 0
    try:
        # aceita "dd/mm/aaaa" ou "aaaa-mm-dd" (se vier ISO por acaso)
        s = str(data_emissao_str).strip()
        if re.match(r"\d{2}/\d{2}/\d{4}$", s):
            dt_emis = datetime.strptime(s, "%d/%m/%Y")
        else:
            dt_emis = datetime.fromisoformat(s[:10])
        dias_desde_emissao = (datetime.now() - dt_emis).days
    except Exception:
        append_log_sheets("DATA EMISSÃO INVÁLIDA", f"Valor: {data_emissao_str!r}")

    if entrada_encomenda:
        return False
    return recebido_form or dias_desde_emissao > 7


def append_log_sheets(processo: str, mensagem: str):
    """Acrescenta uma linha na aba LOGS ENTRADA com data/hora, processo e mensagem."""
    try:
        scopes = ["https://www.googleapis.com/auth/spreadsheets"]
        creds  = service_account.Credentials.from_service_account_file(CAMINHO_JSON, scopes=scopes)
        sheets = build("sheets", "v4", credentials=creds, cache_discovery=False).spreadsheets()

        agora = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        body = {
            "values": [[agora, processo, mensagem]]
        }
        sheets.append(
            spreadsheetId=PLANILHA_ID,
            range=f"'{ABA_LOGS}'!A:C",
            valueInputOption="USER_ENTERED",
            insertDataOption="INSERT_ROWS",
            body=body
        ).execute()
    except Exception as e:
        # Em último caso, pelo menos loga no console se até o log falhar
        logging.error(f"Falha ao registrar log no Sheets ({processo}): {e}")

def log_exceptions(processo_nome: str):
    """
    Decorator: se a função levantar exceção, grava LOG no Sheets com
    data/hora, processo e stack trace. Re-lança a exceção após logar.
    """
    def _decorator(func):
        @wraps(func)
        def _wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                tb = traceback.format_exc()
                msg = f"{e.__class__.__name__}: {e}\n\nTRACEBACK:\n{tb}"
                append_log_sheets(processo_nome, msg)
                logging.error(f"[{processo_nome}] {e}\n{tb}")
                raise
        return _wrapper
    return _decorator

# --------------------------------------------------------------------------- #
# SELENIUM – HELPERS
# --------------------------------------------------------------------------- #
# --- no topo: pode remover o webdriver_manager se quiser ---
# from webdriver_manager.chrome import ChromeDriverManager

def novo_driver() -> webdriver.Chrome:
    import os, tempfile, shutil, glob, time
    from selenium.webdriver.chrome.service import Service

    CHROME_BIN = os.environ.get("CHROME_BIN", "/usr/bin/chromium")
    CHROMEDRIVER_BIN = os.environ.get("CHROMEDRIVER_BIN", "/usr/bin/chromedriver")

    if not os.path.exists(CHROME_BIN):
        raise RuntimeError(f"Chromium não encontrado em {CHROME_BIN}.")
    if not os.path.exists(CHROMEDRIVER_BIN):
        raise RuntimeError(f"Chromedriver não encontrado em {CHROMEDRIVER_BIN}.")

    options = webdriver.ChromeOptions()
    options.binary_location = CHROME_BIN

    # Flags essenciais p/ container
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--remote-debugging-port=9222")
    options.add_argument("--disable-software-rasterizer")
    options.add_argument("--disable-features=VizDisplayCompositor")
    options.add_argument("--disable-blink-features=AutomationControlled")

    # PERFIL: gere um diretório ÚNICO por execução para evitar o erro "user data dir in use"
    base_profile = os.environ.get("CHROME_USER_DIR_BASE", "/app/chrome-profiles")
    os.makedirs(base_profile, exist_ok=True)
    unique_profile = tempfile.mkdtemp(prefix="run_", dir=base_profile)
    options.add_argument(f"--user-data-dir={unique_profile}")

    # Downloads (isolados por execução)
    dl_dir = os.environ.get("DOWNLOAD_DIR", "/app/downloads")
    os.makedirs(dl_dir, exist_ok=True)
    options.add_experimental_option("prefs", {"download.default_directory": dl_dir})

    # Workaround: se alguém passar um USER_DATA_DIR fixo por env, limpamos "Singleton*"
    # (não é necessário com o diretório único, mas deixa resiliente)
    def _unlock_profile(path: str):
        for p in glob.glob(os.path.join(path, "Singleton*")):
            try: os.remove(p)
            except Exception: pass

    try:
        _unlock_profile(unique_profile)
    except Exception:
        pass

    service = Service(CHROMEDRIVER_BIN)
    driver = webdriver.Chrome(service=service, options=options)

    # Anexa o caminho do perfil ao objeto p/ limpar depois, se quiser
    driver._lebebe_profile_dir = unique_profile
    return driver

def w(driver) -> WebDriverWait:
    return WebDriverWait(driver, WAIT)

def until_any(self, *conditions):
    return self.until(lambda d: any(c(d) for c in conditions))
_WDW.until_any = until_any

def safe_click(elem):
    """
    Rola o elemento até o centro da tela e tenta clicar.
    Se ainda assim falhar (interceptado ou não-interact-able), usa JavaScript.
    """
    drv = elem._parent              # webdriver
    drv.execute_script(
        "arguments[0].scrollIntoView({block:'center',inline:'center'});", elem
    )
    try:
        elem.click()
    except (ElementClickInterceptedException, ElementNotInteractableException):
        drv.execute_script("arguments[0].click();", elem)
    time.sleep(0.2)

def esperar_sumir_modal(driver, titulo_contains: str | None = None):
    """
    Aguarda o desaparecimento de qualquer .modal-content.
    Se ‘titulo_contains’ for informado, restringe ao modal que contenha esse texto.
    """
    xpath = '//div[contains(@class,"modal-content")]'
    if titulo_contains:
        xpath += f'[.//*[contains(normalize-space(),"{titulo_contains}")]]'

    try:
        WebDriverWait(driver, WAIT).until(
            EC.invisibility_of_element_located((By.XPATH, xpath))
        )
    except TimeoutException:
        pass


# ==== HELPERS ADICIONAIS (iframe, JS, retries) ====

def switch_to_frame_with(driver, by, value, timeout=10):
    """Tenta encontrar o locator no root; se não, percorre os iframes."""
    driver.switch_to.default_content()
    end = time.time() + timeout
    while time.time() < end:
        # tenta no root
        try:
            if driver.find_elements(by, value):
                return True
        except Exception:
            pass
        # tenta nos iframes
        frames = driver.find_elements(By.TAG_NAME, "iframe")
        for f in frames:
            try:
                driver.switch_to.default_content()
                driver.switch_to.frame(f)
                if driver.find_elements(by, value):
                    return True
            except Exception:
                continue
        time.sleep(0.2)
    driver.switch_to.default_content()
    return False

def safe_scroll_into_view(driver, el):
    try:
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
    except Exception:
        pass

def js_set_value(driver, el, text):
    try:
        driver.execute_script("arguments[0].value='';", el)
        driver.execute_script("arguments[0].value=arguments[1];", el, text)
        driver.execute_script("arguments[0].dispatchEvent(new Event('input',{bubbles:true}));", el)
        driver.execute_script("arguments[0].dispatchEvent(new Event('change',{bubbles:true}));", el)
        return True
    except Exception:
        return False

def try_type_with_retries(driver, locator, text, wait, label, tries=3):
    by, value = locator
    for attempt in range(1, tries + 1):
        try:
            found = switch_to_frame_with(driver, by, value, timeout=5)
            if not found:
                raise TimeoutException(f"{label}: campo não localizado (root/iframes).")

            el = wait.until(EC.visibility_of_element_located(locator))
            safe_scroll_into_view(driver, el)
            try:
                wait.until(EC.element_to_be_clickable(locator)).click()
            except (ElementClickInterceptedException, ElementNotInteractableException):
                driver.execute_script("arguments[0].click();", el)

            try:
                el.clear()
            except Exception:
                driver.execute_script("arguments[0].value='';", el)

            try:
                el.send_keys(text)
                return True
            except ElementNotInteractableException as e:
                # fallback por JS
                if js_set_value(driver, el, text):
                    return True
                else:
                    raise e

        except (TimeoutException, ElementNotInteractableException, ElementClickInterceptedException, StaleElementReferenceException) as e:
            logging.warning(f"{label}: tentativa {attempt}/{tries} falhou ({e}). Recarregando…")
            try:
                driver.switch_to.default_content()
                driver.refresh()
                WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
                if driver.current_url != URL_SGI:
                    driver.get(URL_SGI)
            except Exception:
                pass
    return False

def click_with_retries(driver, locator, wait, label, tries=3):
    by, value = locator
    for attempt in range(1, tries + 1):
        try:
            found = switch_to_frame_with(driver, by, value, timeout=5)
            if not found:
                raise TimeoutException(f"{label}: botão não localizado (root/iframes).")
            el = wait.until(EC.element_to_be_clickable(locator))
            safe_scroll_into_view(driver, el)
            try:
                el.click()
            except (ElementClickInterceptedException, ElementNotInteractableException):
                driver.execute_script("arguments[0].click();", el)
            return True
        except (TimeoutException, ElementClickInterceptedException, ElementNotInteractableException, StaleElementReferenceException) as e:
            logging.warning(f"{label}: tentativa {attempt}/{tries} falhou ({e}). Recarregando…")
            try:
                driver.switch_to.default_content()
                driver.refresh()
                WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
            except Exception:
                pass
    return False


# ------------- RETRY GENÉRICO COM RECUPERAÇÃO DE CONTEXTO -------------
def with_retries(max_tries, label, action, recover):
    """
    Executa 'action()' com até 'max_tries' tentativas.
    Se falhar, chama 'recover(tentativa_idx)' para resetar o contexto e tenta de novo.
    - label: nome curto do processo para logs.
    - action: função sem args que executa o passo crítico.
    - recover: função que recebe o índice da tentativa (1..max_tries-1) e reabre/reaplica filtros.
    Retorna o valor de action() quando tiver sucesso.
    Levanta a última exceção se todas falharem.
    """
    last_exc = None
    for attempt in range(1, max_tries + 1):
        try:
            return action()
        except Exception as e:
            last_exc = e
            append_log_sheets(f"RETRY {label}", f"Tentativa {attempt} falhou: {e}")
            if attempt < max_tries:
                try:
                    recover(attempt)
                except Exception as r:
                    append_log_sheets(f"RECOVER {label}", f"Falha ao recuperar contexto: {r}")
                    # mesmo assim continua para próxima tentativa
            else:
                # acabou as tentativas
                raise last_exc

# ------------- JANELAS / ABAS SEGURAS -------------
def open_new_tab_and_switch(driver, url):
    """Abre nova aba para 'url' e troca o foco para ela. Retorna (handle_anterior, handle_novo)."""
    prev = driver.current_window_handle
    prev_handles = set(driver.window_handles)
    driver.execute_script("window.open(arguments[0], '_blank');", url)
    # acha o novo handle
    for _ in range(10):
        time.sleep(0.2)
        new_handles = set(driver.window_handles) - prev_handles
        if new_handles:
            new_handle = new_handles.pop()
            driver.switch_to.window(new_handle)
            return prev, new_handle
    # fallback: pega o último
    driver.switch_to.window(driver.window_handles[-1])
    return prev, driver.current_window_handle

def safe_close_current_window(driver, fallback_handle=None):
    """
    Fecha a janela atual se existir; se der NoSuchWindow, ignora.
    Depois tenta voltar para 'fallback_handle' se fornecido e existir.
    """
    try:
        cur = driver.current_window_handle
        driver.close()
    except Exception:
        pass
    # tenta voltar
    try:
        if fallback_handle and fallback_handle in driver.window_handles:
            driver.switch_to.window(fallback_handle)
        else:
            # se sobrou alguma, volta para a primeira
            if driver.window_handles:
                driver.switch_to.window(driver.window_handles[0])
    except Exception:
        pass

def aguardar_status_cancelado(drv, row_id: str, timeout=20) -> bool:
    """
    Aguarda a linha com id=row_id ficar com situação 'cancelado'.
    Rebusca a linha a cada iteração para evitar StaleElement/None.
    Retorna True se confirmar o status; False ao estourar o timeout.
    """
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            row = drv.find_element(By.ID, row_id)
            try:
                status = row.find_element(By.CSS_SELECTOR, "td.campo_situacao").text.strip().lower()
                if status == "cancelado":
                    return True
            except (StaleElementReferenceException, NoSuchElementException):
                # célula re-renderizou; só tentar novamente
                pass
        except NoSuchElementException:
            # a linha pode ter sido removida/re-renderizada momentaneamente
            pass
        time.sleep(0.4)
    return False


# --------------------------------------------------------------------------- #
# LOGIN SGI
# --------------------------------------------------------------------------- #
@log_exceptions("LOGIN SGI")
def login_sgi(driver: webdriver.Chrome):
    driver.get(URL_SGI)
    wait = w(driver)

    # 1) Usuário
    ok_user = try_type_with_retries(driver, (By.ID, "usuario"), USUARIO_SGI, wait, "Usuário")
    if not ok_user:
        raise RuntimeError("Falha ao preencher o usuário após múltiplas tentativas.")

    # 2) Senha (com Enter)
    ok_pass = try_type_with_retries(driver, (By.NAME, "senha"), SENHA_SGI, wait, "Senha")
    if not ok_pass:
        raise RuntimeError("Falha ao preencher a senha após múltiplas tentativas.")
    try:
        # tenta Enter direto
        el_pass = driver.find_element(By.NAME, "senha")
        el_pass.send_keys(Keys.RETURN)
    except Exception:
        # fallback: dispara um Enter via JS
        driver.execute_script("""
            const form = document.querySelector('form') || document;
            form.dispatchEvent(new KeyboardEvent('keydown', {key:'Enter', bubbles:true}));
        """)

    # 3) Seleção da filial (robusta)
    driver.switch_to.default_content()
    logging.info("   ⏳ Aguardando select#filial_id…")
    sel = wait.until(EC.visibility_of_element_located((By.ID, "filial_id")))
    wait.until(EC.element_to_be_clickable((By.ID, "filial_id")))
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", sel)

    try:
        # tenta pelo value conhecido do CD (ajuste se o value mudar)
        Select(sel).select_by_value("5")
    except Exception:
        # fallback por JS + eventos
        driver.execute_script("""
            const el = arguments[0];
            el.value = '5';
            el.dispatchEvent(new Event('input', {bubbles:true}));
            el.dispatchEvent(new Event('change', {bubbles:true}));
        """, sel)

    # 4) Prosseguir
    click_with_retries(driver, (By.ID, "botao_prosseguir_informa_local_trabalho"), wait, "Prosseguir", tries=2)
    wait.until(EC.url_to_be(f"{URL_SGI}/home"))
    print("✅ Login realizado.")

# --------------------------------------------------------------------------- #
# ENTRADA – FINALIZAR & EXTRAI CÓDIGOS
# --------------------------------------------------------------------------- #
@log_exceptions("FINALIZAR ENTRADA")
def finalizar_entrada(driver) -> bool:
    """
    Clica em “Finalizar Entrada”, confirma no modal e
    espera o redirecionamento para /gestao_precos?.
    Retorna True se concluiu; False se não encontrou o botão em 5s.
    """
    try:
        # aguarda só 5s pelo botão
        btn = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.ID, "emitir_documento"))
        )
        safe_click(btn)

        # Modal “Deseja prosseguir? → Sim”
        btn_sim = w(driver).until(
            EC.element_to_be_clickable((
                By.CSS_SELECTOR,
                '.modal-content button[data-bb-handler="confirm"]'
            ))
        )
        safe_click(btn_sim)

        # aguarda sumir o modal
        esperar_sumir_modal(driver, "Documento será finalizado")

        # espera o redirecionamento para gestão de preços
        w(driver).until(EC.url_contains("/gestao_precos?"))
        print("   ✔️ Entrada finalizada (redirecionou para Gestão de Preços).")
        return True

    except TimeoutException:
        print("  • Botão “Finalizar Entrada” não encontrado em 5s; seguindo para reservas.")
    except Exception as e:
        print(f"⚠️  Erro ao finalizar entrada: {e}")
    return False

def tentar_finalizar_entrada_com_retries(driver, link_lancamento: str, numero_nf: str, tentativas: int = 3) -> bool:
    """
    Tenta finalizar a entrada até 'tentativas' vezes.
    A cada falha, reabre o link de lançamento e tenta novamente.
    Retorna True se finalizar; False se, após as tentativas, não conseguir.
    """
    for i in range(1, tentativas + 1):
        if i > 1:
            # Reabre a página antes de tentar novamente
            try:
                driver.get(link_lancamento)
            except Exception as e:
                append_log_sheets("FINALIZAR ENTRADA", f"NF {numero_nf}: erro ao reabrir link na tentativa {i}: {e}")
                time.sleep(2)

        try:
            if finalizar_entrada(driver):
                append_log_sheets("FINALIZAR ENTRADA", f"NF {numero_nf}: finalizada na tentativa {i}.")
                return True
            else:
                append_log_sheets("FINALIZAR ENTRADA", f"NF {numero_nf}: botão não encontrado (tentativa {i}).")
        except Exception as e:
            # O decorator de finalizar_entrada já loga, mas deixo um log leve aqui também
            append_log_sheets("FINALIZAR ENTRADA", f"NF {numero_nf}: erro na tentativa {i}: {e}")

        # pequena pausa entre tentativas
        time.sleep(2)

    # Se chegou aqui, não conseguiu finalizar
    append_log_sheets("FINALIZAR ENTRADA", f"NF {numero_nf}: não finalizada após {tentativas} tentativas; seguir para baixas.")
    return False


@log_exceptions("EXTRAIR CÓDIGOS/QTD ENTRADA")
def extrair_codigos_qtd_entrada(driver) -> list[tuple[int, int]]:
    """
    Na tela de Entrada (/entradas/####), coleta [(codigo_produto, qtd)].
    O código visível (p.ex. “18887”) aparece na 2ª coluna ou dentro do texto.
    """
    w(driver).until(EC.presence_of_element_located((By.ID, "tabela_de_produtos")))
    codigos_qtd = []
    linhas = driver.find_elements(By.XPATH, '//table[@id="tabela_de_produtos"]//tbody/tr')
    for ln in linhas:
        tds = ln.find_elements(By.TAG_NAME, "td")
        if len(tds) < 5:
            continue

        # QUANTIDADE (coluna 5)
        txt_qtd = tds[4].text.strip()
        try:
            qtd = int(float(txt_qtd.replace('.', '').replace(',', '.')))
        except ValueError:
            continue

        # CÓDIGO – procura primeiro em <b>xxxx</b>; se não achar, regex geral
        try:
            codigo = int(tds[1].text.strip())
        except ValueError:
            m = re.search(r'(\d{3,})', ln.text)
            if not m:
                continue
            codigo = int(m.group(1))

        codigos_qtd.append((codigo, qtd))
    return codigos_qtd

# --------------------------------------------------------------------------- #
# RESERVAS – SUB-FUNÇÕES
# --------------------------------------------------------------------------- #
def ir_para_reservas(driver):
    driver.get(URL_RESERVAS)
    w(driver).until(EC.presence_of_element_located((By.ID, "codigo_produto")))

def garantir_status_pendente(driver):
    """
    Abre o multiselect de Situação e garante que só ‘Pendente’ esteja marcado.
    A interação é sempre com o <label>, nunca com o <input> escondido.
    """
    botao = driver.find_element(By.CSS_SELECTOR, 'button.multiselect')
    if botao.get_attribute("title").strip() == "Pendente":
        return                                  # já OK

    safe_click(botao)                           # abre dropdown
    time.sleep(0.3)

    def click_label(texto, marcar=True):
        lbl = driver.find_element(
            By.XPATH,
            f'//ul[@class="multiselect-container dropdown-menu"]//label'
            f'[normalize-space()="{texto}"]'
        )
        chk = lbl.find_element(By.TAG_NAME, 'input')
        if chk.is_selected() != marcar:
            safe_click(lbl)

    # desmarca Confirmado, marca Pendente
    try:
        click_label("Confirmado", marcar=False)
    except NoSuchElementException:
        pass
    click_label("Pendente", marcar=True)

    # fecha o dropdown clicando novamente no botão
    safe_click(botao)

def filtrar_codigo(driver, codigo:int):
    campo = driver.find_element(By.ID, "codigo_produto")
    campo.clear()
    campo.send_keys(str(codigo))
    safe_click(driver.find_element(By.ID, "pesquisar-reservas"))
    w(driver).until(EC.presence_of_element_located((By.ID, "tabela_reserva_produto")))
    time.sleep(0.8)

def obter_linhas_reserva(driver):
    return driver.find_elements(By.XPATH, '//table[@id="tabela_reserva_produto"]//tbody/tr[starts-with(@id,"tr_reserva_produto_")]')

def ordenar_por_previsao(linhas):
    def data_previsao(ln):
        try:
            val = ln.find_element(By.CSS_SELECTOR, 'td.campo_data_previsao_entrega').text.strip()
            return datetime.strptime(val, "%d/%m/%Y")
        except Exception:
            return datetime.max
    return sorted(linhas, key=data_previsao)

# --------------------------------------------------------------------------- #
# ENCOMENDA – CANCELA ITEM
# --------------------------------------------------------------------------- #
@log_exceptions("PROCESSAR ITEM ENCOMENDA")
def processar_item_encomenda(driver, link_encomenda: str, codigo_produto: int) -> bool:
    """
    Abre link da encomenda em nova aba, remove o vínculo (X preto) e cancela o item (X vermelho).
    Usa retries com recuperação reabrindo a mesma encomenda se algo der errado.
    """
    def _action():
        ok_local = False
        prev_handle, new_handle = open_new_tab_and_switch(driver, link_encomenda)

        try:
            # valida URL
            if "/encomendas_produtos/" not in driver.current_url:
                print(f"  • Aviso: link abriu página não-encomenda ({driver.current_url}).")
                return False

            wait = WebDriverWait(driver, WAIT)
            wait.until(EC.presence_of_element_located(
                (By.CSS_SELECTOR, 'table.table-bordered.table-hover'))
            )

            # localizar linha do produto
            def achar_linha():
                for ln in driver.find_elements(By.XPATH,
                        '//table//tbody/tr[td[contains(@class,"campo_produto")]]'):
                    if str(codigo_produto) in ln.text:
                        return ln
                return None

            linha = achar_linha()
            if not linha:
                return False

            status_txt = linha.find_element(By.CSS_SELECTOR, "td.campo_situacao").text.strip().lower()
            if status_txt in ("finalizado", "cancelado"):
                print(f"  • Item já está em status '{status_txt}'. Nada a cancelar.")
                return status_txt == "cancelado"

            linha_id = linha.get_attribute("id")

            # ------- util local -------
            def aguardar_invisibilidade_loading(drv, timeout=20):
                try:
                    WebDriverWait(drv, timeout).until(
                        EC.invisibility_of_element_located((By.ID, "mascara_carregando"))
                    )
                except TimeoutException:
                    pass

            # X PRETO (desvincular) — best-effort
            try:
                x_preto = linha.find_element(By.CSS_SELECTOR, "span.remove-vinculo-pedido-compra")
                safe_click(x_preto)
                try:
                    modal_preto = WebDriverWait(driver, 2).until(
                        EC.visibility_of_element_located((By.CSS_SELECTOR, "div.bootbox.modal.in"))
                    )
                    btn_sim = modal_preto.find_element(By.CSS_SELECTOR, 'button[data-bb-handler="confirm"]')
                    safe_click(btn_sim)
                    WebDriverWait(driver, 5).until(EC.staleness_of(modal_preto))
                    aguardar_invisibilidade_loading(driver)
                except TimeoutException:
                    pass
            except NoSuchElementException:
                pass

            # X VERMELHO (cancelar)
            xpath_vermelho = (
                f'//tr[td[contains(@class,"campo_produto") and '
                f'contains(normalize-space(.),"{codigo_produto}")]]'
                f'//span[contains(@class,"cancelar-encomenda")]'
            )

            for tentativa in range(3):
                try:
                    x_verm = WebDriverWait(driver, 8).until(
                        EC.element_to_be_clickable((By.XPATH, xpath_vermelho))
                    )
                    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", x_verm)
                    safe_click(x_verm)
                    break
                except Exception:
                    time.sleep(0.5)
            else:
                # debug opcional
                try:
                    tabela_html = driver.execute_script('return document.querySelector("div.div-table")?.outerHTML || ""')
                    print("\n##### DEBUG – HTML da tabela (parcial) #####\n")
                    print(tabela_html[:3000] + " ...")
                    print("\n##### FIM DEBUG #############################\n")
                except Exception:
                    pass
                return False

            # Modal justificativa
            modal_verm = WebDriverWait(driver, 10).until(
                EC.visibility_of_element_located((By.CSS_SELECTOR, "div.bootbox.modal.in"))
            )
            try:
                textarea = modal_verm.find_element(By.CSS_SELECTOR, "textarea.bootbox-input")
                textarea.clear()
                textarea.send_keys("Cancelado automaticamente – entrada de NF")
            except NoSuchElementException:
                pass

            btn_confirm = modal_verm.find_element(By.CSS_SELECTOR, 'button[data-bb-handler="confirm"]')
            WebDriverWait(driver, 5).until(EC.element_to_be_clickable(btn_confirm))
            safe_click(btn_confirm)

            # toast
            try:
                WebDriverWait(driver, 10).until(EC.visibility_of_element_located((By.CSS_SELECTOR, 'div.texto-alerta')))
                ok_local = True
                print("  • Encomenda cancelada com sucesso!")
            except TimeoutException:
                pass

            try:
                WebDriverWait(driver, 10).until(EC.staleness_of(modal_verm))
            except Exception:
                pass
            aguardar_invisibilidade_loading(driver)
            aguardar_status_cancelado(driver, linha_id, timeout=5)

        finally:
            # fecha com segurança e volta
            safe_close_current_window(driver, fallback_handle=prev_handle)

        return ok_local

    def _recover(_attempt):
        # nada além de reabrir a mesma encomenda em nova aba na próxima ação
        # (o _action já sempre abre de novo)
        pass

    # Tenta 3x processar a encomenda (cada falha reabrirá a aba no próximo loop)
    return with_retries(3, f"ENCOMENDA {codigo_produto}", _action, _recover)


# --------------------------------------------------------------------------- #
# BAIXA DAS RESERVAS PARA 1 CÓDIGO
# --------------------------------------------------------------------------- #
@log_exceptions("TRATAR CÓDIGO RESERVA")
def tratar_codigo_reserva(driver, codigo: int, qtd_disponivel: int, numero_nf: str, erros_whats: list) -> bool:
    def _action_filtrar():
        reset_reservas_para_codigo(driver, codigo)
        linhas = obter_linhas_reserva(driver)
        return linhas

    def _recover_filtrar(_attempt):
        reset_reservas_para_codigo(driver, codigo)

    # Garante que estamos na lista para o código — com retry
    linhas = with_retries(3, f"RESERVAS LISTA {codigo}", _action_filtrar, _recover_filtrar)
    if not linhas:
        print(f"  • Código {codigo}: sem reservas → OK")
        return True

    linhas_sorted = ordenar_por_previsao(linhas)
    baixados = 0

    for ln in linhas_sorted:
        if baixados >= qtd_disponivel:
            break

        # extrai link de encomenda
        def _pegar_link():
            anchors = ln.find_elements(By.XPATH, './/a[contains(@href,"/encomendas_produtos/")]')
            if anchors:
                return anchors[0].get_attribute("href")
            return None

        link_href = with_retries(2, f"PEGAR LINK {codigo}", _pegar_link, lambda _a: reset_reservas_para_codigo(driver, codigo))
        if not link_href:
            num_lanc = ln.find_element(By.XPATH, './/td[contains(@class,"campo_numero_lancamento")]').text.strip() if ln.find_elements(By.XPATH, './/td[contains(@class,"campo_numero_lancamento")]') else "?"
            print(f"  • Código {codigo}: linha {num_lanc} sem link de encomenda (/encomendas_produtos). Pulando.")
            erros_whats.append(f"NF {numero_nf} · Código {codigo} · Sem link de ENCOMENDA na reserva")
            continue

        # processar a encomenda com retry interno
        ok = with_retries(
            2,
            f"PROC ENCOMENDA {codigo}",
            lambda: processar_item_encomenda(driver, link_href, codigo),
            lambda _a: reset_reservas_para_codigo(driver, codigo)
        )

        if ok:
            baixados += 1
        else:
            print(f"  • Falha ao cancelar encomenda {link_href}")
            erros_whats.append(f"NF {numero_nf} · Código {codigo} · LINK DA RESERVA {link_href}")

    print(f"  • Código {codigo}: baixados {baixados}/{qtd_disponivel}")

    max_baixavel = len(linhas)
    esperado     = min(qtd_disponivel, max_baixavel)
    return baixados == esperado

def reset_reservas_para_codigo(driver, codigo:int):
    """
    Reabre a página de Reservas, garante 'Pendente' e refiltra pelo código.
    """
    ir_para_reservas(driver)
    garantir_status_pendente(driver)
    filtrar_codigo(driver, codigo)


# --------------------------------------------------------------------------- #
# DAR BAIXA EM TODOS OS PRODUTOS DA NF
# --------------------------------------------------------------------------- #
@log_exceptions("DAR BAIXA RESERVAS PRODUTOS")
def dar_baixa_reservas_produtos(driver, codigos_qtd, numero_nf:str, erros_whats:list) -> bool:
    ir_para_reservas(driver)
    garantir_status_pendente(driver)
    tudo_ok = True
    for codigo, qtd in codigos_qtd:
        ok_codigo = tratar_codigo_reserva(driver, codigo, qtd, numero_nf, erros_whats)
        tudo_ok &= ok_codigo
    return tudo_ok

# --------------------------------------------------------------------------- #
# FLUXO PRINCIPAL
# --------------------------------------------------------------------------- #
LOCK_PATH = "/app/.baixas_encomendas.lock"

def _acquire_lock():
    if os.path.exists(LOCK_PATH):
        # lock antigo? se passou de 2h, descarta
        try:
            if (time.time() - os.path.getmtime(LOCK_PATH)) > 7200:
                os.remove(LOCK_PATH)
        except Exception:
            pass
    if os.path.exists(LOCK_PATH):
        logging.info("⛔ Já existe uma execução em andamento. Encerrando.")
        return False
    with open(LOCK_PATH, "w") as f:
        f.write(str(os.getpid()))
    return True

def _release_lock():
    try:
        if os.path.exists(LOCK_PATH):
            os.remove(LOCK_PATH)
    except Exception:
        pass

def processar_nfs_pendentes():
    logging.info("🚀 processar_nfs_pendentes() — INÍCIO")
    if not _acquire_lock():
        return
    
    try:
        df = ler_tabela_processo_entrada()
        if df.empty:
            print("Planilha vazia.")
            return
        append_log_sheets("HEADERS", f"Lidos: {list(df.columns)}")

        df_pendentes = df[df.apply(pode_dar_entrada, axis=1)]
        if df_pendentes.empty:
            print("Nenhuma NF apta para processar.")
            return

        nfs_ok_para_whats = []
        erros_whats       = []

        driver = novo_driver()
        try:
            # LOGIN
            login_sgi(driver)

            for _, row in df_pendentes.iterrows():
                numero_nf = _get(row, ["numero", "nf"], default="", log_label="FALTA NUMERO NF")
                link_lancamento = str(_get(row, ["link", "lancamento", "sgi"], default="", log_label="FALTA LINK SGI")).strip()

                if not link_lancamento:
                    aviso = f"NF {numero_nf}: link de lançamento ausente."
                    print(aviso)
                    append_log_sheets("FLUXO PRINCIPAL", aviso)
                    continue

                print(f"\n➡️ NF {numero_nf} — abrindo lançamento …")
                driver.get(link_lancamento)

                # 1) Extrai os produtos / quantidades ANTES de finalizar
                codigos_qtd = extrair_codigos_qtd_entrada(driver)
                if not codigos_qtd:
                    msg = f"NF {numero_nf}: nenhum produto encontrado na tela de entrada."
                    print("  • " + msg)
                    append_log_sheets("EXTRAIR CÓDIGOS/QTD ENTRADA", msg)
                    continue
                print(f"  • Produtos recebidos: {codigos_qtd}")

                # 2) Tenta finalizar a entrada com recarga da página até 2x (total 3 tentativas)
                finalizou = tentar_finalizar_entrada_com_retries(driver, link_lancamento, str(numero_nf), tentativas=3)
                # se não finalizou, vamos direto para as baixas (já registrado no LOG pela função)

                # 3) Dar baixa nas reservas / encomendas
                baixou_ok = dar_baixa_reservas_produtos(driver, codigos_qtd, numero_nf, erros_whats)
                if baixou_ok:
                    marcar_baixa_concluida(numero_nf)
                    nfs_ok_para_whats.append(str(numero_nf))
                    print(f"✔️ NF {numero_nf} concluída (coluna I marcada).")
                else:
                    msg = f"NF {numero_nf}: concluída com pendências – coluna I NÃO marcada."
                    print(f"⚠️  {msg}")
                    append_log_sheets("DAR BAIXA RESERVAS PRODUTOS", msg)

            # ------------------------------------------------------------
            # Após processar todas as NFs, envia mensagem no WhatsApp
            # ------------------------------------------------------------
            if nfs_ok_para_whats or erros_whats:
                partes = []
                if nfs_ok_para_whats:
                    partes.append(
                        "*BAIXAS CONCLUÍDAS DAS NFs MATIC*\n" +
                        "\n".join(f"- {nf}" for nf in nfs_ok_para_whats)
                    )
                if erros_whats:
                    partes.append(
                        "*FALHAS NAS BAIXAS (verificar)*\n" +
                        "\n".join(f"- {linha}" for linha in erros_whats)
                    )
                corpo = "\n\n".join(partes)
                chrome_user_dir = r"C:\Users\Lebebe Home Office\Desktop\AUTOMATIZAÇÕES\CHROME_WPP_AUTOMATION"
                try:
                    enviar_whatsapp_texto(corpo, chrome_user_dir)
                except Exception as e:
                    # além do print, registra no Sheets
                    err = f"Erro ao enviar WhatsApp: {e}"
                    print(f"⚠️  {err}")
                    append_log_sheets("WHATSAPP", err)

        finally:
            # Limpar perfil único do Chrome
            try:
                import shutil
                prof = getattr(driver, "_lebebe_profile_dir", None)
                if prof and os.path.isdir(prof):
                    shutil.rmtree(prof, ignore_errors=True)
                driver.quit()
            except Exception:
                pass
            logging.info("✅ processar_nfs_pendentes() — FIM")


    except Exception as e:
        # Pega qualquer erro inesperado do fluxo inteiro
        tb = traceback.format_exc()
        msg = f"{e.__class__.__name__}: {e}\n\nTRACEBACK:\n{tb}"
        append_log_sheets("FLUXO PRINCIPAL", msg)
        logging.error(f"[FLUXO PRINCIPAL] {e}\n{tb}")
        # opcional: reerguer para sinalizar falha a um orquestrador
        # raise
    
    finally:
        _release_lock()

# --------------------------------------------------------------------------- #
# MAIN
# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    try:
        processar_nfs_pendentes()
    except Exception:
        logging.exception("💥 Erro fatal ao executar o script")
        # opcional: sys.exit(1)