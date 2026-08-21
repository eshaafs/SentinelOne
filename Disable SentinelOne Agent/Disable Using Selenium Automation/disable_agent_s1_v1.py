# =============================================================
# 🛡️  SentinelOne Automation Script: Disable Agent via GUI
# -------------------------------------------------------------
# Author : Esha Sajaka
# Version: 1.0
# Date   : 2025-07-24
# Desc   : Automates the process of disabling agents via
#          SentinelOne Singularity Console using Selenium.
# Target : Workstations in endpoint list (Select All)
# Note   : GUI-based automation, use only on trusted environments.
# =============================================================

import os
import logging
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from logging.handlers import TimedRotatingFileHandler

# ======== SUPPRESS LOW-LEVEL LOGGING ========
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'  # Suppress TensorFlow logs
os.environ['WDM_LOG_LEVEL'] = '0'  # Suppress WebDriver Manager logs

# ======== SELENIUM LOGGING TO FILE ========
selenium_logger = logging.getLogger('selenium')
selenium_logger.setLevel(logging.WARNING)
selenium_handler = logging.FileHandler("selenium_warnings.log")
selenium_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
selenium_logger.addHandler(selenium_handler)

# ======== SCRIPT LOGGING TO FILE (With Monthly Rotation) ========
LOG_DIR = "logs"
LOG_FILE = os.path.join(LOG_DIR, "sentinelone.log")

if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

log_handler = TimedRotatingFileHandler(
    LOG_FILE,
    when="midnight",         # rotasi tiap malam
    interval=1,              # 1 hari, nanti kita custom namer-nya jadi per bulan
    backupCount=12,          # simpan maksimal 12 file log
    encoding="utf-8",
    utc=True
)

def custom_namer(default_name):
    base, ext = os.path.splitext(default_name)
    timestamp = time.strftime("%Y-%m", time.gmtime())
    return f"{base}_{timestamp}{ext}"

log_handler.namer = custom_namer

formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] - %(message)s", "%Y-%m-%d %H:%M:%S")
log_handler.setFormatter(formatter)

log = logging.getLogger("sentinelone_logger")
log.setLevel(logging.INFO)
log.addHandler(log_handler)

# ======== CONFIG SECTION ========
USERNAME = "admin@s1eppsvr.sx-dev.local"
PASSWORD = "P@ssw0rd123"  # 🔒 Replace with your own secure password
BASE_URL = "https://s1eppsvr.sx-dev.local"
LOGIN_URL = f"{BASE_URL}/login"
ENDPOINT_URL = f"{BASE_URL}/sentinels/devices/workstations?page=1&filter={{}}"

# ======== SETUP CHROME DRIVER ========
options = webdriver.ChromeOptions()
# options.add_argument("--start-maximized")
options.add_argument("--headless")
options.add_argument("--no-sandbox")
options.add_argument("--disable-gpu")
options.add_experimental_option("excludeSwitches", ["enable-logging"])
service = Service(log_path=os.devnull)  # Suppress ChromeDriver stderr

driver = webdriver.Chrome(service=service, options=options)
driver.implicitly_wait(10)

# ======== STEP 1: LOGIN ========
try:
    print("🔐 Logging in to SentinelOne console...")
    log.info("Logging in to SentinelOne console")

    driver.get(LOGIN_URL)
    driver.find_element(By.CSS_SELECTOR, 'input[formcontrolname="username"]').send_keys(USERNAME)
    driver.find_element(By.CSS_SELECTOR, 'input[formcontrolname="password"]').send_keys(PASSWORD)
    driver.find_element(By.CSS_SELECTOR, 'button[data-mgmtautomationid="login-button"]').click()

    WebDriverWait(driver, 20).until(EC.url_contains("/dashboard"))
    print("✅ Login successful.")
    log.info("Login successful")
except Exception as e:
    log.error(f"Login failed: {e}")
    raise

# ======== STEP 2: GO TO ENDPOINT PAGE ========
print("🌐 Navigating to Workstation Endpoints page...")
log.info("Navigating to endpoint page")
driver.get(ENDPOINT_URL)

# ======== STEP 3: WAIT FOR FULL LOAD ========
print("⏳ Waiting 30s for full page load (static wait)...")
log.info("Waiting 30 seconds for endpoint page to fully load")
time.sleep(30)

# ======== STEP 4: SELECT ALL ENDPOINTS ========
print("👡️  Clicking 'Select All' checkbox...")
try:
    checkboxes = driver.find_elements(By.CSS_SELECTOR, 'input.mat-checkbox-input')
    if checkboxes:
        select_all_checkbox = checkboxes[0]  # Select the first one as 'Select All'
        driver.execute_script("arguments[0].click();", select_all_checkbox)
        print("✅ Checkbox 'Select All' clicked.")
        log.info("Select All checkbox clicked")
    else:
        print("❌ No checkbox found with 'input.mat-checkbox-input'.")
        log.warning("Checkbox not found")
except Exception as e:
    print(f"❌ Failed to click Select All checkbox: {e}")
    log.error(f"Error clicking Select All checkbox: {e}")

# ======== STEP 5: CLICK 'ACTIONS' BUTTON ========
try:
    print("👉 Clicking 'Actions' menu...")
    actions_button = WebDriverWait(driver, 15).until(
        EC.element_to_be_clickable((By.CSS_SELECTOR, 'button[data-mgmtautomationid="ActionsDropdownOptionsDropdown"]'))
    )
    driver.execute_script("arguments[0].click();", actions_button)
    time.sleep(2)
    log.info("Actions menu clicked")
except Exception as e:
    print(f"❌ Failed to click Actions button: {e}")
    log.error(f"Error clicking Actions: {e}")

# ======== STEP 6: CLICK 'TROUBLESHOOTING' MENU BY TEXT ========
try:
    print("👉 Searching for 'Troubleshooting' menu...")
    menu_overlay = WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, 'div[id^="mat-menu-panel"]'))
    )
    menu_buttons = menu_overlay.find_elements(By.CSS_SELECTOR, "button")
    found = False
    for btn in menu_buttons:
        text = btn.text.strip().lower()
        if "troubleshooting" in text:
            driver.execute_script("arguments[0].click();", btn)
            print("✅ 'Troubleshooting' menu clicked.")
            log.info("Troubleshooting menu clicked")
            found = True
            break
    if not found:
        print("❌ Could not find 'Troubleshooting' menu item.")
        log.warning("Troubleshooting menu not found")
except Exception as e:
    print(f"❌ Error clicking Troubleshooting: {e}")
    log.error(f"Troubleshooting click error: {e}")

# ======== STEP 7 to 11 (DISABLE AGENT WORKFLOW) ========
def safe_click(step_desc, selector_type, selector_value):
    try:
        print(f"👉 {step_desc}...")
        element = WebDriverWait(driver, 15).until(
            EC.element_to_be_clickable((selector_type, selector_value))
        )
        driver.execute_script("arguments[0].click();", element)
        time.sleep(2)
        log.info(f"{step_desc} clicked")
    except Exception as e:
        print(f"❌ Failed: {step_desc}: {e}")
        log.error(f"Error at {step_desc}: {e}")

safe_click("Clicking 'Disable Agent'", By.XPATH, "//span[contains(text(),'Disable Agent')]/ancestor::button")
safe_click("Opening duration dropdown", By.CSS_SELECTOR, 'button[data-mgmtautomationid="enableDisableHoursDropdownOptionsDropdown"]')
safe_click("Selecting '12 Hours' duration", By.XPATH, "//button[@data-ux-id='12 Hours']")
safe_click("Confirming 'Disable Agent' action", By.CSS_SELECTOR, 'button[data-mgmtautomationid="enableDisableAgentEnableButton"]')
safe_click("Clicking final 'Yes' confirmation", By.CSS_SELECTOR, 'button[data-mgmtautomationid="YesButton"]')

# ======== FINISH ========
# driver.quit()  # Uncomment if you want to close the browser automatically
print("🏋️ Automation finished.")
log.info("Automation completed.")
