@echo off
setlocal

:: CCI scheduled task registration
:: Works without PowerShell, without admin rights
:: Run by double-clicking or from cmd.exe

set "DIR=%~dp0"
if "%DIR:~-1%"=="\" set "DIR=%DIR:~0,-1%"

echo.
echo ================================================
echo  CCI Task Scheduler Setup
echo  Folder: %DIR%
echo ================================================
echo.

schtasks /delete /TN "CCI_Doc1_Weekly"     /F 2>nul
schtasks /delete /TN "CCI_Doc1_Daily"      /F 2>nul
schtasks /delete /TN "CCI_Doc2_Weekly"     /F 2>nul
schtasks /delete /TN "CCI_Doc2_Daily"      /F 2>nul
schtasks /delete /TN "CCI_Snapshot_Daily"  /F 2>nul
schtasks /delete /TN "CCI_Notify"          /F 2>nul
schtasks /delete /TN "CCI_Doc2_Doc3_Daily" /F 2>nul

schtasks /create /TN "CCI_Doc1_Weekly"    /TR "%DIR%\run_doc1.bat"         /SC WEEKLY /D MON                  /ST 11:00 /F
schtasks /create /TN "CCI_Doc1_Daily"     /TR "%DIR%\run_doc1_daily.bat"   /SC WEEKLY /D TUE,WED,THU,FRI      /ST 11:00 /F
schtasks /create /TN "CCI_Doc2_Weekly"    /TR "%DIR%\run_doc2.bat"         /SC WEEKLY /D MON                  /ST 10:00 /F
schtasks /create /TN "CCI_Doc2_Daily"     /TR "%DIR%\run_doc2_daily.bat"   /SC WEEKLY /D MON,TUE,WED,THU,FRI /ST 16:00 /F
schtasks /create /TN "CCI_Snapshot_Daily" /TR "%DIR%\run_snapshot.bat"     /SC WEEKLY /D MON,TUE,WED,THU,FRI /ST 18:00 /F
schtasks /create /TN "CCI_Notify"         /TR "%DIR%\run_notify.bat"       /SC WEEKLY /D MON,TUE,WED,THU,FRI /ST 16:00 /F

echo.
echo === Registered CCI tasks ===
schtasks /query /fo TABLE | findstr "CCI_"
echo.
pause
endlocal
