import html
import os
import subprocess
import tempfile
import time

import streamlit as st

st.set_page_config(page_title="Wi-Fi Auto Connect", page_icon="📶", layout="centered")

st.title("📶 Wi-Fi Auto Connect")
st.write("Enter the network name and password prefix/suffix range. This PC will test sequential passwords until connected.")

ssid = st.text_input("Wi-Fi Name (SSID)", placeholder="e.g. MyHomeNetwork")
auth_type = st.selectbox(
    "Security Type",
    ["WPA/WPA2", "WPA3", "WEP", "None (Open)"],
)

pwd_part1 = ""
pwd_part2 = ""

if auth_type != "None (Open)":
    st.write("Wi-Fi Password")
    col1, col2 = st.columns(2)
    with col1:
        pwd_part1 = st.text_input("Prefix", placeholder="e.g. air")
    with col2:
        pwd_part2 = st.text_input("Starting Suffix (Digits)", placeholder="e.g. 41566")

    col_cfg1, col_cfg2 = st.columns(2)
    with col_cfg1:
        test_range = st.number_input("Attempts Count", min_value=1, max_value=5000, value=1, step=1)
    with col_cfg2:
        step_delay = st.number_input("Wait per attempt (sec)", min_value=0, max_value=100, value=5, step=1)

    p1 = pwd_part1.strip()
    p2 = pwd_part2.strip()
    if p1 and p2.isdigit():
        base = int(p2)
        pad = len(p2)
        first_pwd = f"{p1}{str(base).zfill(pad)}"
        last_pwd = f"{p1}{str(base + test_range - 1).zfill(pad)}"
        st.caption(f"Testing range ({test_range} combinations): `{first_pwd}` → `{last_pwd}`")


def _security_xml(auth: str, key: str) -> str:
    if auth == "None (Open)":
        return """
            <authEncryption>
                <authentication>open</authentication>
                <encryption>none</encryption>
                <useOneX>false</useOneX>
            </authEncryption>"""
    if auth == "WEP":
        return f"""
            <authEncryption>
                <authentication>open</authentication>
                <encryption>WEP</encryption>
                <useOneX>false</useOneX>
            </authEncryption>
            <sharedKey>
                <keyType>networkKey</keyType>
                <protected>false</protected>
                <keyMaterial>{key}</keyMaterial>
            </sharedKey>"""
    if auth == "WPA3":
        authentication = "WPA3SAE"
    else:
        authentication = "WPA2PSK"
    return f"""
            <authEncryption>
                <authentication>{authentication}</authentication>
                <encryption>AES</encryption>
                <useOneX>false</useOneX>
            </authEncryption>
            <sharedKey>
                <keyType>passPhrase</keyType>
                <protected>false</protected>
                <keyMaterial>{key}</keyMaterial>
            </sharedKey>"""


def _profile_xml(network_name: str, network_password: str, auth: str) -> str:
    safe_name = html.escape(network_name)
    safe_key = html.escape(network_password)
    security = _security_xml(auth, safe_key)
    return f"""<?xml version="1.0"?>
<WLANProfile xmlns="http://www.microsoft.com/networking/WLAN/profile/v1">
    <name>{safe_name}</name>
    <SSIDConfig>
        <SSID>
            <name>{safe_name}</name>
        </SSID>
    </SSIDConfig>
    <connectionType>ESS</connectionType>
    <connectionMode>auto</connectionMode>
    <MSM>
        <security>{security}
        </security>
    </MSM>
</WLANProfile>
"""


def _run_netsh(args: list[str]) -> tuple[int, str]:
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    result = subprocess.run(
        ["netsh", *args],
        capture_output=True,
        text=True,
        timeout=40,
        creationflags=flags,
    )
    output = ((result.stdout or "") + (result.stderr or "")).strip()
    return result.returncode, output


def _is_on_network(status: str, network_name: str) -> bool:
    state = ""
    connected_ssid = ""
    for line in status.splitlines():
        stripped = line.strip()
        if ":" not in stripped:
            continue
        label, value = stripped.split(":", 1)
        label = label.strip().lower()
        value = value.strip()
        if label == "state":
            state = value.lower()
        elif label == "ssid":
            connected_ssid = value
    return state == "connected" and connected_ssid == network_name


def current_wifi_status() -> str:
    if os.name != "nt":
        return "Auto-connect uses Windows netsh, so it only works on this PC."
    try:
        code, output = _run_netsh(["wlan", "show", "interfaces"])
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"Could not read Wi-Fi status: {exc}"
    if code != 0:
        return output or "No wireless interface found."
    return output


def connect_wifi(network_name: str, network_password: str, auth: str, wait_seconds: int = 4) -> tuple[bool, str]:
    profile_path = None
    try:
        # Delete any existing profile with this name to avoid cache conflicts
        _run_netsh(["wlan", "delete", "profile", f"name={network_name}"])

        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".xml",
            delete=False,
            encoding="utf-8",
        ) as handle:
            handle.write(_profile_xml(network_name, network_password, auth))
            profile_path = handle.name

        code, output = _run_netsh(
            ["wlan", "add", "profile", f"filename={profile_path}", "user=current"]
        )
        if code != 0:
            return False, output or "Windows rejected the Wi-Fi profile."

        code, output = _run_netsh(
            ["wlan", "connect", f"name={network_name}", f"ssid={network_name}"]
        )
        if code != 0:
            return False, output or "Windows could not start the connection."

        time.sleep(wait_seconds)
        _, status = _run_netsh(["wlan", "show", "interfaces"])
        if _is_on_network(status, network_name):
            return True, status
        return False, status or output or "Connection attempted, but interface is not authenticated."
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)
    finally:
        if profile_path and os.path.exists(profile_path):
            os.remove(profile_path)


with st.expander("Current Wi-Fi status"):
    st.code(current_wifi_status())

# Validation logic
cleaned_ssid = ssid.strip()
p1_clean = pwd_part1.strip()
p2_clean = pwd_part2.strip()

if auth_type == "None (Open)":
    can_connect = bool(cleaned_ssid)
else:
    can_connect = bool(cleaned_ssid) and bool(p1_clean) and p2_clean.isdigit()

if not can_connect:
    st.caption("Provide an SSID, a prefix (e.g. `air`), and a numeric suffix (e.g. `41566`).")

if st.button("Connect this PC", type="primary", disabled=not can_connect):
    connected = False
    last_detail = ""

    if auth_type == "None (Open)":
        with st.spinner(f"Connecting to open network {cleaned_ssid}..."):
            ok, last_detail = connect_wifi(cleaned_ssid, "", auth_type, wait_seconds=step_delay)
            if ok:
                st.success(f"Connected to {cleaned_ssid} successfully!")
            else:
                st.error("Could not connect to open network.")
                st.code(last_detail)
    else:
        status_box = st.empty()
        base_number = int(p2_clean)
        pad_width = len(p2_clean)

        for offset in range(int(test_range)):
            current_num = base_number + offset
            formatted_num = str(current_num).zfill(pad_width)
            current_password = f"{p1_clean}{formatted_num}"

            status_box.info(f"Attempting ({offset + 1}/{test_range}): `{current_password}`")

            ok, last_detail = connect_wifi(cleaned_ssid, current_password, auth_type, wait_seconds=step_delay)
            if ok:
                connected = True
                status_box.empty()
                st.success(f"Connected to **{cleaned_ssid}** successfully!")
                st.success(f"Working password found: `{current_password}`")
                break

        if not connected:
            status_box.empty()
            st.error(f"Could not connect after testing {test_range} passwords.")
            st.code(last_detail)