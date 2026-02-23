import re
import pandas as pd
import plotly.express as px
import folium
from folium.plugins import TimestampedGeoJson
from datetime import datetime
from . import gps_codes

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

    # State Tracking
    current_ignition = False
    current_movement = False
    current_trip_state = None
    ignition_threshold = 13000 # 13V threshold if physical detection fails
    last_fix_state = -1
    
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

    # Sort events by timestamp
    events.sort(key=lambda x: x.get('Timestamp', ''))

    return data_points, events, structured_logs

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
        'Trip Status': '#8A2BE2' # BlueViolet
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
