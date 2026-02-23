"""
Teltonika GPS Server - Real-time device monitoring
"""

import streamlit as st
import time
import pandas as pd
import json
import os
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from server_app.teltonika_server import TeltonikaServer

# Page config
st.set_page_config(
    page_title="GPS Server",
    page_icon="📡",
    layout="wide"
)

st.title("📡 Teltonika GPS Server")

# Load configuration
def load_config():
    """Load configuration from toolkit_settings.json"""
    config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'toolkit_settings.json')
    default_config = {'tcp_port': 8000, 'udp_port': 8001}
    
    try:
        if os.path.exists(config_path):
            with open(config_path, 'r') as f:
                config = json.load(f)
                return {
                    'tcp_port': config.get('tcp_port', default_config['tcp_port']),
                    'udp_port': config.get('udp_port', default_config['udp_port'])
                }
    except Exception as e:
        st.warning(f"Could not load config: {e}. Using defaults.")
    
    return default_config

def save_config(tcp_port, udp_port):
    """Save configuration to toolkit_settings.json"""
    config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'toolkit_settings.json')
    
    try:
        # Load existing config
        config = {}
        if os.path.exists(config_path):
            with open(config_path, 'r') as f:
                config = json.load(f)
        
        # Update ports
        config['tcp_port'] = tcp_port
        config['udp_port'] = udp_port
        
        # Save
        with open(config_path, 'w') as f:
            json.dump(config, f, indent=4)
        
        return True
    except Exception as e:
        st.error(f"Could not save config: {e}")
        return False

# Initialize server in session state
if 'server' not in st.session_state:
    config = load_config()
    st.session_state.server = TeltonikaServer(
        tcp_port=config['tcp_port'], 
        udp_port=config['udp_port']
    )
    st.session_state.server.start()

server = st.session_state.server

# Sidebar controls
with st.sidebar:
    st.header("⚙️ Server Control")
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🔄 Restart", use_container_width=True):
            server.stop()
            time.sleep(0.5)
            server.start()
            st.success("Server restarted")
    
    with col2:
        if st.button("🗑️ Clear Data", use_container_width=True):
            with server.lock:
                server.parsed_records = []
                server.raw_messages = []
                server.log_messages = []
                server.command_history = []
            st.success("Data cleared")
    
    st.divider()
    
    st.header("📊 Statistics")
    with server.lock:
        st.metric("Records", len(server.parsed_records))
        st.metric("Commands", len(server.command_history))
        st.metric("Raw Messages", len(server.raw_messages))
        st.metric("Log Entries", len(server.log_messages))
    
    st.divider()
    
    st.header("⚙️ Port Settings")
    current_config = load_config()
    
    with st.form("port_settings"):
        tcp_port_input = st.number_input(
            "TCP Port", 
            min_value=1024, 
            max_value=65535, 
            value=current_config['tcp_port'],
            help="Port for TCP connections"
        )
        
        udp_port_input = st.number_input(
            "UDP Port", 
            min_value=1024, 
            max_value=65535, 
            value=current_config['udp_port'],
            help="Port for UDP connections"
        )
        
        submitted = st.form_submit_button("💾 Save & Restart", use_container_width=True)
        
        if submitted:
            if save_config(tcp_port_input, udp_port_input):
                st.success("Settings saved!")
                server.stop()
                time.sleep(0.5)
                # Recreate server with new ports
                st.session_state.server = TeltonikaServer(
                    tcp_port=tcp_port_input,
                    udp_port=udp_port_input
                )
                st.session_state.server.start()
                st.rerun()
    
    st.divider()
    
    st.header("🔌 Connected Devices")
    devices = server.get_connected_devices()
    if devices:
        for dev in devices:
            st.text(f"{dev['Protocol']}: {dev['IMEI']}")
    else:
        st.text("No devices connected")

# Main tabs
tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
    "📋 Live Data",
    "📨 Send Commands",
    "⏰ Schedule Commands",
    "🧪 Test Sequences",
    "🔁 Interval Commands",
    "📚 Command History",
    "📝 Raw Messages & Logs"
])

# Tab 1: Live Data
with tab1:
    st.header("Live GPS Data")
    
    # Show record details toggle
    show_details = st.checkbox("Show full record details (IO data)", value=False)
    
    with server.lock:
        records = server.parsed_records.copy()
    
    if records:
        if show_details:
            # Show full details including IO data
            display_records = []
            for rec in records:
                display_rec = rec.copy()
                # Convert IO_Data dict to string
                if 'IO_Data' in display_rec:
                    io_str = ", ".join([f"{k}={v}" for k, v in display_rec['IO_Data'].items()])
                    display_rec['IO_Data'] = io_str
                display_records.append(display_rec)
            
            df = pd.DataFrame(display_records)
            st.dataframe(df, use_container_width=True, height=600)
        else:
            # Show basic data only
            display_records = []
            for rec in records:
                display_rec = {
                    'IMEI': rec.get('IMEI', ''),
                    'Protocol': rec.get('Protocol', ''),
                    'Timestamp': rec.get('Timestamp', ''),
                    'Latitude': rec.get('Latitude', ''),
                    'Longitude': rec.get('Longitude', ''),
                    'Speed': rec.get('Speed', ''),
                    'Angle': rec.get('Angle', ''),
                    'Satellites': rec.get('Satellites', ''),
                    'Altitude': rec.get('Altitude', '')
                }
                display_records.append(display_rec)
            
            df = pd.DataFrame(display_records)
            st.dataframe(df, use_container_width=True, height=600)
    else:
        st.info("No records received yet")
    
    # Auto-refresh
    if st.button("🔄 Refresh"):
        st.rerun()

# Tab 2: Send Commands
with tab2:
    st.header("Send Commands to Device")
    
    devices = server.get_connected_devices()
    
    if devices:
        # Create device selection with protocol info
        device_options = [f"{d['IMEI']} ({d['Protocol']})" for d in devices]
        selected_device_str = st.selectbox(
            "Select Device",
            options=device_options
        )
        
        # Get selected device info
        selected_idx = device_options.index(selected_device_str)
        selected_device = devices[selected_idx]
        selected_imei = selected_device['IMEI']
        selected_protocol = selected_device['Protocol']
        
        command = st.text_input("Command", placeholder="e.g., getver, getgps, setparam 1:1")
        
        if st.button("📤 Send Command"):
            if command:
                # Auto-detect TCP or UDP
                success = server.send_command(selected_imei, command)
                
                if success:
                    st.success(f"✅ Command sent to {selected_imei}")
                else:
                    st.error("❌ Failed to send command - device not connected")
            else:
                st.warning("Please enter a command")
    else:
        st.warning("No devices connected")

# Tab 3: Schedule Commands
with tab3:
    st.header("Schedule Commands")
    st.write("Commands will be sent automatically when the device next connects or sends data.")
    
    schedule_imei = st.text_input("Device IMEI", key="schedule_imei")
    schedule_command = st.text_input("Command", key="schedule_command", placeholder="e.g., getver")
    
    if st.button("⏰ Schedule Command"):
        if schedule_imei and schedule_command:
            server.schedule_command(schedule_imei, schedule_command)
            st.success(f"Command scheduled for {schedule_imei}")
        else:
            st.warning("Please enter both IMEI and command")
    
    st.divider()
    st.subheader("Pending Scheduled Commands")
    
    with server.lock:
        scheduled = server.scheduled_commands.copy()
    
    if any(scheduled.values()):
        for imei, cmds in scheduled.items():
            if cmds:
                st.write(f"**{imei}:**")
                for cmd in cmds:
                    st.write(f"  - {cmd}")
    else:
        st.info("No pending commands")

# Tab 4: Test Sequences
with tab4:
    st.header("Test Command Sequences")
    st.write("Send the same command multiple times to a device.")
    
    devices = server.get_connected_devices()
    
    if devices:
        # Create device selection with protocol info
        device_options = [f"{d['IMEI']} ({d['Protocol']})" for d in devices]
        test_device_selection = st.selectbox(
            "Select Device",
            options=device_options,
            key="test_device"
        )
        
        # Get selected IMEI and protocol
        selected_idx = device_options.index(test_device_selection)
        selected_device = devices[selected_idx]
        test_imei = selected_device['IMEI']
        test_protocol = selected_device['Protocol']
        
        test_command = st.text_input("Command", key="test_command", placeholder="e.g., getver")
        test_count = st.number_input("Number of times to send", min_value=1, max_value=100, value=5)
        test_timeout = st.number_input("Response timeout (seconds)", min_value=1.0, max_value=60.0, value=10.0, step=1.0, 
                                       help="Maximum time to wait for response before sending next command")
        
        if st.button("🧪 Run Test Sequence"):
            if test_command:
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                # Send commands and wait for responses
                failed = False
                for i in range(test_count):
                    # Get current command history count
                    with server.lock:
                        initial_count = len(server.command_history)
                    
                    # Send command
                    success = server.send_command(test_imei, test_command)
                    if not success:
                        status_text.error(f"Failed to send command {i+1}/{test_count}")
                        failed = True
                        break
                    
                    status_text.text(f"Sent {i+1}/{test_count}, waiting for response...")
                    progress_bar.progress((i + 0.5) / test_count)
                    
                    # Wait for response (or timeout)
                    response_received = False
                    timeout_start = time.time()
                    
                    while time.time() - timeout_start < test_timeout:
                        with server.lock:
                            current_count = len(server.command_history)
                            # Check if new response for this IMEI
                            if current_count > initial_count:
                                # Check if the latest entry is for our IMEI
                                if server.command_history[0]['imei'] == test_imei:
                                    response_received = True
                                    break
                        
                        time.sleep(0.1)  # Poll every 100ms
                    
                    if response_received:
                        status_text.text(f"Response received for {i+1}/{test_count}")
                        progress_bar.progress((i+1) / test_count)
                    else:
                        status_text.warning(f"Timeout waiting for response {i+1}/{test_count}")
                        progress_bar.progress((i+1) / test_count)
                    
                    # Small delay before next command
                    if i < test_count - 1:
                        time.sleep(0.5)
                
                if not failed:
                    st.success(f"✅ Test sequence completed - {test_count} commands sent")
            else:
                st.warning("Please enter a command")
    else:
        st.warning("No devices connected")

# Tab 5: Interval Commands (Replicates dataServer.js sendGprsCommand)
with tab5:
    st.header("🔁 Send Commands with Interval & Duration")
    st.write("Replicates JavaScript dataServer.js sendGprsCommand functionality")
    st.caption("Example: Send 'getinfo' every 20 seconds for 1 hour (replicating your JS call)")
    
    devices = server.get_connected_devices()
    
    if devices:
        # Device selection
        device_options = [f"{d['IMEI']} ({d['Protocol']})" for d in devices]
        selected_device_str = st.selectbox(
            "Select Device",
            options=device_options,
            key="interval_device"
        )
        
        selected_idx = device_options.index(selected_device_str)
        selected_device = devices[selected_idx]
        interval_imei = selected_device['IMEI']
        interval_protocol = selected_device['Protocol']
        
        # Command input
        interval_command = st.text_input(
            "Command", 
            key="interval_command",
            value="getinfo",
            placeholder="e.g., getinfo, getgps"
        )
        
        # Time unit conversion helper
        def convert_to_seconds(value, unit):
            multipliers = {'s': 1, 'min': 60, 'h': 3600}
            return value * multipliers.get(unit, 1)
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("⏱️ Interval")
            interval_col1, interval_col2 = st.columns([2, 1])
            with interval_col1:
                interval_value = st.number_input(
                    "Value",
                    min_value=0,
                    max_value=3600,
                    value=20,
                    key="interval_value",
                    help="0 = send once"
                )
            with interval_col2:
                interval_unit = st.selectbox(
                    "Unit",
                    options=['s', 'min', 'h'],
                    index=0,
                    key="interval_unit"
                )
            
            interval_seconds = convert_to_seconds(interval_value, interval_unit)
            st.caption(f"= {interval_seconds} seconds")
        
        with col2:
            st.subheader("⏳ Duration")
            duration_col1, duration_col2 = st.columns([2, 1])
            with duration_col1:
                duration_value = st.number_input(
                    "Value",
                    min_value=0,
                    max_value=24,
                    value=1,
                    key="duration_value",
                    help="0 = send once"
                )
            with duration_col2:
                duration_unit = st.selectbox(
                    "Unit",
                    options=['s', 'min', 'h'],
                    index=2,
                    key="duration_unit"
                )
            
            duration_seconds = convert_to_seconds(duration_value, duration_unit)
            st.caption(f"= {duration_seconds} seconds")
        
        # Calculate expected commands
        expected_commands = 1  # Default
        if interval_seconds > 0 and duration_seconds > 0:
            expected_commands = int(duration_seconds / interval_seconds)
            st.info(f"📊 Expected commands: ~{expected_commands} ({duration_seconds}s / {interval_seconds}s)")
        elif interval_seconds == 0 or duration_seconds == 0:
            st.info("📊 Will send command once (interval or duration is 0)")
            expected_commands = 1
        else:
            expected_commands = 1
        
        # Protocol selection
        protocol_choice = st.radio(
            "Protocol",
            options=['auto', 'TCP', 'UDP'],
            index=0,
            horizontal=True,
            key="interval_protocol",
            help="Auto will try TCP first, then UDP"
        )
        
        # Wait for record option (scheduler mode)
        wait_for_record = st.checkbox(
            "🔄 Wait for Record (Scheduler Mode)",
            value=False,
            key="wait_for_record",
            help="Only send commands after device sends a record. Mimics scheduler behavior: waits for active connection + received record before each command."
        )
        
        if wait_for_record:
            st.caption("📌 In this mode, commands are sent only after the device sends a data record, ensuring active connection.")
        
        st.divider()
        
        # Start/Stop controls
        if 'interval_running' not in st.session_state:
            st.session_state.interval_running = False
        
        if 'interval_result' not in st.session_state:
            st.session_state.interval_result = None
        
        col_btn1, col_btn2, col_btn3 = st.columns([1, 1, 2])
        
        with col_btn1:
            if st.button("▶️ Start", use_container_width=True, disabled=st.session_state.interval_running):
                if interval_command:
                    st.session_state.interval_running = True
                    st.session_state.interval_result = None
                    st.rerun()
                else:
                    st.warning("Please enter a command")
        
        with col_btn2:
            if st.button("⏹️ Stop", use_container_width=True, disabled=not st.session_state.interval_running, type="secondary"):
                if st.session_state.interval_running:
                    # Request stop
                    server.stop_interval_command(interval_imei)
                    st.info("Stop requested... (wait for current cycle to complete)")
        
        with col_btn3:
            if st.session_state.interval_running:
                st.warning("⚠️ Loop running... (click Stop to terminate early)")
        
        # Run the interval loop
        if st.session_state.interval_running:
            with st.spinner(f"Sending '{interval_command}' every {interval_seconds}s for {duration_seconds}s..."):
                result = server.send_command_with_interval(
                    imei=interval_imei,
                    command=interval_command,
                    interval_sec=interval_seconds,
                    duration_sec=duration_seconds,
                    protocol=protocol_choice,
                    wait_for_record=wait_for_record
                )
                
                st.session_state.interval_result = result
                st.session_state.interval_running = False
                st.rerun()
        
        # Display result
        if st.session_state.interval_result:
            result = st.session_state.interval_result
            
            if result.get('stopped', False):
                st.info("⏹️ Stopped by user")
            elif result['success'] and len(result['errors']) == 0:
                st.success(f"✅ Interval command loop completed successfully!")
            elif result['commands_sent'] > 0:
                st.warning(f"⚠️ Completed with some errors")
            else:
                st.error("❌ Failed to send commands")
            
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Commands Sent", result['commands_sent'])
            with col2:
                st.metric("Errors", len(result['errors']))
            with col3:
                if expected_commands > 0 and not result.get('stopped'):
                    success_rate = (result['commands_sent'] / expected_commands * 100)
                    st.metric("Success Rate", f"{success_rate:.1f}%")
                elif result.get('stopped'):
                    st.metric("Status", "⏹️ Stopped")
                else:
                    st.metric("Status", "✅ Done")
            
            if result['errors']:
                with st.expander("⚠️ View Errors"):
                    for i, error in enumerate(result['errors'], 1):
                        st.text(f"{i}. {error}")
            
            if st.button("🗑️ Clear Result"):
                st.session_state.interval_result = None
                st.rerun()
    
    else:
        st.warning("No devices connected")

# Tab 6: Command History
with tab6:
    st.header("📚 Command History")
    st.write("View commands sent and their responses")
    
    with server.lock:
        cmd_history = server.command_history.copy()
    
    if cmd_history:
        # Create DataFrame
        df = pd.DataFrame(cmd_history)
        
        # Display as table
        st.dataframe(
            df[['timestamp', 'imei', 'protocol', 'command', 'response', 'duration_ms']],
            use_container_width=True,
            height=600
        )
        
        # Show detailed view for specific entries
        st.subheader("Details")
        if len(cmd_history) > 0:
            selected_idx = st.selectbox(
                "Select command to see details",
                range(len(cmd_history)),
                format_func=lambda i: f"[{cmd_history[i]['timestamp']}] {cmd_history[i]['command']} -> {cmd_history[i]['response'][:50]}{'...' if len(cmd_history[i]['response']) > 50 else ''}"
            )
            
            if selected_idx is not None:
                entry = cmd_history[selected_idx]
                col1, col2 = st.columns(2)
                
                with col1:
                    st.write(f"**Time:** {entry['timestamp']}")
                    st.write(f"**IMEI:** {entry['imei']}")
                    st.write(f"**Protocol:** {entry['protocol']}")
                    st.write(f"**Duration:** {entry['duration_ms']} ms")
                
                with col2:
                    st.write("**Command:**")
                    st.code(entry['command'], language=None)
                    st.write("**Response:**")
                    st.code(entry['response'], language=None)
    else:
        st.info("No command history yet. Send a command to see it here.")
    
    # Auto-refresh
    if st.button("🔄 Refresh History", key="refresh_history"):
        st.rerun()

# Tab 7: Raw Messages & Logs
with tab7:
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("📨 Raw Messages")
        with server.lock:
            raw_msgs = server.raw_messages.copy()
        
        if raw_msgs:
            for msg in raw_msgs[:50]:  # Show last 50
                direction_icon = "⬇️" if msg['direction'] == "RX" else "⬆️"
                st.text(f"{direction_icon} [{msg['timestamp']}] {msg['protocol']} ({msg['length']} bytes)")
                st.code(msg['hex'], language=None)
        else:
            st.info("No raw messages yet")
    
    with col2:
        st.subheader("📝 Server Logs")
        with server.lock:
            logs = server.log_messages.copy()
        
        if logs:
            for log in logs[:50]:  # Show last 50
                type_icon = {
                    "IMEI": "🆔",
                    "DATA": "📊",
                    "ACK": "✅",
                    "CMD": "📤",
                    "CONN": "🔌",
                    "DISC": "🔴",
                    "ERROR": "❌",
                    "START": "🟢",
                    "STOP": "⛔",
                    "SCHEDULE": "⏰"
                }.get(log['type'], "ℹ️")
                
                st.text(f"{type_icon} [{log['timestamp']}] {log['type']}: {log['message']}")
        else:
            st.info("No logs yet")
