"""Alps Toolkit – entry point.

Run with:
    python run.py          # development (with reload)
    python tray_launcher.py  # production (system tray)
"""

import sys
import socket
import uvicorn
from app.main import create_app

app = create_app()


def _find_free_port(start: int = 8501, end: int = 8599) -> int:
    """Return the first available port in [start, end]."""
    for port in range(start, end + 1):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(1)
                s.bind(("127.0.0.1", port))
            return port
        except OSError:
            continue
    raise RuntimeError(f"No free port in {start}–{end}")


if __name__ == "__main__":
    dev = "--reload" in sys.argv or "--dev" in sys.argv
    port = _find_free_port()
    print(f"Starting on port {port}")
    uvicorn.run(
        "run:app",
        host="127.0.0.1",
        port=port,
        reload=dev,
    )
