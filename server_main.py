'''
Created on Sep 10, 2012

@author: apolianskas.ar
'''
import time
import struct
import binascii
import datetime
import linecache
import sys
import socket
import select
import threading
import os
import ipgetter
import random as r
import st_comm as ST
import ssl
import json
from threading import Timer

# ===========================================
global C08
C08 = 0x08

global C8E
C8E = 0x8E

global C12
C12 = 0x0C  # 12 decimal

global C13
C13 = 0x0D  # 13 decimal

global C14
C14 = 0x0E  # 14 decimal

global C17
C17 = 0x11  # 17 decimal

global C32
C32 = 0x20  # 32 decimal

global C33
C33 = 0x21  # 33 decimal

global C34
C34 = 0x22  # 34 decimal FM63.Ver.25.xx.xx

global C36
C36 = 0x24

global C61
C61 = 0x3D  # 61 decimal

global C61E
C61E = 0x4B  # 0x3D + 0x0E

global C18
C18 = 0x18  # 24 decimal

global CMD5
CMD5 = 0x05  # Server -> FM

global GPRS_CMD_FM_TO_SERVER
GPRS_CMD_FM_TO_SERVER = 0x06  # Server <- FM

global GPRS_CMD_FM_TO_SERVER_nACK
GPRS_CMD_FM_TO_SERVER_nACK = 0x11  # Server <- FM

global GPRS_CMD_CAMERA_TO_FM
GPRS_CMD_CAMERA_TO_FM = 13  # 0x0D

global GPRS_CMD_SERVER_IXTP_TO_FM
GPRS_CMD_SERVER_IXTP_TO_FM = 0x21  # IXTP server -> FM

global GPRS_CMD_FM_IXTP_TO_SERVER_SOLO
GPRS_CMD_FM_IXTP_TO_SERVER_SOLO = 0x22  # IXTP server <- FM

global GPRS_CMD_FM_IXTP_TO_SERVER_P1
GPRS_CMD_FM_IXTP_TO_SERVER_P1 = 0x23  # IXTP server <- FM

global GPRS_CMD_FM_IXTP_TO_SERVER_P2
GPRS_CMD_FM_IXTP_TO_SERVER_P2 = 0x24  # IXTP server <- FM

global PSG_CNT_REC_RECEIVE
PSG_CNT_REC_RECEIVE = 0x60

global PSG_CNT_REC_RESPONSE
PSG_CNT_REC_RESPONSE = 0x61

global FMB_FT_FILE_RESUME_CMD_ID
FMB_FT_FILE_RESUME_CMD_ID = 2

global FMB_FT_FILE_REQ_CMD_ID
FMB_FT_FILE_REQ_CMD_ID = 8

global FMB_FT_FILE_CLOSE_SESSION_CMD_ID
FMB_FT_FILE_CLOSE_SESSION_CMD_ID = 0

global sender_running
sender_running = 0

global CMD_TYPE
CMD_TYPE = CMD5  # GPRS_CMD_SERVER_IXTP_TO_FM#CMD5

global TCP_TIMEOUT
TCP_TIMEOUT = 300

global block_nod_reply
block_nod_reply = 0

global reject_nod_reply
reject_nod_reply = 0

global waiting_for_multi
waiting_for_multi = 0

global temp
temp = ''

global skip
skip = False

global time_for_bad
time_for_bad = 0  # to generate bad responses all the time

global bad_pids
bad_pids = 255

global crc
crc = 0

global file_crc
file_crc = 0

global file_size
file_size = 0

global TCP
TCP = 0

global TLS
TLS = 0

global tls_root_cert
tls_root_cert = ""

global tls_key
tls_key = ""

global tcp_config_send
tcp_config_send = 0

global beltrans_server
beltrans_server = 0  # to use beltransputnik type server communication. Basically just answer to imei is different

global imei_resp_sent
imei_resp_sent = 0

# File sending parameters:
global FS_support
FS_support = 'NONE'

global FS_chunk_size
FS_chunk_size = 0

global FS_inv_crc_packet
FS_inv_crc_packet = -1

global FS_init_pos
FS_init_pos = 0

global FS_sent_packets
FS_sent_packets = 0

global FS_sent_size
FS_sent_size = 0

global FS_recalc_done
FS_recalc_done = False

global FS_sending
FS_sending = False

global FS_abort
FS_abort = False

global FS_filename
FS_filename = ''  # 'test.bin' 'test_short.bin'

global ipv6_support
ipv6_support = 0

global FS_file_path_list
FS_file_path_list = []

global FS_file_name_list
FS_file_name_list = []

global FS_file_upl_target
FS_file_upl_target = 0

global FW_file_name
FS_file_name = 0

global FS_test_reject
FS_test_reject = 0

global FS_packet_cnt
FS_packet_cnt = 0

global FS_packet_delay
FS_packet_delay = 0.1

global doubleanswer
doubleanswer = False

global ackTo_C12
ackTo_C12 = False

global FotaWeb
FotaWeb = 0

global FotaWeb_ST_communication
FotaWeb_ST_communication = 0

global FOTA_WEB_2401_par
FOTA_WEB_2401_par = 0

global nod_plus_gprs
nod_plus_gprs = 1

global custom_file_type
custom_file_type = 0

global file_type_to_send
file_type_to_send = 0

global fileDlOld
fileDlOld = 0

global files_to_dl
files_to_dl = 0

global c36_temp
c36_temp = []

global c36_first_half_size
c36_first_half_size = 0

global dwl_file_types
dwl_file_types = {'CUSTOM': 7,
                  'AGPS_MT3333': 8,
                  'OBD': 9,
                  'AGPS_QL89': 10,
                  'QL89_GPS_FW': 11,
                  'CAN_FW': 12,
                  'BLE_FW': 13,
                  'CARRIER_APX_FW': 14,
                  'ADAS_FW': 15,
                  'MT3333_DA': 16,
                  'MT3333_FW': 17}

global instant_codec14_reply
instant_codec14_reply = False

global instant_codec14_reply_delay_ms
instant_codec14_reply_delay_ms = 0

# END of File sending parameters
global main_file

msg = ''
# ===========================================
test = 0
juliui_no_reply_7013 = 0
# ===========================================
new = '3.2'  # Python version
VC = sys.winver
# ===========================================
global SERVER_VERSION
SERVER_VERSION = '00.88'
# ===========================================
gprs_commands = ['#GET VERSION', '#GET IMSI', '#GET NETWORK']
GPRS_0C_SENDER = 0  # regular codec 0x0C commands
GPRS_0D_SENDER_ = 1  # camera codec 0x0D commands

# ===========================================


class DataStatistics():

    def __init__(self, data_out):
        self.bytes_per_session = 0
        self.bytes_per_sec = 0
        self.bytes_per_10sec = 0
        self.bytes_per_60sec = 0
        self.ts_for_10sec = 0
        self.ts_for_60sec = 0
        self.total_data = 0
        self.session_start_ts = 0

        self.display_ts = 0
        self.data_out = data_out

        self._timer = None
        self.is_running = False

    def _run(self):
        self.is_running = False
        self._start()
        self._timer_1s_event()

    def _start(self):
        if not self.is_running:
            self._timer = Timer(1, self._run)
            self._timer.start()
            self.is_running = True

    def _timer_1s_event(self):
        ts = datetime.datetime.now().timestamp()
        if (ts - self.display_ts) > 60:
            self.display_ts = ts
            self.print_statistics()

        if (ts - self.ts_for_60sec) > 60:
            self.bytes_per_60sec = 0
            self.ts_for_60sec = ts

        if (ts - self.ts_for_10sec) > 10:
            self.bytes_per_10sec = 0
            self.ts_for_10sec = ts

        self.bytes_per_sec = 0

    def stop(self):
        if self._timer:
            self._timer.cancel()
            self.is_running = False

    def connection_closed(self):
        self.stop()
        self.print_statistics()
        self.bytes_per_session = 0
        self.bytes_per_sec = 0
        self.bytes_per_10sec = 0
        self.ts_for_10sec = 0
        self.bytes_per_60sec = 0
        self.ts_for_60sec = 0
        self.session_start_ts = 0

    def received_bytes(self, data_size):
        if self.is_running == False:
            ts = datetime.datetime.now().timestamp()
            self.session_start_ts = ts
            self.ts_for_10sec = ts
            self.ts_for_60sec = ts
            self._start()

        self.bytes_per_session += data_size
        self.bytes_per_sec += data_size
        self.bytes_per_10sec += data_size
        self.bytes_per_60sec += data_size

    def print_statistics(self):
        session_duration = 0
        curr_ts = datetime.datetime.now().timestamp()
        if self.session_start_ts != 0:
            session_duration = curr_ts - self.session_start_ts

        kb_s = self.bytes_per_sec/1024
        dur_10sec = curr_ts - self.ts_for_10sec
        dur_60sec = curr_ts - self.ts_for_60sec
        avg_kb_s_10 = self.bytes_per_10sec/1024/dur_10sec
        avg_kb_s_60 = self.bytes_per_60sec/1024/dur_60sec

        self.data_out(
            f" >> Rx Data Statistics:\r\n\tTotal bytes received {self.bytes_per_session}, Connection duration: {session_duration:.1f}sec\r\n"
            f"\tLast  1 sec: {kb_s:.2f}KB/s, {self.bytes_per_sec} bytes\r\n"
            f"\tLast 10 sec: {avg_kb_s_10:.2f}KB/s, {self.bytes_per_10sec} bytes\r\n"
            f"\tLast 60 sec: {avg_kb_s_60:.2f}KB/s, {self.bytes_per_60sec} bytes\r\n")


# ===========================================
def get_reply(imei):  # BELTRANSPUTNIK
    ts = time.gmtime(time.time())
    y = ts.tm_year
    m = ts.tm_mon
    d = ts.tm_mday
    # s = 20 # speaker level
    # imei = 25
    if imei != 0:
        s, imei_from_file = get_values()
        st = (y + m + d * s * imei_from_file) & 0xFF
    else:
        s, asd = get_values()
        st = (y + m + d * s * imei) & 0xFF
    # number = int(y) + int(m) + int(d) * s * imei
    # st_hex = hex(st)
    # print(st_hex, type(st_hex))
    return st, [y, m, d, s, imei, (y + m + d * s * imei)]


# ===========================================
def get_int_value_from_file(string_to_search):
    try:
        f = open('values.txt')
        lines = f.readlines()
        # p = f.readline()
        for line in lines:
            p = line.strip('\r\n\t')
            if p.find(string_to_search) != -1:
                if int(p[len(string_to_search):]) == -1:
                    return -1
                elif p[len(string_to_search):].isdigit() == True:
                    return int(p[len(string_to_search):])
                else:
                    print(' >> Cant read %s value from values.txt! Its not digit!' % string_to_search)
                    return -1
        print(' >> Cant find %s value from values.txt!' % string_to_search)
        return -1
    except Exception as msg:
        print(' >> Cant find %s string in values.txt file! Error: %s' % (string_to_search, str(msg)))
        PrintException()
        return -1


# ===========================================
def get_str_value_from_file(string_to_search):
    try:
        f = open('values.txt')
        lines = f.readlines()
        # p = f.readline()
        for line in lines:
            p = line.strip('\r\n\t')
            # if p.find(string_to_search) != -1:
            if p.startswith(string_to_search):
                return p[len(string_to_search):]
        print(' >> Cant find %s value from values.txt!' % string_to_search)
        return 0
    except Exception as msg:
        print(' >> Cant find %s string in values.txt file! Error: %s' % (string_to_search, str(msg)))
        PrintException()
        return 0


# ===========================================
def get_values():
    # ===========================================================================
    # f = open('values.txt')
    # s = f.readline().strip('\r\n\t')
    # imei = f.readline().strip('\r\n\t')
    # s_poz = s.find('speaker:')
    # i_poz = imei.find('IMEI:')
    # f.close()
    # ===========================================================================
    # print(s, imei, s_poz, i_poz)
    spk = get_str_value_from_file('speaker:')
    im = get_str_value_from_file('IMEI:')
    # if (s_poz == 0) and (i_poz==0):
    # if (spk == 0) and (im == 0):
    # spk = s[8:]
    # im  = imei[5:]
    if (len(im) == 15):
        im = im[13:]
        if spk.isdigit() == True and im.isdigit() == True:
            # print(spk, im, type(spk), type(im))
            return int(spk), int(im)
        else:
            print('speaker level or imei are not digits!')
            return 0, 0
    else:
        print('wrong imei length, must be 15!')
        return 0, 0

    # else:
    #    print('Cant read values from values.txt file!')
    #    return 0, 0
# ===========================================
if test == 0:  # REAL server
    main_file = "server_project_office.txt"
    sender_file = 'cmd sender.txt'
    # main_file = 'ggg_fw_update.txt'
    # main_file = 'FM11.01.10.06 remote log.txt'
    # main_file = "fm11 beltrans udp test savaitgaliui.txt"
    host_check = get_str_value_from_file('host:').strip('\r\n')
    if len(host_check) > 0:
        print('ip addr from configuration: %s' % host_check)
        HOST = host_check
    else:
        print('ip addr autodetection')
        HOST = socket.gethostbyname(socket.getfqdn())

    EXT_IP = ipgetter.myip()
    print('external ip is ' + EXT_IP)
    beltrans_server = get_int_value_from_file('beltrans:')
    if beltrans_server == 1:
        PORT = get_int_value_from_file('port:')  # getport()
    else:
        PORT = get_int_value_from_file('port:')  # getport()

    # ===========================================
    TCP = get_int_value_from_file('tcp:')
    # ===========================================
    ipv6_support = get_int_value_from_file('ipv6:')
    # ===========================================
    TLS = get_int_value_from_file('tls:')
    tls_root_cert = get_str_value_from_file('tls_root_cert:')
    tls_key = get_str_value_from_file('tls_key:')
    # ===========================================
    FS_support = get_str_value_from_file('file_upload:')
    print('FS_Support now: ' + FS_support)
    # ===========================================
    FotaWeb = get_str_value_from_file('fota_web:')
    if FotaWeb == '1':
        FotaWeb = 1
    else:
        FotaWeb = 0
    # ===========================================
    FotaWeb_ST_communication = get_str_value_from_file("ST_communication:")
    if FotaWeb_ST_communication == '1':
        FotaWeb_ST_communication = 1
    else:
        FotaWeb_ST_communication = 0
    # ===========================================
    FOTA_WEB_2401_par = get_str_value_from_file("2401:")
    if FOTA_WEB_2401_par == '1':
        FOTA_WEB_2401_par = 1
    else:
        FOTA_WEB_2401_par = 0
    # ===========================================
    if FS_support == 'NONE' or FS_support == 'GGG' or FS_support == 'TM25' or FS_support == 'FMA' or FS_support == 'FMB_UPL' or FS_support == 'FM6X':
        pass
    else:  # invalid value detected @ values.txt file
        print(' >> Invalid FS_support mode detected: %s, set NONE!' % FS_support)
        FS_support = 'NONE'
    # ===========================================
    if FS_support == 'FMB_UPL':
        temp_path = get_str_value_from_file('file_path:')
        path_list = temp_path.split(';')
        FS_file_path_list = path_list
        idx = 0
        for file_name in path_list:
            temp = file_name.split('\\')
            print(' >> [%02u] path: %s, temp: %s' % (idx, file_name, temp))
            # print(type(temp[-1]))
            FS_file_name_list.append(temp[-1])
            idx += 1
        FS_file_name_list.append(None)
        FS_file_path_list.append(None)
        # temp_name = FS_file_path.split('\\')
        # FS_file_name = temp_name[-1]
    # ===========================================
    if FS_support == 'TM25' or FS_support == 'FM6X':  # for file transfer server -> device only
        FS_filename = get_str_value_from_file('filename:')
    # ===========================================
    FS_inv_crc_packet = get_int_value_from_file('inv_crc_packet:')
    # ===========================================
    FS_test_reject = get_int_value_from_file('test_reject:')
    # ===========================================
    FS_packet_cnt = get_int_value_from_file('packet_cnt:')
    # ===========================================
    FS_packet_delay = get_int_value_from_file('packet_delay:')
    FS_packet_delay = float(FS_packet_delay) / float(10)
    # print('packet delay: %u, float: %.2f' % (FS_packet_delay, FS_packet_delay))
    # ===========================================
    nod_plus_gprs = get_int_value_from_file('nod_plus_gprs:')
    # ===========================================
    instant_codec14_reply = get_int_value_from_file('instant_codec14_reply:')
    instant_codec14_reply_delay_ms = get_int_value_from_file(
        'instant_codec14_reply_delay_ms:')
    # ===========================================
    save_pcap_logs = get_int_value_from_file('save_pcap_logs:')
    if save_pcap_logs == 1:
        try:
            from pcap_logger import PCAPLoggerThread
            protocol = 'tcp' if TCP == 1 else 'udp'
            PCAPLoggerThread(protocol, PORT).start()
        except Exception as msg:
            print(f'Failed to start PCAP logger: {msg}')
    # ===========================================
else:  # TEST mode
    main_file = "draft_server.txt"
    sender_file = 'cmd sender.txt'
    HOST = '192.168.8.107'  # IP
    PORT = 5000  # PORT
    TCP = get_int_value_from_file('tcp:')
# ===========================================
if (TCP >= 0 and TCP <= 1) and PORT != 0:
    pass
else:
    print(' >> TCP: %u, PORT:%u. Quitting' % (TCP, PORT))
    sys.exit()


# ===========================================
def reply_decode(data, cmd_type, CID):
    try:
        ilg = struct.unpack('!I', data[11:15])[0]
        # print(type(data), len)
        data = data[15:(15 + ilg)].strip(b'\r\n')
        # print(gtime() + ' >> GPRS reply: %s\n' % data.decode('utf-8'))
        target = ''
        if cmd_type == GPRS_CMD_FM_TO_SERVER and CID == C12:
            target = 'GPRS Codec12'
        elif cmd_type == GPRS_CMD_FM_TO_SERVER and CID == C14:
            target = 'GPRS Codec14 ACK'
            imei = struct.unpack('!Q', data[0:8])[0]
            data = data[8:]
        elif cmd_type == GPRS_CMD_FM_TO_SERVER_nACK and CID == C14:
            target = 'GPRS Codec14 nACK'
            imei = struct.unpack('!Q', data[0:8])[0]
        elif cmd_type == GPRS_CMD_FM_IXTP_TO_SERVER_SOLO:
            target = 'IXTP SOLO'
        elif cmd_type == GPRS_CMD_FM_IXTP_TO_SERVER_P1:
            target = 'IXTP P1'
        elif cmd_type == GPRS_CMD_FM_IXTP_TO_SERVER_P2:
            target = 'IXTP P2'
        else:
            target = 'unknown'  # data.decode('utf-8')
        if CID == C12:
            proc.log(' >> %s (cmd type: 0x%02X) reply, len: %u: %s\n' % (target, cmd_type, ilg, str(data)))
        elif CID == C14:
            if cmd_type == GPRS_CMD_FM_TO_SERVER:
                proc.log(' >> %s (cmd type: 0x%02X) reply, imei: %016x, len: %u: %s\n' %
                         (target, cmd_type, imei, ilg, str(data)))
            elif cmd_type == GPRS_CMD_FM_TO_SERVER_nACK:
                proc.log(' >> %s (cmd type: 0x%02X) reply, imei: %016x\n' % (target, cmd_type, imei))
        # print(gtime() + ' >> GPRS reply: %s\n' % binascii.hexlify(data))  # deimantui
    except UnicodeDecodeError as msg:
        print(gtime() + ' >> Klaida: %s' % msg)
        print(gtime() + ' >> Data: %s' % str(data))
        print('hex: %s' % binascii.hexlify(data))
        PrintException()


# ===========================================
def Codec13_decode(data, cmd_type):
    try:
        ilg = struct.unpack('!I', data[11:15])[0]
        timestamp = struct.unpack('!I', data[15:19])[0]
        rawdata = data
        data = data[19:(19 + ilg)].strip(b'\r\n')
        target = ''
        if cmd_type == GPRS_CMD_FM_TO_SERVER:
            target = 'GPRS'
        else:
            target = 'unknown'  # data.decode('utf-8')
        proc.log(' >> %s (cmd type: 0x%02X) reply, len: %u, timestamp: %u: %s\n' %
                 (target, cmd_type, ilg, timestamp, str(data[: ilg - 4])))
        packetSize = 18 + ilg + 2
        try:
            if rawdata[packetSize + 10] == cmd_type:
                # this needed in case more than one packet received
                print("next cmd")
                data = rawdata[packetSize:]
                # print(binascii.hexlify(data))
                Codec13_decode(data, data[10])
        except IndexError:
            print("last cmd")
    except UnicodeDecodeError as msg:
        print(gtime() + ' >> Error: %s' % msg)
        print(gtime() + ' >> Data: %s' % str(data))
        print('hex: %s' % binascii.hexlify(data))
        PrintException()

# ===========================================


def Codec17_decode(data, cmd_type):
    """ Decodes Codec 17 data, including GNSS parsing and payload extraction. """

    def format_gnss_data(gnss_bytes):
        """ Parses GNSS data and returns raw hex + decimal values. """
        try:
            if len(gnss_bytes) != 15:
                return f"Invalid GNSS data length: {len(gnss_bytes)} bytes"

            # Unpack GNSS structure
            speed = struct.unpack("!H", gnss_bytes[0:2])[0]
            sat_in_use = struct.unpack("!B", gnss_bytes[2:3])[0]
            angle = struct.unpack("!h", gnss_bytes[3:5])[0]
            altitude = struct.unpack("!h", gnss_bytes[5:7])[0]
            latitude = struct.unpack("!i", gnss_bytes[7:11])[0]
            longitude = struct.unpack("!i", gnss_bytes[11:15])[0]

            return (f"Longitude: {longitude}, Latitude: {latitude}, "
                    f"Altitude: {altitude}, Angle: {angle}, "
                    f"Satellites: {sat_in_use}, Speed: {speed}")

        except struct.error:
            return "Error parsing GNSS data"

    try:
        # Extract packet total size (from Data size field)
        data_size = struct.unpack('!I', data[4:8])[
            0]  # Data size field (4 bytes)
        # Data size + Preamble (4 bytes) + Data Size (4 bytes)
        total_size = data_size + 8

        # Extract GNSS data (15 bytes)
        gnss_data = data[19:34]
        formatted_gnss = format_gnss_data(gnss_data)

        # Extract payload start position
        payload_start = 34  # Response data starts right after GNSS data

        # CRC-16 is always last 4 bytes, Response Quantity 2 is before that
        crc_size = 4
        response_qty_2_size = 1
        payload_end = len(data) - (crc_size + response_qty_2_size)

        # Extract payload (actual message data)
        data_payload = data[payload_start:payload_end]

        # Decode payload safely
        decoded_payload = data_payload.decode(errors='ignore')

        target = 'GPRS' if cmd_type == GPRS_CMD_FM_TO_SERVER else 'unknown'

        # Print log with raw GNSS and decimal conversion
        print(f" >> {target} (cmd type: 0x{cmd_type:02X}) reply, len: {len(data_payload)}, "
              f"timestamp: {struct.unpack('!I', data[15:19])[0]}, GNSS: {formatted_gnss}, "
              f"data: {decoded_payload}")

        # Check if more packets exist
        if len(data) > total_size + 10 and data[total_size + 10] == cmd_type:
            print("Next cmd detected, decoding next packet")
            Codec17_decode(data[total_size:], data[total_size + 10])
        else:
            print("Last cmd in sequence")

    except (UnicodeDecodeError, IndexError, struct.error) as msg:
        print(" >> Error:", msg)
        print(" >> Data (hex):", binascii.hexlify(data).decode())


# ===========================================
def Codec34_decode(data):
    _c34_protocol = data[0]
    print("DataLen:%d" % len(data))
    print("Protocol.Id: " + hex(_c34_protocol))
    _c34_start_ts = struct.unpack('!I', data[1:5])[0]
    print("Start TS:%d" % _c34_start_ts)
    _c34_vin = data[5:22]
    print("VIN:{0}".format(_c34_vin))
    _c34_driver_id = data[22:38]
    print("Driver ID:{0}".format(_c34_driver_id))
    _c34_odo_start = struct.unpack('!I', data[38:42])[0]
    print("Odometer Start:{0}".format(_c34_odo_start))
    _c34_odo_end = struct.unpack('!I', data[42:46])[0]
    print("Odometer End:{0}".format(_c34_odo_end))

    _c34_fu_start = struct.unpack('!I', data[46:50])[0]
    print("Fuel Used Start:{0}".format(_c34_fu_start))
    _c34_fu_end = struct.unpack('!I', data[50:54])[0]
    print("Fuel Used End:{0}".format(_c34_fu_end))

    _c34_ts_start = struct.unpack('!I', data[54:58])[0]
    print("TS Start:{0}".format(_c34_ts_start))
    _c34_ts_end = struct.unpack('!I', data[58:62])[0]
    print("TS End:{0}".format(_c34_ts_end))
    _c34_roll_distance = struct.unpack('!I', data[62:66])[0]
    print("Roll distance:{0}".format(_c34_roll_distance))
    if _c34_protocol == 2:
        _c34_index = 70
        _c34_roll_time = struct.unpack('!I', data[66:_c34_index])[0]
    else:
        _c34_index = 68
        _c34_roll_time = struct.unpack('!H', data[66:_c34_index])[0]
    print("Roll time:{0}".format(_c34_roll_time))

    _c34_cruise_distance = struct.unpack('!I', data[_c34_index:_c34_index + 4])[0]
    _c34_index += 4
    print("Cruise distance:{0}".format(_c34_cruise_distance))
    if _c34_protocol == 2:
        _c34_cruise_time = struct.unpack('!I', data[_c34_index:_c34_index + 4])[0]
        _c34_index += 4
    else:
        _c34_cruise_time = struct.unpack('!H', data[_c34_index:_c34_index + 2])[0]
        _c34_index += 2

    print("Cruise time:{0}".format(_c34_cruise_time))
    INDC_DRV_VMAX_ELEM_COUNT = 15

    _c34_vmax_table = []
    for i in range(INDC_DRV_VMAX_ELEM_COUNT):
        if _c34_protocol == 0:
            _c34_vmax_table.append(struct.unpack('!H', data[_c34_index:_c34_index + 2])[0])
            _c34_index += 2
        elif _c34_protocol >= 1:
            _c34_vmax_table.append(struct.unpack('!I', data[_c34_index:_c34_index + 4])[0])
            _c34_index += 4
    print("VMAX TABLE:{0}".format(_c34_vmax_table))
    _c34_brake_distance = struct.unpack('!I', data[_c34_index:_c34_index + 4])[0]
    _c34_index += 4
    print("Brake distance:{0}".format(_c34_brake_distance))

    _c34_retarder_distance = struct.unpack('!I', data[_c34_index:_c34_index + 4])[0]
    _c34_index += 4
    print("Retarder distance:{0}".format(_c34_retarder_distance))

    _c34_acc_cycles = struct.unpack('!H', data[_c34_index:_c34_index + 2])[0]
    _c34_index += 2
    print("Acc pedal cycles:{0}".format(_c34_acc_cycles))

    _c34_speed_cycles = struct.unpack('!H', data[_c34_index:_c34_index + 2])[0]
    _c34_index += 2
    print("Speed cycles:{0}".format(_c34_speed_cycles))

    _c34_num_stops_10s = struct.unpack('!H', data[_c34_index:_c34_index + 2])[0]
    _c34_index += 2
    print("Num of stops 10s:{0}".format(_c34_num_stops_10s))

    _c34_num_stops_20s = struct.unpack('!H', data[_c34_index:_c34_index + 2])[0]
    _c34_index += 2
    print("Num of stops 20s:{0}".format(_c34_num_stops_20s))

    if _c34_protocol == 2:
        _c34_fuel_consumption_stops = struct.unpack('!I', data[_c34_index:_c34_index + 4])[0]
        _c34_index += 4
        print("Fuel consumption stop:{0}".format(_c34_fuel_consumption_stops))

        _c34_fuel_consumption_stop_t = struct.unpack('!I', data[_c34_index:_c34_index + 4])[0]
        _c34_index += 4
        print("Fuel consumption stop time:{0}".format(_c34_fuel_consumption_stop_t))

        _c34_fuel_consumption_motion = struct.unpack('!I', data[_c34_index:_c34_index + 4])[0]
        _c34_index += 4
        print("Fuel consumption motion:{0}".format(_c34_fuel_consumption_motion))

        _c34_fuel_consumption_motion_t = struct.unpack('!I', data[_c34_index:_c34_index + 4])[0]
        _c34_index += 4
        print("Fuel consumption motion time:{0}".format(_c34_fuel_consumption_motion_t))
    else:
        _c34_fuel_consumption_stops = struct.unpack('!H', data[_c34_index:_c34_index + 2])[0]
        _c34_index += 2
        print("Fuel consumption stop:{0}".format(_c34_fuel_consumption_stops))

        _c34_fuel_consumption_stop_t = struct.unpack('!H', data[_c34_index:_c34_index + 2])[0]
        _c34_index += 2
        print("Fuel consumption stop time:{0}".format(_c34_fuel_consumption_stop_t))

        _c34_fuel_consumption_motion = struct.unpack('!H', data[_c34_index:_c34_index + 2])[0]
        _c34_index += 2
        print("Fuel consumption motion:{0}".format(_c34_fuel_consumption_motion))

        _c34_fuel_consumption_motion_t = struct.unpack('!H', data[_c34_index:_c34_index + 2])[0]
        _c34_index += 2
        print("Fuel consumption motion time:{0}".format(_c34_fuel_consumption_motion_t))

    INDC_DRV_SPEED_TABLE_ROWS_COUNT = 15
    INDC_DRV_SPEED_TABLE_COLUMN_COUNT = 15
    INDC_DRV_SPEED_TABLE_ELEM_SIZE = 2
    _c34_espeed_table = []

    for i in range(INDC_DRV_SPEED_TABLE_COLUMN_COUNT):
        _c34_espeed_row = []
        for y in range(INDC_DRV_SPEED_TABLE_ROWS_COUNT):
            _c34_espeed_row.append(struct.unpack('!H', data[_c34_index:_c34_index + 2])[0])
            _c34_index += 2
        _c34_espeed_table.append(_c34_espeed_row)
    print("ENGINE SPEED TABLE:{0}".format(_c34_espeed_table))

    INDC_DRV_TABLE_PROF_COUNT = 8
    _c34_brake_profile_table = []
    for i in range(INDC_DRV_TABLE_PROF_COUNT):
        _c34_brake_profile_table.append(struct.unpack('!H', data[_c34_index:_c34_index + 2])[0])
        _c34_index += 2
    print("BRAKING PROFILE TABLE:{0}".format(_c34_brake_profile_table))

    _c34_mask = struct.unpack('!I', data[_c34_index:_c34_index + 4])[0]
    print("Mask:" + hex(_c34_mask))


# ===========================================
def Codec36_decode(data):
    _c36_idx = 0
    _c36_protocol = data[_c36_idx]
    print("DataLen:%d" % len(data))
    print("Protocol.Rev: " + hex(_c36_protocol))
    _c36_idx += 1
    _c36_save_ts = struct.unpack('!I', data[_c36_idx:_c36_idx+4])[0]
    print("Save TS:%d" % _c36_save_ts)
    _c36_idx += 4
    _c36_driver_id = data[_c36_idx:_c36_idx+16]
    print("DriverID:0x" + binascii.hexlify(bytearray(_c36_driver_id)).decode('ascii'))
    _c36_idx += 16
    _c36_dur_tot = struct.unpack('!I', data[_c36_idx:_c36_idx+4])[0]
    print("Total duration(s):{0}".format(_c36_dur_tot))
    _c36_idx += 4
    _c36_weight = struct.unpack('!I', data[_c36_idx:_c36_idx+4])[0]
    print("Weight(kg):{0}".format(_c36_weight))
    _c36_idx += 4
    _c36_act_braking_dist = struct.unpack('!I', data[_c36_idx:_c36_idx+4])[0]
    print("Active braking distance(m):{0}".format(_c36_act_braking_dist))
    _c36_idx += 4
    _c36_braking_cnt = struct.unpack('!I', data[_c36_idx:_c36_idx+4])[0]
    print("Braking count:{0}".format(_c36_braking_cnt))
    _c36_idx += 4
    _c36_harsh_braking_cnt = struct.unpack('!I', data[_c36_idx:_c36_idx+4])[0]
    print("Harsh braking count:{0}".format(_c36_harsh_braking_cnt))
    _c36_idx += 4
    _c36_park_dur = struct.unpack('!I', data[_c36_idx:_c36_idx+4])[0]
    print("Parking duration(s):{0}".format(_c36_park_dur))
    _c36_idx += 4
    _c36_adbluelvl_start = struct.unpack('!B', data[_c36_idx:_c36_idx+1])[0]
    print("AdBlue lvl at start:{0}".format(_c36_adbluelvl_start))
    _c36_idx += 1
    _c36_adbluelvl_end = struct.unpack('!B', data[_c36_idx:_c36_idx+1])[0]
    print("AdBlue lvl at end:{0}".format(_c36_adbluelvl_end))
    _c36_idx += 1

    IND_TRIP_TYPE_COUNT = 2
    for i in range(IND_TRIP_TYPE_COUNT):
        print("Trip type - %s" % ("SLOW" if (i == 0) else "FAST"))
        _c36_dist_total = struct.unpack('!I', data[_c36_idx:_c36_idx+4])[0]
        print("Distance total(m):{0}".format(_c36_dist_total))
        _c36_idx += 4
        _c36_height_prof = struct.unpack('!f', data[_c36_idx:_c36_idx+4])[0]
        print("Height profile:{0}".format(_c36_height_prof))
        _c36_idx += 4
        _c36_dist_coast = struct.unpack('!I', data[_c36_idx:_c36_idx+4])[0]
        print("Distance coasting(m):{0}".format(_c36_dist_coast))
        _c36_idx += 4

        IND_FUEL_CATEG = 5
        _c36_fuel_categ_table = []
        for j in range(IND_FUEL_CATEG):
            _c36_fuel_categ_table.append(struct.unpack('!I', data[_c36_idx:_c36_idx + 4])[0])
            _c36_idx += 4
        print("Time(s) in fuel category TABLE:{0}".format(_c36_fuel_categ_table))

        _c36_fuel_total = struct.unpack('!I', data[_c36_idx:_c36_idx+4])[0]
        print("Fuel total(ml):{0}".format(_c36_fuel_total))
        _c36_idx += 4
        _c36_fuel_driving = struct.unpack('!I', data[_c36_idx:_c36_idx+4])[0]
        print("Fuel driving(ml):{0}".format(_c36_fuel_driving))
        _c36_idx += 4
        _c36_fuel_stand = struct.unpack('!I', data[_c36_idx:_c36_idx+4])[0]
        print("Fuel standing(ml):{0}".format(_c36_fuel_stand))
        _c36_idx += 4
        _c36_avg_fuel_tot = struct.unpack('!I', data[_c36_idx:_c36_idx+4])[0]
        print("Avg fuel total(l/100km):{0}".format(_c36_avg_fuel_tot))
        _c36_idx += 4
        _c36_avg_fuel_driving = struct.unpack('!I', data[_c36_idx:_c36_idx+4])[0]
        print("Avg fuel driving(l/100km):{0}".format(_c36_avg_fuel_driving))
        _c36_idx += 4
        _c36_avg_fuel_stand = struct.unpack('!I', data[_c36_idx:_c36_idx+4])[0]
        print("Avg fuel standing(l/h):{0}".format(_c36_avg_fuel_stand))
        _c36_idx += 4
        _c36_height_m = struct.unpack('!i', data[_c36_idx:_c36_idx+4])[0]
        print("Height(m):{0}".format(_c36_height_m))
        _c36_idx += 4
        _c36_brk_dist_m = struct.unpack('!I', data[_c36_idx:_c36_idx+4])[0]
        print("Braking distance(m):{0}".format(_c36_brk_dist_m))
        _c36_idx += 4

        IND_RPM_CATEG = 21
        IND_TORQUE_CATEG = 8
        for j in range(IND_RPM_CATEG):
            _c36_rpm_torq_categ_table = []
            for n in range(IND_TORQUE_CATEG):
                _c36_rpm_torq_categ_table.append(struct.unpack('!I', data[_c36_idx:_c36_idx + 4])[0])
                _c36_idx += 4
            print("Time(s) in RPM[%d] over torque category TABLE:" % j, _c36_rpm_torq_categ_table)

        IND_ACC_PEDAL_CATEG = 8
        _c36_acc_ped_categ_table = []
        for j in range(IND_ACC_PEDAL_CATEG):
            _c36_acc_ped_categ_table.append(struct.unpack('!I', data[_c36_idx:_c36_idx + 4])[0])
            _c36_idx += 4
        print("Time(s) in ACCELERATOR category TABLE:{0}".format(_c36_acc_ped_categ_table))

        _c36_avg_speed = struct.unpack('!H', data[_c36_idx:_c36_idx+2])[0]
        print("Avg speed(km/h):{0}".format(_c36_avg_speed))
        _c36_idx += 2
        _c36_max_speed = struct.unpack('!H', data[_c36_idx:_c36_idx+2])[0]
        print("Max speed(km/h):{0}".format(_c36_max_speed))
        _c36_idx += 2

        IND_SPEED_CATEG = 17
        _c36_speed_categ_table = []
        for j in range(IND_SPEED_CATEG):
            _c36_speed_categ_table.append(struct.unpack('!I', data[_c36_idx:_c36_idx + 4])[0])
            _c36_idx += 4
        print("Time(s) in SPEED category TABLE:{0}".format(_c36_speed_categ_table))

        IND_CRUISE_CTRL_CATEG = 15
        _c36_cruise_ctrl_categ_table = []
        for j in range(IND_CRUISE_CTRL_CATEG):
            _c36_cruise_ctrl_categ_table.append(struct.unpack('!I', data[_c36_idx:_c36_idx + 4])[0])
            _c36_idx += 4
        print("Time(s) in CRUISE CTRL category TABLE:{0}".format(_c36_cruise_ctrl_categ_table))

        _c36_dist_cc = struct.unpack('!I', data[_c36_idx:_c36_idx+4])[0]
        print("Distance cruise control(m):{0}".format(_c36_dist_cc))
        _c36_idx += 4

        _c36_trip_dur = struct.unpack('!I', data[_c36_idx:_c36_idx+4])[0]
        print("Trip duration(s):{0}".format(_c36_trip_dur))
        _c36_idx += 4
# ===========================================
def is_valid_json(string):
    try:
        json.loads(string)
        return True
    except json.JSONDecodeError:
        return False
# ===========================================

def codec12(data, CID, CMD_T):  # when CMD_T == 0, it means its tachograph packet. for regular use must be 1
    zero_4 = struct.pack('!I', 0)
    data = data.encode()
    if data == 0:
        data_len = 0
    else:
        data_len = len(data)
    # -------------------------
    data_length = struct.pack('!I', (data_len + 8))
    CID = struct.pack('B', CID)
    NOD = struct.pack('B', 1)
    CMD = struct.pack('B', CMD_T)
    NO_of_data = struct.pack('!I', data_len)

    if data == 0:
        msg = zero_4 + data_length + CID + NOD + CMD + NO_of_data + NOD
    else:
        msg = zero_4 + data_length + CID + NOD + CMD + NO_of_data + data + NOD

    zero_2 = struct.pack('!H', 0)
    Len = len(msg[8:len(msg)])
    # print('len: %d, data to calc for crc: ' % Len, msg[:])
    # for i in range(8,len(msg)):
    #    print(msg[i])
    # crc16(str(msg[8:len(msg)]), 0)
    # crc16_3(str(msg[8:len(msg)]))
    # crc = crc16((msg[8:]).decode('utf-8'), Len, 0) # reiks pataisyt kad galetu crc skaiciuot kai daugiau nei 128
    crc = crc16(msg[8:], Len, 0)
    crc = struct.pack('!H', crc)
    msg = msg + zero_2 + crc
    # print(type(msg),'formed msg:', msg)
    return msg


# ===========================================
def codec14(data, NOD, CID, CMD_T):  # when CMD_T == 0, it means its tachograph packet. for regular use must be 1
    zero_4 = struct.pack('!I', 0)
    if data == 0:
        data_len = 0
    else:
        data_len = len(data)
    # -------------------------
    data_length = struct.pack('!I', (data_len + 8))
    CID = struct.pack('B', CID)
    _NOD = struct.pack('B', NOD)
    CMD = struct.pack('B', CMD_T)
    NO_of_data = struct.pack('!I', data_len)

    if data == 0:
        msg = zero_4 + data_length + CID + _NOD + CMD + NO_of_data + _NOD
    else:
        msg = zero_4 + data_length + CID + _NOD + CMD + NO_of_data + data + _NOD

    zero_2 = struct.pack('!H', 0)
    Len = len(msg[8:len(msg)])
    crc = crc16(msg[8:], Len, 0)
    crc = struct.pack('!H', crc)
    msg = msg + zero_2 + crc
    return msg


# ===========================================
def crc16(s, Len, mode):
    """
    mode = [0,1]
    0 - calculate crc at once
    1 - by parts
    """
    global crc
    # print(type(s),'len : %d, s: %s' % (Len,s))
    # ===========================================
    if mode == 0:  # all at once
        usCRC = 0
        poly = 0xA001  # reversed 0x8005
    elif mode == 1:  # by parts
        usCRC = crc
        poly = 0x8408
    else:
        print('unknown crc calculation mode')
        return 0
    # ===========================================
    ucCarry = 0  # ucBit = 0
    # ===========================================
    for i in s:
        # print(i)
        # print(type(usCRC), type(i), ord(i) )
        usCRC = usCRC ^ i
        for ucBit in range(0, 8):
            ucCarry = usCRC & 1
            usCRC >>= 1
            if (ucCarry):
                usCRC ^= poly
    # print('crc4: ',usCRC, hex(usCRC))
    if mode == 1:
        # print('crc: %04X => %04X' % (crc, usCRC))
        crc = usCRC
    # ===========================================
    return usCRC


# ==============================
def gtime():
    # return time.strftime("%Y.%m.%d %H:%M:%S")
    return time.strftime("%Y.%m.%d ") + datetime.datetime.now().strftime("%H:%M:%S.%f")


# ==============================
def PrintException():
    exc_type, exc_obj, tb = sys.exc_info()
    f = tb.tb_frame
    lineno = tb.tb_lineno
    filename = f.f_code.co_filename
    linecache.checkcache(filename)
    line = linecache.getline(filename, lineno, f.f_globals)
    proc.log(' >> EXCEPTION IN ({}, LINE {} "{}"): {}'.format(filename, lineno, line.strip(), exc_obj))


# ======================================
def countSetBits(n):
    count = 0
    while (n):
        count += n & 1
        n >>= 1
    return count


# ==============================
def par_pack(par_id, par_data, par_size):
    # data = struct.pack('!HH%ds', par_id, len(par_data),len(par_data), par_data)
    data = struct.pack('!H', par_id)
    if isinstance(par_data, str):
        data += struct.pack('!H%ds' % (len(par_data),), len(par_data), par_data)
    else:
        if par_size == 1:
            data += struct.pack('!HB', par_size, par_data)
        elif par_size == 2:
            data += struct.pack('!HH', par_size, par_data)
        elif par_size == 4:
            data += struct.pack('!HI', par_size, par_data)
        elif par_size == 8:
            data += struct.pack('!HQ' % par_size, par_data)
    # s = par_data
    # data = struct.pack("!I%ds" % (len(s),), len(s), s)

    return data


def encode_imei(imei_str):
    """Convert a 15-digit IMEI string into 8-byte BCD format."""
    if len(imei_str) != 15 or not imei_str.isdigit():
        raise ValueError("IMEI must be a 15-digit numeric string")
    
    # Add leading zero and convert to BCD
    imei_bcd = binascii.unhexlify("0" + imei_str)
    return imei_bcd


class gprs_sender(threading.Thread):

    def __init__(self, mode, period, data):
        global main_file
        threading.Thread.__init__(self)
        self.finished = threading.Event()
        self.file = sender_file
        self.file = open(self.file, 'a')
        self.period = period
        # self.data = binascii.a2b_hex(data)
        self.data = data
        if mode == GPRS_0C_SENDER:
            self.cmd_type = CMD5
        else:
            self.cmd_type = GPRS_CMD_CAMERA_TO_FM

    # ==============================
    def log(self, msg):
        try:
            self.file.write(gtime() + msg + '\n')
            self.file.flush()
            print(gtime() + str(msg))
        except Exception as msg:
            PrintException()

    # ==============================
    def stop(self):
        sender.log(' >> Gprs sender trying to quit.')
        self.finished.set()
        # ===========================================
        try:
            self.join(1)
            sender.log(' >> Joining main program.')
        except RuntimeError as msg:
            sys.stderr.write("[ERROR] %s\n" % msg)
            sender.log(' >> Failed to join main program.')
            PrintException()

    # ==============================
    def run(self):
        global imei_resp_sent
        cnt = 0
        try:
            sender.log(' >> Sender thread started. Will attempt to send one %s cmd to FM every %u sec' %
                       ('gprs' if self.cmd_type == CMD5 else 'camera', self.period))
            while not self.finished.is_set():
                status = proc.connection_status()
                if (cnt >= self.period) and status == 1:
                    cnt = 0
                    sender.log(' >> Connection status: %u' % status)
                    if status == 1:
                        if imei_resp_sent == 1:
                            sender.log(' >> Attempting gprs cmd sending')
                            proc.send_gprs_cmd(self.cmd_type, self.data)
                        else:
                            sender.log(' >> Imei ack not sent yet, waiting ...')
                    else:
                        sender.log(' >> No connection established, waiting ...')
                else:
                    if status == 0:
                        cnt = 0
                    if cnt % 10 == 0 and status == 1:
                        sender.log(' >> gprs sender waiting %u / %u' % (cnt, self.period))
                time.sleep(1)  # 1 sec
                cnt += 1
            sender.log(' >> Gprs cmd sender terminating.')
        except Exception as msg:
            sender.log(' >> Error in sender run f-n: %s' % str(msg))
            PrintException()
        try:
            self.file.close()
        except Exception as msg:
            pass
    # ==============================


# ==============================
class cpu_reset_sender(threading.Thread):

    def __init__(self):
        global main_file
        threading.Thread.__init__(self)
        self.finished = threading.Event()
        self.file = sender_file
        self.file = open(self.file, 'a')
        # ==============================
        try:
            self.period = get_int_value_from_file('cpureset_period:')
        except Exception as msg:
            self.period = 10  # default if reading from file fails
            PrintException()

    # ==============================
    def log(self, msg):
        try:
            self.file.write(gtime() + msg + '\n')
            self.file.flush()
            print(gtime() + str(msg))
        except Exception as msg:
            pass

    # ==============================
    def stop(self):
        sender.log(' >> cpureset sender trying to quit.')
        self.finished.set()
        # ===========================================
        try:
            self.join(1)
            sender.log(' >> Joining main program.')
        except RuntimeError as msg:
            sys.stderr.write("[ERROR] %s\n" % msg)
            sender.log(' >> Failed to join main program.')
            PrintException()

    # ==============================
    def run(self):
        cnt = 0
        try:
            sender.log(' >> Cpureset sender thread started. Will attempt to send cpureset every %u sec' % self.period)
            while not self.finished.is_set():
                if (cnt >= self.period):
                    cnt = 0
                    status = proc.connection_status()
                    sender.log(' >> Connection status: %u' % status)
                    if status == 1:
                        sender.log(' >> Attempting cpureset cmd sending')
                        proc.send_cmd('cpureset')
                        proc.close_socket()
                    else:
                        sender.log(' >> No connection established, waiting ...')
                else:
                    pass  # do nothing
                time.sleep(1)  # 1 sec
                cnt += 1
            sender.log(' >> Gprs cmd sender terminating.')
        except Exception as msg:
            sender.log(' >> Error in sender run f-n: %s' % str(msg))
            PrintException()
        try:
            self.file.close()
        except Exception as msg:
            pass
    # ==============================


# ==============================
class starter(threading.Thread):

    def __init__(self):  # , interval
        global main_file
        global ipvx_protocol
        threading.Thread.__init__(self)
        if ipv6_support == 0:
            ipvx_protocol = socket.AF_INET  # IPv4
        else:
            ipvx_protocol = socket.AF_INET6  # IPv6

        print('Configured IPv%u protocol ' % (6 if ipv6_support > 0 else 4))
        if TCP == 1:
            self.s = socket.socket(ipvx_protocol, socket.SOCK_STREAM)  # TCP
            self.s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        else:
            self.s = socket.socket(ipvx_protocol, socket.SOCK_DGRAM)  # UDP
            self.s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        if TLS == 1:
            print("Using TLS")
            ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
            ssl_context.load_cert_chain(certfile=tls_root_cert, keyfile=tls_key)
            self.s = ssl_context.wrap_socket(self.s, server_side=True)

        self.finished = threading.Event()
        self.disc = threading.Event()
        self.file = main_file
        self.file = open(self.file, 'a')
        self.connected = 0
        if get_int_value_from_file('online_log:') == 1:
            self.online_log = True
        else:
            self.online_log = False
        self.file_upload_idx = 0

    def process_file(self, data, file_reader):
        global crc, mess, FS_test_reject
        global FS_chunk_size
        global C08, C8E, C61, C61E, C18, C32, C33
        global waiting_for_multi, temp
        global FS_support, FS_chunk_size
        global files_to_dl
        crc = 0
        protocol_id = 0
        imei = 0
        settings = 0
        # =================================================================
        if len(data) == 16:  # init packet parsing
            protocol_id = struct.unpack('!H', data[2:4])[0]
            imei = struct.unpack('!Q', data[4:12])[0]
            settings = struct.unpack('!H', data[12:14])[0]
            FS_chunk_size = struct.unpack('!H', data[14:16])[0]
            proc.log(' >> Protocol ID: 0x%04X, imei: %lu, settings: 0x%04X, chunk size: %u' %
                     (protocol_id, imei, settings, FS_chunk_size))
            # proc.log(' >> Data: %x' % (data))
            if FS_test_reject == 0:
                if os.path.exists(os.getcwd() + '\\' + FS_filename) == True:
                    file_size = os.path.getsize(FS_filename)
                    f = open(FS_filename, 'rb')
                    file_data = f.read()
                    f.close()
                    c_crc16 = crc16(file_data, file_size, 1)
                    if file_size > 0:
                        global fileDlOld
                        global file_type_to_send
                        # =================================================
                        proc.log(
                            ' >> FMB file download. Init packet received. File size: %u, c_crc: 0x%04X' %
                            (file_size, c_crc16))
                        if (protocol_id == 0x0001 or FS_filename.lower().endswith('.cfg') or FS_filename.lower().endswith('.dat') or FS_filename.lower().endswith('.bin') or FS_filename.lower().endswith('.tar') or FS_filename.lower().endswith('.zip')
                                or FS_filename.lower().endswith('ephmgps', 0, 7)):  # send start file transfer packet
                            proc.log(
                                ' >> Parsing data from protocol id == 0x0001. Custom file type: %x' %
                                (custom_file_type))
                            proc.log(' >> File_DL_Old: %u' % fileDlOld)
                            if custom_file_type == 0:
                                mess = struct.pack('!H', 1) + struct.pack('!H', 6,) + struct.pack('!I',
                                                                                                  file_size) + struct.pack('!H', c_crc16)
                            else:
                                if custom_file_type == 17:
                                    file_path = 'd:\\gps_fota\\mt3333fw.bin'
                                    file_type = dwl_file_types['MT3333_FW']
                                    proc.log(' >> MT3333 FW file download by path')
                                elif custom_file_type & 0x01 == 1:  # 1 bit used for AGPS MT3333
                                    file_path = 'd:\\agps\\EPO_GR.DAT'
                                    file_type = dwl_file_types['AGPS_MT3333']
                                    proc.log(' >> AGPS file download by path MT3333')
                                elif custom_file_type & 0x02 == 2:  # 2 bit used for OBD file
                                    #                                         file_path = 'd:\\obd\\obd_file.txt'
                                    #                                         file_type = dwl_file_types['DWL_OBD']
                                    proc.log(' >> OBD File download by path')
                                elif custom_file_type & 0x04 == 4:  # 3 bit used for AGPS Quectel L89
                                    file_path = 'd:\\agps\\EphmGps-19-224-06-00.txt'
#                                         file_path = 'd:\\agps\\EphmGps-18-222-08-40.txt'
                                    file_type = dwl_file_types['AGPS_QL89']
                                    proc.log(' >> AGPS file download by path Quectel L89')
                                elif custom_file_type & 0x100 == 256:  # 8 bit used MT3333 GNSS DA
                                    file_path = 'd:\\gps_fota\\mt3333_da.bin'
                                    file_type = dwl_file_types['MT3333_DA']
                                    proc.log(' >> MT3333 DA file download by path')
                                elif custom_file_type & 0x200 == 512:  # 9 bit used MT3333 GNSS FW
                                    file_path = 'd:\\gps_fota\\mt3333fw.bin'
                                    file_type = dwl_file_types['MT3333_FW']
                                    proc.log(' >> MT3333 FW file download by path')
                                elif custom_file_type > 0 or file_type_to_send != 0:
                                    file_type = file_type_to_send
                                    file_path = get_str_value_from_file('file_path:')
#                                    elif custom_file_type & 0x10000000 == 0x10000000:  # 5 bit used for BLE FW
#                                        file_path = 'z:\\ble\\ble_fw.bin'
#                                        #file_path = 'd:\\agps\\EphmGps-18-222-08-40.txt'
#                                        file_type = dwl_file_types['BLE_FW']
#                                        proc.log(' >> BLE file download by path')
                                else:
                                    proc.log(' >> Invalid file type')
                                    return 0, data, data, 0

                                # Use file download by path if fileDlOld == 1
                                if fileDlOld == 0:
                                    file_path_len = len(file_path)
                                    data_len = 8 + file_path_len  # 8 = 4 bytes file size + 2 bytes file crc + 1 byte file type + 1 byte file path size
                                    mess = (struct.pack('!H', 1) + struct.pack('!H', data_len) + struct.pack('!I', file_size) + struct.pack('!H', c_crc16) +
                                            struct.pack('!B', file_type) + struct.pack('!B', file_path_len) + struct.pack('{}s'.format(len(file_path)), file_path))
                                else:
                                    mess = struct.pack('!H', 1) + struct.pack('!H', 6,
                                                                              ) + struct.pack('!I', file_size) + struct.pack('!H', c_crc16)

                            if custom_file_type != 0:
                                proc.log(' >> Sending to FM with path: %s, file type: %u' % (file_path, file_type))
                            proc.send()
                            return 0, data, data, 0
                        # =================================================
                        elif protocol_id == 0x0002:  # new protocol id, lets send query command
                            # fw_ver_4B = struct.pack('B', 2) + struct.pack('B', 0) + struct.pack('B', 0) + struct.pack('B', 0)
                            out_fw_ver, out_device_id, out_client_id = file_reader()
                            mess = struct.pack('!H', 6) + struct.pack('!H', 8) + out_fw_ver + out_device_id
                            proc.send()
                            return 0, data, data, 0
                        # =================================================
                        elif protocol_id == 0x0003 or protocol_id == 0x0005:  # new protocol id, lets send EXTENDED query command
                            out_fw_ver, out_device_id, out_client_id = file_reader()
                            mess = struct.pack('!H', 6) + struct.pack('!H',
                                                                      12) + out_fw_ver + out_device_id + out_client_id
                            proc.send()
                            return 0, data, data, 0
                        # =================================================
                        else:
                            proc.log(' >> Maybe TM25 file download packet, but cant parse %x' % (protocol_id))
                    else:
                        proc.log(' >> Error! Invalid file size!')
                        return 1, data, data, 0
                else:
                    proc.log(' >> Error! Could not read file size for file dl functionality!')
                    return 1, data, data, 0
            else:  # test_reject == 1
                proc.log(' >> Sending reject file dl packet')
                mess = struct.pack('!H', 0) + struct.pack('!H', 4) + struct.pack('!I', 16909060)
                proc.send()
                return 0, data, data, 0
        # =================================================================
        elif len(data) == 8 or len(data) == 5:  # resume file transfer packet parsing
            if len(data) == 5:
                cmd_id = struct.unpack('!H', data[0:2])[0]
                data_len = struct.unpack('!H', data[2:4])[0]
                query_response = struct.unpack('!b', data[4:5])[0]
                proc.log(
                    ' >> TM25 query response received! CMD ID: 0x%02X, Data Length: 0x%02X, Response %i' %
                    (cmd_id, data_len, query_response))
                if query_response == 0 and cmd_id == 0x0007:
                    proc.log(' >> TM25 query response is valid!')
                    file_size = os.path.getsize(FS_filename)
                    f = open(FS_filename, 'rb')
                    file_data = f.read()
                    f.close()
                    c_crc16 = crc16(file_data, file_size, 1)
                    if file_size > 0:
                        mess = struct.pack('!H', 1) + struct.pack('!H', 6,) + struct.pack('!I',
                                                                                          file_size) + struct.pack('!H', c_crc16)
                        proc.send()
                    else:
                        proc.log(' >> Error! Invalid file size!')
                        return 1, data, data, 0
                else:
                    if query_response != 0:
                        proc.log(' >> ERROR, TM25 query response is invalid')
                    elif cmd_id != 0x0007:
                        proc.log(' >> ERROR, expected query response cmd id 0x0007, but received: %04X!' % cmd_id)
                    return 1, data, data, 0
            # ===========================================
            else:
                cmd_id = struct.unpack('!H', data[0:2])[0]
                data_len = struct.unpack('!H', data[2:4])[0]
                file_offset = struct.unpack('!I', data[4:8])[0]
            # ===========================================
            if cmd_id == 2 and data_len == 4:  # send sync file transfer packet
                proc.log(' >> TM25 file download. Resume from offset: %u' % file_offset)
                mess = struct.pack('!H', 3) + struct.pack('!H', 4) + struct.pack('!I', file_offset)
                proc.send()

                # # AA - must add file sending here
                time.sleep(1)
                proc.send_file(FS_filename, FS_chunk_size)

                return 0, data, data, 0
            elif cmd_id == 5 and data_len == 4:
                status_code = struct.unpack('!I', data[4:8])
                status_code = status_code[0]
                proc.log(' >> CMD_ID = 5 received, files to dl: %u, status: %s' % (files_to_dl, status_code))
                if status_code == 0:  # file download was successful
                    proc.log(' >> File download success')
                    if files_to_dl > 1:
                        proc.log(' >> More files to send, send [CMD_ID 0x0001] with Path parameter')
                        pass
                    elif files_to_dl == 1:
                        mess = struct.pack('!H', FMB_FT_FILE_CLOSE_SESSION_CMD_ID) + struct.pack('!H',
                                                                                                 0) + struct.pack('!I', 0)
                        proc.log(' >> Custom file download done, send [CMD_ID 0x0000]')
                        files_to_dl = 0
                        proc.send()

            else:
                proc.log(' >> Maybe TM25 file download packet, but cant parse %d' % (cmd_id))
        # ===================================================================
        else:
            pass  # unknown packet, probably not TM25 file upload related
    # ==============================

    def log(self, msg):
        try:
            self.file.write(gtime() + msg + '\n')
            self.file.flush()
            print(gtime() + str(msg))
        except Exception as msg:
            pass

    # ==============================
    def stop(self):
        proc.log(' >> Server trying to quit.')
        self.finished.set()
        # global t2
        # t2 = os.getpid()
        # ===========================================
        try:
            # self.s.shutdown(2)
            self.s.close()
            # self.s.settimeout(1)
            proc.log(' >> Connection closed.')
        except socket.error as msg:
            proc.log(' >> socket error: %s' % msg)
            PrintException()
        finally:
            # ===========================================
            try:
                self.join(1)
                proc.log(' >> Joining main program.')
            except RuntimeError as msg:
                sys.stderr.write("[ERROR] %s\n" % msg)
                proc.log(' >> Failed to join main program.')
                # os.popen("kill -9 " + str(t2))
                PrintException()
        self.join()
    # ==============================

    def run(self):
        global mess, addr, conn, req_sequence, user_input, encryption_enabled, waiting_for_multi, imei_resp_sent
        global FS_support, FS_inv_crc_packet, FS_filename, FS_packet_cnt, crc, FotaWeb, FOTA_WEB_2401_par
        single = b''
        proc.log(' >> Server version: %s' % SERVER_VERSION)
        if test == 0:  # real mode
            if TCP == 1:
                proc.log(' >> TCP server started : %s : %s. Timeout: %d sec' % (HOST, PORT, TCP_TIMEOUT))
            else:
                proc.log(' >> UDP server started : %s : %s' % (HOST, PORT))
            if beltrans_server == 1 and TCP == 1:
                proc.log(' >> Beltransputnik TCP auto server ON')
            elif beltrans_server == 1 and TCP == 0:
                proc.log(' >> Beltransputnik UDP auto server ON')
        else:  # test mode
            proc.log(' >> Tcp TEST server started : %s : %s' % (HOST, PORT))
        # ==============================
        if self.online_log == True:
            proc.log(' >> Online logging enabled')
        # ==============================
        if FotaWeb == 1:
            if FotaWeb_ST_communication == 1:
                st_comm_string = 'ST communication enabled'
            else:
                st_comm_string = ''
            proc.log(' >> FotaWeb service enabled; %s; 2401 param: %u' % (st_comm_string, FOTA_WEB_2401_par))
        # ==============================
        try:
            if ipv6_support == 0:
                self.s.bind((HOST, PORT))
            else:
                self.s.bind(('::', PORT))

            if TCP == 1:
                self.s.settimeout(10)
            proc.log(' >> Socket binding success!')
            proc.log(' >> Log file: %s' % main_file)
            proc.log(' >> CMD type: %u / 0x%02X' % (CMD_TYPE, CMD_TYPE))
            if (FS_support == 'FMB_UPL'):
                proc.log(' >> FMB file upload support enabled: %s, filenames to dl: %s' %
                         (FS_support, str(FS_file_name_list)))
            elif FS_support == 'FMA':
                if FS_packet_cnt == 0:
                    p_cnt_string = 'infinite'
                else:
                    p_cnt_string = '%u' % FS_packet_cnt
                proc.log(' >> File upload support enabled: %s, packet cnt: %s, delay: %.2f' %
                         (FS_support, p_cnt_string, FS_packet_delay / 10))
            if FS_inv_crc_packet >= 0:
                proc.log(' >> inv crc on packet no: %u enabled' % FS_inv_crc_packet)
            if FS_test_reject == 1:
                proc.log(' >> reject file dl on init packet is enabled!')
            waiting = 1
        except Exception:
            proc.log(' >> Failed to bind socket! Quitting.')
            self.finished.set()
            self.stop()
            PrintException()
        # ==============================
        while not self.finished.is_set():
            # ==============================
            self.connected = 0
            # ==============================
            if waiting == 1:
                proc.log(' >> Waiting for connection.\n')
                waiting = 0
            # ==============================
            if TCP == 1:
                self.s.listen(1)
                # use select to determine when a connection is available
                server_rfds, server_wfds, server_xfds = select.select([self.s], [], [], 2)
                # ==============================
                if self.s in server_rfds:
                    try:
                        conn, addr = self.s.accept()  # accept the connection
                        conn.setblocking(0)  # make new connection non-blocking

                        proc.log(' >> Connected from: %s\n' % str(addr))
                        self.connected = 1
                        self.disc.clear()
                        # if TCP == 1:
                        #   proc.log(' >> Forcefully close socket on connect @ TCP')
                        #  self.s.close()
                    except socket.error as msg:
                        self.connected = 0
                        proc.log(' >> Socket error: %s' % msg)
                        PrintException()
                    imei_resp_sent = 0
                    # ===========================================
                    while (not self.finished.is_set()) and (self.connected == 1) and (not self.disc.is_set()):
                        # ===========================================
                        try:
                            conn_rfds, conn_wfds, conn_xfds = select.select([conn], [], [conn], TCP_TIMEOUT)
                        except Exception as msg:
                            proc.log(' >> Connection selector exception: %s' % str(msg))
                            PrintException()
                        # ===========================================
                        if conn in conn_xfds:  # break on error
                            print('Got some kinda error.')
                            break
                        elif conn in conn_rfds:  # check for data received
                            try:
                                data = conn.recv(5120)
                            except Exception as msg:
                                proc.log(' >> Recv error: %s' % msg)
                                PrintException()
                                break
                            # ===========================================
                            if not data:
                                proc.log(' >> Client disconnected.')
                                waiting_for_multi = 0
                                break
                            else:
                                # ===========================================
                                # if data[0:10].find('IMEI:') != -1:
                                #    proc.log(' >> Online log detected, packets parsing disabled, simply logging')
                                #    self.online_log = True
                                # ===========================================
                                data_stat.received_bytes(len(data))
                                if self.online_log == True:
                                    proc.log(data)
                                else:
                                    proc.log(' >> Packet len: %u, data: %s' %
                                             (len(data), binascii.hexlify(data).upper()))

                                    if FotaWeb and data.startswith(b'FMBX') and data.endswith(b'ENDX'):
                                        global custom_file_type, fileDlOld, files_to_dl
                                        global file_type_to_send
                                        custom_file_type = ST.fotaweb_parse_packet(data)
                                        files_to_dl = countSetBits(custom_file_type)

                                        # If need to force file download from server side, uncomment here:
                                        # custom_file_type = 16
                                        # custom_file_type = 17

                                        print('Custom files to download: %u %u' % (files_to_dl, custom_file_type))
#                                         ST.fotaweb_parse_packet(data)
                                        # proc.log(' >>> Sending: %s' % binascii.hexlify(reply).upper())
                                        proc.log(' >> Sending FMB FotaWeb response: %s' % FS_support)
                                        if FotaWeb_ST_communication == 1:
                                            proc.log(' >> ST comm enabled; waiting for ST commands')
                                        elif FS_support == 'TM25' or FS_support == 'FM6X':
                                            proc.log(' >> TM25 download go')
                                            if FS_filename.lower().endswith('.xim'):
                                                # start fota
                                                proc.log(' >> Start FOTA: Server -> device')
                                                pars = par_pack(1000, 2, 1)
                                            elif FS_filename.lower().endswith('.cfg'):
                                                # start tcp config
                                                proc.log(' >> Start TCP CONFIG: Server -> device')
                                                pars = par_pack(1000, 3, 1)
                                            elif FS_filename.lower().endswith('.bin'):
                                                if FS_filename.lower().startswith('mt3333_fw'):      # If we need to send MT3333 FW
                                                    proc.log(' >> Start MT3333 FW Update: Server -> device')
                                                    pars = par_pack(1000, 7, 1)
                                                    file_type_to_send = dwl_file_types['MT3333_FW']
                                                elif FS_filename.lower().startswith('mt3333_da'):    # If we need to send MT3333 DA
                                                    proc.log(' >> Start MT3333 DA Update: Server -> device')
                                                    pars = par_pack(1000, 7, 1)
                                                    file_type_to_send = dwl_file_types['MT3333_DA']  # debug
                                                    # file_type_to_send = dwl_file_types['MT3333_DA']
                                                else:
                                                    proc.log(' >> Start BLE FW  UPDATE: Server -> device')
                                                    pars = par_pack(1000, 14, 1)
                                                    file_type_to_send = dwl_file_types['BLE_FW']
                                            elif FS_filename.lower().endswith('.tar'):
                                                proc.log(' >> Start Carrier APX FW UPDATE: Server -> device')
                                                pars = par_pack(1000, 14, 1)
                                                file_type_to_send = dwl_file_types['CARRIER_APX_FW']
                                            elif FS_filename.lower().endswith('.zip'):
                                                proc.log(' >> Start ADAS FW UPDATE: Server -> device')
                                                pars = par_pack(1000, 15, 1)
                                                file_type_to_send = dwl_file_types['ADAS_FW']
                                                proc.log(' >> Custom file type: %u' % file_type_to_send)
                                            elif FS_filename.lower().endswith('.bin') or FS_filename.lower().endswith('.dat') or FS_filename.lower().endswith('ephmgps', 0, 7):
                                                customFileTest = get_str_value_from_file('custom_file_transfer_test:')
                                                fileDlOld = int(get_str_value_from_file('File_DL_Old:'))
                                                if customFileTest == '0':
                                                    proc.log(' >> Start AGPS on old FW: Server -> device')
                                                    pars = par_pack(1000, 6, 1)
#                                                 elif (customFileTest == '1' and custom_file_type & 0x01 == 1
#                                                       or custom_file_type & 0x04 == 4):
#                                                     proc.log(' >> Start AGPS on new FW: Server -> device')
#                                                     pars = par_pack(1000, 7, 1)
                                                elif customFileTest == '1' and custom_file_type > 0:
                                                    proc.log(' >> Start AGPS on new FW: Server -> device')
                                                    pars = par_pack(1000, 7, 1)
                                                else:
                                                    proc.log(' >> no valid AGPS conditions')
                                                    pars = par_pack(1000, 1, 1)
                                            else:
                                                proc.log(
                                                    ' >> Unknown file type for sending to device! Dont know what operation type to set! Will set 1(do nothing)')
                                                pars = par_pack(1000, 1, 1)
                                        elif FS_support == 'FMB_UPL':
                                            # start file upload
                                            proc.log(' >> Start File Upload: device -> server')
                                            pars = par_pack(1000, 4, 1)
                                        else:
                                            # do nothing
                                            pars = par_pack(1000, 1, 1)
                                        if FotaWeb_ST_communication == 0:  # because if == 1, then we wait for ST commands
                                            proc.log(' >> Nothing to do here')
                                            # pars += par_pack(2000, EXT_IP, 0) + par_pack(2100, PORT, 2) + par_pack(2200, 'banga', 0) + par_pack(2300, '', 0) + par_pack(2400, '', 0)
                                            # pars += par_pack(2000, EXT_IP, 0) + par_pack(2100, PORT, 2) + par_pack(2200, 'banga', len('banga')) + par_pack(2300, ' ', len(' ')) + par_pack(2400, ' ', len(' ')) + par_pack(2401, 1, 1)
                                            pars += par_pack(2000, EXT_IP, 0) + par_pack(2100, PORT, 2) + par_pack(2200,
                                                                                                                   'banga', len('banga')) + par_pack(2300, '', len('')) + par_pack(2400, '',
                                                                                                                                                                                   len('')) + par_pack(2401, FOTA_WEB_2401_par, 1)
                                            nod = struct.pack('!H', 7)
                                            crc = 0
                                            c_crc16 = struct.pack('!H', crc16(pars, len(pars), 1))
                                            crc = 0
                                            reply = 'FMBX' + struct.pack('!I', len(pars)
                                                                         ) + nod + pars + nod + c_crc16 + 'ENDX'
                                            proc.log(' >> Sending FMB FotaWeb response: %s' %
                                                     binascii.hexlify(reply).upper())
                                            proc.log(' >>> Sending: %s' % binascii.hexlify(reply).upper())
                                            conn.send(reply)
                                    else:

                                        if waiting_for_multi == 1:
                                            print('previous + current: %s' %
                                                  (binascii.hexlify(single).strip(b'\r\n') + binascii.hexlify(data).strip(b'\r\n')).decode())
                                            # print('current: %s' % binascii.hexlify(data))
                                            print('adding two packets')
                                            combined = single + data
                                            data = combined
                                            waiting_for_multi = 0
                                        ret, single, data, packet_list = proc.data_check(data)
                                        # ===========================================
                                        # ex = 0 # exception controller; 0 no exception, 1 exception
                                        # if ex == 0:
                                        #    proc.process_data(single)
                                        # else:
                                        #    try:
                                        #        proc.process_data(single)
                                        #    except Exception as msg:
                                        #        proc.log(' >> [process_data] exception: %s\n' % str(msg) )
                                        if FS_support == 'FMB_UPL':
                                            # proc.log(' >> Starting file upload from device procedure')
                                            proc.file_upload_processor(packet_list)
                                        else:
                                            if ret == 1:
                                                proc.process_data(single)
                                                single = b''
                                                waiting_for_multi = 0
                                                print('')
                                            else:
                                                proc.log(' >> waiting for another packet')
                                                # Send close session command in case all custom files are sent out
                            # ===========================================
                        else:  # break if we have a timeout condition
                            # if self.test_no_resp == 0:
                            proc.log(' >> Connection timeout after %d seconds.' % TCP_TIMEOUT)
                            break
                            # else:
                            #    proc.log(' >> Session timeout disabled.\n')
                    # ===========================================
                    # close the inbound connection
                    waiting = 1
                    # self.online_log = False
                    if self.connected == 1:
                        conn.close()
                        proc.log(' >> Closing connection.')
                        data_stat.connection_closed()
                    # ===========================================
            elif TCP == 0:  # UDP SERVER PART
                try:
                    data, addr = self.s.recvfrom(5120)
                except Exception as msg:
                    proc.log(' >> Error [udp.recv]: %s\n' % str(msg))
                    PrintException()
                # ============
                if self.online_log == True:  # log 2 server logging
                    proc.log('%s' % data)
                else:
                    proc.log(' >> Connected from: %s' % str(addr))
                    # ============
                    if not data:
                        proc.log(' >> Client closed connection.')
                    else:
                        proc.log(' >> Packet len: %u, data: %s' % (len(data), binascii.hexlify(data).upper()))
                        proc.process_data(data)
        # ==============================
        if TCP == 1:
            proc.log(' >> TCP server terminating.')
        else:
            proc.log(' >> UDP server terminating.')
        if self.file.closed == False:
            try:
                self.file.close()
            except Exception as msg:
                PrintException()
                pass

    # ========================================================================
    def file_upload_processor(self, packet_list):
        global mess, crc, skip, file_crc, file_size, FS_file_path, FS_file_path_list, FS_file_name_list, FS_file_upl_target
        for packet in packet_list:
            command_id = struct.unpack('!H', packet[0:2])[0]
            if skip and command_id != 3:
                continue
            proc.log(' >> File upload cmd_id: 0x%04X' % command_id)
            # ================================================================
            if command_id == 0:
                proc.log(' >> INIT command received')
                protocol_id = struct.unpack('!H', packet[2:4])[0]
                imei = struct.unpack('!Q', packet[4:12])[0]
                settings = struct.unpack('!H', packet[12:14])[0]
                FS_chunk_size = struct.unpack('!H', packet[14:16])[0]
                self.file_upload_idx = 0
                for failas in FS_file_path_list:
                    if failas != None:
                        FS_file_upl_target = self.file_upload_idx
                        break
                    else:
                        self.file_upload_idx += 1  # move on to next file
                try:
                    os.remove(FS_file_name_list[FS_file_upl_target])
                except Exception as msg:
                    proc.log(' >> no need to delete file')
                mess = struct.pack('!H', FMB_FT_FILE_REQ_CMD_ID) + struct.pack('!H',
                                                                               len(FS_file_path_list[FS_file_upl_target])) + FS_file_path_list[FS_file_upl_target]
                proc.log(' >> Sending file req cmd_id, file upl target: %u, for file: %s' %
                         (FS_file_upl_target, FS_file_name_list[FS_file_upl_target]))
                proc.send()
                # ================================================================
            elif command_id == 1:
                proc.log(' >> Start file transfer cmd received')
                length = struct.unpack('!H', packet[2:4])[0]
                file_size = struct.unpack('!I', packet[4:8])[0]
                file_crc = struct.unpack('!H', packet[8:10])[0]
                if file_size == 0 or file_crc == 0:
                    size = 0
                    # mess = struct.pack('!H', FMB_FT_FILE_RESUME_CMD_ID) + struct.pack('!H', 4) + struct.pack('!I', size)
                    proc.log(' >> Cant get this file, device does not have it!')
                    proc.check_next_file_for_download()
                else:
                    try:
                        size = os.path.getsize(FS_file_name_list[FS_file_upl_target])
                    except Exception as msg:
                        proc.log(' >> Error, cant get file: %s size!' % FS_file_name_list[FS_file_upl_target])
                        size = 0
                    mess = struct.pack('!H', FMB_FT_FILE_RESUME_CMD_ID) + struct.pack('!H', 4) + struct.pack('!I', size)
                    proc.log(' >> Sending resume cmd_id, offset: %u' % size)
                    proc.send()
                    crc = 0
                # ================================================================
            elif command_id == 3:
                skip = False
                crc = 0
                try:
                    upl_file = open(FS_file_name_list[FS_file_upl_target], "rb")
                    file_data = upl_file.read()
                    crc16(file_data, len(file_data), 1)
                    upl_file.close()
                except Exception as msg:
                    proc.log(' >> Error! File: %s not found' % FS_file_name_list[FS_file_upl_target])
            # ================================================================
            elif command_id == 4:
                data_length = struct.unpack('!H', packet[2:4])[0]
                file_data = packet[4:4 + data_length - 2]
                r_crc = struct.unpack('!H', packet[4 + data_length - 2:4 + data_length])[0]
                c_crc = crc16(file_data, len(file_data), 1)
                if r_crc == c_crc:
                    upl_file = open(FS_file_name_list[FS_file_upl_target], "ab")
                    upl_file.write(file_data)
                    upl_file.close()
                    received = os.path.getsize(FS_file_name_list[FS_file_upl_target])
                    total = file_size
                    proc.log(' >> File upload status: %u/%u  %03u %%\n' %
                             (received, total, float(received * 100 / total)))
                else:
                    skip = True
                    proc.log(
                        ' >> Error while receiving file, r_crc: 0x%04X, c_crc: 0x%04X. Requesting resend' %
                        (r_crc, c_crc))
                    mess = struct.pack('!H', 2) + struct.pack('!H', 4) + struct.pack('!I',
                                                                                     os.path.getsize(FS_file_name_list[FS_file_upl_target]))
                    proc.send()
                if os.path.getsize(FS_file_name_list[FS_file_upl_target]) == file_size and file_crc == c_crc:
                    proc.log(' >> file received successfully')
                    proc.check_next_file_for_download()
            # ================================================================
            else:
                proc.log(' >> Error, undefined cmd_id received: %04X' % command_id)

            # ================================================================
    # ==============================
    def check_next_file_for_download(self):
        global mess, crc, skip, file_crc, file_size, FS_file_path, FS_file_path_list, FS_file_name_list, FS_file_upl_target
        FS_file_name_list[FS_file_upl_target] = None
        FS_file_path_list[FS_file_upl_target] = None
        self.file_upload_idx = 0
        for failas in FS_file_name_list:
            if failas != None:
                FS_file_upl_target = self.file_upload_idx
                break
            else:
                self.file_upload_idx += 1
        if self.file_upload_idx > 0 and FS_file_name_list[FS_file_upl_target] != None:
            proc.log(' >> Got more files to upload, next file target: %u / %s' %
                     (FS_file_upl_target, FS_file_name_list[FS_file_upl_target]))
            try:
                os.remove(FS_file_name_list[FS_file_upl_target])
            except Exception as msg:
                proc.log(' >> no need to delete file')
            mess = struct.pack('!H', FMB_FT_FILE_REQ_CMD_ID) + struct.pack('!H',
                                                                           len(FS_file_path_list[FS_file_upl_target])) + FS_file_path_list[FS_file_upl_target]
            proc.log(' >> Requesting next file: %s' % FS_file_name_list[FS_file_upl_target])
            proc.send()
        else:
            proc.log(' >> All files uploaded. Finish')
            mess = struct.pack('!H', 5) + struct.pack('!H', 4) + struct.pack('!I', 0)
            proc.send()

    # ==============================
    def data_check(self, data):
        global C08, C8E, C61, C61E, C18, C32, C33
        global waiting_for_multi, temp
        global FS_support, FS_chunk_size
        global files_to_dl
        """
        if return == 1, single will be processed, if return == 0 will wait for another packet
        """
        # check if this is imei
        # print('running data check')
        # =====================================================================
        if FS_support != 'FMB_UPL':
            if len(data) >= 2 and waiting_for_multi == 0:
                imei_len = struct.unpack('!H', data[0:2])
                if imei_len[0] == 0x000F:
                    # print('returning supposedly this is imei packet')
                    waiting_for_multi = 0
                    return 1, data, data, 0
            # =======================================================================
            # 2 check if this is GPRS packet
            # =======================================================================
            if len(data) >= 9 and waiting_for_multi == 0:
                if data[8] == C12:  # if gprs packet => process it
                    waiting_for_multi = 0
                    return 1, data, data, 0
        # =====================================================================
        if FS_support == 'GGG':
            if data.startswith(b'START') or data.startswith(b'RESEND') or data.startswith(b'FLASHING SUCCEEDED') or data.startswith(b'retry,'):
                proc.log(' >> %s detected' % data.strip(b'\r\n\t'))
                return 1, data, data, 0
            if data.find(b'ggg_fw.bin') != -1:
                proc.log(' >> Detected GGG FW upload from FM!')
                return 1, data, data, 0
        # =====================================================================
        elif FS_support == 'TM25':
            self.process_file(data, self.process_xim)
        # =====================================================================
        elif FS_support == 'FM6X':
            self.process_file(data, self.process_fm640_xim)
        # ===================================================================
        elif FS_support == 'FMA':
            # global crc, mess
            # crc = 0
            poz = data.find(b',')
            imei = data[0:15]
            if data.startswith(b'START'):
                proc.log(' >> need to start sending FAKE FOTA!\r\ns')
                proc.send_fake_fota()
            elif poz == 15 and imei.isdigit() == True:
                proc.log(' >> presumably FM device sent imei and filename; send fake file size and CRC\r\n')
                mess = '123456,ABCD\r\n'
                proc.send()
            else:
                pass
        # ===================================================================
        elif FS_support == 'FMB_UPL':
            try:
                index = 0
                packet_list = list()
                data = temp + data
                command_id = struct.unpack('!H', data[index:index + 2])[0]
                if command_id == 0:  # special case for INIT packet because of different packet structure
                    packet_list.append(data)
                else:
                    while (True):
                        index += 2
                        data_length = struct.unpack('!H', data[index:index + 2])[0]
                        index += 2
                        if (len(data[index:]) > (data_length)):
                            packet_list.append(data[index - 4:data_length + index])
                            index += data_length
                        elif (len(data[index:]) == (data_length)):
                            packet_list.append(data[index - 4:data_length + index])
                            index += data_length
                            temp = ''
                            break
                        else:
                            temp = data[index - 4:]
                            break
                        if len(data[index:]) < 8:
                            temp = data[index:]
                            break
                return 1, b'', b'', packet_list
            except Exception as msg:
                proc.log(' >> %s\n' % str(msg))
                PrintException()
        # =======================================================================
        # 2. check crc, if its ok give it to data process, its single packet
        # =======================================================================
        if len(data) >= 9:
            # print('len > 9')
            if data[8] in (C08, C8E, C61, C61E, C18, C32, C33):
                # print('9th byte == 0x08, records detected')
                r_crc = struct.unpack('!H', data[-2:])
                r_crc2 = struct.unpack('!H', data[-3:-1])
                for_crc = data[8:len(data) - 4]
                for_crc2 = data[8:len(data) - 5]
                c_crc = crc16(for_crc, len(for_crc), 0)
                last_0x31 = struct.unpack('B', data[-1:])[0]
                c_crc_0x31 = crc16(for_crc2, len(for_crc), 0)
                # ----------
                # print('last byte: 0x%02X' % (last_0x31) )
                # print('r_crc2: 0x%04X' % r_crc2[0] )
                # print('c_crc2: 0x%04X' % c_crc_0x31 )
                # T1 = (r_crc2[0] == c_crc_0x31)
                # T2 = (last_0x31 == 49)
                # print('T1: %s, T2: %s, type(T2): %s' % (T1, T2, type(last_0x31)) )
                # ----------
                if r_crc[0] == c_crc or (r_crc2[0] == c_crc_0x31 and last_0x31 == 0x31):  # single packet
                    rez = 1
                    if last_0x31 == 0x31:
                        data = data[:-1]
                        print('have 0x31 at the end')
                    else:
                        print('no 0x31 at the end')
                        data = data
                    single = data
                    proc.log(' >> this is correct single packet, CRC OK')
                    return rez, single, data, 0
                else:
                    proc.log(' >> calculated crc: %04X, received crc: %04X' % (c_crc, r_crc[0]))
                    proc.log(' >> crc calculated for data length: %u' % len(for_crc))
                    rez = 0
                    proc.log(' >> possibly multipacket detected. CRC MISMATCH DETECTED!')

                    # proc.log(' >> Possible mul')

                    no_of_data = struct.unpack('!I', data[4:8])
                    all_len = len(data)
                    proc.log(' >> Unpacked no of data: %08X == %d, total len: %d' %
                             (no_of_data[0], no_of_data[0], all_len))

                    if (no_of_data[0] + 12 == all_len):
                        proc.log(' >> packet structure is okey! not sending ack to packet (due to crc mismatch)')
                        return 0, data, data, 0
                    else:  # possible multipacket
                        proc.log(' >> packet structure is wrong! waiting for multipacket (expecting rest of the packet)')
                    waiting_for_multi = 1
                    return 0, data, data, 0
                    # ===========================================================
                    # if all_len > (no_of_data[0] + 12):     # detected possible multiple packets
                    #    # buvo: if all_len > (len(data)+12):     # detected possible multiple packets
                    #    single = data[0:no_of_data[0]+4+4+4] # single packet from start
                    #    data = data[no_of_data[0]+4+4+4:]    # rest of data packet
                    #    proc.log(' >> Presumed single packet: %s' % binascii.hexlify(single)) # 4 starting bytes and 4 crc bytes 4 no_of_data bytes
                    #    proc.log(' >> Rest of packet: %s' % binascii.hexlify(data))
                    #    return rez, single, data
                    # else:
                    #    proc.log(' >> Declared single packet len: %d, total received bytes: %d. This doesn`t add up.' % (no_of_data[0]+12, all_len))
                    #    # bad CRC and file download in progress
                    #    #if self.file_dl_in_progress == 1:
                    #    #    proc.send_retry_packet(data)
                    #    return 1, data, data, 0 # not tacho packet so dont care analyze right away
                    # ===========================================================
            else:
                proc.log(' >> [data.check] 9th byte not 0x08, process right away')
                return 1, data, data, 0  # not tacho packet so dont care analyze right away
        # ----------
        proc.log(' >> [data.check] len < 9, returnin')
        return 1, data, data, 0  # not tacho packet so dont care analyze right away

    # ==============================
    def process_data(self, data):
        global mess, addr, time_for_bad, bad_pids, tcp_config_send, imei_resp_sent, crc, doubleanswer, ackTo_C12
        global FS_support, FS_init_pos, FS_sent_packets, FS_sent_size, FS_recalc_done, FS_sending, FS_abort, FS_filename
        global C08, C8E, C61, C61E, C18, nod_plus_gprs, c36_temp, c36_first_half_size
        # ==============================
        try:
            if TCP == 1:
                # print('check ', type(data[15]), data[15], data[15], bytes(data[15], 'utf-8'))
                # ===============================================================
                # #===========================================
                # time.sleep(1)
                # r_crc = struct.unpack('!H', data[-2:])
                # for_crc = data[8:len(data)-4]
                # c_crc = crc16(for_crc, len(for_crc), 0)
                # #---------
                # #print(for_crc, len(for_crc))
                # #print(type(r_crc), type(c_crc), r_crc[0], c_crc)
                # #--------
                # if r_crc[0] == c_crc:
                #    #proc.log(' >> CRC OK')
                #    pass
                # else:
                #    print(for_crc, len(for_crc))
                #    print(type(r_crc), type(c_crc), r_crc[0], c_crc)
                #    proc.log(' >> Received CRC: %X, calculated CRC: %X' % (r_crc[0], c_crc) )
                #    proc.log(' >> CRC NOK')
                # if r_crc[0] == c_crc:
                # ===============================================================
                if data.startswith(b'START'):  # or data.startswith('RESEND'):
                    FS_init_pos = 0
                    FS_sent_size = 0
                    FS_recalc_done = False
                    crc = 0
                    if FS_support == 'GGG':
                        proc.send_file(FS_filename, 256)
                # ------------------------------------
                elif data.startswith(b'DOWNLOAD FAILED') and FS_support == 'GGG':
                    proc.log(' >> FM notified that GGG FW update failed, closing socket')
                    proc.close_socket()
                # ------------------------------------
                elif (data.startswith(b'FLASHING SUCCEEDED') or data.startswith(b'RESEND')) and FS_support == 'GGG':
                    if data.startswith(b'FLASHING SUCCEEDED'):
                        proc.log(' >> FM notified that GGG FW update is successfull! closing socket')
                    elif data.startswith(b'RESEND'):
                        proc.log(' >> FM wants GGG FW data resend. Closing link. Not sending.')
                    proc.close_socket()
                # ------------------------------------
                elif data.find(b'ggg_fw.bin') != -1 and FS_support == 'GGG':
                    proc.send_ggg()
                # ------------------------------------
                elif data.find(b'retry') != -1:
                    # ------------------------------------
                    if FS_sending == True:
                        mess = 'SYNC'
                        if proc.send() == -1:
                            proc.log(' >> Error. Failed sync packet sending')
                        else:
                            proc.log(' >> Sending SYNC packet OK')
                        time.sleep(2)
                    # ------------------------------------
                    if FS_support == 'GGG':
                        poz = data.find(b',')
                    elif FS_support == 'TM25' or FS_support == 'FM6X':
                        poz = data.find(b':')
                    if poz != -1:  # found it
                        position = data[poz + 1:].strip(b'\r\n\t')
                        if position.isdigit() == True:
                            proc.log(
                                ' >> FM requested to cancel sending and to resend from certain position: %u\n' %
                                int(position))
                            FS_init_pos = int(position)
                            FS_sent_size = 0
                            FS_recalc_done = False
                            crc = 0
                            mess = 'SYNC'
                            if proc.send() == -1:
                                proc.log(' >> Error. Failed sync packet sending')
                            else:
                                proc.log(' >> Sending SYNC packet OK')
                                time.sleep(2)
                            if FS_sending == True:
                                proc.log(' >> Sending in progress, attempting to stop and resend')
                                FS_abort = True
                                waiting_cnt = 0
                                while FS_sending == True and waiting_cnt < 10:
                                    waiting_cnt += 1
                                    proc.log(' >> Waiting for sending procedure to stop: 5u / %u' % (waiting_cnt, 10))
                                    time.sleep(1)
                                if FS_sending == False:
                                    proc.log(' >> Starting sending procedure anew')
                                    if FS_support == 'GGG':
                                        proc.send_file(FS_filename, 256)
                                    elif FS_support == 'TM25' or FS_support == 'FM6X':
                                        proc.send_file(FS_filename, 1024)
                                else:
                                    proc.log(' >> Failed to stop sending procedure, cant start anew')
                            else:
                                if FS_support == 'GGG':
                                    proc.send_file(FS_filename, 256)
                                elif FS_support == 'TM25' or FS_support == 'FM6X':
                                    proc.send_file(FS_filename, 1024)
                        else:
                            proc.log(' >> FM requested to cancel sending, but server could not parse file position. Not a digit.')
                            proc.close_socket()
                    else:
                        proc.log(
                            ' >> FM requested to cancel sending, but server could not parse file position. No file position provided.')
                        proc.close_socket()
                # ------------------------------------
                elif data.startswith(b'DOWNLOAD OK') and (FS_support == 'TM25' or FS_support == 'FM6X'):
                    proc.log(' >> TM25 file upload procedure successfull!')
                    proc.close_socket()
                # ------------------------------------
                elif data.startswith(b'DOWNLOAD FAILED') and (FS_support == 'TM25' or FS_support == 'FM6X'):
                    proc.log(' >> TM25 file upload procedure failed!')
                    proc.close_socket()
                # ------------------------------------
                elif data.find(b',new') != -1 and (FS_support == 'TM25' or FS_support == 'FM6X'):
                    if os.path.exists(os.getcwd() + '\\' + FS_filename) == True:
                        FS_sent_packets = 0
                        crc = 0
                        file_size = os.path.getsize(FS_filename)
                        f = open(FS_filename, 'rb')
                        file_data = f.read()
                        f.close()
                        c_crc16 = crc16(file_data, file_size, 1)
                        reply = struct.pack('B', 1)
                        reply += '%u,%04X' % (file_size, c_crc16)
                        proc.log(' >> sending ACK response to new file dl: %s' % reply)
                        proc.log(' >>> Sending: %s' % binascii.hexlify(reply).upper())
                        conn.send(reply)
                    else:
                        proc.log(' >> Error! target file: %s not found!' % FS_filename)
                        proc.close_socket()
                # ------------------------------------
                elif data.find(b',resume') != -1 and (FS_support == 'TM25' or FS_support == 'FM6X'):
                    if os.path.exists(os.getcwd() + '\\' + FS_filename) == True:
                        reply = struct.pack('B', 1)
                        proc.log(' >> sending ACK response to resume file dl: %s' % reply)
                        proc.log(' >>> Sending: %s' % binascii.hexlify(reply).upper())
                        conn.send(reply)
                    else:
                        proc.log(' >> Error! target file: %s not found!' % FS_filename)
                        proc.close_socket()
                # ------------------------------------
                elif (len(data) == 17) or ((len(data) > 17) and (data.count(b";") == 4) and (data.startswith(b'Ver:', 17, 21))):
                    proc.log(' >> imei received: %s' % str(data[2:]))
                    rec_imei = data[2:17]
                    # hardcoded_imei = '356173065281912'
                    hardcoded_imei = ''
                    if hardcoded_imei != '' and hardcoded_imei != rec_imei:
                        proc.log(' >> unwanted device connected, disconnecting')
                        self.close_socket()
                        return
                    if beltrans_server == 1:
                        # -----------
                        if time_for_bad > 0:  # sending bad reply
                            print('time for bad response')
                            reply = struct.pack('B', 255)
                        else:
                            last_two = (data[15:17])
                            # print('last two: %s' % last_two)
                            nr = int(last_two)
                            # print('last two val: %d' % nr)
                            rep1, rep2 = get_reply(nr)
                            print('resp1: %02X, resp2: %s' % (rep1, rep2))
                            reply = struct.pack('B', rep2[5] & 0xFF)
                    else:
                        # -----------
                        if time_for_bad > 0:  # sending bad reply
                            print('time for bad response')
                            reply = struct.pack('B', 255)
                        else:
                            reply = struct.pack('B', 1)
                            if str(data[2:17]) == get_str_value_from_file('tcp_conf_imei:'):
                                tcp_config_send = 1
                                proc.log(' >> TCP CONFIG IMEI DETECTED, will start tcp config sending!\n')
                            else:
                                tcp_config_send = 0
                    # -----------
                    if juliui_no_reply_7013 != 1:
                        conn.send(reply)
                        proc.log(' >> sending accept imei: %s\n' % str(binascii.hexlify(reply)))
                        imei_resp_sent = 1
                        if tcp_config_send == 1:
                            self.send_tcp_config()
                # ===========================================
                elif data.find(b'#NEED SYNC') != -1:
                    proc.log(' >> Got imei and need sync request from FM\n')
                    reply = struct.pack('B', 1)
                    conn.send(reply)
                    proc.log(' >> sending accept imei: %s\n' % str(binascii.hexlify(reply)))
                    ts = time.gmtime(time.time())
                    year = ts.tm_year
                    month = ts.tm_mon
                    day = ts.tm_mday
                    hour = ts.tm_hour
                    minutes = ts.tm_min
                    sec = ts.tm_sec
                    reply = codec12(('#SYNC=%d,%02d,%02d,%02d,%02d,%02d' %
                                    (year, month, day, hour, minutes, sec)) + '\r\n', C12, CMD_TYPE)
                    conn.send(reply)
                    proc.log(' >> sending sync info to FM: %s\n' % str(binascii.hexlify(reply)))
                # ===========================================
                elif len(data) == 1 and data[0] == 0xFF:
                    proc.log(' >> Network ping received from FM.\n')
                # ===========================================
                # elif (data[15] == 35) and data[8] == 0x0C: # kazkodel data[15] yra int !
                elif len(data) >= 11 and (data[8] == C12 or data[8] == C14) and ((data[10] == GPRS_CMD_FM_TO_SERVER) or ((data[10] >= 22) and (data[10] <= 24)) or ((data[10] == 0x11))):
                    # print(gtime(), ' GPRS reply: %s\n' % str(data))
                    # proc.log(' >> GPRS reply: %s\n' % str(data))
                    reply_decode(data, data[10], data[8])
                    # proc.log(' >> raw data: %s\n' % data)
                # ===========================================
                elif len(data) >= 11 and data[8] == C13 and ((data[10] == GPRS_CMD_FM_TO_SERVER) or ((data[10] >= 22) and (data[10] <= 24))):
                    Codec13_decode(data, data[10])
                elif len(data) >= 11 and data[8] == C17 and ((data[10] == GPRS_CMD_FM_TO_SERVER) or ((data[10] >= 22) and (data[10] <= 24))):
                    Codec17_decode(data, data[10])
                # and (data[15] != 13) and (data[10] != 9) and (data[15] != 112) ): # and ((data[15] != 35) and (data[8] != 0x0C))
                elif ((len(data) != 17) and (len(data) >= 20) and ((data[8] == C8E) or (data[8] == C08) or (data[8] == 25) or (data[8] == 22) or (data[8] == C32) or (data[8] == C33) or (data[8] == C61) or (data[8] == C61E) or (data[8] == C18))):
                    # proc.log(' >> Received Bytes: %s, data: %s' % (len(data), str(data)))
                    idx = len(data) - 5

                    # print(idx, type(idx), data[idx], type(data[idx]), int(idx), data[int(idx)])
                    if nod_plus_gprs == 1 or nod_plus_gprs == 2:

                        reply = struct.pack('BBBB', 0, 0, 0, data[idx])
                        gprs = codec12('getinfo' + '\r\n', C12, CMD_TYPE)
                        if nod_plus_gprs == 1:
                            final = reply + gprs
                            proc.log(' >> Sending NOD: %s + gprs: %s\n' % (str(binascii.hexlify(reply)), gprs))
                        elif nod_plus_gprs == 2:
                            final = gprs + reply
                            proc.log(' >> Sending gprs: %s + NOD: %s\n' % (gprs, str(binascii.hexlify(reply))))
                        conn.send(final)
                    else:
                        # if reject_nod_reply == 1:
                        #     proc.log(' >> Reject enabled, sending reject  reply.\n')
                        #     reply = struct.pack('BBBB', 0, 0, 0, data[idx] - 1)
                        #     conn.send(reply)
                        #     proc.log(' >> Sending NOD: %s\n' % str(binascii.hexlify(reply)))
                        if reject_nod_reply == 1:
                            proc.close_socket()
                        if block_nod_reply == 0:  # blocking disabled
                            reply = struct.pack('BBBB', 0, 0, 0, data[idx])
                            conn.send(reply)
                            proc.log(' >> Sending NOD: %s\n' % str(binascii.hexlify(reply)))
                        else:
                            # reply = struct.pack('BBBB', 0,0,0,0)
                            # conn.send(reply)
                            proc.log(' >> Block enabled, not sending NOD reply.\n')
                            # proc.log(' >> Block enabled, sending negative NOD reply.\n')
                # ===========================================
                # 13 yra \r zenklas. tuscia msg su \r\n siuncia FM42.19 FW kai ner ka atsakyt
                elif len(data) >= 16 and (data[15] == 13):
                    proc.log(' >> CID 05 reply received. tipo rn, data: %s\n' % binascii.hexlify(data))
                # ===========================================
                elif len(data) >= 11 and data[8] == C12 and data[10] == 9:
                    try:
                        proc.log(' >> Garmin error packet received. Code 0x%02X\n' % data[18])
                    except Exception as msg:
                        proc.log(' >> Garmin error packet parsing error: %s\n' % str(msg))
                        PrintException()
                # ===========================================
                elif len(data) >= 11 and data[8] == C12 and data[10] == 8:
                    try:
                        proc.log(' >> Garmin data packet received\n')
                    except Exception as msg:
                        proc.log(' >> Garmin data packet parsing error: %s\n' % str(msg))
                        PrintException()
                # ===========================================
                # passenger counter record received
                elif len(data) >= 11 and data[8] == C12 and data[10] == PSG_CNT_REC_RECEIVE:
                    bus_id = 0
                    frame_id = 0
                    try:
                        bus_id = struct.unpack('!I', data[15:19])[0]
                        frame_id = struct.unpack('!H', data[19:21])[0]
                        proc.log(' >> Passenger counter record received, bus id: %u, frame id: %u' % (bus_id, frame_id))
                    except Exception as msg:
                        proc.log(' >> Error while parsing psg cnt record: %s\n' % str(msg))
                        PrintException()
                    bus_frame = struct.pack('!I', bus_id) + struct.pack('!H', frame_id)
                    reply = codec12('K' + bus_frame + '\n', C12, PSG_CNT_REC_RESPONSE)
                    proc.log(' >> Sending response: %s' % binascii.hexlify(reply).upper())
                    conn.send(reply)
                # ===========================================
                elif len(data) >= 16 and (data[15] == 112):
                    proc.log(' >> ping reply received.\n')
                    # proc.log(' >> data: %s' % binascii.hexlify(data))
                # ===========================================
                elif data.find(b'give epo') != -1:
                    # global mess
                    send_by_size = 512
                    epo_filename = get_str_value_from_file('epo_file:')
                    try:
                        if os.path.exists(os.getcwd() + '\\' + epo_filename) == False:
                            proc.log(
                                ' >> Filename %s is not present in the folder! EPO file sending canceled' %
                                epo_filename)
                        else:
                            file_size = os.path.getsize(epo_filename)
                            f = open(epo_filename, 'rb')
                            data = f.read()
                            f.close()
                            FS_sent_size = 0
                            packet_no = 0
                            while FS_sent_size != file_size:
                                if FS_sent_size + send_by_size <= file_size:
                                    file_chunk = data[FS_sent_size:FS_sent_size + send_by_size]
                                    mess = file_chunk
                                    FS_sent_size += send_by_size
                                    proc.log(' >> Sending packet: %02u, packet size: %u, total sent: %u\n' %
                                             (packet_no, len(file_chunk), FS_sent_size))
                                    proc.send()
                                else:
                                    file_chunk = data[FS_sent_size:]
                                    mess = file_chunk
                                    FS_sent_size = file_size
                                    proc.log(' >> Sending packet: %02u, packet size: %u, total sent: %u\n' %
                                             (packet_no, len(file_chunk), FS_sent_size))
                                    proc.send()
                                time.sleep(0.3)  # 300 ms delay
                                packet_no += 1
                            # ----------------------------------------
                        proc.log(' >> EPO sending over\n')
                    except Exception as msg:
                        proc.log(' >> EPO sending exception: %s' % str(msg))
                        PrintException()
                elif len(data) >= 11 and data[8] == C34:
                    proc.log(">> Codec.34 packet got")
                    Codec34_decode(data[10:-5])
                    reply = [0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x04,
                             0x23, 0x01, 0x00, 0x01, 0x00, 0x00, 0x84, 0x9B]
                    reply2 = b""
                    for _b in reply:
                        reply2 += struct.pack('B', _b)
                    conn.send(reply2)
                elif len(data) >= 11 and (data[8] == C36 or (c36_first_half_size > 0)):
                    proc.log(">> Codec.36 packet got")
                    if (len(data) < 1800 and c36_first_half_size == 0):
                        proc.log(">> First half of Codec.36 packet got")
                        c36_first_half_size = len(data)
                        c36_temp = bytearray(data)
                    else:
                        if c36_first_half_size > 0:
                            proc.log(">> Second half of Codec.36 packet got")
                            c36_temp[c36_first_half_size:] = bytearray(data)
                            Codec36_decode(c36_temp[10:-5])
                        else:
                            Codec36_decode(data[10:-5])
                        reply = [0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x0A, 0x0C, 0x01,
                                 0x47, 0x00, 0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x22, 0xDE]
                        reply2 = b""
                        for _b in reply:
                            reply2 += struct.pack('B', _b)
                        conn.send(reply2)
                        c36_temp = []
                        c36_first_half_size = 0
                # ===========================================
                elif data.startswith(b"ID#"):
                    proc.log(" >> Journeytech spec packet received:")
                    proc.log(' >> Data: %s' % str(data))
                    nod = 1
                    reply = struct.pack('BBBB', 0, 0, 0, nod)
                    conn.send(reply)
                    proc.log(' >> Sending NOD: %s\n' % str(binascii.hexlify(reply)))
                # ===========================================
                elif is_valid_json(data):
                    proc.log(" >> JSON packet received:")
                    proc.log(' >> Data: %s' % str(data))
                    nod = 1
                    reply = struct.pack('BBBB', 0, 0, 0, nod)
                    conn.send(reply)
                    proc.log(' >> Sending NOD: %s\n' % str(binascii.hexlify(reply)))
                else:
                    proc.log(' >> Unknown packet: %s\n' % binascii.hexlify(data))
                    proc.log(' >> Data: %s' % str(data))
            # ===========================================
            else:  # UDP packet processing
                last_0x31 = struct.unpack('B', data[-1:])[0]
                if last_0x31 == 0x31:
                    print('have 0x31 at the end')
                    data = data[:-1]  # remove 0x31 at the end
                # ===========================================
                if len(data) == 1 and data[0] == 0xFF:
                    proc.log(' >> Network ping received from FM.\n')
                # ===========================================
                elif len(data) >= 8 and (data[8] == C12 or data[8] == C14):  # kazkodel data[15] yra int !
                    reply_decode(data, data[10], data[8])
                    if ackTo_C12 == True:
                        msg = struct.pack('BBBBBBB', 0, 0, 0, 0, 0, 3, 3)
                        print('reply forming ok. Will send ACK to Codec.12')
                        self.s.sendto(msg, addr)
                # ===========================================
                elif len(data) >= 15 and data[15] == 112:
                    proc.log(' >> ping reply received.\n')
                # ===========================================
                elif len(data) >= 3 and data[2] == 0xca and data[3] == 0xfe:
                    avl_packet_id = data[5:6]
                    if beltrans_server == 1:
                        if len(data) >= 24:
                            imei_last_two = int(data[21:23])
                            # print('imei last two: %s' % imei_last_two)
                        else:
                            imei_last_two = 0
                        mid = struct.unpack('B', avl_packet_id)[0]
                        ST, val = get_reply(imei_last_two)
                        ST = val[5] & 0xFF
                        udp_pid = (mid & ST)
                        udp_nod = data[len(data) - 1]
                        # return st, [y,m,d,s,imei, st&0xFF]
                        printing = 'y: %d, m:%d, d:%d, spk: %d, last2: %d, final_nr: %d/0x%02X, pid: 0x%02X, ST:0x%02X, sending: 0x%02X' % (
                            val[0], val[1], val[2], val[3], val[4], val[5], val[5] & 0xFF, mid, ST, mid & ST)
                        proc.log(' >> %s' % printing)
                    else:
                        udp_pid = data[5:6]
                        udp_nod = data[-1:]
                        udp_pid = struct.unpack('B', udp_pid)[0]
                    # ----------------------------
                    try:
                        udp_nod = struct.unpack('B', udp_nod)[0]
                        # print('udp_nod: %d' % udp_nod, type(udp_nod))
                        # ----------------------------
                        if time_for_bad > 0:  # == 1:
                            udp_pid = 255
                        # elif time_for_bad == 2:
                            # udp_pid = bad_pids
                            # bad_pids = bad_pids -1
                        if time_for_bad > 0:
                            print('time for bad response')
                        # ----------------------------
                        # msg = struct.pack('BBBBBBB', 0,1,0,2,3,udp_pid,udp_nod)
                        msg = struct.pack('BBBBBBB', 0, 0, 0, 0, 0, udp_pid, udp_nod)
                        print('reply forming ok')
                        # ----------------------------
                        # hardcoded_imei = '356307040826850'#356307042441013'
                        # hardcoded_imei = '356307046678529'
                        hardcoded_imei = ''
                        # check imei
                        full_imei = data[8:8 + 15]
                        proc.log(' >> received imei: %s' % full_imei)
                        if (full_imei != hardcoded_imei) and hardcoded_imei != '':
                            msg = 'nieko nezinau, duomenu nepriimu!\r\n'
                            proc.log(' >> %s' % msg)
                            # self.s.sendto(msg, addr)
                        else:  # correct imei
                            # ----------------------------
                            if block_nod_reply == 0:  # blocking disabled
                                proc.log(' >> sending udp reply to records: %s\n' % binascii.hexlify(msg))
                                # proc.log(' >> not sending udp reply\n')
                                if time_for_bad == 2:
                                    self.s.sendto(msg, addr)
                                    self.s.sendto(msg, addr)
                                    self.s.sendto(msg, addr)
                                    self.s.sendto(msg, addr)
                                    self.s.sendto(msg, addr)
                                elif doubleanswer == True:
                                    self.s.sendto(msg, addr)
                                    self.s.sendto(msg, addr)
                                else:
                                    self.s.sendto(msg, addr)
                                    pass
                            else:
                                proc.log(' >> Block enabled, not sending NOD reply.\n')
                                # proc.log(' >> Block enabled, sending negative NOD reply.\n')
                                # msg = struct.pack('BBBBBBB', 0,0,0,0,0,udp_pid,0)
                                # self.s.sendto(msg, addr)

                    except Exception as msg:
                        proc.log(' >> Error [udp]: %s\n' % str(msg))
                        PrintException()
                    if instant_codec14_reply == True:
                        try:
                            proc.log(' >> instant codec14 reply (with delay: %d ms)' %
                                        instant_codec14_reply_delay_ms)
                            full_imei = '0' + \
                                data[8:8 + 15].decode('utf-8')
                            command = 'getinfo'
                            final_data = full_imei + command
                            final_data = final_data.encode('utf-8')
                            if instant_codec14_reply_delay_ms:
                                time.sleep(
                                    instant_codec14_reply_delay_ms / 1000)
                            mess = codec14(final_data, 1, C14, CMD_TYPE)
                            print('will try to send packet: %s Command: %s' %
                                    (binascii.hexlify(mess), command))
                            proc.send()
                        except Exception as e:
                            print(e)
                # ===========================================
                # For JSON records, PID will always be 0
                elif is_valid_json(data):
                    proc.log(" >> JSON packet received:")
                    proc.log(' >> Data: %s' % str(data))
                    msg = struct.pack('BBBBBBB', 0, 0, 0, 0, 0, 0, 1)
                    self.s.sendto(msg, addr)
                # ===========================================
                else:
                    proc.log(' >> Unknown packet: %s\n' % binascii.hexlify(data))
            # ===========================================
        except Exception as msg:
            proc.log(' >> Server parser did not identify the received packet. Error: %s\n' % str(msg))
            PrintException()

        # self.disc.set()
    # ==============================
    def send_tcp_config(self):
        global mess
        send_by_size = 512
        tcp_config_file_name = get_str_value_from_file('tcp_conf_file:')
        try:
            if os.path.exists(os.getcwd() + '\\' + tcp_config_file_name) == False:
                proc.log(' >> Filename %s is not present in the folder! TCP CONFIG sending canceled' % tcp_config_file_name)
            else:
                file_size = os.path.getsize(tcp_config_file_name)
                f = open(tcp_config_file_name, 'rb')
                data = f.read()
                f.close()
                FS_sent_size = 0
                packet_no = 0
                while FS_sent_size != file_size:
                    if FS_sent_size + send_by_size <= file_size:
                        file_chunk = data[FS_sent_size:FS_sent_size + send_by_size]
                        try:
                            mess = binascii.a2b_hex(file_chunk)
                        except Exception as msg:
                            proc.log(' >> File chunk conversion from hex string to binary failed, data sending canceled\n')
                            PrintException()
                            break
                        FS_sent_size += send_by_size
                        proc.log(' >> Sending packet: %02u, packet size: %u, total sent: %u\n' %
                                 (packet_no, len(file_chunk), FS_sent_size))
                        proc.send()
                    else:
                        file_chunk = data[FS_sent_size:]
                        try:
                            mess = binascii.a2b_hex(file_chunk)
                        except Exception as msg:
                            proc.log(' >> File chunk conversion from hex string to binary failed, data sending canceled\n')
                            PrintException()
                            break
                        FS_sent_size = file_size
                        proc.log(' >> Sending packet: %02u, packet size: %u, total sent: %u\n' %
                                 (packet_no, len(file_chunk), FS_sent_size))
                        proc.send()
                    time.sleep(0.3)  # 300 ms delay
                    packet_no += 1
                # ----------------------------------------
            proc.log(' >> TCP CONFIG sending over\n')
        except Exception as msg:
            proc.log(' >> TCP CONFIG sending exception: %s' % str(msg))
            PrintException()

    # ==============================
    def process_xim(self):
        global FS_filename
        out_fw_ver = 0
        out_device_id = 0
        out_client_id = 0
        try:
            file_path = os.getcwd() + '\\' + FS_filename
            file_check = os.path.exists(file_path)
            proc.log(' >> file path: %s, result: %s' % (file_path, file_check))
            if file_check == False:
                proc.log(' >> Filename %s is not present in the folder! File sending canceled' % FS_filename)
            else:
                f = open(FS_filename, 'rb')
                data = f.read()
                f.close()
                fw_ver = data[292:292 + 8].split(b'.')
                device_id = data[284:284 + 4]
                client_id = data[316:316 + 4]

                # print(type(fw_ver), type(out_device_id), type(out_client_id))
                # print(fw_ver, out_device_id, out_client_id)
                if fw_ver[0].isdigit() == True and fw_ver[1].isdigit() == True and fw_ver[2].isdigit() == True:
                    out_fw_ver = struct.pack(
                        'B', int(fw_ver[0])) + struct.pack('B', int(fw_ver[1])) + struct.pack('B', int(fw_ver[2])) + struct.pack('B', 0)
                    # proc.log(' >> valid fw ver formed')
                else:
                    out_fw_ver = struct.pack('B', 0) + struct.pack('B', 0) + struct.pack('B', 0) + struct.pack('B', 0)
                    # proc.log(' >> invalid fw ver formed')
                # print(type(out_fw_ver), out_fw_ver)
                # print('out fw ver: %X / %s' % (struct.unpack('!I', out_fw_ver), out_fw_ver))

                if device_id.isdigit() == True:
                    out_device_id = struct.pack('!I', int(device_id))
                    # proc.log(' >> dev id valid')
                else:
                    out_device_id = struct.pack('!', 0)
                    # proc.log(' >> dev id invalid')
                # print(type(out_device_id), out_device_id)

                out_client_id = struct.unpack('I', client_id)[0]
                out_client_id = struct.pack('!I', int(out_client_id))
                # print(type(out_client_id), out_client_id, str(out_client_id))

                # print(type(out_fw_ver), binascii.hexlify(out_fw_ver))
                # print(type(out_device_id), binascii.hexlify(out_device_id))
                # print(type(out_client_id), binascii.hexlify(out_client_id))
                proc.log(' >> captured data; fw ver: %s, device id: %s, client id: %s\r\n' %
                         (binascii.hexlify(out_fw_ver), binascii.hexlify(out_device_id), binascii.hexlify(out_client_id)))
            return out_fw_ver, out_device_id, out_client_id
        except Exception as msg:
            proc.log(' >> %s xim file process exception: %s' % (FS_filename, str(msg)))
            PrintException()
            out_fw_ver = struct.pack('B', 0) + struct.pack('B', 0) + struct.pack('B', 0) + struct.pack('B', 0)
            out_device_id = struct.pack('!', 0)
            out_client_id = struct.pack('!', 0)
            return out_fw_ver, out_device_id, out_client_id

    # ==============================
    def process_fm640_xim(self):
        global FS_filename
        out_fw_ver = 0
        out_device_id = 0
        out_client_id = 0
        fw_ver = []
        device_id = 0

        try:
            file_path = os.getcwd() + '\\' + FS_filename
            file_check = os.path.exists(file_path)
            proc.log(' >> file path: %s, result: %s' % (file_path, file_check))
            if file_check == False:
                proc.log(' >> Filename %s is not present in the folder! File sending canceled' % FS_filename)
            else:

                if FS_filename.startswith('FMX64'):
                    device_id = 2
                elif FS_filename.startswith('FMX641'):
                    device_id = 5
                elif FS_filename.startswith('FMX65'):
                    device_id = 5
                values = FS_filename.replace('_', '.').split('.')

                fw_ver.append(values[2])
                fw_ver.append(values[3])
                fw_ver.append(values[4])
                fw_ver.append(values[6])

                pos = FS_filename.find("ID")
                if pos != -1:
                    out_client_id = int(FS_filename[pos+2:].split('.')[0])

                out_fw_ver = struct.pack('B', int(fw_ver[0])) + struct.pack('B', int(fw_ver[1])
                                                                            ) + struct.pack('B', int(fw_ver[2])) + struct.pack('B', 0)
                out_client_id = struct.pack('!I', out_client_id)
                out_device_id = struct.pack('!I', device_id)
        except Exception as msg:
            PrintException()
            out_fw_ver = struct.pack('B', 0) + struct.pack('B', 0) + struct.pack('B', 0) + struct.pack('B', 0)
            out_device_id = struct.pack('!', 0)
            out_client_id = struct.pack('!', 0)
        return out_fw_ver, out_device_id, out_client_id
    # ==============================

    def send_file(self, target_file, chunk_size):
        global crc, mess
        global FS_support, FS_inv_crc_packet, FS_init_pos, FS_sent_packets, FS_sent_size, FS_recalc_done, FS_abort
        global FS_sending
        crc = 0
        FS_sending = True
        sending_errors = 0
        RESEND_ATTEMPTS = 20
        ERRORS_BEFORE_CANCEL = 30
        # ------------------------------------
        try:
            file_path = os.getcwd() + '\\' + FS_filename
            file_check = os.path.exists(file_path)
            proc.log(' >> file path: %s, result: %s' % (file_path, file_check))
            if file_check == False:
                proc.log(' >> Filename %s is not present in the folder! File sending canceled' % target_file)
            else:
                file_size = os.path.getsize(target_file)
                proc.log(' >> %s file uploading, file size: %u, from file position: %u\n' %
                         (target_file, file_size, FS_init_pos))
                f = open(target_file, 'rb')
                # ------------------------------------
                data = f.read()
                total_file_size = len(data)
                f.close()
                ongoin_crc = 0
                FS_sent_size = 0
                # ------------------------------------
                if FS_support == 'TM25':
                    small_interval = 0.1
                    big_interval = 1
                    good_packets = 3
                else:
                    small_interval = 0.2
                    big_interval = 3
                    good_packets = 5
                wait_interval = small_interval
                # ------------------------------------
                if FS_init_pos > 0:
                    FS_recalc_done = False
                else:
                    FS_recalc_done = True
                # ------------------------------------
                while FS_sent_size != len(data) and FS_abort == False and proc.connection_status() == 1:
                    # ------------------------------------
                    if sending_errors >= ERRORS_BEFORE_CANCEL:
                        proc.log(' >> %u sending errors -> abort procedure' % sending_errors)
                        FS_abort = True
                        break
                    if FS_recalc_done == False:
                        if FS_sent_size + chunk_size <= FS_init_pos:
                            file_chunk = data[FS_sent_size:FS_sent_size + chunk_size]
                            print("chunk:{0}".format(type(file_chunk)))
                            ongoin_crc = crc16(file_chunk, len(file_chunk), 1)
                            # proc.log(' >> recalculating crc for file position: [%u - %u), calculated crc: %04X. data not sent' % (FS_sent_size, FS_sent_size+chunk_size, ongoin_crc))
                            FS_sent_size += chunk_size
                            if FS_sent_size == FS_init_pos:
                                proc.log(' >> CRC recalculation done, crc: %04X' % ongoin_crc)
                                FS_recalc_done = True
                                # ------------------------------------
                                time.sleep(1)
                                wait_interval = big_interval
                                good_packets = 0
                                time.sleep(2)
                                # ===============================================
                                # try:
                                #    conn.recv(5120)
                                #    # skip received data (if FM spams)
                                # except Exception as msg:
                                #    PrintException()
                                #    pass
                                # ===============================================
                                # ------------------------------------
                            else:
                                continue
                        else:
                            proc.log(' >> invalid file position provided: %u! abort procedure' % FS_init_pos)
                            proc.close_socket()
                            return
                    else:
                        if FS_sent_size + chunk_size <= len(data):
                            file_chunk = data[FS_sent_size:FS_sent_size + chunk_size]
                            ongoin_crc = crc16(file_chunk, len(file_chunk), 1)
                            proc.log(' >> [%03u] calculating crc for file position: [%u - %u), calculated crc: %04X. Sending data %u B, %03u %%' % (FS_sent_packets,
                                     FS_sent_size, FS_sent_size + len(file_chunk), ongoin_crc, len(file_chunk), float((FS_sent_size + len(file_chunk)) * 100 / total_file_size)))
                            if FS_support == 'TM25' or FS_support == 'FM6X':
                                mess = struct.pack('!H', 0x0004) + struct.pack('!H', len(file_chunk) + 2) + file_chunk
                            else:
                                mess = file_chunk
                            if FS_inv_crc_packet >= 0:
                                if FS_sent_packets == FS_inv_crc_packet:
                                    proc.log(' >> Sending invalid CRC, according to configuration!')
                                    mess += struct.pack('H', 43690)
                                else:
                                    mess += struct.pack('H', ongoin_crc)
                            else:
                                mess += struct.pack('H', ongoin_crc)
                            FS_sent_size += chunk_size
                            # ------------------------------------
                            if good_packets < 5:
                                good_packets += 1
                                wait_interval = big_interval
                                proc.log(' >> Wait interval = %u, good packets: %u' % (wait_interval, good_packets))
                            else:
                                if wait_interval != small_interval:
                                    wait_interval = small_interval
                                    proc.log(' >> 5 good packets received, setting wait interval to %.1f' % wait_interval)
                            # ------------------------------------
                            data_sent = False
                            while data_sent == False and sending_errors < RESEND_ATTEMPTS:
                                if proc.send() == 1:
                                    data_sent = True
                                    sending_errors = 0
                                else:
                                    sending_errors += 1
                                    proc.log(
                                        ' >> Error. Failed to send packet, wait 1s and resend. Error: %u/%u' %
                                        (sending_errors, RESEND_ATTEMPTS))
                                    time.sleep(1)

                            if data_sent == False:
                                sending_errors += 1
                                proc.log(' >> Error. Failed to send packet after all retries')
                                if proc.check_for_sync_request(FS_support, 1) == 0:
                                    FS_init_pos = FS_sent_size - chunk_size
                                    FS_sent_size = 0
                                    FS_recalc_done = False
                                    crc = 0
                                    proc.log(
                                        ' >> SYNC request packet not detected after sending error. Attempt file resending from: %u' % FS_init_pos)
                                    continue
                            # ===================================================
                            # if proc.send() == -1:
                            #    sending_errors += 1
                            #    proc.log(' >> Error. Failed to send packet')
                            #    if proc.check_for_sync_request(FS_support, 2) == 0:
                            #        FS_init_pos = FS_sent_size - chunk_size
                            #        FS_sent_size = 0
                            #        FS_recalc_done = False
                            #        crc = 0
                            #        proc.log(' >> SYNC request packet not detected after sending error. Attempt file resending from: %u' % FS_init_pos)
                            #        time.sleep(2)
                            # ===================================================

                            FS_sent_packets += 1
                            # ------------------------------------
                        else:
                            file_chunk = data[FS_sent_size:]
                            ongoin_crc = crc16(file_chunk, len(file_chunk), 1)
                            proc.log(' >> [%03u] calculating crc for file position: [%u - %u), calculated crc: %04X. Sending data %u B, %03u %%' % (FS_sent_packets,
                                     FS_sent_size, FS_sent_size + len(file_chunk), ongoin_crc, len(file_chunk), float((FS_sent_size + len(file_chunk)) * 100 / total_file_size)))
                            if FS_support == 'TM25' or FS_support == 'FM6X':
                                mess = struct.pack('!H', 0x0004) + struct.pack('!H', len(file_chunk) + 2) + file_chunk
                            else:
                                mess = file_chunk
                            if FS_inv_crc_packet >= 0:
                                if FS_sent_packets == FS_inv_crc_packet:
                                    proc.log(' >> Sending invalid CRC, according to configuration!')
                                    mess += struct.pack('H', 43690)
                                else:
                                    mess += struct.pack('H', ongoin_crc)
                            else:
                                mess += struct.pack('H', ongoin_crc)
                            FS_sent_size = len(data)
                            # ------------------------------------
                            data_sent = False
                            while data_sent == False and sending_errors < RESEND_ATTEMPTS:
                                if proc.send() == 1:
                                    data_sent = True
                                    sending_errors = 0
                                else:
                                    sending_errors += 1
                                    proc.log(
                                        ' >> Error. Failed to send packet, wait 1s and resend. Error: %u/%u' %
                                        (sending_errors, RESEND_ATTEMPTS))
                                    time.sleep(1)

                            if data_sent == False:
                                sending_errors += 1
                                proc.log(' >> Error. Failed to send packet after all retries')
                                if proc.check_for_sync_request(FS_support, 3) == 0:
                                    FS_init_pos = FS_sent_size - chunk_size
                                    FS_sent_size = 0
                                    FS_recalc_done = False
                                    crc = 0
                                    proc.log(
                                        ' >> SYNC request packet not detected after sending error. Attempt file resending from: %u' % FS_init_pos)
                                    continue
                            # ===================================================
                            # if proc.send() == -1:
                            #    sending_errors += 1
                            #    proc.log(' >> Error. Failed to send packet')
                            #    if proc.check_for_sync_request(FS_support, 4) == 0:
                            #        FS_init_pos = FS_sent_size - chunk_size
                            #        FS_sent_size = 0
                            #        FS_recalc_done = False
                            #        crc = 0
                            #        proc.log(' >> SYNC request packet not detected after sending error. Attempt file resending from: %u' % FS_init_pos)
                            #        time.sleep(2)
                            # ===================================================

                            FS_sent_packets += 1
                    # ----------------------------------------
                    proc.check_for_sync_request(FS_support, 5)
                    # resending from 0 doesnt work somehow!
                    # ---------------------------------------
                    if (FS_support != 'TM25' and FS_support != 'FM6X') or good_packets < 5:
                        time.sleep(wait_interval)
                    # proc.log(' >> Sleeping')
                # ------------------------------------
                if FS_abort == False:
                    proc.log(' >> %s file sending complete' % target_file)
                elif proc.connection_status() == 0:
                    proc.log(' >> %s file sending aborted, connection lost' % target_file)
                else:
                    proc.log(' >> %s file sending aborted' % target_file)
                    proc.close_socket()
                FS_sending = False
                FS_abort = False
        except Exception as msg:
            proc.log(' >> %s file sending exception: %s' % (target_file, str(msg)))
            PrintException()
            FS_sending = False
            FS_abort = False
            proc.close_socket()

    # ==============================
    def send_fake_fota(self):
        global mess, FS_packet_delay, FS_packet_cnt
        sent_size = 0
        packets_sent = 0
        done = False
        data_packet = ''
        for i in range(0, 256):
            data_packet += struct.pack('B', i)
        mess = data_packet + data_packet
        proc.log(' >> willbe  sending %u bytes packet: %s' % (len(mess), binascii.hexlify(mess)))
        while done != True:
            result = proc.send()
            while result == -1:
                proc.log(' >> sending failed, wait before retry')
                # proc.close_socket()
                # break
                time.sleep(0.5)
                result = proc.send()
            sent_size += 512
            packets_sent += 1
            if packets_sent >= FS_packet_cnt and FS_packet_cnt != 0:
                proc.log(' >> packet cnt reached: %u, further sending canceled' % FS_packet_cnt)
                break
            time.sleep(FS_packet_delay)

    # ==============================
    def check_for_sync_request(self, support, caller):
        global FS_support, FS_init_pos, FS_sent_size, FS_recalc_done, crc, mess
        RetVal = 0
        try:
            fm_data = conn.recv(5120)
        except Exception as msg:
            return RetVal
        proc.log(' >> Received data packet: %s' % binascii.hexlify(fm_data))
        proc.log(' >> Received data: %s, len: %u' % (fm_data.strip(b'\r\n'), len(fm_data)))

        data_stat.received_bytes(len(fm_data))
        try:
            if support == 'GGG':
                if fm_data.find(b'retry') != -1:
                    poz = fm_data.find(b',')
                    split_packet = fm_data.strip(b'\r\n').split(b',', 2)
                    if poz != -1:  # found it
                        if split_packet[1].isdigit() == True:
                            proc.log(' >> FM requested to retry sending from certain position: %u, caller: %u\n' %
                                     (int(split_packet[1]), caller))
                            FS_init_pos = int(split_packet[1])
                            FS_sent_size = 0
                            FS_recalc_done = False
                            crc = 0
                            mess = 'SYNC'
                            if proc.send() == -1:
                                proc.log(' >> Error. Failed sync packet sending')
                            else:
                                proc.log(' >> Sending SYNC packet OK')
                                time.sleep(2)
                                RetVal = 1
                        else:
                            proc.log(
                                ' >> FM requested to retry sending, but server could not parse file position. Not a digit: %s' % split_packet[1])
                            proc.close_socket()
                    else:
                        proc.log(
                            ' >> FM requested to retry sending, but server could not parse file position. No file position provided.')
                        proc.close_socket()
                else:
                    proc.log(' >> FM packet: %s, but no retry found!' % fm_data.strip(b'\r\n'))
            elif support == 'TM25' or support == 'FM6X':
                if len(fm_data) == 8:
                    cmd_id = struct.unpack('!H', fm_data[0:2])[0]
                    data_len = struct.unpack('!H', fm_data[2:4])[0]
                    offset = struct.unpack('!I', fm_data[4:8])[0]
                    if cmd_id == 0x002 and data_len == 0x004:
                        proc.log(
                            ' >> FM requested to resume sending from certain position: %u, caller: %u\n' %
                            (offset, caller))
                        FS_init_pos = offset
                        FS_sent_size = 0
                        FS_recalc_done = False
                        crc = 0
                        mess = struct.pack('!H', 3) + struct.pack('!H', 4) + struct.pack('!I', offset)
                        if proc.send() == -1:
                            proc.log(' >> Error. Failed resume packet sending')
                        else:
                            proc.log(' >> Sending resume packet OK')
                            time.sleep(2)
                            RetVal = 1
                    else:
                        proc.log(
                            ' >> FM requested to resume sending, but server could not parse file position. No file position provided.')
                        proc.close_socket()
                else:
                    proc.log(' >> Unexpected packet')
            else:
                proc.log(' >> undefined FM_support')
        except Exception as msg:
            proc.log(' >> Exception in parsing FM reply (expecting SYNC): %s' % str(msg))
            PrintException()
        return RetVal

    # ==============================
    def send(self):
        global mess
        global conn
        try:
            if mess != None:
                if TCP == 1:
                    conn.send(mess)  # veikia !
                else:
                    self.s.sendto(mess, addr)  # udp sending nzn ar veikia
                proc.log(' >> Packet sent (%u B): %s\n' % (len(mess), binascii.hexlify(mess)))
            # reik padaryt kad atsakymo nesiustu po to kai nusiuncia ale komanda
            # kaip nors su flagais
            # data = conn.recv(1024)
            # print('received answer:', data.decode('utf-8'))
            return 1
        except socket.error or TypeError as msg:
            proc.log(' >> proc.send couldnt send the packet: %s' % msg)
            return -1

    def effortech_test(self):
        # Table of commands and expected CRCs (example CRCs, replace with your own)
        commands = [
            {"cmd": "getstatus", "expected_crc": 0xF05E},
        ]
        results = []
        for entry in commands:
            self.send_cmd(entry["cmd"])
            try:
                # Wait for reply (blocking, adjust timeout as needed)
                reply = conn.recv(1024)
                # Calculate CRC of reply (replace with your CRC function if needed)
                # Example: CRC is last 2 bytes of reply
                if len(reply) >= 2:
                    received_crc = int.from_bytes(reply[-2:], byteorder='big')
                    match = (received_crc == entry["expected_crc"])
                else:
                    received_crc = None
                    match = False
                results.append({
                    "command": entry["cmd"],
                    "expected_crc": entry["expected_crc"],
                    "received_crc": received_crc,
                    "match": match,
                    "reply": reply
                })
                proc.log(f"Command: {entry['cmd']}, Expected CRC: {entry['expected_crc']:04X}, "
                         f"Received CRC: {received_crc if received_crc is not None else 'None'}, Match: {match}")
            except Exception as e:
                proc.log(f"Error receiving reply for command {entry['cmd']}: {e}")
                results.append({
                    "command": entry["cmd"],
                    "expected_crc": entry["expected_crc"],
                    "received_crc": None,
                    "match": False,
                    "reply": None
                })
        # Print table summary
        proc.log("Effortech Test Results:")
        proc.log("Command\t\t\tExpected CRC\tReceived CRC\tMatch")
        for r in results:
            proc.log(f"{r['command']}\t{r['expected_crc']:04X}\t\t{r['received_crc'] if r['received_crc'] is not None else 'None'}\t\t{r['match']}")
    # ==============================
    def send_ggg(self):
        global mess, conn, crc
        crc = 0
        # location = os.getcwd()
        # print('current location: %s' % location)
        try:
            if os.path.exists(os.getcwd() + '\\' + FS_filename) == False:
                proc.log(' >> Filename %s is not present in the folder!' % FS_filename)
            else:
                file_size = os.path.getsize(FS_filename)
                f = open(FS_filename, 'rb')
                file_data = f.read()
                f.close()
                file_crc = crc16(file_data, file_size, 1)
                proc.log(' >> File name: %s, size: %u, CRC16: %04X' % (FS_filename, file_size, file_crc))
                if TCP == 1:
                    mess = '%u,%04x' % (file_size, file_crc)
                    proc.log(' >> Sending: %s\r\n' % mess)
                    conn.send(mess)
                    # ===========================================================
                    # start = 0
                    # crc = 0
                    # while start < file_size:
                    #    proc.log(' >> crc: %04X' % crc16(file_data[start:start+256], 256, 1))
                    #    start += 256
                    # ===========================================================
                else:
                    proc.log(' >> Data sending not created for UDP')
        except Exception as msg:
            proc.log(' >> Exception: %s' % str(msg))
            PrintException()

    # ==============================
    def get_pid(self):
        proc.log(' >> Process ID: %s' % (str(os.getpid())))

    # ==============================
    def close_socket(self):
        global conn
        try:
            conn.close()
            self.disc.set()
            proc.log(' >> Closing socket.\n')
            self.connected = 0
        except Exception as msg:
            proc.log(' >> Failed to close socket: %s' % str(msg))
            PrintException()

    # ==============================
    def set_timeout(self, nr, req):
        global TCP_TIMEOUT
        if req == '?':
            proc.log(' >> TCP timeout is: %d' % TCP_TIMEOUT)
        else:
            TCP_TIMEOUT = nr
            proc.log(' >> Setting new TCP TIMEOUT: %d\n' % nr)

    # ==============================
    def connection_status(self):
        return self.connected

    # ==============================
    def send_gprs_cmd(self, cmd_type, data):
        global mess
        mess = codec12(data, C12, cmd_type)
        target = ''  # 'gprs' if cmd_type == CMD5 elif cmd_type == else 'camera'
        if cmd_type == CMD5:
            target = 'GPRS'
        elif cmd_type == GPRS_CMD_SERVER_IXTP_TO_FM:
            target = 'IXTP'
        elif cmd_type == GPRS_CMD_CAMERA_TO_FM:
            target = 'camera'
        else:
            target = 'unknown'
        sender.log(' >> Will try to send %s cmd: %s' % (target, data))  # mess - encoded message already
        proc.send()

    # ==============================
    def send_cmd(self, message):
        global mess
        mess = codec12(message, C12, CMD_TYPE)
        proc.log(' >> Will try to send cmd: %s' % message)  # mess - encoded message already
        proc.send()
    # ==============================


# Command help dictionary
COMMAND_HELP = {
    "q": "Quit the program",
    "?": "Show this help message",
    "#": "Send a string to server using codec12",
    "@": "Send multiple commands in one message (format: @cmd1@cmd2@cmd3)",
    "-": "Send raw hex data to server (format: -48656C6C6F)",
    "+": "Send raw text to server (format: +Hello)",
    ".": "Send text to server using codec12 (strips newlines)",
    "*": "Send command via codec14 (format: *NOD IMEI COMMAND)",
    ":": "Send text to server using codec12 (strips newlines)",
    "SET OUT3=": "Send OUT3 command",
    "MF": "Send MF command",
    "stop": "Stop the server",
    "run": "Start the server",
    "pid": "Show process ID of main program",
    "crc": "Calculate CRC for hex data (format: crc HEXDATA)",
    "close": "Forcibly close socket from server side",
    "set": "Set TCP timeout (setX where X is seconds, or set? to see current value)",
    "r": "Send random GPRS commands",
    "block:": "Block replying to TCP NOD commands (1=block, 0=unblock, ?=status)",
    "cmdtype:": "Get/Set command type (cmdtype:? or cmdtype:X where X is number)",
    "doubleanswer": "Toggle double answer mode for record receipt",
    "acktocodec12": "Toggle sending ACK packets to Codec 12",
    "bad": "Configure bad responses (bad? to check status, badX to set value)",
    "ggg": "Send GGG command",
    "test": "Test getting GPRS value from config file",
    "fgprs": "Send GPRS command",
    "cpu": "Send CPU reset command",
    "tcpconfig": "Send TCP configuration",
    "par": "Process XIM",
    "tm25": "Check file system paths",
    "nod?": "Check NOD plus GPRS status",
    "b": "Send binary data converted from hex string"
}

def display_welcome_message():
    """Display welcome message and basic command information."""
    print("\n" + "="*80)
    print("TELTONIKA  TCP/UDP SERVER INTERFACE".center(80))
    print("="*80)
    print("This application allows you to manage TCP/UDP connections and send commands to Teltonika devices")
    print("\nType '?' for a list of available commands\n")
    print("-"*80)

def display_help():
    """Display comprehensive help information."""
    print("\nAVAILABLE COMMANDS:")
    print("-"*80)
    
    # Group commands by category
    categories = {
        "Basic Commands": ["q", "?", "stop", "run", "pid"],
        "Send Commands": ["#", "@", "-", "+", ".", "*", ":", "SET OUT3=", "MF", "b", "j", "jraw"],
        "GPRS Commands": ["fgprs", "test", "r", "ggg"],
        "Configuration": ["set", "block:", "cmdtype:", "doubleanswer", "acktocodec12", "bad", "tcpconfig"],
        "System Operations": ["cpu", "crc", "close", "par", "tm25", "nod?"]
    }
    
    for category, cmd_list in categories.items():
        print(f"\n{category}:")
        for cmd in cmd_list:
            if cmd in COMMAND_HELP:
                print(f"  {cmd.ljust(15)} - {COMMAND_HELP[cmd]}")
    
    print("\nExamples:")
    print("  #getinfo        - Send 'getinfo' command using codec12")
    print("  -48656C6C6F     - Send 'Hello' as hex data")
    print("  *1 123456789012345 getver - Send 'getver' command to device with IMEI 123456789012345 using codec14")
    print("  j setdigout 111 - Send '{\"CMD\": \"setdigout 111\"}' JSON command")
    print("  jraw {\"key\":\"value\"} - Send raw JSON data")
    print("-"*80)


# ==================================
if __name__ == '__main__':
    global mess
    # ==============================
    # global user_input
    # global user_requested
    # char_set = string.ascii_uppercase + string.digits
    # print(len(char_set))
    # sys.exit()
    # file = "pietus.txt" # 04-24
    # file = open(file, 'a')

    # for i in range(0,100):
    #    #print(r.randint(1,3))
    #    print(gprs_commands[r.randint(0,2)])
    # for i in range(0,7):
    #    print(tacho_file_type[0x10])
    # sys.exit()
    display_welcome_message()
    proc = starter()
    proc.start()

    if get_int_value_from_file('gprs_sending:') == 1:
        try:
            period = get_int_value_from_file('period:')
            data = get_str_value_from_file('gprs:')
        except Exception as msg:
            print('Exception while parsing gprs configuration: %s' % str(msg))
            PrintException()
            proc.stop()
            sys.exit()

        sender = gprs_sender(GPRS_0C_SENDER, period, data)
        sender.start()
        sender_running = 1
    elif get_int_value_from_file('camera_sending:') == 1:
        try:
            period = get_int_value_from_file('camera_period:')
            data = get_str_value_from_file('camera_data:')
            try:
                temp = binascii.a2b_hex(data)
            except Exception as msg:
                print('failed to convert camera data from hex string to binary format, check configuratio @ values.txt @ camera:data:')
                PrintException()
                proc.stop()
                sys.exit()
        except Exception as msg:
            print('Exception while parsing camera configuration: %s' % str(msg))
            PrintException()
            proc.stop()
            sys.exit()

        sender = gprs_sender(GPRS_0D_SENDER_, period, data)

        sender.start()
        sender_running = 1
    else:
        pass

    if get_int_value_from_file('cpureset_sending:') == 1:
        sender = cpu_reset_sender()
        sender.start()
        sender_running = 1
    else:
        pass

    data_stat = DataStatistics(proc.log)

    allow = 0
    # ==============================
    while True:
        # ==============================
        capt = ''
        try:
            capt = input()
            # print(type(capt), capt)
        except KeyboardInterrupt:
            print('KeyboardInterrupt: Stop server')
            proc.stop()
            data_stat.stop()
            sys.exit(0)
        except Exception as msg:
            print('Input exception: %s' % str(msg))
            PrintException()

        try:
            # CA = capt[0].decode('utf-8')
            CA = capt
            print(CA)
            allow = 1
        except Exception as msg:
            print('Input exception: %s' % str(msg))
            PrintException()
        # ==============================
        if allow == 1 and len(capt) > 0:
            # ==============================
            if capt.startswith('q'):
                print('Quitting program.\n')
                if sender_running == 1:
                    sender.stop()
                proc.stop()
                # file.close()
                sys.exit()
                break
            # ==============================
            elif capt.startswith('?'):
                display_help()

            # ==============================
            # ===================================================================
            # elif capt.startswith('_'):
            #    #number = 4
            #    if len(capt)>=1 and capt[1:2].isdigit():
            #        number = int(capt[1:2])
            #        print('number % d' % number)
            #        if number==0:
            #            mess = codec12(bytes(capt[2:], 'utf-8'), C12, CMD_TYPE)
            #        elif number==1:
            #            mess = codec12(bytes(capt[2:], 'utf-8'), C12, CMD_TYPE)
            #        elif number==2:
            #            mess = codec12(bytes(capt[2:], 'utf-8'), C12, CMD_TYPE)
            #        elif number==3:
            #            mess = codec12(bytes(capt[2:], 'utf-8'), C12, CMD_TYPE)
            #        else:
            #            mess = codec12(bytes(capt[2:], 'utf-8'), C12, CMD_TYPE)
            #        print('[tacho] will try to send: ', capt[2:]) # mess - encoded message already
            #        print(mess)
            #        print(binascii.hexlify(mess))
            #        proc.send()
            # ===================================================================
            # ==============================
            elif capt[0] == '#':
                mess = codec12((capt[1:]), C12, CMD_TYPE)
                # print('will try to send: ', capt) # mess - encoded message already
                proc.log(' >> will try to send: %s\n' % capt)
                # file.write(gtime() + ' >> will try to send: %s\n' % str(capt)); file.flush()
                proc.send()
            # ==============================
            elif capt[0] == '@':
                cmd_list = capt.split('@')[1:]
                mess = b"".join(codec12((cmd_str), C12, CMD_TYPE) for cmd_str in cmd_list)
                proc.log(' >> will try to send: %s\n' % ', '.join(cmd_list))
                proc.send()
            # ==============================
            elif capt[0] == '-':  # siust hexu ka nori i FM'a
                try:
                    combo = binascii.a2b_hex(capt[1:])
                    mess = combo
                    # mess = codec12(combo , C12, CMD_TYPE)
                    try:
                        print('will try to send: %s' % capt[1:])  # mess - encoded message already
                        proc.send()
                    except Exception as msg:
                        proc.log(' >> Failed to send: %s' % str(msg))
                        PrintException()
                except Exception as msg:
                    proc.log(' >> Failed to convert to hex: %s' % str(msg))
                    PrintException()
            elif capt[0] == '+':  # siust raw ka nori i FM'a
                try:
                    mess = capt[1:]
                    try:
                        print('will try to send: %s' % mess)  # mess - encoded message already
                        proc.send()
                    except Exception as msg:
                        proc.log(' >> Failed to send: %s' % str(msg))
                        PrintException()
                except Exception as msg:
                    proc.log(' >> Failed to convert to hex: %s' % str(msg))
                    PrintException()
            # ==============================
            elif capt[0] == '.':
                filtered = capt[1:].strip('\r\n')
                mess = codec12(filtered, C12, CMD_TYPE)
                print('will try to send: ', filtered)  # mess - encoded message already
                proc.send()
            # ==============================
            elif capt[0] == '*':
                filtered = capt[1:].strip('\r\n')
                # komandos formatas: NOD IMEI GPRS_CMD
                # *1 123456789012345 getver
                data_split = filtered.split(' ')
                nod = data_split[0]
                imei = data_split[1]
                command = " ".join(data_split[2:])

                print('nod: %s, imei: %s, C14 gprs cmd: %s' % (nod, imei, command))

                imei_bcd = encode_imei(imei)  # Convert IMEI to BCD
                final_data = imei_bcd + command.encode()  # Construct final data
                mess = codec14(final_data, int(data_split[0]), C14, CMD_TYPE)
                print('will try to send packet: %s Command: %s' % (binascii.hexlify(mess), command))
                proc.send()
            # ==============================
            elif capt[0] == ':':
                mess = codec12((capt[1:].strip('\r\n')), C12, CMD_TYPE)
                print('will try to send: ', capt[1:].strip('\r\n'))  # mess - encoded message already
                # file.write(gtime() + ' >> will try to send: %s\n' % str(capt)); file.flush()
                proc.send()
            # ==============================
            elif capt.startswith('SET OUT3=') or capt.startswith('MF'):
                mess = codec12((capt[0:] + '\r\n'), C12, CMD_TYPE)
                print('will try to send: ', capt)  # mess - encoded message already
                # file.write(gtime() + ' >> will try to send: %s\n' % str(capt)); file.flush()
                proc.send()
            # ==============================
            elif capt.startswith('stop'):
                proc.stop()
            # ==============================
            elif capt.startswith('run'):
                try:
                    proc.start()
                except Exception as msg:
                    print(str(msg))
                    PrintException()
            # ==============================
            elif capt.startswith('pid'):
                print('Process ID: %s' % str(os.getpid()))
            # ==============================
            elif capt.startswith('crc'):  # just calculating this data crc
                # test = '0c0110000003ec06041f3e3e3e3e3f3e3f3e3e3e3e3e3e50035e303e3e3e3e3e3e3e3f3e3e3e3f3e3e3e3e3e3e3e3e3e3f3e3e3e3e3f3e3e3e3e3f3e3f3e3e3e3e3e3e3f3e3f3e3f3e3e3e3e3f3e3f3e3e3f3e3e3e3e3e50035e6c3e3e3e3e3e3e3e3e3e3e3f3e3e3e3e3f3e3e3e3e3e3e3f3e3f3e3e3e3e3e3e3f3e3e3e3e3f3e3f3e3f3e3e3e3e3f3e3e3e3e3f3e3e3f3e3e3e3e3e3e50035ea83e3e3f3e3e3e3e3e3e3e3e3e3f3e3f3e3e3e3e3f3e3f3e3e3e3e3e3e3e3e3e3e3e3e3e3e3e3e3f3e3e3f3e3e3e3e3f3e3e3e3e3e3e3f3e3f3e3f3e3e50035ee43f3e3f3e3e3e3e3e3e3e3e3e3e3f3e3e3f3e3f3e3e3e3e3f3e3e3e3e3e3e3f3e3e3e3e3f3e3e3e3e3f3e3f3e3e3e3e3e3e3e3e3e3e3e3e3e3f3e3e3e50035f203e3f3e3e3e3e3e3e3e3e3e3e3e3e3e3e3e3e3e3e3e3e3f3e3e3e3e3e3e3e3e3e3f3e3e3e3e3e3e3e3e3e3e3f3e3e3e3e3e3f3e3e3e3e3e3e3e3e3e3e50035f5c3e3e3e3f3e3e3f3e3f3e3f3e3f3e3e3e3e3e3e3e3f3e3e3e3e3e3e3e3e3e3e3e3f3e3e3e3e3e3e3e3e3e3e3e3e3e3e3e3f3e3e3f3e3f3e3e3e3e3e3e50035f983f3e3e3e3e3e3e3e3e3f3e3e3e3f3e3e3f3e3e3f3e3e3e3e3e3e3e3e3e3e3e3f3e3e3e3e3e3e3f3e3e3e3e3f3e3e3e3e3e3e3e3e3e3e3e3e3e3e3e3e50035fd43e3f3e3e3e3e3e3e3e3e3e3f3e3e3f3e3e3e3f3e3e3f3e3e3e3e3f3e3f3f3f3e3e3e3e3e3e3e3e3f3e3e3f3e3f3e3f3e3e3e3e3e3e3e3f3e3e3e3e3e500360103e3e3e3e3e3e3f3e3f3e3e3e3e3e3e3e3e3e3e3e3f3e3e3e3e3e3e3e3e3e3e3e3e3e3e3f3e3e3e3e3e3e3e3e3e3e3e3e3e3f3e3e3e3e3e3f3e3e3e3e5003604c3e3e3e3e3e3e3f3e3e3e3e3e3e3f3e3f3f3e3e3e3e3e3e3e3e3e3e3e3f3e3f3e3e3e3f3e3e3e3e3e3e3e3f3e3f3e3e3e3e3e3e3e3e3e3e3e3e3e3e3e500360883e3e3e3e3e3e3e3e3e3e3f3e3e3e3e3e3e3f3e3f3e3e3e3e3f3e3e3e3e3e3e3e3e3e3e3e3e3e3e3e3f3e3e3f3e3e3e3e3e3e3e3e3e3e3f3e3e3f3e3f500360c43e3e3e3e3f3e3e3e3e3f3e3f3e3e3e3e3e3e3e3e3e3e3f3e3e3e3e3e3e3e3e3e3e3e3e3e3e3e3e3e3e3f3e3e3f3e3e3e3e3f3e3e3e3e3e3e3e3e3f3e500361003f3e3f3f3e3e3e3e3e3f3e3e3e3e3f3e3e3e3e3f3e3f3e3e3e3e3f3e3e3e3f3e3e3e3e3e3f3e3e3e3e3e3e3e3e3f3e3f3e3f3e3e3f3e3f3e3e3e3e3e5003613c3e3f3e3e3e3e3f3e3e3e3e3e3e3f3e3e3e3e3e3e3e3e3e3e3e3e3e3f3e3e3f3e3f3e3f3e3e3e3e3e3e3e3e3e3e3f3e3e3f3e3f3e3e3f3e3e3e3f3e3e500361783e3e3e3e3e3e3e3e3e3e3e3e3e3e3e3e3e3e3e3e3e3f0a3e3e3e3e3e3e3e3f3e3e3f3e3f3e3e3e3e3f3e3e3e3e3f3e3e3e3f3e3f3e3e3f3e3e3e3e3e500361b43e3f3e3e3e3e3e3e3e3e3e3f3e3f3e3e3f3e3f3e3f3e3e3e01'
                print('Try to calc crc for: %s' % binascii.hexlify(capt[3:]))
                # combo = test.decode('hex')
                try:
                    combo = binascii.a2b_hex(capt[3:])
                except Exception as msg:
                    proc.log(' >> Failed to convert to hex: %s' % str(msg))
                    PrintException()
                    break

                print('Len: %d Bytes' % len(combo))
                crc = crc16(combo, len(combo), 0)
                # print(type(crc))
                # crc = struct.pack('!H', crc)
                print('Calculated crc: %08X == %d' % (crc, crc))
            # ====================================
            elif capt.startswith('close'):  # forcibly close socket
                proc.close_socket()
            # ====================================
            elif capt.startswith('set'):  # set tcp timeout
                if capt[3:].isdigit() == True:
                    proc.set_timeout(int(capt[3:]), 0)
                elif capt[3:].startswith('?'):
                    proc.set_timeout(0, capt[3:])
            # ====================================
            elif capt.startswith('reject:'): # reject replying to tcp nod commands
                if len(capt) == 8:
                    if capt[7] == '1':
                        reject_nod_reply = 1
                        print('reject enabled')
                    elif capt[7] == '0':
                        reject_nod_reply = 0
                        print('reject disabled')
                    elif capt[7] == '?':
                        print('reject reply: %d' % reject_nod_reply)
                    else:
                        print('unknown reject value, must be [0,1,?]')
            elif capt.startswith('r'):
                mess = ''
                cmd_no = r.randint(1, 3)
                print('Will send %d gprs commands' % cmd_no)
                to_send = ''
                for i in range(0, cmd_no):
                    to_send += gprs_commands[r.randint(0, 2)]
                    # in case of 3.2 just would need to encode this to_send in utf8
                    mess += codec12(to_send, C12, CMD_TYPE)
                # ================================
                # print(binascii.hexlify(mess))
                print(to_send)
                proc.send()
            # ====================================
            elif capt.startswith('block:'):  # block replying to tcp nod commands
                if len(capt) == 7:
                    if capt[6] == '1':
                        block_nod_reply = 1
                        print('block enabled')
                    elif capt[6] == '0':
                        block_nod_reply = 0
                        print('block disabled')
                    elif capt[6] == '?':
                        print('block reply: %d' % block_nod_reply)
                    else:
                        print('unknown block value, must be [0,1,?]')
            # ====================================

            elif capt.startswith('cmdtype:'):
                if capt[8] == '?':
                    print('current cmd type is %02u / 0x%02X' % (CMD_TYPE, CMD_TYPE))
                elif capt[8:].strip('\r\n').isdigit() == True:
                    try:
                        val = int(capt[8:].strip('\r\n'))
                        print('CMD TYPE set to: 0x%02X' % val)
                        CMD_TYPE = val
                    except Exception as msg:
                        print('cmdtype:X error: %s' % str(msg))
                        PrintException()
                else:
                    print('invalid input for cmdtype:X cmd')
            # ====================================
            elif capt.startswith('doubleanswer'):
                doubleanswer = not doubleanswer
                print('Will send double answer on records receive: %d' % doubleanswer)
            # ====================================
            elif capt.startswith('acktocodec12'):
                ackTo_C12 = not ackTo_C12
                print('Will send ack packet to Codec.12: %d' % ackTo_C12)
            # ====================================
            elif capt.startswith('bad'):
                if capt[3:].startswith('?'):
                    if time_for_bad > 0:
                        print('bad responses enabled: %d' % time_for_bad)
                    else:
                        print('bad responses disabled: %d' % time_for_bad)
                elif capt[3:].strip('\r\n').isdigit() == True:
                    try:
                        val = int(capt[3:].strip('\r\n'))
                        time_for_bad = val
                        print('time_for_bad = %d' % val)
                    except Exception as msg:
                        print('bad setting err: %s' % str(msg))
                        PrintException()
            # ====================================
            elif capt.startswith('ggg'):
                proc.send_ggg()
            # ====================================
            elif capt.startswith('test'):
                re = get_str_value_from_file('gprs:')
                print('val to be sent to server: %s' % re)
            # ====================================
            elif capt.startswith('fgprs'):
                proc.send_gprs_cmd(CMD_TYPE, 'asd')
            # ====================================
            elif capt.startswith('cpu'):
                proc.send_cmd('cpureset')
            # ====================================
            elif capt.startswith('tcpconfig'):
                proc.send_tcp_config()
            # ====================================
            elif capt.startswith('par'):
                proc.process_xim()
            # ====================================
            elif capt.startswith('tm25'):
                print(FS_filename)
                print(os.getcwd())
                print(os.getcwd() + '\\' + FS_filename)
                print('path: %s' % os.path.exists(os.getcwd() + '\\' + FS_filename))
            # ====================================
            elif capt.startswith('nod?'):
                print('nod_plus_gprs: %s ' % nod_plus_gprs)
            # ====================================
            elif capt.startswith('b'):

                filtered = capt[1:].strip('\r\n')
                print("filtered" + str(type(filtered)))
                filtered_hex = ''.join([chr(int(''.join(c), 16)) for c in zip(filtered[0::2], filtered[1::2])])
                print("filtered_hex" + str(type(filtered_hex)))
                mess = codec12(filtered_hex, C12, CMD_TYPE)
                print('will try to send: ', filtered_hex)  # mess - encoded message already
                proc.send()
            # Send JSON command (standard format)
            elif capt[0] == 'j':
                if len(capt) > 1:
                    command = capt[1:].strip()
                    json_data = {"CMD": command}
                    json_str = json.dumps(json_data)
                    mess = json_str.encode('utf-8')  # Convert JSON string to bytes
                    print(f'Sending JSON command: {json_str}')
                    proc.send()
                else:
                    print("Error: No command specified. Format should be 'j command'")
            # Send raw JSON data
            elif capt.startswith('jraw'):
                if len(capt) > 4:
                    json_str = capt[4:].strip()
                    try:
                        # Validate JSON format
                        json.loads(json_str)
                        mess = json_str.encode('utf-8')  # Convert JSON string to bytes
                        print(f'Sending raw JSON: {json_str}')
                        proc.send()
                    except json.JSONDecodeError as e:
                        print(f'Invalid JSON format: {e}')
                else:
                    print("Error: No JSON data specified. Format should be 'jraw {\"key\":\"value\"}'")
            # ====================================
            elif capt.startswith('effortech-test'):
                print('effortech-test')
                proc.effortech_test()
            allow = 0  # important
    # ==============================
    proc.stop()
    sys.exit()
