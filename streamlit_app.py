"""
Alp's Toolkit - Main Entry Point
"""

import streamlit as st
import random
from datetime import datetime

# Page config
st.set_page_config(
    page_title="Alp's Toolkit",
    page_icon="🛠️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- Greeting based on time of day ---
hour = datetime.now().hour
if hour < 6:
    greeting = "You're up at this hour? Respect. ☕"
elif hour < 9:
    greeting = "Morning, Alp. Let's pretend we're productive."
elif hour < 12:
    greeting = "The morning is still young. Plenty of time to break things."
elif hour < 14:
    greeting = "Lunch-adjacent coding. Bold strategy."
elif hour < 17:
    greeting = "Afternoon shift. The bugs aren't going to fix themselves."
elif hour < 20:
    greeting = "Still here? Dedication or denial — either way, respect."
else:
    greeting = "Late night session. Tomorrow's problems are tonight's features."

st.title("🛠️ Alp's Toolkit")
st.caption(greeting)

st.markdown("---")

# --- Tool cards: compact, with a personality ---
tools = [
    ("📡", "GPS Server",       "Listen to devices scream their coordinates into the void"),
    ("🔍", "Log Parser",       "Turn wall-of-text logs into something a human can read"),
    ("🔌", "COM Unlocker",     "Evict whatever is squatting on your COM port"),
    ("⏱️", "Jira Tracker",     "Proof you actually worked today"),
    ("🚀", "Release Creator",  "Ship it before QA finds out"),
]

cols = st.columns(len(tools))
for col, (icon, name, tagline) in zip(cols, tools):
    with col:
        st.markdown(
            f"""
            <div style="
                border: 1px solid #333;
                border-radius: 12px;
                padding: 1.2rem 1rem;
                text-align: center;
                height: 180px;
                display: flex;
                flex-direction: column;
                justify-content: center;
            ">
                <div style="font-size: 2rem;">{icon}</div>
                <div style="font-weight: 600; font-size: 1rem; margin: 0.4rem 0;">{name}</div>
                <div style="font-size: 0.8rem; opacity: 0.7;">{tagline}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

st.markdown("")

# --- Random tip / fortune ---
tips = [
    "💡 Pro tip: If you stare at a log file long enough, the bug stares back.",
    "💡 Remember: It worked on my machine™ is a valid deployment strategy.",
    "💡 If the GPS says you're in the ocean, the GPS is probably right. Move.",
    "💡 COM ports are like parking spots — always taken when you need one.",
    "💡 Jira hours logged ≠ hours worked. We all know this.",
    "💡 The firmware is not broken. It's just… differently functional.",
    "💡 AT+CSQ returns 99,99? That's not signal. That's a cry for help.",
    "💡 Never push on a Friday. Unless you enjoy weekend debugging.",
    "💡 Sleep mode works. Except when you're watching. Then it doesn't.",
    "💡 Every release is a hotfix if you're fast enough.",
    "💡 If it compiles, ship it. If it doesn't, ship it anyway — it builds character.",
    "💡 The real firmware was the friends we bricked along the way.",
    "💡 Fun fact: 90% of debugging is re-reading the same log line 47 times.",
]

st.info(random.choice(tips))

# --- Sidebar signature ---
st.sidebar.markdown("---")
st.sidebar.caption("Alp's Toolkit © 2026 — Built with spite and Streamlit.")
