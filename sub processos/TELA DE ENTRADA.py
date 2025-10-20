import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import Select
import logging


# CONFIGURAÇÕES
SGI_URL = "https://smart.sgisistemas.com.br/"
USUARIO = "AUTOMACOES.lebebe"
SENHA = "automacoes"
NUMERO_NF = "263802"

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

def acessar_nf(driver, numero_nf):
    # Vai pra tela de importações
    driver.get(SGI_URL + "importacoes_xml_nfe")
    wait = WebDriverWait(driver, 20)
    # Espera tabela aparecer
    wait.until(EC.presence_of_element_located((By.TAG_NAME, "table")))
    # Busca a linha com a nota desejada (ajuste se mudar o XPATH!)
    xpath_nf = f'//tr[td[@data-title="Número NF-e"]/a[text()="{numero_nf}"]]'
    linha_nf = wait.until(EC.presence_of_element_located((By.XPATH, xpath_nf)))
    # Clica no link da nota
    link_nf = linha_nf.find_element(By.XPATH, './td[@data-title="Número NF-e"]/a')
    driver.execute_script("arguments[0].click();", link_nf)
    print(f"NF {numero_nf} aberta.")

def gerar_entrada_na_nf(driver):
    wait = WebDriverWait(driver, 20)
    # Espera o botão "Gerar Entrada" aparecer
    btn_gerar_entrada = wait.until(EC.element_to_be_clickable((By.ID, "gerar_entrada")))
    btn_gerar_entrada.click()
    print("Cliquei no botão Gerar Entrada.")

    # Tenta localizar o pop-up do CNPJ diferente, se aparecer
    try:
        btn_sim = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, 'button[data-bb-handler="confirm"]'))
        )
        btn_sim.click()
        print("Confirmei o pop-up de CNPJ diferente.")
    except Exception:
        print("Pop-up de CNPJ diferente não apareceu (normal se o CNPJ estiver certo).")

    # Espera até que a URL mude para /entrada?xml_nfe_id=...
    wait.until(lambda d: "/entrada?xml_nfe_id=" in d.current_url)
    print("Chegou na tela de Entrada!")
    # Aguarda tabela de produtos carregar
    wait.until(EC.presence_of_element_located((By.ID, "tabela_de_produtos")))

def preencher_quantidades_deposito_cd(driver):
    wait = WebDriverWait(driver, 15)
    tabela = driver.find_element(By.ID, "tabela_de_produtos")
    linhas = tabela.find_elements(By.XPATH, ".//tbody/tr")
    for idx, linha in enumerate(linhas):
        print(f"\n[ITEM {idx+1}]")
        td_qtde = linha.find_element(By.XPATH, ".//td[contains(@class,'qtde-por-local-estocagem')]")
        try:
            td_qtde.click()
        except:
            driver.execute_script("arguments[0].click();", td_qtde)

        wait.until(EC.presence_of_element_located(
            (By.XPATH, "//div[contains(@class,'modal-content')]//h4[contains(text(),'Quantidade por Local de Estocagem')]")
        ))

        tds = linha.find_elements(By.TAG_NAME, "td")
        print("Valores da linha:")
        for i, td in enumerate(tds):
            print(f"  Coluna {i}: {td.text.strip()}")

        qtd_nota = tds[4].text.strip()
        print(f"Qtde Nota coletada: [{qtd_nota}]")

        # Busca apenas o campo realmente visível e habilitado no modal
        inputs = driver.find_elements(By.XPATH, "//div[contains(@class,'modal-content')]//input[@data-local_id='6']")
        campo_cd = None
        for inp in inputs:
            if inp.is_displayed() and inp.is_enabled():
                campo_cd = inp
                break

        if campo_cd:
            campo_cd.clear()
            campo_cd.send_keys(qtd_nota)
            print(f"Digitado '{qtd_nota}' no campo Depósito C.D.")
        else:
            print("ATENÇÃO: Não achou campo visível para Depósito C.D. no pop-up.")

        try:
            btn_concluir = driver.find_element(By.ID, "concluir_quantidade_por_local")
            btn_concluir.click()
        except Exception as e:
            print(f"ERRO ao clicar em concluir: {e}")

        wait.until(EC.invisibility_of_element_located(
            (By.XPATH, "//div[contains(@class,'modal-content')]//h4[contains(text(),'Quantidade por Local de Estocagem')]")
        ))
        time.sleep(0.5)

def verificar_se_tem_desconto(driver):
    # Pega todas as linhas da tabela
    tabela = driver.find_element(By.ID, "tabela_de_produtos")
    linhas = tabela.find_elements(By.XPATH, ".//tbody/tr")
    tem_desconto = False
    for idx, linha in enumerate(linhas):
        tds = linha.find_elements(By.TAG_NAME, "td")
        desconto = tds[9].text.strip().replace('.', '').replace(',', '.')
        try:
            desconto_float = float(desconto)
        except:
            desconto_float = 0
        if desconto_float > 0:
            print(f"[ITEM {idx+1}] Tem desconto: {desconto_float}")
            tem_desconto = True
    if tem_desconto:
        print("ATENÇÃO: Essa nota é de FEIRA ou MOSTRUÁRIO (tem desconto nos itens).")
    else:
        print("Nota normal, sem desconto nos itens.")
    return tem_desconto

def preencher_outros_acrescimos(driver, tem_desconto):
    # Pega o valor dos produtos
    valor_itens_elem = driver.find_element(By.ID, "valor_itens")
    valor_itens_str = valor_itens_elem.get_attribute("value").replace('.', '').replace(',', '.')
    valor_itens = float(valor_itens_str)
    print(f"Valor dos produtos: {valor_itens}")

    # Calcula o valor para preencher nos acréscimos
    if tem_desconto:
        valor_acrescimos = valor_itens * 3
    else:
        valor_acrescimos = valor_itens
    print(f"Valor a ser colocado em Outros Acréscimos: {valor_acrescimos}")

    # Preenche o campo de outros acréscimos
    campo_acrescimos = driver.find_element(By.ID, "campo_valor_outros_acrescimos")
    campo_acrescimos.clear()
    campo_acrescimos.send_keys(f"{valor_acrescimos:.2f}".replace('.', ','))  # formato brasileiro

    print("Campo 'Outros Acréscimos' preenchido com sucesso.")

def selecionar_forma_pagamento_boleto(driver):
    wait = WebDriverWait(driver, 10)
    # Seleciona o select correto
    select_elem = wait.until(EC.presence_of_element_located((By.ID, "forma_pagamento_id_0")))
    select = Select(select_elem)
    found = False
    for option in select.options:
        if option.text.strip() == "Boleto":
            select.select_by_visible_text("Boleto")
            print("Selecionada a forma de pagamento: Boleto")
            found = True
            break
    if not found:
        raise Exception("Opção 'Boleto' não encontrada!")
    # Aguarda 1 segundo para garantir update na tela
    time.sleep(1)
def processar_todas_notas(driver):
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
        print(f"Linhas encontradas para processar: {len(linhas_nf)}")

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

                sucesso = tentar_salvar_e_continuar(driver, numero_nf, mensagens_erro)
                if not sucesso:
                    nfs_com_erro.append(numero_nf)
                    driver.get("https://smart.sgisistemas.com.br/importacoes_xml_nfe")
                    time.sleep(1)
                    break  # Volta para recarregar a lista, agora pulando essa NF

                print(f"NF {numero_nf} processada com sucesso!")
            except Exception as e:
                print(f"⚠️ Erro inesperado ao processar NF {numero_nf}: {e}")
                mensagens_erro.append(f"NF Nº {numero_nf} NAO DEU PARA DAR ENTRADA POR ERRO: \"{e}\"")
                nfs_com_erro.append(numero_nf)
                driver.get("https://smart.sgisistemas.com.br/importacoes_xml_nfe")
                time.sleep(1)
                break  # Volta para recarregar a lista

            driver.get("https://smart.sgisistemas.com.br/importacoes_xml_nfe")
            time.sleep(1)
            break  # Processa só uma por vez

        if not encontrou_nf_para_processar:
            print("Todas as NFs pendentes já foram tentadas e deram erro.")
            break

    if mensagens_erro:
        print("\n--- RESUMO DE NOTAS NÃO PROCESSADAS (para WhatsApp) ---")
        for msg in mensagens_erro:
            print(msg)


def tentar_salvar_e_continuar(driver, numero_nf, mensagens_erro):
    wait = WebDriverWait(driver, 10)
    try:
        btn_salvar = wait.until(EC.element_to_be_clickable((By.ID, "botao_salvar_continuar")))
        btn_salvar.click()
        print("Cliquei em 'Salvar e Continuar'.")
        # Aguarda até aparecer sucesso (URL com numero_lancamento) OU erro na tela
        for _ in range(20):
            time.sleep(0.7)  # até 14s total
            # Se mudou pra URL de sucesso, return True
            if "numero_lancamento=" in driver.current_url:
                print("Salvou corretamente!")
                return True
            # Se apareceu alerta, captura o texto
            alertas = driver.find_elements(By.CSS_SELECTOR, ".alert-danger, .alert.alert-danger")
            for alerta in alertas:
                if alerta.is_displayed() and alerta.text.strip():
                    mensagem = alerta.text.strip()
                    print(f"Erro ao salvar: {mensagem}")
                    mensagens_erro.append(f"NF Nº {numero_nf} NAO DEU PARA DAR ENTRADA POR ERRO: \"{mensagem}\"")
                    return False
        print("Não ficou claro se salvou. Conferir manualmente!")
        return False
    except Exception as e:
        print(f"ERRO ao tentar salvar e continuar: {e}")
        mensagens_erro.append(f"NF Nº {numero_nf} NAO DEU PARA DAR ENTRADA POR ERRO: \"{e}\"")
        return False



if __name__ == "__main__":
    options = webdriver.ChromeOptions()
    options.add_argument("--start-maximized")
    driver = webdriver.Chrome(options=options)
    try:
        login_sgi(driver, USUARIO, SENHA)
        # Pode chamar aqui a função que vincula os produtos nas NFs, se precisar.
        processar_todas_notas(driver)
        print("Processo em lote concluído!")
    finally:
        input("Pressione ENTER para fechar o navegador...")
        driver.quit()
