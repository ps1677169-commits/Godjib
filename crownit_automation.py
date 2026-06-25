import time
import random
import re
import json
import requests
import logging
import os
import glob
import shutil
import subprocess
from datetime import datetime, timedelta
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import Select

from config import *

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ==================== PROXY HELPERS ====================

def load_proxies():
    proxies = []
    if os.path.exists(PROXY_LIST_FILE):
        with open(PROXY_LIST_FILE, 'r') as f:
            proxies = [line.strip() for line in f if line.strip()]
    return proxies

def get_random_proxy():
    proxies = load_proxies()
    if proxies:
        return random.choice(proxies)
    return None

# ==================== BINARY FINDERS ====================

def find_chromium_binary():
    if os.path.exists("/usr/bin/chromium"):
        logger.info("✅ Found chromium at /usr/bin/chromium")
        return "/usr/bin/chromium"
    env_bin = os.environ.get("CHROME_BIN")
    if env_bin and os.path.exists(env_bin) and os.access(env_bin, os.X_OK):
        logger.info(f"✅ Found CHROME_BIN: {env_bin}")
        return env_bin
    for name in ["chromium", "chromium-browser", "chrome"]:
        bin_path = shutil.which(name)
        if bin_path:
            logger.info(f"✅ Found {name} at: {bin_path}")
            return bin_path
    paths = ["/usr/bin/chromium", "/usr/bin/chromium-browser", "/usr/bin/google-chrome"]
    for p in paths:
        if os.path.exists(p) and os.access(p, os.X_OK):
            logger.info(f"✅ Found binary at: {p}")
            return p
    logger.error("❌ Chromium binary not found.")
    return None

def find_chromedriver():
    if os.path.exists("/usr/bin/chromedriver"):
        logger.info("✅ Found chromedriver at /usr/bin/chromedriver")
        return "/usr/bin/chromedriver"
    env_driver = os.environ.get("CHROMEDRIVER_PATH")
    if env_driver and os.path.exists(env_driver) and os.access(env_driver, os.X_OK):
        logger.info(f"✅ Found CHROMEDRIVER_PATH: {env_driver}")
        return env_driver
    for name in ["chromedriver", "chromium-driver"]:
        driver_path = shutil.which(name)
        if driver_path:
            logger.info(f"✅ Found chromedriver at: {driver_path}")
            return driver_path
    paths = ["/usr/bin/chromedriver", "/usr/lib/chromium/chromedriver"]
    for p in paths:
        if os.path.exists(p) and os.access(p, os.X_OK):
            logger.info(f"✅ Found chromedriver at: {p}")
            return p
    logger.error("❌ Chromedriver not found.")
    return None

# ==================== RANDOM DATA GENERATORS ====================

def random_name():
    first_names = ["Aarav", "Vivaan", "Aditya", "Vihaan", "Arjun", "Sai", "Pranav", "Dhruv", "Krishna", "Shaurya",
                   "Aadhya", "Ananya", "Diya", "Ishita", "Myra", "Sara", "Aanya", "Kavya", "Riya", "Anvi"]
    last_names = ["Sharma", "Verma", "Patel", "Kumar", "Singh", "Reddy", "Gupta", "Joshi", "Nair", "Menon",
                  "Desai", "Shah", "Pillai", "Iyer", "Rao", "Das", "Bose", "Chatterjee", "Mukherjee", "Banerjee"]
    return random.choice(first_names) + " " + random.choice(last_names)

def random_dob_18_plus():
    today = datetime.now()
    min_age = 18
    max_age = 55
    age = random.randint(min_age, max_age)
    dob = today - timedelta(days=age*365 + random.randint(0, 365))
    return dob.strftime("%Y-%m-%d")

def random_gender():
    return random.choice(["Male", "Female", "Other"])

def random_city():
    cities = ["Mumbai", "Delhi", "Bangalore", "Hyderabad", "Ahmedabad", "Chennai", "Kolkata", "Surat", "Pune", "Jaipur",
              "Lucknow", "Kanpur", "Nagpur", "Indore", "Thane", "Bhopal", "Visakhapatnam", "Pimpri-Chinchwad", "Patna",
              "Vadodara", "Ghaziabad", "Ludhiana", "Agra", "Nashik", "Faridabad", "Meerut", "Rajkot", "Kalyan-Dombivli",
              "Vasai-Virar", "Varanasi", "Srinagar", "Aurangabad", "Dhanbad", "Amritsar", "Navi Mumbai", "Allahabad",
              "Howrah", "Ranchi", "Gwalior", "Jabalpur", "Coimbatore", "Vijayawada", "Jodhpur", "Madurai", "Raipur",
              "Kota", "Chandigarh", "Guwahati", "Solapur", "Hubballi-Dharwad"]
    return random.choice(cities)

# ==================== MAIN AUTOMATION CLASS ====================

class CrownitAutomation:
    def __init__(self, proxy=None, headless=True, user_callback=None):
        self.proxy = proxy
        self.headless = headless
        self.driver = None
        self.wait = None
        self.logged_in = False
        self.user_callback = user_callback
        self.pending_questions = {}
        self.cookie = None

    def _get_driver(self):
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
        chrome_options.add_argument("--remote-debugging-port=9222")
        chrome_options.add_argument("--disable-software-rasterizer")
        chrome_options.add_argument("--disable-extensions")

        binary = find_chromium_binary()
        if binary:
            chrome_options.binary_location = binary
        else:
            raise Exception("❌ Chromium binary not found.")

        if self.proxy:
            logger.info(f"🌐 Using proxy: {self.proxy}")
            chrome_options.add_argument(f"--proxy-server={self.proxy}")
        else:
            logger.info("🌐 No proxy used")

        prefs = {"profile.managed_default_content_settings.images": 2}
        chrome_options.add_experimental_option("prefs", prefs)

        chromedriver_path = find_chromedriver()
        if not chromedriver_path:
            raise Exception("❌ Chromedriver not found.")

        logger.info(f"🔧 Using chromedriver: {chromedriver_path}")
        service = Service(chromedriver_path)
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

    def _find_element(self, by, value, timeout=10):
        try:
            return WebDriverWait(self.driver, timeout).until(EC.presence_of_element_located((by, value)))
        except:
            return None

    def _find_elements(self, by, value, timeout=5):
        try:
            WebDriverWait(self.driver, timeout).until(EC.presence_of_element_located((by, value)))
            return self.driver.find_elements(by, value)
        except:
            return []

    def _find_phone_input(self):
        selectors = [
            "input[type='tel']",
            "input[name='phone']",
            "input[placeholder*='phone' i]",
            "input[placeholder*='mobile' i]",
            "input[placeholder*='number' i]",
            "input[id*='phone' i]",
            "input[id*='mobile' i]",
            "input[aria-label*='phone' i]",
        ]
        for sel in selectors:
            try:
                elem = self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, sel)))
                if elem and elem.is_displayed() and elem.is_enabled():
                    return elem
            except:
                continue
        xpaths = [
            "//input[@type='tel']",
            "//input[@name='phone']",
            "//input[contains(@placeholder, 'phone')]",
            "//input[contains(@placeholder, 'mobile')]",
            "//input[contains(@id, 'phone')]",
            "//input[@inputmode='numeric']",
            "//input[@autocomplete='tel']",
        ]
        for xp in xpaths:
            try:
                elem = self.wait.until(EC.presence_of_element_located((By.XPATH, xp)))
                if elem and elem.is_displayed() and elem.is_enabled():
                    return elem
            except:
                continue
        return None

    # ---------- REGISTRATION FLOW ----------
    def register_and_verify(self, phone):
        try:
            logger.info(f"📱 Starting registration for {phone}")
            self.driver = self._get_driver()
            self.wait = WebDriverWait(self.driver, 20)

            self.driver.get(CROWNIT_ONBOARDING_URL)
            self.random_sleep(3, 5)

            # Click Register
            register_btn = None
            buttons = self.driver.find_elements(By.TAG_NAME, "button")
            for btn in buttons:
                if "register" in btn.text.lower() or "sign up" in btn.text.lower():
                    register_btn = btn
                    break
            if not register_btn:
                register_btn = self._find_element(By.LINK_TEXT, "Register")
            if not register_btn:
                register_btn = self._find_element(By.XPATH, "//a[contains(text(),'Register')]")
            if not register_btn:
                register_btn = self._find_element(By.CSS_SELECTOR, "a[href*='register'], button[class*='register']")
            if not register_btn:
                raise Exception("Register button not found.")
            self.human_click(register_btn)
            self.random_sleep(2, 4)

            # Phone input
            phone_input = self._find_phone_input()
            if not phone_input:
                raise Exception("Phone input not found.")
            self.human_type(phone_input, phone)
            self.random_sleep(1, 2)

            # Name
            name_input = self._find_element(By.CSS_SELECTOR, "input[name='name'], input[placeholder*='name' i]")
            if name_input:
                self.human_type(name_input, random_name())
                self.random_sleep(1, 2)

            # DOB
            dob_input = self._find_element(By.CSS_SELECTOR, "input[name='dob'], input[placeholder*='dob' i], input[type='date']")
            if dob_input:
                self.human_type(dob_input, random_dob_18_plus())
                self.random_sleep(1, 2)

            # Gender
            gender_value = random_gender()
            gender_dropdown = self._find_element(By.CSS_SELECTOR, "select[name='gender'], select[id*='gender']")
            if gender_dropdown:
                select = Select(gender_dropdown)
                try:
                    select.select_by_visible_text(gender_value)
                except:
                    select.select_by_index(random.randint(1, 3))
                self.random_sleep(1, 2)
            else:
                gender_radios = self._find_elements(By.CSS_SELECTOR, "input[type='radio'][name*='gender']")
                if gender_radios:
                    random.choice(gender_radios).click()
                    self.random_sleep(1, 2)

            # City
            city_input = self._find_element(By.CSS_SELECTOR, "input[name='city'], input[placeholder*='city' i]")
            if city_input:
                self.human_type(city_input, random_city())
                self.random_sleep(1, 2)

            # Submit
            submit_btn = None
            buttons = self.driver.find_elements(By.TAG_NAME, "button")
            for btn in buttons:
                if "submit" in btn.text.lower() or "register" in btn.text.lower():
                    submit_btn = btn
                    break
            if not submit_btn:
                submit_btn = self._find_element(By.CSS_SELECTOR, "button[type='submit']")
            if submit_btn:
                self.human_click(submit_btn)
                self.random_sleep(3, 5)

            # Check OTP
            otp_input = self._find_element(By.CSS_SELECTOR, "input[type='text'][maxlength='6'], input[name='otp']", timeout=10)
            if otp_input:
                return {"status": "otp_sent", "request_id": f"reg_{int(time.time())}_{phone[-4:]}", "phone": phone}
            
            captcha_img = self.driver.find_elements(By.CSS_SELECTOR, "img[src*='captcha'], .captcha")
            if captcha_img:
                src = captcha_img[0].get_attribute("src")
                if src:
                    resp = requests.get(src)
                    captcha_path = f"captcha_{phone}.png"
                    with open(captcha_path, "wb") as f:
                        f.write(resp.content)
                    return {"status": "captcha_required", "captcha_path": captcha_path, "phone": phone}

            dashboard = self.driver.find_elements(By.CSS_SELECTOR, ".dashboard, .survey-list")
            if dashboard:
                cookies = self.driver.get_cookies()
                cookie_str = "; ".join([f"{c['name']}={c['value']}" for c in cookies]) if cookies else ""
                return {"status": "success", "cookie": cookie_str, "phone": phone}

            raise Exception("Registration submitted but OTP/CAPTCHA not detected.")

        except Exception as e:
            logger.error(f"❌ Registration error: {e}", exc_info=True)
            return {"status": "error", "message": str(e)}

    # ---------- VERIFY OTP ----------
    def verify_otp(self, phone, otp, captcha_solution=None):
        try:
            if not self.driver:
                self.driver = self._get_driver()
                self.wait = WebDriverWait(self.driver, 15)

            if captcha_solution:
                captcha_input = self._find_element(By.CSS_SELECTOR, "input[name='captcha'], #captcha_input")
                if captcha_input:
                    self.human_type(captcha_input, captcha_solution)
                    self.random_sleep(1, 2)
                    buttons = self.driver.find_elements(By.TAG_NAME, "button")
                    for btn in buttons:
                        if "verify" in btn.text.lower() or "submit" in btn.text.lower():
                            self.human_click(btn)
                            break
                    self.random_sleep(2, 4)

            otp_input = None
            selectors = [
                "input[type='text'][maxlength='6']",
                "input[placeholder*='OTP' i]",
                "input[name='otp']",
            ]
            for sel in selectors:
                try:
                    otp_input = self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, sel)))
                    if otp_input and otp_input.is_displayed() and otp_input.is_enabled():
                        break
                except:
                    continue
            if not otp_input:
                raise Exception("OTP input field not found.")

            self.human_type(otp_input, otp)
            self.random_sleep(1, 2)

            buttons = self.driver.find_elements(By.TAG_NAME, "button")
            submit_btn = None
            for btn in buttons:
                txt = btn.text.lower()
                if any(k in txt for k in ["verify", "login", "submit", "confirm"]):
                    submit_btn = btn
                    break
            if submit_btn:
                self.human_click(submit_btn)
                self.random_sleep(3, 5)

            dashboard = self.driver.find_elements(By.CSS_SELECTOR, ".dashboard, .survey-list, .rewards")
            if dashboard:
                self.logged_in = True
                cookies = self.driver.get_cookies()
                cookie_str = "; ".join([f"{c['name']}={c['value']}" for c in cookies]) if cookies else ""
                return {"status": "success", "cookie": cookie_str, "phone": phone}
            else:
                error = self.driver.find_elements(By.CSS_SELECTOR, ".error, .alert")
                if error:
                    return {"status": "error", "message": error[0].text}
                return {"status": "error", "message": "Login failed"}

        except Exception as e:
            logger.error(f"❌ verify_otp error: {e}", exc_info=True)
            return {"status": "error", "message": str(e)}

    # ---------- COMPLETE SURVEY (ASYNC) ----------
    async def complete_survey(self, cookie, user_id=None):
        try:
            if not self.driver:
                self.driver = self._get_driver()
                self.wait = WebDriverWait(self.driver, 15)

            if cookie and isinstance(cookie, str) and "=" in cookie:
                for c in cookie.split("; "):
                    if "=" in c:
                        name, value = c.split("=", 1)
                        self.driver.add_cookie({"name": name, "value": value})
            self.cookie = cookie

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

                question_text = question.text.strip()
                logger.info(f"📝 Question {question_count}: {question_text[:100]}...")

                # Check question type
                options = self.driver.find_elements(By.CSS_SELECTOR, "input[type='radio'], input[type='checkbox'], .option, [class*='option']")
                text_inputs = self.driver.find_elements(By.CSS_SELECTOR, "input[type='text'], textarea")
                dropdowns = self.driver.find_elements(By.CSS_SELECTOR, "select")

                if options:
                    selected = random.randint(0, len(options)-1) if len(options)>1 else 0
                    try:
                        label = self.driver.find_element(By.XPATH, f"//label[contains(@for, '{options[selected].get_attribute('id')}')]")
                        self.human_click(label)
                    except:
                        self.human_click(options[selected])
                    self.random_sleep(0.5, 1.5)

                elif text_inputs:
                    answer = self._generate_text_answer(question_text)
                    if answer:
                        self.human_type(text_inputs[0], answer)
                        self.random_sleep(1, 2)
                    else:
                        # Unknown - send to user
                        if self.user_callback and user_id:
                            await self.user_callback(
                                user_id,
                                f"❓ **Unknown Survey Question**\n\n"
                                f"📝 **Question:** {question_text}\n\n"
                                f"Please reply with your answer."
                            )
                            self.pending_questions[user_id] = {
                                "question": question_text,
                                "element": text_inputs[0],
                                "timestamp": time.time()
                            }
                            return {
                                "status": "pending_user_input",
                                "message": "Question sent to user",
                                "question": question_text,
                                "question_count": question_count
                            }
                        else:
                            # No callback – skip with generic answer
                            self.human_type(text_inputs[0], "N/A")
                            self.random_sleep(1, 2)

                elif dropdowns:
                    select = Select(dropdowns[0])
                    options_count = len(select.options)
                    if options_count > 1:
                        select.select_by_index(random.randint(1, options_count-1))
                    self.random_sleep(0.5, 1.5)

                else:
                    # Unknown type
                    if self.user_callback and user_id:
                        await self.user_callback(
                            user_id,
                            f"❓ **Unknown Question Type**\n\n"
                            f"📝 **Question:** {question_text}\n\n"
                            f"Please check manually."
                        )
                        return {
                            "status": "pending_user_input",
                            "message": "Unknown question type",
                            "question": question_text,
                            "question_count": question_count
                        }

                # Next / Submit
                buttons = self.driver.find_elements(By.TAG_NAME, "button")
                found = False
                for btn in buttons:
                    txt = btn.text.lower()
                    if "next" in txt or "continue" in txt:
                        self.human_click(btn)
                        found = True
                        break
                if not found:
                    for btn in buttons:
                        if "submit" in btn.text.lower() or "finish" in btn.text.lower():
                            self.human_click(btn)
                            found = True
                            break
                if not found:
                    sub = self.driver.find_elements(By.CSS_SELECTOR, "button[type='submit']")
                    if sub:
                        self.human_click(sub[0])
                        found = True
                if found:
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

    def _generate_text_answer(self, question_text):
        q = question_text.lower()
        if any(w in q for w in ["name", "your name"]):
            return random_name()
        if any(w in q for w in ["city", "location"]):
            return random_city()
        if any(w in q for w in ["email", "e-mail"]):
            return f"user{random.randint(1000,9999)}@gmail.com"
        if any(w in q for w in ["age", "old"]):
            return str(random.randint(18, 55))
        if any(w in q for w in ["gender"]):
            return random_gender()
        if any(w in q for w in ["feedback", "comment", "opinion"]):
            return random.choice(["Good", "Satisfied", "Okay", "Works well", "Happy"])
        if any(w in q for w in ["income", "salary", "earn"]):
            return random.choice(["25,000-50,000", "50,000-1,00,000", "1,00,000+"])
        if any(w in q for w in ["education", "study", "school"]):
            return random.choice(["Graduate", "Post Graduate", "Professional"])
        return None

    # ---------- CONTINUE SURVEY (ASYNC) ----------
    async def continue_survey_with_answer(self, user_id, answer):
        if user_id not in self.pending_questions:
            return {"status": "error", "message": "No pending question"}

        pending = self.pending_questions.pop(user_id)
        element = pending.get("element")
        if element:
            self.human_type(element, answer)
            self.random_sleep(1, 2)
            return await self.complete_survey(self.cookie, user_id)
        return {"status": "error", "message": "Element not found"}

    # ---------- REDEEM REWARD ----------
    def redeem_reward(self, cookie, reward_type="amazon"):
        try:
            if not self.driver:
                self.driver = self._get_driver()
                self.wait = WebDriverWait(self.driver, 15)

            if cookie and isinstance(cookie, str) and "=" in cookie:
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

            buttons = self.driver.find_elements(By.TAG_NAME, "button")
            redeem_btn = None
            for btn in buttons:
                if "redeem" in btn.text.lower() or "claim" in btn.text.lower():
                    redeem_btn = btn
                    break
            if redeem_btn:
                self.human_click(redeem_btn)
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
