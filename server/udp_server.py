# server/udp_server.py

import socket
from PySide6.QtCore import QThread, Signal
from core.config_manager import config
from protocols.codec import decode_packet, encode_codec12_command

class UDPServer(QThread):
    """Main UDP server thread."""
    log_message = Signal(str, str)
    device_connected = Signal(str, str) # imei, ip (but connection is transient)
    data_received = Signal(str, bytes, object) # imei, raw_data, decoded_data
    
    def __init__(self):
        super().__init__()
        self.host = config.get('server.host')
        self.port = config.get('server.port')
        self.sock = None
        self.is_running = False
        self.clients = {} # Maps address (ip, port) to IMEI

    def run(self):
        self.log_message.emit(f"Starting UDP server on {self.host}:{self.port}", "info")
        self.is_running = True
        
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.sock.bind((self.host, self.port))
            self.sock.settimeout(1.0)
        except Exception as e:
            self.log_message.emit(f"Failed to start UDP server: {e}", "error")
            return
            
        while self.is_running:
            try:
                data, addr = self.sock.recvfrom(4096)
                
                # Identify device by IMEI inside the packet (if possible)
                # This logic needs to be robust based on Teltonika protocol
                
                imei = None
                # Simple check for IMEI packet
                if len(data) > 17 and data[0:2] == b'\x00\x0f':
                    imei = data[2:17].decode()
                    if addr not in self.clients:
                        self.clients[addr] = imei
                        self.device_connected.emit(imei, addr[0])
                    # Send ACK
                    self.sock.sendto(b'\x01', addr)
                else:
                    imei = self.clients.get(addr, f"Unknown@{addr[0]}")
                    decoded_data = decode_packet(data)
                    self.data_received.emit(imei, data, decoded_data)
                    
                    # Respond to AVL data packets
                    if decoded_data and decoded_data.get('type') in ['Codec 8', 'Codec 8 Extended']:
                        num_records = decoded_data.get('record_count', 0)
                        response = struct.pack('!I', num_records)
                        self.sock.sendto(response, addr)
                        
            except socket.timeout:
                continue
            except Exception as e:
                if self.is_running:
                    self.log_message.emit(f"UDP Server loop error: {e}", "error")
        
        self.sock.close()
        self.log_message.emit("UDP Server stopped.", "info")

    def stop(self):
        self.is_running = False
        self.wait()

    def send_command_to_device(self, imei, command_str):
        """Sends a command to a device with a known IMEI."""
        target_addr = None
        for addr, client_imei in self.clients.items():
            if client_imei == imei:
                target_addr = addr
                break
        
        if target_addr:
            command_packet = encode_codec12_command(command_str)
            self.sock.sendto(command_packet, target_addr)
            self.log_message.emit(f"Sent command '{command_str}' to {imei}", "info")
        else:
            self.log_message.emit(f"Could not send command: Device {imei} not found or address unknown.", "warn")