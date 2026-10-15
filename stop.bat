@echo off
title Hentikan NetWatch
echo Menghentikan proses NetWatch...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :8080 ^| findstr LISTENING') do taskkill /F /PID %%a
echo Selesai. NetWatch telah dihentikan.
pause
