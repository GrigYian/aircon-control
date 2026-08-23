@echo off
cd /d "%~dp0"

if not exist "dist\index.html" (
    echo Building the React interface...
    call npm run build
    if errorlevel 1 pause & exit /b 1
)

start "AirCon Control" "..\.venv\Scripts\pythonw.exe" "%~dp0backend.py"
