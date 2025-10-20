import os
import time
import glob
import logging
import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.action_chains import ActionChains
import xml.etree.ElementTree as ET

# CONFIGURAÇÕES
PASTA_XML = r"C:\Users\Lebebe Home Office\Desktop\AUTOMATIZAÇÕES\DOWLOAD NF MATIC\XML"
URL_LOGIN = "https://smart.sgisistemas.com.br/"
URL_TITULO_NEW = "https://smart.sgisistemas.com.br/titulos/new"
USUARIO = "AUTOMACOES.lebebe"
SENHA = "automacoes"

def login_sgi(driver, usuario, senha):
    driver.get(URL_LOGIN)
    wait = WebDriverWait(driver, 20)
    wait.until(EC.presence_of_element_located((By.ID, "usuario"))).send_keys(usuario)
    driver.find_element(By.NAME, "senha").send_keys(senha)
    driver.find_element(By.NAME, "senha").send_keys(Keys.RETURN)
    wait.until(EC.presence_of_element_located((By.ID, "filial_id")))
    Select(driver.find_element(By.ID, "filial_id")).select_by_visible_text("LEBEBE DEPÓSITO (CD)")
    driver.find_element(By.ID, "botao_prosseguir_informa_local_trabalho").click()
    wait.until(EC.url_to_be("https://smart.sgisistemas.com.br/home"))
    print("✅ Login realizado e filial selecionada.")

def extrair_info_xml(xml_path):
    # Extrai dados relevantes do XML da NF-e (boletos)
    tree = ET.parse(xml_path)
    root = tree.getroot()
    ns = {'nfe': 'http://www.portalfiscal.inf.br/nfe'}

    infNFe = root.find('.//nfe:infNFe', ns)
    emit = infNFe.find('nfe:emit', ns)
    fat = infNFe.find('.//nfe:fat', ns)
    dups = infNFe.findall('.//nfe:dup', ns)
    ide = infNFe.find('nfe:ide', ns)

    # Dados gerais
    numero_nf = ide.find('nfe:nNF', ns).text
    fornecedor_nome = emit.find('nfe:xNome', ns).text
    data_emissao_iso = ide.find('nfe:dhEmi', ns).text[:10]
    data_emissao = datetime.datetime.strptime(data_emissao_iso, "%Y-%m-%d").strftime("%d/%m/%Y")
    
    # Duplicatas/boletos
    duplicatas = []
    for dup in dups:
        nDup = dup.find('nfe:nDup', ns).text
        vDup = dup.find('nfe:vDup', ns).text
        dVenc_iso = dup.find('nfe:dVenc', ns).text
        dVenc = datetime.datetime.strptime(dVenc_iso, "%Y-%m-%d").strftime("%d/%m/%Y")
        duplicatas.append({"nDup": nDup, "vDup": vDup, "dVenc": dVenc})

    return {
        "numero_nf": numero_nf,
        "fornecedor_nome": fornecedor_nome,
        "data_emissao": data_emissao,
        "duplicatas": duplicatas
    }

def esperar_autocomplete(driver, campo_id, valor_digitado):
    campo = WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.ID, campo_id)))
    campo.clear()
    campo.send_keys(valor_digitado)
    time.sleep(1.5)  # Aguarda sugestões aparecerem (ajuste conforme necessário)
    campo.send_keys(Keys.ARROW_DOWN)
    time.sleep(0.5)
    campo.send_keys(Keys.ENTER)
    time.sleep(0.5)

def apagar_e_digitar(element, texto):
    # Seleciona todo o conteúdo do input e apaga antes de digitar o novo valor
    element.click()
    element.send_keys(Keys.CONTROL, 'a')
    time.sleep(0.1)
    element.send_keys(Keys.BACKSPACE)
    time.sleep(0.1)
    element.send_keys(str(texto))
    time.sleep(0.2)

def selecionar_autocomplete_exato(driver, campo_id, texto_digitado, texto_exato):
    campo = WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.ID, campo_id)))
    campo.clear()
    campo.send_keys(texto_digitado)
    time.sleep(1.5)
    # Aguarda dropdown aparecer
    sugestoes = driver.find_elements(By.CSS_SELECTOR, 'div.tt-suggestion')
    for sugestao in sugestoes:
        if sugestao.text.strip().lower() == texto_exato.strip().lower():
            sugestao.click()
            time.sleep(0.3)
            return
    raise Exception(f"Sugestão '{texto_exato}' não encontrada no autocomplete de {campo_id}.")

def preencher_parcelas(driver, duplicatas):
    tabela = WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.ID, "tabela_vencimentos_titulo"))
    )
        # Espera até que a quantidade de linhas seja suficiente
    expected_rows = len(duplicatas)
    for tentativa in range(20):  # Tenta por até 10 segundos (20 x 0.5s)
        linhas = tabela.find_elements(By.XPATH, ".//tbody/tr")
        if len(linhas) >= expected_rows:
            break
        time.sleep(0.5)
    else:
        raise Exception(f"Esperando linhas, mas só encontrou {len(linhas)}. Esperava pelo menos {expected_rows}.")

    for i, dup in enumerate(duplicatas[1:], start=1):  # começa do segundo boleto
        # Sempre recupere a linha de novo dentro do loop
        linhas = tabela.find_elements(By.XPATH, ".//tbody/tr")
        linha = linhas[i]
        
        # Vencimento
        cell_venc = linha.find_elements(By.TAG_NAME, "td")[1]
        ActionChains(driver).double_click(cell_venc).perform()
        time.sleep(0.3)
        campo_venc = cell_venc.find_element(By.XPATH, ".//input[contains(@id,'data_vencimento')]")
        apagar_e_digitar(campo_venc, dup['dVenc'])

        # Valor
        cell_valor = linha.find_elements(By.TAG_NAME, "td")[-2]
        ActionChains(driver).double_click(cell_valor).perform()
        time.sleep(0.3)
        campo_valor = cell_valor.find_element(By.XPATH, ".//input[contains(@id,'valor_nominal')]")
        apagar_e_digitar(campo_valor, dup['vDup'].replace('.', ','))

        # Complemento (opcional)
        try:
            cell_complemento = linha.find_elements(By.TAG_NAME, "td")[4]
            ActionChains(driver).double_click(cell_complemento).perform()
            time.sleep(0.2)
            campo_complemento = cell_complemento.find_element(By.XPATH, ".//input[contains(@id,'complemento')]")
            apagar_e_digitar(campo_complemento, "X")
        except Exception:
            pass



def cadastrar_titulo(driver, info):
    driver.get(URL_TITULO_NEW)
    wait = WebDriverWait(driver, 15)

    esperar_autocomplete(driver, "autocompletar_tipo_titulo_id", "Pagar")
    esperar_autocomplete(driver, "autocompletar_pessoa_cliente_fornecedor_id", "MATIC INDUSTRIA DE MÓVEIS LTDA")
    Select(driver.find_element(By.ID, "conta_financeira_id")).select_by_value("2")
    driver.find_element(By.ID, "numero_titulo").send_keys(info['numero_nf'])
    driver.find_element(By.ID, "complemento").send_keys("X")
    esperar_autocomplete(driver, "autocompletar_forma_pagamento_id", "Boleto *")
    esperar_autocomplete(driver, "autocompletar_portador_titulo_id", "Carteira")
    # ==== HISTÓRICO RECEITA/DESPESA (usa a função nova) ====
    selecionar_autocomplete_exato(driver, "autocompletar_historico_receita_despesa_id",
                                 "Pagamento de Fornecedor", "Pagamento de Fornecedor")

    campo_emissao = driver.find_element(By.ID, "data_emissao")
    campo_emissao.clear()
    campo_emissao.send_keys(info['data_emissao'])

    valor_primeira = info['duplicatas'][1]['vDup'] if len(info['duplicatas']) > 1 else info['duplicatas'][0]['vDup']
    campo_valor = driver.find_element(By.ID, "valor_cada_titulo")
    campo_valor.clear()
    campo_valor.send_keys(valor_primeira.replace('.', ','))

    campo_primeiro_venc = driver.find_element(By.ID, "primeira_data_vencimento")
    campo_primeiro_venc.clear()
    campo_primeiro_venc.send_keys(info['duplicatas'][0]['dVenc'])

    # ==== QUANTIDADE DE PARCELAS (usar função apagar_e_digitar) ====
    campo_parcelas = driver.find_element(By.ID, "quantidade_parcelas")
    apagar_e_digitar(campo_parcelas, str(len(info['duplicatas'])))
    campo_parcelas.send_keys(Keys.TAB)   # <<<<<< Adicionado: força sair do campo!
    time.sleep(1.5)

    # ==== Preencher demais parcelas na tabela ====
    if len(info['duplicatas']) > 1:
        preencher_parcelas(driver, info['duplicatas'])

    wait.until(EC.element_to_be_clickable((By.XPATH, "//input[@type='submit' and @value='Salvar']"))).click()
    print(f"✅ Título NF {info['numero_nf']} cadastrado com sucesso.")
    time.sleep(2)

def checar_erro_alerta(driver):
    try:
        alerta = driver.find_element(By.CSS_SELECTOR, ".alert-danger")
        if alerta.is_displayed():
            return alerta.text
    except Exception:
        pass
    return None


def main():
    logging.basicConfig(level=logging.INFO)
    # Setup Chrome
    options = webdriver.ChromeOptions()
    options.add_argument("--start-maximized")
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    try:
        login_sgi(driver, USUARIO, SENHA)
        time.sleep(2)

        arquivos_xml = glob.glob(os.path.join(PASTA_XML, "*.xml"))
        if not arquivos_xml:
            print("Nenhum XML encontrado na pasta.")
            return

        registros_erro = []
        for xml in arquivos_xml:
            print(f"\nProcessando arquivo: {os.path.basename(xml)}")
            info = extrair_info_xml(xml)
            tentativas = 0
            sucesso = False
            erro_msg = ""
            while tentativas < 3 and not sucesso:
                try:
                    cadastrar_titulo(driver, info)
                    # Após salvar, checa erro:
                    erro_msg = checar_erro_alerta(driver)
                    if erro_msg:
                        print(f"❌ Erro ao salvar título: {erro_msg.strip()}")
                        tentativas += 1
                        driver.refresh()
                        time.sleep(2)
                    else:
                        sucesso = True
                except Exception as e:
                    erro_msg = str(e)
                    print(f"❌ Erro inesperado: {erro_msg}")
                    tentativas += 1
                    driver.refresh()
                    time.sleep(2)
            if sucesso:
                novo_nome = xml.replace('.xml', '(FEITO).xml')
                os.rename(xml, novo_nome)
            else:
                registros_erro.append(f"NF {info['numero_nf']}: {erro_msg}")

        if registros_erro:
            print("\nAs seguintes notas falharam após 3 tentativas:")
            for msg in registros_erro:
                print(msg)

    finally:
        driver.quit()

if __name__ == "__main__":
    main()
