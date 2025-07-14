# server/tcp_server.py

import socket
import threading
import time
import ssl
import binascii
import struct
from PySide6.QtCore import QThread, Signal
from core.config_manager import config
from protocols.codec import decode_packet, encode_codec12_command

class ClientHandler(threading.Thread):
    def __init__(self, connection, address, server_instance):
        super().__init__()
        self.connection = connection
        self.address = address
        self.server = server_instance
        self.signals = server_instance
        self.debug_settings = self.server.debug_settings
        self.imei = None
        self.is_running = True

    def run(self):
        protocol = "TLS" if isinstance(self.connection, ssl.SSLSocket) else "TCP"
        self.signals.log_message.emit(f"New {protocol} connection from {self.address[0]}:{self.address[1]}", "info")
        
        while self.is_running:
            try:
                data = self.connection.recv(4096)
                if not data:
                    break

                if not self.imei:
                    if len(data) >= 17 and data[0:2] == b'\x00\x0f':
                        self.imei = data[2:17].decode()
                        self.server.register_client(self.imei, self)
                        if self.debug_settings.get('delay_imei_ack', 0.0) > 0:
                            delay = self.debug_settings['delay_imei_ack']
                            self.signals.log_message.emit(f"DEBUG: Delaying IMEI ACK for {self.imei} by {delay}s", "warn")
                            time.sleep(delay)
                        self.connection.send(b'\x01')
                    else:
                        self.signals.log_message.emit(f"Invalid first packet from {self.address}: {binascii.hexlify(data).decode()}", "warn")
                        break
                else:
                    decoded_data = decode_packet(data)
                    self.signals.data_received.emit(self.imei, data, decoded_data)
                    
                    if decoded_data and decoded_data.get('type') in ['Codec 8', 'Codec 8 Extended']:
                        num_records = decoded_data.get('record_count', 0)
                        if self.debug_settings.get('delay_record_ack', 0.0) > 0:
                            delay = self.debug_settings['delay_record_ack']
                            self.signals.log_message.emit(f"DEBUG: Delaying Record ACK for {self.imei} by {delay}s", "warn")
                            time.sleep(delay)
                        response = struct.pack('!I', num_records)
                        self.connection.send(response)

            except (ConnectionResetError, BrokenPipeError, ssl.SSLEOFError):
                break
            except ssl.SSLWantReadError:
                continue
            except Exception as e:
                self.signals.log_message.emit(f"Error handling client {self.address}: {e}", "error")
                break
        
        self.stop()

    def stop(self):
        if not self.is_running: return
        self.is_running = False
        if self.imei:
            # <<< MODIFIED: Pass 'self' to unregister, so it knows WHICH handler is stopping.
            self.server.unregister_client(self.imei, self)
        
        self.signals.log_message.emit(f"Connection closed for {self.address[0]} (IMEI: {self.imei})", "info")
        try:
            self.connection.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        self.connection.close()
        
    def send_command(self, command_bytes):
        if self.is_running:
            self.connection.send(command_bytes)


class TCPServer(QThread):
    log_message = Signal(str, str)
    device_connected = Signal(str, str)
    device_disconnected = Signal(str)
    data_received = Signal(str, bytes, object)

    def __init__(self, debug_settings):
        super().__init__()
        self.host = config.get('server.host')
        self.port = config.get('server.port')
        self.debug_settings = debug_settings
        self.sock = None
        self.is_running = False
        self.client_handlers = {}
        self.client_lock = threading.Lock()

    def run(self):
        # ... run method remains the same ...
        server_protocol = "TCP"
        self.is_running = True
        try:
            plain_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            plain_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            if config.get('tls.enabled', False):
                server_protocol = "TCP/TLS"
                self.log_message.emit("TLS is enabled. Attempting to create secure server...", "info")
                context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
                context.load_cert_chain(certfile=config.get('tls.root_cert_path'), keyfile=config.get('tls.key_path'))
                self.sock = context.wrap_socket(plain_socket, server_side=True)
            else:
                self.sock = plain_socket
            self.sock.bind((self.host, self.port))
            self.sock.listen(5)
            self.sock.settimeout(1.0)
        except Exception as e:
            self.log_message.emit(f"Failed to start server: {e}", "error")
            self.is_running = False
            return
            
        self.log_message.emit(f"Starting {server_protocol} server on {self.host}:{self.port}", "info")
        while self.is_running:
            try:
                conn, addr = self.sock.accept()
                client_thread = ClientHandler(conn, addr, self)
                client_thread.start()
            except socket.timeout:
                continue
            except Exception as e:
                if self.is_running:
                    self.log_message.emit(f"Server loop error: {e}", "error")
        
        for handler in list(self.client_handlers.values()):
            handler.stop()
        self.sock.close()
        self.log_message.emit("Server stopped.", "info")


    def stop(self):
        self.is_running = False
        self.wait()

    def register_client(self, imei, handler):
        with self.client_lock:
            self.client_handlers[imei] = handler
        self.device_connected.emit(imei, handler.address[0])

    # <<< MODIFIED: Changed method signature to accept the handler instance.
    def unregister_client(self, imei, handler_to_unregister):
        unregistered = False
        with self.client_lock:
            # <<< MODIFIED: Add a condition to ensure we only delete the correct handler.
            if imei in self.client_handlers and self.client_handlers[imei] is handler_to_unregister:
                del self.client_handlers[imei]
                unregistered = True
        
        if unregistered:
            self.device_disconnected.emit(imei)
    
    def kick_device(self, imei):
        handler_to_kick = None
        with self.client_lock:
            if imei in self.client_handlers:
                handler_to_kick = self.client_handlers[imei]
            else:
                self.log_message.emit(f"Could not kick: Device {imei} not found.", "error")

        if handler_to_kick:
            self.log_message.emit(f"DEBUG: Kicking device {imei}", "warn")
            handler_to_kick.stop()

    def send_command_to_device(self, imei, command_str):
        with self.client_lock:
            if imei in self.client_handlers:
                handler = self.client_handlers[imei]
                command_packet = encode_codec12_command(command_str)
                handler.send_command(command_packet)
            else:
                self.log_message.emit(f"Could not send command: Device {imei} not found.", "error")