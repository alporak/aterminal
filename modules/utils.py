import re
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import folium
from folium.plugins import TimestampedGeoJson
from datetime import datetime
from . import gps_codes

# === Modem / Network State Lookups ===
CREG_STATES = {
    0: 'Not Registered', 1: 'Home', 2: 'Searching',
    3: 'Denied', 4: 'Unknown', 5: 'Roaming'
}
NETWORK_ACT = {
    0: 'GSM', 2: '3G', 3: 'GSM/EGPRS', 4: 'HSDPA',
    5: 'HSUPA', 6: 'HSPA+', 7: 'LTE', 8: 'Cat-M1', 9: 'Cat-NB1'
}
REC_SEND_STATES = {
    0: 'Idle', 1: 'Check Recs', 2: 'Check GPRS', 3: 'Check Link',
    4: 'IMEI Handshake', 5: 'Sending', 6: 'Continue', 7: 'Flush',
    8: 'Error/Finish', 9: 'Close GPRS', 10: 'Done', 11: 'GPS Special',
    12: 'Check FIFO', 13: 'WDT', 14: 'Push Config', 15: 'Push Wait', 16: 'MQTT Init'
}
REC_SEND_ACTIVE = {4, 5, 6, 7, 12, 16}

AT_COMMAND_INFO = {
    # Basic / Init
    'ATE0': ('Init', 'Disable Echo'),
    'ATE1': ('Init', 'Enable Echo'),
    'AT': ('Basic', 'Attention'),
    'AT+CEER': ('Status', 'Extended Error Report'),
    'AT+QIGETERROR': ('Status', 'Quectel IP Error'),
    # Identity
    'AT+CGMM': ('Identity', 'Model Identification'),
    'AT+CGMI': ('Identity', 'Manufacturer Identification'),
    'AT+CGSN': ('Identity', 'IMEI Query'),
    'AT+CIMI': ('Identity', 'IMSI Query'),
    'AT+CGMR': ('Identity', 'Firmware Revision'),
    'AT+QGMR': ('Identity', 'Quectel FW Revision'),
    # SIM
    'AT+CPIN': ('SIM', 'SIM PIN Status'),
    'AT+QCCID': ('SIM', 'SIM ICCID (Quectel)'),
    'AT+ICCID': ('SIM', 'SIM ICCID'),
    'AT+QSIMSTAT': ('SIM', 'SIM Status Notifications'),
    'AT+QSIMDET': ('SIM', 'SIM Detection Config'),
    'AT+QINISTAT': ('SIM', 'Init Status Query'),
    # Signal
    'AT+CSQ': ('Signal', 'Signal Quality (RSSI)'),
    'AT+QCSQ': ('Signal', 'Extended Signal Quality'),
    'AT+CESQ': ('Signal', 'Extended Signal (3GPP)'),
    # Network / Registration
    'AT+CREG': ('Network', 'GSM Registration'),
    'AT+CGREG': ('Network', 'GPRS Registration'),
    'AT+CEREG': ('Network', 'LTE Registration'),
    'AT+COPS': ('Network', 'Operator Selection/Query'),
    'AT+QNWINFO': ('Network', 'Network Info (Tech/Band)'),
    'AT+CPAS': ('Status', 'Phone Activity Status'),
    'AT+CIND': ('Status', 'Indicator Status'),
    # Config
    'AT+CMGF': ('SMS', 'SMS Format (PDU/Text)'),
    'AT+CSCS': ('Config', 'Character Set'),
    'AT+CMEE': ('Config', 'Extended Error Reporting'),
    'AT+CGEREP': ('Config', 'GPRS Event Reporting'),
    'AT+CTZU': ('Config', 'Auto Timezone Update'),
    'AT+CTZR': ('Config', 'Timezone Reporting'),
    'AT+QURCCFG': ('Config', 'URC Port Config'),
    'AT+IFC': ('Config', 'Flow Control'),
    'AT+CLIP': ('Call', 'Calling Line ID'),
    'AT+CNMI': ('SMS', 'New SMS Indication'),
    # Power / Sleep
    'AT+QSCLK': ('Power', 'Sleep Mode Control'),
    'AT+CFUN': ('Power', 'Phone Functionality'),
    'AT+QPOWD': ('Power', 'Power Down Modem'),
    'AT+CBC': ('Power', 'Battery Charge'),
    # GPRS / Socket (Quectel)
    'AT+QICSGP': ('GPRS', 'APN Configuration'),
    'AT+QIACT': ('GPRS', 'Activate PDP Context'),
    'AT+QIDEACT': ('GPRS', 'Deactivate PDP Context'),
    'AT+QIOPEN': ('GPRS', 'Open Socket'),
    'AT+QICLOSE': ('GPRS', 'Close Socket'),
    'AT+QISEND': ('GPRS', 'Send Data'),
    'AT+QIRD': ('GPRS', 'Read Data'),
    'AT+QIDNSGIP': ('GPRS', 'DNS Lookup'),
    'AT+QIDNSCFG': ('GPRS', 'DNS Server Config'),
    'AT+CGATT': ('GPRS', 'GPRS Attach/Detach'),
    'AT+CGDCONT': ('GPRS', 'PDP Context Definition'),
    'AT+QISTATE': ('GPRS', 'Socket State Query'),
    'AT+QPING': ('GPRS', 'Ping'),
    # GPRS / Socket (MeiG / non-Quectel)
    'AT+CIPSTART': ('GPRS', 'Open Socket'),
    'AT+CIPCLOSE': ('GPRS', 'Close Socket'),
    'AT+CIPSEND': ('GPRS', 'Send Data'),
    'AT+CIPSTATUS': ('GPRS', 'Socket Status'),
    'AT+CIPRXGET': ('GPRS', 'Read Data'),
    'AT+CIPSHUT': ('GPRS', 'Close All Connections'),
    # Security
    'AT+QJDCFG': ('Security', 'Jamming Detection Config'),
    'AT+QJDR': ('Security', 'Jamming Detection Enable'),
    # Time
    'AT+QLTS': ('Time', 'Local Timestamp'),
    'AT+CCLK': ('Time', 'Clock'),
    # SMS
    'AT+CMGL': ('SMS', 'List SMS Messages'),
    'AT+CMGS': ('SMS', 'Send SMS'),
    'AT+CMGD': ('SMS', 'Delete SMS'),
    'AT+CMGR': ('SMS', 'Read SMS'),
    # Call
    'AT+CLCC': ('Call', 'List Current Calls'),
    'ATH': ('Call', 'Hang Up'),
    'ATA': ('Call', 'Answer Call'),
    'ATD': ('Call', 'Dial'),
    # Network Config (Quectel)
    'AT+QCFG': ('Config', 'Quectel Configuration'),
    'AT+EGMR': ('Config', 'IMEI Write (Engineer)'),
    'AT+QRFTESTMODEEXIT': ('Config', 'RF Test Mode Exit'),
}

# Identity command base name → device_identity field
_IDENTITY_CMD_MAP = {
    'CIMI': 'imsi', 'CGSN': 'imei', 'CGMM': 'model',
    'CGMI': 'manufacturer', 'QCCID': 'iccid', 'ICCID': 'iccid',
    'CGMR': 'fw_revision', 'QGMR': 'fw_revision',
}

def classify_at_command(cmd_text):
    """Classify an AT command/response and return (category, description)."""
    if not cmd_text:
        return ('Other', '')
    cmd = cmd_text.strip().rstrip('\r\n\x00')
    cmd_upper = cmd.upper()

    # Result codes
    if cmd_upper in ('OK', 'ERROR', '>', 'CONNECT', 'NO CARRIER', 'RING'):
        return ('Result', cmd)
    if 'SEND OK' in cmd_upper:
        return ('Result', 'Send OK')
    if 'SEND FAIL' in cmd_upper:
        return ('Result', 'Send Fail')
    if cmd_upper.startswith('+CME ERROR'):
        return ('Error', 'CME Error')
    if cmd_upper.startswith('+CMS ERROR'):
        return ('Error', 'CMS Error')
    if ',CONNECT OK' in cmd_upper:
        return ('Result', 'Connect OK')
    if ',CLOSED' in cmd_upper or cmd_upper == 'CLOSED':
        return ('Result', 'Socket Closed')

    # URC (unsolicited result codes)
    if cmd_upper.startswith('+CGEV:'):
        return ('URC', 'GPRS Event')
    if cmd_upper.startswith('+QIURC:'):
        return ('URC', 'Socket Event')
    if cmd_upper.startswith('+JAMMED'):
        return ('URC', 'Jamming Detected')
    if cmd_upper.startswith('+OPERATIVE'):
        return ('URC', 'Jamming Cleared')
    if cmd_upper in ('RDY', 'POWERED DOWN', 'NORMAL POWER DOWN'):
        return ('URC', 'Modem Lifecycle')

    # Response prefixes (+XXX: ...)
    if cmd_upper.startswith('+'):
        prefix = cmd.split(':')[0].strip()
        at_cmd = 'AT' + prefix
        if at_cmd.upper() in AT_COMMAND_INFO:
            cat, desc = AT_COMMAND_INFO[at_cmd.upper()]
            return (cat, f'{desc} (Response)')
        return ('Response', prefix)

    # AT commands — exact lookup
    if cmd_upper in AT_COMMAND_INFO:
        return AT_COMMAND_INFO[cmd_upper]
    # Without parameters (before = or ?)
    base_cmd = re.split(r'[=?]', cmd, 1)[0].strip()
    if base_cmd.upper() in AT_COMMAND_INFO:
        return AT_COMMAND_INFO[base_cmd.upper()]
    # Prefix matching for compound commands
    for known_cmd in sorted(AT_COMMAND_INFO.keys(), key=len, reverse=True):
        if cmd_upper.startswith(known_cmd):
            return AT_COMMAND_INFO[known_cmd]

    # Generic categorization
    if cmd_upper.startswith('AT+QI'):
        return ('GPRS', 'Quectel IP Command')
    if cmd_upper.startswith('AT+CI'):
        return ('GPRS', 'IP Command')
    if cmd_upper.startswith('AT+Q'):
        return ('Quectel', 'Quectel Proprietary')
    if cmd_upper.startswith('AT+C'):
        return ('3GPP', 'Standard AT Command')
    if cmd_upper.startswith('AT'):
        return ('Basic', '')
    # Numeric-only (IMSI, IMEI etc.)
    if cmd.replace(' ', '').replace('.', '').replace('-', '').isdigit():
        return ('Data', 'Numeric Response')
    # Parsed fields from [AT.RSP] (e.g. "Parsed Status: 5")
    if any(cmd.startswith(p) for p in ('Parsed ', 'Area Code', 'Cell ID', 'Registration', 'Registered')):
        return ('Parsed', 'Firmware Interpretation')
    return ('Other', '')


def _extract_at_base_cmd(cmd_text):
    """Extract base AT command name for response correlation.
    
    'AT+CIMI\\r' → 'CIMI',  'AT+CREG?' → 'CREG',  'AT+QCFG="nwscanmode"' → 'QCFG'
    """
    cmd = cmd_text.strip().rstrip('\r\n\x00')
    if cmd.upper().startswith('AT+'):
        cmd = cmd[3:]
    elif cmd.upper().startswith('AT'):
        cmd = cmd[2:]
    cmd = re.split(r'[=?,\s]', cmd, 1)[0]
    return cmd.upper()


def ddm_to_dd(raw_val, direction):
    """ Converts NMEA degrees/minutes to decimal degrees. """
    if not raw_val or '.' not in raw_val: return None
    try:
        decimal_point = raw_val.find('.')
        split_index = decimal_point - 2
        degrees = float(raw_val[:split_index])
        minutes = float(raw_val[split_index:])
        dd = degrees + (minutes / 60)
        if direction.upper() in ['S', 'W']: dd = -dd
        return dd
    except: return None

def get_marker_color(speed, ignition):
    """Returns color based on vehicle state."""
    if not ignition:
        return '#000000' # Black = Parked/Ignition Off
    if speed < 5:
        return '#FF8C00' # Orange = Idling
    return '#00FF00'     # Green = Moving

def parse_log(content_str, progress_callback=None):
    data_points = []
    events = []
    structured_logs = []
    modem_info = {
        'signal_readings': [],
        'at_commands': [],
        'device_identity': {},
        'records': [],
    }
    device_identity = modem_info['device_identity']
    
    # --- STRUCTURE REGEX ---
    # Matches: LineNum? SysTime Type Timestamp Date Module, Level Message
    # Example: 095775    0:3167379 [Trace]	13:47:18:434 2026/01/26	MOD_15APP_OBD_LVCAN, TRACE_INFO	"[OBD.OEM] ..."
    # We make parts optional to handle headers/multilines
    rx_structure = re.compile(
        r'^\s*(?:(\d+)\s+)?'             # Group 1: Line number (Optional)
        r'(\d+:\d+)?\s*'                 # Group 2: SysTick (e.g., 0:3167379)
        r'(\[.*?\])?\s*'                 # Group 3: Type (e.g., [Trace] or [Var/Mem])
        r'(\d{2}:\d{2}:\d{2}:\d{3})?\s+' # Group 4: Time
        r'(\d{4}/\d{2}/\d{2})?\s+'       # Group 5: Date
        r'(?:([\w_]+),\s+(\w+)\s*)?'     # Group 6,7: Module, Level (Optional, grouped)
        r'(.*)$'                         # Group 8: Message (Rest of line)
    )

    # --- REGEX PATTERNS FOR EVENTS ---
    # 1. Capture Date from Trace lines
    rx_date = re.compile(r'(\d{4}/\d{2}/\d{2})') 
    
    # 2. Capture NMEA
    rx_nmea = re.compile(r'(\d{2}:\d{2}:\d{2}:\d{3}).*?\[NMEA_LOG\](\$G\w(?:RMC|GGA).*?\*[0-9A-F]{2})')
    
    # 3. Capture Voltage (Fallback Ignition)
    rx_lipo = re.compile(r'(\d{2}:\d{2}:\d{2}:\d{3}).*?\[LiPo\].*?ExtV:\s*(\d+)') 
    
    # 4. Capture Firmware Logic State (TRIP)
    rx_ign_change = re.compile(r'(\d{2}:\d{2}:\d{2}:\d{3}).*?Ignition changed:\s*(\d+)->(\d+)\s*\((\d+)\)')
    rx_trip_periodic = re.compile(r'(\d{2}:\d{2}:\d{2}:\d{3}).*?\[TRIP\].*?Periodic info: State -> (\w+)\. Spd:(\d+)km/h, Mov:(YES|NO), Ign:(ON|OFF)')
    rx_trip_dist = re.compile(r'(\d{2}:\d{2}:\d{2}:\d{3}).*?\[TRIP\].*?Distance driven: (\d+) km')
    rx_trip_start = re.compile(r'(\d{2}:\d{2}:\d{2}:\d{3}).*?\[TRIP\].*?START \(Spd:(\d+)km/h, Mov:(YES|NO), Ign:(ON|OFF)\)')
    rx_trip_end = re.compile(r'(\d{2}:\d{2}:\d{2}:\d{3}).*?\[TRIP\].*?END \(Spd:(\d+)km/h, Mov:(YES|NO), Ign:(ON|OFF)\)')
    rx_trip_true = re.compile(r'(\d{2}:\d{2}:\d{2}:\d{3}).*?\[TRIP\].*?Trip trip_state true')

    # 4b. Movement Detection (Delayed MovDetect)
    # Example: [MovDetect] Delayed movement state changed:0 -> 1
    rx_mov_delayed = re.compile(r'(\d{2}:\d{2}:\d{2}:\d{3}).*?\[MovDetect\].*?Delayed movement state changed:\s*(\d+)\s*->\s*(\d+)')
    
    # 5. GPS Internals
    # Regex 1: The standard "Trace" line with timestamp
    rx_gps_state = re.compile(r'(\d{2}:\d{2}:\d{2}:\d{3}).*?GPS Fix:\s*(\d)')
    # Regex 2: The "No fix reason" line typically follows the Trace line but on a new line without timestamp
    # We must treat the previous Trace line's timestamp as the context for this event if it appears immediately after.
    rx_nofix_code_inline = re.compile(r'(\d{2}:\d{2}:\d{2}:\d{3}).*?No fix reason:\s*(\d+)')
    rx_nofix_code_multiline = re.compile(r'^No fix reason:\s*(\d+)')
    
    # Regex 3: Explicit Fix Status Change (User Request)
    rx_gps_change = re.compile(r'(\d{2}:\d{2}:\d{2}:\d{3}).*?\[GPS\.API\].*?Fix status changed:\s*(\d+)\s*=>\s*(\d+)')

    # 6. Static Navigation
    rx_static_nav = re.compile(r'\[(\d{4}\.\d{2}\.\d{2}\s\d{2}:\d{2}:\d{2})\]-\[GPS\.API\].*?:(Static Navigation (STARTED|ENDED)!)')
    rx_static_nav_simple = re.compile(r'Static nav mode changed:\s*(\d)\s*=>\s*(\d)\.')

    # 7. Sleep Parsing
    rx_sleep_enter = re.compile(r'\[SLEEP\]\s+\*\*\*\s+Enter(?:ed\s+to)?\s+(?:(\w+)\s+)?Sleep\s+Mode(?:\s+\[(\d+)\])?\s+\*\*\*')
    rx_sleep_exit = re.compile(r'\[SLEEP\]\s+\*\*\*\s+Totally\s+woken\s+from\s+sleep!\s+\*\*\*')
    rx_sleep_wakeup = re.compile(r'\[SLEEP\]\s+WakeUp\s+from\s+sleep\s+mode\s+to\s+send\s+data!')
    rx_sleep_warning = re.compile(r'\[SLEEP\]\s+WARNING\s+@.*?:(Sleep:\d+),\s+not\s+allowed!\s+Reason:(.*)')

    # 8. Modem / GSM / Network / Record Sending
    rx_at_cmd = re.compile(r'(\d{2}:\d{2}:\d{2}:\d{3}).*?\[ATCMD\]\s+(.*)')
    rx_at_rsp = re.compile(r'(\d{2}:\d{2}:\d{2}:\d{3}).*?\[AT\.RSP\]\s+(.*)')
    rx_csq_val = re.compile(r'\+CSQ:\s*(\d+),\s*(\d+)')
    rx_qcsq_val = re.compile(r'\+QCSQ:\s*"?(\w+)"?,\s*([-\d]+)(?:,\s*([-\d]+))?(?:,\s*([-\d]+))?(?:,\s*([-\d.]+))?')
    rx_cops_val = re.compile(r'\+COPS:\s*\d+,\s*\d+,\s*"([^"]+)"(?:,\s*(\d+))?')
    rx_creg_val = re.compile(r'\+C(?:E)?REG:\s*(?:\d+,\s*)?(\d+)(?:,\s*"([^"]*)")?(?:,\s*"([^"]*)")?(?:,\s*(\d+))?')
    rx_rec_send = re.compile(r'(\d{2}:\d{2}:\d{2}:\d{3}).*?\[REC\.SEND\.(\d)\].*?(\d{1,2})\s*=>\s*(\d{1,2})')
    # CHANGE.STATE text-based transitions: [REC.SEND.1] [CHANGE.STATE.0842] Server: 0, check link => send imei
    rx_rec_send_change = re.compile(r'(\d{2}:\d{2}:\d{2}:\d{3}).*?\[REC\.SEND\.(\d)\].*?\[CHANGE\.STATE\.(\d+)\]\s*Server:\s*(\d),\s*(.+?)\s*=>\s*(.+?)\s*$')
    # Key rec-send events (text messages)
    rx_rec_send_accepted_imei = re.compile(r'(\d{2}:\d{2}:\d{2}:\d{3}).*?\[REC\.SEND\.(\d)\].*?server accepted imei')
    rx_rec_send_accepted_recs = re.compile(r'(\d{2}:\d{2}:\d{2}:\d{3}).*?\[REC\.SEND\.(\d)\].*?server accepted records')
    rx_rec_send_packed = re.compile(r'(\d{2}:\d{2}:\d{2}:\d{3}).*?\[REC\.SEND\.(\d)\].*?records packed:\s*(\d+)')
    rx_rec_send_sent = re.compile(r'(\d{2}:\d{2}:\d{2}:\d{3}).*?\[REC\.SEND\.(\d)\].*?Sent\s+(\d+)\s+records\s+of\s+min\s+required\s+(\d+)')
    rx_rec_send_starting = re.compile(r'(\d{2}:\d{2}:\d{2}:\d{3}).*?\[REC\.SEND\.(\d)\].*?Starting periodic data sending')
    rx_rec_send_enough = re.compile(r'(\d{2}:\d{2}:\d{2}:\d{3}).*?\[REC\.SEND\.(\d)\].*?Have enough records to send')
    rx_rec_send_periodic = re.compile(r'(\d{2}:\d{2}:\d{2}:\d{3}).*?\[REC\.SEND\.(\d)\].*?Mode:\s*(\d+)/(\w[\w\s]*?)\.\s*(?:Next periodic data sending:\s*(\d+)\s*/\s*(\d+)|Period:\s*(\d+))')
    rx_rec_send_link_tmo = re.compile(r'(\d{2}:\d{2}:\d{2}:\d{3}).*?\[REC\.SEND\.(\d)\].*?link tmo detected.*?server\s*(\d)')
    rx_rec_send_queue = re.compile(r'(\d{2}:\d{2}:\d{2}:\d{3}).*?\[REC\.SEND\.(\d)\].*?queueing recsend\d+ task job type:\s*(\d+)/(\w+)')
    rx_rec_gen = re.compile(r'(\d{2}:\d{2}:\d{2}:\d{3}).*?\[REC\.GEN\]\s+(.*)')
    rx_avl_id = re.compile(r'Event AVL ID\s*:\s*(\d+)')

    # Record Content block fields (multiline, from REC.GEN trace)
    rx_rec_content_start = re.compile(r'Record Content:')
    rx_rec_priority = re.compile(r'Priority\s*:\s*(\d+)')
    rx_rec_latitude = re.compile(r'Latitude\s*:\s*([\-\d.]+)')
    rx_rec_longitude = re.compile(r'Longitude\s*:\s*([\-\d.]+)')
    rx_rec_altitude = re.compile(r'Altitude\s*:\s*([\-\d]+)')
    rx_rec_angle = re.compile(r'Angle\s*:\s*([\-\d]+)')
    rx_rec_speed = re.compile(r'(?<![G])Speed\s*:\s*(\d+)')
    rx_rec_hdop = re.compile(r'HDOP\s*:\s*([\d.]+)')
    rx_rec_sat = re.compile(r'SatInUse\s*:\s*(\d+)')
    rx_rec_fix = re.compile(r'GPS Fix\s*:\s*(\d+)')
    rx_rec_gspeed = re.compile(r'GSpeed\s*:\s*(\d+),\s*src:\s*(\S+)')
    rx_rec_io = re.compile(r'IO ID\[\s*(\d+)\](?:\s*Length\[\s*\d+\])?\s*:\s*(.*)')
    rx_rec_size = re.compile(r'Record Size:\s*(\d+)\s*Bytes')
    rx_rec_save = re.compile(r'(\d{2}:\d{2}:\d{2}:\d{3}).*?\[REC\.GEN\].*?(Eventual|Periodic)\s+(\w+)\s+priority\s+record\s+save\s+queued')
    rx_rec_timestamp = re.compile(r'Timestamp\s*:\s*(\d+)')
    rx_gprs_ev = re.compile(r'(\d{2}:\d{2}:\d{2}:\d{3}).*?\[GPRS\.CMD\]\s+(.*)')
    rx_modem_change = re.compile(r'(\d{2}:\d{2}:\d{2}:\d{3}).*?\[MODEM\].*?[Ss]tate.*?changed.*?(\w+)\s*->\s*(\w+)')
    rx_status_operator = re.compile(r'GSM Operator\s*:\s*(\d+)')
    rx_status_csq = re.compile(r'CSQ \(rssi\)\s*:\s*(\d+)')
    rx_status_rsrp = re.compile(r'QCSQ \(rsrp\)\s*:\s*([-\d]+)')
    rx_status_sinr = re.compile(r'QCSQ \(sinr\)\s*:\s*([-\d.]+)')
    rx_status_rsrq = re.compile(r'QCSQ \(rsrq\)\s*:\s*([-\d.]+)')
    rx_status_network = re.compile(r'Network Type\s*:\s*\d+/(\w+)')
    rx_status_band = re.compile(r'Current LTE BAND\s*:\s*(\d+)')
    rx_status_imsi = re.compile(r'IMSI\s*:\s*(\d{15})')
    rx_status_ccid = re.compile(r'CCID\s*:\s*(\d{19,20})')
    rx_raw_tag = re.compile(r'-\[(.*?)\]\s+(.*)')

    # [SYS.DIAG] block fields
    rx_diag_imei = re.compile(r'IMEI:\s+(\d{15})')
    rx_diag_hw_ver = re.compile(r'HW ver:\s+(\S+)')
    rx_diag_hw_mod = re.compile(r'HW mod:\s+(\S+)')
    rx_diag_code_ver = re.compile(r'Code Version:(\S+)')
    rx_diag_code_rev = re.compile(r'Code Rev:(\d+)')
    rx_diag_bl_ver = re.compile(r'BL ver:\s+(\S+)')
    # Modem type from FMBS payload (e.g. SLM320PE_TK_V51_U09, BG96...)
    rx_modem_fw = re.compile(r'FMBS;\d(\w+?)(?:\x00|ENDS|\s)')
    # Modem type from AT+CGMR/QGMR response or log lines
    rx_modem_type_line = re.compile(r'Modem(?:\s+(?:type|model|name))?\s*:\s*(\S+)', re.IGNORECASE)

    # Catcher AT dump format  (|[AT.CMD] Transmit/Received AT:| ASCII:...)
    rx_at_catcher_ascii = re.compile(
        r'\|\[AT\.CMD\]\s+(Transmit|Received)\s+AT:\|\s+ASCII:(.*)')
    rx_at_catcher_header = re.compile(
        r'(\d{2}:\d{2}:\d{2}:\d{3}).*?\[AT\.CMD\]\s+(Transmit|Received)\s+AT:')
    rx_qnwinfo_val = re.compile(
        r'\+QNWINFO:\s*"?([^"\s,]+)"?,\s*"?([^"\s,]+)"?,\s*"?([^"\s,]+)"?')
    rx_cipstatus_val = re.compile(
        r'\+CIPSTATUS:(\d+),(\d+),(\w+),([^,]+),(\d+),(\w+)')

    # State Tracking
    current_ignition = False
    current_movement = False
    current_trip_state = None
    ignition_threshold = 13000 # 13V threshold if physical detection fails
    last_fix_state = -1
    current_operator = None
    current_network_type = None
    current_creg_state = -1
    _status_snapshot = {}

    # AT command tracking for Catcher format
    _last_at_cmd_sent = ''
    _last_at_cmd_base = ''   # e.g. 'CIMI', 'CREG', 'CSQ'
    _at_group_counter = 0    # groups TX/RX pairs

    # Record generation multiline accumulator
    _rec_accumulating = False       # True while inside a Record Content block
    _rec_current = None             # Dict being built for current record
    _rec_start_line = 0             # Line number where record block started

    # Default date
    current_date_str = datetime.now().strftime('%Y/%m/%d')
    
    def resolve_ts(line_content, time_str):
        # Uses current_date_str from outer scope which is updated in the loop
        return f"{current_date_str} {time_str}"

    lines = content_str.splitlines()
    total_lines = len(lines)
    
    last_timestamp_str = "00:00:00:000"
    
    # Pre-compiled empty values for performance
    last_parsed_time = None
    last_parsed_module = ""
    last_parsed_level = ""

    for i, line in enumerate(lines):
        # Progress callback
        if progress_callback and i % 2000 == 0:
            progress_callback(i / total_lines)

        line = line.strip()
        if not line: continue

        match_at_cmd = None
        match_at_rsp = None
            
        # --- 0. FAST STRUCTURE PARSE ---
        # Try to parse structure first to populate the raw viewer
        struct_match = rx_structure.match(line)
        if struct_match:
            ln, stik, ltype, tm, dt, mod, lvl, msg = struct_match.groups()
            
            # If line starts with a LineNumber (from some editors), use it, otherwise use index+1
            display_ln = int(ln) if ln else (i + 1)
            
            # Timestamp handling
            if tm:
                last_parsed_time = tm
                last_timestamp_str = tm # Sync with event parser
            
            # Date handling
            if dt:
                current_date_str = dt
            
            # Module/Level handling (often persists or is specific to line)
            if mod: last_parsed_module = mod
            if lvl: last_parsed_level = lvl
            
            # If it's a multiline hex dump (usually no timestamp/module),
            # it might match broadly, but we can detect based on missing Type/Time
            is_hex_dump = (ltype is None and tm is None)
            
            structured_logs.append({
                'Line': display_ln,
                'Time': tm if tm else "",
                'Type': ltype if ltype else "",
                'Module': mod if mod else "",
                'Level': lvl if lvl else "",
                'Message': msg.strip() # Remove extra tabs/spaces
            })
        else:
            # Fallback for weird lines
            structured_logs.append({
                'Line': i + 1,
                'Time': "",
                'Type': "",
                'Module': "",
                'Level': "",
                'Message': line
            })

        # 0. Update current date context (Legacy, safe to keep or rely on structure above)
        match_date = rx_date.search(line)
        if match_date:
            current_date_str = match_date.group(1)
            
        # Capture timestamp of the current line if present (used for multiline context)
        # Matches typical HH:MM:SS:MS pattern
        ts_check = re.search(r'(\d{2}:\d{2}:\d{2}:\d{3})', line)
        if ts_check:
            last_timestamp_str = ts_check.group(1)
        # 1. FIRMWARE STATE DETECTION (TRIP) & IGNITION
        
        # A. Explicit Ignition Change
        if 'Ignition changed' in line:
            match_ign = rx_ign_change.search(line)
            if match_ign:
                ts, old_v, new_v, phy = match_ign.groups()
                final_ts = resolve_ts(line, ts)
                new_ign_bool = (new_v == '1')
                
                if new_ign_bool != current_ignition:
                    current_ignition = new_ign_bool
                    events.append({
                        'LineNum': i + 1,
                        'Timestamp': final_ts,
                        'Type': 'Ignition',
                        'Value': 'ON' if new_ign_bool else 'OFF',
                        'Details': f'Ignition Changed ({old_v}->{new_v})',
                        'Log': line.strip()
                    })

        # B. Trip Periodic & Start/End
        if '[TRIP]' in line:
            # Trip Periodic Info
            match_trip = rx_trip_periodic.search(line)
            if match_trip:
                ts, state, spd, mov, ign = match_trip.groups()
                final_ts = resolve_ts(line, ts)
                
                # Sync Ignition
                new_ign_bool = (ign == 'ON')
                if new_ign_bool != current_ignition:
                    current_ignition = new_ign_bool
                    events.append({
                        'LineNum': i + 1,
                        'Timestamp': final_ts,
                        'Type': 'Ignition',
                        'Value': 'ON' if new_ign_bool else 'OFF',
                        'Details': 'Trip Periodic Sync',
                        'Log': line.strip()
                    })
                
                # Sync Trip State (Stop/Moving)
                if state != current_trip_state:
                    current_trip_state = state
                    events.append({
                        'LineNum': i + 1,
                        'Timestamp': final_ts,
                        'Type': 'Trip Status',
                        'Value': state,
                        'Details': f'State Changed to {state} (Spd:{spd})',
                        'Log': line.strip()
                    })

            # Trip Start
            match_start = rx_trip_start.search(line)
            if match_start:
                ts, spd, mov, ign = match_start.groups()
                events.append({
                    'LineNum': i + 1,
                    'Timestamp': resolve_ts(line, ts),
                    'Type': 'Trip Status',
                    'Value': 'START',
                    'Details': f'Trip Started (Ign:{ign})',
                    'Log': line.strip()
                })
                
            # Trip End
            match_end = rx_trip_end.search(line)
            if match_end:
                ts, spd, mov, ign = match_end.groups()
                events.append({
                    'LineNum': i + 1,
                    'Timestamp': resolve_ts(line, ts),
                    'Type': 'Trip Status',
                    'Value': 'END',
                    'Details': f'Trip Ended (Ign:{ign})',
                    'Log': line.strip()
                })

            # Trip True
            match_true = rx_trip_true.search(line)
            if match_true:
                ts = match_true.group(1)
                events.append({
                    'LineNum': i + 1,
                    'Timestamp': resolve_ts(line, ts),
                    'Type': 'Trip Status',
                    'Value': 'Trip State True',
                    'Details': 'Condition Met',
                    'Log': line.strip()
                })

            # Trip Distance
            match_dist = rx_trip_dist.search(line)
            if match_dist:
                ts, dist = match_dist.groups()
                events.append({
                    'LineNum': i + 1,
                    'Timestamp': resolve_ts(line, ts),
                    'Type': 'Trip Info',
                    'Value': 'Distance',
                    'Details': f'{dist} km',
                    'Log': line.strip()
                })

        # 1b. Movement Detection (Delayed)
        if '[MovDetect]' in line:
            match_mov = rx_mov_delayed.search(line)
            if match_mov:
                 ts, old_state, new_state = match_mov.groups()
                 final_ts = resolve_ts(line, ts)
                 new_mov = (new_state == '1')
                 
                 if new_mov != current_movement:
                    current_movement = new_mov
                    events.append({
                        'LineNum': i + 1,
                        'Timestamp': final_ts,
                        'Type': 'Movement',
                        'Value': 'Start' if new_mov else 'Stop',
                        'Details': f'Delayed Mov ({old_state}->{new_state})',
                        'Log': line.strip()
                    })

        # 3a. Explicit GPS Status Change (Priority)
        if '[GPS.API]' in line:
            match_change = rx_gps_change.search(line)
            if match_change:
                ts, old_s, new_s = match_change.groups()
                final_ts = resolve_ts(line, ts)
                new_s_int = int(new_s)
                
                last_fix_state = new_s_int
                events.append({
                    'LineNum': i + 1,
                    'Timestamp': final_ts,
                    'Type': 'GPS State',
                    'Value': 'Fix Acquired' if new_s_int == 1 else 'Lost Fix',
                    'Details': f'Status Change ({old_s}->{new_s})',
                    'Log': line.strip()
                })
                
            # 5. Static Navigation
            match_static = rx_static_nav.search(line)
            if match_static:
                dt_full, full_msg, state_keyword = match_static.groups()
                try:
                    dt_norm = dt_full.replace('.', '/') + ':000'
                    events.append({
                        'LineNum': i + 1,
                        'Timestamp': dt_norm,
                        'Type': 'Static Navigation',
                        'Value': state_keyword, # STARTED / ENDED
                        'Details': full_msg,
                        'Log': line.strip()
                    })
                except: pass

        # 3b. Check GPS Internal State (Periodic)
        if 'GPS Fix:' in line:
            match_state = rx_gps_state.search(line)
            if match_state:
                ts, state = match_state.groups()
                state = int(state)
                # Sync state if we missed the start
                if last_fix_state == -1:
                    last_fix_state = state

        # 4. Check No Fix Reason Code
        if 'No fix reason:' in line:
            # Case A: Inline timestamp (rare but possible)
            match_code = rx_nofix_code_inline.search(line)
            if match_code:
                ts, code_str = match_code.groups()
                final_ts = resolve_ts(line, ts)
                code = int(code_str)
                if code > 0 and last_fix_state == 0:
                    reasons = gps_codes.decode_reason(code)
                    events.append({
                        'LineNum': i + 1,
                        'Timestamp': final_ts,
                        'Type': 'No Fix Reason',
                        'Value': f'Code {code}',
                        'Details': ", ".join(reasons),
                        'Log': line.strip()
                    })
            else:
                # Case B: Multiline (appears on the next line without timestamp)
                # We use the LAST seen timestamp
                match_code_ml = rx_nofix_code_multiline.search(line)
                if match_code_ml:
                    code_str = match_code_ml.group(1)
                    final_ts = resolve_ts(line, last_timestamp_str)
                    code = int(code_str)
                    if code > 0: 
                        reasons = gps_codes.decode_reason(code)
                        events.append({
                            'LineNum': i + 1,
                            'Timestamp': final_ts,
                            'Type': 'No Fix Reason',
                            'Value': f'Code {code}',
                            'Details': ", ".join(reasons),
                            'Log': line.strip()
                        })

        # 6. Standard NMEA Parsing
        if '[NMEA_LOG]' in line:
            match_nmea = rx_nmea.search(line)
            if match_nmea:
                ts, nmea = match_nmea.groups()
                parts = nmea.split(',')
                stype = parts[0][-3:]
                lat, lon, kmh = None, None, 0.0

                if stype == 'RMC' and len(parts) > 7 and parts[2] == 'A':
                    lat = ddm_to_dd(parts[3], parts[4])
                    lon = ddm_to_dd(parts[5], parts[6])
                    try: kmh = float(parts[7].strip() or 0) * 1.852
                    except: pass
                
                elif stype == 'GGA' and len(parts) > 6 and parts[6] != '0':
                    lat = ddm_to_dd(parts[2], parts[3])
                    lon = ddm_to_dd(parts[4], parts[5])

                if lat and lon:
                    clean_ts = ts.split(':')[0:3] 
                    clean_ts = ":".join(clean_ts)
                    dt_obj = datetime.strptime(f"{current_date_str} {clean_ts}", "%Y/%m/%d %H:%M:%S")
                    iso_ts = dt_obj.isoformat()

                    data_points.append({
                        'LineNum': i + 1,
                        'loc': (lat, lon),
                        'desc': f"[{ts}] {nmea}",
                        'speed': kmh,
                        'speed_str': f"{kmh:.1f} km/h",
                        'ignition': current_ignition,
                        'time_iso': iso_ts 
                    })

        # 7. Sleep Events
        if '[SLEEP]' in line:
            match_sleep_ent = rx_sleep_enter.search(line)
            if match_sleep_ent:
                # Check for timestamp at start of line
                ts_check = re.search(r'(\d{2}:\d{2}:\d{2}:\d{3})', line)
                ts_val = ts_check.group(1) if ts_check else last_timestamp_str
                final_ts = resolve_ts(line, ts_val)
                
                mode_name, mode_id = match_sleep_ent.groups()
                details = []
                if mode_name: details.append(mode_name)
                if mode_id: details.append(f"Mode[{mode_id}]")
                
                events.append({
                    'LineNum': i + 1,
                    'Timestamp': final_ts,
                    'Type': 'Sleep Mode',
                    'Value': 'Enter',
                    'Details': f"Entered Sleep ({' '.join(details)})",
                    'Log': line.strip()
                })

            match_sleep_exit = rx_sleep_exit.search(line)
            if match_sleep_exit:
                ts_check = re.search(r'(\d{2}:\d{2}:\d{2}:\d{3})', line)
                ts_val = ts_check.group(1) if ts_check else last_timestamp_str
                final_ts = resolve_ts(line, ts_val)
                events.append({
                    'LineNum': i + 1,
                    'Timestamp': final_ts,
                    'Type': 'Sleep Mode',
                    'Value': 'Exit',
                    'Details': 'Totally Woken',
                    'Log': line.strip()
                })

            match_sleep_wake = rx_sleep_wakeup.search(line)
            if match_sleep_wake:
                ts_check = re.search(r'(\d{2}:\d{2}:\d{2}:\d{3})', line)
                ts_val = ts_check.group(1) if ts_check else last_timestamp_str
                final_ts = resolve_ts(line, ts_val)
                events.append({
                    'LineNum': i + 1,
                    'Timestamp': final_ts,
                    'Type': 'Sleep Mode',
                    'Value': 'WakeUp Send',
                    'Details': 'WakeUp to Send Data',
                    'Log': line.strip()
                })
                
            match_sleep_warn = rx_sleep_warning.search(line)
            if match_sleep_warn:
                ts_check = re.search(r'(\d{2}:\d{2}:\d{2}:\d{3})', line)
                ts_val = ts_check.group(1) if ts_check else last_timestamp_str
                final_ts = resolve_ts(line, ts_val)
                
                err_type, reason = match_sleep_warn.groups()
                events.append({
                    'LineNum': i + 1,
                    'Timestamp': final_ts,
                    'Type': 'Sleep Mode',
                    'Value': 'Warning',
                    'Details': f"{err_type} Blocked: {reason.strip()}",
                    'Log': line.strip()
                })

        # 8. AT Commands & Responses (console-trace format: [ATCMD] / [AT.RSP])
        if '[ATCMD]' in line:
            match_at_cmd = rx_at_cmd.search(line)
            if match_at_cmd:
                ts_ac, cmd = match_at_cmd.groups()
                cmd_clean = cmd.strip().strip('"')
                _at_group_counter += 1
                _last_at_cmd_sent = cmd_clean
                _last_at_cmd_base = _extract_at_base_cmd(cmd_clean)
                _cat, _desc = classify_at_command(cmd_clean)
                modem_info['at_commands'].append({
                    'Timestamp': resolve_ts(line, ts_ac), 'Direction': 'CMD',
                    'Content': cmd_clean, 'LineNum': i + 1,
                    'Category': _cat, 'Description': _desc, 'Group': _at_group_counter,
                })

        if '[AT.RSP]' in line:
            match_at_rsp = rx_at_rsp.search(line)
            if match_at_rsp:
                ts_ar, rsp = match_at_rsp.groups()
                rsp = rsp.strip().strip('"')
                # In Catcher logs [AT.RSP] carries parsed fields ("Parsed Status: 5"),
                # in console-trace logs it carries raw responses ("+CSQ: 15,0").
                _rsp_dir = 'RSP'
                if not (rsp.startswith('+') or rsp.upper() in ('OK', 'ERROR', '>', 'CONNECT')):
                    _rsp_dir = 'INFO'
                _cat, _desc = classify_at_command(rsp)
                modem_info['at_commands'].append({
                    'Timestamp': resolve_ts(line, ts_ar), 'Direction': _rsp_dir,
                    'Content': rsp, 'LineNum': i + 1,
                    'Category': _cat, 'Description': _desc, 'Group': _at_group_counter,
                })
                # Extract signal from +CSQ
                if '+CSQ:' in rsp:
                    m_csq = rx_csq_val.search(rsp)
                    if m_csq:
                        csq = int(m_csq.group(1))
                        if csq < 99:
                            modem_info['signal_readings'].append({
                                'Timestamp': resolve_ts(line, ts_ar), 'CSQ': csq,
                                'RSSI_dBm': -113 + (csq * 2), 'RSRP_dBm': None,
                                'SINR_dB': None, 'RSRQ_dB': None, 'Network': current_network_type
                            })
                # Extract signal from +QCSQ
                if '+QCSQ:' in rsp:
                    m_qcsq = rx_qcsq_val.search(rsp)
                    if m_qcsq:
                        nw = m_qcsq.group(1)
                        rssi_r = int(m_qcsq.group(2)) if m_qcsq.group(2) else None
                        rsrp_r = int(m_qcsq.group(3)) if m_qcsq.group(3) else None
                        sinr_r = int(m_qcsq.group(4)) if m_qcsq.group(4) else None
                        rsrq_r = float(m_qcsq.group(5)) if m_qcsq.group(5) else None
                        modem_info['signal_readings'].append({
                            'Timestamp': resolve_ts(line, ts_ar), 'CSQ': None,
                            'RSSI_dBm': rssi_r, 'RSRP_dBm': rsrp_r,
                            'SINR_dB': sinr_r, 'RSRQ_dB': rsrq_r, 'Network': nw
                        })
                # Extract operator from +COPS
                if '+COPS:' in rsp:
                    m_cops = rx_cops_val.search(rsp)
                    if m_cops:
                        oper = m_cops.group(1)
                        act = int(m_cops.group(2)) if m_cops.group(2) else None
                        nw_name = NETWORK_ACT.get(act, str(act)) if act is not None else current_network_type
                        if oper != current_operator:
                            current_operator = oper
                            current_network_type = nw_name
                            events.append({
                                'LineNum': i + 1, 'Timestamp': resolve_ts(line, ts_ar),
                                'Type': 'Operator', 'Value': oper,
                                'Details': f'Operator: {oper} ({nw_name})', 'Log': line.strip()
                            })
                # Extract registration from +CREG/+CEREG
                if 'REG:' in rsp: # +CREG, +CEREG, +CGREG
                    m_creg = rx_creg_val.search(rsp)
                    if m_creg:
                        stat = int(m_creg.group(1))
                        lac = m_creg.group(2)
                        ci = m_creg.group(3)
                        act = int(m_creg.group(4)) if m_creg.group(4) else None
                        if stat != current_creg_state:
                            current_creg_state = stat
                            sname = CREG_STATES.get(stat, f'Unknown({stat})')
                            nw_name = NETWORK_ACT.get(act, '') if act is not None else ''
                            if nw_name: current_network_type = nw_name
                            det = sname
                            if lac: det += f' LAC:{lac}'
                            if ci: det += f' CID:{ci}'
                            if nw_name: det += f' [{nw_name}]'
                            events.append({
                                'LineNum': i + 1, 'Timestamp': resolve_ts(line, ts_ar),
                                'Type': 'Network', 'Value': sname,
                                'Details': det, 'Log': line.strip()
                            })

        # 8b. Catcher AT dump format (|[AT.CMD] ... AT:| ASCII:...)
        #     These lines have no timestamp — use last_timestamp_str set by the
        #     preceding header line.
        if '|[AT.CMD]' in line:
            _m_cat_ascii = rx_at_catcher_ascii.search(line)
            if _m_cat_ascii:
                _cat_dir_raw = _m_cat_ascii.group(1)   # 'Transmit' or 'Received'
                _cat_content = _m_cat_ascii.group(2).strip().rstrip('\x00').strip()
                if _cat_content:
                    _cat_ts = resolve_ts(line, last_timestamp_str)
                    if _cat_dir_raw == 'Transmit':
                        _at_group_counter += 1
                        _last_at_cmd_sent = _cat_content
                        _last_at_cmd_base = _extract_at_base_cmd(_cat_content)
                        _cat_dir = 'CMD'
                    else:
                        _cat_dir = 'RSP'
                        # ── Identity extraction from plain-value responses ──
                        if _last_at_cmd_base in _IDENTITY_CMD_MAP:
                            _id_field = _IDENTITY_CMD_MAP[_last_at_cmd_base]
                            if (_cat_content
                                    and not _cat_content.startswith('+')
                                    and _cat_content.upper() not in (
                                        'OK', 'ERROR', '>', 'CONNECT',
                                        'NO CARRIER', 'RING')
                                    and not _cat_content.upper().startswith('SEND')):
                                device_identity[_id_field] = _cat_content

                        # ── SIM status from +CPIN ──
                        if _cat_content.upper().startswith('+CPIN:'):
                            device_identity['sim_status'] = _cat_content.split(':', 1)[1].strip()

                        # ── Network info from +QNWINFO ──
                        _m_qnw = rx_qnwinfo_val.search(_cat_content)
                        if _m_qnw:
                            device_identity['network_type'] = _m_qnw.group(1)
                            device_identity['band'] = _m_qnw.group(3)
                            current_network_type = _m_qnw.group(1)

                        # ── Signal from +CSQ ──
                        _m_csq_c = rx_csq_val.search(_cat_content)
                        if _m_csq_c:
                            _csq_v = int(_m_csq_c.group(1))
                            if _csq_v < 99:
                                modem_info['signal_readings'].append({
                                    'Timestamp': _cat_ts, 'CSQ': _csq_v,
                                    'RSSI_dBm': -113 + (_csq_v * 2),
                                    'RSRP_dBm': None, 'SINR_dB': None,
                                    'RSRQ_dB': None, 'Network': current_network_type,
                                })

                        # ── Signal from +QCSQ ──
                        _m_qcsq_c = rx_qcsq_val.search(_cat_content)
                        if _m_qcsq_c:
                            _nw_c = _m_qcsq_c.group(1)
                            modem_info['signal_readings'].append({
                                'Timestamp': _cat_ts, 'CSQ': None,
                                'RSSI_dBm': int(_m_qcsq_c.group(2)) if _m_qcsq_c.group(2) else None,
                                'RSRP_dBm': int(_m_qcsq_c.group(3)) if _m_qcsq_c.group(3) else None,
                                'SINR_dB': int(_m_qcsq_c.group(4)) if _m_qcsq_c.group(4) else None,
                                'RSRQ_dB': float(_m_qcsq_c.group(5)) if _m_qcsq_c.group(5) else None,
                                'Network': _nw_c,
                            })

                        # ── Operator from +COPS ──
                        _m_cops_c = rx_cops_val.search(_cat_content)
                        if _m_cops_c:
                            _oper_c = _m_cops_c.group(1)
                            _act_c = int(_m_cops_c.group(2)) if _m_cops_c.group(2) else None
                            _nw_c = NETWORK_ACT.get(_act_c, str(_act_c)) if _act_c is not None else current_network_type
                            if _oper_c != current_operator:
                                current_operator = _oper_c
                                current_network_type = _nw_c
                                events.append({
                                    'LineNum': i + 1, 'Timestamp': _cat_ts,
                                    'Type': 'Operator', 'Value': _oper_c,
                                    'Details': f'Operator: {_oper_c} ({_nw_c})',
                                    'Log': line.strip(),
                                })

                        # ── Registration from +CREG / +CEREG / +CGREG ──
                        _m_creg_c = rx_creg_val.search(_cat_content)
                        if _m_creg_c:
                            _stat_c = int(_m_creg_c.group(1))
                            _lac_c = _m_creg_c.group(2)
                            _ci_c = _m_creg_c.group(3)
                            _act_c2 = int(_m_creg_c.group(4)) if _m_creg_c.group(4) else None
                            if _stat_c != current_creg_state:
                                current_creg_state = _stat_c
                                _sn = CREG_STATES.get(_stat_c, f'Unknown({_stat_c})')
                                _nwn = NETWORK_ACT.get(_act_c2, '') if _act_c2 is not None else ''
                                if _nwn: current_network_type = _nwn
                                _det = _sn
                                if _lac_c: _det += f' LAC:{_lac_c}'
                                if _ci_c: _det += f' CID:{_ci_c}'
                                if _nwn: _det += f' [{_nwn}]'
                                events.append({
                                    'LineNum': i + 1, 'Timestamp': _cat_ts,
                                    'Type': 'Network', 'Value': _sn,
                                    'Details': _det, 'Log': line.strip(),
                                })

                        # ── Socket status from +CIPSTATUS ──
                        _m_cip = rx_cipstatus_val.search(_cat_content)
                        if _m_cip:
                            device_identity.setdefault('sockets', [])

                        # Clear pending command after OK/ERROR (end of transaction)
                        if _cat_content.upper() in ('OK', 'ERROR') \
                                or _cat_content.upper().startswith('+CME ERROR') \
                                or _cat_content.upper().startswith('+CMS ERROR'):
                            _last_at_cmd_base = ''

                    _cat_c, _desc_c = classify_at_command(_cat_content)
                    modem_info['at_commands'].append({
                        'Timestamp': _cat_ts, 'Direction': _cat_dir,
                        'Content': _cat_content, 'LineNum': i + 1,
                        'Category': _cat_c, 'Description': _desc_c,
                        'Group': _at_group_counter,
                    })

        # 9. Record Sending State Changes
        # 9a. Text-based CHANGE.STATE transitions (preferred, more readable)
        _rs_matched = False
        _m_cs = rx_rec_send_change.search(line)
        if _m_cs:
            _rs_matched = True
            ts_rs, rs_task, _cs_line, rs_server, old_name, new_name = _m_cs.groups()
            old_name = old_name.strip()
            new_name = new_name.strip()
            events.append({
                'LineNum': i + 1, 'Timestamp': resolve_ts(line, ts_rs),
                'Type': 'Record Sending', 'Value': new_name,
                'Details': f'RS{rs_task} Srv{rs_server}: {old_name} \u2192 {new_name}',
                'Log': line.strip()
            })

        # 9b. Numeric state transitions (fallback for older formats)
        if not _rs_matched:
            match_rec = rx_rec_send.search(line)
            if match_rec:
                _rs_matched = True
                ts_rs, server, old_s, new_s = match_rec.groups()
                old_si, new_si = int(old_s), int(new_s)
                old_name = REC_SEND_STATES.get(old_si, str(old_si))
                new_name = REC_SEND_STATES.get(new_si, str(new_si))
                events.append({
                    'LineNum': i + 1, 'Timestamp': resolve_ts(line, ts_rs),
                    'Type': 'Record Sending', 'Value': new_name,
                    'Details': f'RS{server} Srv{server}: {old_name} \u2192 {new_name}',
                    'Log': line.strip()
                })

        # 9c. Key record sending milestones
        if not _rs_matched and '[REC.SEND' in line:
            _m_ai = rx_rec_send_accepted_imei.search(line)
            if _m_ai:
                _rs_matched = True
                events.append({
                    'LineNum': i + 1, 'Timestamp': resolve_ts(line, _m_ai.group(1)),
                    'Type': 'Record Sending', 'Value': 'IMEI Accepted',
                    'Details': f'RS{_m_ai.group(2)}: Server accepted IMEI',
                    'Log': line.strip()
                })
            _m_ar = rx_rec_send_accepted_recs.search(line)
            if _m_ar:
                _rs_matched = True
                events.append({
                    'LineNum': i + 1, 'Timestamp': resolve_ts(line, _m_ar.group(1)),
                    'Type': 'Record Sending', 'Value': 'Records Accepted',
                    'Details': f'RS{_m_ar.group(2)}: Server accepted records',
                    'Log': line.strip()
                })
            _m_pk = rx_rec_send_packed.search(line)
            if _m_pk:
                _rs_matched = True
                events.append({
                    'LineNum': i + 1, 'Timestamp': resolve_ts(line, _m_pk.group(1)),
                    'Type': 'Record Sending', 'Value': f'Packed {_m_pk.group(3)}',
                    'Details': f'RS{_m_pk.group(2)}: {_m_pk.group(3)} records packed, waiting for ACK',
                    'Log': line.strip()
                })
            _m_st = rx_rec_send_sent.search(line)
            if _m_st:
                _rs_matched = True
                events.append({
                    'LineNum': i + 1, 'Timestamp': resolve_ts(line, _m_st.group(1)),
                    'Type': 'Record Sending', 'Value': f'Sent {_m_st.group(3)}/{_m_st.group(4)}',
                    'Details': f'RS{_m_st.group(2)}: Sent {_m_st.group(3)} records (min required {_m_st.group(4)})',
                    'Log': line.strip()
                })
            _m_sp = rx_rec_send_starting.search(line)
            if _m_sp:
                _rs_matched = True
                events.append({
                    'LineNum': i + 1, 'Timestamp': resolve_ts(line, _m_sp.group(1)),
                    'Type': 'Record Sending', 'Value': 'Starting Send',
                    'Details': f'RS{_m_sp.group(2)}: Starting periodic data sending',
                    'Log': line.strip()
                })
            _m_en = rx_rec_send_enough.search(line)
            if _m_en:
                _rs_matched = True
                events.append({
                    'LineNum': i + 1, 'Timestamp': resolve_ts(line, _m_en.group(1)),
                    'Type': 'Record Sending', 'Value': 'Enough Records',
                    'Details': f'RS{_m_en.group(2)}: Have enough records to send',
                    'Log': line.strip()
                })
            _m_lt = rx_rec_send_link_tmo.search(line)
            if _m_lt:
                _rs_matched = True
                events.append({
                    'LineNum': i + 1, 'Timestamp': resolve_ts(line, _m_lt.group(1)),
                    'Type': 'Record Sending', 'Value': 'Link Timeout',
                    'Details': f'RS{_m_lt.group(2)}: Link timeout on server {_m_lt.group(3)} \u2192 closing',
                    'Log': line.strip()
                })

        # 9b. Record Generation — multiline accumulator
        # The firmware prints a multiline block starting with [REC.GEN] Record Content:
        # followed by GPS fields, IO IDs, Record Size, then a summary line.
        # We accumulate all lines until the block ends (Record Size or save-queued line).

        # Check for "Record Content:" to start accumulation
        if rx_rec_content_start.search(line):
            # Flush any previous incomplete record
            if _rec_accumulating and _rec_current:
                modem_info['records'].append(_rec_current)
            _rec_accumulating = True
            _rec_start_line = i + 1
            _rec_current = {
                'LineNum': i + 1,
                'Timestamp': resolve_ts(line, last_timestamp_str),
                'RecTimestamp': None,
                'Priority': None,
                'Latitude': None, 'Longitude': None,
                'Altitude': None, 'Angle': None,
                'Speed': None, 'HDOP': None,
                'SatInUse': None, 'GPSFix': None,
                'GSpeed': None, 'GSpeedSrc': None,
                'EventAVLID': None,
                'IOs': {},          # {avl_id_int: value_str}
                'RecordSize': None,
                'RecType': None,    # Eventual / Periodic
                'RecPriority': None, # none/low/high/panic
            }

        # While accumulating, parse fields from continuation lines
        if _rec_accumulating and _rec_current:
            # Timestamp (record epoch)
            _m = rx_rec_timestamp.search(line)
            if _m: _rec_current['RecTimestamp'] = int(_m.group(1))
            
            # Priority
            _m = rx_rec_priority.search(line)
            if _m: _rec_current['Priority'] = int(_m.group(1))
            
            # GPS fields
            _m = rx_rec_latitude.search(line)
            if _m: _rec_current['Latitude'] = float(_m.group(1))
            _m = rx_rec_longitude.search(line)
            if _m: _rec_current['Longitude'] = float(_m.group(1))
            _m = rx_rec_altitude.search(line)
            if _m: _rec_current['Altitude'] = int(_m.group(1))
            _m = rx_rec_angle.search(line)
            if _m: _rec_current['Angle'] = int(_m.group(1))
            _m = rx_rec_speed.search(line)
            if _m: _rec_current['Speed'] = int(_m.group(1))
            _m = rx_rec_hdop.search(line)
            if _m: _rec_current['HDOP'] = float(_m.group(1))
            _m = rx_rec_sat.search(line)
            if _m: _rec_current['SatInUse'] = int(_m.group(1))
            _m = rx_rec_fix.search(line)
            if _m: _rec_current['GPSFix'] = int(_m.group(1))
            _m = rx_rec_gspeed.search(line)
            if _m:
                _rec_current['GSpeed'] = int(_m.group(1))
                _rec_current['GSpeedSrc'] = _m.group(2)
            
            # Event AVL ID
            _m = rx_avl_id.search(line)
            if _m: _rec_current['EventAVLID'] = int(_m.group(1))
            
            # IO elements
            _m = rx_rec_io.search(line)
            if _m:
                _io_id = int(_m.group(1))
                _io_val = _m.group(2).strip().strip('"')
                _rec_current['IOs'][_io_id] = _io_val
            
            # Record Size — marks the end of the content block
            _m = rx_rec_size.search(line)
            if _m:
                _rec_current['RecordSize'] = int(_m.group(1))

        # Record save-queued line: "Eventual/Periodic <prio> priority record save queued"
        _m_save = rx_rec_save.search(line)
        if _m_save:
            _ts_save = _m_save.group(1)
            _rec_type = _m_save.group(2)   # Eventual / Periodic
            _rec_prio = _m_save.group(3)   # none / low / high / panic
            
            if _rec_accumulating and _rec_current:
                _rec_current['RecType'] = _rec_type
                _rec_current['RecPriority'] = _rec_prio
                _rec_current['Timestamp'] = resolve_ts(line, _ts_save)
                modem_info['records'].append(_rec_current)
                
                # Also emit a summary event
                _io_count = len(_rec_current['IOs'])
                _avl = _rec_current.get('EventAVLID', '?')
                _sz = _rec_current.get('RecordSize', '?')
                _spd = _rec_current.get('Speed', 0)
                _fix = 'Fix' if _rec_current.get('GPSFix') == 1 else 'NoFix'
                _io_ids = ', '.join(str(k) for k in sorted(_rec_current['IOs'].keys())) if _rec_current['IOs'] else 'none'
                events.append({
                    'LineNum': _rec_start_line,
                    'Timestamp': resolve_ts(line, _ts_save),
                    'Type': 'Record Generation',
                    'Value': f'{_rec_type} ({_rec_prio})',
                    'Details': f'AVL:{_avl} | {_fix} | Spd:{_spd} | IOs:[{_io_ids}] | {_sz}B',
                    'Log': line.strip()
                })
                _rec_accumulating = False
                _rec_current = None
            else:
                # Save-queued line without a preceding content block (unusual but handle it)
                events.append({
                    'LineNum': i + 1,
                    'Timestamp': resolve_ts(line, _ts_save),
                    'Type': 'Record Generation',
                    'Value': f'{_rec_type} ({_rec_prio})',
                    'Details': f'{_rec_type} {_rec_prio} record save queued',
                    'Log': line.strip()
                })
        elif not _m_save and _rec_accumulating and _rec_current:
            # Check if we've gone too far without closing (safety: 80 lines max)
            if (i + 1 - _rec_start_line) > 80:
                modem_info['records'].append(_rec_current)
                _rec_accumulating = False
                _rec_current = None

        # 10. Modem State Changes
        match_modem = rx_modem_change.search(line)
        if match_modem:
            ts_mc, old_st, new_st = match_modem.groups()
            events.append({
                'LineNum': i + 1, 'Timestamp': resolve_ts(line, ts_mc),
                'Type': 'Modem', 'Value': new_st,
                'Details': f'{old_st} \u2192 {new_st}', 'Log': line.strip()
            })

        # 11. MODEM.STATUS block field extraction
        m_op = rx_status_operator.search(line)
        if m_op:
            new_op = m_op.group(1)
            # Flush previous snapshot if it has signal data
            if _status_snapshot and ('csq' in _status_snapshot or 'rsrp_dbm' in _status_snapshot):
                modem_info['signal_readings'].append({
                    'Timestamp': resolve_ts(line, last_timestamp_str),
                    'CSQ': _status_snapshot.get('csq'),
                    'RSSI_dBm': _status_snapshot.get('rssi_dbm'),
                    'RSRP_dBm': _status_snapshot.get('rsrp_dbm'),
                    'SINR_dB': _status_snapshot.get('sinr_db'),
                    'RSRQ_dB': _status_snapshot.get('rsrq_db'),
                    'Network': _status_snapshot.get('network', current_network_type),
                })
            _status_snapshot = {'operator': new_op}
            if new_op != current_operator and new_op != '0':
                current_operator = new_op
                events.append({
                    'LineNum': i + 1, 'Timestamp': resolve_ts(line, last_timestamp_str),
                    'Type': 'Operator', 'Value': new_op,
                    'Details': f'Status Report: {new_op}', 'Log': line.strip()
                })

        m_csq_s = rx_status_csq.search(line)
        if m_csq_s:
            csq = int(m_csq_s.group(1))
            _status_snapshot['csq'] = csq
            if csq < 99: _status_snapshot['rssi_dbm'] = -113 + (csq * 2)
        m_rsrp_s = rx_status_rsrp.search(line)
        if m_rsrp_s: _status_snapshot['rsrp_dbm'] = int(m_rsrp_s.group(1))
        m_sinr_s = rx_status_sinr.search(line)
        if m_sinr_s: _status_snapshot['sinr_db'] = float(m_sinr_s.group(1))
        m_rsrq_s = rx_status_rsrq.search(line)
        if m_rsrq_s: _status_snapshot['rsrq_db'] = float(m_rsrq_s.group(1))
        m_nw_s = rx_status_network.search(line)
        if m_nw_s:
            _status_snapshot['network'] = m_nw_s.group(1)
            current_network_type = m_nw_s.group(1)
        m_band_s = rx_status_band.search(line)
        if m_band_s: _status_snapshot['band'] = int(m_band_s.group(1))

        # 11b. MODEM.STATUS IMSI / CCID extraction
        m_imsi_s = rx_status_imsi.search(line)
        if m_imsi_s and 'imsi' not in device_identity:
            device_identity['imsi'] = m_imsi_s.group(1)
        m_ccid_s = rx_status_ccid.search(line)
        if m_ccid_s and 'iccid' not in device_identity:
            device_identity['iccid'] = m_ccid_s.group(1)

        # 11c. [SYS.DIAG] block identity extraction
        m_diag_imei = rx_diag_imei.search(line)
        if m_diag_imei:
            device_identity['imei'] = m_diag_imei.group(1)
        m_diag_hw = rx_diag_hw_ver.search(line)
        if m_diag_hw and 'hw_ver' not in device_identity:
            device_identity['hw_ver'] = m_diag_hw.group(1)
        m_diag_hw_mod = rx_diag_hw_mod.search(line)
        if m_diag_hw_mod and 'hw_mod' not in device_identity:
            device_identity['hw_mod'] = m_diag_hw_mod.group(1)
        m_diag_cv = rx_diag_code_ver.search(line)
        if m_diag_cv and 'fw_version' not in device_identity:
            device_identity['fw_version'] = m_diag_cv.group(1)
        m_diag_cr = rx_diag_code_rev.search(line)
        if m_diag_cr and 'fw_revision' not in device_identity:
            device_identity['fw_revision'] = m_diag_cr.group(1)
        m_diag_bl = rx_diag_bl_ver.search(line)
        if m_diag_bl and 'bl_ver' not in device_identity:
            device_identity['bl_ver'] = m_diag_bl.group(1)

        # 11d. Modem type from FMBS payload or explicit log line
        m_modem_fw = rx_modem_fw.search(line)
        if m_modem_fw and 'modem_type' not in device_identity:
            device_identity['modem_type'] = m_modem_fw.group(1)
        m_modem_t = rx_modem_type_line.search(line)
        if m_modem_t and 'modem_type' not in device_identity:
            device_identity['modem_type'] = m_modem_t.group(1)

        # 12. GPRS events
        match_gprs = rx_gprs_ev.search(line)
        if match_gprs:
            ts_gp, msg_gp = match_gprs.groups()
            msg_gp = msg_gp.strip()
            if any(kw in msg_gp.lower() for kw in ['open', 'close', 'error', 'fail', 'attach', 'detach']):
                events.append({
                    'LineNum': i + 1, 'Timestamp': resolve_ts(line, ts_gp),
                    'Type': 'GPRS', 'Value': msg_gp[:30],
                    'Details': msg_gp, 'Log': line.strip()
                })

        # 13. Raw -[TAG] format (backwards compat with non-Catcher logs)
        if not match_at_cmd and not match_at_rsp:
            match_raw = rx_raw_tag.search(line)
            if match_raw:
                raw_tag, raw_msg = match_raw.groups()
                if raw_tag in ('ATCMD', 'MDM.QTL', 'AT.RSP', 'MODEM', 'MODEM.ST', 'MODEM.ACTION'):
                    _rt_dir = 'CMD' if raw_tag == 'ATCMD' else 'RSP' if raw_tag == 'AT.RSP' else 'INFO'
                    _rt_content = f'[{raw_tag}] {raw_msg.strip()}'
                    _rt_cat, _rt_desc = classify_at_command(raw_msg.strip())
                    modem_info['at_commands'].append({
                        'Timestamp': resolve_ts(line, last_timestamp_str),
                        'Direction': _rt_dir, 'Content': _rt_content,
                        'LineNum': i + 1,
                        'Category': _rt_cat, 'Description': _rt_desc,
                        'Group': _at_group_counter,
                    })

    # Flush remaining MODEM.STATUS snapshot
    if _status_snapshot and ('csq' in _status_snapshot or 'rsrp_dbm' in _status_snapshot):
        modem_info['signal_readings'].append({
            'Timestamp': resolve_ts('', last_timestamp_str),
            'CSQ': _status_snapshot.get('csq'),
            'RSSI_dBm': _status_snapshot.get('rssi_dbm'),
            'RSRP_dBm': _status_snapshot.get('rsrp_dbm'),
            'SINR_dB': _status_snapshot.get('sinr_db'),
            'RSRQ_dB': _status_snapshot.get('rsrq_db'),
            'Network': _status_snapshot.get('network', current_network_type),
        })

    # Flush remaining incomplete record accumulator
    if _rec_accumulating and _rec_current:
        modem_info['records'].append(_rec_current)

    # Sort events by timestamp
    events.sort(key=lambda x: x.get('Timestamp', ''))

    return data_points, events, structured_logs, modem_info

def create_map(data):
    if not data: return None
    
    start_loc = data[0]['loc']
    m = folium.Map(location=start_loc, zoom_start=15, tiles="CartoDB positron")

    # Static Path
    path_coords = [d['loc'] for d in data]
    folium.PolyLine(path_coords, color="lightgray", weight=3, opacity=0.5).add_to(m)

    features = []
    
    for point in data:
        # Use existing logic, but current_ignition is now more accurate from TRIP logs
        color = get_marker_color(point['speed'], point['ignition'])
        
        feature = {
            'type': 'Feature',
            'geometry': {
                'type': 'Point',
                'coordinates': [point['loc'][1], point['loc'][0]], 
            },
            'properties': {
                'time': point['time_iso'],
                'style': {'color': color},
                'icon': 'circle',
                'iconstyle': {
                    'fillColor': color,
                    'fillOpacity': 1,
                    'stroke': 'false',
                    'radius': 6
                },
                'popup': f"<b>{point['speed_str']}</b><br>Ignition: {point['ignition']}"
            }
        }
        features.append(feature)

    TimestampedGeoJson(
        {'type': 'FeatureCollection', 'features': features},
        period='PT1S', 
        duration='PT1S', 
        transition_time=200,
        auto_play=False,
        loop=False,
        max_speed=10,
        loop_button=True,
        date_options='YYYY/MM/DD HH:mm:ss',
        time_slider_drag_update=True
    ).add_to(m)

    legend_html = '''
     <div style="position: fixed; 
     bottom: 50px; right: 50px; width: 150px; height: 90px; 
     border:2px solid grey; z-index:9999; font-size:12px;
     background-color:white; opacity: 0.8; padding: 10px; color: black;">
       <b>Status Legend</b><br>
       <i style="background:#00FF00;width:10px;height:10px;display:inline-block;border-radius:50%"></i> Moving (>5km/h)<br>
       <i style="background:#FF8C00;width:10px;height:10px;display:inline-block;border-radius:50%"></i> Idling (Ign ON)<br>
       <i style="background:#000000;width:10px;height:10px;display:inline-block;border-radius:50%"></i> Parked (Ign OFF)
     </div>
     '''
    m.get_root().html.add_child(folium.Element(legend_html))

    css_fix = '''
    <style>
        .time-control-speed { margin-right: 30px !important; }
    </style>
    '''
    m.get_root().html.add_child(folium.Element(css_fix))
    
    return m

def create_timeline(events):
    if not events:
        return None
        
    df_events = pd.DataFrame(events)
    if df_events.empty:
        return None

    # Consistent Color Map
    color_map = {
        'Ignition': '#FFA500',   # Orange
        'Movement': '#00FF00',   # Green
        'GPS State': '#0000FF',  # Blue
        'No Fix Reason': '#FF0000', # Red
        'Sleep Mode': '#4682B4',   # SteelBlue
        'Static Navigation': '#800080', # Purple
        'Trip Status': '#8A2BE2', # BlueViolet
        'Network': '#20B2AA',    # LightSeaGreen
        'Operator': '#DAA520',   # Goldenrod
        'Record Sending': '#DC143C', # Crimson
        'Record Generation': '#FF69B4', # HotPink
        'Modem': '#708090',      # SlateGray
        'GPRS': '#FF6347',       # Tomato
    }

    # Clean and convert Timestamp
    try:
        df_events['Timestamp'] = pd.to_datetime(df_events['Timestamp'], format='%Y/%m/%d %H:%M:%S:%f', errors='coerce')
        df_events = df_events.dropna(subset=['Timestamp'])
    except Exception as e:
        pass

    if df_events.empty:
        return None

    # Use graph_objects for better performance with large datasets (WebGL)
    fig = go.Figure()
    
    # Group by Type to assign colors and maintain legend
    for event_type, group in df_events.groupby("Type"):
        color = color_map.get(event_type, '#888888')
        
        # Create hover text
        hover_text = (
            "<b>" + group["Type"] + "</b><br>" +
            "Value: " + group["Value"].astype(str) + "<br>" +
            "Details: " + group["Details"].astype(str) + "<br>" +
            "Time: " + group["Timestamp"].dt.strftime('%H:%M:%S.%f').str[:-3] + "<br>" +
            "Line: " + group["LineNum"].astype(str)
        )

        fig.add_trace(go.Scattergl(
            x=group["Timestamp"],
            y=group["Type"],
            mode='markers',
            marker=dict(
                color=color,
                size=10,
                line=dict(width=1, color='DarkSlateGrey')
            ),
            name=event_type,
            text=hover_text,
            hoverinfo="text",
            customdata=group[["Log", "Details", "Value", "LineNum"]],
        ))

    fig.update_layout(
        title="Event Timeline",
        xaxis_title=None,
        yaxis_title=None,
        legend_title=None,
        xaxis=dict(
            rangeslider=dict(visible=True, thickness=0.1),
            type="date"
        ),
        margin=dict(l=20, r=20, t=40, b=20),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1
        ),
        hovermode="closest", # x unified can be heavy with many points
        height=500
    )
    
    return fig


def create_signal_chart(signal_readings):
    """Create a signal strength chart from parsed signal data."""
    if not signal_readings:
        return None

    df = pd.DataFrame(signal_readings)
    df['Timestamp'] = pd.to_datetime(df['Timestamp'], format='%Y/%m/%d %H:%M:%S:%f', errors='coerce')
    df = df.dropna(subset=['Timestamp']).sort_values('Timestamp')
    if df.empty:
        return None

    fig = make_subplots(specs=[[{"secondary_y": True}]])
    has_rsrp = df['RSRP_dBm'].notna().any()

    # RSRP (primary metric for LTE)
    if has_rsrp:
        fig.add_trace(go.Scatter(
            x=df.loc[df['RSRP_dBm'].notna(), 'Timestamp'],
            y=df.loc[df['RSRP_dBm'].notna(), 'RSRP_dBm'],
            mode='lines+markers', name='RSRP (dBm)',
            line=dict(color='#1f77b4', width=2), marker=dict(size=4),
        ), secondary_y=False)

    # SINR
    if df['SINR_dB'].notna().any():
        fig.add_trace(go.Scatter(
            x=df.loc[df['SINR_dB'].notna(), 'Timestamp'],
            y=df.loc[df['SINR_dB'].notna(), 'SINR_dB'],
            mode='lines+markers', name='SINR (dB)',
            line=dict(color='#2ca02c', width=1, dash='dot'), marker=dict(size=3),
        ), secondary_y=True)

    # RSRQ
    if df['RSRQ_dB'].notna().any():
        fig.add_trace(go.Scatter(
            x=df.loc[df['RSRQ_dB'].notna(), 'Timestamp'],
            y=df.loc[df['RSRQ_dB'].notna(), 'RSRQ_dB'],
            mode='lines+markers', name='RSRQ (dB)',
            line=dict(color='#9467bd', width=1, dash='dash'), marker=dict(size=3),
        ), secondary_y=False)

    # CSQ (if no RSRP available, show on primary)
    if df['CSQ'].notna().any():
        fig.add_trace(go.Scatter(
            x=df.loc[df['CSQ'].notna(), 'Timestamp'],
            y=df.loc[df['CSQ'].notna(), 'CSQ'],
            mode='lines+markers', name='CSQ (0-31)',
            line=dict(color='#ff7f0e', width=2), marker=dict(size=4),
        ), secondary_y=not has_rsrp)

    fig.update_layout(
        height=300, margin=dict(l=20, r=20, t=10, b=20),
        legend=dict(orientation="h", y=1.15, font=dict(size=10)),
        hovermode="x unified",
        xaxis=dict(rangeslider=dict(visible=True, thickness=0.08)),
    )
    fig.update_yaxes(title_text="dBm" if has_rsrp else "CSQ", secondary_y=False)
    fig.update_yaxes(title_text="SINR (dB)", secondary_y=True)

    return fig


def create_state_timeline(events):
    """Create a swimlane/Gantt-style state timeline showing device state durations."""
    if not events:
        return None

    STATE_COLORS = {
        # Ignition
        'ON': '#FF8C00', 'OFF': '#555555',
        # GPS
        'Fix Acquired': '#00CC00', 'Lost Fix': '#CC0000',
        # Sleep
        'Enter': '#4682B4', 'Exit': '#87CEEB', 'WakeUp Send': '#B0C4DE',
        # Trip
        'START': '#7B68EE', 'Moving': '#9370DB', 'Stop': '#D8BFD8', 'END': '#DDA0DD',
        # Network
        'Home': '#20B2AA', 'Roaming': '#FFD700', 'Searching': '#FF6347',
        'Denied': '#DC143C', 'Not Registered': '#808080',
        # Record Sending
        'Idle': '#DCDCDC', 'Sending': '#DC143C', 'Check Link': '#FF8C00',
        'Check GPRS': '#FFA500', 'IMEI Handshake': '#FF6347',
        'Done': '#90EE90', 'Error/Finish': '#B22222', 'Check Recs': '#FFB6C1',
        'Continue': '#E9967A', 'Flush': '#F08080', 'Close GPRS': '#CD853F',
        # Record Sending (text-based state names from CHANGE.STATE)
        'check rec no': '#FFB6C1', 'check gprs': '#FFA500', 'check link': '#FF8C00',
        'send imei': '#FF6347', 'send records': '#DC143C', 'send records cont': '#E9967A',
        'waiting': '#DAA520', 'finish': '#B22222', 'finished': '#90EE90',
        # Record Sending milestones
        'IMEI Accepted': '#20B2AA', 'Records Accepted': '#228B22',
        'Starting Send': '#7B68EE', 'Enough Records': '#9370DB',
        'Link Timeout': '#B22222',
        # Modem
        'READY': '#228B22', 'INIT': '#DAA520', 'UNAV': '#B22222', 'PROT': '#808080',
    }

    SWIMLANE_TYPES = ['Ignition', 'GPS State', 'Sleep Mode', 'Network',
                      'Record Sending', 'Trip Status', 'Modem']

    df_events = pd.DataFrame(events)
    if df_events.empty:
        return None

    df_events['Timestamp'] = pd.to_datetime(
        df_events['Timestamp'], format='%Y/%m/%d %H:%M:%S:%f', errors='coerce')
    df_events = df_events.dropna(subset=['Timestamp']).sort_values('Timestamp')
    if df_events.empty:
        return None

    log_end = df_events['Timestamp'].max()
    gantt_dfs = []

    for stype in SWIMLANE_TYPES:
        type_df = df_events[df_events['Type'] == stype].sort_values('Timestamp').copy()
        if type_df.empty:
            continue
        
        # Vectorized end-time calculation
        type_df['Start'] = type_df['Timestamp']
        type_df['End'] = type_df['Start'].shift(-1).fillna(log_end)
        
        # Fix zero duration events
        mask = type_df['End'] == type_df['Start']
        type_df.loc[mask, 'End'] = type_df.loc[mask, 'End'] + pd.Timedelta(seconds=1)
        
        type_df['Category'] = stype
        type_df['State'] = type_df['Value'].astype(str)
        
        gantt_dfs.append(type_df[['Category', 'Start', 'End', 'State', 'Details']])

    if not gantt_dfs:
        return None

    df_gantt = pd.concat(gantt_dfs)

    fig = px.timeline(
        df_gantt, x_start='Start', x_end='End', y='Category', color='State',
        color_discrete_map=STATE_COLORS,
        hover_data={'Details': True, 'State': True, 'Category': False},
        height=max(250, len(set(df_gantt['Category'])) * 55 + 80),
    )

    fig.update_layout(
        margin=dict(l=20, r=20, t=10, b=20),
        legend=dict(orientation="h", y=1.15, font=dict(size=10)),
        xaxis=dict(rangeslider=dict(visible=True, thickness=0.08), type="date"),
        yaxis=dict(autorange="reversed", title=None),
        hovermode="closest",
    )

    return fig