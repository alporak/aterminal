import sys
import binascii
import struct
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QTextEdit, QListWidget, QListWidgetItem, QLineEdit, QStatusBar, QTabWidget,
    QMessageBox, QFileDialog, QSplitter, QInputDialog, QMenu, QCheckBox, QLabel
)
from PySide6.QtGui import QColor, QAction, QTextCursor, QKeySequence, QTextDocument
from PySide6.QtCore import Qt, Slot
from server.tcp_server import TCPServer
from server.udp_server import UDPServer
from serial_comms.serial_monitor import SerialMonitor
from gui.settings_dialog import SettingsDialog
from gui.debug_dialog import DebugDialog
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
        self.debug_settings = {'delay_imei_ack': 0.0, 'delay_record_ack': 0.0}

        self.setup_ui()
        self.create_actions()
        self.create_menus()

    def setup_ui(self):
        main_widget = QWidget()
        main_layout = QVBoxLayout(main_widget)
        self.setCentralWidget(main_widget)
        splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(splitter)
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        self.device_list_widget = QListWidget()
        left_layout.addWidget(self.device_list_widget)
        self.tabs = QTabWidget()

        # --- Server Log Tab ---
        log_widget = QWidget()
        log_layout = QVBoxLayout(log_widget)
        log_widget.setLayout(log_layout)

        log_controls_layout = QHBoxLayout()
        self.server_log_auto_scroll_check = QCheckBox("Auto Scroll")
        self.server_log_auto_scroll_check.setChecked(True)
        log_controls_layout.addWidget(self.server_log_auto_scroll_check)
        log_controls_layout.addStretch()
        log_layout.addLayout(log_controls_layout)

        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        log_layout.addWidget(self.log_view)

        self.server_search_widget = QWidget()
        search_layout = QHBoxLayout(self.server_search_widget)
        search_layout.setContentsMargins(0, 5, 0, 0)
        self.server_search_input = QLineEdit()
        self.server_search_input.setPlaceholderText("Search log...")
        self.server_search_case_check = QCheckBox("Case Sensitive")
        find_prev_btn = QPushButton("Previous")
        find_next_btn = QPushButton("Next")
        close_search_btn = QPushButton("✕")
        search_layout.addWidget(QLabel("Find:"))
        search_layout.addWidget(self.server_search_input)
        search_layout.addWidget(self.server_search_case_check)
        search_layout.addWidget(find_prev_btn)
        search_layout.addWidget(find_next_btn)
        search_layout.addWidget(close_search_btn)
        log_layout.addWidget(self.server_search_widget)
        self.server_search_widget.hide()

        # Connections for search
        close_search_btn.clicked.connect(self.server_search_widget.hide)
        find_next_btn.clicked.connect(self._find_next_in_server_log)
        find_prev_btn.clicked.connect(self._find_prev_in_server_log)
        self.server_search_input.returnPressed.connect(self._find_next_in_server_log)

        command_layout = QHBoxLayout()
        self.command_input = QLineEdit()
        self.command_input.setPlaceholderText("Select a device and type a command (e.g., getinfo)...")
        self.send_button = QPushButton("Send")
        command_layout.addWidget(self.command_input)
        command_layout.addWidget(self.send_button)
        log_layout.addLayout(command_layout)

        # --- Serial Monitor Tab ---
        self.serial_monitor = SerialMonitor()

        self.tabs.addTab(log_widget, "Server Log")
        self.tabs.addTab(self.serial_monitor, "Serial Monitor")

        splitter.addWidget(left_panel)
        splitter.addWidget(self.tabs)
        splitter.setSizes([250, 950])
        self.setStatusBar(QStatusBar())
        self.status_bar.showMessage("Server stopped.")
        self.send_button.clicked.connect(self.send_command)
        self.device_list_widget.setContextMenuPolicy(Qt.CustomContextMenu)
        self.device_list_widget.customContextMenuRequested.connect(self.open_device_menu)
        self.device_list_widget.itemSelectionChanged.connect(self.update_debug_actions)

    @property
    def status_bar(self):
        return self.statusBar()

    def create_actions(self):
        # File Menu Actions
        self.settings_action = QAction("&Settings...", self)
        self.exit_action = QAction("E&xit", self)
        self.settings_action.triggered.connect(self.open_settings)
        self.exit_action.triggered.connect(self.close)

        self.find_action = QAction("&Find...", self)
        self.find_action.setShortcut(QKeySequence.Find) # Ctrl+F
        self.find_action.triggered.connect(self._toggle_find_widget)

        # Server Options Menu Actions
        self.start_server_action = QAction("Start Server", self)
        self.stop_server_action = QAction("Stop Server", self)
        self.show_config_action = QAction("Show Active Configuration", self)
        self.export_log_action = QAction("Export Log...", self)
        self.clear_log_action = QAction("Clear Log View", self)
        self.start_server_action.triggered.connect(self.start_server)
        self.stop_server_action.triggered.connect(self.stop_server)
        self.show_config_action.triggered.connect(self.show_active_config)
        self.export_log_action.triggered.connect(self.export_log)
        self.clear_log_action.triggered.connect(self.log_view.clear)
        self.stop_server_action.setEnabled(False)

        # Debug Menu Actions
        self.debug_settings_action = QAction("Response Delays...", self)
        self.kick_device_action = QAction("Kick Selected Device", self)
        self.debug_settings_action.triggered.connect(self.open_debug_settings)
        self.kick_device_action.triggered.connect(self.kick_selected_device)
        self.kick_device_action.setEnabled(False)

    def create_menus(self):
        menu_bar = self.menuBar()

        # File Menu
        file_menu = menu_bar.addMenu("&File")
        file_menu.addAction(self.settings_action)
        file_menu.addSeparator()
        file_menu.addAction(self.exit_action)
        
        edit_menu = menu_bar.addMenu("&Edit")
        edit_menu.addAction(self.find_action)

        # Server Options Menu
        server_menu = menu_bar.addMenu("Server Options")
        server_menu.addAction(self.start_server_action)
        server_menu.addAction(self.stop_server_action)
        server_menu.addSeparator()
        server_menu.addAction(self.show_config_action)
        server_menu.addSeparator()
        server_menu.addAction(self.export_log_action)
        server_menu.addAction(self.clear_log_action)

        # Debug Menu
        debug_menu = menu_bar.addMenu("&Debug")
        debug_menu.addAction(self.debug_settings_action)
        debug_menu.addAction(self.kick_device_action)

    def start_server(self):
        protocol = config.get('server.protocol')
        ServerClass = TCPServer if protocol == 'tcp' else UDPServer
        self.server_thread = ServerClass(self.debug_settings)
        self.server_thread.log_message.connect(self.log)
        self.server_thread.device_connected.connect(self.add_device_to_list)
        self.server_thread.device_disconnected.connect(self.remove_device_from_list)
        self.server_thread.data_received.connect(self.handle_data_received)
        self.server_thread.start()
        self.start_server_action.setEnabled(False)
        self.stop_server_action.setEnabled(True)
        self.status_bar.showMessage(f"{protocol.upper()} server running on {config.get('server.host')}:{config.get('server.port')}", 5000)

    def stop_server(self):
        if self.server_thread and self.server_thread.isRunning():
            self.server_thread.stop()
        self.start_server_action.setEnabled(True)
        self.stop_server_action.setEnabled(False)
        self.status_bar.showMessage("Server stopped.")
    def show_active_config(self):
        protocol = config.get('server.protocol')
        host = config.get('server.host')
        port = config.get('server.port')
        QMessageBox.information(self, "Active Server Configuration", f"Protocol: {protocol.upper()}\nHost: {host}\nPort: {port}")

    def update_debug_actions(self):
        is_device_selected = bool(self.device_list_widget.selectedItems())
        self.kick_device_action.setEnabled(is_device_selected)

    def open_debug_settings(self):
        dialog = DebugDialog(self.debug_settings, self)
        if dialog.exec():
            self.debug_settings = dialog.get_settings()
            self.log("Debug settings updated.", "warn")
            if self.server_thread and self.server_thread.isRunning():
                self.server_thread.debug_settings = self.debug_settings

    def kick_selected_device(self):
        current_item = self.device_list_widget.currentItem()
        if not current_item:
            return
        imei = current_item.data(Qt.UserRole)
        if self.server_thread and self.server_thread.isRunning():
            self.server_thread.kick_device(imei)
            
    @Slot(str, str)
    def log(self, message, level="info"):
        scroll_bar = self.log_view.verticalScrollBar()
        # Check if scrollbar is at the bottom before we add text
        is_at_bottom = scroll_bar.value() == scroll_bar.maximum()

        color_map = {"info": "blue", "warn": "orange", "error": "red", "data": "#800080"}
        color = color_map.get(level, "black")
        
        # Use moveCursor and insertHtml instead of append()
        self.log_view.moveCursor(QTextCursor.End)
        self.log_view.insertHtml(f'<font color="{color}">[{gtime()}] {message}</font><br>')

        # Scroll to the bottom only if the checkbox is checked OR if we were already there
        if self.server_log_auto_scroll_check.isChecked() or is_at_bottom:
            scroll_bar.setValue(scroll_bar.maximum())

    @Slot(str, str)
    def add_device_to_list(self, imei, ip):
        if not self.find_device_item(imei):
            display_name = self.device_manager.get_device_name(imei)
            item = QListWidgetItem(f"{display_name} [{imei}]")
            item.setData(Qt.UserRole, imei)
            self.device_list_widget.addItem(item)
        self.log(f"Device connected: {imei} from {ip}", "info")
        self.update_debug_actions()

    @Slot(str)
    def remove_device_from_list(self, imei):
        item = self.find_device_item(imei)
        if item:
            self.device_list_widget.takeItem(self.device_list_widget.row(item))
        self.log(f"Device disconnected: {imei}", "warn")
        self.update_debug_actions()

    @Slot(str, bytes, object)
    def handle_data_received(self, imei, raw_data, decoded_data):
        self.log(f"RX from {imei}: {binascii.hexlify(raw_data).decode().upper()}", "data")
        if decoded_data and 'error' not in decoded_data:
            self.log(f"Decoded: {decoded_data}", "info")
        elif decoded_data and 'error' in decoded_data:
            self.log(f"Decoding failed: {decoded_data['error']}", "error")

    def find_device_item(self, imei):
        for i in range(self.device_list_widget.count()):
            item = self.device_list_widget.item(i)
            if item.data(Qt.UserRole) == imei:
                return item
        return None

    def send_command(self):
        current_item = self.device_list_widget.currentItem()
        if not current_item:
            QMessageBox.warning(self, "No Device Selected", "Please select a device from the list.")
            return
        imei = current_item.data(Qt.UserRole)
        command_str = self.command_input.text()
        if not command_str:
            QMessageBox.warning(self, "No Command", "Please enter a command to send.")
            return
        if self.server_thread and self.server_thread.isRunning():
            self.server_thread.send_command_to_device(imei, command_str)
            self.log(f"TX to {imei}: {command_str}", "data")
            self.command_input.clear()

    def export_log(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export Log", "", "Text Files (*.txt);;All Files (*)")
        if path:
            try:
                with open(path, 'w') as f:
                    f.write(self.log_view.toPlainText())
                self.log(f"Log exported to {path}", "info")
            except Exception as e:
                self.log(f"Failed to export log: {e}", "error")

    def open_settings(self):
        dialog = SettingsDialog(self)
        if dialog.exec():
            self.log("Settings updated. Please restart the server for all changes to take effect.", "warn")

    def open_device_menu(self, position):
        item = self.device_list_widget.itemAt(position)
        if not item:
            return
        menu = QMenu()
        rename_action = menu.addAction("Rename Device")
        action = menu.exec(self.device_list_widget.mapToGlobal(position))
        if action == rename_action:
            self.rename_device(item)

    def rename_device(self, item):
        imei = item.data(Qt.UserRole)
        current_name = self.device_manager.get_device_name(imei)
        new_name, ok = QInputDialog.getText(self, "Rename Device", "Enter new name:", text=current_name if imei != current_name else "")
        if ok and new_name:
            self.device_manager.set_device_name(imei, new_name)
            item.setText(f"{new_name} [{imei}]")
            self.log(f"Device {imei} renamed to '{new_name}'", "info")

    def _toggle_find_widget(self):
        # This function handles the Ctrl+F shortcut and routes it to the correct tab.
        current_tab_widget = self.tabs.currentWidget()
        if current_tab_widget == self.serial_monitor:
            self.serial_monitor.toggle_search_widget()
        else: # Assumes it's the server log tab
            is_visible = self.server_search_widget.isVisible()
            self.server_search_widget.setVisible(not is_visible)
            if not is_visible:
                self.server_search_input.setFocus()
                
    def _find_in_log(self, find_backwards=False):
        text_to_find = self.server_search_input.text()
        if not text_to_find:
            return

        flags = QTextDocument.FindFlag()
        if find_backwards:
            flags |= QTextDocument.FindBackward
        if self.server_search_case_check.isChecked():
            flags |= QTextDocument.FindCaseSensitively

        if not self.log_view.find(text_to_find, flags):
            # If not found, wrap around to the beginning/end
            cursor = self.log_view.textCursor()
            cursor.movePosition(QTextCursor.End if find_backwards else QTextCursor.Start)
            self.log_view.setTextCursor(cursor)
            self.log_view.find(text_to_find, flags)

    def _find_next_in_server_log(self):
        self._find_in_log(find_backwards=False)

    def _find_prev_in_server_log(self):
        self._find_in_log(find_backwards=True)
    
    def closeEvent(self, event):
        self.stop_server()
        self.device_manager.close()
        # Allow serial monitor to save its settings
        self.serial_monitor.save_settings()
        event.accept()