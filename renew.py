import os
import random
from getpass import getpass
from sys import argv
from time import sleep

import pyotp
import requests
from deep_translator import GoogleTranslator
from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.firefox_profile import FirefoxProfile
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.support import expected_conditions
from selenium.webdriver.support.ui import WebDriverWait


# THAY ĐỔI: Logic get_hosts được viết lại để phù hợp với HTML mới
def get_hosts():
    """Lấy danh sách các thẻ div, mỗi div đại diện cho một host."""
    return browser.find_elements(by=By.CLASS_NAME, value="zone-record")


def translate(text):
    if str(os.getenv("TRANSLATE_ENABLED", True)).lower() == "true":
        return GoogleTranslator(source="auto", target="en").translate(text=text)
    return text


def get_user_agent():
    try:
        r = requests.get(url="https://jnrbsn.github.io/user-agents/user-agents.json")
        r.close()
        if r.status_code == 200 and len(list(r.json())) > 0:
            agents = r.json()
            return list(agents).pop(random.randint(0, len(agents) - 1))
    except Exception:
        pass
    return "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/102.0.5005.63 Safari/537.36"


def exit_with_error(message):
    print(str(message))
    browser.quit()
    exit(1)


def get_credentials():
    email = os.getenv("NO_IP_USERNAME", "")
    password = os.getenv("NO_IP_PASSWORD", "")

    if len(email) == 0 or len(password) == 0:
        if len(argv) == 3:
            email = argv[1]
            password = argv[2]
        else:
            email = str(input("Email: ")).replace("\n", "")
            password = getpass("Password: ").replace("\n", "")

    return email, password


def validate_otp(code):
    if len(code) != 6 or not code.isnumeric():
        exit_with_error("Mã OTP không hợp lệ. Phải là 6 chữ số.")
    return True


def validate_2fa(code):
    if len(code) != 16 or not code.isalnum():
        exit_with_error("Khóa 2FA không hợp lệ. Phải là 16 ký tự chữ và số.")
    return True


if __name__ == "__main__":
    LOGIN_URL = "https://www.noip.com/login?ref_url=console"
    HOST_URL = "https://my.noip.com/dns/records"
    LOGOUT_URL = "https://my.noip.com/logout"

    email, password = get_credentials()

    # Set up browser
    profile = FirefoxProfile()
    profile.set_preference("general.useragent.override", get_user_agent())
    browser_options = webdriver.FirefoxOptions()
    browser_options.add_argument("--headless")
    # THÊM TÙY CHỌN: Đặt kích thước cửa sổ để tránh lỗi phần tử không hiển thị
    browser_options.add_argument("--width=1920")
    browser_options.add_argument("--height=1080")
    browser_options.profile = profile
    service = Service(executable_path="/usr/local/bin/geckodriver")
    browser = webdriver.Firefox(options=browser_options, service=service)

    try:
        print(f'Using user agent "{browser.execute_script("return navigator.userAgent;")}"')
        print("Opening browser")

        # Go to login page
        browser.get(LOGIN_URL)

        if "login" in browser.current_url:
            # Find and fill login form
            username_input = WebDriverWait(browser, 20).until(
                expected_conditions.visibility_of_element_located((By.ID, "username"))
            )
            password_input = browser.find_element(by=By.ID, value="password")
            login_button = browser.find_element(By.ID, "clogs-captcha-button")
            
            username_input.send_keys(email)
            password_input.send_keys(password)
            login_button.click()
            
            WebDriverWait(browser, 60).until(
                expected_conditions.any_of(
                    expected_conditions.url_contains("my.noip.com"),
                    expected_conditions.url_contains("2fa")
                )
            )

            # Check if login has 2FA enabled and handle it
            if "2fa" in browser.current_url:
                print("2FA required...")
                WebDriverWait(driver=browser, timeout=60).until(
                    expected_conditions.element_to_be_clickable((By.NAME, "submit"))
                )
                
                try:
                    # Account has email verification code
                    code_form = browser.find_element(by=By.ID, value="otp-input")
                    otp_code = str(input("Enter OTP code: ")).replace("\n", "")
                    if validate_otp(otp_code):
                        code_inputs = code_form.find_elements(by=By.TAG_NAME, value="input")
                        for i in range(len(code_inputs)):
                            code_inputs[i].send_keys(otp_code[i])
                except NoSuchElementException:
                    # Account has 2FA code
                    code_form = browser.find_element(by=By.ID, value="challenge_code")
                    totp_secret = os.getenv("NO_IP_TOTP_KEY", "")
                    if len(totp_secret) == 0:
                        totp_secret = str(input("Enter 2FA key: ")).replace("\n", "")
                    if validate_2fa(totp_secret):
                        totp = pyotp.TOTP(totp_secret)
                        code = totp.now()
                        # THAY ĐỔI: Sử dụng JavaScript để điền mã 2FA một cách an toàn
                        browser.execute_script("arguments[0].value = arguments[1];", code_form, code)
                
                # Click submit button
                browser.find_element(By.NAME, "submit").click()

            # Wait for account dashboard to load
            WebDriverWait(driver=browser, timeout=120).until(
                expected_conditions.visibility_of_element_located((By.ID, "content-wrapper"))
            )
            print("Login successful")

            # Go to hostnames page
            browser.get(HOST_URL)

            # Wait for the new host page to load
            WebDriverWait(driver=browser, timeout=60).until(
                expected_conditions.visibility_of_element_located((By.ID, "zone-collection-wrapper"))
            )
            
            # Confirm hosts
            hosts = get_hosts()
            print("Confirming hosts phase")
            confirmed_hosts = 0

            for host in hosts:
                hostname = host.get_attribute("data-name")
                zone = host.get_attribute("data-zone")
                current_host = f"{hostname}.{zone}"

                print(f'Checking if host "{current_host}" needs confirmation')
                try:
                    button = host.find_element(By.XPATH, ".//*[self::a or self::button][contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'confirm')]")
                    
                    if "confirm" in button.text.lower() or "confirm" in translate(button.text).lower():
                        print(f'--> Found confirm button for "{current_host}". Clicking...')
                        browser.execute_script("arguments[0].click();", button)
                        confirmed_hosts += 1
                        print(f'--> Host "{current_host}" confirmed')
                        sleep(3)
                except NoSuchElementException:
                    continue
            
            if confirmed_hosts == 1:
                print("1 host confirmed")
            else:
                print(f"{confirmed_hosts} hosts confirmed")
            
            print("Finished")
    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        print("Logging off and quitting browser...\n\n")
        if 'browser' in locals() and browser.service.is_connectable():
            browser.quit()
