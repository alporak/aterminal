# main.py

import sys
from PySide6.QtWidgets import QApplication
from gui.main_window import MainWindow
from core.theme_manager import ThemeManager

if __name__ == '__main__':
    app = QApplication(sys.argv)
    
    # Apply theme before creating any UI elements
    ThemeManager.apply_theme(app)
    
    # You can add global exception handling here if needed
    
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec())