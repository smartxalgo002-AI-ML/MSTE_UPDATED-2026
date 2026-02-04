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

## How to Run

### 1. Setup Environment
```bash
# Create virtual environment
python -m venv .venv

# Activate it (Windows)
.venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Run the Pipeline

**Run once:**
```bash
python main.py --once
```

**Run continuously (every 5 minutes):**
```bash
python main.py
```

---

## Project Structure

```
News_Sentiment_Model_Step1/
├── main.py                    # Main entry point (runs all 4 steps)
├── config.py                  # All file paths and settings
├── requirements.txt           # Python dependencies
│
├── modules/
│   ├── news_fetcher_step1.py      # Step 1: Fetches news
│   ├── company_tagging_step2.py   # Step 2: Tags companies
│   ├── longformer_step3.py        # Step 3: Summarizes articles
│   ├── deberta_step4.py           # Step 4: Sentiment analysis
│   ├── feature_builder_step5.py   # Step 5: Feature extraction
│   ├── ohlcv_merge_step6.py       # Step 6: Market data merge
│   ├── label_generator_step7.py   # Step 7: Training labels
│   ├── xgboost_trainer_step8.py   # Step 8: Model training
│   ├── signal_predictor_step9.py  # Step 9: ML predictions
│   │
│   └── news_sources/              # Individual scrapers
│       ├── moneycontrol.py
│       ├── livemint.py
│       ├── the_economic_times.py
│       ├── cnbc_tv18.py
│       ├── business_today.py
│       └── hindu_business_Line.py
│
├── mapping/
│   └── companywise_keyword_mapping.csv.csv  # Company → Keywords mapping
│
├── output/                    # All output files saved here
│   ├── news_fetcher/
│   ├── company_tagger/
│   ├── longformer/
│   ├── deberta_fin/
│   ├── features/
│   ├── ohlcv_merger/
│   ├── labels/
│   └── signals/              # ML trading signals
│
├── models/                   # Trained XGBoost models
│   └── xgb_news_model_latest.pkl
│
└── logs/                      # Log files
```

---

## Configuration

Edit `config.py` to change:
- `MAX_ARTICLES` – How many articles to fetch per source (default: 30)
- Output file paths
- Mapping file paths

---

## Requirements

- Python 3.10+
- GPU recommended for faster model inference (Longformer & DeBERTa)
- Internet connection for scraping news

---

## Notes

- The pipeline skips already-processed articles (no duplicates)
- Each run only processes NEW articles
- All cumulative data is preserved in `all_*.json` files
- Use `--once` flag for single run, otherwise it loops every 5 minutes

Hp@LAPTOP-L204T18A MINGW64 /d/Final_MSTE_Long_Debert
$ cd News_Sentiment_Model_Step1

Hp@LAPTOP-L204T18A MINGW64 /d/Final_MSTE_Long_Debert/News_Sentiment_Model_Step1
$ python -m venv .venv
source .venv/Scripts/activate
(.venv) 
Hp@LAPTOP-L204T18A MINGW64 /d/Final_MSTE_Long_Debert/News_Sentiment_Model_Step1
$ pip install -r requirements.txt

Hp@LAPTOP-L204T18A MINGW64 /d/Final_MSTE_Long_Debert/News_Sentiment_Model_Step1
$ python main.py
🔁 Starting News Sentiment Pipeline (loop mode)
   Interval: 5 minutes
   Press CTRL+C to stop.

   to run ohlcv fetcher:
   cd "d:\Final_MSTE_Long_Debert\News_Sentiment_Model_Step1\CORRECT OHLCV TICK DATA"
python "new ohlcv.py"

to run the track accuracy script:

cd "d:\Final_MSTE_Long_Debert\News_Sentiment_Model_Step1"
python "track_live_accuracy.py"

to run mste dashboard
"d:\Final_MSTE_Long_Debert\News_Sentiment_Model_Step1\Dashboard_mste\run_dashboard_standalone.bat"