# News Sentiment Model - Quick Start Guide

## 🚀 Easiest Way (One Command)

### Windows:
```cmd
start.bat
```

### Linux / macOS:
```bash
chmod +x start.sh
./start.sh
```

**That's it!** The script automatically:
- Detects if setup is needed and runs it
- Creates virtual environment
- Installs dependencies
- Starts the pipeline

---

## Manual Setup (Optional)

### Windows:
```cmd
# 1. Run setup script
setup.bat

# 2. Activate environment
.venv\Scripts\activate

# 3. Create Dhan token file
# Edit: correct_ohlcv_tick_data\dhan_token.json

# 4. Run pipeline
python main.py
```

### Linux / macOS:
```bash
# 1. Run setup script
chmod +x setup.sh
./setup.sh

# 2. Activate environment  
source .venv/bin/activate

# 3. Create Dhan token file
nano "correct_ohlcv_tick_data/dhan_token.json"

# 4. Run pipeline
python3 main.py
```

---

## Dhan Token Template

Create `correct_ohlcv_tick_data/dhan_token.json`:

```json
{
  "access_token": "YOUR_TOKEN_HERE",
  "client_id": "YOUR_CLIENT_ID",
  "expires_at": 1770277211,
  "renewed_at": 1738645228
}
```

---

## Scripts Available

### Windows:
- `setup.bat` - One-time setup
- `run_dashboard.bat` - Start dashboard

### Linux:
- `setup.sh` - One-time setup
- `run_news_pipeline.sh` - Start news pipeline
- `run_ohlcv_collector.sh` - Start OHLCV collector
- `run_dashboard.sh` - Start dashboard

### Both:
- `python main.py` - Run full pipeline (continuous)
- `python main.py --once` - Run once and exit

---

## Troubleshooting

### "Module not found" error:
```bash
# Reinstall dependencies
pip install -r requirements.txt
```

### Selenium/ChromeDriver issues:
```bash
# The webdriver-manager handles ChromeDriver automatically
# If issues persist:
pip install --upgrade selenium webdriver-manager
```

### NLTK data missing:
```python
import nltk
nltk.download('punkt')
nltk.download('stopwords') 
nltk.download('wordnet')
```

### Permission denied (Linux):
```bash
chmod +x *.sh
```

---

## Directory Structure

```
News_Sentiment_Model_Step1/
├── main.py                  # Main pipeline
├── config.py                # Configuration
├── requirements.txt         # Dependencies
├── setup.sh / setup.bat     # Setup scripts
├── modules/                 # Pipeline steps
├── mapping/                 # Company mappings
├── output/                  # Generated data
├── models/                  # ML models
├── Dashboard_mste/          # Streamlit dashboard
└── correct_ohlcv_tick_data/ # Market data collector
```
