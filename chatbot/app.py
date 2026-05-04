# =============================================================================
#  Sycophantic Chatbot Experiment
# =============================================================================


# ── Standard library ──────────────────────────────────────────────────────────
import os
import io
import csv
import requests
from datetime import datetime, timezone

# ── Third-party ───────────────────────────────────────────────────────────────
import streamlit as st
from dotenv import load_dotenv
from azure.storage.blob import BlobServiceClient
from azure.core.exceptions import AzureError

from system_prompts import get_system_prompt    
load_dotenv()


# ── Environment setup ──────────────────────────────────────────────────────────
API_KEY = os.getenv("MY_API_KEY")
BASE_URL = "https://llmproxy.uva.nl"  # Azure LiteLLM proxy "https://ai-research-proxy.azurewebsites.net"
ENDPOINT = "/chat/completions"
MODEL_NAME = "gpt-5.1"
MAX_TURNS = 6           # user turns, excluding the chatbot's initial greeting

HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json"
}

# Azure Blob Storage
BLOB_CONN_STR  = os.getenv("AZURE_STORAGE_CONNECTION_STRING", "")
BLOB_CONTAINER = os.getenv("BLOB_CONTAINER_NAME", "experiment-logs")
BLOB_NAME      = "chat_log.csv"

FIELDNAMES = [
    "pid", 
    "condition", 
    "turn", 
    "user_response_len", 
    "chatbot_response_len", 
    "timestamp_utc"
]


# ── Helper Functions ──────────────────────────────────────────────────────────
def log_to_blob(data_dict: dict):
    """Appends experiment metadata to a CSV file stored in Azure Blob Storage."""
    if not BLOB_CONN_STR:
        st.error("Azure Connection String missing. Data not saved.")
        return

    try:
        blob_service_client = BlobServiceClient.from_connection_string(BLOB_CONN_STR)
        blob_client = blob_service_client.get_blob_client(container=BLOB_CONTAINER, blob=BLOB_NAME)

        # Download existing content or start new
        existing_content = ""
        if blob_client.exists():
            existing_content = blob_client.download_blob().readall().decode('utf-8')
        
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=FIELDNAMES)
        
        # If the file is new/empty, write the header first
        if not existing_content:
            writer.writeheader()
        
        writer.writerow(data_dict)
        final_csv_data = existing_content + output.getvalue()
        
        # Upload updated CSV back to Azure
        blob_client.upload_blob(final_csv_data, overwrite=True)
    except Exception as e:
        st.error(f"Data logging failed: {e}")

def parse_params():
    """Extracts pid and condition from Qualtrics URL parameters."""
    params = st.query_params
    pid = params.get("pid", "unknown_user")
    condition = params.get("condition", "0") # Default to non-sycophantic
    
    # Ensure condition is within valid experimental bounds
    if condition not in {"0", "1", "2"}:
        condition = "0"
        
    return pid, condition

def get_ai_reply(system_prompt: str, history: list) -> str:
    """Calls the LLM Proxy for a chatbot response."""
    payload = {
        "model": MODEL_NAME,
        "messages": [{"role": "system", "content": system_prompt}] + history[-8:],
        "temperature": 0.9,
        "max_tokens": 150,
    }
    try:
        resp = requests.post(BASE_URL + ENDPOINT, headers=HEADERS, json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]
    except Exception as e:
        return "I'm having a little trouble connecting right now. Please try again."



# ── Session state initialization ─────────────────────────────────────────────────────────
pid, condition = parse_params()

if "messages" not in st.session_state:
    st.session_state.messages = [
        {
            "role": "assistant",
            "content": "Hello there! Close your eyes and scan your last 24 hours like a treasure hunt. What is one small, beautiful moment you noticed?"
        }
    ]

if "turn" not in st.session_state:
    st.session_state.turn = 0

if "assistant_turn" not in st.session_state:
    st.session_state.assistant_turn = 0

if "system_prompt" not in st.session_state:
    st.session_state.system_prompt = get_system_prompt(condition)



# ── UI ───────────────────────────────────────────────────────────────
st.set_page_config(page_title="Reflection chatbot 💬", page_icon="💬")
st.title("Reflect with a chatbot 💬")
st.markdown(
    """
    Take a moment to reflect through a short conversation with an AI chatbot.

    Share anything on your mind—your thoughts, feelings, or recent experiences. 
    The conversation is here to help you explore your perspective and gain new insights.
    The conversation will last for **6 turns**.
    The conversation is private and anonymous. We do not store the content of your messages; only minimal metadata (e.g., message length and pronoun counts) is recorded.
    """
)


# ── Display chat ────────────────────────────────────────────
for msg in st.session_state.messages:
    st.chat_message(msg["role"]).write(msg["content"])

# ── Input control ───────────────────────────────────────────
if st.session_state.turn < MAX_TURNS:
    user_input = st.chat_input("Your thoughts...")
else:
    user_input = None

# ── Chat loop ───────────────────────────────────────────────
if user_input:

    # ── user ───────────────────────────────────────────────
    user_len = len(user_input)

    st.session_state.messages.append({"role": "user", "content": user_input})
    st.chat_message("user").write(user_input)

    # ── assistant ─────────────────────────────────────────
    is_final_assistant_turn = st.session_state.assistant_turn == (MAX_TURNS - 1)

    system_prompt = st.session_state.system_prompt

    if is_final_assistant_turn:
        system_prompt += (
            "\nThis is the final message. "
            "Provide a summary of the conversation. "
            "Do NOT ask any further question and end the conversation naturally."
        )

    assistant_reply = get_ai_reply(system_prompt, st.session_state.messages)

    chatbot_len = len(assistant_reply)

    st.session_state.messages.append({"role": "assistant", "content": assistant_reply})
    st.chat_message("assistant").write(assistant_reply)

    
    # ── Log to Azure Blob Storage ─────────────────────────────────────────────
    log_to_blob({
        "pid":                 pid,
        "condition":           condition,
        "turn":                st.session_state.turn + 1,
        "user_response_len":   user_len,
        "chatbot_response_len": chatbot_len,
        "timestamp_utc":       datetime.now(timezone.utc).isoformat(),
    })
 

    # ── update state ──────────────────────────────────────────────────────────
    st.session_state.turn += 1
    st.session_state.assistant_turn += 1

    st.rerun()


# ── End message ──────────────────────────────────────────────────────────────
else:
    st.divider()
    st.success("The reflection session is now complete.")
    st.info("Thank you for your participation! Please click the button below to return to the Qualtrics and finish your response.")
    
    qualtrics_url = f"https://uva.fra1.qualtrics.com/xxx?pid={pid}&status=complete"
    
    st.link_button("Return to Qualtrics Survey", qualtrics_url)
