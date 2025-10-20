import os
import time
import datetime
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
from webdriver_manager.chrome import ChromeDriverManager
import pandas as pd

def automate_sgi_analysis():
    # Configurações iniciais
    options = webdriver.ChromeOptions()
    download_dir = "C:\\Users\\escritorio\\Desktop\\PYTHON\\AUTO\\TESTE"
    prefs = {"download.default_directory": download_dir}
    options.add_experimental_option("prefs", prefs)
    
    # Configurando o WebDriver
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    wait = WebDriverWait(driver, 20)

    try:
        # Login no SGI
        login(driver, wait)

        # Seleção de filial
        select_filial(driver, wait)

        # Navegar para análises de metas
        driver.get("https://smart.sgisistemas.com.br/relatorio_analises_metas")

        # Clicar no botão de pesquisa
        search_button = driver.find_element(By.CSS_SELECTOR, 'span.input-group-addon.cursor-pointer.span-elemento-pesquisa')
        search_button.click()

        # Localizar e clicar na meta de filial do mês anterior
        find_and_click_previous_month(driver, wait)

        # Clicar no botão "Gerar"
        generate_button = wait.until(EC.element_to_be_clickable((By.ID, 'gerar')))
        generate_button.click()

        # Aguardar os resultados e copiar o texto
        results = get_results(driver, wait)

        # Colar os resultados no Excel
        save_to_excel(results, "C:\\Users\\escritorio\\Desktop\\PYTHON\\AUTO\\TESTE\\Resultados.xlsx")

    finally:
        driver.quit()

def login(driver, wait):
    driver.get("https://smart.sgisistemas.com.br/")
    wait.until(EC.presence_of_element_located((By.ID, "usuario"))).send_keys("Lucas.lebebe")  # Insira o usuário correto
    wait.until(EC.presence_of_element_located((By.NAME, "senha"))).send_keys("0032456")  # Insira a senha correta
    driver.find_element(By.NAME, "senha").send_keys(Keys.RETURN)

def select_filial(driver, wait):
    wait.until(EC.presence_of_element_located((By.ID, "filial_id")))
    filial_select = driver.find_element(By.ID, "filial_id")
    filial_select.click()
    filial_select.find_element(By.XPATH, "//option[contains(text(), 'LEBEBE ECOMMERCE')]").click()
    driver.find_element(By.ID, "botao_prosseguir_informa_local_trabalho").click()
    wait.until(EC.url_to_be("https://smart.sgisistemas.com.br/home"))

def find_and_click_previous_month(driver, wait):
    previous_month_date = (datetime.datetime.now().replace(day=1) - datetime.timedelta(days=1)).replace(day=1)
    previous_month_start_date = previous_month_date.strftime("%d/%m/%Y")  # Exemplo: "01/12/2024"

    table_rows = driver.find_elements(By.CSS_SELECTOR, "table tbody tr")

    for row in table_rows:
        columns = row.find_elements(By.TAG_NAME, "td")
        if previous_month_start_date == columns[3].text.strip():  # Verificar "Data Inicial"
            hyperlink = columns[0].find_element(By.TAG_NAME, "a")
            hyperlink.click()
            print(f"Cliquei no número '{hyperlink.text}' para a meta de 'Filial' com data inicial: {previous_month_start_date}")
            break

def get_results(driver, wait):
    wait.until(EC.presence_of_element_located((By.XPATH, '//*[contains(text(), "ranking")]')))
    page_content = driver.page_source
    start = page_content.find("ranking")
    end = page_content.find("Grupos de operação")
    if start != -1 and end != -1:
        return page_content[start:end].strip()
    else:
        print("Erro ao localizar os resultados.")
        return ""

def save_to_excel(results, file_path):
    lines = results.split("\n")
    data = [line.split() for line in lines]  # Supondo que os dados estejam separados por espaços
    df = pd.DataFrame(data)
    df.to_excel(file_path, index=False, header=False)
    print(f"Resultados salvos em: {file_path}")

if __name__ == "__main__":
    automate_sgi_analysis()
