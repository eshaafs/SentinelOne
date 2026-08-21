# =============================================================
# 🛡️  SentinelOne Automation Script: Disable Agent via GUI
# -------------------------------------------------------------
# Author : Esha Sajaka
# Version: 1.1
# Date   : 2025-07-25
# Desc   : Automates the process of disabling agents via
#          SentinelOne Singularity Console using Selenium.
# Target : Workstations in endpoint list (Select All)
# Retry  : Max 7 attempts if failure occurs at any step
# =============================================================

import os
import time
import logging
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import TimeoutException
from logging.handlers import TimedRotatingFileHandler

# ======== SUPPRESS LOW-LEVEL LOGGING ========
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'  # Suppress TensorFlow logs
os.environ['WDM_LOG_LEVEL'] = '0'  # Suppress WebDriver Manager logs

# ======== LOGGING SETUP WITH ROTATION ========
LOG_DIR = "logs"
LOG_FILE = os.path.join(LOG_DIR, "sentinelone.log")
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

log_handler = TimedRotatingFileHandler(
    LOG_FILE,
    when="midnight",
    interval=1,
    backupCount=12,
    encoding="utf-8",
    utc=True
)
log_handler.namer = lambda default_name: f"{os.path.splitext(default_name)[0]}_{time.strftime('%Y-%m')}.log"
formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] - %(message)s", "%Y-%m-%d %H:%M:%S")
log_handler.setFormatter(formatter)
log = logging.getLogger("sentinelone_logger")
log.setLevel(logging.INFO)
log.addHandler(log_handler)

# ======== CONFIG ========
USERNAME = "admin@s1eppsvr.sx-dev.local"
PASSWORD = "P@ssw0rd123"
BASE_URL = "https://s1eppsvr.sx-dev.local"
LOGIN_URL = f"{BASE_URL}/login"
ENDPOINT_URL = f"{BASE_URL}/sentinels/devices/workstations?page=1&filter={{}}"

def safe_click(driver, step_desc, selector_type, selector_value):
    try:
        print(f"👉 {step_desc}...")
        element = WebDriverWait(driver, 15).until(
            EC.element_to_be_clickable((selector_type, selector_value))
        )
        driver.execute_script("arguments[0].click();", element)
        time.sleep(2)
        log.info(f"{step_desc} clicked")
    except Exception as e:
        log.error(f"❌ Failed: {step_desc}: {e}")
        driver.save_screenshot("error_step_failed.png")
        raise RuntimeError(f"Step failed: {step_desc}") from e

def run_automation():
    try:
        options = webdriver.ChromeOptions()
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-gpu")
        options.add_experimental_option("excludeSwitches", ["enable-logging"])
        service = Service(log_path=os.devnull)
        driver = webdriver.Chrome(service=service, options=options)
        driver.implicitly_wait(10)

        # ======== STEP 1: LOGIN ========
        print("🔐 Logging in to SentinelOne console...")
        log.info("Logging in to SentinelOne console")
        driver.get(LOGIN_URL)
        driver.find_element(By.CSS_SELECTOR, 'input[formcontrolname="username"]').send_keys(USERNAME)
        driver.find_element(By.CSS_SELECTOR, 'input[formcontrolname="password"]').send_keys(PASSWORD)
        driver.find_element(By.CSS_SELECTOR, 'button[data-mgmtautomationid="login-button"]').click()

        WebDriverWait(driver, 20).until(EC.url_contains("/dashboard"))
        print("✅ Login successful.")
        log.info("Login successful")

        # ======== STEP 2: GO TO ENDPOINT PAGE ========
        print("🌐 Navigating to Workstation Endpoints page...")
        driver.get(ENDPOINT_URL)

        # ======== STEP 3: WAIT FOR FULL LOAD ========
        print("⏳ Waiting 30s for full page load...")
        log.info("Waiting 30 seconds for endpoint page to fully load")
        time.sleep(30)

        # ======== STEP 4: SELECT ALL ENDPOINTS ========
        checkboxes = driver.find_elements(By.CSS_SELECTOR, 'input.mat-checkbox-input')
        if checkboxes:
            driver.execute_script("arguments[0].click();", checkboxes[0])
            log.info("✅ Checkbox 'Select All' clicked.")
        else:
            raise RuntimeError("No checkboxes found")

        # ======== STEP 5: CLICK 'ACTIONS' BUTTON ========
        safe_click(driver, "Clicking 'Actions' menu", By.CSS_SELECTOR, 'button[data-mgmtautomationid="ActionsDropdownOptionsDropdown"]')

        # ======== STEP 6: CLICK 'TROUBLESHOOTING' MENU BY TEXT ========
        print("👉 Searching for 'Troubleshooting'...")
        menu_overlay = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, 'div[id^="mat-menu-panel"]'))
        )
        menu_buttons = menu_overlay.find_elements(By.CSS_SELECTOR, "button")
        for btn in menu_buttons:
            if "troubleshooting" in btn.text.strip().lower():
                driver.execute_script("arguments[0].click();", btn)
                log.info("✅ Troubleshooting clicked")
                break
        else:
            raise RuntimeError("Troubleshooting menu not found")

        # ======== STEP 7 to 11 (DISABLE AGENT WORKFLOW) ========
        safe_click(driver, "Clicking 'Disable Agent'", By.XPATH, "//span[contains(text(),'Disable Agent')]/ancestor::button")
        safe_click(driver, "Opening duration dropdown", By.CSS_SELECTOR, 'button[data-mgmtautomationid="enableDisableHoursDropdownOptionsDropdown"]')
        safe_click(driver, "Selecting '12 Hours'", By.XPATH, "//button[@data-ux-id='12 Hours']")
        safe_click(driver, "Confirming 'Disable Agent'", By.CSS_SELECTOR, 'button[data-mgmtautomationid="enableDisableAgentEnableButton"]')
        safe_click(driver, "Clicking 'Yes' confirmation", By.CSS_SELECTOR, 'button[data-mgmtautomationid="YesButton"]')

        driver.quit()
        return True

    except Exception as e:
        log.error(f"‼️ Automation error: {e}")
        print(f"❌ {e}")
        try:
            driver.save_screenshot("error_screenshot.png")
            driver.quit()
        except:
            pass
        return False

# ======== RETRY LOOP ========
max_attempts = 7
for attempt in range(1, max_attempts + 1):
    print(f"\n🔁 Attempt {attempt}/{max_attempts}")
    log.info(f"Attempt {attempt}")
    success = run_automation()
    if success:
        print("✅ Automation succeeded.")
        log.info("Automation succeeded.")
        break
    else:
        print("🔄 Retrying...")
        log.warning(f"Attempt {attempt} failed.")

else:
    print("❌ All attempts failed.")
    log.error("All retry attempts failed.")
