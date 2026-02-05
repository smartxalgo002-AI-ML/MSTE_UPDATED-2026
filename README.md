# News Sentiment Analysis Pipeline

A complete pipeline that fetches financial news, identifies companies mentioned, and analyzes sentiment using AI models.

---

## What This Project Does

This project automatically:
1. **Collects news** from 6 Indian financial news websites
2. **Tags companies** mentioned in each article
3. **Condenses long articles** into short, focused text
4. **Analyzes sentiment** (Positive / Neutral / Negative) for each company
5. **Extracts market features** (price momentum, volume, volatility) for context
6. **Generates ML-based trading signals** (BUY / SELL / HOLD) using XGBoost with 15 features

---

## Pipeline Steps (How It Works)

### Step 1: News Fetcher
- Scrapes latest news from 6 sources:
  - Moneycontrol
  - LiveMint
  - Economic Times
  - CNBC-TV18
  - Business Today
  - Hindu Business Line
- Saves articles with headline, content, URL, and timestamp
- Removes duplicate articles automatically

### Step 2: Company Tagger
- Reads the fetched news articles
- Searches headlines for company names/keywords
- Maps each article to the company it mentions (with Symbol, Sector, Index)
- Uses keyword mapping from `mapping/companywise_keyword_mapping.csv.csv`

### Step 3: Longformer Condensation
- Takes long news articles and shortens them
- Keeps only the important financial events/facts
- Uses Longformer AI model (handles very long text)

### Step 4: DeBERTa Sentiment Analysis
- Reads the condensed text
- Classifies sentiment as: **Positive**, **Neutral**, or **Negative**
- Uses DeBERTa model fine-tuned for financial text

### Step 5: Feature Builder
- Extracts numerical features from sentiment analysis
- Calculates sentiment scores, confidence, probabilities
- Adds time-based and regulatory news features

### Step 6: OHLCV Merge
- Merges 15-minute market reaction data (price changes after news)
- Calculates returns and volatility from live market data

### Step 7: Label Generator  
- Creates BUY/SELL/HOLD labels based on price movement
- Uses rule-based thresholds on 15-minute returns
- Generates training data for ML model

### Step 8: XGBoost Self-Training
- Trains machine learning model on labeled historical data
- Requires 300+ samples to retrain
- Automatically improves over time with more data

### Step 9: Signal Predictor
- Uses trained XGBoost model to predict BUY/SELL/HOLD signals
- Generates confidence scores and probabilities
- Provides actionable trading signals for new articles

---

## Output Files

| Folder | File | Description |
|--------|------|-------------|
| `output/news_fetcher/` | `all_*.json` | All articles ever fetched (cumulative) |
| `output/news_fetcher/` | `*_new.json` | Only articles from latest run |
| `output/news_fetcher/` | `merged_news.json` | All new articles combined |
| `output/company_tagger/` | `all_tagged_news.json` | All tagged articles (cumulative) |
| `output/company_tagger/` | `tagged_new.json` | Newly tagged articles |
| `output/longformer/` | `all_condensed_news.json` | All condensed articles |
| `output/deberta_fin/` | `all_news_sentiment.json` | All articles with sentiment |
| `output/features/` | `all_features.json` | All feature vectors for ML |
| `output/ohlcv_merger/` | `all_ohlcv_merger.json` | Articles with market data |
| `output/labels/` | `all_labeled_news.json` | Training labels (BUY/SELL/HOLD) |
| `output/signals/` | `all_signals.json` | **ML predictions (trading signals)** |
| `models/` | `xgb_news_model_latest.pkl` | Trained XGBoost model |

---

## 🚀 How to Run (One-Click)

The project includes automated scripts for Windows and Linux/Mac.

### 1. Start the Entire System
This single command launches:
- **News Pipeline** (Scrapes news & runs AI models)
- **OHLCV Collector** (Fetches market data 24/7)
- **Auto-Sleep System** (Sleeps at 15:31, restarts at 09:00 AM)

**Windows:**
```powershell
.\start.bat
```

**Linux / Mac:**
```bash
./start.sh
```

### 2. Run the Dashboard
Opens the Streamlit dashboard to visualize signals and data.

**Windows:**
```powershell
.\run_dashboard.bat
```

**Linux / Mac:**
```bash
./run_dashboard.sh
```

---

## 🛠️ Deployment & Cloud
This project is **Cloud-Ready** (AWS/GCP/Azure).
- See [AWS Deployment Guide](aws_deployment_guide.md) for full server setup.
- Includes `systemd` service files for auto-restart on Linux servers.

---

## 📂 Project Structure

```
News_Sentiment_Model_Step1/
├── start.bat / .sh            # 🚀 MASTER START SCRIPT
├── run_dashboard.bat / .sh    # 📊 DASHBOARD SCRIPT
├── main.py                    # Main entry point (News Pipeline)
├── config.py                  # All file paths and settings
├── aws_deployment_guide.md    # Deployment instructions
│
├── modules/                   # AI & Processing Modules
│   ├── news_fetcher_step1.py
│   ├── company_tagging_step2.py
│   ├── longformer_step3.py
│   ├── deberta_step4.py
│   ├── feature_builder_step5.py
│   ├── ohlcv_merge_step6.py
│   ├── label_generator_step7.py
│   ├── xgboost_trainer_step8.py
│   └── signal_predictor_step9.py
│
├── CORRECT OHLCV TICK DATA/   # 📈 Market Data Engine
│   ├── new ohlcv.py           # The 24/7 Collector Script
│   └── token_manager.py       # Auto-renews Dhan tokens
│
├── Dashboard_mste/            # Streamlit Dashboard
│   └── app.py
│
├── output/                    # All Generated Data (JSONs)
├── models/                    # Trained Models (.pkl)
└── logs/                      # System Logs
```

---

## ⚙️ Configuration
- **`config.py`**: Main path settings.
- **`CORRECT OHLCV TICK DATA/new ohlcv.py`**: Collection schedule (09:00 - 15:31).
- **`dhan_token.json`**: Token storage (auto-renews).

---
## ⚠️ Notes
- The **OHLCV Collector** is designed to run **24/7**. It automatically sleeps after market close (15:30) and wakes up the next morning (09:00).
- **Do not close the terminal** running `start.bat` if you want continuous data collection.
