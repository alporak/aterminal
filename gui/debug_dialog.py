# gui/debug_dialog.py

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QCheckBox,
    QDoubleSpinBox, QDialogButtonBox, QLabel
)

class DebugDialog(QDialog):
    """A dialog to configure debug settings like response delays."""
    def __init__(self, current_settings, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Debug Settings")

        self.settings = current_settings.copy() # Work on a copy

        layout = QVBoxLayout(self)
        form_layout = QFormLayout()

        # --- Delay Settings ---
        self.delay_imei_check = QCheckBox("Delay IMEI Handshake ACK")
        self.delay_imei_check.setChecked(self.settings.get('delay_imei_ack', 0.0) > 0)

        self.delay_record_check = QCheckBox("Delay Record Data ACK")
        self.delay_record_check.setChecked(self.settings.get('delay_record_ack', 0.0) > 0)

        self.delay_spinbox = QDoubleSpinBox()
        self.delay_spinbox.setSuffix(" seconds")
        self.delay_spinbox.setMinimum(0.0)
        self.delay_spinbox.setMaximum(60.0) # 60-second max delay
        self.delay_spinbox.setSingleStep(0.5)
        # Set value to the first non-zero delay found, or 1.0 as a default
        initial_delay = self.settings.get('delay_imei_ack') or self.settings.get('delay_record_ack') or 1.0
        self.delay_spinbox.setValue(initial_delay)

        form_layout.addRow(self.delay_imei_check)
        form_layout.addRow(self.delay_record_check)
        form_layout.addRow("Delay Duration:", self.delay_spinbox)

        layout.addLayout(form_layout)

        # --- Buttons ---
        button_box = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.save_settings)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def save_settings(self):
        """Updates the settings dictionary based on the dialog's state."""
        delay_value = self.delay_spinbox.value()
        self.settings['delay_imei_ack'] = delay_value if self.delay_imei_check.isChecked() else 0.0
        self.settings['delay_record_ack'] = delay_value if self.delay_record_check.isChecked() else 0.0
        self.accept()

    def get_settings(self):
        """Returns the configured settings."""
        return self.settings