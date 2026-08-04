@echo off
cd /d C:\Users\innocean\cci-analyst

if not exist "logs" mkdir logs

set LOGFILE=logs\doc2_doc3_%date:~0,4%%date:~5,2%%date:~8,2%_%time:~0,2%%time:~3,2%.log
set LOGFILE=%LOGFILE: =0%

echo [%date% %time%] Doc2/Doc3 업데이트 시작 >> "%LOGFILE%"
C:\Users\innocean\AppData\Local\Python\pythoncore-3.14-64\python.exe main.py --doc2 >> "%LOGFILE%" 2>&1
echo [%date% %time%] Doc2 완료 >> "%LOGFILE%"
C:\Users\innocean\AppData\Local\Python\pythoncore-3.14-64\python.exe main.py --doc3 >> "%LOGFILE%" 2>&1
echo [%date% %time%] Doc3 완료 >> "%LOGFILE%"
