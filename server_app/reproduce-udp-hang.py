import time
import threading
import sys
from datetime import datetime, timedelta
from teltonika_server import TeltonikaServer

# CONFIGURATION (Matches your JS parameters)
# -------------------------------------------------
COMMAND = "getinfo"
DURATION = {"value": 1, "units": "h"}   # JS: duration: { value: 1, units: 'h' }
INTERVAL = {"value": 20, "units": "s"}  # JS: interval: { value: 20, units: 's' }
WRONG_CRC = False                       # JS: wrongCRC: false
SERVER_PORT_UDP = 8001
# -------------------------------------------------

def get_seconds(param):
    """Helper to convert JS-style time objects to seconds"""
    val = float(param['value'])
    unit = param['units']
    if unit == 's': return val
    if unit == 'min': return val * 60
    if unit == 'h': return val * 3600
    return val

def run_gprs_loop(server, target_imei):
    """
    Replicates the 'cycle' logic from dataServer.js sendGprsCommand function.
    See dataServer.js
    """
    duration_sec = get_seconds(DURATION)
    interval_sec = get_seconds(INTERVAL)
    
    start_time = datetime.now()
    end_time = start_time + timedelta(seconds=duration_sec)
    
    print(f"\n[TEST START] Loop started for IMEI: {target_imei}")
    print(f"Command: '{COMMAND}' | Interval: {interval_sec}s | Duration: {duration_sec}s")
    print("-" * 60)

    cycle_count = 0

    while datetime.now() < end_time:
        cycle_count += 1
        now_str = datetime.now().strftime('%H:%M:%S')
        
        # 1. Check if we still have a valid UDP address for this IMEI
        # In Python server, this is stored in udp_clients
        udp_addr = server.udp_clients.get(target_imei)
        
        if not udp_addr:
            print(f"[{now_str}] #{cycle_count} ERROR: Lost UDP reference for {target_imei}. NAT timeout likely occurred.")
            # We don't break, because we want to see if it recovers (device sends keepalive)
        else:
            # 2. Send the command
            # The JS code uses wrongCRC param, but your Python Protocol class
            # currently always calculates valid CRC. Since wrongCRC=False, this is fine.
            try:
                # We explicitly use UDP to match your issue description
                success = server.send_udp_command(target_imei, COMMAND)
                
                status = "SENT" if success else "FAILED (Socket Error)"
                print(f"[{now_str}] #{cycle_count} UDP Command {status} -> {udp_addr}")
                
            except Exception as e:
                print(f"[{now_str}] #{cycle_count} EXCEPTION: {e}")

        # 3. Wait for interval (Replicating setTimeout recursion)
        # We calculate drift to keep timing precise
        elapsed = (datetime.now() - start_time).total_seconds()
        next_cycle_target = (cycle_count * interval_sec)
        sleep_time = next_cycle_target - elapsed
        
        if sleep_time > 0:
            time.sleep(sleep_time)

    print("-" * 60)
    print(f"[TEST END] Duration expired.")

def main():
    # 1. Start the Server
    print(f"--- Teltonika UDP Debugger ---")
    server = TeltonikaServer(udp_port=SERVER_PORT_UDP)
    server.start()

    target_imei = None

    try:
        print(f"Waiting for ANY UDP packet to identify device...")
        print(f"Please trigger the device to send a record (e.g. ignition on, or wait for periodic).")
        
        # 2. Wait for Device Connection (Handshake)
        # We poll the udp_clients dictionary until we see a device
        while target_imei is None:
            with server.lock:
                if len(server.udp_clients) > 0:
                    # Pick the first connected device
                    target_imei, addr = list(server.udp_clients.items())[0]
                    print(f"\n[FOUND DEVICE] IMEI: {target_imei} @ IP: {addr}")
                    print("Waiting 5 seconds before starting loop...")
                    break
            time.sleep(1)
        
        time.sleep(5)

        # 3. Start the Replication Loop
        run_gprs_loop(server, target_imei)

    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        server.stop()

if __name__ == "__main__":
    main()