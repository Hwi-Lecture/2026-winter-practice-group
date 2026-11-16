@echo off
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python is not installed. Install it from https://www.python.org/downloads/
    pause
    exit /b 1
)

echo Installing required packages... (first run may take a minute)
python -m pip install -q -r requirements.txt
if errorlevel 1 (
    echo [ERROR] Package installation failed.
    pause
    exit /b 1
)

echo Starting chatbot. Your browser will open shortly.
echo Close this window to stop the chatbot.
python -m streamlit run app.py
pause
