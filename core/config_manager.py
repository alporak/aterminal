import json
import os

class ConfigManager:
    """Manages loading and accessing application configuration from a JSON file."""

    def __init__(self, config_path='config.json'):
        self.config_path = config_path
        self.settings = {}
        self.load_config()

    def load_config(self):
        """Loads the configuration from the JSON file."""
        if not os.path.exists(self.config_path):
            raise FileNotFoundError(f"Configuration file not found: {self.config_path}")
        
        with open(self.config_path, 'r') as f:
            self.settings = json.load(f)

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
        with open(self.config_path, 'w') as f:
            json.dump(self.settings, f, indent=4)

# Create a global instance for easy access across the application
config = ConfigManager()