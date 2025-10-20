from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
import time

def testar_whatsapp_mensagem():
    chrome_user_dir = r"C:\Users\Lebebe Home Office\Desktop\AUTOMATIZAÇÕES\CHROME_WPP_AUTOMATION"  # troque o caminho se preferir

    options = webdriver.ChromeOptions()
    options.add_argument(f"--user-data-dir={chrome_user_dir}")
    options.add_argument("--start-maximized")
    driver = webdriver.Chrome(options=options)

    try:
        driver.get("https://web.whatsapp.com/")
        print("Aguardando WhatsApp Web carregar (escaneie o QR code se necessário)...")
        time.sleep(10)  # Aumente esse tempo se o WhatsApp demorar pra carregar

        # Busca o grupo pelo nome
        # Tenta encontrar o campo de pesquisa global pelo atributo [role="textbox"]
        caixa_pesquisa = WebDriverWait(driver, 30).until(
            lambda d: d.find_element(By.XPATH, '//div[@role="textbox" and @contenteditable="true"]')
        )
        caixa_pesquisa.click()
        time.sleep(1)
        caixa_pesquisa.send_keys("AVISOS/GRUPO - POS VENDA")
        time.sleep(2)
        caixa_pesquisa.send_keys(Keys.ENTER)
        time.sleep(2)

        # Envia mensagem
        # Alternativa mais robusta para localizar o campo de mensagem
        caixa_msg = driver.find_element(By.XPATH, '//footer//div[contains(@contenteditable,"true")]')
        caixa_msg.click()
        caixa_msg.send_keys("Teste")
        caixa_msg.send_keys(Keys.ENTER)
        print("Mensagem de teste enviada com sucesso!")
        time.sleep(2)
    except Exception as e:
        print(f"Erro no envio: {e}")
        driver.save_screenshot("erro_whatsapp.png")
    finally:
         driver.quit()

if __name__ == "__main__":
    testar_whatsapp_mensagem()
