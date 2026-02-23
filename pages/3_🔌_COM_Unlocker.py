"""
COM Port Unlocker - Identify and kill processes locking COM ports
"""

import streamlit as st
import subprocess
import os
import sys
import re
import time
import psutil

# Add parent directory for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Page config
st.set_page_config(
    page_title="COM Port Unlocker",
    page_icon="🔌",
    layout="wide"
)

st.title("🔌 COM Port Unlocker")
st.markdown("Identify and kill processes locking COM ports")

# Configuration
HANDLE_TOOL = "handle64.exe"

def relaunch_streamlit_as_admin():
    """Relaunch the toolkit Streamlit app with elevation."""
    if os.name != 'nt':
        return False, "Elevation relaunch is only supported on Windows"
    try:
        import ctypes
        root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        app_entry = os.path.join(root_dir, "streamlit_app.py")
        port = os.environ.get("STREAMLIT_SERVER_PORT", "8501")
        args = f'-m streamlit run "{app_entry}" --server.headless=true --server.port={port}'
        result = ctypes.windll.shell32.ShellExecuteW(
            None,
            "runas",
            sys.executable,
            args,
            root_dir,
            1,
        )
        if result <= 32:
            return False, "UAC elevation request was cancelled or failed"
        return True, "Elevated Streamlit instance started"
    except Exception as exc:
        return False, str(exc)

def check_admin():
    """Check if running with admin privileges"""
    try:
        import ctypes
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except:
        return False

def find_handle_tool():
    """Locate handle64.exe tool"""
    # Check in com-killer directory
    tool_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'com-killer', HANDLE_TOOL)
    if os.path.exists(tool_path):
        return tool_path
    
    # Check current directory
    if os.path.exists(HANDLE_TOOL):
        return HANDLE_TOOL
    
    return None

def list_com_ports():
    """List available COM ports"""
    try:
        import serial.tools.list_ports
        ports = serial.tools.list_ports.comports()
        return sorted(ports, key=lambda p: p.device)
    except ImportError:
        st.error("⚠️ pyserial not installed. Install with: pip install pyserial")
        return []

def get_process_using_port(port_name, tool_path):
    """Find process locking a port"""
    try:
        cmd = [tool_path, "-a", "-nobanner", port_name]
        
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        
        result = subprocess.run(
            cmd, 
            capture_output=True, 
            text=True, 
            startupinfo=startupinfo,
            timeout=5
        )
        
        output = result.stdout
        
        if not output or "No matching handles found" in output:
            return None
        
        # Extract process name and PID
        match = re.search(r'(?P<name>[\w\.-]+)\s+pid:\s+(?P<pid>\d+)', output, re.IGNORECASE)
        
        if match:
            return {
                'pid': int(match.group('pid')),
                'name': match.group('name')
            }
        
        return None
    except Exception as e:
        st.error(f"Error scanning port: {e}")
        return None

def probe_port_access(port_name):
    """Attempt to open COM port briefly to verify actual accessibility."""
    try:
        import serial
        test = serial.Serial(port=port_name, timeout=0.2)
        if test.is_open:
            test.close()
        return True, "Port open test succeeded"
    except Exception as exc:
        return False, f"Port open failed: {exc}"

def find_pnp_instance_id_for_port(port_name):
    """Find PnP instance id for a COM port using PowerShell."""
    try:
        ps_cmd = (
            "$p = Get-PnpDevice -Class Ports -PresentOnly -ErrorAction SilentlyContinue | "
            f"Where-Object {{ $_.FriendlyName -match '\\({re.escape(port_name)}\\)' }} | "
            "Select-Object -First 1 -ExpandProperty InstanceId; "
            "if ($p) { Write-Output $p }"
        )
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_cmd],
            capture_output=True,
            text=True,
            timeout=8
        )
        instance_id = (result.stdout or "").strip()
        return instance_id or None
    except Exception:
        return None

def restart_port_device(port_name):
    """Try to restart COM device with pnputil for kernel-level lock cases."""
    instance_id = find_pnp_instance_id_for_port(port_name)
    if not instance_id:
        return False, f"Could not find a PnP device for {port_name}"
    try:
        result = subprocess.run(
            ["pnputil", "/restart-device", instance_id],
            capture_output=True,
            text=True,
            timeout=20
        )
        output = ((result.stdout or "") + "\n" + (result.stderr or "")).strip()
        if result.returncode == 0:
            return True, f"Device restart requested ({instance_id})"
        return False, output or f"pnputil failed with code {result.returncode}"
    except Exception as exc:
        return False, str(exc)

def kill_process(pid, name):
    """Kill a process by PID"""
    try:
        p = psutil.Process(pid)
        p.terminate()
        try:
            p.wait(timeout=3)
            return True, "Process terminated successfully"
        except psutil.TimeoutExpired:
            p.kill()
            return True, "Process forcefully killed"
    except psutil.NoSuchProcess:
        return False, "Process no longer exists"
    except psutil.AccessDenied:
        return False, "Access denied. Requires Administrator privileges"
    except Exception as e:
        return False, str(e)

# Check prerequisites
is_admin = check_admin()
tool_path = find_handle_tool()

# Warnings
if not is_admin:
    st.warning("⚠️ **Not running as Administrator**. Some features may not work properly. Please run this app with elevated privileges.")
    if st.button("🛡️ Relaunch Toolkit as Administrator", type="primary", use_container_width=True):
        ok, message = relaunch_streamlit_as_admin()
        if ok:
            st.success("UAC prompt sent. Closing this non-admin instance...")
            time.sleep(0.7)
            os._exit(0)
        st.error(f"Failed to relaunch elevated: {message}")

if not tool_path:
    st.error(f"""
    ❌ **{HANDLE_TOOL} not found!**
    
    1. Download Sysinternals Handle from: https://learn.microsoft.com/en-us/sysinternals/downloads/handle
    2. Place `{HANDLE_TOOL}` in the `com-killer/` directory
    """)
    st.stop()

# Sidebar
with st.sidebar:
    st.header("⚙️ Status")
    
    st.metric("Admin Privileges", "✅ Yes" if is_admin else "❌ No")
    st.metric("Handle Tool", "✅ Found" if tool_path else "❌ Missing")
    
    if tool_path:
        st.text(f"Path: {os.path.basename(tool_path)}")
    
    st.divider()
    
    if st.button("🔄 Refresh Port List", use_container_width=True):
        st.rerun()
    
    st.divider()
    
    st.subheader("ℹ️ About")
    st.write("""
    This tool uses Sysinternals Handle to identify processes that are locking COM ports.
    
    **Requirements:**
    - Windows OS
    - Administrator privileges
    - handle64.exe tool
    """)

# Main content
st.header("Available COM Ports")

ports = list_com_ports()

if not ports:
    st.info("No COM ports found on this system")
else:
    # Display ports in a table
    port_data = []
    for p in ports:
        port_data.append({
            "Port": p.device,
            "Description": p.description,
            "Hardware ID": p.hwid if hasattr(p, 'hwid') else "N/A"
        })
    
    st.dataframe(port_data, use_container_width=True, hide_index=True)
    
    st.divider()
    
    # Port selection and scanning
    st.header("🔍 Scan for Port Locks")
    
    port_names = [p.device for p in ports]
    selected_port = st.selectbox("Select a port to scan:", port_names)
    
    col1, col2 = st.columns([1, 3])
    
    with col1:
        scan_button = st.button("🔍 Scan Port", type="primary", use_container_width=True)
    
    if scan_button and selected_port:
        with st.spinner(f"Scanning {selected_port}..."):
            result = get_process_using_port(selected_port, tool_path)
            
            if result:
                st.error(f"🔒 **Port Locked!**")
                
                # Display process info
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Process Name", result['name'])
                with col2:
                    st.metric("PID", result['pid'])
                with col3:
                    # Get additional process info
                    try:
                        proc = psutil.Process(result['pid'])
                        st.metric("Status", proc.status())
                    except:
                        st.metric("Status", "Unknown")
                
                st.divider()
                
                # Kill option
                st.subheader("⚠️ Kill Process?")
                st.warning(f"This will forcefully terminate **{result['name']}** (PID: {result['pid']})")
                
                col1, col2, col3 = st.columns([1, 1, 2])
                
                with col1:
                    if st.button("💀 Kill Process", type="primary", use_container_width=True):
                        success, message = kill_process(result['pid'], result['name'])
                        if success:
                            st.success(f"✅ {message}")
                            st.balloons()
                        else:
                            st.error(f"❌ {message}")
                
                with col2:
                    if st.button("❌ Cancel", use_container_width=True):
                        st.info("Operation cancelled")
            else:
                is_accessible, probe_message = probe_port_access(selected_port)
                if is_accessible:
                    st.success(f"✅ **{selected_port} is free and accessible**")
                    st.info("No process is currently locking this port.")
                else:
                    st.warning(f"⚠️ No user process found, but {selected_port} is still not accessible")
                    st.code(probe_message)
                    st.info("This usually means a kernel/system driver lock. You can attempt a device-level restart.")
                    if st.button("🔁 Restart COM Device", use_container_width=True):
                        ok, message = restart_port_device(selected_port)
                        if ok:
                            st.success(message)
                            check_ok, check_msg = probe_port_access(selected_port)
                            if check_ok:
                                st.success(f"✅ Re-check passed: {check_msg}")
                            else:
                                st.warning(f"⚠️ Re-check still failing: {check_msg}")
                        else:
                            st.error(f"❌ Device restart failed: {message}")

# Additional Info
st.divider()
with st.expander("📖 How to use"):
    st.markdown("""
    ### Step-by-Step Guide
    
    1. **Run as Administrator**: Make sure you're running this app with elevated privileges
    2. **Select a COM Port**: Choose the port you want to check from the dropdown
    3. **Scan**: Click "Scan Port" to identify if any process is locking it
    4. **Kill Process** (if needed): If a process is found, you can terminate it to free the port
    
    ### Common Scenarios
    
    - **Arduino IDE**: Sometimes doesn't release COM ports properly
    - **Serial Terminal Apps**: May lock ports even after closing
    - **Crashed Applications**: Leave handles open
    - **Driver Issues**: System processes might hold ports
    
    ### Safety Notes
    
    ⚠️ Killing system processes can cause instability. Only kill processes you recognize.
    """)
