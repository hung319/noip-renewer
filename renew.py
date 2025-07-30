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


def get_hosts():
    """
    Lấy danh sách các phần tử host từ trang.
    Trong phiên bản mới của No-IP, mỗi host là một div có class 'zone-record'.
    """
    return browser.find_elements(by=By.CLASS_NAME, value="zone-record")


def translate(text):
    """Dịch văn bản nếu được bật trong biến môi trường."""
    if str(os.getenv("TRANSLATE_ENABLED", True)).lower() == "true":
        try:
            return GoogleTranslator(source="auto", target="en").translate(text=text)
        except Exception:
            return text
    return text


def get_user_agent():
    """Lấy một User Agent ngẫu nhiên để tránh bị phát hiện là bot."""
    try:
        r = requests.get(url="https://jnrbsn.github.io/user-agents/user-agents.json")
        r.raise_for_status()
        agents = r.json()
        return random.choice(agents)
    except Exception:
        return "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/102.0.5005.63 Safari/537.36"


def exit_with_error(message):
    """In thông báo lỗi và thoát script một cách an toàn."""
    print(f"ERROR: {message}")
    if 'browser' in globals():
        browser.quit()
    exit(1)


def get_credentials():
    """
    Lấy thông tin đăng nhập từ biến môi trường, tham số dòng lệnh, hoặc input của người dùng.
    """
    email = os.getenv("NO_IP_USERNAME", "")
    password = os.getenv("NO_IP_PASSWORD", "")

    if not email or not password:
        if len(argv) == 3:
            email = argv[1]
            password = argv[2]
        else:
            email = str(input("Email: ")).strip()
            password = getpass("Password: ").strip()

    if not email or not password:
        exit_with_error("Email and password cannot be empty.")

    return email, password


def validate_otp(code):
    """Kiểm tra mã OTP email."""
    if len(code) != 6 or not code.isnumeric():
        exit_with_error("Invalid email verification code. The code must have 6 digits.")
    return True


def validate_2fa(code):
    """Kiểm tra khóa 2FA."""
    if len(code) != 16 or not code.isalnum():
        exit_with_error("Invalid 2FA key. Key must have 16 alphanumeric characters.")
    return True


if __name__ == "__main__":
    LOGIN_URL = "https://www.noip.com/login?ref_url=console"
    HOST_URL = "https://my.noip.com/dynamic-dns"
    LOGOUT_URL = "https://my.noip.com/logout"

    email, password = get_credentials()

    # Thiết lập trình duyệt
    profile = FirefoxProfile()
    profile.set_preference("general.useragent.override", get_user_agent())
    browser_options = webdriver.FirefoxOptions()
    browser_options.add_argument("--headless")
    browser_options.profile = profile
    service = Service(executable_path="/usr/local/bin/geckodriver", log_output="/dev/null")
    browser = webdriver.Firefox(options=browser_options, service=service)

    try:
        print(f'Using user agent "{browser.execute_script("return navigator.userAgent;")}"')
        print("Opening browser and navigating to login page...")
        browser.get(LOGIN_URL)

        if "login" in browser.current_url:
            # Tìm và điền form đăng nhập
            try:
                username_input = WebDriverWait(browser, 10).until(
                    expected_conditions.visibility_of_element_located((By.ID, "username"))
                )
                password_input = browser.find_element(by=By.ID, value="password")
            except TimeoutException:
                exit_with_error("Username or password input not found.")

            username_input.send_keys(email)
            password_input.send_keys(password)

            # Tìm và nhấp nút đăng nhập
            try:
                login_button = WebDriverWait(browser, 10).until(
                    expected_conditions.element_to_be_clickable((By.ID, "clogs-captcha-button"))
                )
                login_button.click()
            except TimeoutException:
                exit_with_error("Login button not found.")

            # Chờ trang sau đăng nhập tải
            WebDriverWait(browser, 60).until(
                lambda d: "login" not in d.current_url or "2fa" in d.current_url
            )

            # Xử lý 2FA nếu cần
            if "2fa" in browser.current_url:
                print("2FA required. Please check your email or authenticator app.")
                
                # Chờ form 2FA tải xong
                WebDriverWait(browser, 60).until(
                    expected_conditions.element_to_be_clickable((By.NAME, "submit"))
                )

                CODE_METHOD = None
                try:
                    # Kiểm tra mã OTP email
                    code_form = browser.find_element(by=By.ID, value="otp-input")
                    CODE_METHOD = "email"
                except NoSuchElementException:
                    try:
                        # Kiểm tra mã ứng dụng
                        code_form = browser.find_element(by=By.ID, value="challenge_code")
                        CODE_METHOD = "app"
                    except NoSuchElementException:
                        exit_with_error("2FA/Email code input not found.")

                if CODE_METHOD == "email":
                    otp_code = input("Enter OTP code from email: ").strip()
                    if validate_otp(otp_code):
                        code_inputs = code_form.find_elements(by=By.TAG_NAME, value="input")
                        if len(code_inputs) == 6:
                            for i in range(len(code_inputs)):
                                code_inputs[i].send_keys(otp_code[i])
                        else:
                            exit_with_error("Email code input form is incorrect.")
                
                elif CODE_METHOD == "app":
                    totp_secret = os.getenv("NO_IP_TOTP_KEY", "")
                    if not totp_secret:
                        totp_secret = input("Enter 2FA key: ").strip()
                    if validate_2fa(totp_secret):
                        totp = pyotp.TOTP(totp_secret)
                        ActionChains(browser).move_to_element(code_form).click().send_keys(totp.now()).perform()
                
                browser.find_element(By.NAME, "submit").click()

            # Chờ trang dashboard tải xong
            WebDriverWait(browser, 120).until(
                expected_conditions.visibility_of_element_located((By.ID, "content-wrapper"))
            )
            print("Login successful.")
        
        # Đi đến trang quản lý host
        print("Navigating to Host Management page...")
        browser.get(HOST_URL)

        # Chờ trang quản lý host tải xong, tìm container mới
        try:
            WebDriverWait(browser, 60).until(
                expected_conditions.visibility_of_element_located((By.CLASS_NAME, "dns-management-container"))
            )
        except TimeoutException:
            exit_with_error("Could not load NO-IP hostnames page (dns-management-container not found).")

        # Bắt đầu xác nhận host
        print("--- Starting Host Confirmation ---")
        hosts = get_hosts()
        confirmed_hosts = 0

        if not hosts:
            print("No hosts found on the page.")
        
        for host in hosts:
            try:
                # Lấy tên host chính xác từ thuộc tính data-fqdm
                host_link = host.find_element(by=By.CLASS_NAME, value="js-copy-fqdm-link")
                current_host = host_link.get_attribute("data-fqdm")
            except NoSuchElementException:
                print("Could not find hostname for a record, skipping.")
                continue

            print(f'Checking host: "{current_host}"')
            
            # Cố gắng tìm và nhấp vào nút "Confirm"
            try:
                buttons = host.find_elements(by=By.TAG_NAME, value="button")
                for button in buttons:
                    button_text = button.text.strip()
                    if button_text.lower() == "confirm" or (translate(button_text) or "").lower() == "confirm":
                        print(f'   -> Found "Confirm" button for "{current_host}". Clicking...')
                        button.click()
                        confirmed_hosts += 1
                        sleep(0.5) # Chờ một chút để xử lý
                        break
            except NoSuchElementException:
                # Đây là trường hợp bình thường khi không có nút Confirm
                pass
        
        print("--- Host Confirmation Finished ---")
        if confirmed_hosts == 1:
            print("1 host was confirmed.")
        else:
            print(f"{confirmed_hosts} hosts were confirmed.")

    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        import traceback
        traceback.print_exc()

    finally:
        # Luôn đăng xuất và đóng trình duyệt
        if 'browser' in globals():
            print("Logging off and closing browser.")
            browser.get(LOGOUT_URL)
            sleep(2) # Chờ trang đăng xuất
            browser.quit()
