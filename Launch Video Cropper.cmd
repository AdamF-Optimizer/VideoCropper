@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
    powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Setup.ps1"
    if errorlevel 1 (
        echo Setup failed. See the error above.
        pause
        exit /b 1
    )
)
".venv\Scripts\python.exe" -c "import PySide6, imageio_ffmpeg" >nul 2>&1
if errorlevel 1 (
    echo Dependencies are missing. Run Setup.ps1 to repair this installation.
    pause
    exit /b 1
)
start "" ".venv\Scripts\pythonw.exe" "%~dp0main.py"
