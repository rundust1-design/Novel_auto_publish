@echo off
chcp 65001 > nul
cd /d "%~dp0"
if not exist logs mkdir logs

echo [%date% %time%] Start unattended Qidian publish >> logs\scheduled_publish.log
py -3 publish.py --platform qidian --no-prompt --headless >> logs\scheduled_publish.log 2>&1
set EXIT_CODE=%ERRORLEVEL%
echo [%date% %time%] Finished with exit code %EXIT_CODE% >> logs\scheduled_publish.log
exit /b %EXIT_CODE%
