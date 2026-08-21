import requests
import urllib3
import datetime
import sys
import json
import os

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# === Konfigurasi ===
API_TOKEN = "hfUT7faV5n5wLbbaR8KK7d1NbsI9O3t6KH63Z0fasSSrvdqs3HvYnK8MpRQUpsPpNMIecdvrXUGgTDbp"
CONSOLE_URL = "https://192.168.88.178"  # Ganti sesuai
LOG_DIR = "/var/log/sentinelone"
os.makedirs(LOG_DIR, exist_ok=True)

HEADERS = {
    "Authorization": f"ApiToken {API_TOKEN}",
    "Content-Type": "application/json"
}

# === Fungsi Logging JSON ===
def log_json(action, status_code, response_text, agent_ids):
    log_entry = {
        "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "action": action,
        "status_code": status_code,
        "agent_count": len(agent_ids),
        "agent_ids": agent_ids,
        "response": response_text
    }
    log_file = os.path.join(LOG_DIR, f"{action}_log.json")
    with open(log_file, "a") as f:
        json.dump(log_entry, f)
        f.write("\n")

# === Ambil semua endpoint ===
def get_all_agent_ids():
    url = f"{CONSOLE_URL}/web/api/v2.1/agents"
    response = requests.get(url, headers=HEADERS, verify=False)
    agents = response.json().get("data", [])
    return [agent["id"] for agent in agents]

# === Disable Agent ===
def disable_agents(agent_ids, duration_hours=9):
    expiration = (datetime.datetime.utcnow() + datetime.timedelta(hours=duration_hours)).strftime("%Y-%m-%dT%H:%M:%SZ")
    url = f"{CONSOLE_URL}/web/api/v2.1/agents/actions/disable"
    payload = {
        "filter": {
            "ids": agent_ids
        },
        "data": {
            "expiration": expiration
        }
    }
    r = requests.post(url, headers=HEADERS, json=payload, verify=False)
    log_json("disable", r.status_code, r.text, agent_ids)

# === Enable Agent ===
def enable_agents(agent_ids):
    url = f"{CONSOLE_URL}/web/api/v2.1/agents/actions/enable"
    payload = {
        "filter": {
            "ids": agent_ids
        }
    }
    r = requests.post(url, headers=HEADERS, json=payload, verify=False)
    log_json("enable", r.status_code, r.text, agent_ids)

# === Main ===
def main():
    if len(sys.argv) != 2 or sys.argv[1] not in ["disable", "enable"]:
        print("Gunakan: python toggle_agent.py [disable|enable]")
        return

    action = sys.argv[1]
    agent_ids = get_all_agent_ids()
    if not agent_ids:
        print("Tidak ada endpoint ditemukan.")
        return

    if action == "disable":
        disable_agents(agent_ids)
        print(f"[INFO] DISABLE {len(agent_ids)} endpoint.")
    elif action == "enable":
        enable_agents(agent_ids)
        print(f"[INFO] ENABLE {len(agent_ids)} endpoint.")

if __name__ == "__main__":
    main()
