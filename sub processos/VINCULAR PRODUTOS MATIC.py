from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
import time
import re

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
    print("✅ Login realizado e filial selecionada.")

def codigos_equivalentes(ref, codigo_final):
    if ref == codigo_final:
        return True
    # Zera à esquerda, caso de 1 ou 2 zeros só
    if ref.lstrip('0') == codigo_final.lstrip('0') and 0 < len(ref) - len(ref.lstrip('0')) <= 2:
        return True
    if codigo_final.lstrip('0') == ref.lstrip('0') and 0 < len(codigo_final) - len(codigo_final.lstrip('0')) <= 2:
        return True
    return False


def esperar_vinculo(linha):
    # Espera o botão de check aparecer no lugar da caneta, timeout rápido!
    try:
        WebDriverWait(linha, 3).until(
            EC.presence_of_element_located(
                (By.XPATH, './/span[contains(@class,"vincular-desvincular-glyphicon-check")]')
            )
        )
    except:
        pass  # Se for rápido, não espera

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
                print(f"✅ Vinculando item {ref}")
                esperar_vinculo(linha)
            except Exception as e:
                print(f"❌ Erro ao tentar vincular item {ref}: {e}")
        else:
            print(f"⏩ Item {ref} não precisa de vínculo automático.")

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
            print("✅ Não há NFs MATIC pendentes para vincular.")
            break
        print(f"🔍 Encontradas {len(linhas_nf)} NFs MATIC para vincular.")
        linha_nf = linhas_nf[0]
        numero_nf = linha_nf.find_element(By.XPATH, './td[@data-title="Número NF-e"]/a').text.strip()
        print(f"➡️ Processando NF {numero_nf}")
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
            print("❌ Tabela de produtos não carregou! Tentando próximo...")
        vincular_produtos(driver)
        driver.get("https://smart.sgisistemas.com.br/importacoes_xml_nfe")
        time.sleep(2)

if __name__ == "__main__":
    options = webdriver.ChromeOptions()
    options.add_argument("--start-maximized")
    driver = webdriver.Chrome(options=options)
    try:
        login_sgi(driver, "AUTOMACOES.lebebe", "automacoes")
        processar_todas_nfs(driver)
        print("🚀 Processo de vinculação de produtos concluído!")
    finally:
        driver.quit()
