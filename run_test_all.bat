@echo off
cd /d "%~dp0"

if not exist "logs" mkdir logs

set LOGFILE=logs\test_all_%date:~0,4%%date:~5,2%%date:~8,2%_%time:~0,2%%time:~3,2%.log
set LOGFILE=%LOGFILE: =0%

echo [%date% %time%] [TEST] 전체 업데이트 시작 (6-7회차) >> "%LOGFILE%"
python main.py --all --test >> "%LOGFILE%" 2>&1
echo [%date% %time%] 완료 >> "%LOGFILE%"
