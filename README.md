# 🛠️ Alp's Toolkit

A collection of utilities for Teltonika device development, built with Streamlit and good intentions.

## Features

### 📡 GPS Server
- Real-time TCP/UDP listener for Teltonika GPS devices (Codec 8/8E/12/13).
- Live data feed with auto-refresh (no full page reload).
- Parsing of AVL IDs, IO elements, and raw hex (with color-coded breakdown).
- Command sending (TCP/UDP) with queueing.

### 🔍 Log Parser
- Parse `Teltonika Catcher` logs (.clg, .txt) and device dumps.
- Visual timeline of connection events, record sending, and errors.
- Extract AT commands and modem responses.
- Map visualization of GPS points from logs.

### 🔌 COM Unlocker
- Identify which process is locking your COM port.
- Kill the locking process directly from the UI.
- Restart the device driver if the port is stuck in kernel limbo.

### ⏱️ Jira Tracker
- Log work to Jira tickets efficiently.
- "Standup" mode: quickly log meeting times.
- View daily/weekly progress bars.
- Open local folders associated with tickets.

### 🚀 Release Creator
- Wizard for creating new Firmware versions in Jira.
- Auto-generates release tickets with proper version links.
- Handles standard Release vs Revision workflows.

## Installation

1.  **Clone the repository**:

2.  **Install dependencies**:
    ```bash
    pip install -r requirements.txt
    ```

## Usage

### Option 1: System Tray (Windows)
Run the script to start the toolkit in the background with a system tray icon:
```bash
python streamlit_tray.py
```
Or double-click `start_Home_hidden.vbs`.

### Option 2: Direct Launch
Run Streamlit directly in your terminal:
```bash
streamlit run Home.py
```
Or double-click `start_Home.bat`.

## Configuration
- **GPS Server**: Config is stored in `toolkit_settings.json` (auto-created).
- **Jira**: Credentials are stored in `jira-time-tracker/jira_config.json`.

---
