@echo off
REM All-in-one script for Windows - Setup + Run
REM Just run: start.bat

echo.
echo ========================================
echo News Sentiment Pipeline - Auto Setup
echo ========================================
echo.

REM Check if virtual environment exists
if not exist ".venv\Scripts\python.exe" (
    echo First-time setup detected. Running setup...
    echo.
    call setup.bat
    if %ERRORLEVEL% NEQ 0 (
        echo Setup failed!
        pause
        exit /b 1
    )
)

REM Activate virtual environment
echo Activating virtual environment...
call .venv\Scripts\activate.bat

REM Check for Dhan token (for OHLCV collector)
if not exist "CORRECT OHLCV TICK DATA\dhan_token.json" (
    echo.
    echo ========================================
    echo WARNING: Dhan token file not found!
    echo ========================================
    echo.
    echo The OHLCV collector requires: CORRECT OHLCV TICK DATA\dhan_token.json
    echo.
    echo Create the file with this format:
    echo {
    echo   "access_token": "YOUR_TOKEN_HERE",
    echo   "client_id": "YOUR_CLIENT_ID",
    echo   "expires_at": 1770277211,
    echo   "renewed_at": 1738645228
    echo }
    echo.
    echo The news pipeline will still run, but OHLCV data won't be collected.
    echo.
    timeout /t 5
)

REM Start OHLCV Data Collector (in a separate window)
echo.
echo ========================================
echo Starting OHLCV Market Data Collector...
echo ========================================
echo.
start "OHLCV Collector" cmd /k "call .venv\Scripts\activate.bat && cd "CORRECT OHLCV TICK DATA" && python "new ohlcv.py""

REM Start the pipeline (in this window)
echo.
echo ========================================
echo Starting News Sentiment Pipeline...
echo ========================================
echo.
python main.py

pause
