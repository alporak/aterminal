"""
Teltonika GPS Server Module
Contains protocol parsing and server logic
"""

import socket
import threading
import time
import struct
import datetime
import select
from collections import defaultdict


class TeltonikaProtocol:
    """Complete Teltonika Protocol Parser supporting all codecs"""
    
    # Codec Constants
    CODEC_8 = 0x08
    CODEC_8E = 0x8E
    CODEC_12 = 0x0C
    CODEC_13 = 0x0D
    CODEC_14 = 0x0E
    CODEC_16 = 0x10
    CODEC_61 = 0x3D
    
    @staticmethod
    def crc16(data: bytes) -> int:
        """CRC16 calculation for Teltonika packets"""
        crc = 0
        poly = 0xA001
        for byte in data:
            crc ^= byte
            for _ in range(8):
                if crc & 1:
                    crc = (crc >> 1) ^ poly
                else:
                    crc >>= 1
        return crc
    
    @staticmethod
    def validate_data_packet(data_payload: bytes) -> bool:
        """Validate CRC of data packet"""
        if len(data_payload) < 5:
            return False
        
        received_crc = struct.unpack('!I', data_payload[-4:])[0]
        calc_data = data_payload[:-4]
        calculated_crc = TeltonikaProtocol.crc16(calc_data)
        
        return received_crc == calculated_crc
    
    @staticmethod
    def parse_tcp_packet(packet: bytes) -> dict:
        """Parse TCP packet (IMEI or Data)"""
        result = {'type': 'unknown', 'raw': packet.hex().upper()}
        
        try:
            # Check for IMEI packet (starts with 0x000F)
            if len(packet) >= 2 and packet[0:2] == b'\x00\x0F':
                if len(packet) == 17:  # 2 bytes length + 15 bytes IMEI
                    imei = packet[2:17].decode('ascii')
                    result = {
                        'type': 'imei',
                        'imei': imei,
                        'raw': packet.hex().upper()
                    }
                return result
            
            # Check for Data packet
            if len(packet) >= 12:
                preamble = struct.unpack('!I', packet[0:4])[0]
                data_len = struct.unpack('!I', packet[4:8])[0]
                
                if preamble == 0:  # Valid data packet preamble
                    codec_id = packet[8]
                    
                    # Extract payload (codec to CRC-4)
                    payload = packet[8:-4]
                    
                    if codec_id in [TeltonikaProtocol.CODEC_8, TeltonikaProtocol.CODEC_8E, TeltonikaProtocol.CODEC_16]:
                        # Parse AVL data
                        count1 = packet[9]
                        avl_data = payload[2:]  # Skip codec and count1
                        
                        records = TeltonikaProtocol.decode_avl_records(codec_id, avl_data, count1)
                        
                        result = {
                            'type': 'data',
                            'codec': f'0x{codec_id:02X}',
                            'count': count1,
                            'records': records,
                            'raw': packet.hex().upper()
                        }
                    
                    elif codec_id == TeltonikaProtocol.CODEC_12:
                        # Codec 12 - Commands/Responses
                        qty = packet[9]
                        cmd_type = packet[10]
                        
                        if cmd_type == 0x06:  # Response from device
                            # Extract response data
                            resp_len = struct.unpack('!I', packet[11:15])[0]
                            resp_data = packet[15:15+resp_len].decode('ascii', errors='ignore')
                            
                            result = {
                                'type': 'response',
                                'codec': 'Codec12',
                                'resp_type': cmd_type,
                                'response': resp_data,
                                'raw': packet.hex().upper()
                            }
                        else:
                            result = {
                                'type': 'codec12_data',
                                'codec': 'Codec12',
                                'raw': packet.hex().upper()
                            }
                    
                    elif codec_id == TeltonikaProtocol.CODEC_14:
                        # Codec 14
                        result = {
                            'type': 'codec14_data',
                            'codec': 'Codec14',
                            'raw': packet.hex().upper()
                        }
                    
        except Exception as e:
            result['error'] = str(e)
        
        return result
    
    @staticmethod
    def parse_udp_packet(packet: bytes) -> dict:
        """Parse UDP packet"""
        result = {'type': 'unknown', 'raw': packet.hex().upper()}
        
        try:
            if len(packet) < 5:
                return result
            
            # UDP Channel Header: Length(2) + PacketID(2) + NotUsed(1) + AVLPacketID(1) + IMEILen(2) + IMEI
            pkt_len = struct.unpack('!H', packet[0:2])[0]
            pkt_id = struct.unpack('!H', packet[2:4])[0]
            not_used = packet[4]
            
            offset = 5
            
            # Check if this looks like AVL data
            if offset < len(packet):
                avl_pkt_id = packet[offset]
                offset += 1
                
                # IMEI
                if offset + 2 <= len(packet):
                    imei_len = struct.unpack('!H', packet[offset:offset+2])[0]
                    offset += 2
                    
                    if offset + imei_len <= len(packet):
                        imei = packet[offset:offset+imei_len].decode('ascii')
                        offset += imei_len
                        
                        # Codec
                        if offset < len(packet):
                            codec_id = packet[offset]
                            offset += 1
                            
                            # Count
                            if offset < len(packet):
                                count = packet[offset]
                                offset += 1
                                
                                # AVL Records
                                avl_data = packet[offset:]
                                records = TeltonikaProtocol.decode_avl_records(codec_id, avl_data, count)
                                
                                result = {
                                    'type': 'data',
                                    'udp_id': pkt_id,
                                    'avl_id': avl_pkt_id,
                                    'imei': imei,
                                    'codec': f'0x{codec_id:02X}',
                                    'count': count,
                                    'records': records,
                                    'raw': packet.hex().upper()
                                }
        except Exception as e:
            result['error'] = str(e)
        
        return result
    
    @staticmethod
    def decode_avl_records(codec: int, data_bytes: bytes, count: int) -> list:
        """Decode AVL records from data"""
        records = []
        offset = 0
        
        try:
            for i in range(count):
                if offset + 15 > len(data_bytes):
                    break
                
                record = {}
                
                # Timestamp (8 bytes)
                timestamp_ms = struct.unpack('!Q', data_bytes[offset:offset+8])[0]
                offset += 8
                dt = datetime.datetime.fromtimestamp(timestamp_ms / 1000.0)
                record['Timestamp'] = dt.strftime('%Y-%m-%d %H:%M:%S')
                record['Timestamp_ms'] = timestamp_ms
                
                # Priority (1 byte)
                priority = data_bytes[offset]
                offset += 1
                record['Priority'] = priority
                
                # GPS Data (15 bytes)
                lon = struct.unpack('!i', data_bytes[offset:offset+4])[0] / 10000000.0
                offset += 4
                lat = struct.unpack('!i', data_bytes[offset:offset+4])[0] / 10000000.0
                offset += 4
                alt = struct.unpack('!h', data_bytes[offset:offset+2])[0]
                offset += 2
                angle = struct.unpack('!H', data_bytes[offset:offset+2])[0]
                offset += 2
                sat = data_bytes[offset]
                offset += 1
                speed = struct.unpack('!H', data_bytes[offset:offset+2])[0]
                offset += 2
                
                record['Longitude'] = lon
                record['Latitude'] = lat
                record['Altitude'] = alt
                record['Angle'] = angle
                record['Satellites'] = sat
                record['Speed'] = speed
                
                # IO Elements
                if offset >= len(data_bytes):
                    records.append(record)
                    continue
                
                event_id = data_bytes[offset]
                offset += 1
                record['Event_ID'] = event_id
                
                if offset >= len(data_bytes):
                    records.append(record)
                    continue
                
                total_io = data_bytes[offset]
                offset += 1
                record['Total_IO'] = total_io
                
                io_data = {}
                
                # Helper function to read IO elements
                def read_io_section(byte_width):
                    nonlocal offset
                    if offset >= len(data_bytes):
                        return
                    
                    count_io = data_bytes[offset]
                    offset += 1
                    
                    for _ in range(count_io):
                        if offset >= len(data_bytes):
                            return
                        
                        io_id = data_bytes[offset]
                        offset += 1
                        
                        if offset + byte_width > len(data_bytes):
                            return
                        
                        if byte_width == 1:
                            val = data_bytes[offset]
                            offset += 1
                        elif byte_width == 2:
                            val = struct.unpack('!H', data_bytes[offset:offset+2])[0]
                            offset += 2
                        elif byte_width == 4:
                            val = struct.unpack('!I', data_bytes[offset:offset+4])[0]
                            offset += 4
                        elif byte_width == 8:
                            val = struct.unpack('!Q', data_bytes[offset:offset+8])[0]
                            offset += 8
                        
                        io_data[f'IO_{io_id}'] = val
                
                # Read 1, 2, 4, 8 byte IO elements
                read_io_section(1)
                read_io_section(2)
                read_io_section(4)
                read_io_section(8)
                
                record['IO_Data'] = io_data
                records.append(record)
        
        except Exception as e:
            pass  # Partial decode is ok
        
        return records
    
    @staticmethod
    def build_tcp_command(cmd_text: str) -> bytes:
        """Build Codec12 TCP command packet"""
        data = cmd_text.encode('ascii')
        data_len = len(data)
        
        # Build Payload
        payload = struct.pack('B', TeltonikaProtocol.CODEC_12)  # Codec
        payload += struct.pack('B', 1)  # Quantity 1
        payload += struct.pack('B', 0x05)  # Type (Command)
        payload += struct.pack('!I', data_len)  # Command length
        payload += data  # Command data
        payload += struct.pack('B', 1)  # Quantity 2
        
        # Calculate CRC
        crc = TeltonikaProtocol.crc16(payload)
        
        # Build full packet
        packet = struct.pack('!I', 0)  # Preamble
        packet += struct.pack('!I', len(payload))  # Data length
        packet += payload
        packet += struct.pack('!I', crc)  # CRC
        
        return packet
    
    @staticmethod
    def build_udp_ack(packet_id: int, avl_packet_id: int, count: int) -> bytes:
        """Build UDP ACK packet"""
        resp = struct.pack('!H', 5)  # Length
        resp += struct.pack('!H', packet_id)  # Packet ID
        resp += b'\x01'  # Type
        resp += struct.pack('B', avl_packet_id)  # AVL Packet ID
        resp += struct.pack('B', count)  # Count
        return resp


class TeltonikaServer:
    """Teltonika GPS Server with TCP and UDP support"""
    
    def __init__(self, tcp_port=8000, udp_port=8001):
        self.tcp_port = tcp_port
        self.udp_port = udp_port
        self.running = False
        
        # TCP State
        self.tcp_socket = None
        self.tcp_clients = {}  # socket -> address
        self.tcp_imei = {}  # socket -> IMEI
        self.tcp_buffers = {}  # socket -> buffer
        
        # UDP State
        self.udp_socket = None
        self.udp_clients = {}  # IMEI -> address
        
        # Data Storage
        self.parsed_records = []  # List of parsed records
        self.raw_messages = []  # List of raw messages
        self.log_messages = []  # List of log messages
        self.command_history = []  # List of command/response pairs
        
        # Command Queues
        self.scheduled_commands = defaultdict(list)  # IMEI -> [commands]
        self.pending_test_sequences = {}  # socket/IMEI -> (command, count, sent)
        self.pending_commands = {}  # Track commands awaiting response: key -> {imei, command, sent_time, protocol}
        
        # Interval command control
        self.interval_stop_flag = {}  # IMEI -> bool (stop request)
        self.interval_last_record = {}  # IMEI -> timestamp of last record
        
        # Locks
        self.lock = threading.Lock()
    
    def log(self, direction: str, message: str, msg_type: str = "INFO"):
        """Add log message"""
        timestamp = datetime.datetime.now().strftime('%H:%M:%S.%f')[:-3]
        log_entry = {
            'timestamp': timestamp,
            'direction': direction,
            'type': msg_type,
            'message': message
        }
        with self.lock:
            self.log_messages.insert(0, log_entry)
            if len(self.log_messages) > 500:
                self.log_messages = self.log_messages[:500]
    
    def add_raw_message(self, direction: str, data: bytes, protocol: str):
        """Add raw message"""
        timestamp = datetime.datetime.now().strftime('%H:%M:%S.%f')[:-3]
        raw_entry = {
            'timestamp': timestamp,
            'direction': direction,
            'protocol': protocol,
            'hex': data.hex().upper(),
            'length': len(data)
        }
        with self.lock:
            self.raw_messages.insert(0, raw_entry)
            if len(self.raw_messages) > 500:
                self.raw_messages = self.raw_messages[:500]
    
    def start(self):
        """Start the server"""
        if self.running:
            return
        
        self.running = True
        
        # Start TCP Server
        tcp_thread = threading.Thread(target=self._tcp_server_thread, daemon=True)
        tcp_thread.start()
        
        # Start UDP Server
        udp_thread = threading.Thread(target=self._udp_server_thread, daemon=True)
        udp_thread.start()
        
        self.log("SYS", f"Server started - TCP:{self.tcp_port}, UDP:{self.udp_port}", "START")
    
    def stop(self):
        """Stop the server"""
        self.running = False
        
        # Close TCP
        if self.tcp_socket:
            try:
                self.tcp_socket.close()
            except:
                pass
        
        # Close UDP
        if self.udp_socket:
            try:
                self.udp_socket.close()
            except:
                pass
        
        self.log("SYS", "Server stopped", "STOP")
    
    def _tcp_server_thread(self):
        """TCP server thread"""
        try:
            self.tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.tcp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.tcp_socket.bind(('0.0.0.0', self.tcp_port))
            self.tcp_socket.listen(5)
            self.tcp_socket.setblocking(False)
            
            self.log("TCP", f"Listening on port {self.tcp_port}", "LISTEN")
            
            while self.running:
                try:
                    # Build list of sockets to check
                    readable_sockets = [self.tcp_socket] + list(self.tcp_clients.keys())
                    
                    readable, _, exceptional = select.select(readable_sockets, [], readable_sockets, 1.0)
                    
                    for s in readable:
                        if s is self.tcp_socket:
                            # New connection
                            try:
                                client, addr = self.tcp_socket.accept()
                                client.setblocking(False)
                                with self.lock:
                                    self.tcp_clients[client] = addr
                                    self.tcp_buffers[client] = b''
                                self.log("TCP", f"New connection from {addr[0]}:{addr[1]}", "CONN")
                            except:
                                pass
                        else:
                            # Existing client
                            try:
                                data = s.recv(4096)
                                if data:
                                    with self.lock:
                                        self.tcp_buffers[s] += data
                                    self.add_raw_message("RX", data, "TCP")
                                    self._process_tcp_buffer(s)
                                else:
                                    # Disconnected
                                    self._close_tcp(s)
                            except ConnectionResetError:
                                self._close_tcp(s)
                            except:
                                pass
                    
                    for s in exceptional:
                        self._close_tcp(s)
                
                except Exception as e:
                    if self.running:
                        self.log("ERR", f"TCP Error: {e}", "ERROR")
                    time.sleep(0.1)
        
        except Exception as e:
            self.log("ERR", f"TCP Server Error: {e}", "ERROR")
    
    def _process_tcp_buffer(self, sock):
        """Process TCP buffer and extract packets"""
        with self.lock:
            buff = self.tcp_buffers[sock]
        
        while True:
            if len(buff) == 0:
                break
            
            # Check for IMEI packet (starts with 0x00 0x0F)
            if len(buff) >= 2 and buff[0:2] == b'\x00\x0F':
                if len(buff) >= 17:  # 2 + 15 bytes
                    packet = buff[0:17]
                    buff = buff[17:]
                    
                    # Parse IMEI
                    info = TeltonikaProtocol.parse_tcp_packet(packet)
                    if info['type'] == 'imei':
                        imei = info['imei']
                        with self.lock:
                            self.tcp_imei[sock] = imei
                            self.tcp_buffers[sock] = buff
                        
                        self.log("RX", f"IMEI: {imei}", "IMEI")
                        
                        # Send IMEI ACK (0x01)
                        try:
                            sock.send(b'\x01')
                            self.add_raw_message("TX", b'\x01', "TCP")
                            self.log("TX", "IMEI ACK (0x01)", "ACK")
                        except:
                            self._close_tcp(sock)
                            return
                        
                        # Check for scheduled commands
                        self._check_scheduled_commands(sock, imei)
                    
                    continue
                else:
                    # Wait for more data
                    break
            
            # Check for Data packet
            elif len(buff) >= 12:
                try:
                    preamble = struct.unpack('!I', buff[0:4])[0]
                    data_len = struct.unpack('!I', buff[4:8])[0]
                    
                    if preamble == 0 and data_len > 0 and data_len < 10000:
                        # Looks like valid packet
                        total_len = 8 + data_len + 4  # Preamble + Length + Data + CRC
                        
                        if len(buff) >= total_len:
                            packet = buff[0:total_len]
                            buff = buff[total_len:]
                            
                            # Validate CRC
                            payload_plus_crc = packet[8:]
                            if TeltonikaProtocol.validate_data_packet(payload_plus_crc):
                                # Parse packet
                                info = TeltonikaProtocol.parse_tcp_packet(packet)
                                
                                if info['type'] == 'data':
                                    count = info['count']
                                    self.log("RX", f"Data packet: {count} records (Codec: {info['codec']})", "DATA")
                                    
                                    # Store records
                                    if 'records' in info and info['records']:
                                        imei = self.tcp_imei.get(sock, "Unknown")
                                        with self.lock:
                                            for rec in info['records']:
                                                rec['IMEI'] = imei
                                                rec['Protocol'] = 'TCP'
                                                self.parsed_records.insert(0, rec)
                                            if len(self.parsed_records) > 1000:
                                                self.parsed_records = self.parsed_records[:1000]
                                            
                                            # Update last record timestamp for interval commands
                                            if imei and imei != 'Unknown':
                                                self.interval_last_record[imei] = datetime.datetime.now()
                                    
                                    # Send DATA ACK (number of records as 4-byte integer)
                                    ack = struct.pack('!I', count)
                                    try:
                                        sock.send(ack)
                                        self.add_raw_message("TX", ack, "TCP")
                                        self.log("TX", f"Data ACK ({count} records)", "ACK")
                                    except:
                                        self._close_tcp(sock)
                                        with self.lock:
                                            self.tcp_buffers[sock] = buff
                                        return
                                    
                                    # Check for scheduled commands after receiving data
                                    imei = self.tcp_imei.get(sock, None)
                                    if imei:
                                        self._check_scheduled_commands(sock, imei)
                                
                                elif info['type'] == 'response':
                                    response_text = info.get('response', 'No response data')
                                    self.log("RX", f"Response: {response_text}", "RESP")
                                    
                                    # Match with pending command
                                    imei = self.tcp_imei.get(sock, "Unknown")
                                    self._record_command_response(imei, response_text, "TCP")
                                
                                with self.lock:
                                    self.tcp_buffers[sock] = buff
                                continue
                            else:
                                self.log("ERR", f"CRC validation failed", "CRC")
                                # Skip this packet
                                buff = buff[total_len:]
                                with self.lock:
                                    self.tcp_buffers[sock] = buff
                                continue
                        else:
                            # Wait for more data
                            break
                    else:
                        # Invalid header, skip 1 byte
                        buff = buff[1:]
                        with self.lock:
                            self.tcp_buffers[sock] = buff
                        continue
                except:
                    # Error parsing, skip 1 byte
                    buff = buff[1:]
                    with self.lock:
                        self.tcp_buffers[sock] = buff
                    continue
            else:
                # Not enough data
                if len(buff) > 4096:
                    # Clear buffer if too large
                    self.log("ERR", "Buffer overflow, clearing", "ERR")
                    buff = b''
                    with self.lock:
                        self.tcp_buffers[sock] = buff
                break
        
        with self.lock:
            self.tcp_buffers[sock] = buff
    
    def _check_scheduled_commands(self, sock, imei):
        """Check and send scheduled commands for an IMEI via TCP"""
        # Get commands while holding lock
        commands_to_send = []
        with self.lock:
            if imei in self.scheduled_commands and len(self.scheduled_commands[imei]) > 0:
                commands_to_send = self.scheduled_commands[imei].copy()
                self.scheduled_commands[imei] = []
        
        # Send commands without holding lock
        for cmd in commands_to_send:
            self._send_tcp_command(sock, cmd, imei)
    
    def _check_scheduled_commands_udp(self, addr, imei):
        """Check and send scheduled commands for an IMEI via UDP"""
        # Get commands while holding lock
        commands_to_send = []
        with self.lock:
            if imei in self.scheduled_commands and len(self.scheduled_commands[imei]) > 0:
                commands_to_send = self.scheduled_commands[imei].copy()
                self.scheduled_commands[imei] = []
        
        # Send commands without holding lock
        for cmd in commands_to_send:
            self._send_udp_command(addr, cmd, imei)
    
    def _record_command_response(self, imei: str, response: str, protocol: str):
        """Match response with pending command and record in history"""
        with self.lock:
            # Find oldest pending command for this IMEI
            matched_cmd = None
            matched_key = None
            oldest_time = None
            
            for key, cmd_info in self.pending_commands.items():
                if cmd_info['imei'] == imei:
                    if oldest_time is None or cmd_info['sent_time'] < oldest_time:
                        oldest_time = cmd_info['sent_time']
                        matched_cmd = cmd_info
                        matched_key = key
            
            # Record in history
            history_entry = {
                'timestamp': datetime.datetime.now().strftime('%H:%M:%S.%f')[:-3],
                'imei': imei,
                'command': matched_cmd['command'] if matched_cmd else 'Unknown',
                'response': response,
                'protocol': protocol,
                'duration_ms': int((datetime.datetime.now() - matched_cmd['sent_time']).total_seconds() * 1000) if matched_cmd else 0
            }
            
            self.command_history.insert(0, history_entry)
            if len(self.command_history) > 500:
                self.command_history = self.command_history[:500]
            
            # Remove matched command from pending
            if matched_key:
                del self.pending_commands[matched_key]
    
    def _close_tcp(self, client):
        """Close TCP client connection"""
        with self.lock:
            if client in self.tcp_clients:
                addr = self.tcp_clients[client]
                del self.tcp_clients[client]
                if client in self.tcp_imei:
                    del self.tcp_imei[client]
                if client in self.tcp_buffers:
                    del self.tcp_buffers[client]
                try:
                    client.close()
                except:
                    pass
                self.log("TCP", f"Disconnected: {addr[0]}:{addr[1]}", "DISC")
    
    def _udp_server_thread(self):
        """UDP server thread"""
        try:
            self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.udp_socket.bind(('0.0.0.0', self.udp_port))
            self.udp_socket.setblocking(False)
            
            self.log("UDP", f"Listening on port {self.udp_port}", "LISTEN")
            
            while self.running:
                try:
                    readable, _, _ = select.select([self.udp_socket], [], [], 1.0)
                    
                    if readable:
                        data, addr = self.udp_socket.recvfrom(4096)
                        
                        self.add_raw_message("RX", data, "UDP")
                        self.log("RX", f"UDP packet from {addr[0]}:{addr[1]} ({len(data)} bytes)", "UDP")
                        
                        # Try parsing as standard UDP packet first
                        info = TeltonikaProtocol.parse_udp_packet(data)
                        
                        # If unknown, try parsing as TCP packet (for Codec12 responses via UDP)
                        if info['type'] == 'unknown' and len(data) >= 12:
                            info = TeltonikaProtocol.parse_tcp_packet(data)
                            if info['type'] == 'response':
                                # Codec12 response via UDP
                                response_text = info.get('response', 'No response data')
                                self.log("RX", f"Response via UDP: {response_text}", "RESP")
                                
                                # Try to find IMEI from recent UDP clients with this address
                                imei = None
                                with self.lock:
                                    for client_imei, client_addr in self.udp_clients.items():
                                        if client_addr == addr:
                                            imei = client_imei
                                            break
                                
                                if imei:
                                    self._record_command_response(imei, response_text, "UDP")
                                continue
                        
                        if info['type'] == 'data':
                            imei = info.get('imei', 'Unknown')
                            count = info['count']
                            
                            self.log("RX", f"IMEI: {imei}, {count} records (Codec: {info['codec']})", "DATA")
                            
                            # Update last record timestamp for interval commands
                            if imei and imei != 'Unknown':
                                with self.lock:
                                    self.interval_last_record[imei] = datetime.datetime.now()
                            
                            # Store records
                            if 'records' in info and info['records']:
                                with self.lock:
                                    for rec in info['records']:
                                        rec['IMEI'] = imei
                                        rec['Protocol'] = 'UDP'
                                        self.parsed_records.insert(0, rec)
                                    if len(self.parsed_records) > 1000:
                                        self.parsed_records = self.parsed_records[:1000]
                            
                            # Update UDP client table
                            if imei:
                                with self.lock:
                                    self.udp_clients[imei] = addr
                            
                            # Send UDP ACK
                            ack = TeltonikaProtocol.build_udp_ack(
                                info['udp_id'],
                                info['avl_id'],
                                count
                            )
                            self.udp_socket.sendto(ack, addr)
                            self.add_raw_message("TX", ack, "UDP")
                            self.log("TX", f"UDP ACK (ID: {info['udp_id']}, Count: {count})", "ACK")
                            
                            # Check for scheduled commands after sending ACK
                            if imei:
                                self._check_scheduled_commands_udp(addr, imei)
                
                except Exception as e:
                    if self.running:
                        pass  # Ignore timeout errors
                    time.sleep(0.1)
        
        except Exception as e:
            self.log("ERR", f"UDP Server Error: {e}", "ERROR")
    
    def send_tcp_command(self, imei: str, command: str, silent_fail=False):
        """Send TCP command to device by IMEI"""
        # Find socket by IMEI
        sock = None
        with self.lock:
            for s, client_imei in self.tcp_imei.items():
                if client_imei == imei:
                    sock = s
                    break
        
        if sock:
            self._send_tcp_command(sock, command, imei)
            return True
        else:
            if not silent_fail:
                self.log("ERR", f"No active TCP connection for IMEI: {imei}", "ERROR")
            return False
    
    def _send_tcp_command(self, sock, command: str, imei: str):
        """Send TCP command to specific socket"""
        try:
            packet = TeltonikaProtocol.build_tcp_command(command)
            sock.send(packet)
            self.add_raw_message("TX", packet, "TCP")
            self.log("TX", f"Command: {command}", "CMD")
            
            # Track command for response matching
            cmd_id = f"{imei}_{datetime.datetime.now().timestamp()}"
            with self.lock:
                self.pending_commands[cmd_id] = {
                    'imei': imei,
                    'command': command,
                    'sent_time': datetime.datetime.now(),
                    'protocol': 'TCP'
                }
        except Exception as e:
            self.log("ERR", f"Failed to send command: {e}", "ERROR")
    
    def send_udp_command(self, imei: str, command: str, silent_fail=False):
        """Send UDP command to device by IMEI"""
        # Find address by IMEI
        addr = None
        with self.lock:
            addr = self.udp_clients.get(imei)
        
        if addr:
            self._send_udp_command(addr, command, imei)
            return True
        else:
            if not silent_fail:
                self.log("ERR", f"No active UDP connection for IMEI: {imei}", "ERROR")
            return False
    
    def _send_udp_command(self, addr, command: str, imei: str):
        """Send UDP command to specific address"""
        try:
            packet = TeltonikaProtocol.build_tcp_command(command)
            self.udp_socket.sendto(packet, addr)
            self.add_raw_message("TX", packet, "UDP")
            self.log("TX", f"Command: {command}", "CMD")
            
            # Track command for response matching
            cmd_id = f"{imei}_{datetime.datetime.now().timestamp()}"
            with self.lock:
                self.pending_commands[cmd_id] = {
                    'imei': imei,
                    'command': command,
                    'sent_time': datetime.datetime.now(),
                    'protocol': 'UDP'
                }
        except Exception as e:
            self.log("ERR", f"Failed to send UDP command: {e}", "ERROR")
    
    def send_command(self, imei: str, command: str):
        """Send command to device (auto-detect TCP or UDP)"""
        # Try TCP first (silent fail)
        if self.send_tcp_command(imei, command, silent_fail=True):
            return True
        # Try UDP if TCP failed
        if self.send_udp_command(imei, command, silent_fail=False):
            return True
        return False
    
    def schedule_command(self, imei: str, command: str):
        """Schedule a command to be sent when device next connects/sends data"""
        with self.lock:
            self.scheduled_commands[imei].append(command)
        self.log("SYS", f"Scheduled command for {imei}: {command}", "SCHEDULE")
    
    def is_device_connected(self, imei: str) -> bool:
        """Check if device is currently connected"""
        with self.lock:
            # Check TCP connections
            for sock, client_imei in self.tcp_imei.items():
                if client_imei == imei and sock in self.tcp_clients:
                    return True
            
            # Check UDP connections (consider connected if seen recently)
            if imei in self.udp_clients:
                return True
        
        return False
    
    def stop_interval_command(self, imei: str):
        """Request stop for running interval command"""
        with self.lock:
            self.interval_stop_flag[imei] = True
        self.log("SYS", f"Stop requested for interval command on {imei}", "INFO")
    
    def send_command_with_interval(self, imei: str, command: str, 
                                   interval_sec: float = 0, duration_sec: float = 0,
                                   protocol: str = 'auto', wait_for_record: bool = False):
        """Send GPRS command with interval and duration support (replicates dataServer.js sendGprsCommand)
        
        Args:
            imei: Device IMEI
            command: Command string (e.g., 'getinfo')
            interval_sec: Interval between sends in seconds (0 = send once)
            duration_sec: Total duration to send commands in seconds (0 = send once)
            protocol: 'auto', 'TCP', or 'UDP'
            wait_for_record: If True, only send after device sends a record (like scheduler)
        
        Returns:
            dict with result info: {'success': bool, 'commands_sent': int, 'errors': [], 'stopped': bool}
        """
        import time
        from datetime import datetime, timedelta
        
        # Clear stop flag at start
        with self.lock:
            self.interval_stop_flag[imei] = False
        
        result = {
            'success': True,
            'commands_sent': 0,
            'errors': [],
            'stopped': False
        }
        
        send_once = interval_sec == 0 or duration_sec == 0
        
        # Check if device is connected
        if not self.is_device_connected(imei):
            error_msg = f"Device {imei} is not connected"
            self.log("ERR", error_msg, "ERROR")
            result['success'] = False
            result['errors'].append(error_msg)
            return result
        
        start_time = datetime.now()
        end_time = start_time + timedelta(seconds=duration_sec)
        cycle_count = 0
        
        mode_str = "with wait-for-record" if wait_for_record else "standard"
        self.log("SYS", f"Starting interval command loop ({mode_str}): cmd={command}, interval={interval_sec}s, duration={duration_sec}s", "INFO")
        
        try:
            while True:
                elapsed = (datetime.now() - start_time).total_seconds()
                
                # Check stop flag
                with self.lock:
                    if self.interval_stop_flag.get(imei, False):
                        result['stopped'] = True
                        self.log("SYS", f"Interval command loop stopped by user at cycle {cycle_count}", "INFO")
                        break
                
                # Check if we should continue
                if not send_once and datetime.now() >= end_time:
                    break
                
                cycle_count += 1
                
                # Wait for record mode (like scheduler behavior)
                if wait_for_record:
                    # Wait for device to send a record
                    record_timeout = 60  # 60 seconds timeout for record
                    record_wait_start = datetime.now()
                    
                    with self.lock:
                        last_record_time = self.interval_last_record.get(imei)
                    
                    # If no record yet, or if last record was before this cycle started
                    if not last_record_time or last_record_time < start_time:
                        self.log("SYS", f"Waiting for record from {imei} before sending command...", "INFO")
                        
                        while (datetime.now() - record_wait_start).total_seconds() < record_timeout:
                            # Check stop flag while waiting
                            with self.lock:
                                if self.interval_stop_flag.get(imei, False):
                                    result['stopped'] = True
                                    self.log("SYS", "Stopped while waiting for record", "INFO")
                                    return result
                                
                                last_record_time = self.interval_last_record.get(imei)
                            
                            # Check if new record received
                            if last_record_time and last_record_time > record_wait_start:
                                self.log("SYS", f"Record received from {imei}, proceeding with command", "INFO")
                                break
                            
                            time.sleep(0.5)  # Check every 500ms
                        else:
                            # Timeout waiting for record
                            error_msg = f"Timeout waiting for record from {imei} at cycle {cycle_count}"
                            self.log("WARN", error_msg, "WARNING")
                            result['errors'].append(error_msg)
                            
                            # Skip this cycle
                            if send_once:
                                break
                            continue
                
                # Check connection status
                if not self.is_device_connected(imei):
                    error_msg = f"Device {imei} disconnected at cycle {cycle_count}"
                    self.log("WARN", error_msg, "WARNING")
                    result['errors'].append(error_msg)
                    
                    if not wait_for_record:
                        # If not in wait mode, stop the loop
                        break
                    else:
                        # In wait mode, wait for reconnection
                        time.sleep(5)
                        continue
                
                # Check if UDP address still valid (detect NAT timeout)
                if protocol.upper() == 'UDP' or (protocol == 'auto' and imei in self.udp_clients):
                    with self.lock:
                        udp_addr = self.udp_clients.get(imei)
                    
                    if not udp_addr:
                        error_msg = f"Lost UDP reference for {imei} at cycle {cycle_count}. NAT timeout likely occurred."
                        self.log("WARN", error_msg, "WARNING")
                        result['errors'].append(error_msg)
                
                # Send command based on protocol
                success = False
                if protocol.upper() == 'TCP':
                    success = self.send_tcp_command(imei, command, silent_fail=False)
                elif protocol.upper() == 'UDP':
                    success = self.send_udp_command(imei, command, silent_fail=False)
                else:  # auto
                    success = self.send_command(imei, command)
                
                if success:
                    result['commands_sent'] += 1
                else:
                    result['errors'].append(f"Failed to send at {elapsed:.1f}s (cycle {cycle_count})")
                
                # If sending once, break after first send
                if send_once:
                    break
                
                # Calculate precise sleep time to maintain interval timing
                next_cycle_target = cycle_count * interval_sec
                elapsed_now = (datetime.now() - start_time).total_seconds()
                sleep_time = next_cycle_target - elapsed_now
                
                if sleep_time > 0:
                    time.sleep(sleep_time)
        
        except Exception as e:
            result['success'] = False
            result['errors'].append(str(e))
            self.log("ERR", f"send_command_with_interval error: {e}", "ERROR")
        
        total_time = (datetime.now() - start_time).total_seconds()
        self.log("SYS", 
                f"Interval command loop completed: sent {result['commands_sent']} commands to {imei} "
                f"over {total_time:.1f}s", "INFO")
        
        return result
    
    def get_connected_devices(self):
        """Get list of connected devices"""
        devices = []
        with self.lock:
            # TCP devices
            for sock, imei in self.tcp_imei.items():
                if sock in self.tcp_clients:
                    addr = self.tcp_clients[sock]
                    devices.append({
                        'IMEI': imei,
                        'Protocol': 'TCP',
                        'Address': f"{addr[0]}:{addr[1]}",
                        'Status': 'Connected'
                    })
            
            # UDP devices (recent)
            for imei, addr in self.udp_clients.items():
                devices.append({
                    'IMEI': imei,
                    'Protocol': 'UDP',
                    'Address': f"{addr[0]}:{addr[1]}",
                    'Status': 'Recent'
                })
        
        return devices