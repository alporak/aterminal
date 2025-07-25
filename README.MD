# Teltonika Device Server v2.0

## Overview

This application is a complete rewrite of the original procedural server script. It provides a robust, high-performance TCP/UDP server for managing Teltonika tracking devices, now featuring a user-friendly graphical interface built with PySide6.

The server can handle multiple device connections simultaneously, decode various Teltonika data codecs, manage file transfers (including FOTA updates), and log all activity with high-precision timestamps.

## Features

- **Dual Protocol Support**: Runs as a TCP or UDP server, configurable with a single click.
- **Graphical User Interface**: A simple and intuitive GUI to manage the server, view logs, and interact with devices. No more command-line hassle.
- **Robust Configuration**: All settings are managed in a human-readable `config.json` file. The GUI provides a settings dialog to manage this configuration easily.
- **Device Management**:
    - Automatically detects and lists connected devices by their IMEI.
    - Ability to assign custom names to devices (e.g., "Truck-102").
    - Device names and IMEIs are stored in a local `devices.db` (SQLite) and are remembered across application restarts.
- **Real-time Logging**:
    - Live log view for all server events, connection status, and raw/decoded data packets.
    - Timestamps with millisecond precision for accurate event tracking.
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