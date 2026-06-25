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
    """Generate random DOB for someone 18-55 years old."""
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
        """
        user_callback: async function to send messages to user
        """
        self.proxy = proxy
        self.headless = headless
        self.driver = None
        self.wait = None
        self.logged_in = False
        self.user_callback = user_callback
        self.pending_questions = {}  # Store questions waiting for user input

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
        chrome_options.add_argument("--window-size=375,812")  # Mobile viewport
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
        """Find element with wait and return None if not found."""
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

    # ---------- REGISTRATION FLOW ----------
    def register_and_verify(self, phone):
        """
        Complete flow: Open onboarding → Register → Fill details → OTP → Login
        Returns: dict with status and cookie if successful.
        """
        try:
            logger.info(f"📱 Starting registration for {phone}")
            self.driver = self._get_driver()
            self.wait = WebDriverWait(self.driver, 20)

            # Step 1: Open onboarding page
            self.driver.get(CROWNIT_ONBOARDING_URL)
            self.random_sleep(3, 5)

            # Step 2: Click Register button
            register_btn = None
            buttons = self.driver.find_elements(By.TAG_NAME, "button")
            for btn in buttons:
                if "register" in btn.text.lower() or "sign up" in btn.text.lower():
                    register_btn = btn
                    break
            if not register_btn:
                # Try by link text
                register_btn = self._find_element(By.LINK_TEXT, "Register")
            if not register_btn:
                register_btn = self._find_element(By.PARTIAL_LINK_TEXT, "Register")
            if not register_btn:
                register_btn = self._find_element(By.XPATH, "//a[contains(text(),'Register')]")
            if not register_btn:
                # Try by CSS
                register_btn = self._find_element(By.CSS_SELECTOR, "a[href*='register'], button[class*='register']")
            if not register_btn:
                raise Exception("Register button not found on onboarding page.")

            self.human_click(register_btn)
            self.random_sleep(2, 4)

            # Step 3: Fill registration form
            # Phone input
            phone_input = self._find_phone_input()
            if not phone_input:
                raise Exception("Phone input not found on registration page.")
            self.human_type(phone_input, phone)
            self.random_sleep(1, 2)

            # Name input
            name_input = self._find_element(By.CSS_SELECTOR, "input[name='name'], input[placeholder*='name' i], input[placeholder*='full name' i]")
            if not name_input:
                name_input = self._find_element(By.XPATH, "//input[contains(@placeholder, 'Name') or contains(@placeholder, 'name')]")
            if name_input:
                self.human_type(name_input, random_name())
                self.random_sleep(1, 2)

            # DOB input
            dob_input = self._find_element(By.CSS_SELECTOR, "input[name='dob'], input[placeholder*='dob' i], input[placeholder*='birth' i], input[type='date']")
            if not dob_input:
                dob_input = self._find_element(By.XPATH, "//input[contains(@placeholder, 'DOB') or contains(@placeholder, 'Birth') or contains(@id, 'dob')]")
            if dob_input:
                dob = random_dob_18_plus()
                self.human_type(dob_input, dob)
                self.random_sleep(1, 2)

            # Gender - try dropdown or radio buttons
            gender_value = random_gender()
            gender_dropdown = self._find_element(By.CSS_SELECTOR, "select[name='gender'], select[id*='gender']")
            if gender_dropdown:
                from selenium.webdriver.support.ui import Select
                select = Select(gender_dropdown)
                try:
                    select.select_by_visible_text(gender_value)
                except:
                    select.select_by_index(random.randint(1, 3))
                self.random_sleep(1, 2)
            else:
                # Try radio buttons
                gender_radios = self._find_elements(By.CSS_SELECTOR, "input[type='radio'][name*='gender']")
                if gender_radios:
                    random.choice(gender_radios).click()
                    self.random_sleep(1, 2)

            # City input
            city_input = self._find_element(By.CSS_SELECTOR, "input[name='city'], input[placeholder*='city' i], input[placeholder*='location' i]")
            if not city_input:
                city_input = self._find_element(By.XPATH, "//input[contains(@placeholder, 'City') or contains(@placeholder, 'Location')]")
            if city_input:
                self.human_type(city_input, random_city())
                self.random_sleep(1, 2)

            # Step 4: Submit registration
            submit_btn = None
            buttons = self.driver.find_elements(By.TAG_NAME, "button")
            for btn in buttons:
                txt = btn.text.lower()
                if "submit" in txt or "register" in txt or "sign up" in txt or "create" in txt:
                    submit_btn = btn
                    break
            if not submit_btn:
                submit_btn = self._find_element(By.CSS_SELECTOR, "button[type='submit']")
            if submit_btn:
                self.human_click(submit_btn)
                self.random_sleep(3, 5)

            # Step 5: Check if OTP is sent
            # Look for OTP input or success message
            otp_input = self._find_element(By.CSS_SELECTOR, "input[type='text'][maxlength='6'], input[placeholder*='OTP' i], input[name='otp']", timeout=10)
            if otp_input:
                request_id = f"reg_{int(time.time())}_{phone[-4:]}"
                return {
                    "status": "otp_sent",
                    "request_id": request_id,
                    "phone": phone,
                    "message": "OTP sent successfully. Please enter OTP."
                }
            else:
                # Check for CAPTCHA
                captcha_img = self.driver.find_elements(By.CSS_SELECTOR, "img[src*='captcha'], .captcha, #captcha")
                if captcha_img:
                    src = captcha_img[0].get_attribute("src")
                    if src:
                        resp = requests.get(src)
                        captcha_path = f"captcha_{phone}.png"
                        with open(captcha_path, "wb") as f:
                            f.write(resp.content)
                        logger.info("🧩 CAPTCHA detected")
                        return {
                            "status": "captcha_required",
                            "message": "CAPTCHA required",
                            "captcha_path": captcha_path,
                            "phone": phone
                        }

                # Maybe already logged in?
                dashboard = self.driver.find_elements(By.CSS_SELECTOR, ".dashboard, .survey-list, .rewards, [class*='home']")
                if dashboard:
                    self.logged_in = True
                    cookies = self.driver.get_cookies()
                    cookie_str = "; ".join([f"{c['name']}={c['value']}" for c in cookies]) if cookies else ""
                    return {
                        "status": "success",
                        "message": "Already logged in",
                        "cookie": cookie_str,
                        "phone": phone
                    }

                raise Exception("Registration submitted but OTP/CAPTCHA not detected.")

        except Exception as e:
            logger.error(f"❌ Registration error: {e}", exc_info=True)
            return {"status": "error", "message": str(e)}

    # ---------- FIND PHONE INPUT ----------
    def _find_phone_input(self):
        """Find phone input using multiple strategies."""
        selectors = [
            "input[type='tel']",
            "input[name='phone']",
            "input[placeholder*='phone' i]",
            "input[placeholder*='mobile' i]",
            "input[placeholder*='number' i]",
            "input[placeholder*='Phone' i]",
            "input[placeholder*='Mobile' i]",
            "input[placeholder*='Enter phone' i]",
            "input[id*='phone' i]",
            "input[id*='mobile' i]",
            "input[aria-label*='phone' i]",
            "input[aria-label*='mobile' i]",
            "input[data-testid*='phone']",
            "input[data-testid*='mobile']",
        ]
        for sel in selectors:
            try:
                elem = self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, sel)))
                if elem and elem.is_displayed() and elem.is_enabled():
                    logger.info(f"✅ Found phone input with selector: {sel}")
                    return elem
            except:
                continue

        xpaths = [
            "//input[@type='tel']",
            "//input[@name='phone']",
            "//input[contains(@placeholder, 'phone')]",
            "//input[contains(@placeholder, 'mobile')]",
            "//input[contains(@id, 'phone')]",
            "//input[contains(@id, 'mobile')]",
            "//input[contains(@class, 'phone')]",
            "//input[contains(@class, 'mobile')]",
            "//input[@inputmode='numeric']",
            "//input[@autocomplete='tel']",
        ]
        for xp in xpaths:
            try:
                elem = self.wait.until(EC.presence_of_element_located((By.XPATH, xp)))
                if elem and elem.is_displayed() and elem.is_enabled():
                    logger.info(f"✅ Found phone input with XPath: {xp}")
                    return elem
            except:
                continue

        try:
            inputs = self.driver.find_elements(By.TAG_NAME, "input")
            for inp in inputs:
                if inp.is_displayed() and inp.is_enabled():
                    attrs = {
                        'type': inp.get_attribute('type'),
                        'name': inp.get_attribute('name'),
                        'id': inp.get_attribute('id'),
                        'placeholder': inp.get_attribute('placeholder'),
                        'class': inp.get_attribute('class'),
                        'aria-label': inp.get_attribute('aria-label'),
                        'autocomplete': inp.get_attribute('autocomplete'),
                    }
                    combined = ' '.join(str(v) for v in attrs.values() if v).lower()
                    if any(k in combined for k in ['phone', 'mobile', 'tel', 'number']):
                        logger.info(f"✅ Found phone input by scanning: {inp.get_attribute('outerHTML')}")
                        return inp
        except:
            pass
        return None

    # ---------- VERIFY OTP ----------
    def verify_otp(self, phone, otp, captcha_solution=None):
        """Verify OTP after registration or login."""
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

            # Find OTP input
            otp_input = None
            selectors = [
                "input[type='text'][maxlength='6']",
                "input[placeholder*='OTP' i]",
                "input[name='otp']",
                "input[placeholder*='verification code' i]",
                "input[id*='otp' i]",
                "input[id*='code' i]",
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

            # Check if logged in
            dashboard = self.driver.find_elements(By.CSS_SELECTOR, ".dashboard, .survey-list, .rewards, [class*='home']")
            if dashboard:
                self.logged_in = True
                cookies = self.driver.get_cookies()
                cookie_str = "; ".join([f"{c['name']}={c['value']}" for c in cookies]) if cookies else ""
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

    # ---------- COMPLETE SURVEY (with user callback) ----------
    def complete_survey(self, cookie, user_id=None):
        """
        Complete survey with human-like behavior.
        If unknown question type, sends to user via callback.
        """
        try:
            if not self.driver:
                self.driver = self._get_driver()
                self.wait = WebDriverWait(self.driver, 15)

            if cookie and isinstance(cookie, str) and "=" in cookie:
                for c in cookie.split("; "):
                    if "=" in c:
                        name, value = c.split("=", 1)
                        self.driver.add_cookie({"name": name, "value": value})
            else:
                logger.info("No valid cookie provided for survey.")

            self.driver.get(CROWNIT_SURVEY_URL)
            self.random_sleep(3, 5)

            survey_available = self.driver.find_elements(By.CSS_SELECTOR, ".survey-item, .available-survey, [class*='survey']")
            if not survey_available:
                return {"status": "no_survey", "message": "No survey available"}

            self.human_click(survey_available[0])
            self.random_sleep(2, 4)

            question_count = 0
            max_questions = 30
            survey_data = {"questions": [], "answers": []}

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
                    # Multiple choice
                    selected = random.randint(0, len(options)-1) if len(options)>1 else 0
                    try:
                        label = self.driver.find_element(By.XPATH, f"//label[contains(@for, '{options[selected].get_attribute('id')}')]")
                        self.human_click(label)
                    except:
                        self.human_click(options[selected])
                    survey_data["answers"].append({"type": "choice", "selected": selected})
                    self.random_sleep(0.5, 1.5)

                elif text_inputs:
                    # Text input - try to answer automatically, or ask user
                    answer = self._generate_text_answer(question_text)
                    if answer:
                        self.human_type(text_inputs[0], answer)
                        survey_data["answers"].append({"type": "text", "answer": answer})
                    else:
                        # Unknown - send to user
                        if self.user_callback and user_id:
                            await self.user_callback(
                                user_id,
                                f"❓ **Unknown Survey Question**\n\n"
                                f"📝 **Question:** {question_text}\n\n"
                                f"Please reply with your answer."
                            )
                            # Wait for user response (handled externally)
                            # We'll store the question and wait
                            self.pending_questions[user_id] = {
                                "question": question_text,
                                "element": text_inputs[0],
                                "timestamp": time.time()
                            }
                            # Return to caller with pending status
                            return {
                                "status": "pending_user_input",
                                "message": "Question sent to user for input",
                                "question": question_text,
                                "question_count": question_count
                            }
                    self.random_sleep(1, 2)

                elif dropdowns:
                    # Dropdown - select random option
                    from selenium.webdriver.support.ui import Select
                    select = Select(dropdowns[0])
                    options_count = len(select.options)
                    if options_count > 1:
                        select.select_by_index(random.randint(1, options_count-1))
                    survey_data["answers"].append({"type": "dropdown", "selected": random.randint(1, options_count-1)})
                    self.random_sleep(0.5, 1.5)

                else:
                    # Unknown question type
                    if self.user_callback and user_id:
                        await self.user_callback(
                            user_id,
                            f"❓ **Unknown Question Type**\n\n"
                            f"📝 **Question:** {question_text}\n\n"
                            f"Please check manually and provide guidance."
                        )
                        return {
                            "status": "pending_user_input",
                            "message": "Unknown question type, sent to user",
                            "question": question_text,
                            "question_count": question_count
                        }

                # Find next/submit button
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
                        if "submit" in txt or "finish" in txt:
                            self.human_click(btn)
                            found = True
                            break
                if not found:
                    submit_btns = self.driver.find_elements(By.CSS_SELECTOR, "button[type='submit']")
                    if submit_btns:
                        self.human_click(submit_btns[0])
                        found = True

                if found:
                    self.random_sleep(3, 5)
                    if self.driver.find_elements(By.CSS_SELECTOR, ".complete, .thank-you"):
                        break
                else:
                    break

            # Survey complete
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
                "questions_answered": question_count,
                "survey_data": survey_data
            }

        except Exception as e:
            logger.error(f"❌ complete_survey error: {e}", exc_info=True)
            return {"status": "error", "message": str(e)}

    def _generate_text_answer(self, question_text):
        """Generate a generic answer for text questions."""
        question_lower = question_text.lower()
        if any(w in question_lower for w in ["name", "your name"]):
            return random_name()
        if any(w in question_lower for w in ["city", "location", "town"]):
            return random_city()
        if any(w in question_lower for w in ["email", "e-mail"]):
            return f"user{random.randint(1000,9999)}@gmail.com"
        if any(w in question_lower for w in ["age", "old"]):
            return str(random.randint(18, 55))
        if any(w in question_lower for w in ["gender"]):
            return random_gender()
        if any(w in question_lower for w in ["feedback", "comment", "opinion"]):
            return random.choice(["Good", "Satisfied", "Okay", "Works well", "Happy"])
        if any(w in question_lower for w in ["income", "salary", "earn"]):
            return random.choice(["25,000-50,000", "50,000-1,00,000", "1,00,000+"])
        if any(w in question_lower for w in ["education", "study", "school"]):
            return random.choice(["Graduate", "Post Graduate", "Professional"])
        return None

    def continue_survey_with_answer(self, user_id, answer):
        """Continue survey after user provided an answer."""
        if user_id not in self.pending_questions:
            return {"status": "error", "message": "No pending question for this user"}

        pending = self.pending_questions.pop(user_id)
        element = pending.get("element")
        if element:
            self.human_type(element, answer)
            self.random_sleep(1, 2)
            # Continue the survey
            return self.complete_survey(self.cookie, user_id)
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
            else:
                logger.info("No valid cookie provided for redemption.")

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
