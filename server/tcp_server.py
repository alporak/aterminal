import socket
import threading
from PySide6.QtCore import QThread, Signal
from core.config_manager import config
from protocols.codec import decode_packet # Protocol decoder function

class ClientHandler(threading.Thread):
    """Handles an individual client connection."""
    def __init__(self, connection, address, server_signals):
        super().__init__()
        self.connection = connection
        self.address = address
        self.signals = server_signals
        self.imei = None
        self.is_running = True

    def run(self):
        self.signals.log_message.emit(f"New connection from {self.address[0]}:{self.address[1]}", "info")
        
        while self.is_running:
            try:
                data = self.connection.recv(4096)
                if not data:
                    break # Connection closed by client
                
                # First packet is likely the IMEI
                if not self.imei:
                    # Simple IMEI check (replace with robust logic from original script)
                    if len(data) == 17 and data[0:2] == b'\x00\x0f':
                        self.imei = data[2:].decode()
                        self.signals.device_connected.emit(self.imei, self.address[0])
                        # Send acknowledgment (0x01)
                        self.connection.send(b'\x01')
                    else:
                        self.signals.log_message.emit(f"Invalid first packet from {self.address}", "warn")
                        break
                else:
                    # Process subsequent data packets
                    decoded_data = decode_packet(data)
                    self.signals.data_received.emit(self.imei, data, decoded_data)
                    
                    # Example: Send back number of records received
                    # This logic needs to be fully ported from the original script
                    if decoded_data and 'record_count' in decoded_data:
                        response = b'\x00\x00\x00' + decoded_data['record_count'].to_bytes(1, 'big')
                        self.connection.send(response)

            except ConnectionResetError:
                break
            except Exception as e:
                self.signals.log_message.emit(f"Error handling client {self.address}: {e}", "error")
                break
        
        self.stop()

    def stop(self):
        self.is_running = False
        if self.imei:
            self.signals.device_disconnected.emit(self.imei)
        self.signals.log_message.emit(f"Connection closed for {self.address}", "info")
        self.connection.close()
        
    def send_command(self, command_bytes):
        self.connection.send(command_bytes)


class TCPServer(QThread):
    """Main TCP server thread that listens for and handles connections."""
    # Signals to communicate with the GUI
    log_message = Signal(str, str) # message, level
    device_connected = Signal(str, str) # imei, ip
    device_disconnected = Signal(str) # imei
    data_received = Signal(str, bytes, object) # imei, raw_data, decoded_data

    def __init__(self):
        super().__init__()
        self.host = config.get('server.host')
        self.port = config.get('server.port')
        self.sock = None
        self.is_running = False
        self.clients = {} # Maps IMEI to ClientHandler thread

    def run(self):
        self.log_message.emit(f"Starting TCP server on {self.host}:{self.port}", "info")
        self.is_running = True
        
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.sock.bind((self.host, self.port))
            self.sock.listen(5)
            self.sock.settimeout(1.0) # Timeout to allow checking `is_running` flag
        except Exception as e:
            self.log_message.emit(f"Failed to start server: {e}", "error")
            self.is_running = False
            return
            
        while self.is_running:
            try:
                conn, addr = self.sock.accept()
                client_thread = ClientHandler(conn, addr, self)
                # We need a way to map the thread before IMEI is known, or manage it post-identification
                client_thread.start()
            except socket.timeout:
                continue # Loop again to check is_running
            except Exception as e:
                if self.is_running:
                    self.log_message.emit(f"Server loop error: {e}", "error")
        
        self.sock.close()
        self.log_message.emit("Server stopped.", "info")

    def stop(self):
        self.is_running = False
        # Clean up client threads...
        self.wait() # Wait for the thread to finish

    def send_command_to_device(self, imei, command_str):
        # The full implementation would find the correct client handler and send the data
        pass