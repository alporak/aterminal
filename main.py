# main.py

import sys
from PySide6.QtWidgets import QApplication
from gui.main_window import MainWindow

if __name__ == '__main__':
    app = QApplication(sys.argv)
    
    # You can add global exception handling here if needed
    
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec())