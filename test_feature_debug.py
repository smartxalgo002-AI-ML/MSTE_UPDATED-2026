"""
Test script to debug why calculate_market_features returns null
"""
import os
import sys
from datetime import datetime, timezone, timedelta
import pandas as pd

# Add modules to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'modules'))

from feature_builder_step5 import parse_published_time, load_ohlcv_for_features, sanitize_for_filename
from config import OHLCV_DATA_DIR

# Test with actual article data
company_name = "Hindustan Aeronautics Limited"
published_time_str = "February 13, 2026/ 12:07 IST"

print(f"Testing with: {company_name}")
print(f"Published: {published_time_str}")
print(f"OHLCV_DATA_DIR: {OHLCV_DATA_DIR}")
print("=" * 60)

# 1. Test timestamp parsing
news_time = parse_published_time(published_time_str)
print(f"\n1. Parsed timestamp: {news_time}")
print(f"   Timezone: {news_time.tzinfo if news_time else 'None'}")

# 2. Test file path construction
if news_time:
    sanitized_name = sanitize_for_filename(company_name)
    date_str = news_time.strftime("%d-%m-%Y")
    
    company_dir = os.path.join(OHLCV_DATA_DIR, sanitized_name)
    file_path = os.path.join(company_dir, f"{sanitized_name} {date_str}.csv")
    
    print(f"\n2. File path construction:")
    print(f"   Sanitized name: {sanitized_name}")
    print(f"   Date string: {date_str}")
    print(f"   File path: {file_path}")
    print(f"   Exists: {os.path.exists(file_path)}")

# 3. Test OHLCV loading
if news_time:
    ohlcv_df = load_ohlcv_for_features(company_name, news_time)
    print(f"\n3. OHLCV loading:")
    if ohlcv_df is not None:
        print(f"   Loaded {len(ohlcv_df)} rows")
        print(f"   First timestamp: {ohlcv_df.iloc[0]['timestamp']}")
        print(f"   Last timestamp: {ohlcv_df.iloc[-1]['timestamp']}")
        
        # 4. Test pre-news filtering
        news_time_naive = news_time.replace(tzinfo=None) if news_time.tzinfo else news_time
        pre_news_df = ohlcv_df[ohlcv_df['timestamp'] < news_time_naive]
        
        print(f"\n4. Pre-news filtering:")
        print(f"   News time (naive): {news_time_naive}")
        print(f"   Pre-news rows: {len(pre_news_df)}")
        
        if len(pre_news_df) > 0:
            print(f"   Last pre-news timestamp: {pre_news_df.iloc[-1]['timestamp']}")
            print(f"   Last pre-news close: {pre_news_df.iloc[-1]['close']}")
        
        if len(pre_news_df) < 5:
            print(f"   [ERROR] NOT ENOUGH DATA (<5 rows) - This is why it returns None!")
        else:
            print(f"   [OK] Sufficient data for calculation")
    else:
        print(f"   [ERROR] Failed to load OHLCV data")
