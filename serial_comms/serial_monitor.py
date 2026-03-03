import sys
import os
import collections
import time
from datetime import datetime
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, QPushButton, QComboBox,
    QLabel, QListWidget, QListWidgetItem, QSplitter,
    QInputDialog, QMessageBox, QCheckBox, QLineEdit
)
from PySide6.QtCore import QThread, Signal, QObject, QTimer, Qt, Slot
from PySide6.QtGui import QFont, QColor, QTextCursor, QTextDocument, QTextCharFormat
import serial
import serial.tools.list_ports
from core.config_manager import config

# --- Constants ---
MAX_TERMINAL_BLOCKS = 15000
UPDATE_INTERVAL_MS = 250  # Increased from 100ms to 250ms to reduce CPU usage
COMMAND_HISTORY_SIZE = 50
RECONNECT_INTERVAL_MS = 2000
LOG_DIRECTORY = "logs"

# --- Colors ---
COLOR_RX = QColor("#D4D4D4")
COLOR_TX = QColor("#87CEFA")
COLOR_INFO = QColor("#00FF7F")
COLOR_WARN = QColor("#FFA500")
COLOR_ERROR = QColor("#FF4500")
COLOR_LOG = QColor("#ADD8E6")


class SerialWorker(QObject):
    data_received = Signal(bytes)
    error_occurred = Signal(str)
    connection_status = Signal(bool)

    def __init__(self, port, baudrate):
        super().__init__()
        self.serial_conn = None
        self._port = port
        self._baudrate = baudrate
        self._is_running = False

    @Slot()
    def run(self):
        self._is_running = True
        import time  # Add time import for sleep
        try:
            self.serial_conn = serial.Serial(self._port, self._baudrate, timeout=0.1)
            self.connection_status.emit(True)
            while self._is_running:
                try:
                    if self.serial_conn and self.serial_conn.in_waiting > 0:
                        data = self.serial_conn.read(self.serial_conn.in_waiting)
                        if data: self.data_received.emit(data)
                    else:
                        # Add a small sleep when no data is available to reduce CPU usage
                        time.sleep(0.005)  # 5ms sleep
                except serial.SerialException as e:
                    self.error_occurred.emit(f"Device disconnected: {e}")
                    break
        except serial.SerialException as e:
            self.error_occurred.emit(f"Connection failed: {e}")
        finally:
            if self.serial_conn and self.serial_conn.is_open:
                self.serial_conn.close()
            # This is the last signal emitted before the thread dies.
            self.connection_status.emit(False)


    def stop(self): self._is_running = False

    def send_data(self, data: bytes):
        if self.serial_conn and self.serial_conn.is_open:
            try: self.serial_conn.write(data)
            except serial.SerialException as e: self.error_occurred.emit(f"TX Error: {e}")


class SerialMonitor(QWidget):
    def __init__(self):
        super().__init__()
        self.serial_thread = None
        self.serial_worker = None
        self.rx_buffer = bytearray()
        self.log_file = None
        self.terminal_font = QFont("Consolas", 10)
        os.makedirs(LOG_DIRECTORY, exist_ok=True)
        self.command_history = collections.deque(config.get('serial_monitor.command_history', []), maxlen=COMMAND_HISTORY_SIZE)
        self.predefined_commands = config.get('serial_monitor.predefined_commands', [])
        
        self.is_attempting_reconnect = False
        self.user_initiated_disconnect = False
        
        # Performance tracking
        self._last_full_process_time = datetime.now()
        self._performance_stats = {
            'process_count': 0,
            'process_time_total': 0,
            'ui_update_count': 0,
            'ui_update_time_total': 0
        }
        
        self.update_timer = QTimer(self)
        self.update_timer.setInterval(UPDATE_INTERVAL_MS)
        self.update_timer.timeout.connect(self._process_rx_buffer)
        
        # Add a slower timer for adaptive interval adjustment
        self.adaptive_timer = QTimer(self)
        self.adaptive_timer.setInterval(5000)  # Check every 5 seconds
        self.adaptive_timer.timeout.connect(self._adjust_update_interval)
        
        self.reconnect_timer = QTimer(self)
        self.reconnect_timer.setInterval(RECONNECT_INTERVAL_MS)
        self.reconnect_timer.timeout.connect(self._attempt_reconnect)
        
        # Track data rate
        self._bytes_received_in_window = 0
        self._last_rate_check = time.time()
        
        self._setup_ui()
        self._load_ui_data()

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        self.terminal_view = QTextEdit()
        self.terminal_view.setReadOnly(True)
        self.terminal_view.setFont(self.terminal_font)
        self.terminal_view.setStyleSheet("background-color: #1E1E1E; border: 1px solid #444; color: #D4D4D4;")
        self._setup_control_bar(main_layout); self._setup_search_ui(main_layout)
        main_splitter = QSplitter(Qt.Orientation.Vertical); bottom_panel = self._create_bottom_panel()
        main_splitter.addWidget(self.terminal_view); main_splitter.addWidget(bottom_panel)
        main_splitter.setSizes([600, 200]); main_layout.addWidget(main_splitter)

    def _setup_control_bar(self, parent_layout):
        layout = QHBoxLayout()
        self.port_combo = QComboBox(); self.baud_combo = QComboBox()
        self.connect_button = QPushButton("Connect"); self.connect_button.setCheckable(True)
        self.auto_reconnect_checkbox = QCheckBox("Auto Reconnect"); self.auto_reconnect_checkbox.setChecked(True)
        self.auto_scroll_checkbox = QCheckBox("Auto Scroll"); self.auto_scroll_checkbox.setChecked(True)
        self.clear_button = QPushButton("Clear"); self.find_button = QPushButton("Find")
        layout.addWidget(QLabel("Port:")); layout.addWidget(self.port_combo); layout.addWidget(QLabel("Baudrate:")); layout.addWidget(self.baud_combo)
        layout.addWidget(self.auto_reconnect_checkbox); layout.addWidget(self.auto_scroll_checkbox)
        layout.addWidget(self.clear_button); layout.addWidget(self.find_button)
        
        # --- MODIFICATION: Add Live Highlight feature UI ---
        layout.addWidget(QLabel("   |   Live Highlight:"))
        self.highlight_input = QLineEdit()
        self.highlight_input.setPlaceholderText("Term...")
        self.highlight_input.setMaximumWidth(150)
        self.highlight_case_check = QCheckBox("Case")
        layout.addWidget(self.highlight_input)
        layout.addWidget(self.highlight_case_check)

        layout.addStretch(); layout.addWidget(self.connect_button)
        parent_layout.addLayout(layout)
        self.connect_button.clicked.connect(self.toggle_connection); self.clear_button.clicked.connect(self.terminal_view.clear); self.find_button.clicked.connect(self.toggle_search_widget)
        
    def _setup_search_ui(self, parent_layout):
        self.search_widget = QWidget(); self.search_widget.hide()
        layout = QHBoxLayout(self.search_widget); layout.setContentsMargins(0, 0, 0, 5)
        self.search_input = QLineEdit(); self.search_input.setPlaceholderText("Search existing log...")
        self.search_case_check = QCheckBox("Case Sensitive")
        find_prev_btn = QPushButton("Previous"); find_next_btn = QPushButton("Next"); close_search_btn = QPushButton("✕")
        layout.addWidget(QLabel("Find:")); layout.addWidget(self.search_input); layout.addWidget(self.search_case_check)
        layout.addWidget(find_prev_btn); layout.addWidget(find_next_btn); layout.addWidget(close_search_btn)
        parent_layout.addWidget(self.search_widget)
        close_search_btn.clicked.connect(self.search_widget.hide); find_next_btn.clicked.connect(self._find_next)
        find_prev_btn.clicked.connect(self._find_previous); self.search_input.returnPressed.connect(self._find_next)

    def _create_bottom_panel(self):
        bottom_panel = QWidget(); bottom_layout = QHBoxLayout(bottom_panel); tx_splitter = QSplitter(Qt.Orientation.Horizontal); bottom_layout.addWidget(tx_splitter)
        predefined_widget = QWidget(); predefined_layout = QVBoxLayout(predefined_widget)
        predefined_layout.addWidget(QLabel("Predefined Commands (Double-click)")); self.predefined_list = QListWidget()
        self.predefined_list.itemDoubleClicked.connect(self._send_predefined_command); predefined_layout.addWidget(self.predefined_list)
        predef_btn_layout = QHBoxLayout(); add_btn = QPushButton("Add"); edit_btn = QPushButton("Edit"); del_btn = QPushButton("Del")
        predef_btn_layout.addWidget(add_btn); predef_btn_layout.addWidget(edit_btn); predef_btn_layout.addWidget(del_btn)
        predefined_layout.addLayout(predef_btn_layout); add_btn.clicked.connect(self._add_predefined); edit_btn.clicked.connect(self._edit_predefined); del_btn.clicked.connect(self._del_predefined)
        tx_widget = QWidget(); tx_layout = QVBoxLayout(tx_widget)
        tx_layout.addWidget(QLabel("Command History & Input")); self.history_combo = QComboBox(); self.history_combo.setEditable(False)
        self.history_combo.activated.connect(self._load_history_to_tx); tx_layout.addWidget(self.history_combo)
        self.tx_input = QLineEdit(); self.tx_input.setFont(self.terminal_font); self.tx_input.returnPressed.connect(self._send_command_from_input)
        tx_layout.addWidget(self.tx_input); tx_btn_layout = QHBoxLayout()
        self.line_ending_combo = QComboBox(); self.line_ending_combo.addItems(["None", "LF (\\n)", "CR (\\r)", "CRLF (\\r\\n)"]); self.line_ending_combo.setCurrentText("CR (\\r)"); self.send_button = QPushButton("Send Command")
        tx_btn_layout.addWidget(QLabel("Line Ending:")); tx_btn_layout.addWidget(self.line_ending_combo); tx_btn_layout.addStretch(); tx_btn_layout.addWidget(self.send_button)
        tx_layout.addLayout(tx_btn_layout); self.send_button.clicked.connect(self._send_command_from_input)
        tx_splitter.addWidget(predefined_widget); tx_splitter.addWidget(tx_widget); tx_splitter.setSizes([300, 600])
        return bottom_panel

    def _load_ui_data(self):
        self.refresh_ports(); self.baud_combo.addItems(['9600', '19200', '38400', '57600', '115200', '921600'])
        self.baud_combo.setCurrentText(str(config.get('serial_monitor.last_used_baudrate', '115200')))
        for cmd in self.predefined_commands: self.predefined_list.addItem(QListWidgetItem(cmd['name']))
        self.history_combo.addItems(self.command_history)

    # Optimized to reduce CPU usage in highlighting
    def _add_text_to_terminal(self, text: str, color: QColor):
        scroll_bar = self.terminal_view.verticalScrollBar()
        auto_scroll_enabled = self.auto_scroll_checkbox.isChecked()
        old_scroll_value = scroll_bar.value()

        # Move cursor to the end once
        cursor = self.terminal_view.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.terminal_view.setTextCursor(cursor)
        
        # Check if highlighting is needed - skip the whole process if no highlight term
        highlight_term = self.highlight_input.text()
        if not highlight_term:
            # Fast path: no highlighting at all
            self.terminal_view.setTextColor(color)
            self.terminal_view.insertPlainText(text)
        else:
            # Only do the more expensive case-insensitive check if there's a term to highlight
            is_case_sensitive = self.highlight_case_check.isChecked()
            should_highlight = (highlight_term in text if is_case_sensitive 
                               else highlight_term.lower() in text.lower())
            
            if not should_highlight:
                # Simple path: no highlighting needed for this text block
                self.terminal_view.setTextColor(color)
                self.terminal_view.insertPlainText(text)
            else:
                # Complex path: insert text in pieces to apply highlighting
                normal_format = QTextCharFormat()
                normal_format.setForeground(color)
    
                highlight_format = QTextCharFormat()
                highlight_format.setBackground(QColor("yellow"))
                highlight_format.setForeground(QColor("black"))
                
                # Use different variables for case-insensitive search
                text_to_search = text if is_case_sensitive else text.lower()
                term_to_search = highlight_term if is_case_sensitive else highlight_term.lower()
                
                last_index = 0
                while True:
                    start_index = text_to_search.find(term_to_search, last_index)
                    if start_index == -1:
                        break
    
                    # Insert the part before the match
                    cursor.setCharFormat(normal_format)
                    cursor.insertText(text[last_index:start_index])
    
                    # Insert the highlighted match
                    cursor.setCharFormat(highlight_format)
                    cursor.insertText(text[start_index : start_index + len(highlight_term)])
    
                    last_index = start_index + len(highlight_term)
    
                # Insert any remaining text after the last match
                cursor.setCharFormat(normal_format)
                cursor.insertText(text[last_index:])
            
        # Handle scrollbar
        if auto_scroll_enabled:
            scroll_bar.setValue(scroll_bar.maximum())
        else:
            scroll_bar.setValue(old_scroll_value)
        
        # --- Only prune text when necessary and with a margin to avoid doing it too often ---
        document = self.terminal_view.document()
        if document.blockCount() > MAX_TERMINAL_BLOCKS + 500:  # Add margin to reduce pruning frequency
            cursor = QTextCursor(document); cursor.movePosition(QTextCursor.MoveOperation.Start)
            cursor.movePosition(QTextCursor.MoveOperation.NextBlock, QTextCursor.MoveMode.KeepAnchor, document.blockCount() - MAX_TERMINAL_BLOCKS)
            cursor.removeSelectedText(); cursor.deleteChar()

    @Slot(bool)
    def toggle_connection(self, checked):
        if checked:
            port, baud = self.port_combo.currentText(), int(self.baud_combo.currentText())
            if not port: self._add_text_to_terminal("\n--- No COM port selected ---\n", COLOR_ERROR); self.connect_button.setChecked(False); return
            self._start_new_connection(port, baud)
        else: self._stop_current_connection()
    def _start_new_connection(self, port, baud):
        self._cleanup_serial_thread()

        self.serial_thread = QThread()
        self.serial_worker = SerialWorker(port, baud)
        self.serial_worker.moveToThread(self.serial_thread)
        self.serial_worker.data_received.connect(self.on_data_received)
        self.serial_worker.error_occurred.connect(lambda msg: self._add_text_to_terminal(f"\n--- {msg} ---\n", COLOR_ERROR))
        self.serial_worker.connection_status.connect(self.on_connection_status_changed)
        self.serial_thread.started.connect(self.serial_worker.run)
        self.serial_thread.finished.connect(self.serial_worker.deleteLater)
        self.serial_thread.start()
        self.connect_button.setText("Connecting...")
        self.port_combo.setEnabled(False)
        self.baud_combo.setEnabled(False)
        
    def _cleanup_serial_thread(self):
        """Safely stops and cleans up the current serial thread and worker."""
        if self.serial_worker:
            self.serial_worker.stop()
        if self.serial_thread:
            self.serial_thread.quit()
            # Wait a reasonable time for the thread to finish.
            if not self.serial_thread.wait(1000):
                self._add_text_to_terminal("\n--- Serial thread did not stop gracefully. Forcing termination. ---\n", COLOR_ERROR)
                self.serial_thread.terminate()
                self.serial_thread.wait() # Wait after termination
        # Set to None to allow garbage collection and prevent reuse of old objects.
        self.serial_thread = None
        self.serial_worker = None
        
    def _stop_current_connection(self):
        self.user_initiated_disconnect = True
        self.reconnect_timer.stop()
        if self.serial_worker:
            self.serial_worker.stop()
        if self.serial_thread:
            self.serial_thread.quit()
            self.serial_thread.wait(2000)  # Wait up to 2 seconds for clean exit
            if self.serial_thread.isRunning():
                self.serial_thread.terminate()
                self.serial_thread.wait(1000)
            self.serial_thread = None
            self.serial_worker = None

    @Slot(bool)
    def on_connection_status_changed(self, is_connected):
        if is_connected:
            self.is_attempting_reconnect = False
            self.reconnect_timer.stop()
            self.connect_button.setChecked(True)
            self.connect_button.setText("Disconnect")
            self._add_text_to_terminal(f"\n--- Connected to {self.port_combo.currentText()} @ {self.baud_combo.currentText()} baud ---\n", COLOR_INFO)
            config.settings['serial_monitor']['last_used_port'] = self.port_combo.currentText()
            config.settings['serial_monitor']['last_used_baudrate'] = int(self.baud_combo.currentText())
            self.start_file_logging()
            self.update_timer.start()
            self.adaptive_timer.start()
        else: # Disconnected
            self.stop_file_logging()
            self.update_timer.stop()
            self.adaptive_timer.stop()
            self._process_rx_buffer() # Process any remaining data

            # --- FIX: The cleanup now happens before we decide to reconnect. ---
            # The worker thread has finished, now we clean it up completely.
            self._cleanup_serial_thread()
            
            self.port_combo.setEnabled(True)
            self.baud_combo.setEnabled(True)
            self.connect_button.setChecked(False)
            self.connect_button.setText("Connect")
            
            if self.auto_reconnect_checkbox.isChecked() and not self.user_initiated_disconnect:
                if not self.is_attempting_reconnect:
                    self._add_text_to_terminal("\n--- Connection lost. Attempting to reconnect... ---\n", COLOR_WARN)
                    self.is_attempting_reconnect = True
                    self.reconnect_timer.start()
            
    @Slot(bytes)
    def on_data_received(self, data):
        data_size = len(data)
        self.rx_buffer.extend(data)
        self._bytes_received_in_window += data_size
        
        if self.log_file and not self.log_file.closed:
            try: self.log_file.write(data.decode('utf-8', errors='ignore'))
            except Exception: pass

    @Slot()
    def _process_rx_buffer(self):
        if not self.rx_buffer: return
        
        # Process data in larger batches to reduce UI updates
        processed_len = 0
        buffer_size = len(self.rx_buffer)
        
        # Only process if we have enough data or it's been a while since last update
        if buffer_size < 1024 and hasattr(self, '_last_full_process_time') and (datetime.now() - self._last_full_process_time).total_seconds() < 0.5:
            return
            
        # Update timestamp for batching logic
        self._last_full_process_time = datetime.now()
        
        decoded = self.rx_buffer.decode('utf-8', 'ignore')
        lines = []
        current_position = 0
        
        # First collect complete lines
        for line in decoded.splitlines(keepends=True):
            if line.endswith(('\n', '\r')):
                lines.append(line)
                current_position += len(line.encode('utf-8', 'ignore'))
            else:
                break
        
        # If we have complete lines, add them all at once
        if lines:
            self._add_text_to_terminal(''.join(lines), COLOR_RX)
            processed_len = current_position
            
        # Remove processed data
        if processed_len > 0:
            self.rx_buffer = self.rx_buffer[processed_len:]

    def _send_command(self, command: str):
        if not command.strip(): return
        if not self.serial_worker: QMessageBox.warning(self, "Not Connected", "Please connect to a serial port first."); return
        line_ending_map = {"None": b'', "LF (\\n)": b'\n', "CR (\\r)": b'\r', "CRLF (\\r\\n)": b'\r\n'}; line_ending = line_ending_map.get(self.line_ending_combo.currentText(), b'')
        data_to_send = command.encode('utf-8') + line_ending
        self.serial_worker.send_data(data_to_send); self._add_text_to_terminal(f"TX: {command}\n", COLOR_TX)
        if command not in self.command_history: self.command_history.appendleft(command); self.history_combo.clear(); self.history_combo.addItems(self.command_history)

    def _send_command_from_input(self): self._send_command(self.tx_input.text()); self.tx_input.clear()
    def _send_predefined_command(self, item: QListWidgetItem): self._send_command(self.predefined_commands[self.predefined_list.row(item)]['command'])
    def _load_history_to_tx(self, index): self.tx_input.setText(self.history_combo.itemText(index))
    def _attempt_reconnect(self):
        # This timer runs in the main GUI thread, so no need to worry about thread-safety of list_ports
        available_ports = [p.device for p in serial.tools.list_ports.comports()]
        if self.port_combo.currentText() in available_ports:
            self._add_text_to_terminal("\n--- Port found. Reconnecting... ---\n", COLOR_INFO)
            self.reconnect_timer.stop()
            self.is_attempting_reconnect = False
            self.toggle_connection(True)
    
    def toggle_search_widget(self): self.search_widget.setVisible(not self.search_widget.isVisible()); self.search_input.setFocus() if self.search_widget.isVisible() else None
    def _find_next(self): self._find(find_backwards=False)
    def _find_previous(self): self._find(find_backwards=True)

    def _find(self, find_backwards=False):
        search_text = self.search_input.text()
        if not search_text: return
        flags = QTextDocument.FindFlag()
        if find_backwards: flags |= QTextDocument.FindFlag.FindBackward
        if self.search_case_check.isChecked(): flags |= QTextDocument.FindFlag.FindCaseSensitively
        if not self.terminal_view.find(search_text, flags):
            cursor = self.terminal_view.textCursor(); cursor.movePosition(QTextCursor.MoveOperation.End if find_backwards else QTextCursor.MoveOperation.Start)
            self.terminal_view.setTextCursor(cursor); self.terminal_view.find(search_text, flags)

    def start_file_logging(self):
        self.stop_file_logging(); ts = datetime.now().strftime("%Y%m%d_%H%M%S"); self.current_log_filepath = os.path.join(LOG_DIRECTORY, f"serial_log_{ts}.log")
        try: self.log_file = open(self.current_log_filepath, "w", encoding="utf-8"); self._add_text_to_terminal(f"\n--- Logging to {os.path.basename(self.current_log_filepath)} ---\n", COLOR_LOG)
        except Exception as e: self._add_text_to_terminal(f"\n--- Failed to start logging: {e} ---\n", COLOR_ERROR)

    def stop_file_logging(self):
        if self.log_file and not self.log_file.closed: self.log_file.close(); self.log_file = None; self._add_text_to_terminal("\n--- Stopped file logging ---\n", COLOR_LOG)
    
    def _add_predefined(self):
        name, ok = QInputDialog.getText(self, "Add Command", "Name:");
        if ok and name:
            command, ok = QInputDialog.getText(self, "Add Command Text", f"Command for '{name}':")
            if ok and command: self.predefined_commands.append({'name': name, 'command': command}); self.predefined_list.addItem(QListWidgetItem(name))

    def _edit_predefined(self):
        item = self.predefined_list.currentItem();
        if not item: return
        index = self.predefined_list.row(item); cmd_obj = self.predefined_commands[index]
        new_cmd, ok = QInputDialog.getText(self, "Edit Command", f"Editing '{cmd_obj['name']}':", text=cmd_obj['command'])
        if ok and new_cmd: self.predefined_commands[index]['command'] = new_cmd
        
    def _del_predefined(self):
        item = self.predefined_list.currentItem();
        if not item: return
        if QMessageBox.question(self, "Delete", f"Delete '{item.text()}'?") == QMessageBox.StandardButton.Yes:
            index = self.predefined_list.row(item); del self.predefined_commands[index]; self.predefined_list.takeItem(index)
            
    def save_settings(self):
        if 'serial_monitor' not in config.settings:
            config.settings['serial_monitor'] = {}
        config.settings['serial_monitor']['command_history'] = list(self.command_history)
        config.settings['serial_monitor']['predefined_commands'] = self.predefined_commands
        config.settings['serial_monitor']['auto_scroll_enabled'] = self.auto_scroll_checkbox.isChecked()
        config.save_config()

    def refresh_ports(self):
        current = self.port_combo.currentText(); self.port_combo.clear(); ports = sorted([p.device for p in serial.tools.list_ports.comports()])
        self.port_combo.addItems(ports); last_used = config.get('serial_monitor.last_used_port')
        if current in ports: self.port_combo.setCurrentText(current)
        elif last_used in ports: self.port_combo.setCurrentText(last_used)
    
    @Slot()
    def _adjust_update_interval(self):
        """Dynamically adjust update interval based on data rate to optimize CPU usage."""
        current_time = time.time()
        time_diff = current_time - self._last_rate_check
        if time_diff <= 0:
            return
            
        # Calculate bytes per second
        bytes_per_sec = self._bytes_received_in_window / time_diff
        
        # Reset for next window
        self._bytes_received_in_window = 0
        self._last_rate_check = current_time
        
        # Adjust timer interval based on data rate
        if bytes_per_sec > 10000:  # Very high data rate
            new_interval = 50  # Update more frequently for high data rates
        elif bytes_per_sec > 5000:
            new_interval = 100
        elif bytes_per_sec > 1000:
            new_interval = 200
        elif bytes_per_sec > 100:
            new_interval = 300
        else:
            new_interval = 400  # For very low data rates, update less frequently
            
        # Cap at reasonable values
        new_interval = max(50, min(500, new_interval))
        
        # Only update if changed significantly to avoid constant minor adjustments
        current_interval = self.update_timer.interval()
        if abs(current_interval - new_interval) > 50:
            self.update_timer.setInterval(new_interval)