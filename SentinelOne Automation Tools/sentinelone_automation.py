import argparse
import requests
import logging
from logging.handlers import TimedRotatingFileHandler
from datetime import datetime, timedelta
import pytz
import sys
import urllib3
import os
import configparser

# ====== LOGGING SETUP ======
LOG_DIR = "/var/log/s1-automation"
os.makedirs(LOG_DIR, exist_ok=True)
log_file = os.path.join(LOG_DIR, "sentinelone_automation.log")
logger = logging.getLogger()
logger.setLevel(logging.INFO)
handler = TimedRotatingFileHandler(log_file, when="midnight", interval=1, backupCount=36, encoding="utf-8")
handler.suffix = "%Y-%m"
formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
handler.setFormatter(formatter)
logger.addHandler(handler)
console = logging.StreamHandler()
console.setFormatter(formatter)
logger.addHandler(console)
logging = logger

# ====== CONFIG & API PLACEHOLDERS ======
def get_base_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    else:
        return os.path.dirname(os.path.abspath(__file__))

CONFIG_PATH = os.path.join(get_base_dir(), "config.ini")
config = configparser.ConfigParser()

S1_CONSOLE = None
API_TOKEN = None
BASE_URL = None
HEADERS = None

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ====== Resolve Site/Group ID by Name ======
def resolve_id(api_url, filter_name, target_names):
    resolved = []
    try:
        resp = requests.get(api_url, headers=HEADERS, params={"limit": 100}, verify=False)
        resp.raise_for_status()
        data = resp.json().get("data", {})
        items = data if isinstance(data, list) else data.get("sites") or data.get("groupList") or []
        for name in target_names:
            match = next((item for item in items if item.get("name", "").lower() == name.lower()), None)
            if match:
                resolved.append((match.get("id"), match.get("name")))
            else:
                logging.error(f"{filter_name.capitalize()} '{name}' not found.")
                return None   # ❗ stop tanpa raise
        return resolved
    except Exception as e:
        logging.error(f"Error resolving {filter_name} ID(s): {e}")
        return None

# ====== Resolve Name by ID ======
def resolve_name_from_id(api_url, item_type, item_id):
    """Looks up a Site or Group name from its ID using the correct endpoint."""
    # Correct endpoint is /api/v2.1/sites/<site_id>
    lookup_url = f"{api_url}/{item_id}"
    try:
        resp = requests.get(lookup_url, headers=HEADERS, verify=False)
        resp.raise_for_status()
        # The response for a single item is a 'data' object, not a list
        data = resp.json().get("data", {})
        
        if data and "name" in data:
            # If found, return the actual name
            return data.get("name")
        else:
            # If API returns no data for that ID
            logging.warning(f"Could not find a name for {item_type} ID '{item_id}'. Using the ID as a fallback.")
            return f"ID: {item_id}"
            
    except requests.exceptions.HTTPError as e:
        # Specifically catch HTTP errors to provide better feedback
        if e.response.status_code == 404:
            logging.warning(f"{item_type.capitalize()} with ID '{item_id}' not found (404).")
        else:
            logging.error(f"An HTTP error occurred while resolving name for {item_type} ID '{item_id}': {e}")
        return f"ID: {item_id}"
    except Exception as e:
        logging.error(f"A general error occurred while resolving name for {item_type} ID '{item_id}': {e}")
        return f"ID: {item_id}"
    
# ====== Disable Agent Function ======
def disable_agents(expiration, site_id=None, group_id=None, reboot=False, all_agents=False):
    url = f"{BASE_URL}/agents/actions/disable-agent"
    data = {
        "data": {
            "expiration": expiration,
            "shouldReboot": reboot
        },
        "filter": {}
    }
    if not all_agents:
        if site_id: data["filter"]["siteIds"] = [site_id]
        if group_id: data["filter"]["groupIds"] = [group_id]
    try:
        resp = requests.post(url, headers=HEADERS, json=data, verify=False)
        if resp.ok:
            logging.info("Disable command sent successfully.")
        else:
            logging.error(f"Request failed: {resp.status_code} - {resp.text}")
            sys.exit(1)
    except Exception as e:
        logging.error(f"Exception occurred: {e}")
        sys.exit(1)

# ====== Get Current Policy ======
def get_current_policy(target_type, target_id):
    url = f"{BASE_URL}/{target_type}s/{target_id}/policy"
    try:
        resp = requests.get(url, headers=HEADERS, verify=False)
        if resp.ok:
            return resp.json().get("data", {})
        else:
            logging.error(f"Failed to fetch current policy: {resp.status_code} - {resp.text}")
            sys.exit(1)
    except Exception as e:
        logging.error(f"Error fetching policy: {e}")
        sys.exit(1)

# ====== Set Protection Mode Function ======
def set_protection_mode(target_type, target_id, target_name, mode, auto_action=None):
    url = f"{BASE_URL}/{target_type}s/{target_id}/policy"

    current_policy = get_current_policy(target_type, target_id)
    if not current_policy:
        logging.error("No policy data found.")
        sys.exit(1)

    current_policy["mitigationMode"] = mode
    current_policy["mitigationModeSuspicious"] = mode

    if mode == "detect":
        current_policy["autoMitigationAction"] = "mitigation.none"
    elif mode == "protect":
        mapping = {
            "quarantine": "mitigation.quarantineThreat",
            "remediate": "mitigation.remediateThreat",
            "rollback": "mitigation.rollbackThreat"
        }
        current_policy["autoMitigationAction"] = mapping.get(auto_action or "rollback", "mitigation.rollbackThreat")

    data = {"data": current_policy}

    try:
        resp = requests.put(url, headers=HEADERS, json=data, verify=False)
        if resp.ok:
            logging.info(f"Updating {target_type} '{target_name}' (ID: {target_id}) protection mode to '{mode}' mode.")
            logging.info(f"Protection mode updated to '{mode}' for {target_type} '{target_name}' (ID: {target_id}).")
        else:
            logging.error(f"Failed to update protection mode: {resp.status_code} - {resp.text}")
            sys.exit(1)
    except Exception as e:
        logging.error(f"Error updating protection: {e}")
        sys.exit(1)

# ====== Main Entrypoint ======
def main():
    global S1_CONSOLE, API_TOKEN, BASE_URL, HEADERS
    
    parser = argparse.ArgumentParser(
        description="""
SentinelOne Automation Script
Author : Esha Sajaka
Version: 1.0

This script supports multiple actions:
  - Disable SentinelOne agent(s)
  - Change protection mode policy (detect/protect)

Requirement:
- A 'config.ini' file must be in the same folder as this script.
- Generate a template by running with: --init-config

Examples:
  sentinelone_automation.py --action disable-agent --duration 1 --site-name "Site A" --group-name "Group B"
  sentinelone_automation.py --action set-protection-mode --protection-mode protect --site-name "Site A"
  sentinelone_automation.py --init-config
        """,
        formatter_class=argparse.RawTextHelpFormatter
    )
    
    # Utility arguments
    parser.add_argument("--init-config", action="store_true", help="Create a template config.ini and exit.")
    parser.add_argument("--version", action="store_true", help="Show script version and exit.")
    parser.add_argument("--show-config-path", action="store_true", help="Show the resolved path for config.ini and exit.")

    # Main action arguments
    parser.add_argument("--action", choices=["disable-agent", "set-protection-mode"], help="Action to perform")
    parser.add_argument("--site-id", nargs="+", help="Target site ID(s)")
    parser.add_argument("--group-id", nargs="+", help="Target group ID(s)")
    parser.add_argument("--site-name", nargs="+", help="Target site name(s)")
    parser.add_argument("--group-name", nargs="+", help="Target group name(s)")
    parser.add_argument("--duration", type=int, help="Duration (hours) for disable-agent")
    parser.add_argument("--reboot", action="store_true", help="Reboot device after disabling")
    parser.add_argument("--all", action="store_true", help="Affect all agents (disable-agent only)")
    parser.add_argument("--timezone", default="Asia/Jakarta", help="Timezone (default: Asia/Jakarta)")
    parser.add_argument("--protection-mode", choices=["detect", "protect"], help="Policy mode for set-protection-mode")
    parser.add_argument("--auto-mitigation-action", choices=["quarantine", "remediate", "rollback"], help="Auto mitigation action for protection mode protect (default: rollback)")

    args = parser.parse_args()

    # Handle utility arguments first
    if args.version:
        print("SentinelOne Automation Script - Version 1.1 (by Esha Sajaka)")
        sys.exit(0)
        
    if args.show_config_path:
        print(f"Resolved config.ini path: {CONFIG_PATH}")
        sys.exit(0)

    if args.init_config:
        if os.path.exists(CONFIG_PATH):
            print(f"Config file already exists: {CONFIG_PATH}")
        else:
            with open(CONFIG_PATH, "w") as f:
                f.write("[sentinelone]\nconsole=YOUR_CONSOLE_URL\napi_token=YOUR_API_TOKEN\n")
            print(f"Template config.ini created at: {CONFIG_PATH}")
        try:
            if sys.platform.startswith("win"):
                os.startfile(CONFIG_PATH)
            elif sys.platform.startswith("darwin"):
                os.system(f"open {CONFIG_PATH}")
            else:
                os.system(f"nano {CONFIG_PATH}")
        except Exception as e:
            print(f"Failed to open config.ini: {e}")
        sys.exit(0)

    # --- Main Logic ---
    # From here on, we assume an action is being performed, so config is required.
    
    try:
        if not os.path.isfile(CONFIG_PATH):
            print(f"Error: Config file not found at {CONFIG_PATH}")
            print("Please run with '--init-config' to create a template file.")
            sys.exit(1)
        config.read(CONFIG_PATH)
        S1_CONSOLE = config.get("sentinelone", "console")
        API_TOKEN = config.get("sentinelone", "api_token")
        if not S1_CONSOLE or not API_TOKEN or "YOUR_CONSOLE" in S1_CONSOLE or "YOUR_API_TOKEN" in API_TOKEN:
            logging.error("Console URL or API token is missing or not updated in config.ini.")
            sys.exit(1)
            
        # Initialize API variables
        BASE_URL = f"{S1_CONSOLE}/web/api/v2.1"
        HEADERS = {
            "Authorization": f"ApiToken {API_TOKEN}",
            "Content-Type": "application/json"
        }

    except configparser.NoSectionError as e:
        logging.error(f"Missing section in config.ini: {e}")
        sys.exit(1)
    except configparser.NoOptionError as e:
        logging.error(f"Missing option in config.ini: {e}")
        sys.exit(1)
    except Exception as e:
        logging.error(f"Failed to read configuration: {e}")
        sys.exit(1)

    # Action validation
    if not args.action:
        print("Error: --action is required. Choose either 'disable-agent' or 'set-protection-mode'.")
        sys.exit(1)

    if args.action == "disable-agent":
        if not args.duration:
            print("Error: --duration is required for disable-agent")
            sys.exit(1)
        if not args.all and not any([args.site_name, args.group_name, args.site_id, args.group_id]):
            print("Error: For 'disable-agent', you must specify scope with --site-id, --site-name, group-id, --group-name, or --all.")
            sys.exit(1)

        tz = pytz.timezone(args.timezone)
        now = datetime.now(tz)
        expiration = now + timedelta(hours=args.duration)
        expiration_utc = expiration.astimezone(pytz.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        # Process Site targets
        if args.site_name:
            site_targets = resolve_id(f"{BASE_URL}/sites", "site", args.site_name)
            if not site_targets:
                logging.error("One or more site names could not be resolved. Please check your input.")
                sys.exit(1)

        elif args.site_id:
            site_targets = []
            for sid in args.site_id:
                name = resolve_name_from_id(f"{BASE_URL}/sites", "site", sid)
                site_targets.append((sid, name))
        else:
            site_targets = [("ALL", "All Sites")]

        # Process Group targets
        if args.group_name:
            group_targets = resolve_id(f"{BASE_URL}/groups", "group", args.group_name)
            if not group_targets:
                logging.error("One or more group names could not be resolved. Please check your input.")
                sys.exit(1)

        elif args.group_id:
            group_targets = []
            for gid in args.group_id:
                name = resolve_name_from_id(f"{BASE_URL}/groups", "group", gid)
                group_targets.append((gid, name))
        else:
            group_targets = [("ALL", "All Groups")]

        for site_id, site_name in site_targets:
            for group_id, group_name in group_targets:
                logging.info(f"Disabling agents in site '{site_name}' group '{group_name}' for {args.duration}h")
                disable_agents(
                    expiration=expiration_utc,
                    site_id=None if site_id == "ALL" else site_id,
                    group_id=None if group_id == "ALL" else group_id,
                    reboot=args.reboot,
                    all_agents=args.all
                )

    elif args.action == "set-protection-mode":
        if not args.protection_mode:
            print("Error: --protection-mode is required for set-protection-mode. Choose either 'protect' or 'detect' protection mode.")
            sys.exit(1)
        if not any([args.site_name, args.group_name, args.site_id, args.group_id]):
            print("Error: You must specify at least site-id, -site-name, group-id or --group-name for action 'set-protection-mode'.")
            sys.exit(1)
            
        # Process Site targets
        if args.site_name:
            site_targets = resolve_id(f"{BASE_URL}/sites", "site", args.site_name)
        elif args.site_id:
            site_targets = []
            for sid in args.site_id:
                name = resolve_name_from_id(f"{BASE_URL}/sites", "site", sid)
                site_targets.append((sid, name))
        else:
            site_targets = []

        # Process Group targets
        if args.group_name:
            group_targets = resolve_id(f"{BASE_URL}/groups", "group", args.group_name)
        elif args.group_id:
            group_targets = []
            for gid in args.group_id:
                name = resolve_name_from_id(f"{BASE_URL}/groups", "group", gid)
                group_targets.append((gid, name))
        else:
            group_targets = []

        for site_id, site_name in site_targets:
            set_protection_mode("site", site_id, site_name, args.protection_mode, args.auto_mitigation_action)

        for group_id, group_name in group_targets:
            set_protection_mode("group", group_id, group_name, args.protection_mode, args.auto_mitigation_action)

if __name__ == "__main__":
    main()
