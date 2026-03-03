import subprocess
import sys
import webbrowser
import ctypes
from pathlib import Path
import pystray
from PIL import Image, ImageDraw

# Get the directory where this script is located
SCRIPT_DIR = Path(__file__).parent
STREAMLIT_URL = "http://localhost:8501"

def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False

def relaunch_self_as_admin():
    try:
        result = ctypes.windll.shell32.ShellExecuteW(
            None,
            "runas",
            sys.executable,
            f'"{Path(__file__).resolve()}"',
            str(SCRIPT_DIR),
            1,
        )
        return result > 32
    except Exception:
        return False

class StreamlitTrayApp:
    def __init__(self):
        self.process = None
        self.icon = None
        
    def create_icon_image(self):
        """Create a simple icon for the system tray"""
        width = 64
        height = 64
        image = Image.new('RGB', (width, height), color='#3B8ED0')
        dc = ImageDraw.Draw(image)
        
        # Draw a simple "S" shape
        dc.text((20, 20), "ST", fill='white')
        
        return image
    
    def start_streamlit(self):
        """Start the Streamlit server (multi-page toolkit)"""
        if self.process is None or self.process.poll() is not None:
            print("Starting Streamlit...")
            self.process = subprocess.Popen(
                [sys.executable, "-m", "streamlit", "run", "Home.py", 
                 "--server.headless=true"],
                cwd=SCRIPT_DIR,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
            )
            print("Streamlit started!")
    
    def stop_streamlit(self):
        """Stop the Streamlit server"""
        if self.process:
            print("Stopping Streamlit...")
            self.process.terminate()
            self.process.wait()
            self.process = None
            print("Streamlit stopped!")
    
    def open_browser(self, icon, item):
        """Open Streamlit in browser"""
        webbrowser.open(STREAMLIT_URL)
    
    def restart(self, icon, item):
        """Restart Streamlit"""
        self.stop_streamlit()
        self.start_streamlit()
    
    def quit_app(self, icon, item):
        """Quit the application"""
        self.stop_streamlit()
        icon.stop()
    
    def run(self):
        """Run the system tray application"""
        # Start Streamlit
        self.start_streamlit()
        
        # Create system tray icon
        menu = pystray.Menu(
            pystray.MenuItem("Open Toolkit Webpage", self.open_browser, default=True),
            pystray.MenuItem("Restart", self.restart),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", self.quit_app)
        )
        
        self.icon = pystray.Icon(
            "alps_toolkit",
            self.create_icon_image(),
            "Alps Toolkit - Streamlit",
            menu
        )
        
        # Run the icon (this blocks until quit)
        self.icon.run()

if __name__ == "__main__":
    if not is_admin():
        if relaunch_self_as_admin():
            sys.exit(0)
    app = StreamlitTrayApp()
    app.run()
