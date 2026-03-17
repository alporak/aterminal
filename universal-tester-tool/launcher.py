"""
Launcher wrapper for universal-tester-tool.
Stubs out BLE driver imports (pc_ble_driver_py / blatann) so the tester
can run on systems without a Nordic BLE dongle.
"""
import sys
import os
from types import ModuleType


def _make_mock(name):
    m = ModuleType(name)
    m.__path__ = []          # pretend it's a package
    m.__all__ = []
    sys.modules[name] = m
    return m


# Build minimal stub tree so  `from blatann import BleDevice` etc. resolve.
_STUBS = [
    "pc_ble_driver_py",
    "pc_ble_driver_py.config",
    "blatann",
    "blatann.nrf",
    "blatann.nrf.nrf_types",
    "blatann.nrf.nrf_types.gap",
    "blatann.nrf.nrf_events",
    "blatann.gap",
    "blatann.gap.gap_types",
]

for s in _STUBS:
    _make_mock(s)

# Provide the symbols that are actually referenced at import time
sys.modules["blatann"].BleDevice = type("BleDevice", (), {})
sys.modules["blatann.gap.gap_types"].ConnectionParameters = type(
    "ConnectionParameters", (), {}
)

# ── now run the real main.py ──────────────────────────────────────────
# argv is forwarded as-is (launcher.py replaces main.py in the command)
universal_tester_tool_root = os.environ.get("UNIVERSAL_TESTER_TOOL_ROOT") or os.path.dirname(os.path.abspath(__file__))
# If UNIVERSAL_TESTER_TOOL_ROOT is relative, resolve it safely.
if not os.path.isabs(universal_tester_tool_root):
    cwd_resolved = os.path.abspath(universal_tester_tool_root)
    repo_resolved = os.path.abspath(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", universal_tester_tool_root)
    )
    if os.path.isdir(cwd_resolved):
        universal_tester_tool_root = cwd_resolved
    elif os.path.isdir(repo_resolved):
        universal_tester_tool_root = repo_resolved
    else:
        universal_tester_tool_root = cwd_resolved

os.chdir(universal_tester_tool_root)
if universal_tester_tool_root not in sys.path:
    sys.path.insert(0, universal_tester_tool_root)

# Import and let main.py's top-level code execute
import runpy
runpy.run_path(os.path.join(universal_tester_tool_root, "main.py"), run_name="__main__")

