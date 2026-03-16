"""
Alps Toolkit – System Tray Launcher

Runs the FastAPI server in a background thread and provides a system tray icon
with controls for:
  • Open in browser
  • View recent logs (last N lines)
  • Restart server
  • Quit

Designed to be launched silently via VBS from shell:startup on Windows.
"""

import io
import os
import sys
import time
import signal
import socket
import ctypes
import logging
import threading
import subprocess
import webbrowser
from collections import deque
from typing import Optional

# ── Ensure project root is on path ──────────────────────────────────
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

try:
    import pystray
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    print("Missing dependencies. Install with:")
    print("  pip install pystray Pillow")
    sys.exit(1)

import uvicorn

# ── Constants ───────────────────────────────────────────────────────
APP_NAME = "Alps Toolkit"
HOST = "127.0.0.1"
PORT_START = 8501          # first port to try
PORT_MAX   = 8599          # give up after this
LOG_BUFFER_SIZE = 500
LOG_WINDOW_LINES = 60

# Resolved at startup by _find_free_port()
_active_port: int = PORT_START


def _find_free_port() -> int:
    """Scan from PORT_START upward and return the first available port."""
    for port in range(PORT_START, PORT_MAX + 1):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(1)
                s.bind((HOST, port))
            return port
        except OSError:
            continue
    raise RuntimeError(
        f"No free port found in range {PORT_START}–{PORT_MAX}"
    )


# ═══════════════════════════════════════════════════════════════════
#  Log capture ring buffer
# ═══════════════════════════════════════════════════════════════════
class RingLogHandler(logging.Handler):
    """Captures log records into a thread-safe ring buffer."""

    def __init__(self, maxlen: int = LOG_BUFFER_SIZE):
        super().__init__()
        self.buffer: deque[str] = deque(maxlen=maxlen)
        self._lock = threading.Lock()

    def emit(self, record: logging.LogRecord):
        try:
            msg = self.format(record)
            with self._lock:
                self.buffer.append(msg)
        except Exception:
            pass

    def get_lines(self, n: int = LOG_WINDOW_LINES) -> list[str]:
        with self._lock:
            items = list(self.buffer)
        return items[-n:]

    def clear(self):
        with self._lock:
            self.buffer.clear()


# Global log handler
_log_handler = RingLogHandler()
_log_handler.setFormatter(logging.Formatter(
    "%(asctime)s [%(levelname)-5s] %(name)s – %(message)s",
    datefmt="%H:%M:%S"
))


# ═══════════════════════════════════════════════════════════════════
#  Server management
# ═══════════════════════════════════════════════════════════════════
class ServerManager:
    """Manages the uvicorn server lifecycle in a background thread."""

    def __init__(self):
        self._server: Optional[uvicorn.Server] = None
        self._thread: Optional[threading.Thread] = None
        self._started = threading.Event()
        self._start_count = 0

    @property
    def running(self) -> bool:
        return (
            self._server is not None
            and self._thread is not None
            and self._thread.is_alive()
            and self._server.started
        )

    @property
    def url(self) -> str:
        return f"http://{HOST}:{_active_port}"

    @property
    def start_count(self) -> int:
        return self._start_count

    def start(self):
        """Start the uvicorn server (non-blocking)."""
        if self.running:
            return

        _log_info("Starting server…")

        config = uvicorn.Config(
            "run:app",
            host=HOST,
            port=_active_port,
            log_level="info",
            access_log=True,
            reload=False,
        )
        self._server = uvicorn.Server(config)

        # Attach our log handler to uvicorn loggers
        for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
            logger = logging.getLogger(name)
            logger.addHandler(_log_handler)
            logger.setLevel(logging.INFO)

        # Also capture root for our own app logs
        root = logging.getLogger()
        root.addHandler(_log_handler)
        root.setLevel(logging.INFO)

        self._started.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="uvicorn")
        self._thread.start()

        # Wait for server to become ready (or timeout)
        self._started.wait(timeout=15)
        self._start_count += 1
        _log_info(f"Server ready at {self.url}")

    def _run(self):
        """Thread target – runs the server."""
        try:
            # We run the asyncio loop inside this thread
            self._server.run()
        except Exception as exc:
            _log_info(f"Server error: {exc}")
        finally:
            self._started.set()

    def stop(self):
        """Gracefully stop the server."""
        if self._server:
            _log_info("Stopping server…")
            self._server.should_exit = True
            if self._thread and self._thread.is_alive():
                self._thread.join(timeout=10)
            self._server = None
            self._thread = None
            _log_info("Server stopped")

    def restart(self):
        """Stop then start."""
        self.stop()
        time.sleep(0.5)
        self.start()


_server_mgr = ServerManager()


def _log_info(msg: str):
    """Quick log helper that also pushes to our ring buffer."""
    record = logging.LogRecord(
        name="tray", level=logging.INFO, pathname="", lineno=0,
        msg=msg, args=(), exc_info=None,
    )
    _log_handler.emit(record)
    print(f"[tray] {msg}")


# ═══════════════════════════════════════════════════════════════════
#  Tray icon generation
# ═══════════════════════════════════════════════════════════════════
def _create_icon_image(running: bool = True) -> Image.Image:
    """Generate a 64x64 tray icon with the TK brand mark."""
    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Background rounded rect
    bg_color = (15, 25, 35, 240)  # --tk-navy
    draw.rounded_rectangle([0, 0, size - 1, size - 1], radius=12, fill=bg_color)

    # Brand "T" mark in green or red
    mark_color = (0, 184, 107) if running else (239, 68, 68)

    # Simplified "T" shape
    # Vertical bar
    draw.rectangle([14, 14, 22, 50], fill=mark_color)
    # Horizontal bars (stylized Lines)
    draw.rectangle([26, 14, 50, 22], fill=mark_color)
    draw.rectangle([26, 27, 46, 35], fill=mark_color)
    draw.rectangle([26, 40, 50, 48], fill=mark_color)

    # Status dot
    dot_color = (0, 184, 107) if running else (239, 68, 68)
    draw.ellipse([48, 48, 62, 62], fill=dot_color, outline=bg_color, width=2)

    return img


# ═══════════════════════════════════════════════════════════════════
#  Log viewer window (simple Tkinter)
# ═══════════════════════════════════════════════════════════════════
def _show_log_window():
    """Open a simple Tkinter window displaying recent logs."""
    try:
        import tkinter as tk
        from tkinter import scrolledtext
    except ImportError:
        _log_info("tkinter not available for log viewer")
        return

    def _refresh():
        text.config(state=tk.NORMAL)
        text.delete("1.0", tk.END)
        lines = _log_handler.get_lines(LOG_WINDOW_LINES)
        text.insert(tk.END, "\n".join(lines) if lines else "(no logs yet)")
        text.see(tk.END)
        text.config(state=tk.DISABLED)

    def _auto_refresh():
        if win.winfo_exists():
            _refresh()
            win.after(2000, _auto_refresh)

    def _clear():
        _log_handler.clear()
        _refresh()

    win = tk.Tk()
    win.title(f"{APP_NAME} – Logs")
    win.geometry("800x500")
    win.configure(bg="#0f1923")

    # Toolbar
    toolbar = tk.Frame(win, bg="#162230", padx=8, pady=4)
    toolbar.pack(fill=tk.X)

    tk.Button(toolbar, text="⟳ Refresh", command=_refresh,
              bg="#1c2d3f", fg="#e8edf2", relief=tk.FLAT,
              padx=10, pady=2).pack(side=tk.LEFT, padx=(0, 4))
    tk.Button(toolbar, text="Clear", command=_clear,
              bg="#1c2d3f", fg="#e8edf2", relief=tk.FLAT,
              padx=10, pady=2).pack(side=tk.LEFT, padx=(0, 4))

    status_label = tk.Label(toolbar, text="", bg="#162230", fg="#8899aa", anchor=tk.E)
    status_label.pack(side=tk.RIGHT)

    def _update_status():
        if win.winfo_exists():
            s = "● Running" if _server_mgr.running else "○ Stopped"
            c = "#00b86b" if _server_mgr.running else "#ef4444"
            status_label.config(text=s, fg=c)
            win.after(3000, _update_status)

    # Log text area
    text = scrolledtext.ScrolledText(
        win, wrap=tk.WORD, state=tk.DISABLED,
        bg="#0f1923", fg="#e8edf2", insertbackground="#e8edf2",
        font=("Consolas", 10), relief=tk.FLAT, borderwidth=0,
        selectbackground="#2a3f55",
    )
    text.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

    _refresh()
    _auto_refresh()
    _update_status()

    win.mainloop()


def _open_log_viewer():
    """Open log viewer in a separate thread so tray stays responsive."""
    t = threading.Thread(target=_show_log_window, daemon=True, name="log-viewer")
    t.start()


# ═══════════════════════════════════════════════════════════════════
#  Tray application
# ═══════════════════════════════════════════════════════════════════
class TrayApp:
    """System tray icon and menu management."""

    def __init__(self):
        self._icon: Optional[pystray.Icon] = None
        self._running = True

    def _build_menu(self) -> pystray.Menu:
        """Build the context menu dynamically."""
        running = _server_mgr.running

        return pystray.Menu(
            pystray.MenuItem(
                f"{'●' if running else '○'} {APP_NAME}",
                None,
                enabled=False,
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "Open in Browser",
                self._on_open_browser,
                default=True,
                enabled=True,
            ),
            pystray.MenuItem(
                "View Logs",
                lambda: _open_log_viewer(),
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "Start Server" if not running else "Server Running",
                self._on_start,
                enabled=not running,
            ),
            pystray.MenuItem(
                "Restart Server",
                self._on_restart,
                enabled=running,
            ),
            pystray.MenuItem(
                "Stop Server",
                self._on_stop,
                enabled=running,
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                f"Port: {_active_port}",
                None,
                enabled=False,
            ),
            pystray.MenuItem(
                f"Restarts: {_server_mgr.start_count}",
                None,
                enabled=False,
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "Quit",
                self._on_quit,
            ),
        )

    def _on_open_browser(self, icon=None, item=None):
        if _server_mgr.running:
            webbrowser.open(_server_mgr.url)
            return

        def _start_and_open():
            self._do_start()
            if _server_mgr.running:
                webbrowser.open(_server_mgr.url)

        threading.Thread(target=_start_and_open, daemon=True).start()

    def _on_start(self):
        threading.Thread(target=self._do_start, daemon=True).start()

    def _on_restart(self):
        threading.Thread(target=self._do_restart, daemon=True).start()

    def _on_stop(self):
        threading.Thread(target=self._do_stop, daemon=True).start()

    def _on_quit(self):
        _log_info("Shutting down…")
        _server_mgr.stop()
        self._running = False
        if self._icon:
            self._icon.stop()

    def _do_start(self):
        _server_mgr.start()
        self._update_icon()

    def _do_restart(self):
        _server_mgr.restart()
        self._update_icon()

    def _do_stop(self):
        _server_mgr.stop()
        self._update_icon()

    def _update_icon(self):
        """Refresh the tray icon image and menu."""
        if self._icon:
            self._icon.icon = _create_icon_image(_server_mgr.running)
            self._icon.menu = self._build_menu()

    def run(self):
        """Main entry point – start server then run tray icon."""
        _log_info(f"{APP_NAME} starting…")

        # Find a free port
        global _active_port
        _active_port = _find_free_port()
        _log_info(f"Using port {_active_port}")

        # Start server
        _server_mgr.start()

        # Create and run tray icon
        self._icon = pystray.Icon(
            name="alps-toolkit",
            icon=_create_icon_image(_server_mgr.running),
            title=f"{APP_NAME} – {_server_mgr.url}",
            menu=self._build_menu(),
        )

        # Open browser on first launch
        if _server_mgr.running:
            threading.Timer(1.5, lambda: webbrowser.open(_server_mgr.url)).start()

        # Periodic icon refresh (to sync status)
        def _periodic_refresh():
            while self._running:
                time.sleep(5)
                try:
                    self._update_icon()
                except Exception:
                    pass

        threading.Thread(target=_periodic_refresh, daemon=True, name="icon-refresh").start()

        _log_info("Tray icon active. Right-click for menu.")
        self._icon.run()


# ═══════════════════════════════════════════════════════════════════
#  Entry point
# ═══════════════════════════════════════════════════════════════════
def main():
    # Hide console window on Windows (if run from pythonw or VBS)
    if sys.platform == "win32":
        try:
            kernel32 = ctypes.windll.kernel32
            hwnd = kernel32.GetConsoleWindow()
            if hwnd:
                ctypes.windll.user32.ShowWindow(hwnd, 0)  # SW_HIDE
        except Exception:
            pass

    app = TrayApp()
    try:
        app.run()
    except KeyboardInterrupt:
        _server_mgr.stop()
    finally:
        _log_info("Exited.")


if __name__ == "__main__":
    main()
