import os

# ============== Base Paths ==============
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
MAPPING_DIR = os.path.join(BASE_DIR, "mapping")
MODULES_DIR = os.path.join(BASE_DIR, "modules")
HISTORIC_DATA_DIR = os.path.join(BASE_DIR, "historic_dataset")

# ============== Logging ==============
LOG_FILE = os.path.join(BASE_DIR, "logs", "scraper.log")
MAX_ARTICLES = 30

# ============== News Fetcher Output Paths ==============
NEWS_FETCHER_OUTPUT_DIR = os.path.join(OUTPUT_DIR, "news_fetcher")

# Moneycontrol
MONEYCONTROL_ALL_PATH = os.path.join(NEWS_FETCHER_OUTPUT_DIR, "all_moneycontrol.json")
MONEYCONTROL_NEW_PATH = os.path.join(NEWS_FETCHER_OUTPUT_DIR, "moneycontrol_new.json")

# Economic Times
ET_ALL_PATH = os.path.join(NEWS_FETCHER_OUTPUT_DIR, "all_et.json")
ET_NEW_PATH = os.path.join(NEWS_FETCHER_OUTPUT_DIR, "et_new.json")

# LiveMint
LIVEMINT_ALL_PATH = os.path.join(NEWS_FETCHER_OUTPUT_DIR, "all_livemint.json")
LIVEMINT_NEW_PATH = os.path.join(NEWS_FETCHER_OUTPUT_DIR, "livemint_new.json")

# CNBC-TV18
CNBC_ALL_PATH = os.path.join(NEWS_FETCHER_OUTPUT_DIR, "all_cnbc.json")
CNBC_NEW_PATH = os.path.join(NEWS_FETCHER_OUTPUT_DIR, "cnbc_new.json")

# Business Today
BUSINESS_TODAY_ALL_PATH = os.path.join(NEWS_FETCHER_OUTPUT_DIR, "all_business_today.json")
BUSINESS_TODAY_NEW_PATH = os.path.join(NEWS_FETCHER_OUTPUT_DIR, "business_today_new.json")

# Hindu Business Line
HINDU_BL_ALL_PATH = os.path.join(NEWS_FETCHER_OUTPUT_DIR, "all_hindu_business_line.json")
HINDU_BL_NEW_PATH = os.path.join(NEWS_FETCHER_OUTPUT_DIR, "hindu_business_line_new.json")

# Merged (cumulative and per-run)
MERGED_NEWS_ALL_PATH = os.path.join(NEWS_FETCHER_OUTPUT_DIR, "all_news.json")
MERGED_NEWS_NEW_PATH = os.path.join(NEWS_FETCHER_OUTPUT_DIR, "news_new.json")

# Legacy merged path (for backward compatibility)
MERGED_NEWS_PATH = MERGED_NEWS_NEW_PATH

# ============== Company Tagger Output Paths ==============
COMPANY_TAGGER_OUTPUT_DIR = os.path.join(OUTPUT_DIR, "company_tagger")
TAGGED_ALL_PATH = os.path.join(COMPANY_TAGGER_OUTPUT_DIR, "all_tagged_news.json")
TAGGED_NEW_PATH = os.path.join(COMPANY_TAGGER_OUTPUT_DIR, "tagged_new.json")

# ============== Longformer Output Paths ==============
LONGFORMER_OUTPUT_DIR = os.path.join(OUTPUT_DIR, "longformer")
CONDENSED_ALL_PATH = os.path.join(LONGFORMER_OUTPUT_DIR, "all_condensed_news.json")
CONDENSED_NEW_PATH = os.path.join(LONGFORMER_OUTPUT_DIR, "condensed_news_new.json")

# ============== DeBERTa Output Paths ==============
DEBERTA_OUTPUT_DIR = os.path.join(OUTPUT_DIR, "deberta_fin")
SENTIMENT_ALL_PATH = os.path.join(DEBERTA_OUTPUT_DIR, "all_news_sentiment.json")
SENTIMENT_NEW_PATH = os.path.join(DEBERTA_OUTPUT_DIR, "news_sentiment_new.json")

# ============== Feature Builder Output Paths ==============
FEATURES_OUTPUT_DIR = os.path.join(OUTPUT_DIR, "features")
FEATURES_ALL_PATH = os.path.join(FEATURES_OUTPUT_DIR, "all_features.json")
FEATURES_NEW_PATH = os.path.join(FEATURES_OUTPUT_DIR, "features_new.json")

# ============== OHLCV Merger Output Paths ==============
OHLCV_MERGER_OUTPUT_DIR = os.path.join(OUTPUT_DIR, "ohlcv_merger")
OHLCV_MERGER_ALL_PATH = os.path.join(OHLCV_MERGER_OUTPUT_DIR, "all_ohlcv_merger.json")
OHLCV_MERGER_NEW_PATH = os.path.join(OHLCV_MERGER_OUTPUT_DIR, "ohlcv_merger_new.json")

# ============== Label Generator Output Paths ==============
LABELS_OUTPUT_DIR = os.path.join(OUTPUT_DIR, "labels")
LABELS_ALL_PATH = os.path.join(LABELS_OUTPUT_DIR, "all_labeled_news.json")
LABELS_NEW_PATH = os.path.join(LABELS_OUTPUT_DIR, "labeled_news_new.json")

# ============== Models Directory ==============
MODELS_DIR = os.path.join(BASE_DIR, "models")

# ============== Signal Predictor Output Paths ==============
SIGNALS_OUTPUT_DIR = os.path.join(OUTPUT_DIR, "signals")
SIGNALS_ALL_PATH = os.path.join(SIGNALS_OUTPUT_DIR, "all_signals.json")
SIGNALS_NEW_PATH = os.path.join(SIGNALS_OUTPUT_DIR, "signals_new.json")

# ============== Mapping Files ==============
COMPANY_MAPPING_PATH = os.path.join(MAPPING_DIR, "companywise_keyword_mapping.csv.csv")
INDEX_MAPPING_PATH = os.path.join(MAPPING_DIR, "index_mapping.csv")

# Aliases for company_tagging_step2.py
MAPPING_CSV_PATH = COMPANY_MAPPING_PATH
TAGGED_OUTPUT_PATH = TAGGED_ALL_PATH
TAGGED_RECENT_PATH = TAGGED_NEW_PATH
RECENT_MERGED_PATH = MERGED_NEWS_NEW_PATH

# ============== OHLCV Fetcher Paths ==============
OHLCV_OUTPUT_DIR = os.path.join(OUTPUT_DIR, "data_fetch_ohlcv")
OHLCV_MAPPING_PATH = os.path.join(BASE_DIR, "CORRECT OHLCV TICK DATA", "mapping_security_ids.csv")

# Directory containing the actual tick/OHLCV data CSVs
# Using the corrected data source provided by user (files are in group_XX)
OHLCV_DATA_DIR = os.path.join(BASE_DIR, "CORRECT OHLCV TICK DATA", "data_ohlcv", "group_XX")

# ============== Price Mapping Output Paths ==============
PRICE_MAPPED_OUTPUT_DIR = os.path.join(OUTPUT_DIR, "price_mapped")
PRICE_MAPPED_ALL_PATH = os.path.join(PRICE_MAPPED_OUTPUT_DIR, "all_sentiment_with_price.json")
PRICE_MAPPED_NEW_PATH = os.path.join(PRICE_MAPPED_OUTPUT_DIR, "sentiment_with_price_new.json")

# ============== Legacy Paths (for backward compatibility with scrapers) ==============
DATA_DIR = os.path.join(BASE_DIR, "data")
CNBC_RAW_NEWS_PATH = CNBC_ALL_PATH
CNBC_RECENT_NEWS_PATH = CNBC_NEW_PATH
LIVEMINT_RAW_NEWS_PATH = LIVEMINT_ALL_PATH
LIVEMINT_RECENT_NEWS_PATH = LIVEMINT_NEW_PATH
MONEYCONTROL_RAW_NEWS_PATH = MONEYCONTROL_ALL_PATH
MONEYCONTROL_RECENT_NEWS_PATH = MONEYCONTROL_NEW_PATH
ET_RAW_NEWS_PATH = ET_ALL_PATH
ET_RECENT_NEWS_PATH = ET_NEW_PATH
MERGED_RAW_NEWS_PATH = MERGED_NEWS_PATH
MERGED_RECENT_NEWS_PATH = MERGED_NEWS_PATH
RECENT_MERGED_PATH = MERGED_NEWS_PATH
INPUT_NEWS_PATH = os.path.join(BASE_DIR, "input_news.json")

# ============== Historic Dataset Path ==============
HISTORIC_DATASET_DIR = os.path.join(BASE_DIR, 'historic_dataset')
