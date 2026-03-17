"""
BTS Tester plugin – Drag/drop test case builder for Universal BTS Tester (FMB).

Generates YAML configs, launches the universal-bts-tester, and monitors runs.
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

from app.plugins.base import ToolkitPlugin
from app import config

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ── Paths ───────────────────────────────────────────────────────────
CASES_DIR = os.path.join(ROOT, "bts-tester", "test_cases")
GENERATED_DIR = os.path.join(ROOT, "bts-tester", "generated")
os.makedirs(CASES_DIR, exist_ok=True)
os.makedirs(GENERATED_DIR, exist_ok=True)

# Default path to the universal-bts-tester installation
_DEFAULT_BTS_PATH = os.path.join(ROOT, "third_party", "universal-bts-tester")

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
            "resource": "Terminal", "output": "", "args": [],
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
            "resource": "Terminal", "input": "", "output": "", "args": [],
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

# Maps step type → the print the bts-tester emits when hitting that func
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
        self.steps: list[dict] = []      # step tracker for the UI
        self.current_step: int = -1      # index into self.steps
        self._expected_funcs: list[str] = []  # expected func-print per step
        self._func_cursor: int = 0       # next expected func-print index
        self._lock = threading.Lock()
        self.fail_reason: str = ""       # 'com_port' | '' — helps UI show guidance
        self.log_file: str = ""          # path to saved log file

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
                "current_step": self.current_step,
                "fail_reason": self.fail_reason,
                "log_file": self.log_file,
            }

    def append_log(self, line: str):
        with self._lock:
            self.log_lines.append(line)
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
        if stripped.startswith("[") and ("PASSED" in stripped or "Warning" in stripped or "Error" in stripped):
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

    def init_steps(self, case_steps: list[dict]):
        """Initialise step tracker for a new iteration."""
        with self._lock:
            self.steps = _build_step_tracker(case_steps)
            self.current_step = -1
            self._expected_funcs = [
                _FUNC_PRINTS.get(s.get("type", ""), "") for s in case_steps
            ]
            self._func_cursor = 0

    def reset(self):
        with self._lock:
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


def _nuke_all_bts_processes():
    """Kill every Python process whose command-line references bts-tester/launcher.

    Uses PowerShell's Get-CimInstance (reliable, unlike deprecated wmic) to find
    orphaned processes, then taskkill /T /F each one.
    """
    if os.name != "nt":
        return
    my_pid = str(os.getpid())
    try:
        # PowerShell one-liner: get PIDs of python processes matching our keywords
        ps_cmd = (
            "Get-CimInstance Win32_Process -Filter \"Name='python.exe' or Name='python3.exe' or Name='pythonw.exe'\" "
            "| Where-Object { $_.CommandLine -match 'launcher\\.py|universal-bts-tester|bts-tester' } "
            "| Select-Object -ExpandProperty ProcessId"
        )
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_cmd],
            capture_output=True, text=True, timeout=15, check=False,
        )
        for line in result.stdout.strip().splitlines():
            pid = line.strip()
            if pid and pid.isdigit() and pid != my_pid:
                subprocess.run(
                    ["taskkill", "/PID", pid, "/T", "/F"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    check=False, timeout=10,
                )
    except Exception:
        pass


# ── YAML generation ────────────────────────────────────────────────

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
        '        rx_end_line: "\\r\\n"',
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
        output = step.get("output", "")
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
        output = step.get("output", "")
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
        lines = [
            '- !Func',
            '    func: "Delay"',
            '    resource: "OS"',
            f'    delay: {step.get("delay", 5)}',
            f'    timeout: {step.get("timeout", 40)}',
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

    run_time controls the *internal* loop of the universal-bts-tester
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

    bts_root = config.load().get("bts_tester_path", _DEFAULT_BTS_PATH)

    # Test steps YAML
    test_yaml = _generate_test_yaml(case.get("steps", []))
    test_file = os.path.join(run_dir, "test_steps.yaml")
    with open(test_file, "w", encoding="utf-8") as f:
        f.write(test_yaml)

    # Calculate relative path from bts_root
    test_file_rel = os.path.relpath(test_file, bts_root).replace("\\", "/")

    # test_main.yaml
    test_main_yaml = _generate_test_main_yaml(case, test_file_rel)
    test_main_file = os.path.join(run_dir, "test_main.yaml")
    with open(test_main_file, "w", encoding="utf-8") as f:
        f.write(test_main_yaml)

    # Store the test_main path for settings.yaml
    test_main_rel = os.path.relpath(test_main_file, bts_root).replace("\\", "/")
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

    # interfaces_desc.yaml – tells bts-tester to store serial output to file
    iface_desc_lines = ['- !Description', '    name: "Terminal"', '    action: "store"']
    iface = case.get("interfaces", {})
    if iface.get("catcher_port"):
        iface_desc_lines += ['- !Description', '    name: "Catcher"', '    action: "store"']
    iface_desc_file = os.path.join(run_dir, "interfaces_desc.yaml")
    with open(iface_desc_file, "w", encoding="utf-8") as f:
        f.write("\n".join(iface_desc_lines) + "\n")

    return {
        "run_dir": run_dir,
        "bts_root": bts_root,
        "run_dir_rel": os.path.relpath(run_dir, bts_root).replace("\\", "/") + "/",
    }


# ── Test runner ─────────────────────────────────────────────────────

def _run_test_thread(case: dict, paths: dict):
    """Run the universal-bts-tester in a background thread."""
    global _run
    bts_root = paths["bts_root"]
    run_dir_rel = paths["run_dir_rel"]

    iterations = case.get("iterations", 1)
    _run.total_iterations = iterations

    for iteration in range(1, iterations + 1):
        if not _run.running:
            break

        _run.current_iteration = iteration
        _run.init_steps(case.get("steps", []))
        _run.append_log(f"\n{'='*60}")
        _run.append_log(f"  ITERATION {iteration}/{iterations}")
        _run.append_log(f"{'='*60}\n")

        # Use our launcher wrapper to stub BLE imports (avoids
        # pc-ble-driver-py native dependency that can't install on Py3.11).
        launcher = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "bts-tester", "launcher.py",
        )
        cmd = [
            sys.executable, "-u", launcher,
            "-app_type", "test",
            "-paths", run_dir_rel,
        ]
        _run.append_log(f"[CMD] {' '.join(cmd)}")
        _run.append_log(f"[CWD] {bts_root}")
        _run.append_log(f"[CFG] run_dir_rel={run_dir_rel}")

        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        env["BTS_ROOT"] = bts_root

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                cwd=bts_root,
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
                try:
                    line = _line_q.get(timeout=2)
                except _queue.Empty:
                    # No output for 2s — check if process died
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

            # Clean up process — it may already be dead from stop/nuke.
            try:
                if proc.poll() is None:
                    proc.kill()
                proc.wait(timeout=5)
            except Exception:
                pass
            exit_code = proc.returncode
            # Only log if we're still the active run (stop/nuke may have reset us).
            if _run.run_id:
                _run.append_log(f"[EXIT] Process exited with code {exit_code}")

            if exit_code != 0 and _run.running:
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
        if _run.running:
            _run.status = "completed"
            _run.append_log("\n[DONE] All iterations completed successfully.")
        else:
            _run.status = "stopped"
            _run.append_log("\n[STOPPED] Test was stopped by user.")
        _run.running = False

    # Save terminal log to file
    _save_log_file()


def _save_log_file():
    """Write all captured log lines to a timestamped file."""
    if not _run.log_lines:
        return
    cfg = config.load()
    log_dir = cfg.get("bts_log_dir", os.path.join(ROOT, "output", "bts_logs"))
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

class BTSTesterPlugin(ToolkitPlugin):
    id = "bts_tester"
    name = "BTS Tester"
    icon = "🧪"
    order = 15

    def register_routes(self, app: FastAPI):

        # ── Step catalog ────────────────────────────────────────
        @app.get("/api/bts_tester/catalog")
        async def get_catalog():
            return STEP_CATALOG

        # ── BTS configuration ──────────────────────────────────

        @app.get("/api/bts_tester/config")
        async def get_bts_config():
            cfg = config.load()
            return {
                "bts_tester_path": cfg.get("bts_tester_path", _DEFAULT_BTS_PATH),
                "bts_log_dir": cfg.get("bts_log_dir", os.path.join(ROOT, "output", "bts_logs")),
            }

        @app.put("/api/bts_tester/config")
        async def update_bts_config(body: dict):
            updates = {}
            if "bts_tester_path" in body:
                p = body["bts_tester_path"].strip()
                if p:
                    updates["bts_tester_path"] = p
            if "bts_log_dir" in body:
                p = body["bts_log_dir"].strip()
                if p:
                    updates["bts_log_dir"] = p
            if updates:
                config.save(updates)
            cfg = config.load()
            return {
                "bts_tester_path": cfg.get("bts_tester_path", _DEFAULT_BTS_PATH),
                "bts_log_dir": cfg.get("bts_log_dir", os.path.join(ROOT, "output", "bts_logs")),
            }

        # ── CRUD for test cases ─────────────────────────────────

        @app.get("/api/bts_tester/cases")
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

        @app.get("/api/bts_tester/cases/{case_id}")
        async def get_case(case_id: str):
            fpath = os.path.join(CASES_DIR, f"{case_id}.json")
            if not os.path.exists(fpath):
                from fastapi import HTTPException
                raise HTTPException(404, "Test case not found")
            with open(fpath, "r", encoding="utf-8") as f:
                return json.load(f)

        @app.post("/api/bts_tester/cases")
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

        @app.delete("/api/bts_tester/cases/{case_id}")
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

        @app.post("/api/bts_tester/preview")
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

        @app.post("/api/bts_tester/run/{case_id}")
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

            bts_root = config.load().get("bts_tester_path", _DEFAULT_BTS_PATH)
            if not os.path.isdir(bts_root):
                from fastapi import HTTPException
                raise HTTPException(400, f"BTS tester path not found: {bts_root}")

            paths = _prepare_run_directory(case)

            _run.reset()
            _run.running = True
            _run.run_id = str(uuid.uuid4())[:8]
            _run.status = "running"
            _run.started_at = datetime.now().isoformat()
            _run.case_name = case.get("name", case_id)
            _run.total_iterations = case.get("iterations", 1)

            thread = threading.Thread(target=_run_test_thread, args=(case, paths), daemon=True)
            thread.start()

            return {"run_id": _run.run_id, "status": "started"}

        @app.post("/api/bts_tester/stop")
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
                _nuke_all_bts_processes()
            threading.Thread(target=_do_nuke, daemon=True).start()
            _run.reset()
            return {"status": "idle"}

        @app.post("/api/bts_tester/reset")
        async def reset_run():
            global _run
            _run.running = False
            proc = _run.process
            def _do_nuke():
                _force_kill_process_tree(proc)
                _nuke_all_bts_processes()
            threading.Thread(target=_do_nuke, daemon=True).start()
            _run.reset()
            return {"status": "idle"}

        @app.get("/api/bts_tester/status")
        async def get_status():
            return _run.to_dict()

        # ── COM port discovery ──────────────────────────────────

        @app.get("/api/bts_tester/ports")
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

        @app.websocket("/ws/bts")
        async def ws_bts(ws: WebSocket):
            await ws.accept()
            _ws_clients.add(ws)
            last_len = 0
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

plugin = BTSTesterPlugin()
