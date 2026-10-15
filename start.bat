@echo off
title NetWatch - Automated Network & Device Monitor
cd /d "%~dp0"

echo =======================================================
echo    NetWatch - Network & Device Monitoring Dashboard
echo =======================================================
echo.
echo Server Dashboard: http://localhost:8080
echo Anda juga bisa buka dari HP / PC lain: http://[IP-Laptop-Ini]:8080
echo.
echo Tekan Ctrl+C untuk berhenti.
echo -------------------------------------------------------

set PYTHON_CMD="C:\Users\Chaerul\AppData\Local\Programs\Python\Python310\python.exe"

if exist %PYTHON_CMD% (
    %PYTHON_CMD% -m uvicorn main:app --host 0.0.0.0 --port 8080 --reload
) else (
    python -m uvicorn main:app --host 0.0.0.0 --port 8080 --reload
)

pause
