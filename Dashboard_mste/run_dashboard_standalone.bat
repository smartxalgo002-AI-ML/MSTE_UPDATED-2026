@echo off
cd /d "%~dp0"
echo Starting SignalNews Dashboard...
echo Directory: %CD%
echo.

:: Check/Install requirements
python -c "import streamlit" 2>nul
if %errorlevel% neq 0 (
    echo [WARNING] streamlit might not be installed. Installing requirements...
    pip install -r requirements.txt
)

:: Run the app
python -m streamlit run app.py

echo.
echo Dashboard closed.
pause
