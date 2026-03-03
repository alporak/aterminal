from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QLineEdit,
    QPushButton, QComboBox, QCheckBox, QDialogButtonBox,
    QGroupBox, QFileDialog, QHBoxLayout
)
from core.config_manager import config
import os

class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumWidth(450)

        layout = QVBoxLayout(self)

        # --- Server Settings Group ---
        server_group = QGroupBox("Server Settings")
        server_layout = QFormLayout(server_group)
        self.protocol_combo = QComboBox()
        self.protocol_combo.addItems(["tcp", "udp"])
        self.protocol_combo.setCurrentText(config.get('server.protocol'))
        self.host_input = QLineEdit(config.get('server.host'))
        self.port_input = QLineEdit(str(config.get('server.port')))
        server_layout.addRow("Protocol:", self.protocol_combo)
        server_layout.addRow("Host IP:", self.host_input)
        server_layout.addRow("Port:", self.port_input)

        # --- TLS Settings Group ---
        tls_group = QGroupBox("TLS Settings (TCP Only)")
        tls_layout = QFormLayout(tls_group)
        self.tls_enabled_check = QCheckBox("Enable TLS")
        self.tls_enabled_check.setChecked(config.get('tls.enabled', False))
        self.tls_enabled_check.toggled.connect(self.toggle_tls_fields)
        self.tls_cert_path_input = QLineEdit(config.get('tls.root_cert_path'))
        self.tls_key_path_input = QLineEdit(config.get('tls.key_path'))
        tls_layout.addRow(self.tls_enabled_check)
        tls_layout.addRow("Certificate File:", self.tls_cert_path_input)
        tls_layout.addRow("Private Key File:", self.tls_key_path_input)

        # --- MODIFICATION: Server Logging Settings Group ---
        log_group = QGroupBox("Server File Logging")
        log_layout = QFormLayout(log_group)
        
        self.log_mode_combo = QComboBox()
        self.log_mode_combo.addItems(["daily", "session", "persistent"])
        self.log_mode_combo.setCurrentText(config.get('logging.mode', 'daily'))
        self.log_mode_combo.currentTextChanged.connect(self.toggle_log_path_field)
        
        self.log_path_input = QLineEdit(config.get('logging.path', 'persistent_log.log'))
        self.log_browse_button = QPushButton("Browse...")
        self.log_browse_button.clicked.connect(self.browse_log_file)
        
        path_layout = QHBoxLayout()
        path_layout.addWidget(self.log_path_input)
        path_layout.addWidget(self.log_browse_button)
        
        log_layout.addRow("Log Mode:", self.log_mode_combo)
        log_layout.addRow("Persistent Log File:", path_layout)
        
        # --- Appearance Settings Group ---
        appearance_group = QGroupBox("Appearance")
        appearance_layout = QFormLayout(appearance_group)
        
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["system", "light", "dark"])
        self.theme_combo.setCurrentText(config.get('appearance.theme', 'system'))
        
        appearance_layout.addRow("Theme:", self.theme_combo)
        
        # Add groups to the main layout
        layout.addWidget(server_group)
        layout.addWidget(tls_group)
        layout.addWidget(log_group)
        layout.addWidget(appearance_group)

        # --- Buttons ---
        button_box = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.save_settings)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        # Initial states
        self.toggle_tls_fields(self.tls_enabled_check.isChecked())
        self.protocol_combo.currentTextChanged.connect(self.update_tls_group_state)
        self.update_tls_group_state(self.protocol_combo.currentText())
        self.toggle_log_path_field(self.log_mode_combo.currentText())

    def update_tls_group_state(self, protocol):
        is_tcp = (protocol == 'tcp')
        self.tls_enabled_check.parent().setEnabled(is_tcp)
        if not is_tcp:
            self.tls_enabled_check.setChecked(False)

    def toggle_tls_fields(self, checked):
        self.tls_cert_path_input.setEnabled(checked)
        self.tls_key_path_input.setEnabled(checked)

    # MODIFICATION: New method to manage log setting UI
    def toggle_log_path_field(self, mode):
        is_persistent = (mode == 'persistent')
        self.log_path_input.setEnabled(is_persistent)
        self.log_browse_button.setEnabled(is_persistent)

    # MODIFICATION: New method for browsing for a log file
    def browse_log_file(self):
        path, _ = QFileDialog.getSaveFileName(self, "Select Persistent Log File", self.log_path_input.text(), "Log Files (*.log *.txt);;All Files (*)")
        if path:
            self.log_path_input.setText(path)

    def save_settings(self):
        # Server
        config.settings['server']['protocol'] = self.protocol_combo.currentText()
        config.settings['server']['host'] = self.host_input.text()
        config.settings['server']['port'] = int(self.port_input.text())

        # TLS
        config.settings['tls']['enabled'] = self.tls_enabled_check.isChecked()
        config.settings['tls']['root_cert_path'] = self.tls_cert_path_input.text()
        config.settings['tls']['key_path'] = self.tls_key_path_input.text()
        
        # MODIFICATION: Save logging settings
        if 'logging' not in config.settings:
            config.settings['logging'] = {}
        config.settings['logging']['mode'] = self.log_mode_combo.currentText()
        config.settings['logging']['path'] = self.log_path_input.text()
        
        # Save appearance settings
        if 'appearance' not in config.settings:
            config.settings['appearance'] = {}
        config.settings['appearance']['theme'] = self.theme_combo.currentText()

        config.save_config()
        self.accept()