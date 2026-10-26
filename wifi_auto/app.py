import streamlit as st
from supabase import create_client, Client
import time

st.set_page_config(page_title="Wi-Fi Remote Controller", page_icon="📶", layout="centered")

# Configure your Supabase credentials (use st.secrets in Streamlit Cloud)
SUPABASE_URL = st.secrets.get("SUPABASE_URL", "https://YOUR_PROJECT.supabase.co")
SUPABASE_KEY = st.secrets.get("SUPABASE_KEY", "YOUR_ANON_KEY")


@st.cache_resource
def init_supabase() -> Client:
    return create_client(SUPABASE_URL, SUPABASE_KEY)


supabase = init_supabase()

st.title("📶 Wi-Fi Remote Controller")
st.write("Submit connection jobs from anywhere. Your local laptop will pick up the task and connect.")

ssid = st.text_input("Wi-Fi Name (SSID)", placeholder="e.g. realme 7i")
auth_type = st.selectbox("Security Type", ["WPA/WPA2", "WPA3", "WEP", "None (Open)"])

col1, col2 = st.columns(2)
with col1:
    prefix = st.text_input("Password Prefix", placeholder="e.g. air")
with col2:
    start_suffix = st.text_input("Starting Suffix", placeholder="e.g. 41566")

attempts = st.number_input("Attempts Count", min_value=1, max_value=100, value=10, step=1)

can_submit = bool(ssid.strip()) and bool(prefix.strip()) and start_suffix.strip().isdigit()

if st.button("Send Job to Laptop", type="primary", disabled=not can_submit):
    job_payload = {
        "ssid": ssid.strip(),
        "prefix": prefix.strip(),
        "start_suffix": int(start_suffix.strip()),
        "attempts": int(attempts),
        "auth_type": auth_type,
        "status": "pending"
    }
    res = supabase.table("wifi_jobs").insert(job_payload).execute()
    if res.data:
        st.session_state["active_job_id"] = res.data[0]["id"]
        st.success(f"Job #{res.data[0]['id']} queued! Waiting for your laptop to process...")

# Live Job Tracker
if "active_job_id" in st.session_state:
    job_id = st.session_state["active_job_id"]
    status_box = st.empty()

    # Poll database for updates
    job_res = supabase.table("wifi_jobs").select("*").eq("id", job_id).execute()
    if job_res.data:
        job = job_res.data[0]
        st.markdown(f"**Current Status:** `{job['status']}`")
        if job["result_message"]:
            st.info(job["result_message"])

        if job["status"] in ["success", "failed"]:
            del st.session_state["active_job_id"]
    time.sleep(2)
    st.rerun()