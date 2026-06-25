import time
import random
import re
import json
import requests
import logging
import os
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service

from config import *

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------- PROXY LOADER ----------
def load_proxies():
    """Load proxies from file, return list."""
    proxies = []
    if os.path.exists(PROXY_LIST_FILE):
        with open(PROXY_LIST_FILE, 'r') as f:
            proxies = [line.strip() for line in f if line.strip()]
    return proxies

def get_random_proxy():
    """Return a random proxy from the file, or None if none available."""
    proxies = load_proxies()
    if proxies:
        return random.choice(proxies)
    return None

# ---------- AUTOMATION CLASS ----------
class CrownitAutomation:
    def __init__(self, proxy=None, headless=True):
        self.proxy = proxy
        self.headless = headless
        self.driver = None
        self.wait = None
        self.logged_in = False

    def _get_driver(self):
        """Setup Chrome driver with proxy if available."""
        chrome_options = Options()
        if self.headless:
            chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option("useAutomationExtension", False)
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--window-size=375,812")
        chrome_options.add_argument("--user-agent=Mozilla/5.0 (Linux; Android 11; SM-G998B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Mobile Safari/537.36")

        # Proxy
        if self.proxy:
            logger.info(f"🌐 Using proxy: {self.proxy}")
            chrome_options.add_argument(f"--proxy-server={self.proxy}")
        else:
            logger.info("🌐 No proxy used (direct connection)")

        # Disable images for speed
        prefs = {"profile.managed_default_content_settings.images": 2}
        chrome_options.add_experimental_option("prefs", prefs)

        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        return driver

    def human_type(self, element, text):
        for char in text:
            element.send_keys(char)
            time.sleep(random.uniform(0.05, 0.2))

    def human_click(self, element):
        ActionChains(self.driver).move_to_element(element).pause(random.uniform(0.1, 0.3)).click().perform()

    def random_sleep(self, min_sec=1, max_sec=3):
        time.sleep(random.uniform(min_sec, max_sec))

    def create_account(self, phone):
        """Create a new Crownit account using OTP flow."""
        try:
            logger.info(f"📱 Creating account for {phone}")
            self.driver = self._get_driver()
            self.wait = WebDriverWait(self.driver, 15)

            # 1. Go to login page
            self.driver.get(CROWNIT_LOGIN_URL)
            self.random_sleep(2, 4)

            # 2. Find phone input
            phone_input = None
            selectors = ["input[type='tel']", "input[name='phone']", "input[placeholder*='phone' i]", "input[placeholder*='mobile' i]"]
            for sel in selectors:
                try:
                    phone_input = self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, sel)))
                    break
                except:
                    continue
            if not phone_input:
                raise Exception("Phone input field not found on page.")

            self.human_type(phone_input, phone)
            self.random_sleep(1, 2)

            # 3. Click continue/Get OTP button
            buttons = self.driver.find_elements(By.TAG_NAME, "button")
            continue_btn = None
            for btn in buttons:
                txt = btn.text.lower()
                if "continue" in txt or "otp" in txt or "next" in txt or "submit" in txt:
                    continue_btn = btn
                    break
            if not continue_btn:
                # Try by type
                continue_btn = self.driver.find_elements(By.CSS_SELECTOR, "button[type='submit']")
                if continue_btn:
                    continue_btn = continue_btn[0]
                else:
                    raise Exception("Continue/Get OTP button not found.")
            self.human_click(continue_btn)
            self.random_sleep(2, 4)

            # 4. Check for CAPTCHA
            captcha_img = self.driver.find_elements(By.CSS_SELECTOR, "img[src*='captcha'], .captcha, #captcha")
            if captcha_img:
                src = captcha_img[0].get_attribute("src")
                if src:
                    # Download captcha image
                    resp = requests.get(src)
                    captcha_path = f"captcha_{phone}.png"
                    with open(captcha_path, "wb") as f:
                        f.write(resp.content)
                    logger.info("🧩 CAPTCHA detected, saved for user")
                    return {
                        "status": "captcha_required",
                        "message": "CAPTCHA required",
                        "captcha_path": captcha_path,
                        "phone": phone
                    }

            # 5. OTP sent
            request_id = f"req_{int(time.time())}_{phone[-4:]}"
            return {
                "status": "otp_sent",
                "request_id": request_id,
                "phone": phone,
                "message": "OTP sent successfully."
            }

        except Exception as e:
            logger.error(f"❌ create_account error: {e}", exc_info=True)
            return {
                "status": "error",
                "message": str(e)
            }

    def verify_otp(self, phone, otp, captcha_solution=None):
        """Verify OTP and complete login."""
        try:
            if not self.driver:
                self.driver = self._get_driver()
                self.wait = WebDriverWait(self.driver, 15)
                self.driver.get(CROWNIT_LOGIN_URL)
                self.random_sleep(2, 4)

            # If CAPTCHA solution provided
            if captcha_solution:
                captcha_input = self.driver.find_elements(By.CSS_SELECTOR, "input[name='captcha'], #captcha_input")
                if captcha_input:
                    self.human_type(captcha_input[0], captcha_solution)
                    self.random_sleep(1, 2)
                    verify_btn = self.driver.find_elements(By.CSS_SELECTOR, "button[type='submit'], button:contains('Verify')")
                    if verify_btn:
                        self.human_click(verify_btn[0])
                        self.random_sleep(2, 4)

            # Enter OTP
            otp_input = None
            selectors = ["input[type='text'][maxlength='6']", "input[placeholder*='OTP' i]", "input[name='otp']"]
            for sel in selectors:
                try:
                    otp_input = self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, sel)))
                    break
                except:
                    continue
            if not otp_input:
                raise Exception("OTP input field not found.")

            self.human_type(otp_input, otp)
            self.random_sleep(1, 2)

            # Submit OTP
            submit_btn = self.driver.find_elements(By.CSS_SELECTOR, "button[type='submit'], button:contains('Verify'), button:contains('Login')")
            if submit_btn:
                self.human_click(submit_btn[0])
                self.random_sleep(3, 5)

            # Check login success
            dashboard = self.driver.find_elements(By.CSS_SELECTOR, ".dashboard, .survey-list, .rewards, [class*='home']")
            if dashboard:
                self.logged_in = True
                cookies = self.driver.get_cookies()
                cookie_str = "; ".join([f"{c['name']}={c['value']}" for c in cookies])
                return {
                    "status": "success",
                    "message": "Login successful",
                    "cookie": cookie_str,
                    "phone": phone
                }
            else:
                error = self.driver.find_elements(By.CSS_SELECTOR, ".error, .alert, [class*='error']")
                if error:
                    return {"status": "error", "message": error[0].text}
                return {"status": "error", "message": "Login failed - unknown reason"}

        except Exception as e:
            logger.error(f"❌ verify_otp error: {e}", exc_info=True)
            return {"status": "error", "message": str(e)}

    def complete_survey(self, cookie):
        """Complete survey using cookie."""
        try:
            if not self.driver:
                self.driver = self._get_driver()
                self.wait = WebDriverWait(self.driver, 15)

            if cookie:
                for c in cookie.split("; "):
                    if "=" in c:
                        name, value = c.split("=", 1)
                        self.driver.add_cookie({"name": name, "value": value})

            self.driver.get(CROWNIT_SURVEY_URL)
            self.random_sleep(3, 5)

            survey_available = self.driver.find_elements(By.CSS_SELECTOR, ".survey-item, .available-survey, [class*='survey']")
            if not survey_available:
                return {"status": "no_survey", "message": "No survey available"}

            self.human_click(survey_available[0])
            self.random_sleep(2, 4)

            question_count = 0
            max_questions = 30
            while question_count < max_questions:
                question_count += 1
                try:
                    question = self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, ".question, [class*='question'], .survey-question")))
                except:
                    break

                options = self.driver.find_elements(By.CSS_SELECTOR, "input[type='radio'], input[type='checkbox'], .option, [class*='option']")
                if options:
                    selected = random.randint(0, len(options)-1) if len(options)>1 else 0
                    try:
                        label = self.driver.find_element(By.XPATH, f"//label[contains(@for, '{options[selected].get_attribute('id')}')]")
                        self.human_click(label)
                    except:
                        self.human_click(options[selected])
                    self.random_sleep(0.5, 1.5)
                else:
                    text_input = self.driver.find_elements(By.CSS_SELECTOR, "input[type='text'], textarea")
                    if text_input:
                        answers = ["Good", "Satisfied", "Okay", "Works well", "Happy"]
                        self.human_type(text_input[0], random.choice(answers))
                        self.random_sleep(1, 2)

                next_btn = self.driver.find_elements(By.CSS_SELECTOR, "button:contains('Next'), button:contains('Continue'), .next-btn")
                if next_btn:
                    self.human_click(next_btn[0])
                    self.random_sleep(2, 4)
                else:
                    submit_btn = self.driver.find_elements(By.CSS_SELECTOR, "button[type='submit'], button:contains('Submit')")
                    if submit_btn:
                        self.human_click(submit_btn[0])
                        self.random_sleep(3, 5)
                        if self.driver.find_elements(By.CSS_SELECTOR, ".complete, .thank-you"):
                            break
                    else:
                        break

            reward_element = self.driver.find_elements(By.CSS_SELECTOR, ".reward, [class*='reward'], .points-earned")
            reward = 0
            if reward_element:
                match = re.search(r'(\d+)', reward_element[0].text)
                if match:
                    reward = int(match.group(1))

            return {
                "status": "success",
                "message": "Survey completed",
                "reward": reward,
                "questions_answered": question_count
            }

        except Exception as e:
            logger.error(f"❌ complete_survey error: {e}", exc_info=True)
            return {"status": "error", "message": str(e)}

    def redeem_reward(self, cookie, reward_type="amazon"):
        """Redeem reward."""
        try:
            if not self.driver:
                self.driver = self._get_driver()
                self.wait = WebDriverWait(self.driver, 15)

            if cookie:
                for c in cookie.split("; "):
                    if "=" in c:
                        name, value = c.split("=", 1)
                        self.driver.add_cookie({"name": name, "value": value})

            self.driver.get(CROWNIT_REWARDS_URL)
            self.random_sleep(3, 5)

            rewards = self.driver.find_elements(By.CSS_SELECTOR, ".reward-item, [class*='reward'], .gift-card")
            target = None
            for r in rewards:
                txt = r.text.lower()
                if reward_type == "amazon" and ("amazon" in txt or "amzn" in txt):
                    target = r
                    break
                elif reward_type == "playstore" and ("playstore" in txt or "google play" in txt):
                    target = r
                    break
            if not target and rewards:
                target = rewards[0]
            if not target:
                return {"status": "error", "message": "No rewards found"}

            self.human_click(target)
            self.random_sleep(2, 4)

            redeem_btn = self.driver.find_elements(By.CSS_SELECTOR, "button:contains('Redeem'), button:contains('Claim'), .redeem-btn")
            if redeem_btn:
                self.human_click(redeem_btn[0])
                self.random_sleep(3, 5)

            code = self.driver.find_elements(By.CSS_SELECTOR, ".code, .gift-code, [class*='code']")
            link = self.driver.find_elements(By.CSS_SELECTOR, "a[href*='redeem']")

            return {
                "status": "success",
                "message": "Reward redeemed",
                "reward_code": code[0].text if code else None,
                "reward_link": link[0].get_attribute("href") if link else None,
                "reward_type": reward_type
            }

        except Exception as e:
            logger.error(f"❌ redeem_reward error: {e}", exc_info=True)
            return {"status": "error", "message": str(e)}

    def cleanup(self):
        if self.driver:
            self.driver.quit()
            self.driver = None
