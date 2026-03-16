"""
COM Unlocker plugin – Identify and kill processes locking COM ports.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from app.plugins.base import ToolkitPlugin

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HANDLE_TOOL = os.path.join(ROOT, "com-killer", "handle64.exe")


def _is_admin() -> bool:
    if os.name != "nt":
        return False
    try:
        import ctypes
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def _list_com_ports() -> list[dict]:
    try:
        import serial.tools.list_ports
        ports = serial.tools.list_ports.comports()
        return sorted(
            [{"port": p.device, "desc": p.description, "hwid": getattr(p, "hwid", "")}
             for p in ports],
            key=lambda x: x["port"],
        )
    except ImportError:
        return []


def _scan_port(port: str) -> dict | None:
    if not os.path.exists(HANDLE_TOOL):
        return None
    try:
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        r = subprocess.run(
            [HANDLE_TOOL, "-a", "-nobanner", port],
            capture_output=True, text=True, startupinfo=si, timeout=5,
        )
        out = r.stdout
        if not out or "No matching handles found" in out:
            return None
        m = re.search(r"(?P<name>[\w.\-]+)\s+pid:\s+(?P<pid>\d+)", out, re.I)
        if m:
            return {"pid": int(m.group("pid")), "name": m.group("name")}
    except Exception:
        pass
    return None


def _kill_pid(pid: int) -> tuple[bool, str]:
    try:
        import psutil
        p = psutil.Process(pid)
        p.terminate()
        try:
            p.wait(timeout=3)
            return True, "Terminated"
        except psutil.TimeoutExpired:
            p.kill()
            return True, "Force killed"
    except Exception as e:
        return False, str(e)


def _probe_port(port: str) -> tuple[bool, str]:
    try:
        import serial
        s = serial.Serial(port=port, timeout=0.2)
        if s.is_open:
            s.close()
        return True, "Port accessible"
    except Exception as e:
        return False, str(e)


def _restart_device(port: str) -> tuple[bool, str]:
    try:
        ps = (
            "$p = Get-PnpDevice -Class Ports -PresentOnly -EA SilentlyContinue | "
            f"Where-Object {{ $_.FriendlyName -match '\\({re.escape(port)}\\)' }} | "
            "Select -First 1 -Expand InstanceId; if ($p) { Write-Output $p }"
        )
        r = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                           capture_output=True, text=True, timeout=8)
        iid = (r.stdout or "").strip()
        if not iid:
            return False, f"No PnP device for {port}"
        r2 = subprocess.run(["pnputil", "/restart-device", iid],
                            capture_output=True, text=True, timeout=20)
        if r2.returncode == 0:
            return True, f"Device restarted ({iid})"
        return False, (r2.stdout or "") + (r2.stderr or "")
    except Exception as e:
        return False, str(e)


def _launch_admin_instance() -> tuple[bool, str]:
    """Spawn com_unlocker_admin.py elevated (triggers UAC)."""
    script = os.path.join(ROOT, "com_unlocker_admin.py")
    if not os.path.exists(script):
        return False, "com_unlocker_admin.py not found"
    try:
        import ctypes
        ret = ctypes.windll.shell32.ShellExecuteW(
            None, "runas", sys.executable, f'"{script}"', ROOT, 1,
        )
        if ret <= 32:
            return False, f"ShellExecute failed (code {ret})"
        return True, "Launched with admin rights"
    except Exception as e:
        return False, str(e)


class COMUnlockerPlugin(ToolkitPlugin):
    id = "com"
    name = "COM Unlocker"
    icon = "🔌"
    order = 30

    def register_routes(self, app: FastAPI):

        @app.get("/api/com/status")
        async def com_status():
            return {
                "admin": _is_admin(),
                "handle_found": os.path.exists(HANDLE_TOOL),
                "handle_path": HANDLE_TOOL,
            }

        @app.get("/api/com/ports")
        async def com_ports():
            return _list_com_ports()

        @app.get("/api/com/scan/{port}")
        async def com_scan(port: str):
            if not os.path.exists(HANDLE_TOOL):
                raise HTTPException(500, "handle64.exe not found")
            result = _scan_port(port)
            accessible, msg = _probe_port(port)
            return {
                "locked": result is not None,
                "process": result,
                "accessible": accessible,
                "probe_msg": msg,
            }

        @app.post("/api/com/kill/{pid}")
        async def com_kill(pid: int):
            ok, msg = _kill_pid(pid)
            return {"ok": ok, "msg": msg}

        @app.post("/api/com/restart/{port}")
        async def com_restart(port: str):
            ok, msg = _restart_device(port)
            return {"ok": ok, "msg": msg}

        @app.post("/api/com/launch_admin")
        async def com_launch_admin():
            ok, msg = _launch_admin_instance()
            if not ok:
                raise HTTPException(500, msg)
            return {"ok": True, "msg": msg}


plugin = COMUnlockerPlugin()
