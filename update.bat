@echo off
setlocal
cd /d "%~dp0"

set "LOGDIR=%~dp0logs"
if not exist "%LOGDIR%" mkdir "%LOGDIR%"
set "LOGFILE=%LOGDIR%\update_%date:~0,4%%date:~5,2%%date:~8,2%.log"
set "LOGFILE=%LOGFILE: =0%"

echo [%date% %time%] ===== 자동 업데이트 시작 ===== >> "%LOGFILE%"

:: Python으로 GitHub ZIP 다운로드 (git 불필요)
echo [%date% %time%] GitHub 최신 코드 확인 중... >> "%LOGFILE%"
python "%~dp0auto_update.py" >> "%LOGFILE%" 2>&1
if errorlevel 1 (
    echo [%date% %time%] [경고] 업데이트 실패. logs 폴더 확인 필요. >> "%LOGFILE%"
) else (
    echo [%date% %time%] 업데이트 완료. >> "%LOGFILE%"
)

echo [%date% %time%] ===== 자동 업데이트 종료 ===== >> "%LOGFILE%"
endlocal
