@echo off
rem Anipang 7-poker bot - runs without Claude. Phone must be on USB with debugging allowed.
cd /d "%~dp0"
:loop
python run_bot.py
if errorlevel 3 goto end
timeout /t 10 >nul
goto loop
:end
echo Bot stopped (out of gold or payment screen detected). See logs\supervisor.log
pause
