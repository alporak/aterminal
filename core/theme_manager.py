# core/theme_manager.py

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QPalette, QColor
from PySide6.QtCore import Qt
import sys
import os
from core.config_manager import config

class ThemeManager:
    """
    Manages application theming including light and dark mode.
    Ensures text visibility in all color schemes.
    """
    
    @staticmethod
    def get_system_theme():
        """
        Determines if system is using dark mode.
        Returns True for dark mode, False for light mode.
        """
        if sys.platform == 'win32':
            # Windows detection
            try:
                import winreg
                registry = winreg.ConnectRegistry(None, winreg.HKEY_CURRENT_USER)
                key = winreg.OpenKey(registry, r'Software\Microsoft\Windows\CurrentVersion\Themes\Personalize')
                value, _ = winreg.QueryValueEx(key, 'AppsUseLightTheme')
                return value == 0  # 0 means dark mode
            except:
                return False
        elif sys.platform == 'darwin':
            # macOS detection
            try:
                import subprocess
                cmd = 'defaults read -g AppleInterfaceStyle'
                result = subprocess.run(cmd, shell=True, text=True, capture_output=True)
                return result.stdout.strip() == 'Dark'
            except:
                return False
        else:
            # Linux and others - could expand this with specific desktop environment checks
            return False
    
    @staticmethod
    def apply_theme(app):
        """
        Applies the appropriate theme based on config settings.
        
        Args:
            app: QApplication instance
        """
        theme = config.get('appearance.theme', 'system')
        
        # Determine if we should use dark mode
        use_dark = False
        if theme == 'dark':
            use_dark = True
        elif theme == 'light':
            use_dark = False
        else:  # system
            use_dark = ThemeManager.get_system_theme()
        
        if use_dark:
            ThemeManager._apply_dark_theme(app)
        else:
            ThemeManager._apply_light_theme(app)
        
        # Apply any custom styles from config
        custom_styles = config.get('appearance.custom_styles', '')
        if custom_styles:
            app.setStyleSheet(app.styleSheet() + "\n" + custom_styles)
    
    @staticmethod
    def _apply_dark_theme(app):
        """Apply dark theme styling to the application"""
        # Create a dark palette
        dark_palette = QPalette()
        
        # Set colors that work well with dark mode
        dark_color = QColor(45, 45, 45)
        dark_text = QColor(245, 245, 245)  # Almost white for best visibility
        
        # Set colors for all palette roles
        dark_palette.setColor(QPalette.Window, dark_color)
        dark_palette.setColor(QPalette.WindowText, dark_text)
        dark_palette.setColor(QPalette.Base, QColor(36, 36, 36))
        dark_palette.setColor(QPalette.AlternateBase, QColor(60, 60, 60))
        dark_palette.setColor(QPalette.ToolTipBase, dark_color)
        dark_palette.setColor(QPalette.ToolTipText, dark_text)
        dark_palette.setColor(QPalette.Text, dark_text)
        dark_palette.setColor(QPalette.Button, dark_color)
        dark_palette.setColor(QPalette.ButtonText, dark_text)
        dark_palette.setColor(QPalette.BrightText, Qt.red)
        dark_palette.setColor(QPalette.Link, QColor(42, 130, 218))
        dark_palette.setColor(QPalette.Highlight, QColor(42, 130, 218))
        dark_palette.setColor(QPalette.HighlightedText, Qt.white)
        
        # Disabled colors
        dark_palette.setColor(QPalette.Disabled, QPalette.Text, QColor(150, 150, 150))
        dark_palette.setColor(QPalette.Disabled, QPalette.ButtonText, QColor(150, 150, 150))
        dark_palette.setColor(QPalette.Disabled, QPalette.WindowText, QColor(150, 150, 150))
        
        app.setPalette(dark_palette)
        
        # Define stylesheet for specific widgets
        app.setStyleSheet("""
            /* Dark theme styles */
            QMainWindow, QDialog {
                background-color: #2d2d2d;
                color: #f5f5f5;
            }
            
            /* Text widgets */
            QTextEdit, QPlainTextEdit {
                background-color: #262626;
                color: #f5f5f5;
                border: 1px solid #555555;
            }
            
            /* Lists and views */
            QListWidget, QTreeWidget, QTableWidget {
                background-color: #262626;
                color: #f5f5f5;
                border: 1px solid #555555;
            }
            
            /* Input fields */
            QLineEdit {
                background-color: #262626;
                color: #f5f5f5;
                border: 1px solid #555555;
                padding: 2px;
            }
            
            /* Tab widgets */
            QTabWidget::pane {
                border: 1px solid #555555;
            }
            
            QTabBar::tab {
                background-color: #3c3c3c;
                color: #f5f5f5;
                padding: 5px;
                border: 1px solid #555555;
                border-bottom: none;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
            }
            
            QTabBar::tab:selected {
                background-color: #4f4f4f;
            }
            
            /* Buttons */
            QPushButton {
                background-color: #3c3c3c;
                color: #f5f5f5;
                border: 1px solid #555555;
                padding: 5px;
                border-radius: 3px;
            }
            
            QPushButton:hover {
                background-color: #4f4f4f;
            }
            
            QPushButton:pressed {
                background-color: #2a82da;
            }
            
            /* Dropdown menus */
            QComboBox {
                background-color: #3c3c3c;
                color: #f5f5f5;
                border: 1px solid #555555;
                padding: 2px;
            }
            
            QComboBox QAbstractItemView {
                background-color: #262626;
                color: #f5f5f5;
                selection-background-color: #2a82da;
            }
            
            /* Group boxes */
            QGroupBox {
                border: 1px solid #555555;
                margin-top: 8px;
                padding-top: 8px;
            }
            
            QGroupBox::title {
                color: #f5f5f5;
                subcontrol-origin: margin;
                subcontrol-position: top center;
                padding: 0 5px;
            }
            
            /* Checkboxes and radio buttons */
            QCheckBox, QRadioButton {
                color: #f5f5f5;
            }
            
            /* Menu bar */
            QMenuBar {
                background-color: #2d2d2d;
                color: #f5f5f5;
            }
            
            QMenuBar::item:selected {
                background-color: #3c3c3c;
            }
            
            /* Menu */
            QMenu {
                background-color: #2d2d2d;
                color: #f5f5f5;
                border: 1px solid #555555;
            }
            
            QMenu::item:selected {
                background-color: #2a82da;
            }
            
            /* Status bar */
            QStatusBar {
                background-color: #2d2d2d;
                color: #f5f5f5;
            }
            
            /* Tooltips */
            QToolTip {
                background-color: #262626;
                color: #f5f5f5;
                border: 1px solid #555555;
            }
            
            /* Web view (for GPS map) */
            QWebEngineView {
                background-color: #262626;
            }
            
            /* Scrollbars */
            QScrollBar:vertical {
                background-color: #2d2d2d;
                width: 14px;
                margin: 15px 0 15px 0;
            }
            
            QScrollBar::handle:vertical {
                background-color: #3c3c3c;
                min-height: 20px;
                border-radius: 7px;
            }
            
            QScrollBar::handle:vertical:hover {
                background-color: #4f4f4f;
            }
            
            QScrollBar:horizontal {
                background-color: #2d2d2d;
                height: 14px;
                margin: 0 15px 0 15px;
            }
            
            QScrollBar::handle:horizontal {
                background-color: #3c3c3c;
                min-width: 20px;
                border-radius: 7px;
            }
            
            QScrollBar::handle:horizontal:hover {
                background-color: #4f4f4f;
            }
        """)
    
    @staticmethod
    def _apply_light_theme(app):
        """Apply light theme styling to the application"""
        # Reset to default palette
        app.setPalette(QApplication.style().standardPalette())
        
        # Define stylesheet for specific widgets
        app.setStyleSheet("""
            /* Light theme styles */
            QMainWindow, QDialog {
                background-color: #f5f5f5;
                color: #202020;
            }
            
            /* Text widgets */
            QTextEdit, QPlainTextEdit {
                background-color: #ffffff;
                color: #202020;
                border: 1px solid #c0c0c0;
            }
            
            /* Lists and views */
            QListWidget, QTreeWidget, QTableWidget {
                background-color: #ffffff;
                color: #202020;
                border: 1px solid #c0c0c0;
            }
            
            /* Input fields */
            QLineEdit {
                background-color: #ffffff;
                color: #202020;
                border: 1px solid #c0c0c0;
                padding: 2px;
            }
            
            /* Tab widgets */
            QTabWidget::pane {
                border: 1px solid #c0c0c0;
            }
            
            QTabBar::tab {
                background-color: #e6e6e6;
                color: #202020;
                padding: 5px;
                border: 1px solid #c0c0c0;
                border-bottom: none;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
            }
            
            QTabBar::tab:selected {
                background-color: #ffffff;
            }
            
            /* Buttons */
            QPushButton {
                background-color: #e6e6e6;
                color: #202020;
                border: 1px solid #c0c0c0;
                padding: 5px;
                border-radius: 3px;
            }
            
            QPushButton:hover {
                background-color: #d0d0d0;
            }
            
            QPushButton:pressed {
                background-color: #0078d7;
                color: #ffffff;
            }
            
            /* Dropdown menus */
            QComboBox {
                background-color: #ffffff;
                color: #202020;
                border: 1px solid #c0c0c0;
                padding: 2px;
            }
            
            QComboBox QAbstractItemView {
                background-color: #ffffff;
                color: #202020;
                selection-background-color: #0078d7;
                selection-color: #ffffff;
            }
            
            /* Group boxes */
            QGroupBox {
                border: 1px solid #c0c0c0;
                margin-top: 8px;
                padding-top: 8px;
            }
            
            QGroupBox::title {
                color: #202020;
                subcontrol-origin: margin;
                subcontrol-position: top center;
                padding: 0 5px;
            }
            
            /* Checkboxes and radio buttons */
            QCheckBox, QRadioButton {
                color: #202020;
            }
            
            /* Menu bar */
            QMenuBar {
                background-color: #f5f5f5;
                color: #202020;
            }
            
            QMenuBar::item:selected {
                background-color: #e0e0e0;
            }
            
            /* Menu */
            QMenu {
                background-color: #f5f5f5;
                color: #202020;
                border: 1px solid #c0c0c0;
            }
            
            QMenu::item:selected {
                background-color: #0078d7;
                color: #ffffff;
            }
            
            /* Status bar */
            QStatusBar {
                background-color: #f5f5f5;
                color: #202020;
            }
            
            /* Tooltips */
            QToolTip {
                background-color: #f5f5f5;
                color: #202020;
                border: 1px solid #c0c0c0;
            }
            
            /* Web view (for GPS map) */
            QWebEngineView {
                background-color: #ffffff;
            }
            
            /* Scrollbars */
            QScrollBar:vertical {
                background-color: #f5f5f5;
                width: 14px;
                margin: 15px 0 15px 0;
            }
            
            QScrollBar::handle:vertical {
                background-color: #c0c0c0;
                min-height: 20px;
                border-radius: 7px;
            }
            
            QScrollBar::handle:vertical:hover {
                background-color: #a0a0a0;
            }
            
            QScrollBar:horizontal {
                background-color: #f5f5f5;
                height: 14px;
                margin: 0 15px 0 15px;
            }
            
            QScrollBar::handle:horizontal {
                background-color: #c0c0c0;
                min-width: 20px;
                border-radius: 7px;
            }
            
            QScrollBar::handle:horizontal:hover {
                background-color: #a0a0a0;
            }
        """)