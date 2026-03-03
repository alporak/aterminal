# 🛠️ ALPS Toolkit

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
    ```bash
    git clone <http://your-repo-url>
    cd alps-toolkit
    ```

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
*Built with Streamlit & Spite.*

    - Color-coded logs for different event types (Info, Warning, Error, Data).
- **Log Export**: Easily export the entire session log to a text file for archival or analysis.
- **Serial Port Monitor**: A built-in terminal to monitor any local serial (COM) port, useful for debugging hardware or connected peripherals.
- **Feature Parity**: Includes all major functionalities from the original script, including:
    - Codec 8, 12, 13, 14, 17, 34, 36 and other decoders.
    - File transfers to/from devices (TM25, FMB_UPL, etc.).
    - FotaWeb integration support.
    - GPRS command sending.
- **Extensible Architecture**: The code is now object-oriented and modular, making it easier to add support for new codecs or custom features in the future.

## Project Structure

The project is organized into a modular structure for clarity and maintainability:

```
.
├── core/                    # Core backend functionality
│   ├── config_manager.py    # Handles loading/saving configuration
│   └── device_manager.py    # Manages device connections and states
├── gui/                     # User interface components
│   ├── debug_dialog.py      # Debug information dialog
│   ├── main_window.py       # Main application window
│   └── settings_dialog.py   # Configuration settings dialog
├── protocols/               # Protocol implementations
│   └── codec.py             # Teltonika codec implementations
├── serial_comms/            # Serial communication functionality
│   └── serial_monitor.py    # Monitors and logs serial port data
├── server/                  # Server implementation
│   ├── tcp_server.py        # TCP server implementation
│   └── udp_server.py        # UDP server implementation
├── conn_logs/               # Connection log storage
├── logs/                    # Application log storage
├── server_logs/             # Server events log storage
├── main.py                  # Application entry point
├── config.json              # Application configuration
└── devices.db               # SQLite database for device storage
```

## Installation

### Method 1: Using the Pre-built Executable

1. Download the latest release from the [Releases page](https://github.com/alporak/aterminal/releases).
2. Extract the ZIP file.
3. Run `aterminal.exe` to start the application.

### Method 2: Running from Source

1. Clone this repository:
   ```
   git clone https://github.com/alporak/aterminal.git
   cd aterminal
   ```

2. Install the required dependencies:
   ```
   pip install -r requirements.txt
   ```

3. Run the application:
   ```
   python main.py
   ```

## Usage

1. Start the application.
2. Choose the protocol (TCP or UDP) from the interface.
3. Configure the listening port through the Settings dialog.
4. Click "Start Server" to begin listening for device connections.
5. Connected devices will appear in the devices list with their IMEIs.
6. View real-time logs in the main window.
7. Use the Serial Monitor feature to observe data on serial ports when needed.

## Building from Source

To build the executable yourself:

1. Install PyInstaller:
   ```
   pip install pyinstaller
   ```

2. Build using the provided spec file:
   ```
   pyinstaller aterminal.spec --noconfirm
   ```

3. The executable will be created in the `dist/aterminal/` directory.

## Development

### Adding a New Codec

1. Add your codec implementation to `protocols/codec.py`.
2. Register the codec in the codec factory.
3. Test with appropriate device data.

### Modifying the GUI

The application uses PySide6 for the GUI. The main interface components are found in the `gui/` directory.

## Troubleshooting

### Executable Won't Start

If the executable fails to start:

1. **Missing DLLs**: Ensure you have the Visual C++ Redistributable for Visual Studio 2019 installed. You can download it from the [Microsoft website](https://support.microsoft.com/en-us/help/2977003/the-latest-supported-visual-c-downloads).

2. **Config File Missing**: Make sure `config.json` is in the same directory as the executable.

3. **Antivirus Blocking**: Some antivirus software may block the application. Try adding an exception for `aterminal.exe`.

4. **Run as Administrator**: Right-click on the executable and select "Run as Administrator".

### Runtime Errors

1. **Port Already in Use**: If you receive an error about the port being already in use, ensure no other application is using the same port or change the listening port in the Settings dialog.

2. **Database Errors**: If you encounter database errors, try deleting `devices.db` and restarting the application (this will reset your saved devices).

3. **Log Directory Permissions**: Make sure the application has write permissions to the `logs/`, `conn_logs/`, and `server_logs/` directories.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.