import time
import random
import re
import json
import requests
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service
import logging
from datetime import datetime
from config import *
import os

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class CrownitAutomation:
    def __init__(self, proxy=None, headless=False):
        """
        Initialize Crownit automation with optional proxy.
        proxy: str in format "http://user:pass@ip:port"
        """
        self.proxy = proxy
        self.headless = headless
        self.driver = None
        self.wait = None
        self.logged_in = False
        
    def _get_driver(self):
        """Setup Chrome driver with options."""
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
        
        # User agent - mobile
        chrome_options.add_argument("--user-agent=Mozilla/5.0 (Linux; Android 11; SM-G998B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Mobile Safari/537.36")
        
        # Proxy setup
        if self.proxy:
            chrome_options.add_argument(f"--proxy-server={self.proxy}")
            logger.info(f"Using proxy: {self.proxy}")
        
        # Disable images for speed
        prefs = {"profile.managed_default_content_settings.images": 2}
        chrome_options.add_experimental_option("prefs", prefs)
        
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        return driver
    
    def human_type(self, element, text):
        """Type text with human-like delays."""
        for char in text:
            element.send_keys(char)
            time.sleep(random.uniform(*HUMAN_TYPING_DELAY))
    
    def human_click(self, element):
        """Click with human-like movement."""
        ActionChains(self.driver).move_to_element(element).pause(random.uniform(0.1, 0.3)).click().perform()
    
    def random_sleep(self, min_sec=1, max_sec=3):
        """Random sleep to simulate human behavior."""
        time.sleep(random.uniform(min_sec, max_sec))
    
    def create_account(self, phone):
        """
        Create a new Crownit account.
        Returns: dict with status, request_id, and message.
        """
        try:
            self.driver = self._get_driver()
            self.wait = WebDriverWait(self.driver, 15)
            
            logger.info(f"Creating account for phone: {phone}")
            
            # Step 1: Go to login page
            self.driver.get(CROWNIT_LOGIN_URL)
            self.random_sleep(2, 4)
            
            # Step 2: Find and fill phone number
            phone_input = self.wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='tel'], input[name='phone'], input[placeholder*='phone' i]"))
            )
            self.human_type(phone_input, phone)
            self.random_sleep(1, 2)
            
            # Step 3: Click continue/get OTP button
            continue_btn = self.driver.find_element(By.CSS_SELECTOR, "button[type='submit'], button:contains('Continue'), button:contains('Get OTP')")
            # Fallback: find by text
            if not continue_btn:
                buttons = self.driver.find_elements(By.TAG_NAME, "button")
                for btn in buttons:
                    if "continue" in btn.text.lower() or "otp" in btn.text.lower() or "next" in btn.text.lower():
                        continue_btn = btn
                        break
            
            if continue_btn:
                self.human_click(continue_btn)
                self.random_sleep(2, 4)
            
            # Step 4: Check if CAPTCHA appears
            captcha_element = self.driver.find_elements(By.CSS_SELECTOR, "img[src*='captcha'], .captcha, #captcha")
            if captcha_element:
                # Save CAPTCHA image and return to user
                captcha_img = captcha_element[0]
                captcha_src = captcha_img.get_attribute("src")
                if captcha_src:
                    # Download and save captcha
                    response = requests.get(captcha_src)
                    captcha_path = f"captcha_{phone}.png"
                    with open(captcha_path, "wb") as f:
                        f.write(response.content)
                    logger.info("CAPTCHA detected, saved for user")
                    return {
                        "status": "captcha_required",
                        "message": "CAPTCHA required",
                        "captcha_path": captcha_path,
                        "phone": phone
                    }
            
            # Step 5: OTP sent - wait for user to provide OTP
            # Store the request
            request_id = f"req_{int(time.time())}_{phone[-4:]}"
            
            return {
                "status": "otp_sent",
                "request_id": request_id,
                "phone": phone,
                "message": "OTP sent to your phone. Please provide the OTP."
            }
            
        except Exception as e:
            logger.error(f"Account creation error: {e}")
            return {
                "status": "error",
                "message": f"Failed to create account: {str(e)}"
            }
        finally:
            # Don't close driver here - we need it for OTP verification
            pass
    
    def verify_otp(self, phone, otp, captcha_solution=None):
        """
        Verify OTP and complete login.
        If captcha_solution is provided, solves captcha first.
        """
        try:
            if not self.driver:
                self.driver = self._get_driver()
                self.wait = WebDriverWait(self.driver, 15)
                self.driver.get(CROWNIT_LOGIN_URL)
                self.random_sleep(2, 4)
            
            # If CAPTCHA needs solving
            if captcha_solution:
                captcha_input = self.driver.find_element(By.CSS_SELECTOR, "input[name='captcha'], #captcha_input")
                if captcha_input:
                    self.human_type(captcha_input, captcha_solution)
                    self.random_sleep(1, 2)
                    
                    # Click verify/submit
                    verify_btn = self.driver.find_element(By.CSS_SELECTOR, "button[type='submit'], button:contains('Verify')")
                    if verify_btn:
                        self.human_click(verify_btn)
                        self.random_sleep(2, 4)
            
            # Enter OTP
            otp_input = self.wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='text'][maxlength='6'], input[placeholder*='OTP' i], input[name='otp']"))
            )
            self.human_type(otp_input, otp)
            self.random_sleep(1, 2)
            
            # Submit OTP
            submit_btn = self.driver.find_element(By.CSS_SELECTOR, "button[type='submit'], button:contains('Verify'), button:contains('Login')")
            if submit_btn:
                self.human_click(submit_btn)
                self.random_sleep(3, 5)
            
            # Check if login successful
            # Look for dashboard/survey elements
            dashboard = self.driver.find_elements(By.CSS_SELECTOR, ".dashboard, .survey-list, .rewards, [class*='home']")
            if dashboard:
                self.logged_in = True
                # Get cookies
                cookies = self.driver.get_cookies()
                cookie_str = "; ".join([f"{c['name']}={c['value']}" for c in cookies])
                
                return {
                    "status": "success",
                    "message": "Login successful",
                    "cookie": cookie_str,
                    "phone": phone
                }
            else:
                # Check for error
                error = self.driver.find_elements(By.CSS_SELECTOR, ".error, .alert, [class*='error']")
                if error:
                    return {
                        "status": "error",
                        "message": f"Login failed: {error[0].text}"
                    }
                return {
                    "status": "error",
                    "message": "Login failed - unknown error"
                }
                
        except Exception as e:
            logger.error(f"OTP verification error: {e}")
            return {
                "status": "error",
                "message": f"Verification failed: {str(e)}"
            }
    
    def complete_survey(self, cookie):
        """
        Complete a survey with human-like behavior.
        Returns: dict with status, reward, etc.
        """
        try:
            if not self.driver:
                self.driver = self._get_driver()
                self.wait = WebDriverWait(self.driver, 15)
            
            # Set cookies
            if cookie:
                for c in cookie.split("; "):
                    if "=" in c:
                        name, value = c.split("=", 1)
                        self.driver.add_cookie({"name": name, "value": value})
            
            # Go to survey page
            self.driver.get(CROWNIT_SURVEY_URL)
            self.random_sleep(3, 5)
            
            # Check if survey available
            survey_available = self.driver.find_elements(By.CSS_SELECTOR, ".survey-item, .available-survey, [class*='survey']")
            if not survey_available:
                return {
                    "status": "no_survey",
                    "message": "No survey available at this time"
                }
            
            # Click on first available survey
            self.human_click(survey_available[0])
            self.random_sleep(2, 4)
            
            # Survey flow - loop through questions
            question_count = 0
            max_questions = 30  # Safety limit
            
            while question_count < max_questions:
                question_count += 1
                
                # Wait for question to load
                question = self.wait.until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, ".question, [class*='question'], .survey-question"))
                )
                question_text = question.text
                logger.info(f"Question {question_count}: {question_text[:50]}...")
                
                # Find answer options
                options = self.driver.find_elements(By.CSS_SELECTOR, "input[type='radio'], input[type='checkbox'], .option, [class*='option'], button.option")
                
                if options:
                    # Select random answer (with bias toward first options for speed)
                    if len(options) > 1:
                        # Sometimes select first, sometimes random
                        if random.random() < 0.3:
                            selected = 0
                        else:
                            selected = random.randint(0, len(options) - 1)
                    else:
                        selected = 0
                    
                    # Click on the option label or the input itself
                    try:
                        option_label = self.driver.find_element(By.XPATH, f"//label[contains(@for, '{options[selected].get_attribute('id')}')]")
                        self.human_click(option_label)
                    except:
                        self.human_click(options[selected])
                    
                    self.random_sleep(0.5, 1.5)
                else:
                    # Text input question
                    text_input = self.driver.find_elements(By.CSS_SELECTOR, "input[type='text'], textarea")
                    if text_input:
                        # Generate a realistic answer
                        answers = [
                            "I think it's good", 
                            "Works well for me", 
                            "Satisfied with the experience",
                            "Pretty good overall",
                            "Could be better but okay",
                            "Happy with the service",
                            "Would recommend to others"
                        ]
                        self.human_type(text_input[0], random.choice(answers))
                        self.random_sleep(1, 2)
                
                # Click next/continue button
                next_btn = self.driver.find_elements(By.CSS_SELECTOR, "button:contains('Next'), button:contains('Continue'), .next-btn, [class*='next']")
                if next_btn:
                    self.human_click(next_btn[0])
                    self.random_sleep(2, 4)
                else:
                    # Try to find submit button
                    submit_btn = self.driver.find_elements(By.CSS_SELECTOR, "button[type='submit'], button:contains('Submit'), button:contains('Finish')")
                    if submit_btn:
                        self.human_click(submit_btn[0])
                        self.random_sleep(3, 5)
                        # Check if survey completed
                        completion_msg = self.driver.find_elements(By.CSS_SELECTOR, ".complete, .thank-you, [class*='complete'], [class*='thank']")
                        if completion_msg:
                            break
                    else:
                        # No next button - might be last question
                        break
                
                # Random pause between questions
                self.random_sleep(1, 3)
            
            # Survey complete - get reward
            reward_element = self.driver.find_elements(By.CSS_SELECTOR, ".reward, [class*='reward'], .points-earned")
            reward = 0
            if reward_element:
                reward_text = reward_element[0].text
                reward_match = re.search(r'(\d+)', reward_text)
                if reward_match:
                    reward = int(reward_match.group(1))
            
            return {
                "status": "success",
                "message": "Survey completed successfully",
                "reward": reward,
                "questions_answered": question_count
            }
            
        except TimeoutException:
            return {
                "status": "timeout",
                "message": "Survey timed out"
            }
        except Exception as e:
            logger.error(f"Survey completion error: {e}")
            return {
                "status": "error",
                "message": f"Survey failed: {str(e)}"
            }
    
    def redeem_reward(self, cookie, reward_type="amazon"):
        """
        Redeem reward from Crownit.
        reward_type: 'amazon' or 'playstore'
        """
        try:
            if not self.driver:
                self.driver = self._get_driver()
                self.wait = WebDriverWait(self.driver, 15)
            
            # Set cookies
            if cookie:
                for c in cookie.split("; "):
                    if "=" in c:
                        name, value = c.split("=", 1)
                        self.driver.add_cookie({"name": name, "value": value})
            
            # Go to rewards page
            self.driver.get(CROWNIT_REWARDS_URL)
            self.random_sleep(3, 5)
            
            # Find reward options
            rewards = self.driver.find_elements(By.CSS_SELECTOR, ".reward-item, [class*='reward'], .gift-card")
            
            # Filter by type
            target_reward = None
            for reward in rewards:
                reward_text = reward.text.lower()
                if reward_type == "amazon" and ("amazon" in reward_text or "amzn" in reward_text):
                    target_reward = reward
                    break
                elif reward_type == "playstore" and ("playstore" in reward_text or "google play" in reward_text or "play store" in reward_text):
                    target_reward = reward
                    break
            
            if not target_reward:
                # If not found, pick the first available
                target_reward = rewards[0] if rewards else None
            
            if not target_reward:
                return {
                    "status": "error",
                    "message": "No rewards available"
                }
            
            # Click on reward
            self.human_click(target_reward)
            self.random_sleep(2, 4)
            
            # Click redeem button
            redeem_btn = self.driver.find_element(By.CSS_SELECTOR, "button:contains('Redeem'), button:contains('Claim'), .redeem-btn")
            if redeem_btn:
                self.human_click(redeem_btn)
                self.random_sleep(3, 5)
            
            # Check if code or link is provided
            code_element = self.driver.find_elements(By.CSS_SELECTOR, ".code, .gift-code, [class*='code'], .reward-code")
            link_element = self.driver.find_elements(By.CSS_SELECTOR, "a[href*='redeem'], .reward-link, [class*='link']")
            
            reward_code = None
            reward_link = None
            
            if code_element:
                reward_code = code_element[0].text
            elif link_element:
                reward_link = link_element[0].get_attribute("href")
            
            return {
                "status": "success",
                "message": "Reward redeemed successfully",
                "reward_code": reward_code,
                "reward_link": reward_link,
                "reward_type": reward_type
            }
            
        except Exception as e:
            logger.error(f"Reward redemption error: {e}")
            return {
                "status": "error",
                "message": f"Reward redemption failed: {str(e)}"
            }
    
    def cleanup(self):
        """Close the driver."""
        if self.driver:
            self.driver.quit()
            self.driver = None