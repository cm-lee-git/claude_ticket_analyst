@echo off
setlocal
cd /d "%~dp0"

echo.
echo ================================================
echo  CCI Analyst 초기 설정
echo ================================================
echo.

:: Python 확인
python --version >nul 2>&1
if errorlevel 1 (
    echo [오류] Python이 설치되어 있지 않습니다.
    echo https://www.python.org/downloads/ 에서 설치 후 다시 실행하세요.
    pause
    exit /b 1
)
echo [OK] Python 확인됨

:: pip 패키지 설치
echo.
echo [1/3] 패키지 설치 중...
pip install -r requirements.txt
if errorlevel 1 (
    echo [오류] pip install 실패. 위 오류 메시지를 확인하세요.
    pause
    exit /b 1
)
echo [OK] 패키지 설치 완료

:: .env 파일 생성
echo.
echo [2/3] 환경 설정 파일 확인...
if not exist ".env" (
    copy ".env.example" ".env" >nul
    echo [생성됨] .env 파일이 만들어졌습니다.
    echo.
    echo !! 중요: 아래 파일을 열어서 본인의 API 키와 이메일을 입력하세요 !!
    echo    %~dp0.env
    echo.
    notepad "%~dp0.env"
) else (
    echo [OK] .env 파일이 이미 존재합니다.
)

:: 작업 스케줄러 등록
echo.
echo [3/3] Windows 작업 스케줄러 등록 중...
call "%~dp0setup_tasks.bat"

echo.
echo ================================================
echo  설정 완료!
echo  이제 매일 08:30에 자동으로 코드가 업데이트됩니다.
echo  수동 업데이트: update.bat 실행
echo ================================================
echo.
endlocal
