#!/usr/bin/python

# =============================================================
# SentinelOne Automation Script: Disable Agent via API
# -------------------------------------------------------------
# Author : Esha Sajaka
# Version: 1.0
# Date   : 2025-07-31
# Desc   : Disables SentinelOne agents using the API
#          with support for filtering by site/group name or ID,
#          duration, reboot flag, and timezone control.
# Target : Agents in specified site/group or all agents
# Logging: Writes logs to disable_agents.log
# =============================================================

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

# ====== LOGGING with Monthly Rotation ======
LOG_DIR = "/var/log/s1-auto-disable"
os.makedirs(LOG_DIR, exist_ok=True)

log_file = os.path.join(LOG_DIR, "disable_agents.log")

logger = logging.getLogger()
logger.setLevel(logging.INFO)

handler = TimedRotatingFileHandler(
    log_file,
    when="midnight",
    interval=1,
    backupCount=36,
    encoding="utf-8"
)
handler.suffix = "%Y-%m"
formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
handler.setFormatter(formatter)
logger.addHandler(handler)

console = logging.StreamHandler()
console.setFormatter(formatter)
logger.addHandler(console)

logging = logger

# ====== CONFIG LOAD ======
def get_base_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    else:
        return os.path.dirname(os.path.abspath(__file__))

CONFIG_PATH = os.path.join(get_base_dir(), "config.ini")
config = configparser.ConfigParser()
S1_CONSOLE = None
API_TOKEN = None

# ====== API URL CONFIGURATION PLACEHOLDER ======
API_URL = None
SITE_LIST_URL = None
GROUP_LIST_URL = None
HEADERS = None

# ====== DISABLE SSL WARNING ======
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ====== UTILITY: Resolve ID from name ======
def resolve_id(api_url, filter_name, target_names):
    resolved = []
    try:
        resp = requests.get(api_url, headers=HEADERS, params={"limit": 100}, verify=False)
        resp.raise_for_status()
        data = resp.json().get("data", {})
        items = data if isinstance(data, list) else data.get("sites") or data.get("groupList") or []
        for target_name in target_names:
            match = next((item for item in items if item.get("name", "").lower() == target_name.lower()), None)
            if match:
                resolved.append((match.get("id"), match.get("name")))
            else:
                raise ValueError(f"{filter_name.capitalize()} '{target_name}' not found.")
        return resolved
    except Exception as e:
        logging.error(f"Error resolving {filter_name} ID(s): {e}")
        raise

# ====== GET TOTAL AFFECTED AGENTS FUNCTION ======
def get_affected_agents(site_id=None, group_id=None, all_agents=False):
    query_url = f"https://{S1_CONSOLE}/web/api/v2.1/agents"
    params = {"limit": 1}
    if not all_agents:
        if site_id:
            params["siteIds"] = site_id
        if group_id:
            params["groupIds"] = group_id
    try:
        resp = requests.get(query_url, headers=HEADERS, params=params, verify=False)
        resp.raise_for_status()
        total = resp.json().get("pagination", {}).get("totalItems", 0)
        return total
    except Exception as e:
        logging.error(f"Failed to fetch affected agents: {e}")
        return -1

# ====== DISABLE AGENT FUNCTION ======
def disable_agents(expiration, site_id=None, group_id=None, reboot=False, all_agents=False):
    data = {
        "data": {
            "expiration": expiration,
            "shouldReboot": reboot
        },
        "filter": {}
    }
    if not all_agents:
        if site_id:
            data["filter"]["siteIds"] = [site_id]
        if group_id:
            data["filter"]["groupIds"] = [group_id]
    try:
        response = requests.post(API_URL, headers=HEADERS, json=data, verify=False)
        if response.ok:
            logging.info("Successfully sent disable command")
        else:
            logging.error(f"Request failed: {response.status_code} - {response.text}")
            sys.exit(1)
    except Exception as e:
        logging.error(f"Exception occurred: {e}")
        sys.exit(1)

# ====== MAIN ======
def main():
    global S1_CONSOLE, API_TOKEN, API_URL, SITE_LIST_URL, GROUP_LIST_URL, HEADERS

    parser = argparse.ArgumentParser(
    description="""
SentinelOne Automation Script: Disable Agent via API
---------------------------------------------------
Author : Esha Sajaka
Version: 1.0
Date   : 2025-07-31

This tool disables SentinelOne agents via API with support for:
- Filtering by Site Name or ID
- Filtering by Group Name or ID
- Specifying a disable duration (in hours)
- Optional reboot trigger
- Local timezone control
- Bulk action using --all

REQUIREMENT:
- A 'config.ini' file must be located in the same directory as this script or executable.
- You can generate one using: --init-config

EXAMPLE config.ini:
[sentinelone]
console = YOUR_CONSOLE_URL
api_token = YOUR_API_TOKEN_HERE

USAGE EXAMPLES:
# Disable all agents in a group for 1 hour
  ./disable_agent --duration 1 --group-name "Workstation Group"

# Disable by site and group names
  ./disable_agent --duration 2 --site-name "Jakarta" "Surabaya" --group-name "Server" "Workstation"

# Disable all agents across tenant
  ./disable_agent --duration 4 --all
"""
,
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--init-config", action="store_true", help="Create a template config.ini in the current directory and exit")
    parser.add_argument("--version", action="store_true", help="Show script version and exit")
    parser.add_argument("--show-config-path", action="store_true", help="Show resolved config.ini path and exit")
    parser.add_argument("--site-id", help="SentinelOne Site ID")
    parser.add_argument("--group-id", help="SentinelOne Group ID")
    parser.add_argument("--site-name", nargs="+", help="SentinelOne Site Name(s) (support multiple names)")
    parser.add_argument("--group-name", nargs="+", help="SentinelOne Group Name(s) (support multiple names)")
    parser.add_argument("--duration", type=int, required=False, help="Duration in hours to disable the agent")
    parser.add_argument("--timezone", default="Asia/Jakarta", help="Timezone for expiration")
    parser.add_argument("--reboot", action="store_true", help="Whether to reboot the agent machine")
    parser.add_argument("--all", action="store_true", help="Disable all agents")

    args = parser.parse_args()

    if args.init_config:
        if os.path.exists(CONFIG_PATH):
            print(f"config.ini already exists at: {CONFIG_PATH}")
        else:
            with open(CONFIG_PATH, "w") as f:
                f.write("[sentinelone]\nconsole = YOUR_CONSOLE_URL\napi_token = YOUR_API_TOKEN\n")
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

    if args.version:
        print("Disable SentinelOne Agent Script - Version 1.0 (by Esha Sajaka)")
        sys.exit(0)

    if args.show_config_path:
        print(f"Resolved config.ini path: {CONFIG_PATH}")
        sys.exit(0)

    try:
        if not os.path.isfile(CONFIG_PATH):
            print(f"Error: Config file not found at {CONFIG_PATH}. Please run the script with '--init-config' to generate a default config file.")
            sys.exit(1)

        config.read(CONFIG_PATH)
        S1_CONSOLE = config.get("sentinelone", "console")
        API_TOKEN = config.get("sentinelone", "api_token")
        if not S1_CONSOLE or not API_TOKEN:
            logging.error("Console URL or API token is missing in config.ini.")
            sys.exit(1)

        API_URL = f"https://{S1_CONSOLE}/web/api/v2.1/agents/actions/disable-agent"
        SITE_LIST_URL = f"https://{S1_CONSOLE}/web/api/v2.1/sites"
        GROUP_LIST_URL = f"https://{S1_CONSOLE}/web/api/v2.1/groups"
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

    if not args.duration:
        print("Error: --duration is required.")
        # parser.print_help()
        sys.exit(1)

    if not args.all and not any([args.site_id, args.site_name, args.group_id, args.group_name]):
        print("Error: Provide site/group or use --all.")
        # parser.print_help()
        sys.exit(1)

    try:
        if args.site_name:
            site_targets = resolve_id(SITE_LIST_URL, "site", args.site_name)
        elif args.site_id:
            site_targets = [(args.site_id, "ID-only")]
        else:
            site_targets = [("ALL", "ALL")]

        if args.group_name:
            group_targets = resolve_id(GROUP_LIST_URL, "group", args.group_name)
        elif args.group_id:
            group_targets = [(args.group_id, "ID-only")]
        else:
            group_targets = [("ALL", "ALL")]

        tz = pytz.timezone(args.timezone)
        now = datetime.now(tz)
        expiration_time = now + timedelta(hours=args.duration)
        expiration_utc = expiration_time.astimezone(pytz.utc)
        expiration_iso = expiration_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
        local_time_str = expiration_time.strftime("%Y-%m-%d %H:%M:%S")

        for site_id, site_name in site_targets:
            for group_id, group_name in group_targets:
                logging.info("============ DISABLE AGENT INITIATED ============")
                logging.info(f"Site: {site_name} (ID: {site_id})")
                logging.info(f"Group: {group_name} (ID: {group_id})")
                logging.info(f"Duration: {args.duration} hours")
                logging.info(f"Expiration UTC: {expiration_iso} | Local Time ({args.timezone}): {local_time_str}")
                logging.info(f"Reboot after disable: {'Yes' if args.reboot else 'No'}")

                affected_count = get_affected_agents(
                    site_id=None if site_id == "ALL" else site_id,
                    group_id=None if group_id == "ALL" else group_id,
                    all_agents=args.all
                )
                logging.info(f"Affected agents: {affected_count if affected_count >= 0 else 'Unknown'}")

                disable_agents(
                    expiration=expiration_iso,
                    site_id=None if site_id == "ALL" else site_id,
                    group_id=None if group_id == "ALL" else group_id,
                    reboot=args.reboot,
                    all_agents=args.all
                )

    except Exception as e:
        logging.error(f"Fatal error: {e}")
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
