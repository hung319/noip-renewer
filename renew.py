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

# THAY ĐỔI: Sử dụng class name thay vì table/tbody/tr
def get_hosts():
    """Lấy tất cả các phần tử div chứa thông tin của từng host."""
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
    # THAY ĐỔI: Cập nhật URL quản lý host
    HOST_URL = "https://my.noip.com/dns/records"
    LOGOUT_URL = "https://my.noip.com/logout"

    email, password = get_credentials()

    # Set up browser
    profile = FirefoxProfile()
    profile.set_preference("general.useragent.override", get_user_agent())
    browser_options = webdriver.FirefoxOptions()
    browser_options.add_argument("--headless")
    browser_options.profile = profile
    # Cân nhắc thay đổi đường dẫn geckodriver nếu cần
    service = Service(executable_path="/usr/local/bin/geckodriver")
    browser = webdriver.Firefox(options=browser_options, service=service)

    print(f'Sử dụng user agent: "{browser.execute_script("return navigator.userAgent;")}"')
    print("Mở trình duyệt...")
    browser.get(LOGIN_URL)

    if "login" in browser.current_url:
        try:
            username_input = WebDriverWait(browser, 20).until(
                expected_conditions.visibility_of_element_located((By.ID, "username"))
            )
            password_input = browser.find_element(by=By.ID, value="password")
            login_button = browser.find_element(By.ID, "clogs-captcha-button")

            username_input.send_keys(email)
            password_input.send_keys(password)
            login_button.click()
            print("Đã gửi thông tin đăng nhập.")
        except TimeoutException:
            exit_with_error("Không tìm thấy form đăng nhập. Trang web có thể đã thay đổi.")

        # Chờ chuyển trang sau khi login
        sleep(5)

        # Xử lý 2FA
        if "2fa" in browser.current_url:
            print("Phát hiện trang xác thực 2 yếu tố (2FA).")
            try:
                # Chờ một trong hai loại form 2FA xuất hiện
                WebDriverWait(browser, 20).until(
                    expected_conditions.any_of(
                        expected_conditions.visibility_of_element_located((By.ID, "otp-input")),
                        expected_conditions.visibility_of_element_located((By.ID, "challenge_code"))
                    )
                )

                # Kiểm tra xem là 2FA qua email hay app
                try:
                    code_form = browser.find_element(by=By.ID, value="otp-input")
                    # Email OTP
                    otp_code = input("Nhập mã OTP 6 số từ email: ")
                    if validate_otp(otp_code):
                        code_inputs = code_form.find_elements(by=By.TAG_NAME, value="input")
                        for i, char in enumerate(otp_code):
                            code_inputs[i].send_keys(char)

                except NoSuchElementException:
                    # App TOTP
                    code_form = browser.find_element(by=By.ID, value="challenge_code")
                    totp_secret = os.getenv("NO_IP_TOTP_KEY", "")
                    if not totp_secret:
                        totp_secret = input("Nhập khóa 2FA (16 ký tự): ")
                    if validate_2fa(totp_secret):
                        totp = pyotp.TOTP(totp_secret)
                        ActionChains(browser).move_to_element(code_form).click().send_keys(totp.now()).perform()
                
                # Nút submit chung cho cả hai form
                browser.find_element(By.NAME, "submit").click()
                print("Đã gửi mã 2FA.")

            except TimeoutException:
                exit_with_error("Không thể tải trang 2FA hoặc không tìm thấy ô nhập mã.")

        # Chờ đến khi vào được dashboard
        try:
            WebDriverWait(browser, 60).until(
                expected_conditions.visibility_of_element_located((By.ID, "content-wrapper"))
            )
            print("Đăng nhập thành công.")
        except TimeoutException:
            exit_with_error("Đăng nhập thất bại. Kiểm tra lại thông tin hoặc tài khoản có thể bị khóa.")
        
        # Đi đến trang quản lý host
        print(f"Điều hướng đến trang quản lý host: {HOST_URL}")
        browser.get(HOST_URL)

        # THAY ĐỔI: Chờ cho container của các host được tải
        try:
            WebDriverWait(browser, 60).until(
                expected_conditions.visibility_of_element_located((By.ID, "zone-collection-wrapper"))
            )
            print("Trang quản lý host đã tải xong.")
        except TimeoutException:
            exit_with_error("Không thể tải trang quản lý host của No-IP.")
        
        # Bắt đầu xác nhận host
        try:
            hosts = get_hosts()
            if not hosts:
                print("Không tìm thấy host nào trong tài khoản.")
            else:
                print(f"Tìm thấy {len(hosts)} host. Bắt đầu kiểm tra và xác nhận...")
            
            confirmed_hosts = 0
            for host in hosts:
                # THAY ĐỔI: Lấy thông tin host từ data attributes
                hostname = host.get_attribute("data-name")
                zone = host.get_attribute("data-zone")
                full_hostname = f"{hostname}.{zone}"
                
                print(f'Kiểm tra host "{full_hostname}"...')

                try:
                    # !!! QUAN TRỌNG !!!
                    # Giao diện mới không có nút "Confirm" rõ ràng. 
                    # Bạn cần kiểm tra một host sắp hết hạn để tìm ra selector (bộ chọn) đúng.
                    # Nó có thể là một button, một thẻ <a> với text là "Confirm", "Renew", "Verify"
                    # hoặc có một class đặc biệt như "btn-warning", "text-danger".
                    #
                    # Dưới đây là một vài ví dụ bạn có thể thử thay thế:
                    # button = host.find_element(By.LINK_TEXT, "Confirm")
                    # button = host.find_element(By.CSS_SELECTOR, ".btn.btn-warning")
                    # button = host.find_element(By.XPATH, ".//a[contains(text(), 'Confirm')]")
                    
                    # Tạm thời, ta tìm kiếm bất kỳ button hoặc link nào có chữ "Confirm"
                    button = host.find_element(By.XPATH, ".//*[self::a or self::button][contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'confirm')]")
                    
                    print(f'---> Tìm thấy nút xác nhận cho host "{full_hostname}". Đang nhấp...')
                    button.click()
                    confirmed_hosts += 1
                    print(f'---> Host "{full_hostname}" đã được xác nhận.')
                    # Chờ một chút để trang xử lý, tránh lỗi
                    sleep(3)
                
                except NoSuchElementException:
                    # Không tìm thấy nút confirm, nghĩa là host này không cần xác nhận
                    print(f'Host "{full_hostname}" không cần xác nhận.')
                    continue

            print("-" * 20)
            if confirmed_hosts > 0:
                print(f"Đã xác nhận thành công {confirmed_hosts} host.")
            else:
                print("Không có host nào cần xác nhận lần này.")
            print("Hoàn tất.")

        except Exception as e:
            print(f"Đã xảy ra lỗi trong quá trình xác nhận: {e}")

    else:
        print("Không thể truy cập trang đăng nhập: " + LOGIN_URL)

    # Đăng xuất và đóng trình duyệt
    finally:
        print("Đăng xuất...")
        browser.get(LOGOUT_URL)
        sleep(2)
        browser.quit()
