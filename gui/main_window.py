import sys
import binascii
import struct
import os
from datetime import datetime
import pandas as pd
import ast
import folium
import re

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QTextEdit, QListWidget, QListWidgetItem, QLineEdit, QStatusBar, QTabWidget,
    QMessageBox, QFileDialog, QSplitter, QInputDialog, QMenu, QCheckBox, QLabel
)
from PySide6.QtGui import QColor, QAction, QTextCursor, QKeySequence, QTextDocument
from PySide6.QtCore import Qt, Slot, QUrl
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEngineSettings

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
        
        self.server_log_file = None

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

        # --- GPS Map Tab ---
        self.map_widget = QWidget()
        map_layout = QVBoxLayout(self.map_widget)
        map_controls_layout = QHBoxLayout()
        refresh_map_btn = QPushButton("Refresh Map Data")
        refresh_map_btn.clicked.connect(self.update_gps_map)
        map_controls_layout.addWidget(refresh_map_btn)
        map_controls_layout.addStretch()
        map_layout.addLayout(map_controls_layout)
        self.web_view = QWebEngineView()
        self.web_view.settings().setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
        self.web_view.settings().setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
        self.web_view.setHtml("<html><body><h1>Map will appear here.</h1><p>Start the server, receive GPS data, and click 'Refresh Map Data'.</p></body></html>")
        map_layout.addWidget(self.web_view)

        self.tabs.addTab(log_widget, "Server Log")
        self.tabs.addTab(self.serial_monitor, "Serial Monitor")
        self.tabs.addTab(self.map_widget, "GPS Map") 

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
        self.settings_action = QAction("&Settings...", self)
        self.exit_action = QAction("E&xit", self)
        self.settings_action.triggered.connect(self.open_settings)
        self.exit_action.triggered.connect(self.close)
        self.find_action = QAction("&Find...", self)
        self.find_action.setShortcut(QKeySequence.Find)
        self.find_action.triggered.connect(self._toggle_find_widget)
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
        self.debug_settings_action = QAction("Response Delays...", self)
        self.kick_device_action = QAction("Kick Selected Device", self)
        self.debug_settings_action.triggered.connect(self.open_debug_settings)
        self.kick_device_action.triggered.connect(self.kick_selected_device)
        self.kick_device_action.setEnabled(False)

    def create_menus(self):
        menu_bar = self.menuBar()
        file_menu = menu_bar.addMenu("&File"); file_menu.addAction(self.settings_action); file_menu.addSeparator(); file_menu.addAction(self.exit_action)
        edit_menu = menu_bar.addMenu("&Edit"); edit_menu.addAction(self.find_action)
        server_menu = menu_bar.addMenu("Server Options"); server_menu.addAction(self.start_server_action); server_menu.addAction(self.stop_server_action); server_menu.addSeparator(); server_menu.addAction(self.show_config_action); server_menu.addSeparator(); server_menu.addAction(self.export_log_action); server_menu.addAction(self.clear_log_action)
        debug_menu = menu_bar.addMenu("&Debug"); debug_menu.addAction(self.debug_settings_action); debug_menu.addAction(self.kick_device_action)

    def start_server(self):
        self.open_log_file()
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
        if self.server_thread and self.server_thread.isRunning(): self.server_thread.stop()
        self.close_log_file()
        self.start_server_action.setEnabled(True)
        self.stop_server_action.setEnabled(False)
        self.status_bar.showMessage("Server stopped.")

    def show_active_config(self):
        protocol = config.get('server.protocol'); host = config.get('server.host'); port = config.get('server.port')
        QMessageBox.information(self, "Active Server Configuration", f"Protocol: {protocol.upper()}\nHost: {host}\nPort: {port}")

    def update_debug_actions(self):
        self.kick_device_action.setEnabled(bool(self.device_list_widget.selectedItems()))

    def open_debug_settings(self):
        dialog = DebugDialog(self.debug_settings, self)
        if dialog.exec():
            self.debug_settings = dialog.get_settings(); self.log("Debug settings updated.", "warn")
            if self.server_thread and self.server_thread.isRunning(): self.server_thread.debug_settings = self.debug_settings

    def kick_selected_device(self):
        current_item = self.device_list_widget.currentItem()
        if not current_item: return
        imei = current_item.data(Qt.UserRole)
        if self.server_thread and self.server_thread.isRunning(): self.server_thread.kick_device(imei)
            
    @Slot(str, str)
    def log(self, message, level="info"):
        if self.server_log_file and not self.server_log_file.closed:
            self.server_log_file.write(f'[{gtime()}] [{level.upper()}] {message}\n'); self.server_log_file.flush()
        scroll_bar = self.log_view.verticalScrollBar(); is_at_bottom = scroll_bar.value() == scroll_bar.maximum()
        color_map = {"info": "blue", "warn": "orange", "error": "red", "data": "#800080"}; color = color_map.get(level, "black")
        self.log_view.moveCursor(QTextCursor.End); self.log_view.insertHtml(f'<font color="{color}">[{gtime()}] {message}</font><br>')
        if self.server_log_auto_scroll_check.isChecked() or is_at_bottom: scroll_bar.setValue(scroll_bar.maximum())

    @Slot(str, str)
    def add_device_to_list(self, imei, ip):
        if not self.find_device_item(imei):
            item = QListWidgetItem(f"{self.device_manager.get_device_name(imei)} [{imei}]"); item.setData(Qt.UserRole, imei); self.device_list_widget.addItem(item)
        self.log(f"Device connected: {imei} from {ip}", "info"); self.update_debug_actions()

    @Slot(str)
    def remove_device_from_list(self, imei):
        item = self.find_device_item(imei)
        if item: self.device_list_widget.takeItem(self.device_list_widget.row(item))
        self.log(f"Device disconnected: {imei}", "warn"); self.update_debug_actions()

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

    def send_command(self):
        current_item = self.device_list_widget.currentItem()
        if not current_item: QMessageBox.warning(self, "No Device Selected", "Please select a device from the list."); return
        imei = current_item.data(Qt.UserRole); command_str = self.command_input.text()
        if not command_str: QMessageBox.warning(self, "No Command", "Please enter a command to send."); return
        if self.server_thread and self.server_thread.isRunning():
            self.server_thread.send_command_to_device(imei, command_str); self.log(f"TX to {imei}: {command_str}", "data"); self.command_input.clear()

    def export_log(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export Log", "", "Excel Files (*.xlsx);;Text Files (*.txt);;All Files (*)")
        if not path: return
        if not path.lower().endswith(('.xlsx', '.txt')): path += '.xlsx'
        if path.lower().endswith('.txt'):
            try:
                with open(path, 'w', encoding='utf-8') as f: f.write(self.log_view.toPlainText())
                self.log(f"Log exported to {path}", "info")
            except Exception as e: self.log(f"Failed to export text log: {e}", "error")
        elif path.lower().endswith('.xlsx'): self.export_log_to_excel(path)

    def export_log_to_excel(self, path):
        self.status_bar.showMessage("Exporting to Excel... this may take a moment."); QApplication.processEvents()
        lines = self.log_view.toPlainText().strip().split('\n'); parsed_records = []
        for line in lines:
            try:
                timestamp_str = line[1:25]; message = line[27:]
                record = {'Timestamp': timestamp_str, 'IMEI': None, 'DataType': None, 'Latitude': None, 'Longitude': None, 'Altitude': None, 'Speed': None, 'RawMessage': message}
                if " from " in message or " to " in message:
                    parts = message.split(' ');
                    if len(parts) > 2 and parts[2] != 'None:': record['IMEI'] = parts[2].replace(':', '')
                if "Decoded:" in message:
                    record['DataType'] = 'DecodedData'
                    try:
                        data_dict = ast.literal_eval(message.replace("Decoded: ", ""))
                        if isinstance(data_dict, dict) and 'records' in data_dict and data_dict['records']:
                            first_record = data_dict['records'][0]
                            record.update({ 'DataType': data_dict.get('type', 'AVL Data'), 'Latitude': first_record.get('latitude'), 'Longitude': first_record.get('longitude'), 'Altitude': first_record.get('altitude'), 'Speed': first_record.get('speed') })
                    except: pass
                parsed_records.append(record)
            except IndexError: parsed_records.append({'Timestamp': None, 'RawMessage': line})
        if not parsed_records: QMessageBox.warning(self, "Export Failed", "The log is empty or could not be parsed."); self.status_bar.showMessage("Export failed.", 3000); return
        try:
            df = pd.DataFrame(parsed_records); df = df[['Timestamp', 'IMEI', 'DataType', 'Latitude', 'Longitude', 'Altitude', 'Speed', 'RawMessage']]
            df.to_excel(path, index=False, engine='openpyxl')
            self.log(f"Log successfully exported to Excel file: {path}", "info"); self.status_bar.showMessage(f"Export complete: {os.path.basename(path)}", 5000)
        except Exception as e: self.log(f"Failed to write Excel file: {e}", "error"); self.status_bar.showMessage("Excel export failed.", 3000); QMessageBox.critical(self, "Excel Export Error", f"An error occurred: {e}\n\nPlease ensure you have 'pandas' and 'openpyxl' installed.")

    def open_settings(self):
        dialog = SettingsDialog(self)
        if dialog.exec(): self.log("Settings updated. Please restart the server for all changes to take effect.", "warn")

    def open_device_menu(self, position):
        item = self.device_list_widget.itemAt(position);
        if not item: return
        menu = QMenu(); rename_action = menu.addAction("Rename Device"); action = menu.exec(self.device_list_widget.mapToGlobal(position))
        if action == rename_action: self.rename_device(item)

    def rename_device(self, item):
        imei = item.data(Qt.UserRole); current_name = self.device_manager.get_device_name(imei)
        new_name, ok = QInputDialog.getText(self, "Rename Device", "Enter new name:", text=current_name if imei != current_name else "")
        if ok and new_name: self.device_manager.set_device_name(imei, new_name); item.setText(f"{new_name} [{imei}]"); self.log(f"Device {imei} renamed to '{new_name}'", "info")

    def _toggle_find_widget(self):
        current_tab_widget = self.tabs.currentWidget()
        if current_tab_widget == self.serial_monitor: self.serial_monitor.toggle_search_widget()
        elif self.tabs.tabText(self.tabs.currentIndex()) == "Server Log":
            is_visible = self.server_search_widget.isVisible(); self.server_search_widget.setVisible(not is_visible)
            if not is_visible: self.server_search_input.setFocus()
                
    def _find_in_log(self, find_backwards=False):
        text_to_find = self.server_search_input.text()
        if not text_to_find: return
        flags = QTextDocument.FindFlag();
        if find_backwards: flags |= QTextDocument.FindBackward
        if self.server_search_case_check.isChecked(): flags |= QTextDocument.FindCaseSensitively
        if not self.log_view.find(text_to_find, flags):
            cursor = self.log_view.textCursor(); cursor.movePosition(QTextCursor.End if find_backwards else QTextCursor.Start); self.log_view.setTextCursor(cursor); self.log_view.find(text_to_find, flags)

    def _find_next_in_server_log(self): self._find_in_log(find_backwards=False)
    def _find_prev_in_server_log(self): self._find_in_log(find_backwards=True)
    
    def open_log_file(self):
        self.close_log_file(); log_config = config.get('logging', {'mode': 'daily', 'path': 'server_log.txt'}); mode = log_config.get('mode', 'daily'); log_dir = "server_logs"; os.makedirs(log_dir, exist_ok=True)
        filename = ""
        if mode == 'daily': filename = f"log_{datetime.now().strftime('%Y-%m-%d')}.log"
        elif mode == 'session': filename = f"log_session_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        elif mode == 'persistent': filename = log_config.get('path', 'server_log.txt')
        if filename:
            filepath = filename if os.path.isabs(filename) else os.path.join(log_dir, filename)
            try: self.server_log_file = open(filepath, 'a', encoding='utf-8'); self.log(f"Server logging active. Mode: {mode}. File: {filepath}", "info")
            except Exception as e: self.log(f"Failed to open server log file '{filepath}': {e}", "error")

    def close_log_file(self):
        if self.server_log_file: self.log(f"Closing server log file.", "info"); self.server_log_file.close(); self.server_log_file = None

    # --- MODIFICATION: Renamed function for clarity
    def get_all_records_from_log(self):
        log_text = self.log_view.toPlainText()
        # --- MODIFICATION: Changed data structure to hold full records
        records_by_imei = {}
        current_imei = None
        datetime_regex = re.compile(r"datetime\.datetime\([^)]+\)")
        imei_regex = re.compile(r"RX from (\d{15,17})")
        for line in log_text.strip().split('\n'):
            imei_match = imei_regex.search(line)
            if imei_match: current_imei = imei_match.group(1)
            
            if "Decoded:" in line and current_imei:
                try:
                    log_timestamp = line[1:25] # Capture timestamp from the log line itself
                    dict_str_match = re.search(r"Decoded: (\{.*\})", line)
                    if not dict_str_match: continue
                    dict_str = dict_str_match.group(1)
                    sanitized_dict_str = datetime_regex.sub("None", dict_str)
                    data_dict = ast.literal_eval(sanitized_dict_str)
                    
                    if isinstance(data_dict, dict) and 'records' in data_dict and data_dict.get('records'):
                        for rec in data_dict['records']:
                            if 'latitude' in rec and 'longitude' in rec and isinstance(rec.get('latitude'), (int, float)) and isinstance(rec.get('longitude'), (int, float)):
                                lat, lon = rec['latitude'], rec['longitude']
                                if abs(lat) > 0.0001 and abs(lon) > 0.0001:
                                    if current_imei not in records_by_imei: records_by_imei[current_imei] = []
                                    # --- MODIFICATION: Add full record, not just coords ---
                                    rec['log_timestamp'] = log_timestamp # Add captured timestamp to the record
                                    records_by_imei[current_imei].append(rec)
                except Exception: continue
        return records_by_imei

    # --- MODIFICATION: New helper function to format popups ---
    def _format_record_for_popup(self, record):
        """Creates a nicely formatted HTML string from a record dictionary."""
        html = "<div style='font-family: monospace;'>"
        # Prioritize key fields
        priority_keys = ['log_timestamp', 'latitude', 'longitude', 'speed', 'satellites', 'altitude', 'angle']
        for key in priority_keys:
            if key in record:
                html += f"<b>{key.replace('_',' ').title()}:</b> {record[key]}<br>"
        html += "<hr>"
        # Add all other fields
        for key, value in record.items():
            if key not in priority_keys:
                html += f"<b>{str(key).replace('_',' ').title()}:</b> {str(value)}<br>"
        html += "</div>"
        return html

    def update_gps_map(self):
        self.status_bar.showMessage("Generating map from log data...")
        QApplication.processEvents()
        
        # --- MODIFICATION: Use new function and variable name
        records_by_imei = self.get_all_records_from_log()
        
        if not records_by_imei:
            self.web_view.setHtml("<html><body><h2>No valid GPS data found in the server log.</h2></body></html>")
            self.status_bar.showMessage("Map generation failed: No GPS data found.", 4000)
            return

        first_imei_with_records = next((imei for imei, recs in records_by_imei.items() if recs), None)
        if not first_imei_with_records:
             self.web_view.setHtml("<html><body><h2>No valid GPS data found in the server log.</h2></body></html>")
             return

        # --- MODIFICATION: Get map center from the first record's lat/lon
        first_record = records_by_imei[first_imei_with_records][0]
        map_center = (first_record['latitude'], first_record['longitude'])
        
        m = folium.Map(location=map_center, zoom_start=13, tiles="CartoDB positron")
        colors = ['blue', 'red', 'green', 'purple', 'orange', 'darkred', 'cadetblue', 'darkgreen', 'lightred']
        
        for i, (imei, records) in enumerate(records_by_imei.items()):
            if not records: continue
            
            # Create a list of (lat, lon) for the polyline
            path_coords = [(rec['latitude'], rec['longitude']) for rec in records]
            color = colors[i % len(colors)]
            
            # Draw the path
            folium.PolyLine(path_coords, color=color, weight=2.5, opacity=1, popup=f"Path for {imei}").add_to(m)
            
            # --- MODIFICATION: Add detailed popups and per-point markers ---
            # Add Start Marker
            start_popup_html = self._format_record_for_popup(records[0])
            iframe = folium.IFrame(html=start_popup_html, width=300, height=180)
            popup = folium.Popup(iframe, max_width=300)
            folium.Marker(location=path_coords[0], popup=popup, tooltip=f"Start: {imei}", icon=folium.Icon(color='green', icon='play')).add_to(m)

            # Add End Marker (if more than one point)
            if len(records) > 1:
                end_popup_html = self._format_record_for_popup(records[-1])
                iframe = folium.IFrame(html=end_popup_html, width=300, height=180)
                popup = folium.Popup(iframe, max_width=300)
                folium.Marker(location=path_coords[-1], popup=popup, tooltip=f"End: {imei}", icon=folium.Icon(color='red', icon='stop')).add_to(m)
                
            # Add a small circle for every data point
            for rec in records:
                point_popup_html = self._format_record_for_popup(rec)
                iframe = folium.IFrame(html=point_popup_html, width=300, height=180)
                popup = folium.Popup(iframe, max_width=300)
                folium.CircleMarker(
                    location=(rec['latitude'], rec['longitude']),
                    radius=4,
                    color=color,
                    fill=True,
                    fill_color=color,
                    fill_opacity=0.7,
                    popup=popup,
                    tooltip=f"Point @ {rec.get('log_timestamp', '')}"
                ).add_to(m)

        map_file_path = os.path.abspath("gps_map_render.html")
        m.save(map_file_path)
        self.web_view.setUrl(QUrl.fromLocalFile(map_file_path))
        self.status_bar.showMessage("Map updated successfully.", 4000)

    def closeEvent(self, event):
        self.stop_server()
        self.device_manager.close()
        self.serial_monitor.save_settings()
        event.accept()