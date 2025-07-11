# gui/main_window.py

import sys
import binascii
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QTextEdit, QListWidget, QListWidgetItem, QLineEdit, QStatusBar,
    QTabWidget, QMessageBox, QFileDialog, QSplitter, QInputDialog, QMenu,
    QPlainTextEdit, QLabel
)
from PySide6.QtGui import QColor, QAction, QFont
from PySide6.QtCore import Qt, Slot
from server.tcp_server import TCPServer
from server.udp_server import UDPServer
from serial_comms.serial_monitor import SerialMonitor
from gui.settings_dialog import SettingsDialog
from core.device_manager import DeviceManager
from core.config_manager import config
from protocols.codec import gtime, decode_packet, encode_codec12_command

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Teltonika Device Server v2.0")
        self.setGeometry(100, 100, 1200, 800)

        self.server_thread = None
        self.device_manager = DeviceManager(config.get('device_management.database_file'))
        self.queued_server_command = None
        self.server_commands = config.get('server_commands', [])
        self.serial_monitor = SerialMonitor()

        self.create_actions()
        self.create_menus()
        self.setup_ui()

    def setup_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)

        top_controls_layout = QHBoxLayout()
        self.start_button = QPushButton("Start Server")
        self.stop_button = QPushButton("Stop Server"); self.stop_button.setEnabled(False)
        top_controls_layout.addWidget(self.start_button); top_controls_layout.addWidget(self.stop_button); top_controls_layout.addStretch()
        main_layout.addLayout(top_controls_layout)

        main_splitter = QSplitter(Qt.Vertical)
        main_layout.addWidget(main_splitter)

        self.tabs = QTabWidget()
        self.log_view = QTextEdit(); self.log_view.setReadOnly(True)
        self.serial_monitor = SerialMonitor()
        self.tabs.addTab(self.log_view, "Server Log"); self.tabs.addTab(self.serial_monitor, "Serial Monitor")

        bottom_panel = QTabWidget()
        self.device_list_widget = QListWidget()
        
        server_cmd_widget = self._create_server_command_panel()

        bottom_panel.addTab(self.device_list_widget, "Connected Devices")
        bottom_panel.addTab(server_cmd_widget, "Server Commands")

        main_splitter.addWidget(self.tabs); main_splitter.addWidget(bottom_panel); main_splitter.setSizes([600, 200])
        self.setStatusBar(QStatusBar()); self.status_bar.showMessage("Server stopped.")

        self.start_button.clicked.connect(self.start_server); self.stop_button.clicked.connect(self.stop_server)
        self.device_list_widget.setContextMenuPolicy(Qt.CustomContextMenu); self.device_list_widget.customContextMenuRequested.connect(self.open_device_menu)
        self.serial_monitor.logging_status_changed.connect(self.update_log_menu_text)

    def _create_server_command_panel(self):
        panel = QWidget(); layout = QVBoxLayout(panel)
        
        splitter = QSplitter(Qt.Horizontal)
        
        predefined_widget = QWidget(); predefined_layout = QVBoxLayout(predefined_widget)
        predefined_layout.addWidget(QLabel("Predefined Commands (Double-click to send)"))
        self.server_cmd_list = QListWidget()
        for cmd in self.server_commands: self.server_cmd_list.addItem(cmd['name'])
        self.server_cmd_list.itemDoubleClicked.connect(self._send_predefined_server_cmd)
        predefined_layout.addWidget(self.server_cmd_list)
        
        predef_btn_layout = QHBoxLayout(); add_btn = QPushButton("Add"); edit_btn = QPushButton("Edit"); del_btn = QPushButton("Del")
        predef_btn_layout.addWidget(add_btn); predef_btn_layout.addWidget(edit_btn); predef_btn_layout.addWidget(del_btn)
        predefined_layout.addLayout(predef_btn_layout)
        
        manual_cmd_widget = QWidget(); manual_cmd_layout = QVBoxLayout(manual_cmd_widget)
        manual_cmd_layout.addWidget(QLabel("Manual Command Entry"))
        self.server_manual_cmd_input = QPlainTextEdit()
        self.server_manual_cmd_input.setFont(QFont("Consolas", 10))
        send_manual_btn = QPushButton("Send Manual Command")
        manual_cmd_layout.addWidget(self.server_manual_cmd_input)
        manual_cmd_layout.addWidget(send_manual_btn)

        splitter.addWidget(predefined_widget); splitter.addWidget(manual_cmd_widget)
        layout.addWidget(splitter)
        
        add_btn.clicked.connect(self._add_server_cmd); edit_btn.clicked.connect(self._edit_server_cmd); del_btn.clicked.connect(self._del_server_cmd)
        send_manual_btn.clicked.connect(self._send_manual_server_cmd)

        return panel

    @property
    def status_bar(self): return self.statusBar()

    def create_actions(self):
        self.export_log_action = QAction("&Export Server Log...", self); self.settings_action = QAction("&Settings...", self); self.exit_action = QAction("E&xit", self)
        self.open_log_action = QAction("&Open Log File", self); self.toggle_logging_action = QAction("&Stop File Logging", self); self.toggle_logging_action.setCheckable(True)

        self.export_log_action.triggered.connect(self.export_log); self.settings_action.triggered.connect(self.open_settings); self.exit_action.triggered.connect(self.close)
        self.open_log_action.triggered.connect(self.serial_monitor.open_current_log_file); self.toggle_logging_action.triggered.connect(self.serial_monitor.toggle_file_logging)

    def create_menus(self):
        menu_bar = self.menuBar()
        file_menu = menu_bar.addMenu("&File"); file_menu.addAction(self.export_log_action); file_menu.addAction(self.settings_action); file_menu.addSeparator(); file_menu.addAction(self.exit_action)
        logs_menu = menu_bar.addMenu("&Logs"); logs_menu.addAction(self.open_log_action); logs_menu.addAction(self.toggle_logging_action)

    @Slot(bool)
    def update_log_menu_text(self, is_logging):
        self.toggle_logging_action.setText("&Stop File Logging" if is_logging else "&Start File Logging")
        self.toggle_logging_action.setChecked(is_logging)

    def start_server(self):
        protocol = config.get('server.protocol'); ServerClass = TCPServer if protocol == 'tcp' else UDPServer
        self.server_thread = ServerClass()
        self.server_thread.log_message.connect(self.log); self.server_thread.device_connected.connect(self.add_device_to_list)
        self.server_thread.device_disconnected.connect(self.remove_device_from_list); self.server_thread.data_received.connect(self.handle_data_received)
        self.server_thread.start(); self.start_button.setEnabled(False); self.stop_button.setEnabled(True)
        self.status_bar.showMessage(f"{protocol.upper()} server running on {config.get('server.host')}:{config.get('server.port')}", 5000)

    def stop_server(self):
        if self.server_thread and self.server_thread.isRunning(): self.server_thread.stop()
        self.start_button.setEnabled(True); self.stop_button.setEnabled(False); self.status_bar.showMessage("Server stopped.")

    @Slot(str, str)
    def log(self, message, level="info"):
        color_map = {"info": "blue", "warn": "orange", "error": "red", "data": "#800080"}
        self.log_view.append(f'<font color="{color_map.get(level, "black")}">[{gtime()}] {message}</font>')

    @Slot(str, str)
    def add_device_to_list(self, imei, ip):
        if not self.find_device_item(imei):
            display_name = self.device_manager.get_device_name(imei)
            item = QListWidgetItem(f"{display_name} [{imei}]"); item.setData(Qt.UserRole, imei)
            self.device_list_widget.addItem(item)
        self.log(f"Device connected: {imei} from {ip}", "info")
        if self.queued_server_command:
            self.log(f"Sending queued command '{self.queued_server_command}' to new device {imei}", "info")
            self.server_thread.send_command_to_device(imei, self.queued_server_command); self.queued_server_command = None

    @Slot(str)
    def remove_device_from_list(self, imei):
        item = self.find_device_item(imei);
        if item: self.device_list_widget.takeItem(self.device_list_widget.row(item))
        self.log(f"Device disconnected: {imei}", "warn")

    @Slot(str, bytes, object)
    def handle_data_received(self, imei, raw_data, decoded_data):
        self.log(f"RX from {imei}: {binascii.hexlify(raw_data).decode().upper()}", "data")
        if decoded_data and 'error' not in decoded_data: self.log(f"Decoded: {decoded_data}", "info")
        elif decoded_data and 'error' in decoded_data: self.log(f"Decoding failed: {decoded_data['error']}", "error")

    def find_device_item(self, imei):
        for i in range(self.device_list_widget.count()):
            item = self.device_list_widget.item(i)
            if item.data(Qt.UserRole) == imei: return item
        return None

    def _send_server_command(self, command_str):
        if not (self.server_thread and self.server_thread.isRunning()):
            QMessageBox.warning(self, "Server Not Running", "Please start the server before sending commands."); return
        
        current_item = self.device_list_widget.currentItem()
        if not current_item:
            self.queued_server_command = command_str
            self.log(f"No device selected. Command '{command_str}' is queued for the next connection.", "warn"); return

        imei = current_item.data(Qt.UserRole)
        self.server_thread.send_command_to_device(imei, command_str); self.log(f"TX to {imei}: {command_str}", "data")

    def _send_manual_server_cmd(self):
        cmd = self.server_manual_cmd_input.toPlainText()
        if cmd: self._send_server_command(cmd)

    def _send_predefined_server_cmd(self, item):
        index = self.server_cmd_list.row(item)
        cmd = self.server_commands[index]['command']; self._send_server_command(cmd)

    def _add_server_cmd(self):
        name, ok = QInputDialog.getText(self, "Add Server Command", "Enter command name:")
        if ok and name:
            command, ok_cmd = QInputDialog.getMultiLineText(self, "Add Command Text", f"Enter command for '{name}':")
            if ok_cmd and command: self.server_commands.append({'name': name, 'command': command}); self.server_cmd_list.addItem(name)

    def _edit_server_cmd(self):
        item = self.server_cmd_list.currentItem()
        if not item: return
        index = self.server_cmd_list.row(item); cmd_obj = self.server_commands[index]
        new_cmd, ok = QInputDialog.getMultiLineText(self, "Edit Server Command", f"Editing '{cmd_obj['name']}':", cmd_obj['command'])
        if ok and new_cmd: self.server_commands[index]['command'] = new_cmd

    def _del_server_cmd(self):
        item = self.server_cmd_list.currentItem()
        if not item: return
        if QMessageBox.question(self, "Delete Server Command", f"Delete '{item.text()}'?") == QMessageBox.Yes:
            index = self.server_cmd_list.row(item); del self.server_commands[index]; self.server_cmd_list.takeItem(index)
            
    def export_log(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export Server Log", "", "Text Files (*.txt);;All Files (*)")
        if path:
            try:
                with open(path, 'w') as f: f.write(self.log_view.toPlainText())
                self.log(f"Server log exported to {path}", "info")
            except Exception as e:
                self.log(f"Failed to export log: {e}", "error")

    def open_settings(self):
        dialog = SettingsDialog(self); dialog.exec()
        self.log("Settings updated. Restart the server for changes to take effect.", "warn")

    def open_device_menu(self, position):
        item = self.device_list_widget.itemAt(position)
        if not item: return
        menu = QMenu(); rename_action = menu.addAction("Rename Device"); action = menu.exec(self.device_list_widget.mapToGlobal(position))
        if action == rename_action: self.rename_device(item)

    def rename_device(self, item):
        imei = item.data(Qt.UserRole); current_name = self.device_manager.get_device_name(imei)
        new_name, ok = QInputDialog.getText(self, "Rename Device", "Enter new name:", text=current_name if imei != current_name else "")
        if ok and new_name:
            self.device_manager.set_device_name(imei, new_name); item.setText(f"{new_name} [{imei}]")
            self.log(f"Device {imei} renamed to '{new_name}'", "info")

    def closeEvent(self, event):
        self.stop_server(); self.device_manager.close(); self.serial_monitor.save_settings()
        config.settings['server_commands'] = self.server_commands; config.save_config()
        event.accept()