# serial_comms/serial_monitor.py

import sys
import collections
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPlainTextEdit, QPushButton, QComboBox,
    QLabel, QListWidget, QListWidgetItem, QSplitter, QDialog, QDialogButtonBox,
    QInputDialog, QMessageBox
)
from PySide6.QtCore import QThread, Signal, QObject, QTimer, Qt, Slot
from PySide6.QtGui import QTextCursor, QFont
import serial
import serial.tools.list_ports
from core.config_manager import config

# --- Configuration ---
MAX_TERMINAL_BLOCKS = 5000  # Max lines in terminal to prevent memory hog
UPDATE_INTERVAL_MS = 100    # Update GUI every 100ms to batch incoming data
COMMAND_HISTORY_SIZE = 50   # Store last 50 commands

class SerialWorker(QObject):
    """
    Handles all serial communication in a separate thread to keep the GUI responsive.
    """
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
        """Connects and continuously reads from the serial port."""
        self._is_running = True
        try:
            self.serial_conn = serial.Serial(self.port, self.baudrate, timeout=0.1)
            self.connection_status.emit(True)
            while self._is_running:
                if self.serial_conn.in_waiting > 0:
                    data = self.serial_conn.read(self.serial_conn.in_waiting)
                    self.data_received.emit(data)
        except serial.SerialException as e:
            self.error_occurred.emit(f"Serial error: {e}")
        finally:
            if self.serial_conn and self.serial_conn.is_open:
                self.serial_conn.close()
            self.connection_status.emit(False)

    def stop(self):
        """Stops the reading loop."""
        self._is_running = False

    def send_data(self, data: bytes):
        """Writes data to the serial port."""
        if self.serial_conn and self.serial_conn.is_open:
            self.serial_conn.write(data)


class SerialMonitor(QWidget):
    """
    High-performance serial terminal widget with advanced TX/RX features.
    """
    def __init__(self):
        super().__init__()
        self.serial_thread = None
        self.serial_worker = None

        self.command_history = collections.deque(
            config.get('serial_monitor.command_history', []),
            maxlen=COMMAND_HISTORY_SIZE
        )
        self.predefined_commands = config.get('serial_monitor.predefined_commands', [])

        # --- Optimized RX Buffer ---
        self.rx_buffer = bytearray()
        self.update_timer = QTimer(self)
        self.update_timer.setInterval(UPDATE_INTERVAL_MS)
        self.update_timer.timeout.connect(self._update_terminal_view)

        self._setup_ui()
        self._load_ui_data()

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)

        # --- Top Controls ---
        control_layout = QHBoxLayout()
        self.port_combo = QComboBox()
        self.baud_combo = QComboBox()
        self.connect_button = QPushButton("Connect")

        ports = serial.tools.list_ports.comports()
        self.port_combo.addItems([port.device for port in ports])
        self.baud_combo.addItems(['9600', '19200', '38400', '57600', '115200', '921600'])
        self.baud_combo.setCurrentText(str(config.get('serial_monitor.default_baudrate', '115200')))

        control_layout.addWidget(QLabel("Port:"))
        control_layout.addWidget(self.port_combo)
        control_layout.addWidget(QLabel("Baudrate:"))
        control_layout.addWidget(self.baud_combo)
        control_layout.addWidget(self.connect_button)
        control_layout.addStretch()
        main_layout.addLayout(control_layout)

        # --- Main Splitter (RX vs TX/Commands) ---
        main_splitter = QSplitter(Qt.Vertical)
        main_layout.addWidget(main_splitter)

        # --- RX Terminal View ---
        self.terminal_view = QPlainTextEdit()
        self.terminal_view.setReadOnly(True)
        self.terminal_view.setFont(QFont("Consolas", 10))
        self.terminal_view.setStyleSheet("background-color: #1E1E1E; color: #D4D4D4;")

        # --- Bottom Panel (TX and Commands) ---
        bottom_panel = QWidget()
        bottom_panel_layout = QHBoxLayout(bottom_panel)

        tx_splitter = QSplitter(Qt.Horizontal)
        bottom_panel_layout.addWidget(tx_splitter)

        # --- Predefined Commands List ---
        predefined_widget = QWidget()
        predefined_layout = QVBoxLayout(predefined_widget)
        predefined_layout.addWidget(QLabel("Predefined Commands"))
        self.predefined_list = QListWidget()
        self.predefined_list.itemDoubleClicked.connect(self._load_predefined_to_tx)
        predefined_layout.addWidget(self.predefined_list)

        predef_btn_layout = QHBoxLayout()
        self.add_cmd_btn = QPushButton("Add")
        self.edit_cmd_btn = QPushButton("Edit")
        self.del_cmd_btn = QPushButton("Del")
        predef_btn_layout.addWidget(self.add_cmd_btn)
        predef_btn_layout.addWidget(self.edit_cmd_btn)
        predef_btn_layout.addWidget(self.del_cmd_btn)
        predefined_layout.addLayout(predef_btn_layout)

        # --- TX Area ---
        tx_widget = QWidget()
        tx_layout = QVBoxLayout(tx_widget)

        tx_layout.addWidget(QLabel("Command History & Input"))
        self.history_combo = QComboBox()
        self.history_combo.setEditable(False)
        self.history_combo.activated.connect(self._load_history_to_tx)
        tx_layout.addWidget(self.history_combo)

        self.tx_input = QPlainTextEdit()
        self.tx_input.setFont(QFont("Consolas", 10))
        tx_layout.addWidget(self.tx_input)

        tx_btn_layout = QHBoxLayout()
        self.line_ending_combo = QComboBox()
        self.line_ending_combo.addItems(["None", "LF (\\n)", "CR (\\r)", "CRLF (\\r\\n)"])
        self.line_ending_combo.setCurrentIndex(3)
        self.send_button = QPushButton("Send Command")

        tx_btn_layout.addWidget(QLabel("Line Ending:"))
        tx_btn_layout.addWidget(self.line_ending_combo)
        tx_btn_layout.addStretch()
        tx_btn_layout.addWidget(self.send_button)
        tx_layout.addLayout(tx_btn_layout)

        tx_splitter.addWidget(predefined_widget)
        tx_splitter.addWidget(tx_widget)
        tx_splitter.setSizes([300, 600])

        main_splitter.addWidget(self.terminal_view)
        main_splitter.addWidget(bottom_panel)
        main_splitter.setSizes([600, 200])

        # --- Connect Signals ---
        self.connect_button.clicked.connect(self.toggle_connection)
        self.send_button.clicked.connect(self._send_command)
        self.add_cmd_btn.clicked.connect(self._add_predefined)
        self.edit_cmd_btn.clicked.connect(self._edit_predefined)
        self.del_cmd_btn.clicked.connect(self._del_predefined)

    def _load_ui_data(self):
        """Populates UI lists from loaded config data."""
        self.history_combo.addItems(self.command_history)
        for cmd in self.predefined_commands:
            self.predefined_list.addItem(QListWidgetItem(cmd['name']))

    def toggle_connection(self):
        if self.serial_thread and self.serial_thread.isRunning():
            self.serial_worker.stop()
        else:
            port = self.port_combo.currentText()
            baud = int(self.baud_combo.currentText())
            if not port:
                self._log_to_terminal("--- No COM port selected ---", "#FFA500")
                return

            self.serial_thread = QThread()
            self.serial_worker = SerialWorker(port, baud)
            self.serial_worker.moveToThread(self.serial_thread)

            self.serial_worker.data_received.connect(self._handle_data_received)
            self.serial_worker.error_occurred.connect(lambda msg: self._log_to_terminal(msg, "#FF4500"))
            self.serial_worker.connection_status.connect(self._handle_connection_status)
            self.serial_thread.started.connect(self.serial_worker.run)

            self.serial_thread.start()

    @Slot(bool)
    def _handle_connection_status(self, is_connected):
        if is_connected:
            self.connect_button.setText("Disconnect")
            port = self.port_combo.currentText()
            baud = self.baud_combo.currentText()
            self._log_to_terminal(f"--- Connected to {port} at {baud} baud ---", "#00FF7F")
            self.update_timer.start()
        else:
            self.connect_button.setText("Connect")
            self._log_to_terminal("--- Disconnected ---", "#FFA500")
            if self.serial_thread:
                self.serial_thread.quit()
                self.serial_thread.wait()
            self.update_timer.stop()
            self._update_terminal_view() # Final flush

    @Slot(bytes)
    def _handle_data_received(self, data):
        self.rx_buffer.extend(data)

    def _update_terminal_view(self):
        """Optimized GUI update, called by a timer."""
        if not self.rx_buffer:
            return

        text = self.rx_buffer.decode('utf-8', errors='ignore')
        self.rx_buffer.clear()

        # Performance: append once, then ensure max block count
        self.terminal_view.appendPlainText(text)
        if self.terminal_view.blockCount() > MAX_TERMINAL_BLOCKS:
            cursor = self.terminal_view.textCursor()
            cursor.movePosition(QTextCursor.Start)
            cursor.movePosition(QTextCursor.Down, QTextCursor.KeepAnchor, self.terminal_view.blockCount() - MAX_TERMINAL_BLOCKS)
            cursor.removeSelectedText()
            cursor.movePosition(QTextCursor.End)
            self.terminal_view.setTextCursor(cursor)

    def _send_command(self):
        if not (self.serial_worker and self.serial_thread.isRunning()):
            QMessageBox.warning(self, "Not Connected", "Please connect to a serial port first.")
            return

        command = self.tx_input.toPlainText()
        if not command:
            return

        line_ending_map = {
            "None": b'',
            "LF (\\n)": b'\n',
            "CR (\\r)": b'\r',
            "CRLF (\\r\\n)": b'\r\n'
        }
        line_ending = line_ending_map[self.line_ending_combo.currentText()]

        data_to_send = command.encode('utf-8') + line_ending
        self.serial_worker.send_data(data_to_send)
        self._log_to_terminal(f"TX: {command}", "#87CEFA")

        # Update history
        if command not in self.command_history:
            self.command_history.appendleft(command)
            self.history_combo.clear()
            self.history_combo.addItems(self.command_history)

    def _load_history_to_tx(self, index):
        self.tx_input.setPlainText(self.history_combo.itemText(index))

    def _load_predefined_to_tx(self, item: QListWidgetItem):
        index = self.predefined_list.row(item)
        self.tx_input.setPlainText(self.predefined_commands[index]['command'])

    def _add_predefined(self):
        name, ok = QInputDialog.getText(self, "Add Command", "Enter a name for the command:")
        if ok and name:
            command, ok_cmd = QInputDialog.getMultiLineText(self, "Add Command Text", f"Enter command for '{name}':", "")
            if ok_cmd and command:
                new_cmd = {'name': name, 'command': command}
                self.predefined_commands.append(new_cmd)
                self.predefined_list.addItem(QListWidgetItem(name))
            else:
                QMessageBox.warning(self, "Empty Command", "Cannot save an empty command.")

    def _edit_predefined(self):
        current_item = self.predefined_list.currentItem()
        if not current_item: return

        index = self.predefined_list.row(current_item)
        cmd_obj = self.predefined_commands[index]

        new_cmd, ok = QInputDialog.getMultiLineText(self, "Edit Command", f"Editing '{cmd_obj['name']}':", cmd_obj['command'])
        if ok and new_cmd:
            self.predefined_commands[index]['command'] = new_cmd

    def _del_predefined(self):
        current_item = self.predefined_list.currentItem()
        if not current_item: return

        reply = QMessageBox.question(self, "Delete Command", f"Are you sure you want to delete '{current_item.text()}'?")
        if reply == QMessageBox.Yes:
            index = self.predefined_list.row(current_item)
            del self.predefined_commands[index]
            self.predefined_list.takeItem(index)

    def _log_to_terminal(self, message: str, color: str):
        self.terminal_view.appendHtml(f'<font color="{color}">{message}</font>')

    def save_settings(self):
        """Called by MainWindow to persist settings on close."""
        config.settings['serial_monitor']['command_history'] = list(self.command_history)
        config.settings['serial_monitor']['predefined_commands'] = self.predefined_commands
        config.save_config()