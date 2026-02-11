"""
Step 6: OHLCV Merge
Merges news features with 15-minute OHLCV data to create labeled training data.
"""
import json
import os
import pandas as pd
from datetime import datetime, timedelta, timezone

from config import (
    LOG_FILE,
    FEATURES_NEW_PATH,
    OHLCV_MERGER_OUTPUT_DIR,
    OHLCV_MERGER_ALL_PATH,
    OHLCV_MERGER_NEW_PATH,
    OHLCV_DATA_DIR,
)

# ==================================================
# PATHS
# ==================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

STEP5_FILE = FEATURES_NEW_PATH  # Read from features_new.json

OHLCV_DIR = OHLCV_DATA_DIR

# ==================================================
# HELPERS
# ==================================================

def sanitize_for_filename(name: str) -> str:
    """Sanitize company name for filename (matches ohlcv_fetcher.py logic)"""
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 -_.")
    cleaned = "".join(ch for ch in name if ch in allowed).strip()
    return cleaned or "UNKNOWN"


def parse_published_time(published_time):
    """Parse various published_time formats to datetime (matches feature_builder_step5.py logic)"""
    if not published_time:
        return None
    
    try:
        # Format: "05:16 PM | 17 Jan 2026"
        if "|" in published_time:
            time_part, date_part = published_time.split("|")
            time_part = time_part.strip()
            date_part = date_part.strip()
            dt_str = f"{date_part} {time_part}"
            
            # Handle MM:SS in time part if present
            fmt = "%d %b %Y %I:%M %p"
            if len(time_part.split(":")) == 3:  # Has seconds: 08:59:00 AM
                fmt = "%d %b %Y %I:%M:%S %p"
                
            dt = datetime.strptime(dt_str, fmt)
            return dt.replace(tzinfo=timezone.utc)
        
        # Format: "January 17, 2026/ 14:47 IST"
        if "/" in published_time and "IST" in published_time:
            dt_str = published_time.replace(" IST", "").replace("/", "")
            dt = datetime.strptime(dt_str.strip(), "%B %d, %Y %H:%M")
            # Convert IST to UTC by subtracting 5 hours 30 minutes
            dt_utc = dt - timedelta(hours=5, minutes=30)
            return dt_utc.replace(tzinfo=timezone.utc)
        
        # Format: "2026-01-17 17:25:29"
        if "-" in published_time and ":" in published_time:
            dt = datetime.strptime(published_time[:19], "%Y-%m-%d %H:%M:%S")
            return dt.replace(tzinfo=timezone.utc)
        
        # Format: "January 17, 2026 at 02:44 PM"
        if " at " in published_time:
            dt = datetime.strptime(published_time, "%B %d, %Y at %I:%M %p")
            return dt.replace(tzinfo=timezone.utc)
        
    except Exception as e:
        log(f"Could not parse time '{published_time}': {e}")
    
    return None


def log(msg: str):
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"{datetime.now()} | [ohlcv_merge_step6] {msg}\n")
    print(f"[ohlcv_merge_step6] {msg}")


def save_json(path: str, data: list):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


def load_json(path: str) -> list:
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            log(f"JSON load error ({path}): {e}")
    return []


def append_to_all(all_path: str, new_rows: list) -> list:
    """Append new_rows to all_path, deduplicating by (article_id, symbol)."""
    existing = load_json(all_path)
    existing_keys = {(r.get("article_id"), r.get("symbol")) for r in existing}
    
    fresh = [r for r in new_rows if (r.get("article_id"), r.get("symbol")) not in existing_keys]
    
    if fresh:
        all_data = existing + fresh
        save_json(all_path, all_data)
        log(f"💾 Appended {len(fresh)} new rows to {all_path} (total: {len(all_data)})")
    else:
        log(f"🟡 No new rows to append to {all_path}")
    
    return fresh


def load_ohlcv(company_name, news_date):
    """
    Load 1-min OHLCV CSV for a company on a specific date.
    Matches the format from ohlcv_fetcher.py: [CompanyName]/[CompanyName] DD-MM-YYYY.csv
    """
    sanitized_name = sanitize_for_filename(company_name)
    date_str = news_date.strftime("%d-%m-%Y")
    
    company_dir = os.path.join(OHLCV_DIR, sanitized_name)
    file_path = os.path.join(company_dir, f"{sanitized_name} {date_str}.csv")
    
    if not os.path.exists(file_path):
        return None

    df = pd.read_csv(file_path)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    return df.sort_values("timestamp")


def find_next_15m_candle(df, news_time):
    """
    Get the 15-minute window after news by aggregating 1-minute candles.
    Returns OHLCV for the 15 minutes following the news.
    """
    # Convert timezone-aware datetime to naive for pandas comparison
    if news_time.tzinfo is not None:
        news_time = news_time.replace(tzinfo=None)
    
    # Find candles within the 15-minute window after news
    end_time = news_time + timedelta(minutes=15)
    window = df[(df["timestamp"] >= news_time) & (df["timestamp"] < end_time)]
    
    if window.empty:
        return None
    
    # Aggregate 1-minute candles into 15-minute OHLCV
    return {
        "open_15m": float(window["open"].iloc[0]),
        "high_15m": float(window["high"].max()),
        "low_15m": float(window["low"].min()),
        "close_15m": float(window["close"].iloc[-1]),
        "volume_15m": float(window["volume"].sum()),
        "return_15m": float(((window["close"].iloc[-1] - window["open"].iloc[0]) / window["open"].iloc[0]) * 100)
    }


def get_pre_market_stats(company_name, news_time):
    """
    Fetch comprehensive pre-news stats including 1, 2, 5, 10, 15, 20, 30 min lookbacks.
    Handles weekends/holidays by searching backwards for the last available trading data.
    """
    # 1. Try finding data for the news date
    current_date = news_time.date()
    df = load_ohlcv(company_name, current_date)
    
    # 2. If no data (e.g. Sunday), look back up to 5 days
    lookback_days = 0
    while df is None and lookback_days < 5:
        lookback_days += 1
        prev_date = current_date - timedelta(days=lookback_days)
        # log(f"No data for {current_date}, checking {prev_date}...")
        df = load_ohlcv(company_name, prev_date)
    
    if df is None:
        return {} # Truly no data found

    # Make datetimes naive for comparison
    if news_time.tzinfo is not None:
        news_time = news_time.replace(tzinfo=None)
        
    # If we found data from a PREVIOUS day, effectively the "news time" relative to that data 
    # is the END of that day (uses the last known data)
    if lookback_days > 0:
        # Use the very last timestamp in the file as reference
        reference_time = df["timestamp"].max()
    else:
        reference_time = news_time

    # Filter for data BEFORE the reference time
    past_data = df[df["timestamp"] <= reference_time].sort_values("timestamp")
    
    if len(past_data) == 0:
        return {}

    stats = {}
    
    # Snapshot at signal (open/close at exact news time or last available)
    last_row = past_data.iloc[-1]
    stats["open_at_signal"] = float(last_row["open"])
    stats["high_at_signal"] = float(last_row["high"])
    stats["low_at_signal"] = float(last_row["low"])
    stats["close_at_signal"] = float(last_row["close"])
    stats["volume_at_signal"] = float(last_row["volume"])
    
    # Granular Lookbacks
    validation_times = [1, 2, 5, 10, 15, 20, 30, 45, 60, 90, 120]
    
    for minutes in validation_times:
        # Find the row closest to 'minutes' ago
        target_time = reference_time - timedelta(minutes=minutes)
        
        # Get slice of data up to that target time
        # We want the specific candle at T-minus-X minutes
        # Since likely 1-min intervals, we look for timestamp <= target_time
        
        # Taking the closest row BEFORE or AT expected time
        closest_row_candidates = past_data[past_data["timestamp"] <= target_time]
        
        if not closest_row_candidates.empty:
            row = closest_row_candidates.iloc[-1]
            suffix = f"_{minutes}min"
            stats[f"open{suffix}"] = float(row["open"])
            stats[f"high{suffix}"] = float(row["high"])
            stats[f"low{suffix}"] = float(row["low"])
            stats[f"close{suffix}"] = float(row["close"])
            stats[f"volume{suffix}"] = float(row["volume"])
            
            # Add simple volatility (High-Low) for this candle
            stats[f"volatility{suffix}_pre_news"] = (float(row["high"]) - float(row["low"])) / float(row["open"]) if float(row["open"]) > 0 else 0.0
        else:
            # Data might not go back that far (e.g. market just opened)
            pass
            
    return stats


# ==================================================
# MAIN STEP-6
# ==================================================

def run_ohlcv_merge(input_path: str = None) -> list:
    """
    Main entry point for Step 6.
    Merges news features with OHLCV data.
    Returns the list of enriched rows.
    """
    # Determine input file
    input_file = input_path or STEP5_FILE
    
    if not os.path.exists(input_file):
        print(f"⚠️ Step-5 output not found at {input_file}")
        return []

    with open(input_file, "r", encoding="utf-8") as f:
        news_features = json.load(f)

    if not news_features:
        print("⚠️ No news features to process")
        return []

    print(f"📥 Loaded {len(news_features)} feature rows from Step 5")

    enriched_rows = []

    for row in news_features:

        symbol = row.get("symbol")
        company_name = row.get("company_name")
        published_time_str = row.get("published_time")
        
        if not company_name or not published_time_str:
            continue
        
        # Parse the actual news time
        news_time = parse_published_time(published_time_str)
        if not news_time:
            continue
        
        # 1. Get Pre-Market / Pre-News Data (Input Features)
        pre_market_data = get_pre_market_stats(company_name, news_time)
        
        # If we have absolutely no data (not even from previous days), we might skip or keep with defaults
        # For training, it's safer to skip. For inference, maybe critical.
        # User said: "if there is no pre market data availabele it will get the last available data"
        # get_pre_market_stats handles the "last available" logic internally.
        if not pre_market_data:
            # log(f"Missing pre-market data for {company_name} at {news_time}")
            continue

        row.update(pre_market_data)

        # 2. Get Post-News Data (Training Label) for Label Generator
        # We need the 15-min reaction strictly AFTER the news.
        ohlcv_df = load_ohlcv(company_name, news_time)
        
        # If finding 15m candle fails (e.g. market closed), we can't label it for training.
        # But we still want to save it if it triggers an inference?
        # For now, if we are building the "labeled_news.json", we need a label.
        
        candle_data = None
        if ohlcv_df is not None:
             candle_data = find_next_15m_candle(ohlcv_df, news_time)
        
        if candle_data:
             row.update(candle_data)
        else:
             # Mark as unlabelable (optional, label generator handles missing returns)
             pass

        enriched_rows.append(row)



    # Create output directory
    os.makedirs(OHLCV_MERGER_OUTPUT_DIR, exist_ok=True)
    
    # Save ohlcv_merger_new.json (current run only)
    save_json(OHLCV_MERGER_NEW_PATH, enriched_rows)
    log(f"💾 Saved ohlcv_merger_new.json ({len(enriched_rows)} enriched rows)")
    
    # Append to all_ohlcv_merger.json (cumulative)
    truly_new = append_to_all(OHLCV_MERGER_ALL_PATH, enriched_rows)
    log(f"➕ Appended {len(truly_new)} to all_ohlcv_merger.json (cumulative)")
    
    log("=" * 60)
    log(f"Step 6 Complete: {len(enriched_rows)} enriched rows created")
    log("=" * 60)
    
    return enriched_rows


if __name__ == "__main__":
    enriched = run_ohlcv_merge()
    print(f"\n✅ OHLCV Merge completed: {len(enriched)} rows created")
