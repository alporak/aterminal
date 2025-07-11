# serial_comms/serial_monitor.py

import sys
import os
import collections
import subprocess
from datetime import datetime
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPlainTextEdit, QPushButton, QComboBox,
    QLabel, QListWidget, QListWidgetItem, QSplitter, QDialogButtonBox,
    QInputDialog, QMessageBox, QCheckBox
)
from PySide6.QtCore import QThread, Signal, QObject, QTimer, Qt, Slot
from PySide6.QtGui import QFont, QTextCursor
import serial
import serial.tools.list_ports
from core.config_manager import config

MAX_TERMINAL_BLOCKS = 5000
UPDATE_INTERVAL_MS = 100
COMMAND_HISTORY_SIZE = 50
RECONNECT_INTERVAL_MS = 2000
LOG_DIRECTORY = "logs"

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
        self.auto_scroll_enabled = True

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
        self.auto_scroll_checkbox = QCheckBox("Auto Scroll"); self.auto_scroll_checkbox.setChecked(True)
        self.clear_button = QPushButton("Clear")

        self.refresh_ports()
        self.baud_combo.addItems(['9600', '19200', '38400', '57600', '115200', '921600'])
        last_port = config.get('serial_monitor.last_used_port'); last_baud = str(config.get('serial_monitor.last_used_baudrate', '115200'))
        if last_port: self.port_combo.setCurrentText(last_port)
        if last_baud: self.baud_combo.setCurrentText(last_baud)

        control_layout.addWidget(QLabel("Port:")); control_layout.addWidget(self.port_combo)
        control_layout.addWidget(QLabel("Baudrate:")); control_layout.addWidget(self.baud_combo)
        control_layout.addWidget(self.auto_reconnect_checkbox); control_layout.addWidget(self.auto_scroll_checkbox)
        control_layout.addWidget(self.clear_button); control_layout.addWidget(self.connect_button); control_layout.addStretch()
        main_layout.addLayout(control_layout)

        main_splitter = QSplitter(Qt.Vertical); main_layout.addWidget(main_splitter)
        self.terminal_view = QPlainTextEdit(); self.terminal_view.setReadOnly(True); self.terminal_view.setFont(QFont("Consolas", 10)); self.terminal_view.setStyleSheet("background-color: #1E1E1E; color: #D4D4D4;")

        bottom_panel = QWidget(); bottom_panel_layout = QHBoxLayout(bottom_panel)
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

    @Slot(int)
    def _handle_auto_scroll_checkbox(self, state):
        self.auto_scroll_enabled = (state == Qt.Checked)

    def _load_ui_data(self):
        self.history_combo.addItems(self.command_history)
        for cmd in self.predefined_commands: self.predefined_list.addItem(QListWidgetItem(cmd['name']))
    
    def toggle_connection(self):
        if (self.serial_thread and self.serial_thread.isRunning()) or self.is_attempting_reconnect:
            self._stop_current_connection()
        else:
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
            if self.auto_reconnect_checkbox.isChecked() and not self.is_attempting_reconnect: # check prevents double start
                self.is_attempting_reconnect = True; self.reconnect_timer.start(); self.connect_button.setText("Cancel Reconnect")
                self._log_to_terminal("--- Connection lost. Attempting to reconnect... ---", "#FFA500")
            else:
                self.connect_button.setText("Connect")

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

    def _update_terminal_view(self):
        if not self.rx_buffer:
            return
        text = self.rx_buffer.decode('utf-8', errors='ignore')
        self.rx_buffer.clear()
        cursor = self.terminal_view.textCursor()
        cursor.movePosition(QTextCursor.End)
        self.terminal_view.setTextCursor(cursor)
        # Ensure RX data ends with a newline
        if not text.endswith('\n'):
            text += '\n'
        self.terminal_view.insertPlainText(text)
        if self.terminal_view.blockCount() > MAX_TERMINAL_BLOCKS:
            cursor.movePosition(QTextCursor.Start)
            cursor.movePosition(QTextCursor.Down, QTextCursor.KeepAnchor, self.terminal_view.blockCount() - MAX_TERMINAL_BLOCKS)
            cursor.removeSelectedText()
        if self.auto_scroll_enabled:
            self.terminal_view.verticalScrollBar().setValue(self.terminal_view.verticalScrollBar().maximum())

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

    def _log_to_terminal(self, message: str, color: str):
        # Ensure every log entry starts on a new line
        self.terminal_view.appendHtml(f'<font color="{color}">{message}</font><br>')

    def save_settings(self):
        config.settings['serial_monitor']['command_history'] = list(self.command_history)
        config.settings['serial_monitor']['predefined_commands'] = self.predefined_commands
        config.save_config()

    def refresh_ports(self):
        """Refresh the list of available serial ports in the port_combo UI element."""
        self.port_combo.clear()
        ports = serial.tools.list_ports.comports()
        for port in ports:
            self.port_combo.addItem(port.device)