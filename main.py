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
    
    st.subheader("📟 AT Command Parser")
    st.write("Extract and analyze modem AT commands from device logs")
    st.write("- Filter specific modem tags")
    st.write("- Clean log output")
    st.write("- Command/response analysis")

with col2:
    st.subheader("🔌 COM Port Unlocker")
    st.write("Identify and kill processes locking COM ports")
    st.write("- Scan for port locks")
    st.write("- Process identification")
    st.write("- Force unlock capability")
    
    st.markdown("")
    
    st.subheader("📊 Easy Catcher")
    st.write("Catcher log analyzer and GPS visualizer")
    st.write("- Parse Catcher logs")
    st.write("- GPS timeline visualization")
    st.write("- Event detection and mapping")
    
    st.markdown("")
    
    st.subheader("⏱️ Jira Time Tracker")
    st.write("Track and visualize your Jira worklogs")
    st.write("- Daily / weekly time view")
    st.write("- Auto-refresh & caching")
    st.write("- Log work directly from the app")

st.markdown("---")

# Quick links
st.markdown("### 🚀 Quick Start")
col1, col2, col3, col4, col5 = st.columns(5)

with col1:
    st.info("**GPS Server**\n\nStart receiving GPS data from Teltonika devices over TCP/UDP.")

with col2:
    st.info("**AT Parser**\n\nUpload device logs to extract modem communication.")

with col3:
    st.info("**COM Unlocker**\n\nFree up locked COM ports for development.")

with col4:
    st.info("**Easy Catcher**\n\nAnalyze Catcher logs with GPS visualization.")

with col5:
    st.info("**Jira Tracker**\n\nView and log your Jira worklogs.")

st.markdown("---")
st.success("👈 **Select a utility from the sidebar to get started**")

# Footer
st.markdown("---")
st.caption("ALPS Toolkit © 2026 | For internal Teltonika development use")
