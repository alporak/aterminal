import sys
import os
import re
import subprocess
import psutil
import serial
import serial.tools.list_ports
from shutil import which

# Configuration: Name of the Sysinternals tool
# Use handle64.exe for 64-bit windows, handle.exe for 32-bit
HANDLE_TOOL = "handle64.exe" 

def check_admin():
    """Checks if the script is running with Admin privileges."""
    try:
        is_admin = os.getuid() == 0
    except AttributeError:
        # Windows check
        import ctypes
        is_admin = ctypes.windll.shell32.IsUserAnAdmin() != 0
    return is_admin

def prompt_and_elevate_if_needed():
    """Prompts user and relaunches script with admin rights on Windows if needed."""
    if check_admin():
        return True

    print("This action requires Administrator privileges.")
    choice = input("Relaunch as Administrator now? (Y/n): ").strip().lower()
    if choice in ("", "y", "yes"):
        try:
            import ctypes
            script = os.path.abspath(sys.argv[0])
            args = " ".join([f'\"{arg}\"' for arg in sys.argv[1:]])
            result = ctypes.windll.shell32.ShellExecuteW(
                None,
                "runas",
                sys.executable,
                f'\"{script}\" {args}'.strip(),
                None,
                1,
            )
            if result <= 32:
                print("[-] Elevation request failed or was cancelled.")
                input("Press Enter to exit...")
                return False
            return False
        except Exception as exc:
            print(f"[-] Failed to request elevation: {exc}")
            input("Press Enter to exit...")
            return False

    print("Administrator privileges are required to inspect and unlock COM ports.")
    input("Press Enter to exit...")
    return False

def find_handle_tool():
    """Locates the handle.exe tool in current dir or PATH."""
    # Check current directory first
    if os.path.exists(os.path.join(os.getcwd(), HANDLE_TOOL)):
        return os.path.join(os.getcwd(), HANDLE_TOOL)
    
    # Check system PATH
    tool_path = which(HANDLE_TOOL)
    if tool_path:
        return tool_path
        
    return None

def list_com_ports():
    """Lists available COM ports."""
    ports = serial.tools.list_ports.comports()
    return sorted(ports, key=lambda p: p.device)

def get_process_using_port(port_name, tool_path):
    """
    Uses handle.exe to find the PID locking the port.
    Returns: (pid, process_name) or None
    """
    print(f"[*] Scanning handles for {port_name}...")
    
    # Arguments: -a (dump all handles), -nobanner (clean output)
    # We search specifically for the port name (e.g., "COM3")
    cmd = [tool_path, "-a", "-nobanner", port_name]
    
    try:
        # Run handle.exe; hide window if possible
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        
        result = subprocess.run(
            cmd, 
            capture_output=True, 
            text=True, 
            startupinfo=startupinfo
        )
    except FileNotFoundError:
        return None

    # Output format typically looks like:
    # python.exe         pid: 12345  type: File  1C4: \Device\Serial0
    
    output = result.stdout or ""
    
    if not output or "No matching handles found" in output:
        return None

    # Regex to grab the Process Name and PID
    # Looks for: Name.exe ... pid: 1234 ...
    match = re.search(r'(?P<name>[\w\.-]+)\s+pid:\s+(?P<pid>\d+)', output, re.IGNORECASE)
    
    if match:
        return int(match.group('pid')), match.group('name')
    
    return None

def probe_port_access(port_name):
    """Attempts to open the COM port briefly to determine whether it is actually accessible."""
    try:
        test = serial.Serial(port=port_name, timeout=0.2)
        if test.is_open:
            test.close()
        return True, "Port open test succeeded."
    except serial.SerialException as exc:
        text = str(exc)
        lowered = text.lower()
        if "access is denied" in lowered or "permission" in lowered:
            return False, f"Port open failed: {text}"
        if "could not open port" in lowered:
            return False, f"Port open failed: {text}"
        return False, f"Port open failed: {text}"
    except Exception as exc:
        return False, f"Port open failed: {exc}"

def kill_process(pid, name):
    """Kills the process by PID."""
    try:
        p = psutil.Process(pid)
        print(f"\n[!] ATTEMPTING TO KILL: {name} (PID: {pid})")
        p.terminate()
        try:
            p.wait(timeout=3)
        except psutil.TimeoutExpired:
            print("[-] Process refused to terminate. Forcing kill...")
            p.kill()
        print(f"[+] Successfully killed {name}.")
    except psutil.NoSuchProcess:
        print(f"[-] Process {pid} no longer exists.")
    except psutil.AccessDenied:
        print(f"[-] Access Denied. Please run this script as Administrator.")
    except Exception as e:
        print(f"[-] Error: {e}")

def find_pnp_instance_id_for_port(port_name):
    """Find PnP instance id for a COM port using PowerShell."""
    if os.name != 'nt':
        return None
    ps_cmd = (
        "$p = Get-PnpDevice -Class Ports -PresentOnly -ErrorAction SilentlyContinue | "
        f"Where-Object {{ $_.FriendlyName -match '\\({re.escape(port_name)}\\)' }} | "
        "Select-Object -First 1 -ExpandProperty InstanceId; "
        "if ($p) { Write-Output $p }"
    )
    try:
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
    """Attempt to restart the COM device via pnputil."""
    instance_id = find_pnp_instance_id_for_port(port_name)
    if not instance_id:
        return False, f"Could not find a PnP device for {port_name}."
    try:
        result = subprocess.run(
            ["pnputil", "/restart-device", instance_id],
            capture_output=True,
            text=True,
            timeout=20
        )
        output = ((result.stdout or "") + "\n" + (result.stderr or "")).strip()
        if result.returncode == 0:
            return True, f"Device restart requested for {port_name} ({instance_id})."
        return False, output or f"pnputil failed with code {result.returncode}."
    except Exception as exc:
        return False, str(exc)

def main():
    if not prompt_and_elevate_if_needed():
        return

    tool_path = find_handle_tool()
    if not tool_path:
        print(f"CRITICAL ERROR: '{HANDLE_TOOL}' not found.")
        print("1. Download Sysinternals Handle: https://learn.microsoft.com/en-us/sysinternals/downloads/handle")
        print(f"2. Place '{HANDLE_TOOL}' in the same folder as this script.")
        input("Press Enter to exit...")
        return

    while True:
        os.system('cls' if os.name == 'nt' else 'clear')
        print("=== COM Port Unlocker ===")
        ports = list_com_ports()
        
        if not ports:
            print("No COM ports found.")
            input("Press Enter to refresh...")
            continue

        print(f"{'#':<4} {'Port':<10} {'Description'}")
        print("-" * 40)
        for i, p in enumerate(ports):
            print(f"{i+1:<4} {p.device:<10} {p.description}")
        
        print("-" * 40)
        print("Q. Quit")
        
        choice = input("\nSelect a port number to check: ").strip().lower()
        
        if choice == 'q':
            break
            
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(ports):
                selected_port = ports[idx].device
                
                is_accessible, probe_message = probe_port_access(selected_port)
                result = get_process_using_port(selected_port, tool_path)
                
                if result:
                    pid, name = result
                    print(f"\n[!] FOUND LOCKER: Process '{name}' (PID: {pid}) is using {selected_port}")
                    confirm = input(">>> Kill this process? (y/N): ").lower()
                    if confirm == 'y':
                        kill_process(pid, name)
                    else:
                        print("Operation cancelled.")
                else:
                    print(f"\n[-] No process found holding {selected_port}.")
                    if is_accessible:
                        print(f"    [+] {probe_message}")
                        print("    The COM port appears available to user-space applications.")
                    else:
                        print(f"    [!] {probe_message}")
                        print("    The port is not accessible. It may be locked by a kernel/system driver or another service.")
                        restart_confirm = input("    >>> Attempt driver-level restart for this port device? (y/N): ").strip().lower()
                        if restart_confirm == 'y':
                            ok, message = restart_port_device(selected_port)
                            if ok:
                                print(f"    [+] {message}")
                                is_accessible_after, probe_after = probe_port_access(selected_port)
                                if is_accessible_after:
                                    print(f"    [+] Re-check passed: {probe_after}")
                                else:
                                    print(f"    [!] Re-check failed: {probe_after}")
                            else:
                                print(f"    [-] Driver-level restart failed: {message}")
                
                input("\nPress Enter to continue...")
            else:
                print("Invalid selection.")
                input()
        except ValueError:
            pass

if __name__ == "__main__":
    main()