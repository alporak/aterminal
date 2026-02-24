"""
ALPS Toolkit - Main Entry Point
A collection of utilities for Teltonika device development
"""

import streamlit as st

# Page config
st.set_page_config(
    page_title="Alp's Toolkit",
    page_icon="🛠️",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.title("🛠️ ALPS Toolkit")
st.markdown("### A collection of utilities for Teltonika device development")

st.markdown("---")

# Create columns for utility cards
col1, col2 = st.columns(2)

with col1:
    st.subheader("📡 GPS Server")
    st.write("Real-time Teltonika GPS data receiver and command sender")
    st.write("- TCP/UDP server for device connections")
    st.write("- Live data monitoring and visualization")
    st.write("- Command scheduling and testing")
    
    st.markdown("")
    
    st.subheader("� Log Parser")
    st.write("Combined AT parser, signal analyzer, and device state tracker")
    st.write("- AT command / response flow")
    st.write("- GSM signal, operator, network tracking")
    st.write("- State timeline: sleep, trip, record sending")
    st.write("- GPS route visualization")

with col2:
    st.subheader("🔌 COM Port Unlocker")
    st.write("Identify and kill processes locking COM ports")
    st.write("- Scan for port locks")
    st.write("- Process identification")
    st.write("- Force unlock capability")
    
    st.markdown("")
    
    st.subheader("⏱️ Jira Time Tracker")
    st.write("Track and visualize your Jira worklogs")
    st.write("- Daily / weekly time view")
    st.write("- Auto-refresh & caching")
    st.write("- Log work directly from the app")

st.markdown("---")

# Quick links
st.markdown("### 🚀 Quick Start")
col1, col2, col3, col4 = st.columns(4)

with col1:
    st.info("**GPS Server**\n\nStart receiving GPS data from Teltonika devices over TCP/UDP.")

with col2:
    st.info("**Log Parser**\n\nUpload logs to analyze AT commands, signal, and device states.")

with col3:
    st.info("**COM Unlocker**\n\nFree up locked COM ports for development.")

with col4:
    st.info("**Jira Tracker**\n\nView and log your Jira worklogs.")

st.markdown("---")
st.success("👈 **Select a utility from the sidebar to get started**")

# Footer
st.markdown("---")
st.caption("ALPS Toolkit © 2026 | For internal Teltonika development use")
