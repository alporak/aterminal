"""
Universal Tester Tool plugin – Drag/drop test case builder for Universal Tester Tool (FMB).

Generates YAML configs, launches the universal tester engine, and monitors runs.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

import re as _re

from app.plugins.base import ToolkitPlugin
from app import config

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ── Paths ───────────────────────────────────────────────────────────
CASES_DIR = os.path.join(ROOT, "universal-tester-tool", "test_cases")
GENERATED_DIR = os.path.join(ROOT, "universal-tester-tool", "generated")
os.makedirs(CASES_DIR, exist_ok=True)
os.makedirs(GENERATED_DIR, exist_ok=True)

# Default path to the Universal Tester Tool engine installation
_DEFAULT_UNIVERSAL_TESTER_TOOL_PATH = os.path.join(ROOT, "third_party", "universal-tester-tool")


def _resolve_utt_root(path: str | None) -> str:
    """Resolve configured engine path to an absolute path."""
    candidate = (path or "").strip() or _DEFAULT_UNIVERSAL_TESTER_TOOL_PATH
    if os.path.isabs(candidate):
        return os.path.normpath(candidate)
    return os.path.normpath(os.path.join(ROOT, candidate))

# ── Step catalog (FMB-focused) ──────────────────────────────────────

STEP_CATALOG = [
    {
        "type": "power_off",
        "label": "Power OFF",
        "icon": "⏻",
        "category": "Power",
        "description": "Turn off power supply via OTII",
        "defaults": {"resource": "PPK", "timeout": 40, "retry": 1, "error_level": "Warning"},
    },
    {
        "type": "power_on",
        "label": "Power ON",
        "icon": "🔌",
        "category": "Power",
        "description": "Turn on power supply via OTII",
        "defaults": {"resource": "PPK", "timeout": 40, "retry": 1, "error_level": "Warning"},
    },
    {
        "type": "send_command",
        "label": "Send Command",
        "icon": "📤",
        "category": "Serial",
        "description": "Write a command to the device terminal",
        "defaults": {"resource": "Terminal", "input": "", "timeout": 40, "retry": 1, "error_level": "Warning"},
    },
    {
        "type": "read_response",
        "label": "Read Response",
        "icon": "📥",
        "category": "Serial",
        "description": "Read and verify output from terminal",
        "defaults": {
            "resource": "Terminal", "output": "", "match_type": "loose", "args": [],
            "timeout": 40, "retry": 1, "error_level": "Warning",
        },
    },
    {
        "type": "send_and_verify",
        "label": "Send & Verify",
        "icon": "🔄",
        "category": "Serial",
        "description": "Send command and verify the response",
        "defaults": {
            "resource": "Terminal", "input": "", "output": "", "match_type": "loose", "args": [],
            "timeout": 40, "retry": 1, "error_level": "Warning",
        },
    },
    {
        "type": "delay",
        "label": "Delay / Wait",
        "icon": "⏱️",
        "category": "General",
        "description": "Wait for a specified number of seconds",
        "defaults": {"delay": 5, "timeout": 40, "retry": 1, "error_level": "Warning"},
    },
    {
        "type": "read_catcher",
        "label": "Read Catcher",
        "icon": "🔍",
        "category": "Catcher",
        "description": "Read trace from Catcher port",
        "defaults": {
            "resource": "Catcher", "source": "", "destination": "",
            "SAP": "", "msg_id": "", "args": [],
            "timeout": 40, "retry": 1, "error_level": "Warning",
        },
    },
]


# ── Step label mapping ──────────────────────────────────────────────

_STEP_LABELS = {
    "power_off": "Power OFF",
    "power_on": "Power ON",
    "send_command": "Send Command",
    "read_response": "Read Response",
    "send_and_verify": "Send & Verify",
    "delay": "Delay / Wait",
    "read_catcher": "Read Catcher",
}

# Maps step type -> the print the Universal Tester Tool engine emits when hitting that func
_FUNC_PRINTS = {
    "power_off": "OtiiSetOut",
    "power_on": "OtiiSetOut",
    "send_command": "UartWrite",
    "read_response": "UartRead",
    "send_and_verify": "UartWriteRead",
    "delay": "Delay",
    "read_catcher": "UartRead",
}


def _build_step_tracker(steps: list[dict]) -> list[dict]:
    """Build a list of step-progress dicts from the case steps."""
    tracker = []
    for i, s in enumerate(steps):
        label = _STEP_LABELS.get(s.get("type", ""), s.get("type", "?"))
        detail = ""
        if s.get("input"):
            detail = s["input"]
        elif s.get("output"):
            detail = s["output"]
        elif s.get("type") == "delay":
            detail = f"{s.get('delay', 0)}s"
        tracker.append({
            "index": i,
            "type": s.get("type", ""),
            "label": label,
            "detail": detail,
            "status": "pending",  # pending | running | passed | failed
            "result": "",
        })
    return tracker


# ── Active run state ────────────────────────────────────────────────

class RunState:
    def __init__(self):
        self.running = False
        self.run_id: str = ""
        self.process: Optional[subprocess.Popen] = None
        self.log_lines: list[str] = []
        self.current_iteration = 0
        self.total_iterations = 1
        self.status = "idle"  # idle | running | completed | failed | stopped
        self.started_at: Optional[str] = None
        self.case_name: str = ""
        self.steps: list[dict] = []      
        self.current_step: int = -1      
        self._expected_funcs: list[str] = []  
        self._func_cursor: int = 0       
        self._lock = threading.Lock()
        self.fail_reason: str = ""       
        self.log_file: str = ""          
        self.device_name: str = ""       
        self.utt_root: str = ""          
        self.run_logs_dir: str = ""      
        self.log_file_handle = None
        self.history: list[dict] = []
        
    def init_log_file(self):
        """Open a log file handle for real-time streaming."""
        cfg = config.load()
        log_dir = cfg.get("universal_tester_tool_log_dir", os.path.join(ROOT, "output", "universal_tester_tool_logs"))
        os.makedirs(log_dir, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        case_slug = self.case_name.replace(" ", "_")[:30] if self.case_name else "unknown"
        self.log_file = os.path.join(log_dir, f"{ts}_{case_slug}.log")
        try:
            self.log_file_handle = open(self.log_file, "w", encoding="utf-8")
            self.append_log(f"[LOG] Streaming live logs to {self.log_file}")
        except Exception as e:
            self.append_log(f"[LOG] Failed to open live log file: {e}")
            self.log_file_handle = None

    def close_log_file(self):
        with self._lock:
            if self.log_file_handle:
                self.log_file_handle.close()
                self.log_file_handle = None

    def to_dict(self) -> dict:
        with self._lock:
            return {
                "running": self.running,
                "run_id": self.run_id,
                "status": self.status,
                "case_name": self.case_name,
                "current_iteration": self.current_iteration,
                "total_iterations": self.total_iterations,
                "started_at": self.started_at,
                "log_tail": self.log_lines[-100:],
                "steps": list(self.steps),
                "history": list(self.history),
                "current_step": self.current_step,
                "fail_reason": self.fail_reason,
                "log_file": self.log_file,
                "run_logs_dir": self.run_logs_dir,
            }

    def append_log(self, line: str):
        with self._lock:
            self.log_lines.append(line)
            # Write to disk in real-time
            if self.log_file_handle:
                try:
                    self.log_file_handle.write(line + "\n")
                    self.log_file_handle.flush()
                except Exception:
                    pass
            self._parse_line(line)

    def _parse_line(self, line: str):
        """Detect step transitions and results from subprocess stdout."""
        stripped = line.strip()
        if not stripped or not self.steps:
            return

        # Detect function start prints: "UartWrite", "UartRead", "UartWriteRead", "Delay"
        # Note: UartWriteRead internally prints UartWrite + UartRead as sub-calls.
        # Only advance the cursor on the TOP-LEVEL function that matches the expected step.
        _ALL_FUNC_NAMES = {"UartWrite", "UartRead", "UartWriteRead", "Delay", "OtiiSetOut",
                           "OtiiConfig", "OtiiSet5V", "OtiiStartMeasuring", "OtiiStopMeasuring",
                           "Running func"}
        if stripped in _ALL_FUNC_NAMES:
            if stripped == "Running func":
                return  # skip this noise line
            if self._func_cursor < len(self._expected_funcs):
                expected = self._expected_funcs[self._func_cursor]
                if stripped == expected:
                    # Mark previous step as passed (if it was running and we moved on)
                    if self.current_step >= 0 and self.steps[self.current_step]["status"] == "running":
                        self.steps[self.current_step]["status"] = "passed"
                    # Advance to next step
                    self.current_step = self._func_cursor
                    if self.current_step < len(self.steps):
                        self.steps[self.current_step]["status"] = "running"
                    self._func_cursor += 1
                # else: sub-call (e.g. UartWrite inside UartWriteRead) — ignore
            return

        # Capture TX/RX/SERIAL detail lines and attach to current step
        if self.current_step >= 0 and self.current_step < len(self.steps):
            step = self.steps[self.current_step]
            if stripped.startswith(">> TX "):
                step["detail"] = stripped
                return
            if stripped.startswith(".. RX ") or stripped.startswith("<< RX "):
                # Keep TX if already set, append RX
                prev = step.get("detail", "")
                step["detail"] = (prev + " | " + stripped) if prev and "TX" in prev else stripped
                return
            if stripped.startswith("[SERIAL "):
                # Raw serial data — show latest received data
                step["detail"] = stripped
                return

        # Detect per-function results from test_settings.py logger
        # Pattern: "Function run: <func> retries: X, time: Y [<result>] [PASS]"
        if "Function run:" in stripped and self.current_step >= 0 and self.current_step < len(self.steps):
            step = self.steps[self.current_step]
            if "[PASS]" in stripped:
                step["status"] = "passed"
                # Extract the result portion
                import re as _re
                m = _re.search(r'\[(.+?)\]\s*\[PASS\]', stripped)
                if m:
                    step["result"] = m.group(1)
            elif "Timeout" in stripped or "Warning" in stripped or "Error" in stripped:
                step["result"] = stripped.split("Function run:")[-1].strip()
            return

        # Detect routine-level pass/fail:  "[Name] PASSED" or "[Name] Warning/Error"
        if ("PASSED" in stripped or "Warning" in stripped or "Error" in stripped) and "Elapsed time:" in stripped:
            self.iteration_done = True
            if "PASSED" in stripped:
                # Mark any still-running step as passed
                if self.current_step >= 0 and self.current_step < len(self.steps):
                    if self.steps[self.current_step]["status"] == "running":
                        self.steps[self.current_step]["status"] = "passed"
            else:
                if self.current_step >= 0 and self.current_step < len(self.steps):
                    if self.steps[self.current_step]["status"] == "running":
                        self.steps[self.current_step]["status"] = "failed"
                        self.steps[self.current_step]["result"] = stripped

        # Backup end-of-test triggers
        if "Scheduler off" in stripped or "FS thread dead" in stripped:
            self.iteration_done = True

    def init_steps(self, case_steps: list[dict]):
        """Initialise step tracker for a new iteration."""
        with self._lock:
            self.iteration_done = False   # <-- Add this flag
            self.steps = _build_step_tracker(case_steps)
            self.current_step = -1
            self._expected_funcs = [
                _FUNC_PRINTS.get(s.get("type", ""), "") for s in case_steps
            ]
            self._func_cursor = 0

    def reset(self):
        self.close_log_file()
        with self._lock:
            self.iteration_done = False   # <-- Add this flag
            self.running = False
            self.process = None
            self.log_lines = []
            self.current_iteration = 0
            self.total_iterations = 1
            self.status = "idle"
            self.started_at = None
            self.case_name = ""
            self.run_id = ""
            self.steps = []
            self.current_step = -1
            self._expected_funcs = []
            self._func_cursor = 0
            self.fail_reason = ""
            self.log_file = ""
            self.device_name = ""
            self.utt_root = ""
            self.run_logs_dir = ""
            self.history = []


def _find_latest_run_logs_dir(utt_root: str, device_name: str = "") -> str:
    """Resolve the newest UTT run Logs directory, optionally filtered by device name."""
    reports_dir = os.path.join(utt_root, "Reports")
    if not os.path.isdir(reports_dir):
        return ""

    try:
        entries = [
            d for d in os.listdir(reports_dir)
            if os.path.isdir(os.path.join(reports_dir, d)) and d.startswith("Report_")
        ]
    except Exception:
        return ""

    if device_name:
        prefix = f"Report_{device_name}_"
        filtered = [d for d in entries if d.startswith(prefix)]
        if filtered:
            entries = filtered

    entries.sort(key=lambda d: os.path.getmtime(os.path.join(reports_dir, d)), reverse=True)

    for folder in entries:
        logs_dir = os.path.join(reports_dir, folder, "Logs")
        if os.path.isdir(logs_dir):
            return logs_dir

    return reports_dir


_run = RunState()
_ws_clients: set[WebSocket] = set()


def _force_kill_process_tree(proc: Optional[subprocess.Popen]):
    """Force-kill runner process and ALL children (especially on Windows)."""
    if not proc:
        return
    pid = proc.pid
    try:
        if os.name == "nt":
            # Always attempt taskkill regardless of poll() — children may survive
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                timeout=10,
            )
        else:
            proc.kill()
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass
    # Reap the process so it doesn't become a zombie
    try:
        proc.wait(timeout=3)
    except Exception:
        pass


def _get_protected_pids() -> set[str]:
    """Return a set of PID strings that must never be killed (server + ancestors)."""
    protected = {str(os.getpid())}
    try:
        import psutil
        proc = psutil.Process(os.getpid())
        for parent in proc.parents():
            protected.add(str(parent.pid))
    except Exception:
        # psutil may not be installed; fall back to PowerShell parent lookup
        try:
            ps_cmd = (
                f"(Get-CimInstance Win32_Process -Filter \"ProcessId={os.getpid()}\""
                ").ParentProcessId"
            )
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps_cmd],
                capture_output=True, text=True, timeout=10, check=False,
            )
            ppid = result.stdout.strip()
            if ppid and ppid.isdigit():
                protected.add(ppid)
        except Exception:
            pass
    return protected


def _nuke_all_universal_tester_tool_processes():
    """Kill every Python process whose command-line references the UTT launcher.

    Uses PowerShell's Get-CimInstance (reliable, unlike deprecated wmic) to find
    orphaned processes, then taskkill /F each one.  Carefully excludes the
    server process and all its ancestors so the toolkit stays alive.
    """
    if os.name != "nt":
        return
    protected = _get_protected_pids()
    try:
        # Only match processes that are clearly UTT launcher invocations
        ps_cmd = (
            "Get-CimInstance Win32_Process -Filter \"Name='python.exe' or Name='python3.exe' or Name='pythonw.exe'\" "
            "| Where-Object { $_.CommandLine -match 'launcher\\.py.*universal-tester-tool|universal-tester-tool.*launcher\\.py' } "
            "| Select-Object -ExpandProperty ProcessId"
        )
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_cmd],
            capture_output=True, text=True, timeout=15, check=False,
        )
        for line in result.stdout.strip().splitlines():
            pid = line.strip()
            if pid and pid.isdigit() and pid not in protected:
                subprocess.run(
                    ["taskkill", "/PID", pid, "/F"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    check=False, timeout=10,
                )
    except Exception:
        pass


# ── YAML generation ────────────────────────────────────────────────

# Regex metacharacters that need escaping so UTT compiles them as literals.
_REGEX_META = _re.compile(r'(%\w+%)|([\[\](){}.*+?^$|\\])')


def _format_output_for_yaml(output: str, match_type: str = "loose") -> str:
    """
    Format the output string for YAML compilation based on match_type.
    - loose (default): escapes regex metacharacters, matches anywhere in the string.
    - strict: escapes regex metacharacters, but forces an exact line match using anchors.
    - regex: treats the input as raw regex, only double-escaping backslashes for YAML parsing.
    """
    if match_type == "regex":
        # Just double-escape backslashes for the YAML parser
        return output.replace("\\", "\\\\")

    # For strict/loose, we escape regex metacharacters but preserve %var% placeholders
    def _replacer(m: _re.Match) -> str:
        if m.group(1):          
            return m.group(1)
        return "\\\\" + m.group(2)
        
    escaped = _REGEX_META.sub(_replacer, output)

    if match_type == "strict":
        # Anchors force full line match. \s* allows for trailing \r or \n
        return f"^\\\\s*{escaped}\\\\s*$"
        
    return escaped
def _generate_interfaces_yaml(case: dict) -> str:
    iface = case.get("interfaces", {})
    port = iface.get("terminal_port", "COM7")
    baudrate = iface.get("baudrate", 115200)
    lines = [
        '- !Interfaces',
        '    serial:',
        '    - !Serial',
        '        name: "Terminal"',
        f'        port: "{port}"',
        f'        baudrate: {baudrate}',
        '        parity: "None"',
        '        data_bits: 8',
        '        stop_bits: 1',
        '        tx_end_line: "\\r"',
        '        rx_end_line: "\\r"',
    ]

    catcher_port = iface.get("catcher_port", "")
    if catcher_port:
        lines += [
            '    - !Serial',
            '        name: "Catcher"',
            f'        port: "{catcher_port}"',
            '        baudrate: 115200',
            '        parity: "None"',
            '        data_bits: 8',
            '        stop_bits: 1',
            '        tx_end_line: "\\r"',
            '        rx_end_line: "\\n\\0"',
        ]

    use_otii = iface.get("use_otii", False)
    if use_otii:
        lines += [
            '    ppk:',
            '    - !Ppk',
            '        name: "PPK"',
        ]

    return "\n".join(lines) + "\n"


def _generate_settings_yaml(case: dict) -> str:
    name = case.get("device_name", "FMB_Device")
    fw = case.get("firmware", "03.29.00")
    test_loc = case.get("_test_main_path", "test_main.yaml")
    return (
        f'- !DUT_settings\n'
        f'    name: "{name}"\n'
        f'    hw: "None"\n'
        f'    fw: "{fw}"\n'
        f'    test_loc: "{test_loc}"\n'
    )


def _step_to_yaml_func(step: dict) -> str:
    """Convert a single UI step to a YAML !Func block."""
    t = step["type"]
    lines = []

    if t == "power_off":
        lines = [
            '- !Func',
            '    func: "OtiiSetOut"',
            f'    resource: "{step.get("resource", "PPK")}"',
            '    state: False',
            f'    timeout: {step.get("timeout", 40)}',
            f'    retry: {step.get("retry", 1)}',
            f'    Error_level: "{step.get("error_level", "Warning")}"',
        ]
    elif t == "power_on":
        lines = [
            '- !Func',
            '    func: "OtiiSetOut"',
            f'    resource: "{step.get("resource", "PPK")}"',
            '    state: True',
            f'    timeout: {step.get("timeout", 40)}',
            f'    retry: {step.get("retry", 1)}',
            f'    Error_level: "{step.get("error_level", "Warning")}"',
        ]
    elif t == "send_command":
        lines = [
            '- !Func',
            '    func: "UartWrite"',
            f'    resource: "{step.get("resource", "Terminal")}"',
            f'    input: "{step.get("input", "")}"',
            f'    timeout: {step.get("timeout", 40)}',
            f'    retry: {step.get("retry", 1)}',
            f'    Error_level: "{step.get("error_level", "Warning")}"',
        ]
    elif t == "read_response":
        match_type = step.get("match_type", "loose")
        output = _format_output_for_yaml(step.get("output", ""), match_type)
        lines = [
            '- !Func',
            '    func: "UartRead"',
            f'    resource: "{step.get("resource", "Terminal")}"',
            f'    output: "{output}"',
        ]
        args = step.get("args", [])
        if not args:
            import re as _re
            n_vars = len(_re.findall(r'%\w+%', output))
            args = ["NaN"] * max(n_vars, 1)
        lines.append('    args:')
        for a in args:
            lines.append(f'        - "{a}"')
        lines += [
            f'    timeout: {step.get("timeout", 40)}',
            f'    retry: {step.get("retry", 1)}',
            f'    Error_level: "{step.get("error_level", "Warning")}"',
        ]
    elif t == "send_and_verify":
        match_type = step.get("match_type", "loose")
        output = _format_output_for_yaml(step.get("output", ""), match_type)
        lines = [
            '- !Func',
            '    func: "UartWriteRead"',
            f'    resource: "{step.get("resource", "Terminal")}"',
            f'    input: "{step.get("input", "")}"',
            f'    output: "{output}"',
        ]
        args = step.get("args", [])
        if not args:
            # Count %var% placeholders in output; if none, still need one arg
            import re as _re
            n_vars = len(_re.findall(r'%\w+%', output))
            args = ["NaN"] * max(n_vars, 1)
        lines.append('    args:')
        for a in args:
            lines.append(f'        - "{a}"')
        lines += [
            f'    timeout: {step.get("timeout", 40)}',
            f'    retry: {step.get("retry", 1)}',
            f'    Error_level: "{step.get("error_level", "Warning")}"',
        ]
    elif t == "delay":
        delay_val = step.get("delay", 5)
        timeout_val = step.get("timeout", 40)
        
        # Prevent premature step failure: timeout must be strictly larger than the delay duration
        if timeout_val <= delay_val:
            timeout_val = delay_val + 5
            
        lines = [
            '- !Func',
            '    func: "Delay"',
            '    resource: "OS"',
            f'    delay: {delay_val}',
            f'    timeout: {timeout_val}',
            f'    retry: {step.get("retry", 1)}',
            f'    Error_level: "{step.get("error_level", "Warning")}"',
        ]
    elif t == "read_catcher":
        lines = [
            '- !Func',
            '    func: "UartRead"',
            '    resource: "Catcher"',
            f'    source: "{step.get("source", "")}"',
            f'    destination: "{step.get("destination", "")}"',
            f'    SAP: "{step.get("SAP", "")}"',
            f'    msg_id: "{step.get("msg_id", "")}"',
        ]
        args = step.get("args", [])
        if not args:
            args = ["NaN"]
        lines.append('    args:')
        for a in args:
            lines.append(f'        - "{a}"')
        lines += [
            f'    timeout: {step.get("timeout", 40)}',
            f'    retry: {step.get("retry", 1)}',
            f'    Error_level: "{step.get("error_level", "Warning")}"',
        ]

    return "\n".join(lines)


def _generate_test_yaml(steps: list[dict]) -> str:
    """Generate the individual test YAML from steps."""
    blocks = []
    for step in steps:
        block = _step_to_yaml_func(step)
        if block:
            blocks.append(block)
    return "\n".join(blocks) + "\n"


def _generate_test_main_yaml(case: dict, test_file_rel: str) -> str:
    """Generate test_main.yaml.

    run_time controls the *internal* loop of the Universal Tester Tool engine
    ("0s" = run once, "30m" = keep running for 30 min, etc.).
    Our external iteration loop re-launches the process N times.
    """
    run_time = case.get("run_time", "0s")

    lines = [
        '- !Test_Overview',
        '    write_to_file_everything: True',
        f'    test_run_time: "{run_time}"',
        '    test_routines:',
        '    - !Test_setting',
        f'        name: {case.get("name", "TestCase")}',
        f'        file: "{test_file_rel}"',
    ]
    return "\n".join(lines) + "\n"


def _prepare_run_directory(case: dict) -> dict:
    """Generate all YAML files for a test case and return paths."""
    case_id = case.get("id", str(uuid.uuid4())[:8])
    run_dir = os.path.join(GENERATED_DIR, case_id)
    os.makedirs(run_dir, exist_ok=True)

    utt_root = _resolve_utt_root(
        config.load().get("universal_tester_tool_path", _DEFAULT_UNIVERSAL_TESTER_TOOL_PATH)
    )

    # Test steps YAML
    test_yaml = _generate_test_yaml(case.get("steps", []))
    test_file = os.path.join(run_dir, "test_steps.yaml")
    with open(test_file, "w", encoding="utf-8") as f:
        f.write(test_yaml)

    # Calculate relative path from utt_root
    test_file_rel = os.path.relpath(test_file, utt_root).replace("\\", "/")

    # test_main.yaml
    test_main_yaml = _generate_test_main_yaml(case, test_file_rel)
    test_main_file = os.path.join(run_dir, "test_main.yaml")
    with open(test_main_file, "w", encoding="utf-8") as f:
        f.write(test_main_yaml)

    # Store the test_main path for settings.yaml
    test_main_rel = os.path.relpath(test_main_file, utt_root).replace("\\", "/")
    case["_test_main_path"] = test_main_rel

    # interfaces.yaml
    iface_yaml = _generate_interfaces_yaml(case)
    iface_file = os.path.join(run_dir, "interfaces.yaml")
    with open(iface_file, "w", encoding="utf-8") as f:
        f.write(iface_yaml)

    # settings.yaml
    settings_yaml = _generate_settings_yaml(case)
    settings_file = os.path.join(run_dir, "settings.yaml")
    with open(settings_file, "w", encoding="utf-8") as f:
        f.write(settings_yaml)

    # interfaces_desc.yaml - tells the Universal Tester Tool engine to store serial output to file
    iface_desc_lines = ['- !Description', '    name: "Terminal"', '    action: "store"']
    iface = case.get("interfaces", {})
    if iface.get("catcher_port"):
        iface_desc_lines += ['- !Description', '    name: "Catcher"', '    action: "store"']
    iface_desc_file = os.path.join(run_dir, "interfaces_desc.yaml")
    with open(iface_desc_file, "w", encoding="utf-8") as f:
        f.write("\n".join(iface_desc_lines) + "\n")

    return {
        "run_dir": run_dir,
        "utt_root": utt_root,
        "run_dir_rel": os.path.relpath(run_dir, utt_root).replace("\\", "/") + "/",
    }


# ── Test runner ─────────────────────────────────────────────────────

def _run_test_thread(case: dict, paths: dict, my_run_id: str):
    """Run the Universal Tester Tool engine in a background thread."""
    global _run
    utt_root = paths["utt_root"]
    run_dir_rel = paths["run_dir_rel"]

    # --- Create ONE UTT report directory for the whole run ---
    device_name = case.get("device_name", "FMB_Device")
    current_date = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    utt_report_dir = os.path.join(utt_root, "Reports", f"Report_{device_name}_{current_date}_id_{my_run_id}")
    os.makedirs(os.path.join(utt_report_dir, "Logs"), exist_ok=True)

    iterations = case.get("iterations", 1)
    _run.total_iterations = iterations

    for iteration in range(1, iterations + 1):
        if not _run.running:
            break

        # --- At the end of the previous iteration, snapshot the results for the UI history ---
        if iteration > 1:
            with _run._lock:
                # Get the final state of the previous iteration's steps
                last_steps = list(_run.steps)
                _run.history.append({
                    "iteration": iteration - 1,
                    "steps": last_steps,
                    "passed": all(s.get("status") == "passed" for s in last_steps)
                })

        _run.current_iteration = iteration
        _run.init_steps(case.get("steps", []))
        _run.append_log(f"\n{'='*60}")
        _run.append_log(f"  ITERATION {iteration}/{iterations}")
        _run.append_log(f"{'='*60}\n")

        launcher = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "universal-tester-tool", "launcher.py",
        )
        cmd = [
            sys.executable, "-u", launcher,
            "-a", "test",
            "-p", run_dir_rel,
            "--output_dir", utt_report_dir,
        ]
        _run.append_log(f"[CMD] {' '.join(cmd)}")
        _run.append_log(f"[CWD] {utt_root}")
        _run.append_log(f"[CFG] run_dir_rel={run_dir_rel}")

        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        env["UNIVERSAL_TESTER_TOOL_ROOT"] = utt_root

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                cwd=utt_root,
                env=env,
                bufsize=1,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
            )
            _run.process = proc

            # Non-blocking readline via a reader thread so we can
            # detect hangs and honour stop requests without blocking.
            import queue as _queue
            _line_q: _queue.Queue = _queue.Queue()

            def _reader():
                try:
                    for ln in iter(proc.stdout.readline, ""):
                        _line_q.put(ln)
                except Exception:
                    pass
                _line_q.put(None)  # sentinel

            _reader_t = threading.Thread(target=_reader, daemon=True)
            _reader_t.start()

            _no_output_since = time.time()
            while True:
                if not _run.running:
                    break
                
                # THE NUCLEAR OPTION: If the test logic has finished but Windows locked the COM port,
                # we purposefully execute the Stop & Kill function and break the loop to move to the next iteration.
                if getattr(_run, 'iteration_done', False):
                    time.sleep(1)  # Let any final logging statements flush
                    _run.append_log("\n[TOOLKIT] Test logic complete. Forcefully terminating deadlocked subprocess...")
                    _force_kill_process_tree(proc)
                    _nuke_all_universal_tester_tool_processes()
                    break

                try:
                    line = _line_q.get(timeout=1)
                except _queue.Empty:
                    # No output for 1s — check if process died naturally
                    if proc.poll() is not None:
                        break
                    continue
                    
                if line is None:
                    break  # pipe closed
                
                _no_output_since = time.time()
                stripped = line.rstrip()
                if stripped:
                    _run.append_log(stripped)

                    # Fail fast on busy/unavailable COM ports with actionable guidance.
                    if "Failed to open COM" in stripped or "could not open port" in stripped:
                        _run.append_log("[ACTION] COM port is busy or locked by another tool.")
                        _run.append_log("[ACTION] Close any program using the port (e.g. PuTTY, Catcher, another terminal), then press NUKE RESET and retry.")
                        if _run.run_id == my_run_id:
                            with _run._lock:
                                for s in _run.steps:
                                    if s["status"] == "running":
                                        s["status"] = "failed"
                                        s["result"] = "COM port busy"
                                _run.status = "failed"
                                _run.fail_reason = "com_port"
                                _run.running = False
                        _force_kill_process_tree(proc)
                        return

            # Clean up process
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                try:
                    proc.wait(timeout=2)
                except Exception:
                    pass
            except Exception:
                pass
                
            exit_code = proc.returncode

            all_steps_passed = all(
                s["status"] == "passed" for s in _run.steps
            ) if _run.steps else False

            if _run.run_id == my_run_id:
                _run.append_log(f"[EXIT] Process exited with code {exit_code}")

            # If we nuked it because it finished, exit_code will be non-zero (like 1 or -9). 
            # We must ignore the non-zero exit code if iteration_done is True.
            is_done = getattr(_run, 'iteration_done', False)
            if exit_code != 0 and _run.running and _run.run_id == my_run_id and not is_done and not all_steps_passed:
                _run.append_log(f"[FAIL] Subprocess crashed on iteration {iteration}")
                with _run._lock:
                    for s in _run.steps:
                        if s["status"] == "running":
                            s["status"] = "failed"
                            s["result"] = f"Process exited with code {exit_code}"
                    _run.status = "failed"
                    _run.running = False
                return  # stop iterating
            # Clean up process — let it exit naturally.  The UTT engine
            # should exit within ~1-2s after the test finishes.
            try:
                proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                proc.kill()
                try:
                    proc.wait(timeout=5)
                except Exception:
                    pass
            except Exception:
                pass
            exit_code = proc.returncode

            # Check if all steps in this iteration actually passed.
            # The UTT engine doesn't use meaningful exit codes — we parse
            # step results from stdout, so trust those over the exit code.
            all_steps_passed = all(
                s["status"] == "passed" for s in _run.steps
            ) if _run.steps else False

            # Only log if we're still the active run (stop/nuke may have reset us).
            if _run.run_id == my_run_id:
                _run.append_log(f"[EXIT] Process exited with code {exit_code}")

            if exit_code != 0 and _run.running and _run.run_id == my_run_id and not all_steps_passed:
                _run.append_log(f"[FAIL] Subprocess crashed on iteration {iteration}")
                # Mark any in-progress step as failed
                with _run._lock:
                    for s in _run.steps:
                        if s["status"] == "running":
                            s["status"] = "failed"
                            s["result"] = f"Process exited with code {exit_code}"
                    _run.status = "failed"
                    _run.running = False
                return  # stop iterating

        except Exception as e:
            if _run.run_id != my_run_id:
                return
            _run.append_log(f"[ERROR] {e}")
            with _run._lock:
                for s in _run.steps:
                    if s["status"] == "running":
                        s["status"] = "failed"
                        s["result"] = str(e)
                _run.status = "failed"
                _run.running = False
            return

    with _run._lock:
        # Only update state if this thread's run is still the active one
        if _run.run_id != my_run_id:
            return  # a reset/stop already wiped our run — don't overwrite
        if _run.running:
            _run.status = "completed"
            _run.append_log("\n[DONE] All iterations completed successfully.")
        else:
            _run.status = "stopped"
            _run.append_log("\n[STOPPED] Test was stopped by user.")
        _run.running = False

    # Safely close the real-time file stream
    _run.close_log_file()

    # Save terminal log to file
    _save_log_file()


def _save_log_file():
    """Write all captured log lines to a timestamped file."""
    if not _run.log_lines:
        return
    cfg = config.load()
    log_dir = cfg.get("universal_tester_tool_log_dir", os.path.join(ROOT, "output", "universal_tester_tool_logs"))
    os.makedirs(log_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    case_slug = _run.case_name.replace(" ", "_")[:30] if _run.case_name else "unknown"
    fname = f"{ts}_{case_slug}.log"
    fpath = os.path.join(log_dir, fname)
    try:
        with open(fpath, "w", encoding="utf-8") as f:
            f.write("\n".join(_run.log_lines))
        _run.log_file = fpath
        _run.append_log(f"[LOG] Saved to {fpath}")
    except Exception as e:
        _run.append_log(f"[LOG] Failed to save log: {e}")


# ── Pydantic models ─────────────────────────────────────────────────

class TestCaseIn(BaseModel):
    name: str
    device_name: str = "FMB_Device"
    firmware: str = "03.29.00"
    run_time: str = "0s"
    iterations: int = 1
    interfaces: dict = {}
    steps: list[dict] = []


class RunRequest(BaseModel):
    case_id: str


# ── Plugin class ────────────────────────────────────────────────────

class UniversalTesterToolPlugin(ToolkitPlugin):
    id = "universal_tester_tool"
    name = "Universal Tester Tool"
    icon = "🧪"
    order = 15

    def register_routes(self, app: FastAPI):

        # ── Step catalog ────────────────────────────────────────
        @app.get("/api/universal_tester_tool/catalog")
        async def get_catalog():
            return STEP_CATALOG

        # ── Universal Tester Tool configuration ───────────────

        @app.get("/api/universal_tester_tool/config")
        async def get_universal_tester_tool_config():
            cfg = config.load()
            return {
                "universal_tester_tool_path": cfg.get("universal_tester_tool_path", _DEFAULT_UNIVERSAL_TESTER_TOOL_PATH),
                "universal_tester_tool_log_dir": cfg.get("universal_tester_tool_log_dir", os.path.join(ROOT, "output", "universal_tester_tool_logs")),
            }

        @app.put("/api/universal_tester_tool/config")
        async def update_universal_tester_tool_config(body: dict):
            updates = {}
            if "universal_tester_tool_path" in body:
                p = body["universal_tester_tool_path"].strip()
                if p:
                    updates["universal_tester_tool_path"] = p
            if "universal_tester_tool_log_dir" in body:
                p = body["universal_tester_tool_log_dir"].strip()
                if p:
                    updates["universal_tester_tool_log_dir"] = p
            if updates:
                config.save(updates)
            cfg = config.load()
            return {
                "universal_tester_tool_path": cfg.get("universal_tester_tool_path", _DEFAULT_UNIVERSAL_TESTER_TOOL_PATH),
                "universal_tester_tool_log_dir": cfg.get("universal_tester_tool_log_dir", os.path.join(ROOT, "output", "universal_tester_tool_logs")),
            }

        # ── CRUD for test cases ─────────────────────────────────

        @app.get("/api/universal_tester_tool/cases")
        async def list_cases():
            cases = []
            for fname in sorted(os.listdir(CASES_DIR)):
                if fname.endswith(".json"):
                    fpath = os.path.join(CASES_DIR, fname)
                    try:
                        with open(fpath, "r", encoding="utf-8") as f:
                            data = json.load(f)
                        cases.append({
                            "id": data.get("id", fname[:-5]),
                            "name": data.get("name", fname[:-5]),
                            "device_name": data.get("device_name", ""),
                            "steps_count": len(data.get("steps", [])),
                            "iterations": data.get("iterations", 1),
                        })
                    except Exception:
                        pass
            return cases

        @app.get("/api/universal_tester_tool/cases/{case_id}")
        async def get_case(case_id: str):
            fpath = os.path.join(CASES_DIR, f"{case_id}.json")
            if not os.path.exists(fpath):
                from fastapi import HTTPException
                raise HTTPException(404, "Test case not found")
            with open(fpath, "r", encoding="utf-8") as f:
                return json.load(f)

        @app.post("/api/universal_tester_tool/cases")
        async def save_case(body: TestCaseIn):
            case_id = body.name.replace(" ", "_").lower()[:40]
            # Sanitize case_id: only allow alphanumeric, underscore, dash
            import re
            case_id = re.sub(r"[^a-zA-Z0-9_\-]", "", case_id)
            if not case_id:
                case_id = str(uuid.uuid4())[:8]
            data = body.dict()
            data["id"] = case_id
            data["updated_at"] = datetime.now().isoformat()
            fpath = os.path.join(CASES_DIR, f"{case_id}.json")
            with open(fpath, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            # Return the full saved case so the frontend can sync
            return data

        @app.delete("/api/universal_tester_tool/cases/{case_id}")
        async def delete_case(case_id: str):
            import re
            if not re.match(r"^[a-zA-Z0-9_\-]+$", case_id):
                from fastapi import HTTPException
                raise HTTPException(400, "Invalid case ID")
            fpath = os.path.join(CASES_DIR, f"{case_id}.json")
            if os.path.exists(fpath):
                os.remove(fpath)
                return {"status": "deleted"}
            from fastapi import HTTPException
            raise HTTPException(404, "Test case not found")

        # ── Preview generated YAML ──────────────────────────────

        @app.post("/api/universal_tester_tool/preview")
        async def preview_yaml(body: TestCaseIn):
            data = body.dict()
            data["id"] = "preview"
            return {
                "interfaces": _generate_interfaces_yaml(data),
                "settings": _generate_settings_yaml(data),
                "test_steps": _generate_test_yaml(data.get("steps", [])),
                "test_main": _generate_test_main_yaml(data, "generated/preview/test_steps.yaml"),
            }

        # ── Run controls ────────────────────────────────────────

        @app.post("/api/universal_tester_tool/run/{case_id}")
        async def start_run(case_id: str):
            global _run
            if _run.running:
                from fastapi import HTTPException
                raise HTTPException(409, "A test is already running")

            import re
            if not re.match(r"^[a-zA-Z0-9_\-]+$", case_id):
                from fastapi import HTTPException
                raise HTTPException(400, "Invalid case ID")

            fpath = os.path.join(CASES_DIR, f"{case_id}.json")
            if not os.path.exists(fpath):
                from fastapi import HTTPException
                raise HTTPException(404, "Test case not found")

            with open(fpath, "r", encoding="utf-8") as f:
                case = json.load(f)

            utt_root = _resolve_utt_root(
                config.load().get("universal_tester_tool_path", _DEFAULT_UNIVERSAL_TESTER_TOOL_PATH)
            )
            if not os.path.isdir(utt_root):
                from fastapi import HTTPException
                raise HTTPException(400, f"Universal Tester Tool path not found: {utt_root}")

            paths = _prepare_run_directory(case)

            _run.reset()
            _run.running = True
            _run.run_id = str(uuid.uuid4())[:8]
            _run.status = "running"
            _run.started_at = datetime.now().isoformat()
            _run.case_name = case.get("name", case_id)
            _run.total_iterations = case.get("iterations", 1)
            _run.device_name = case.get("device_name", "")
            _run.utt_root = utt_root
            _run.run_logs_dir = ""
            _run.init_log_file()
            run_id = _run.run_id
            thread = threading.Thread(target=_run_test_thread, args=(case, paths, run_id), daemon=True)
            thread.start()

            return {"run_id": _run.run_id, "status": "started"}

        @app.post("/api/universal_tester_tool/stop")
        async def stop_run():
            global _run
            if not _run.running and _run.status == "idle":
                return {"status": "idle"}
            # Immediately flip flags so the runner thread exits its loop.
            _run.running = False
            proc = _run.process
            # Fire the heavy kill work in a background thread so this
            # async handler returns instantly and uvicorn stays responsive.
            def _do_nuke():
                _force_kill_process_tree(proc)
                _nuke_all_universal_tester_tool_processes()
            threading.Thread(target=_do_nuke, daemon=True).start()
            _run.reset()
            return {"status": "idle"}

        @app.post("/api/universal_tester_tool/reset")
        async def reset_run():
            global _run
            _run.running = False
            proc = _run.process
            def _do_nuke():
                _force_kill_process_tree(proc)
                _nuke_all_universal_tester_tool_processes()
            threading.Thread(target=_do_nuke, daemon=True).start()
            _run.reset()
            return {"status": "idle"}

        @app.get("/api/universal_tester_tool/status")
        async def get_status():
            if _run.utt_root and not _run.run_logs_dir:
                found_logs_dir = _find_latest_run_logs_dir(_run.utt_root, _run.device_name)
                if found_logs_dir:
                    _run.run_logs_dir = found_logs_dir
            return _run.to_dict()

        @app.post("/api/universal_tester_tool/open_logs_folder")
        async def open_run_logs_folder():
            cfg = config.load()
            utt_root = _run.utt_root or _resolve_utt_root(
                cfg.get("universal_tester_tool_path", _DEFAULT_UNIVERSAL_TESTER_TOOL_PATH)
            )

            logs_dir = _run.run_logs_dir
            if not logs_dir or not os.path.isdir(logs_dir):
                logs_dir = _find_latest_run_logs_dir(utt_root, _run.device_name)

            if not logs_dir or not os.path.isdir(logs_dir):
                from fastapi import HTTPException
                raise HTTPException(404, "Run logs folder was not found")

            try:
                if os.name == "nt":
                    os.startfile(logs_dir)
                elif sys.platform == "darwin":
                    subprocess.Popen(["open", logs_dir])
                else:
                    subprocess.Popen(["xdg-open", logs_dir])
            except Exception as e:
                from fastapi import HTTPException
                raise HTTPException(500, f"Failed to open logs folder: {e}")

            _run.run_logs_dir = logs_dir
            return {"ok": True, "path": logs_dir}

        # ── COM port discovery ──────────────────────────────────

        @app.get("/api/universal_tester_tool/ports")
        async def list_ports():
            try:
                import serial.tools.list_ports
                ports = serial.tools.list_ports.comports()
                return sorted(
                    [{"port": p.device, "desc": p.description}
                     for p in ports],
                    key=lambda x: x["port"],
                )
            except ImportError:
                return []

        # ── WebSocket for live log streaming ────────────────────

        @app.websocket("/ws/universal-tester-tool")
        async def ws_universal_tester_tool(ws: WebSocket):
            await ws.accept()
            _ws_clients.add(ws)
            # Start from current length so the HTTP status fetch (log_tail)
            # handles initial log population without the WS duplicating it.
            last_len = len(_run.log_lines)
            try:
                while True:
                    await asyncio.sleep(1)
                    state = _run.to_dict()
                    logs = state.pop("log_tail", [])
                    # Only send new lines
                    if len(_run.log_lines) > last_len:
                        new_lines = _run.log_lines[last_len:]
                        last_len = len(_run.log_lines)
                        state["new_lines"] = new_lines
                    else:
                        state["new_lines"] = []
                    await ws.send_json(state)
            except (WebSocketDisconnect, Exception):
                pass
            finally:
                _ws_clients.discard(ws)

    def startup(self):
        pass

    def shutdown(self):
        global _run
        if _run.running:
            _run.running = False
            proc = _run.process
            if proc and proc.poll() is None:
                try:
                    proc.terminate()
                except Exception:
                    pass


import asyncio

plugin = UniversalTesterToolPlugin()

