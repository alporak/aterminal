# gui/settings_dialog.py

from PySide6.QtWidgets import (QDialog, QVBoxLayout, QFormLayout, QLineEdit, 
                             QPushButton, QComboBox, QCheckBox, QDialogButtonBox)
from core.config_manager import config

class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        
        layout = QVBoxLayout(self)
        form_layout = QFormLayout()

        # Server Settings
        self.protocol_combo = QComboBox()
        self.protocol_combo.addItems(["tcp", "udp"])
        self.protocol_combo.setCurrentText(config.get('server.protocol'))
        
        self.host_input = QLineEdit(config.get('server.host'))
        self.port_input = QLineEdit(str(config.get('server.port')))
        
        form_layout.addRow("Protocol:", self.protocol_combo)
        form_layout.addRow("Host IP:", self.host_input)
        form_layout.addRow("Port:", self.port_input)
        
        # File Transfer Settings
        self.ft_mode_input = QLineEdit(config.get('file_transfer.mode'))
        self.ft_path_input = QLineEdit(config.get('file_transfer.file_path'))
        
        form_layout.addRow("File Transfer Mode:", self.ft_mode_input)
        form_layout.addRow("File Path:", self.ft_path_input)

        layout.addLayout(form_layout)
        
        # --- Buttons ---
        button_box = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.save_settings)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def save_settings(self):
        """Saves the settings from the dialog back to the config object."""
        config.settings['server']['protocol'] = self.protocol_combo.currentText()
        config.settings['server']['host'] = self.host_input.text()
        config.settings['server']['port'] = int(self.port_input.text())
        
        config.settings['file_transfer']['mode'] = self.ft_mode_input.text()
        config.settings['file_transfer']['file_path'] = self.ft_path_input.text()
        
        config.save_config()
        self.accept()