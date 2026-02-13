"""
Step 5: Feature Builder
Extracts features from sentiment analysis output for downstream ML models.
Builds feature vectors including sentiment scores, source credibility, regulatory flags, and market context.
"""
import json
import math
import os
import pandas as pd
from datetime import datetime, timezone, timedelta

from config import (
    LOG_FILE,
    SENTIMENT_NEW_PATH,
    DEBERTA_OUTPUT_DIR,
    FEATURES_OUTPUT_DIR,
    FEATURES_ALL_PATH,
    FEATURES_NEW_PATH,
    OHLCV_DATA_DIR,
)

# ==================================================
# OHLCV DATA PATH
# ==================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OHLCV_DIR = OHLCV_DATA_DIR

# ==================================================
# CONFIGURATION
# ==================================================

SOURCE_SCORE = {
    "Moneycontrol": 0.90,
    "CNBC-TV18": 0.95,
    "Economic Times": 0.85
}

REGULATORY_WORDS = [
    "rbi", "sebi", "ccpa", "regulator",
    "guidelines", "intervention", "penalty"
]

NEGATIVE_EVENT_WORDS = [
    "delay", "failed", "refund", "penalty",
    "fraud", "loss", "violation", "fine"
]

# ==================================================
# LOGGING
# ==================================================

def log(msg: str):
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"{datetime.now()} | [feature_builder_step5] {msg}\n")
    print(f"[feature_builder_step5] {msg}")

# ==================================================
# HELPERS
# ==================================================

def parse_published_time(published_time):
    """Parse various published_time formats to datetime.
    
    Article timestamps are in IST - properly converts to UTC.
    Returns timezone-aware datetime in UTC.
    """
    if not published_time:
        return None
    
    try:
        # Format: "10:49:00 AM | 13 Feb 2026" (IST)
        if "|" in published_time:
            time_part, date_part = published_time.split("|")
            time_part = time_part.strip()
            date_part = date_part.strip()
            dt_str = f"{date_part} {time_part}"
            
            # Handle with/without seconds in time format
            fmt = "%d %b %Y %I:%M %p"
            if len(time_part.split(":")) == 3:  # Has seconds: "10:49:00 AM"
                fmt = "%d %b %Y %I:%M:%S %p"
            
            dt = datetime.strptime(dt_str, fmt)
            # Properly assign IST timezone and convert to UTC
            dt_ist = dt.replace(tzinfo=timezone(timedelta(hours=5, minutes=30)))
            return dt_ist.astimezone(timezone.utc)
        
        # Format: "January 17, 2026/ 14:47 IST"
        if "/" in published_time and "IST" in published_time:
            dt_str = published_time.replace(" IST", "").replace("/", "")
            dt = datetime.strptime(dt_str.strip(), "%B %d, %Y %H:%M")
            # Properly assign IST timezone and convert to UTC
            dt_ist = dt.replace(tzinfo=timezone(timedelta(hours=5, minutes=30)))
            return dt_ist.astimezone(timezone.utc)
        
        # Format: "2026-01-17 17:25:29" (assume IST)
        if "-" in published_time and ":" in published_time:
            dt = datetime.strptime(published_time[:19], "%Y-%m-%d %H:%M:%S")
            dt_ist = dt.replace(tzinfo=timezone(timedelta(hours=5, minutes=30)))
            return dt_ist.astimezone(timezone.utc)
        
        # Format: "January 17, 2026 at 02:44 PM" (assume IST)
        if " at " in published_time:
            dt = datetime.strptime(published_time, "%B %d, %Y at %I:%M %p")
            dt_ist = dt.replace(tzinfo=timezone(timedelta(hours=5, minutes=30)))
            return dt_ist.astimezone(timezone.utc)
        
    except Exception as e:
        log(f"Could not parse time '{published_time}': {e}")
    
    return None


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


def append_to_all(all_path: str, new_features: list) -> list:
    """
    Append new_features to all_path, deduplicating by (article_id, symbol).
    Returns the list of truly new features that were appended.
    """
    existing = load_json(all_path)
    existing_keys = {(f.get("article_id"), f.get("symbol")) for f in existing}
    
    fresh = [f for f in new_features if (f.get("article_id"), f.get("symbol")) not in existing_keys]
    
    if fresh:
        all_data = existing + fresh
        save_json(all_path, all_data)
        log(f"💾 Appended {len(fresh)} new features to {all_path} (total: {len(all_data)})")
    else:
        log(f"🟡 No new features to append to {all_path}")
    
    return fresh


def time_decay_15m(published_time):
    """Calculate exponential time decay with 15-minute half-life.
    
    Returns value in (0, 1] range:
    - Returns 1.0 if parsing fails (most recent)
    - Clamps future timestamps to 0 minutes (decay = 1.0)
    - Applies exponential decay for past timestamps
    """
    dt = parse_published_time(published_time)
    if not dt:
        # If we can't parse time, assume it's recent (return 1.0)
        return 1.0

    now = datetime.now(timezone.utc)
    minutes_diff = (now - dt).total_seconds() / 60
    
    # Clamp future timestamps to 0 minutes to prevent exp() from exploding
    if minutes_diff < 0:
        minutes_diff = 0.0
    
    # Exponential decay: exp(-t/15)
    # This ensures output is always in (0, 1] since minutes_diff >= 0
    return round(math.exp(-minutes_diff / 15), 4)


def company_mention_strength(text, company):
    if not company:
        return 0
    
    # Extract meaningful keywords from company name (ignore common suffixes)
    # This handles cases like "Hindustan Aeronautics Limited" vs "Hindustan Aeronautics"
    stop_words = {'limited', 'ltd', 'ltd.', 'inc', 'corp', 'corporation', 'company', 'co'}
    words = [w.strip() for w in company.lower().split() if len(w.strip()) > 2]
    keywords = [w for w in words if w not in stop_words]
    
    if not keywords:
        # If only stop words, use full name
        return text.lower().count(company.lower())
    
    # Count mentions of any keyword
    total_count = 0
    for keyword in keywords:
        total_count += text.lower().count(keyword)
    
    return total_count


def is_regulatory_news(text):
    return int(any(w in text for w in REGULATORY_WORDS))


def is_negative_event(text):
    return int(any(w in text for w in NEGATIVE_EVENT_WORDS))


# ==================================================
# MARKET FEATURE EXTRACTION
# ==================================================

def sanitize_for_filename(name: str) -> str:
    """Sanitize company name for filename (matches ohlcv_fetcher.py logic)"""
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 -_.")
    cleaned = "".join(ch for ch in name if ch in allowed).strip()
    return cleaned or "UNKNOWN"


def load_ohlcv_for_features(company_name, news_date):
    """
    Load 1-min OHLCV CSV for a company on a specific date.
    Handles weekends/holidays by searching backwards up to 5 days.
    Returns pandas DataFrame or None if file doesn't exist.
    """
    if not company_name or not news_date:
        return None
        
    sanitized_name = sanitize_for_filename(company_name)
    
    # Try the news date first
    current_date = news_date if isinstance(news_date, datetime) else news_date
    if not isinstance(current_date, datetime):
        current_date = datetime.combine(news_date, datetime.min.time())
    
    # Look back up to 5 days for available data (handles weekends/holidays)
    for lookback_days in range(6):  # 0 to 5 days back
        check_date = current_date - timedelta(days=lookback_days)
        date_str = check_date.strftime("%d-%m-%Y")
        
        company_dir = os.path.join(OHLCV_DIR, sanitized_name)
        file_path = os.path.join(company_dir, f"{sanitized_name} {date_str}.csv")
        
        if os.path.exists(file_path):
            try:
                df = pd.read_csv(file_path)
                df["timestamp"] = pd.to_datetime(df["timestamp"])
                return df.sort_values("timestamp")
            except Exception as e:
                log(f"Error loading OHLCV for {company_name} on {date_str}: {e}")
                continue
    
    # No data found in last 5 days
    return None


def calculate_market_features(company_name, news_time):
    """
    Extract pre-news market features from OHLCV data.
    Uses ONLY data from BEFORE news_time (no future leakage).
    
    Returns dict with 5 market features or None if data unavailable:
    - pre_news_momentum_5m: Price change in last 5 minutes (%)
    - pre_news_momentum_30m: Price change in last 30 minutes (%)
    - pre_news_volume_ratio: Current volume vs rolling average
    - intraday_volatility: Today's high-low range (%)
    - pre_news_price: Price when news published
    """
    if not company_name or not news_time:
        return None
    
    # Load OHLCV data
    ohlcv_df = load_ohlcv_for_features(company_name, news_time)
    if ohlcv_df is None or len(ohlcv_df) == 0:
        return None
    
    # Critical: OHLCV timestamps are stored in IST (naive)
    # news_time comes from parse_published_time() as UTC
    # We need to convert UTC → IST, then make naive for comparison
    if news_time.tzinfo is not None:
        # Convert UTC to IST (UTC + 5:30)
        news_time_ist = news_time + timedelta(hours=5, minutes=30)
        news_time = news_time_ist.replace(tzinfo=None)
    
    # Get data BEFORE news (critical: no future leakage!)
    pre_news_df = ohlcv_df[ohlcv_df['timestamp'] < news_time]
    
    if len(pre_news_df) < 5:  # Need at least 5 minutes of data
        return None
    
    try:
        # 1. Price momentum (last 5 minutes)
        last_5min = pre_news_df.tail(5)
        if len(last_5min) >= 2:
            open_5m = last_5min.iloc[0]['open']
            close_5m = last_5min.iloc[-1]['close']
            momentum_5m = ((close_5m - open_5m) / open_5m * 100) if open_5m > 0 else 0.0
        else:
            momentum_5m = 0.0
        
        # 2. Price momentum (last 30 minutes)
        if len(pre_news_df) >= 30:
            last_30min = pre_news_df.tail(30)
            open_30m = last_30min.iloc[0]['open']
            close_30m = last_30min.iloc[-1]['close']
            momentum_30m = ((close_30m - open_30m) / open_30m * 100) if open_30m > 0 else 0.0
        else:
            momentum_30m = momentum_5m  # Fallback to 5-min if less data
        
        # 3. Volume ratio (current vs average)
        avg_volume = pre_news_df['volume'].mean()
        current_volume = pre_news_df.iloc[-1]['volume']
        volume_ratio = (current_volume / avg_volume) if avg_volume > 0 else 1.0
        
        # 4. Intraday volatility (high-low range)
        intraday_high = pre_news_df['high'].max()
        intraday_low = pre_news_df['low'].min()
        intraday_open = pre_news_df.iloc[0]['open']
        volatility = ((intraday_high - intraday_low) / intraday_open * 100) if intraday_open > 0 else 0.0
        
        # 5. Current price (for context)
        pre_news_price = pre_news_df.iloc[-1]['close']
        
        return {
            'pre_news_momentum_5m': round(momentum_5m, 4),
            'pre_news_momentum_30m': round(momentum_30m, 4),
            'pre_news_volume_ratio': round(volume_ratio, 4),
            'intraday_volatility': round(volatility, 4),
            'pre_news_price': round(pre_news_price, 2)
        }
        
    except Exception as e:
        log(f"Error calculating market features for {company_name}: {e}")
        return None


# ==================================================
# FEATURE ROW BUILDER
# ==================================================

def build_feature_row(news):
    if "sentiment" not in news or "confidence" not in news:
        return None

    # Compute sentiment_score as positive_prob - negative_prob
    positive_prob = news.get("positive_prob")
    negative_prob = news.get("negative_prob")
    
    if positive_prob is not None and negative_prob is not None:
        sentiment_score = round(positive_prob - negative_prob, 4)
    else:
        sentiment_score = 0.0

    text_blob = (news.get("headline", "") + " " + news.get("condensed_text", "")).lower()
    
    # Extract market features
    news_time = parse_published_time(news.get("published_time", ""))
    market_features = calculate_market_features(
        news.get("CompanyName"),
        news_time
    )

    return {
        "article_id": news.get("article_id"),
        "symbol": news.get("Symbol"),
        "company_name": news.get("CompanyName"),
        "headline": news.get("headline"),
        
        "sentiment": news.get("sentiment"),
        "sentiment_score": sentiment_score,
        "confidence": news["confidence"],
        
        # Sentiment probabilities from DeBERTa (preserve valid 0.0 values)
        "positive_prob": news["positive_prob"] if news.get("positive_prob") is not None else 0.0,
        "negative_prob": news["negative_prob"] if news.get("negative_prob") is not None else 0.0,
        "neutral_prob": news["neutral_prob"] if news.get("neutral_prob") is not None else 0.0,

        "news_source_score": SOURCE_SCORE.get(
            news.get("source", ""), 0.7
        ),

        "is_regulatory_news": is_regulatory_news(text_blob),
        "is_negative_event": is_negative_event(text_blob),

        "company_mention_strength": company_mention_strength(
            text_blob, news.get("CompanyName", "")
        ),

        "time_decay_15m": time_decay_15m(
            news.get("published_time", "")
        ),
        
        # Market features (use explicit None checks to preserve valid 0.0 values)
        "pre_news_momentum_5m": news["pre_news_momentum_5m"] if news.get("pre_news_momentum_5m") is not None else (market_features.get('pre_news_momentum_5m') if market_features else None),
        "pre_news_momentum_30m": news["pre_news_momentum_30m"] if news.get("pre_news_momentum_30m") is not None else (market_features.get('pre_news_momentum_30m') if market_features else None),
        "pre_news_volume_ratio": news["pre_news_volume_ratio"] if news.get("pre_news_volume_ratio") is not None else (market_features.get('pre_news_volume_ratio') if market_features else None),
        "intraday_volatility": news["intraday_volatility"] if news.get("intraday_volatility") is not None else (market_features.get('intraday_volatility') if market_features else None),
        "pre_news_price": news["pre_news_price"] if news.get("pre_news_price") is not None else (market_features.get('pre_news_price') if market_features else None),
        
        "published_time": news.get("published_time"),
        "source": news.get("source"),
        "url": news.get("url"),
    }


# ==================================================
# MAIN EXECUTION FUNCTION
# ==================================================

def run_feature_builder(input_path: str = None) -> list:
    """
    Main entry point for Step 5.
    Reads from DeBERTa sentiment output, builds feature vectors.
    Returns the list of feature rows.
    """
    log("=" * 60)
    log("Step 5: Feature Builder Started")
    log("=" * 60)
    
    # Determine input file
    input_file = input_path or SENTIMENT_NEW_PATH
    
    if not os.path.exists(input_file):
        log(f"🟡 No sentiment data found at {input_file}")
        return []
    
    # Load sentiment data
    try:
        with open(input_file, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        log(f"❌ Error loading {input_file}: {e}")
        return []
    
    if not data:
        log("🟡 No data to process")
        return []
    
    log(f"📥 Loaded {len(data)} articles from {input_file}")
    
    # Build features
    all_features = []
    for item in data:
        if not isinstance(item, dict):
            continue
        row = build_feature_row(item)
        if row:
            all_features.append(row)
    
    if not all_features:
        log("⚠️ No valid features could be extracted")
        return []
    
    log(f"✔ Built {len(all_features)} feature vectors")
    
    # Create output directory
    os.makedirs(FEATURES_OUTPUT_DIR, exist_ok=True)
    
    # Save features_new.json (current run only)
    save_json(FEATURES_NEW_PATH, all_features)
    log(f"💾 Saved features_new.json ({len(all_features)} features)")
    
    # Append to all_features.json (cumulative)
    truly_new = append_to_all(FEATURES_ALL_PATH, all_features)
    log(f"➕ Appended {len(truly_new)} to all_features.json (cumulative)")
    
    # Also save to legacy location for backward compatibility
    legacy_output = os.path.join(DEBERTA_OUTPUT_DIR, "step5_features.json")
    save_json(legacy_output, all_features)
    log(f"💾 Saved to legacy path: {legacy_output}")
    
    log("=" * 60)
    log(f"Step 5 Complete: {len(all_features)} features extracted")
    log("=" * 60)
    
    return all_features


if __name__ == "__main__":
    features = run_feature_builder()
    print(f"\n✅ Feature Builder completed: {len(features)} features extracted")
