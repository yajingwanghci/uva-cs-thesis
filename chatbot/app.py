# =============================================================================
#  Sycophantic Chatbot Experiment
# =============================================================================

# streamlit run app.py

# ── Standard library ──────────────────────────────────────────────────────────
import json
import requests
import os
import random
from datetime import datetime, timezone

# ── Third-party ───────────────────────────────────────────────────────────────
import streamlit as st
from dotenv import load_dotenv
from textblob import TextBlob 

from system_prompts import get_system_prompt    
load_dotenv()


# ── API configuration ──────────────────────────────────────────────────────────
API_KEY = os.getenv("MY_API_KEY")
API_BASE_URL = "https://llmproxy.uva.nl"  # Azure LiteLLM proxy "https://ai-research-proxy.azurewebsites.net"
ENDPOINT = "/chat/completions"
MODEL_NAME = "gpt-5.1"
MAX_TURNS = 6           # user turns, excluding the chatbot's initial greeting

HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json"
}


# ── Helper functions ──────────────────────────────────────────────────────────
def build_api_messages(conversation: list, system_prompt: str) -> list:
    """
    Construct the message list to send to the LLM API for a single turn.

    The system prompt is inserted as a {"role": "system"} message at
    position 0.  Participants never see this text, but it defines the
    model's entire persona and behavioral instructions for the conversation.

    Only "role" and "content" are forwarded from the conversation history.
    The "timestamp" key is local-only metadata that the chat completions API
    does not accept and would cause a validation error if included.

    Parameters
    ----------
    conversation : list[dict]
        The current value of st.session_state["messages"].  Each element
        has "role" ("user" or "assistant"), "content", and "timestamp" keys.
    system_prompt : str
        The hidden system prompt from the active condition dict.

    Returns
    -------
    list[dict]
        A list of {"role": str, "content": str} dicts ready for the
        chat completions endpoint.
    """
    return (
        [{"role": "system", "content": system_prompt}]
        + [
            {"role": m["role"], "content": m["content"]}
            for m in conversation
        ]
    )


def build_anonymous_metadata(messages):
    """
    Extracts only metadata (word count, sentiment) and removes raw text.
    Sentiment score: -1.0 (negative) to 1.0 (positive).
    """
    metadata_list = []
    
    for m in messages:
        # Calculate Word Count
        word_count = len(m["content"].split())
        
        # Calculate Sentiment Score using TextBlob
        # If text is too short, score defaults to 0.0
        analysis = TextBlob(m["content"])
        sentiment_score = round(analysis.sentiment.polarity, 3) 
        
        metadata_list.append({
            "role": "participant" if m["role"] == "user" else "assistant",
            "word_count": word_count,
            "sentiment_score": sentiment_score,
            "timestamp": m.get("timestamp", "")
        })
    
    return {
        "study_info": {
            "total_turns": len(metadata_list) // 2,
            "completion_time": datetime.now(timezone.utc).isoformat()
        },
        "data": metadata_list
    }

# ── Experiment conditions ───────────────────────────────────────────────────────
N_CONDITIONS = 3 

CONDITIONS = [
    {"name": "Condition A", "passcode": "ALPHA", "model": MODEL_NAME, "system_prompt": get_system_prompt("Condition A - Non-sycophantic")},
    {"name": "Condition B", "passcode": "BETA", "model": MODEL_NAME, "system_prompt": get_system_prompt("Condition B - Moderately sycophantic")},
    {"name": "Condition C", "passcode": "GAMMA", "model": MODEL_NAME, "system_prompt": get_system_prompt("Condition C - Highly sycophantic")}
]

STUDY_TITLE = "Reflection Chatbot"

WELCOME_MESSAGE = """
### 👋 Welcome!
I am your AI assistant, here to guide you through a brief reflection session.

Take a moment to share whatever is on your mind—your thoughts, feelings, or recent experiences. 

**How it works:**
*   💬 **Duration:** The conversation consists of exactly **6 turns**.
*   🔐 **Privacy:** This session is anonymous. We **do not** store your message text; only metadata (e.g., message length and emotional tone) is recorded.
*   ✅ **Completion:** After the 6th turn, click **End chat** to generate your session code.

*Please **copy and paste** the generated code back into the survey to complete the study.*
"""

PASSCODE_ENTRY_PROMPT = (
    "Please enter the passcode you received in the survey to begin chatting."
)


# ── Page setup ──────────────────────────────────────────────────────────
st.set_page_config(
    page_title=STUDY_TITLE,
    page_icon="💬",
    layout="centered",
    initial_sidebar_state="collapsed",
)


# ── Session State Initialization ─────────────────────────────────────────────
if "messages" not in st.session_state:
    _use_passcode = N_CONDITIONS > 1 and all("passcode" in c for c in CONDITIONS[:N_CONDITIONS])
    
    st.session_state.update({
        "messages": [{
            "role": "assistant", 
            "content": "Hello there! Close your eyes and scan your last 24 hours like a treasure hunt. What is one small, beautiful moment you noticed?",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }],
        "turn_count": 0,
        "chat_ended": False,
        "confirm_end": False,
        "passcode_accepted": not _use_passcode,
        "condition_index": 0 if not _use_passcode and N_CONDITIONS == 1 else None 
    })
    
    if not _use_passcode and N_CONDITIONS > 1:
        st.session_state["condition_index"] = random.randint(0, N_CONDITIONS - 1)

# ── Main Interface ───────────────────────────────────────────────────────────
st.markdown(f'<h3>💬 {STUDY_TITLE}</h3><hr>', unsafe_allow_html=True)

# ── Stage 1: Passcode Entry ──────────────────────────────────────────────────
if not st.session_state["passcode_accepted"]:
    if WELCOME_MESSAGE:
        st.info(WELCOME_MESSAGE)
    
    with st.form("key_form"):
        _code = st.text_input(PASSCODE_ENTRY_PROMPT).strip().lower()
        if st.form_submit_button("Continue →", type="primary"):
            _passcode_map = {c["passcode"].lower(): i for i, c in enumerate(CONDITIONS[:N_CONDITIONS])}
            if _code in _passcode_map:
                st.session_state.update({"condition_index": _passcode_map[_code], "passcode_accepted": True})
                st.rerun()
            else:
                st.error("Code not recognised. Please check and try again.")
    st.stop()

active_condition = CONDITIONS[st.session_state["condition_index"]]

# ── Stage 2: Active Chat ─────────────────────────────────────────────────────
if not st.session_state["chat_ended"]:
    # Display message history
    for m in st.session_state.messages:
        with st.chat_message(m["role"]):
            st.markdown(m["content"])

    # Chat input logic
    limit_reached = st.session_state.turn_count >= MAX_TURNS
    input_label = "Your thoughts..." if not limit_reached else "Turn limit reached. Please end the chat."
    
    if prompt := st.chat_input(input_label, disabled=limit_reached):
        # Append User Message
        st.session_state.messages.append({
            "role": "user", 
            "content": prompt, 
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        st.session_state.turn_count += 1
        st.rerun()

    # Trigger Assistant Reply if last message was from User
    if st.session_state.messages[-1]["role"] == "user":
        with st.chat_message("assistant"):
            try:
                # Modify system prompt on the final turn to prevent further questions
                current_sys_prompt = active_condition["system_prompt"]
                api_messages = build_api_messages(st.session_state.messages, current_sys_prompt)
                if limit_reached:
                    api_messages[0]["content"] += (
                        "\n\n[MANDATORY] THIS IS THE FINAL TURN. "
                        "Give a very brief 2-3 sentence closing reflection. "
                        "You MUST NOT ask any questions. Summarize and say goodbye naturally."
                    )
                    api_messages[-1]["content"] += (
                        "\n\n(Note to assistant: This is the final response. Please provide a brief 2-3 sentencesummary "
                        "and ending statement without asking futher question.)"
                    )

                payload = {
                    "model": active_condition["model"],
                    "messages": api_messages,
                    "stream": False
                }
                
                response = requests.post(API_BASE_URL + ENDPOINT, headers=HEADERS, json=payload, timeout=30)
                response.raise_for_status()
                content = response.json()["choices"][0]["message"]["content"]
                
                st.session_state.messages.append({
                    "role": "assistant", 
                    "content": content, 
                    "timestamp": datetime.now(timezone.utc).isoformat()
                })
                st.rerun()
            except Exception as e:
                st.error(f"Chat Error: {e}")
                st.session_state.messages.pop()
                st.session_state.turn_count -= 1

    # ── End Button (only shown when turn limit is reached) ──────────────────
    if st.session_state.turn_count >= MAX_TURNS and not st.session_state["chat_ended"]:
        st.write("---")
        if not st.session_state.confirm_end:
            if st.button("End chat", use_container_width=True):
                st.session_state.confirm_end = True
                st.rerun()
        else:
            st.warning("All turns completed. Click below to finalize.")
            if st.button("✓ Confirm & Get Data", type="primary", use_container_width=True):
                st.session_state.chat_ended = True
                st.rerun()

# ── Stage 3: Final Metadata (Privacy-Preserving) ─────────────────────────────
else:
    st.success("Session completed! Your privacy-safe session code has been generated.")
    
    # 1. Generate the anonymized metadata
    safe_data = build_anonymous_metadata(st.session_state.messages)
    
    # 2. Display concise instructions to the participant
    st.markdown("""
        **Next Steps:**
        1. Click the **copy icon** on the box below.
        2. **Paste** the code into the survey to finalize your participation.

        *Note: This code only contains metadata (e.g., message length and tone) to ensure your privacy.*
    """)

    # 3. Show the JSON for the participant to copy
    st.code(json.dumps(safe_data, indent=2), language="json")