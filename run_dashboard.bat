@echo off
REM Go to the dashboard directory
cd /d "%~dp0Dashboard_mste"

REM Run Streamlit using the virtual environment python
"..\.venv\Scripts\python.exe" -m streamlit run app.py

pause
