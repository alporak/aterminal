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