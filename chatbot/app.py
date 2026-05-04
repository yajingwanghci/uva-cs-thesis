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
import streamlit.components.v1 as components
from dotenv import load_dotenv
from azure.storage.blob import BlobServiceClient

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
    "tid", 
    "condition", 
    "turn", 
    "user_response_len", 
    "chatbot_response_len", 
    "timestamp_utc"
]


# ── Helpers ───────────────────────────────────────────────────────────────────
def parse_params():
    """Read tid and condition from Qualtrics iframe URL."""
    params    = st.query_params
    tid       = params.get("tid", "unknown")       # LabTool participant ID
    condition = params.get("condition", "0")
    if condition not in {"0", "1", "2"}:
        condition = "0"
    return tid, condition


def get_ai_reply(system_prompt: str, history: list) -> str:
    payload = {
        "model":       MODEL_NAME,
        "messages":    [{"role": "system", "content": system_prompt}] + history[-8:],
        "temperature": 0.9,
        "max_tokens":  150,
    }
    try:
        resp = requests.post(
            BASE_URL + ENDPOINT, headers=HEADERS, json=payload, timeout=30
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]
    except Exception:
        return "I'm having a little trouble connecting right now. Please try again."


def log_to_blob(row: dict):
    if not BLOB_CONN_STR:
        return  
    try:
        blob_service = BlobServiceClient.from_connection_string(BLOB_CONN_STR)
        blob_client  = blob_service.get_blob_client(
            container=BLOB_CONTAINER, blob=BLOB_NAME
        )
        existing = ""
        if blob_client.exists():
            existing = blob_client.download_blob().readall().decode("utf-8")

        buf    = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=FIELDNAMES)
        if not existing:
            writer.writeheader()
        writer.writerow(row)

        blob_client.upload_blob(existing + buf.getvalue(), overwrite=True)
    except Exception as e:
        pass 



# ── Session state initialization ─────────────────────────────────────────────────────────
tid, condition = parse_params()

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

    The conversation will last for **6 turns**.
    The conversation is private and anonymous. We do not store the content of your messages; only minimal metadata (e.g., message length) is recorded.
    """
)


# ── Display chat ────────────────────────────────────────────
for msg in st.session_state.messages:
    st.chat_message(msg["role"]).write(msg["content"])


# ── Active conversation ────────────────────────────────────────────────────────
if st.session_state.turn < MAX_TURNS:
    user_input = st.chat_input("Your thoughts...")

    if user_input:
        user_len = len(user_input)
        st.session_state.messages.append({"role": "user", "content": user_input})
        st.chat_message("user").write(user_input)

        # Build system prompt (append closing instruction on final turn)
        system_prompt = st.session_state.system_prompt
        if st.session_state.assistant_turn == MAX_TURNS - 1:
            system_prompt += (
                "\nThis is the final message. "
                "Provide a summary of the conversation. "
                "Do NOT ask any further questions and end conversation naturally."
            )

        assistant_reply = get_ai_reply(system_prompt, st.session_state.messages)
        chatbot_len     = len(assistant_reply)

        st.session_state.messages.append(
            {"role": "assistant", "content": assistant_reply}
        )
        st.chat_message("assistant").write(assistant_reply)

        log_to_blob({
            "tid":                  tid,
            "condition":            condition,
            "turn":                 st.session_state.turn + 1,
            "user_response_len":    user_len,
            "chatbot_response_len": chatbot_len,
            "timestamp_utc":        datetime.now(timezone.utc).isoformat(),
        })

        st.session_state.turn           += 1
        st.session_state.assistant_turn += 1
        st.rerun()


# ── End message ──────────────────────────────────────────────────────────────
else:
    st.divider()
    st.success("✅ The reflection session is now complete.")
    st.info(
        "Thank you for your participation! "
        "Please click **Next** in the survey to continue."
    )

    # Notify the Qualtrics parent frame → triggers showNextButton() in JS
    components.html(
        f"""
        <script>
            window.parent.postMessage({{
                type:      'chatbot_done',
                tid:       '{tid}',
                condition: '{condition}',
                turns:     {st.session_state.turn}
            }}, '*');
        </script>
        """,
        height=0,
    )