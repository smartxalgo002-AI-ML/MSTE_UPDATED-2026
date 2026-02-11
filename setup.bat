@echo off
REM First-time setup script for Windows
REM Run this once to set up the environment

echo.
echo ========================================
echo News Sentiment Model - Setup Script
echo ========================================
echo.

REM Check Python
python --version
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Python not found. Please install Python 3.8+
    pause
    exit /b 1
)

REM Create virtual environment
echo.
echo Creating virtual environment...
python -m venv .venv
call .venv\Scripts\activate.bat

REM Upgrade pip
echo.
echo Upgrading pip...
python -m pip install --upgrade pip

REM Install dependencies
echo.
echo Installing dependencies from requirements.txt...
pip install -r requirements.txt

REM Download NLTK data
echo.
echo Downloading NLTK data...
python -c "import nltk; nltk.download('punkt'); nltk.download('stopwords'); nltk.download('wordnet'); print('NLTK data downloaded')"

REM Create required directories
echo.
echo Creating required directories...
if not exist "logs" mkdir logs
if not exist "output\news_fetcher" mkdir output\news_fetcher
if not exist "output\company_tagger" mkdir output\company_tagger
if not exist "output\longformer" mkdir output\longformer
if not exist "output\deberta_fin" mkdir output\deberta_fin
if not exist "output\features" mkdir output\features
if not exist "output\ohlcv_merger" mkdir output\ohlcv_merger
if not exist "output\labels" mkdir output\labels
if not exist "output\signals" mkdir output\signals
if not exist "models" mkdir models
if not exist "correct_ohlcv_tick_data\data_ohlcv\group_XX" mkdir "correct_ohlcv_tick_data\data_ohlcv\group_XX"

REM Check for mapping files
echo.
echo Checking mapping files...
if exist "mapping\companywise_keyword_mapping.csv" (
    echo Company mapping file found
) else (
    echo WARNING: mapping\companywise_keyword_mapping.csv not found
)

if exist "mapping\index_mapping.csv" (
    echo Index mapping file found
) else (
    echo WARNING: mapping\index_mapping.csv not found
)

echo.
echo ========================================
echo Setup complete!
echo.
echo Next steps:
echo 1. Activate virtual environment: .venv\Scripts\activate
echo 2. Create "correct_ohlcv_tick_data\dhan_token.json" with your Dhan credentials
echo 3. Run the pipeline: python main.py
echo.
echo ========================================
pause
