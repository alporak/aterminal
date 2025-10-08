# core/config_manager.py

import json
import os
import sys

# --- MODIFICATION: Helper function to handle paths in dev vs. bundled exe ---
def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)


class ConfigManager:
    """Manages loading and accessing application configuration from a JSON file."""

    def __init__(self, config_path='config.json'):
        # --- MODIFICATION: Use the resource_path helper for the config file ---
        # This makes it look for config.json next to the .exe file
        if getattr(sys, 'frozen', False):
             # If the application is run as a bundle, the config file is expected
             # next to the executable, not in the temp folder.
             self.config_path = os.path.join(os.path.dirname(sys.executable), config_path)
        else:
             # Running from source, so it's in the project root.
             self.config_path = config_path

        self.settings = {}
        self.load_config()

    def load_config(self):
        """Loads the configuration from the JSON file or generates a default one."""
        try:
            # --- MODIFICATION: Use 'r' and handle FileNotFoundError ---
            with open(self.config_path, 'r', encoding='utf-8') as f:
                self.settings = json.load(f)
        except FileNotFoundError:
            print(f"Configuration file not found at {self.config_path}. Generating a new one.")
            self._generate_default_config()


    def _generate_default_config(self):
        """Generates a default config.json file and saves it."""
        print("Creating default configuration...")
        self.settings = {
            "server": {
                "protocol": "tcp",
                "host": "0.0.0.0",
                "port": 9000
            },
            "tls": {
                "enabled": False,
                "root_cert_path": "",
                "key_path": ""
            },
            "device_management": {
                "database_file": "devices.db"
            },
            "logging": {
                "mode": "daily",
                "path": "persistent_log.log"
            },
            "serial_monitor": {
                "last_used_port": "",
                "last_used_baudrate": 115200,
                "auto_scroll_enabled": True,
                "command_history": [],
                "predefined_commands": [
                    { "name": "Get Info", "command": "getinfo" },
                    { "name": "Get Status", "command": "getstatus" }
                ]
            },
            "appearance": {
                "theme": "system",  # Options: "light", "dark", "system"
                "custom_styles": ""
            }
        }
        self.save_config()

    def get(self, key_path, default=None):
        """
        Gets a value from the configuration using a dot-separated path.
        Example: get('server.port')
        """
        try:
            value = self.settings
            for key in key_path.split('.'):
                value = value[key]
            return value
        except (KeyError, TypeError):
            return default

    def save_config(self):
        """Saves the current settings back to the JSON file."""
        try:
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(self.settings, f, indent=4)
        except Exception as e:
            print(f"Error saving configuration file: {e}")


# Create a global instance for easy access across the application
config = ConfigManager()