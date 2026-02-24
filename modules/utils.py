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

def parse_log(content_str):
    data_points = []
    events = []
    structured_logs = []
    modem_info = {
        'signal_readings': [],
        'at_commands': [],
    }
    
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
    rx_gprs_ev = re.compile(r'(\d{2}:\d{2}:\d{2}:\d{3}).*?\[GPRS\.CMD\]\s+(.*)')
    rx_modem_change = re.compile(r'(\d{2}:\d{2}:\d{2}:\d{3}).*?\[MODEM\].*?[Ss]tate.*?changed.*?(\w+)\s*->\s*(\w+)')
    rx_status_operator = re.compile(r'GSM Operator\s*:\s*(\d+)')
    rx_status_csq = re.compile(r'CSQ \(rssi\)\s*:\s*(\d+)')
    rx_status_rsrp = re.compile(r'QCSQ \(rsrp\)\s*:\s*([-\d]+)')
    rx_status_sinr = re.compile(r'QCSQ \(sinr\)\s*:\s*([-\d.]+)')
    rx_status_rsrq = re.compile(r'QCSQ \(rsrq\)\s*:\s*([-\d.]+)')
    rx_status_network = re.compile(r'Network Type\s*:\s*\d+/(\w+)')
    rx_status_band = re.compile(r'Current LTE BAND\s*:\s*(\d+)')
    rx_raw_tag = re.compile(r'-\[(.*?)\]\s+(.*)')

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

    # Default date
    current_date_str = datetime.now().strftime('%Y/%m/%d')
    
    def resolve_ts(line_content, time_str):
        # Uses current_date_str from outer scope which is updated in the loop
        return f"{current_date_str} {time_str}"

    lines = content_str.splitlines()
    
    last_timestamp_str = "00:00:00:000"
    
    # Pre-compiled empty values for performance
    last_parsed_time = None
    last_parsed_module = ""
    last_parsed_level = ""

    for i, line in enumerate(lines):
        line = line.strip()
        if not line: continue
            
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

        # B. Trip Periodic Info
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

        # C. Trip Start/End
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
            
        # D. Other Trip Events
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

        match_dist = rx_trip_dist.search(line)
        if match_dist:
            ts, dist = match_dist.groups()
            # Optional: Filter out 0km if too noisy, but user asked for it
            events.append({
                'LineNum': i + 1,
                'Timestamp': resolve_ts(line, ts),
                'Type': 'Trip Info',
                'Value': 'Distance',
                'Details': f'{dist} km',
                'Log': line.strip()
            })

        # 1b. Movement Detection (Delayed)
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

        # 2. Voltage Check (Fallback if TRIP logs missing)
        # Only runs if we haven't seen a TRIP line recently (simplified logic: check anyway)
        match_lipo = rx_lipo.search(line)
        if match_lipo:
            # Pass
            pass

        # 3a. Explicit GPS Status Change (Priority)
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

        # 3b. Check GPS Internal State (Periodic)
        # We use this to sync state for NoFix reason logic, but we no longer generate events
        # from this periodic message to avoid noise/duplication with the explicit change event.
        match_state = rx_gps_state.search(line)
        if match_state:
            ts, state = match_state.groups()
            state = int(state)
            
            # Sync state if we missed the start
            if last_fix_state == -1:
                last_fix_state = state
            
            # Commented out: Periodic update event generation
            # if state != last_fix_state:
            #     last_fix_state = state
            #     events.append({
            #         'LineNum': i + 1,
            #         'Timestamp': resolve_ts(line, ts),
            #         'Type': 'GPS State', 
            #         'Value': 'Fix Acquired' if state == 1 else 'Lost Fix',
            #         'Details': 'Internal GNSS (Periodic)'
            #     })

        # 4. Check No Fix Reason Code
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
                if code > 0: # We might check last_fix_state == 0 but sometimes logs are async
                    reasons = gps_codes.decode_reason(code)
                    events.append({
                        'LineNum': i + 1,
                        'Timestamp': final_ts,
                        'Type': 'No Fix Reason',
                        'Value': f'Code {code}',
                        'Details': ", ".join(reasons),
                        'Log': line.strip()
                    })

        # 5. Static Navigation
        match_static = rx_static_nav.search(line)
        if match_static:
            dt_full, full_msg, state_keyword = match_static.groups()
            # Timestamp example: 2026.01.13 06:12:39
            # Normalize to match our other timestamps: YYYY/MM/DD HH:MM:SS:000
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

        # 6. Standard NMEA Parsing
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

        # 8. AT Commands & Responses
        match_at_cmd = rx_at_cmd.search(line)
        if match_at_cmd:
            ts_ac, cmd = match_at_cmd.groups()
            modem_info['at_commands'].append({
                'Timestamp': resolve_ts(line, ts_ac), 'Direction': 'CMD',
                'Content': cmd.strip().strip('"'), 'LineNum': i + 1
            })

        match_at_rsp = rx_at_rsp.search(line)
        if match_at_rsp:
            ts_ar, rsp = match_at_rsp.groups()
            rsp = rsp.strip().strip('"')
            modem_info['at_commands'].append({
                'Timestamp': resolve_ts(line, ts_ar), 'Direction': 'RSP',
                'Content': rsp, 'LineNum': i + 1
            })
            # Extract signal from +CSQ
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

        # 9. Record Sending State Changes
        match_rec = rx_rec_send.search(line)
        if match_rec:
            ts_rs, server, old_s, new_s = match_rec.groups()
            old_si, new_si = int(old_s), int(new_s)
            old_name = REC_SEND_STATES.get(old_si, str(old_si))
            new_name = REC_SEND_STATES.get(new_si, str(new_si))
            events.append({
                'LineNum': i + 1, 'Timestamp': resolve_ts(line, ts_rs),
                'Type': 'Record Sending', 'Value': new_name,
                'Details': f'Server {server}: {old_name} \u2192 {new_name}',
                'Log': line.strip()
            })

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
                    modem_info['at_commands'].append({
                        'Timestamp': resolve_ts(line, last_timestamp_str),
                        'Direction': 'CMD' if raw_tag == 'ATCMD' else 'RSP' if raw_tag == 'AT.RSP' else 'INFO',
                        'Content': f'[{raw_tag}] {raw_msg.strip()}', 'LineNum': i + 1
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
        'Modem': '#708090',      # SlateGray
        'GPRS': '#FF6347',       # Tomato
    }

    # Clean and convert Timestamp
    # The timestamps from the logger are like "2026/01/26 13:16:11:148"
    # We need to replace the last colon with a dot for milliseconds parsing, or use a custom format
    try:
        # Replace the last colon with a dot if it looks like milliseconds
        # Or just tell pandas the format: %Y/%m/%d %H:%M:%S:%f
        df_events['Timestamp'] = pd.to_datetime(df_events['Timestamp'], format='%Y/%m/%d %H:%M:%S:%f', errors='coerce')
        
        # Fallback for other formats (like Static Nav might have slightly different one)
        if df_events['Timestamp'].isnull().any():
             # Try a more generic parse for failed rows (e.g. Static Nav might lack ms or use dots)
             # The failed entries are currently NaT, so we can't get the original string easily from the column
             # But usually the main format covers 99% of cases. 
             # If needed, we can rely on Plotly's string parsing if we don't convert to datetime,
             # but we need datetime for the range slider to work well.
             pass

        # Drop rows where timestamp parsing failed completely
        df_events = df_events.dropna(subset=['Timestamp'])
        
    except Exception as e:
        # Fallback: simple conversion (might lose milliseconds or fallback to string)
        pass

    fig = px.scatter(
        df_events, 
        x="Timestamp", 
        y="Type", 
        color="Type", 
        symbol="Type", # Use Type for symbol to avoid 'Value' cardinality issues
        hover_data={"Value": True, "Details": True, "Log": False, "Type": False, "Timestamp": True, "LineNum": True}, 
        custom_data=["Log", "Details", "Value", "LineNum"], # Make Log available for click events
        title="Event Timeline",
        color_discrete_map=color_map,
        height=500, # Slightly taller
        opacity=0.9
    )

    fig.update_traces(marker=dict(size=10, line=dict(width=1, color='DarkSlateGrey')))
    
    fig.update_layout(
        xaxis_title=None, 
        yaxis_title=None, 
        legend_title=None,
        xaxis=dict(
            rangeslider=dict(visible=True, thickness=0.1), # Add Range Slider
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
        hovermode="x unified" # Easier comparison
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
    gantt_rows = []

    for stype in SWIMLANE_TYPES:
        type_df = df_events[df_events['Type'] == stype].sort_values('Timestamp')
        if type_df.empty:
            continue

        for idx in range(len(type_df)):
            row = type_df.iloc[idx]
            start = row['Timestamp']
            end = type_df.iloc[idx + 1]['Timestamp'] if idx + 1 < len(type_df) else log_end
            if start == end:
                end = start + pd.Timedelta(seconds=2)
            gantt_rows.append({
                'Category': stype, 'Start': start, 'End': end,
                'State': str(row['Value']),
                'Details': row.get('Details', ''),
            })

    if not gantt_rows:
        return None

    df_gantt = pd.DataFrame(gantt_rows)

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