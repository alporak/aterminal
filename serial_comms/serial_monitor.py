import sys
import os
import collections
import subprocess
from datetime import datetime
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, QPlainTextEdit, QPushButton, QComboBox,
    QLabel, QListWidget, QListWidgetItem, QSplitter, QDialogButtonBox,
    QInputDialog, QMessageBox, QCheckBox, QLineEdit
)
from PySide6.QtCore import QThread, Signal, QObject, QTimer, Qt, Slot
### FIX 2: Import QTextDocument for search flags ###
from PySide6.QtGui import QFont, QTextCursor, QTextDocument
import serial
import serial.tools.list_ports
from core.config_manager import config

MAX_TERMINAL_BLOCKS = 5000
UPDATE_INTERVAL_MS = 100
COMMAND_HISTORY_SIZE = 50
RECONNECT_INTERVAL_MS = 2000
LOG_DIRECTORY = "logs"

# ... SerialWorker class is unchanged ...
class SerialWorker(QObject):
    data_received = Signal(bytes)
    error_occurred = Signal(str)
    connection_status = Signal(bool)

    def __init__(self, port, baudrate):
        super().__init__()
        self.port = port
        self.baudrate = baudrate
        self.serial_conn = None
        self._is_running = False

    def run(self):
        self._is_running = True
        try:
            self.serial_conn = serial.Serial(self.port, self.baudrate, timeout=0.1)
            self.connection_status.emit(True)
            while self._is_running:
                try:
                    if self.serial_conn.in_waiting > 0:
                        data = self.serial_conn.read(self.serial_conn.in_waiting)
                        self.data_received.emit(data)
                except serial.SerialException as read_error:
                    self.error_occurred.emit(f"Device disconnected: {read_error}")
                    break
        except serial.SerialException as conn_error:
            self.error_occurred.emit(f"Connection failed: {conn_error}")
        finally:
            if self.serial_conn and self.serial_conn.is_open:
                self.serial_conn.close()
            self.connection_status.emit(False)

    def stop(self):
        self._is_running = False

    def send_data(self, data: bytes):
        if self.serial_conn and self.serial_conn.is_open:
            try:
                self.serial_conn.write(data)
            except serial.SerialException as e:
                self.error_occurred.emit(f"TX Error: {e}")


class SerialMonitor(QWidget):
    logging_status_changed = Signal(bool)

    def __init__(self):
        super().__init__()
        self.serial_thread = None
        self.serial_worker = None
        self.log_file = None
        self.current_log_filepath = ""
        self.is_attempting_reconnect = False
        self.user_initiated_disconnect = False
        self.auto_scroll_enabled = config.get('serial_monitor.auto_scroll_enabled', True)

        os.makedirs(LOG_DIRECTORY, exist_ok=True)
        self.command_history = collections.deque(config.get('serial_monitor.command_history', []), maxlen=COMMAND_HISTORY_SIZE)
        self.predefined_commands = config.get('serial_monitor.predefined_commands', [])
        self.rx_buffer = bytearray()
        
        self.update_timer = QTimer(self); self.update_timer.setInterval(UPDATE_INTERVAL_MS); self.update_timer.timeout.connect(self._update_terminal_view)
        self.reconnect_timer = QTimer(self); self.reconnect_timer.setInterval(RECONNECT_INTERVAL_MS); self.reconnect_timer.timeout.connect(self._attempt_reconnect)

        self._setup_ui()
        self._load_ui_data()

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        control_layout = QHBoxLayout()
        self.port_combo = QComboBox(); self.baud_combo = QComboBox(); self.connect_button = QPushButton("Connect")
        self.auto_reconnect_checkbox = QCheckBox("Auto Reconnect"); self.auto_reconnect_checkbox.setChecked(True)
        self.auto_scroll_checkbox = QCheckBox("Auto Scroll")
        self.auto_scroll_checkbox.setChecked(self.auto_scroll_enabled)
        self.clear_button = QPushButton("Clear")
        ### FIX 2: Add a Find button ###
        self.find_button = QPushButton("Find")

        self.refresh_ports()
        self.baud_combo.addItems(['9600', '19200', '38400', '57600', '115200', '921600'])
        last_port = config.get('serial_monitor.last_used_port'); last_baud = str(config.get('serial_monitor.last_used_baudrate', '115200'))
        if last_port: self.port_combo.setCurrentText(last_port)
        if last_baud: self.baud_combo.setCurrentText(last_baud)

        control_layout.addWidget(QLabel("Port:")); control_layout.addWidget(self.port_combo)
        control_layout.addWidget(QLabel("Baudrate:")); control_layout.addWidget(self.baud_combo)
        control_layout.addWidget(self.auto_reconnect_checkbox); control_layout.addWidget(self.auto_scroll_checkbox)
        control_layout.addWidget(self.clear_button)
        ### FIX 2: Add find button to layout ###
        control_layout.addWidget(self.find_button)
        control_layout.addWidget(self.connect_button); control_layout.addStretch()
        main_layout.addLayout(control_layout)

        ### FIX 2 START: Add a hidden search widget ###
        self.search_widget = QWidget()
        search_layout = QHBoxLayout(self.search_widget)
        search_layout.setContentsMargins(0, 0, 0, 5)
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search terminal...")
        self.search_case_check = QCheckBox("Case Sensitive")
        find_prev_btn = QPushButton("Previous")
        find_next_btn = QPushButton("Next")
        close_search_btn = QPushButton("✕")
        search_layout.addWidget(QLabel("Find:"))
        search_layout.addWidget(self.search_input)
        search_layout.addWidget(self.search_case_check)
        search_layout.addWidget(find_prev_btn)
        search_layout.addWidget(find_next_btn)
        search_layout.addWidget(close_search_btn)
        main_layout.addWidget(self.search_widget)
        self.search_widget.hide()
        ### FIX 2 END ###

        main_splitter = QSplitter(Qt.Vertical); main_layout.addWidget(main_splitter)
        self.terminal_view = QTextEdit(); self.terminal_view.setReadOnly(True); self.terminal_view.setFont(QFont("Consolas", 10)); self.terminal_view.setStyleSheet("background-color: #1E1E1E; color: #D4D4D4;")

        bottom_panel = QWidget(); bottom_panel_layout = QHBoxLayout(bottom_panel)
        # ... rest of the UI setup is unchanged ...
        tx_splitter = QSplitter(Qt.Horizontal); bottom_panel_layout.addWidget(tx_splitter)
        predefined_widget = QWidget(); predefined_layout = QVBoxLayout(predefined_widget)
        predefined_layout.addWidget(QLabel("Predefined Commands (Double-click to send)")); self.predefined_list = QListWidget()
        self.predefined_list.itemDoubleClicked.connect(self._send_predefined_command)
        predefined_layout.addWidget(self.predefined_list)
        predef_btn_layout = QHBoxLayout(); self.add_cmd_btn = QPushButton("Add"); self.edit_cmd_btn = QPushButton("Edit"); self.del_cmd_btn = QPushButton("Del")
        predef_btn_layout.addWidget(self.add_cmd_btn); predef_btn_layout.addWidget(self.edit_cmd_btn); predef_btn_layout.addWidget(self.del_cmd_btn)
        predefined_layout.addLayout(predef_btn_layout)

        tx_widget = QWidget(); tx_layout = QVBoxLayout(tx_widget)
        tx_layout.addWidget(QLabel("Command History & Input")); self.history_combo = QComboBox(); self.history_combo.setEditable(False)
        self.history_combo.activated.connect(self._load_history_to_tx); tx_layout.addWidget(self.history_combo)
        self.tx_input = QPlainTextEdit(); self.tx_input.setFont(QFont("Consolas", 10)); tx_layout.addWidget(self.tx_input)

        tx_btn_layout = QHBoxLayout(); self.line_ending_combo = QComboBox(); self.line_ending_combo.addItems(["None", "LF (\\n)", "CR (\\r)", "CRLF (\\r\\n)"])
        self.line_ending_combo.setCurrentIndex(2); self.send_button = QPushButton("Send Command")
        tx_btn_layout.addWidget(QLabel("Line Ending:")); tx_btn_layout.addWidget(self.line_ending_combo); tx_btn_layout.addStretch(); tx_btn_layout.addWidget(self.send_button)
        tx_layout.addLayout(tx_btn_layout)

        tx_splitter.addWidget(predefined_widget); tx_splitter.addWidget(tx_widget); tx_splitter.setSizes([300, 600])
        main_splitter.addWidget(self.terminal_view); main_splitter.addWidget(bottom_panel); main_splitter.setSizes([600, 200])

        self.connect_button.clicked.connect(self.toggle_connection); self.send_button.clicked.connect(self._send_command_from_input)
        self.add_cmd_btn.clicked.connect(self._add_predefined); self.edit_cmd_btn.clicked.connect(self._edit_predefined); self.del_cmd_btn.clicked.connect(self._del_predefined)
        self.clear_button.clicked.connect(self.terminal_view.clear)
        self.auto_scroll_checkbox.stateChanged.connect(self._handle_auto_scroll_checkbox)

        ### FIX 2: Connect search buttons ###
        self.find_button.clicked.connect(self.toggle_search_widget)
        close_search_btn.clicked.connect(self.search_widget.hide)
        find_next_btn.clicked.connect(self._find_next)
        find_prev_btn.clicked.connect(self._find_previous)
        self.search_input.returnPressed.connect(self._find_next)

    @Slot(int)
    def _handle_auto_scroll_checkbox(self, state):
        self.auto_scroll_enabled = (state == Qt.CheckState.Checked)
        config.settings['serial_monitor']['auto_scroll_enabled'] = self.auto_scroll_enabled
        # No need to call save_config here, we can do it once when the app closes.

    # ... (other methods unchanged until _update_terminal_view) ...
    def _load_ui_data(self):
        self.history_combo.addItems(self.command_history)
        for cmd in self.predefined_commands: self.predefined_list.addItem(QListWidgetItem(cmd['name']))
    
    def toggle_connection(self):
        if (self.serial_thread and self.serial_thread.isRunning()) or self.is_attempting_reconnect:
            self.user_initiated_disconnect = True
            self._stop_current_connection()
        else:
            self.user_initiated_disconnect = False
            self._start_new_connection()

    def _start_new_connection(self):
        port = self.port_combo.currentText(); baud = int(self.baud_combo.currentText())
        if not port: self._log_to_terminal("--- No COM port selected ---", "#FFA500"); return
        self.connect_button.setText("Disconnect"); self.is_attempting_reconnect = False
        self.serial_thread = QThread(); self.serial_worker = SerialWorker(port, baud); self.serial_worker.moveToThread(self.serial_thread)
        self.serial_worker.data_received.connect(self._handle_data_received); self.serial_worker.error_occurred.connect(lambda msg: self._log_to_terminal(msg, "#FF4500"))
        self.serial_worker.connection_status.connect(self._handle_connection_status); self.serial_thread.started.connect(self.serial_worker.run); self.serial_thread.start()

    def _stop_current_connection(self):
        self.reconnect_timer.stop()
        if self.serial_worker: self.serial_worker.stop()
        self.connect_button.setText("Connect"); self.is_attempting_reconnect = False

    @Slot(bool)
    def _handle_connection_status(self, is_connected):
        if is_connected:
            self.reconnect_timer.stop(); self.connect_button.setText("Disconnect"); self.is_attempting_reconnect = False
            port = self.port_combo.currentText(); baud = self.baud_combo.currentText()
            self._log_to_terminal(f"--- Connected to {port} at {baud} baud ---", "#00FF7F")
            config.settings['serial_monitor']['last_used_port'] = port; config.settings['serial_monitor']['last_used_baudrate'] = int(baud)
            self.start_file_logging(); self.update_timer.start()
        else:
            self.stop_file_logging(); self.update_timer.stop(); self._update_terminal_view()
            if self.serial_thread: self.serial_thread.quit(); self.serial_thread.wait()
            # Only auto-reconnect if not user-initiated disconnect
            if self.auto_reconnect_checkbox.isChecked() and not self.is_attempting_reconnect and not self.user_initiated_disconnect:
                self.is_attempting_reconnect = True; self.reconnect_timer.start(); self.connect_button.setText("Cancel Reconnect")
                self._log_to_terminal("--- Connection lost. Attempting to reconnect... ---", "#FFA500")
            else:
                self.connect_button.setText("Connect")
            self.user_initiated_disconnect = False

    def _attempt_reconnect(self):
        port_to_find = self.port_combo.currentText()
        if port_to_find in [port.device for port in serial.tools.list_ports.comports()]:
            self._log_to_terminal(f"--- Port {port_to_find} found. Reconnecting... ---", "#00FF7F"); self.reconnect_timer.stop(); self._start_new_connection()

    @Slot(bytes)
    def _handle_data_received(self, data):
        if self.log_file and not self.log_file.closed:
            try: self.log_file.write(data.decode('utf-8', errors='ignore'))
            except Exception: pass
        self.rx_buffer.extend(data)

    ### FIX 1: Modified _update_terminal_view for conditional auto-scrolling ###
    def _update_terminal_view(self):
        if not self.rx_buffer:
            return

        scroll_bar = self.terminal_view.verticalScrollBar()
        is_at_bottom = scroll_bar.value() == scroll_bar.maximum()

        text = self.rx_buffer.decode('utf-8', errors='ignore')
        self.rx_buffer.clear()
        
        # Move cursor to the end to append text
        self.terminal_view.moveCursor(QTextCursor.End)
        self.terminal_view.insertPlainText(text)
        
        if self.terminal_view.document().blockCount() > MAX_TERMINAL_BLOCKS:
            cursor = self.terminal_view.textCursor()
            cursor.movePosition(QTextCursor.Start)
            # This logic correctly selects the first N blocks to be removed
            cursor.movePosition(QTextCursor.Down, QTextCursor.KeepAnchor, self.terminal_view.document().blockCount() - MAX_TERMINAL_BLOCKS)
            cursor.removeSelectedText()

        if self.auto_scroll_enabled or is_at_bottom:
            scroll_bar.setValue(scroll_bar.maximum())

    # ... (file logging methods are unchanged) ...
    def start_file_logging(self):
        self.stop_file_logging()
        self.current_log_filepath = os.path.join(LOG_DIRECTORY, datetime.now().strftime("serial_log_%Y-%m-%d.log"))
        try:
            self.log_file = open(self.current_log_filepath, "a", encoding="utf-8")
            self._log_to_terminal(f"--- Logging to {self.current_log_filepath} ---", "#ADD8E6")
            self.logging_status_changed.emit(True)
        except Exception as e:
            self._log_to_terminal(f"--- Failed to start logging: {e} ---", "#FF4500")

    def stop_file_logging(self):
        if self.log_file and not self.log_file.closed:
            self._log_to_terminal("--- Stopped file logging ---", "#ADD8E6")
            self.log_file.close(); self.log_file = None
            self.logging_status_changed.emit(False)

    def toggle_file_logging(self):
        if self.log_file and not self.log_file.closed: self.stop_file_logging()
        else: self.start_file_logging()
        
    def open_current_log_file(self):
        if not self.current_log_filepath or not os.path.exists(self.current_log_filepath):
            QMessageBox.information(self, "No Log File", "No log file has been created for this session yet.")
            return
        if sys.platform == "win32": os.startfile(self.current_log_filepath)
        else: subprocess.run(['xdg-open', self.current_log_filepath])


    def _send_command(self, command: str):
        if not (self.serial_worker and self.serial_thread.isRunning()):
            QMessageBox.warning(self, "Not Connected", "Please connect to a serial port first."); return
        line_ending_map = {"None": b'', "LF (\\n)": b'\n', "CR (\\r)": b'\r', "CRLF (\\r\\n)": b'\r\\n'}
        line_ending = line_ending_map[self.line_ending_combo.currentText()]; data_to_send = command.encode('utf-8') + line_ending
        self.serial_worker.send_data(data_to_send); self._log_to_terminal(f"TX: {command}", "#87CEFA")
        if command not in self.command_history: self.command_history.appendleft(command); self.history_combo.clear(); self.history_combo.addItems(self.command_history)

    # ... (_send_command_from_input, etc. are unchanged) ...
    def _send_command_from_input(self):
        self._send_command(self.tx_input.toPlainText())

    def _send_predefined_command(self, item: QListWidgetItem):
        index = self.predefined_list.row(item)
        command = self.predefined_commands[index]['command']
        self._send_command(command)

    def _load_history_to_tx(self, index):
        self.tx_input.setPlainText(self.history_combo.itemText(index))
        
    def _add_predefined(self):
        name, ok = QInputDialog.getText(self, "Add Command", "Enter a name for the command:")
        if ok and name:
            command, ok_cmd = QInputDialog.getMultiLineText(self, "Add Command Text", f"Enter command for '{name}':")
            if ok_cmd and command: self.predefined_commands.append({'name': name, 'command': command}); self.predefined_list.addItem(QListWidgetItem(name))
            elif ok_cmd: QMessageBox.warning(self, "Empty Command", "Cannot save an empty command.")

    def _edit_predefined(self):
        current_item = self.predefined_list.currentItem();
        if not current_item: return
        index = self.predefined_list.row(current_item); cmd_obj = self.predefined_commands[index]
        new_cmd, ok = QInputDialog.getMultiLineText(self, "Edit Command", f"Editing '{cmd_obj['name']}':", cmd_obj['command'])
        if ok and new_cmd: self.predefined_commands[index]['command'] = new_cmd

    def _del_predefined(self):
        current_item = self.predefined_list.currentItem()
        if not current_item: return
        if QMessageBox.question(self, "Delete Command", f"Are you sure you want to delete '{current_item.text()}'?") == QMessageBox.Yes:
            index = self.predefined_list.row(current_item); del self.predefined_commands[index]; self.predefined_list.takeItem(index)

    ### FIX 1: Modified _log_to_terminal to fix unconditional auto-scrolling ###
    def _log_to_terminal(self, message: str, color: str):
        scroll_bar = self.terminal_view.verticalScrollBar()
        is_at_bottom = scroll_bar.value() == scroll_bar.maximum()

        self.terminal_view.moveCursor(QTextCursor.End)
        # Using insertHtml instead of appendHtml gives us control over scrolling
        self.terminal_view.insertHtml(f'<font color="{color}">{message}</font><br>')

        if self.auto_scroll_enabled or is_at_bottom:
            scroll_bar.setValue(scroll_bar.maximum())

    ### FIX 2 START: Methods for search functionality ###
    def toggle_search_widget(self):
        is_visible = self.search_widget.isVisible()
        self.search_widget.setVisible(not is_visible)
        if not is_visible:
            self.search_input.setFocus()

    def _find(self, find_backwards=False):
        text_to_find = self.search_input.text()
        if not text_to_find:
            return

        flags = QTextDocument.FindFlag()
        if find_backwards:
            flags |= QTextDocument.FindBackward
        if self.search_case_check.isChecked():
            flags |= QTextDocument.FindCaseSensitively
            
        # find() returns True if found, False otherwise
        if not self.terminal_view.find(text_to_find, flags):
            # If not found, wrap around to the beginning/end to search again
            cursor = self.terminal_view.textCursor()
            cursor.movePosition(QTextCursor.End if find_backwards else QTextCursor.Start)
            self.terminal_view.setTextCursor(cursor)
            # Try one more time from the wrapped position
            self.terminal_view.find(text_to_find, flags)

    def _find_next(self):
        self._find(find_backwards=False)

    def _find_previous(self):
        self._find(find_backwards=True)
    ### FIX 2 END ###

    def save_settings(self):
        config.settings['serial_monitor']['command_history'] = list(self.command_history)
        config.settings['serial_monitor']['predefined_commands'] = self.predefined_commands
        config.settings['serial_monitor']['auto_scroll_enabled'] = self.auto_scroll_enabled
        config.save_config()

    def refresh_ports(self):
        """Refresh the list of available serial ports in the port_combo UI element."""
        current_port = self.port_combo.currentText()
        self.port_combo.clear()
        ports = serial.tools.list_ports.comports()
        for port in ports:
            self.port_combo.addItem(port.device)
        
        # Try to restore the previously selected port
        if current_port and self.port_combo.findText(current_port) != -1:
            self.port_combo.setCurrentText(current_port)