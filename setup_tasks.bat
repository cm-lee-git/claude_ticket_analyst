@echo off
chcp 65001 > nul
echo.
echo ================================================
echo  CCI 작업 스케줄러 등록 (관리자 권한 필요)
echo ================================================
echo.

:: 기존 태스크 제거 (없으면 오류 무시)
schtasks /delete /TN "CCI_Doc1_Weekly"    /F 2>nul
schtasks /delete /TN "CCI_Doc1_Daily"     /F 2>nul
schtasks /delete /TN "CCI_Doc2_Weekly"    /F 2>nul
schtasks /delete /TN "CCI_Doc2_Daily"     /F 2>nul
schtasks /delete /TN "CCI_Snapshot_Daily" /F 2>nul
schtasks /delete /TN "CCI_Notify"         /F 2>nul
schtasks /delete /TN "CCI_Doc2_Doc3_Daily" /F 2>nul

:: 새 태스크 등록
schtasks /create /TN "CCI_Doc1_Weekly"    /TR "C:\Users\innocean\cci-analyst\run_doc1.bat"         /SC WEEKLY /D MON                  /ST 11:00 /F
schtasks /create /TN "CCI_Doc1_Daily"     /TR "C:\Users\innocean\cci-analyst\run_doc1_daily.bat"   /SC WEEKLY /D TUE,WED,THU,FRI      /ST 11:00 /F
schtasks /create /TN "CCI_Doc2_Weekly"    /TR "C:\Users\innocean\cci-analyst\run_doc2.bat"         /SC WEEKLY /D MON                  /ST 10:00 /F
schtasks /create /TN "CCI_Doc2_Daily"     /TR "C:\Users\innocean\cci-analyst\run_doc2_daily.bat"   /SC WEEKLY /D MON,TUE,WED,THU,FRI /ST 16:00 /F
schtasks /create /TN "CCI_Snapshot_Daily" /TR "C:\Users\innocean\cci-analyst\run_snapshot.bat"     /SC WEEKLY /D MON,TUE,WED,THU,FRI /ST 18:00 /F
schtasks /create /TN "CCI_Notify"         /TR "C:\Users\innocean\cci-analyst\run_notify.bat"       /SC WEEKLY /D MON,TUE,WED,THU,FRI /ST 16:00 /F

echo.
echo === 등록된 CCI 태스크 확인 ===
schtasks /query /fo TABLE | findstr "CCI_"
echo.
echo 완료. 창을 닫으려면 아무 키나 누르세요.
pause > nul
