@echo off
cd /d "%~dp0"

net session >nul 2>&1
if %errorlevel% neq 0 (
	powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
	exit /b
)

start "" python -m streamlit run streamlit_app.py --server.headless=true
