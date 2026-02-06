"""
Step 9: Signal Predictor
Uses trained XGBoost model to predict BUY/SELL/HOLD signals on new articles.
Runs after Step 5 (Feature Builder) to generate ML-based trading signals.
"""

import json
import os
import joblib
import numpy as np
from datetime import datetime, timezone, timedelta

from config import (
    LOG_FILE,
    FEATURES_NEW_PATH,
    DEBERTA_OUTPUT_DIR,
    SENTIMENT_NEW_PATH,
    OHLCV_MERGER_NEW_PATH,
    MODELS_DIR,
)

# ==================================================
# CONFIGURATION
# ==================================================

FEATURE_COLUMNS = [
    # Sentiment features (10)
    "sentiment_score",
    "confidence",
    "positive_prob",
    "negative_prob",
    "neutral_prob",
    "news_source_score",
    "is_regulatory_news",
    "is_negative_event",
    "company_mention_strength",
    "time_decay_15m",
    
    # Market features (Legacy - kept for compatibility/fallback)
    "pre_news_momentum_5m",
    "pre_news_momentum_30m",
    "pre_news_volume_ratio",
    "intraday_volatility",
    "pre_news_price",

    # Pre-Market / Pre-News History (New Concept)
    # The model observes past 30 minutes to predict post-15 min
    "open_at_signal", "high_at_signal", "low_at_signal", "close_at_signal", "volume_at_signal",
    
    # 1 min lookback
    "open_1min", "high_1min", "low_1min", "close_1min", "volume_1min", "volatility_1min_pre_news",
    # 2 min lookback
    "open_2min", "high_2min", "low_2min", "close_2min", "volume_2min", "volatility_2min_pre_news",
    # 5 min lookback
    "open_5min", "high_5min", "low_5min", "close_5min", "volume_5min", "volatility_5min_pre_news",
     # 10 min lookback
    "open_10min", "high_10min", "low_10min", "close_10min", "volume_10min", "volatility_10min_pre_news",
    # 15 min lookback
    "open_15min", "high_15min", "low_15min", "close_15min", "volume_15min", "volatility_15min_pre_news",
    # 20 min lookback
    "open_20min", "high_20min", "low_20min", "close_20min", "volume_20min", "volatility_20min_pre_news",
    # 30 min lookback
    "open_30min", "high_30min", "low_30min", "close_30min", "volume_30min", "volatility_30min_pre_news",
]

LABEL_MAP = {0: "BUY", 1: "SELL", 2: "HOLD"}

MODEL_NAME = "xgb_news_model"
LATEST_MODEL_PATH = os.path.join(MODELS_DIR, f"{MODEL_NAME}_latest.pkl")
META_PATH = os.path.join(MODELS_DIR, f"{MODEL_NAME}_meta.json")

# ==================================================
# LOGGING
# ==================================================

def log(msg):
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"{datetime.now()} | [signal_predictor_step9] {msg}\n")
    print(f"[signal_predictor_step9] {msg}")

# ==================================================
# HELPERS
# ==================================================

def load_json(path):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


def append_to_all(all_path, new_rows):
    """Upsert new_rows into all_path, updating existing ones and adding new ones."""
    existing = load_json(all_path)
    # Map article_id (as string) to index for quick lookup
    existing_map = {str(r.get("article_id")): i for i, r in enumerate(existing)}
    
    added_count = 0
    updated_count = 0
    
    for row in new_rows:
        aid = str(row.get("article_id"))
        if aid in existing_map:
            idx = existing_map[aid]
            # Update existing record (merges new fields like source/full_content/url)
            existing[idx].update(row)
            updated_count += 1
        else:
            existing.append(row)
            added_count += 1
    
    if added_count > 0 or updated_count > 0:
        save_json(all_path, existing)
        log(f"💾 Updated {all_path}: {added_count} new, {updated_count} updated (total: {len(existing)})")
    else:
        log(f"🟡 No changes for {all_path}")
    
    # Return count of truly new records for compatibility
    return [r for r in new_rows if str(r.get("article_id")) not in existing_map]



def load_model_metadata():
    """Load model metadata to get version info."""
    if not os.path.exists(META_PATH):
        return None
    with open(META_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def repair_all_signals(all_path, raw_news_map):
    """Scan all_signals and fill missing metadata for any record."""
    if not os.path.exists(all_path):
        return
    
    data = load_json(all_path)
    repaired_count = 0
    
    for row in data:
        aid = str(row.get("article_id"))
        raw = raw_news_map.get(aid)
        if raw:
            # Check if any field is missing or generic
            needs_repair = False
            if "source" not in row or row.get("source") in ["Unknown", "Unknown Source"]:
                row["source"] = raw.get("source", "Unknown")
                needs_repair = True
            if "full_content" not in row or not row.get("full_content") or row.get("full_content") == row.get("condensed_text"):
                row["full_content"] = raw.get("content", row.get("condensed_text", ""))
                needs_repair = True
            if "url" not in row or not row.get("url"):
                row["url"] = raw.get("url", "")
                needs_repair = True
            
            if needs_repair:
                repaired_count += 1
                
    if repaired_count > 0:
        save_json(all_path, data)
        log(f"🔧 Repaired {repaired_count} historic records in {all_path}")
    else:
        log(f"✨ No historic records in {all_path} needed repair")


# ==================================================
# MAIN PREDICTION LOGIC
# ==================================================

def run_signal_predictor(signals_new_path=None, signals_all_path=None):
    """
    Main entry point for Step 9.
    Loads trained model and predicts signals on new feature vectors.
    
    Returns:
        list: List of enriched articles with predicted signals
    """
    log("=" * 60)
    log("Step 9: Signal Predictor Started")
    log("=" * 60)
    
    # Import here to avoid circular dependency
    from config import (
        SIGNALS_NEW_PATH, SIGNALS_ALL_PATH, RECENT_MERGED_PATH, SENTIMENT_ALL_PATH, MERGED_NEWS_ALL_PATH,
        MONEYCONTROL_ALL_PATH, ET_ALL_PATH, LIVEMINT_ALL_PATH, CNBC_ALL_PATH, 
        BUSINESS_TODAY_ALL_PATH, HINDU_BL_ALL_PATH,
        MONEYCONTROL_NEW_PATH, ET_NEW_PATH, LIVEMINT_NEW_PATH, CNBC_NEW_PATH,
        BUSINESS_TODAY_NEW_PATH, HINDU_BL_NEW_PATH
    )
    
    signals_new_path = signals_new_path or SIGNALS_NEW_PATH
    signals_all_path = signals_all_path or SIGNALS_ALL_PATH
    
    # Check if model exists
    if not os.path.exists(LATEST_MODEL_PATH):
        log("⚠️ No trained model found. Skipping signal prediction.")
        log(f"   Train a model first by accumulating {300}+ labeled samples.")
        return []
    
    # Load model
    try:
        model = joblib.load(LATEST_MODEL_PATH)
        metadata = load_model_metadata()
        model_version = metadata.get("model_version", "unknown") if metadata else "unknown"
        log(f"✅ Loaded model: {LATEST_MODEL_PATH}")
        log(f"   Model version: {model_version}")
        if metadata:
            metrics = metadata.get("validation_metrics", {})
            log(f"   Accuracy: {metrics.get('accuracy', 'N/A')}, F1: {metrics.get('macro_f1', 'N/A')}")
    except Exception as e:
        log(f"❌ Failed to load model: {e}")
        return []
    
    # Check if features exist (Now reading from Step 6 Enriched Output!)
    if not os.path.exists(OHLCV_MERGER_NEW_PATH):
        log(f"⚠️ No enriched feature data found at {OHLCV_MERGER_NEW_PATH}")
        return []

    features = load_json(OHLCV_MERGER_NEW_PATH)
    
    if not features:
        log(f"⚠️ No features to predict on")
        
    log(f"📊 Loaded {len(features)} feature vectors")
    
    # ==================================================
    # OVERNIGHT LOGIC
    # ==================================================
    
    # Import overnight paths
    from config import OVERNIGHT_BUFFER_PATH, OVERNIGHT_SIGNAL_PATH

    def is_market_open():
        """
        Check if market is open (09:30 - 15:30 IST).
        Note: We start at 09:30 to allow 15 mins of fresh data accumulation (09:15-09:30).
        """
        now_utc = datetime.now(timezone.utc)
        now_ist = now_utc + timedelta(hours=5, minutes=30)
        current_time = now_ist.time()
        
        # Market hours: 09:30 to 15:30
        start_time = datetime.strptime("09:30", "%H:%M").time()
        end_time = datetime.strptime("15:30", "%H:%M").time()
        
        is_open = start_time <= current_time <= end_time
        
        log(f"🕒 Current Time (IST): {current_time.strftime('%H:%M:%S')} | Market Open: {is_open}")
        return is_open

    market_is_active = is_market_open()

    # Load previously buffered overnight news if market is now open
    buffered_features = []
    if market_is_active and os.path.exists(OVERNIGHT_BUFFER_PATH):
        buffered_features = load_json(OVERNIGHT_BUFFER_PATH)
        if buffered_features:
            log(f"🌅 Market OPEN: Processing {len(buffered_features)} buffered overnight items")
            # Clear the buffer file immediately to avoid double processing if crash happens later (safeguard)
            save_json(OVERNIGHT_BUFFER_PATH, [])
            
            # Also clear the overnight signal display file
            if os.path.exists(OVERNIGHT_SIGNAL_PATH):
                save_json(OVERNIGHT_SIGNAL_PATH, [])
                log("🧹 Cleared overnight_signal.json")

    # If market is closed, we buffer incoming features instead of predicting
    if not market_is_active:
        log("🌙 Market CLOSED (Overnight Mode)")
        
        if features:
            # 1. Buffer the features
            append_to_all(OVERNIGHT_BUFFER_PATH, features)
            log(f"📥 Buffered {len(features)} items for morning processing")
            
            # 2. Generate simplified "Overnight Signals" (No XGBoost, just Sentiment)
            overnight_signals = []
            
            # Load sentiment/raw data map for enrichment
            sentiment_data = load_json(SENTIMENT_NEW_PATH)
            sentiment_map = {s.get("article_id"): s for s in sentiment_data}
            raw_news_data = load_json(RECENT_MERGED_PATH)
            raw_news_map = {str(n.get("article_id")): n for n in raw_news_data}
            
            for feature_row in features:
                article_id = str(feature_row.get("article_id"))
                
                # Get metadata
                original_article = sentiment_map.get(article_id, {})
                raw_article = raw_news_map.get(article_id, {})
                
                # Create simplified signal object
                overnight_sig = {
                    "article_id": article_id,
                    "symbol": feature_row.get("symbol"),
                    "headline": original_article.get("headline", feature_row.get("headline")),
                    "source": original_article.get("source", raw_article.get("source", "Unknown")),
                    "published_time": feature_row.get("published_time"),
                    "full_content": raw_article.get("content", original_article.get("condensed_text", "")),
                    "sentiment": feature_row.get("sentiment"),
                    "sentiment_score": feature_row.get("sentiment_score"),
                    "confidence": feature_row.get("confidence"),
                    
                    # Placeholder values for compatibility
                    "predicted_signal": "HOLD",  # Default to Neutral/Hold overnight
                    "signal_confidence": 0.0,
                    "buy_prob": 0.0,
                    "sell_prob": 0.0,
                    "hold_prob": 1.0, 
                    "model_version": "overnight_bias",
                    "url": raw_article.get("url", ""),
                    "predicted_at": (datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)).strftime("%Y-%m-%d %H:%M:%S IST"),
                    "is_overnight": True
                }
                overnight_signals.append(overnight_sig)
            
            # Append to overnight display file (cumulative for the night)
            append_to_all(OVERNIGHT_SIGNAL_PATH, overnight_signals)
            log(f"💾 Updated {OVERNIGHT_SIGNAL_PATH} with {len(overnight_signals)} overnight items")
            
        return []

    # ==================================================
    # MARKET OPEN EXECUTION (Process Current + Buffered)
    # ==================================================

    # Merge buffered features with current features
    # Note: Buffered features have "stale" market data from when they were fetched.
    # In a perfect V2 implementation, we would re-fetch fresh OHLCV for them here.
    # For now, we process them with the XGBoost model which (as requested) 
    # will now run since it is > 9:30 AM.
    
    combined_features = buffered_features + features
    
    if not combined_features:
        log("⚠️ No features to predict on (Current or Buffered)")
        return []
        
    log(f"📊 Processing {len(combined_features)} items ({len(buffered_features)} buffered + {len(features)} new)")

    # Also load sentiment data to enrich predictions with original article info
    sentiment_data = load_json(SENTIMENT_NEW_PATH)
    sentiment_map = {s.get("article_id"): s for s in sentiment_data}
    
    sentiment_all = load_json(SENTIMENT_ALL_PATH)
    sentiment_all_map = {s.get("article_id"): s for s in sentiment_all}

    # Load Full/Raw News Content for the dashboard
    raw_news_data = load_json(RECENT_MERGED_PATH)
    raw_news_map = {str(n.get("article_id")): n for n in raw_news_data} # ensure ID is str
    
    raw_news_all = load_json(MERGED_NEWS_ALL_PATH)
    raw_news_all_map = {str(n.get("article_id")): n for n in raw_news_all}

    # Load all individual source files to ensure we catch every article
    extra_sources = [
        MONEYCONTROL_ALL_PATH, ET_ALL_PATH, LIVEMINT_ALL_PATH, CNBC_ALL_PATH, 
        BUSINESS_TODAY_ALL_PATH, HINDU_BL_ALL_PATH,
        MONEYCONTROL_NEW_PATH, ET_NEW_PATH, LIVEMINT_NEW_PATH, CNBC_NEW_PATH,
        BUSINESS_TODAY_NEW_PATH, HINDU_BL_NEW_PATH
    ]
    
    for path in extra_sources:
        try:
            source_data = load_json(path)
            for n in source_data:
                raw_news_all_map[str(n.get("article_id"))] = n
        except Exception:
            pass
    
    # Generate predictions
    predictions = []
    
    # Iterate over COMBINED features
    for feature_row in combined_features:
        article_id = str(feature_row.get("article_id"))
        
        # Extract feature vector
        X = np.array([[feature_row.get(col, 0.0) for col in FEATURE_COLUMNS]])
        
        # Predict
        try:
            pred_proba = model.predict_proba(X)[0]
            
            # Extract probabilities
            buy_prob = float(pred_proba[0])
            sell_prob = float(pred_proba[1])
            hold_prob = float(pred_proba[2])
            
            # Threshold-based decision (fixes HOLD bias)
            # BUY/SELL need 25% confidence AND must beat the competing signal
            # Lowered from 35% because model probabilities are inherently low
            BUY_SELL_THRESHOLD = 0.25
            
            if buy_prob >= BUY_SELL_THRESHOLD and buy_prob > sell_prob:
                predicted_signal = "BUY"
                signal_confidence = buy_prob
            elif sell_prob >= BUY_SELL_THRESHOLD and sell_prob > buy_prob:
                predicted_signal = "SELL"
                signal_confidence = sell_prob
            else:
                predicted_signal = "HOLD"
                signal_confidence = hold_prob
            
            # Get original article metadata (from sentiment step)
            original_article = sentiment_map.get(article_id, sentiment_all_map.get(article_id, {}))
            # Get raw article data (from fetcher step)
            raw_article = raw_news_map.get(article_id, raw_news_all_map.get(article_id, {}))
            
            # Build enriched prediction
            prediction = {
                "article_id": article_id,
                "symbol": feature_row.get("symbol"),
                "company_name": feature_row.get("company_name"),
                "headline": original_article.get("headline", feature_row.get("headline")),
                "source": original_article.get("source", raw_article.get("source", "Unknown")),
                "published_time": feature_row.get("published_time"),
                "condensed_text": original_article.get("condensed_text", ""),
                "full_content": raw_article.get("content", original_article.get("condensed_text", "")),
                "sentiment": feature_row.get("sentiment"),
                "sentiment_score": feature_row.get("sentiment_score"),
                "confidence": feature_row.get("confidence"),
                "predicted_signal": predicted_signal,
                "signal_confidence": round(signal_confidence, 4),
                "buy_prob": round(buy_prob, 4),
                "sell_prob": round(sell_prob, 4),
                "hold_prob": round(hold_prob, 4),
                "model_version": model_version,
                "url": raw_article.get("url", ""),
                "predicted_at": (datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)).strftime("%Y-%m-%d %H:%M:%S IST"),
            }
            
            predictions.append(prediction)
            
        except Exception as e:
            log(f"❌ Prediction failed for article {article_id}: {e}")
            continue
    
    if not predictions:
        log("⚠️ No predictions generated")
        return []
    
    # Save signals
    save_json(signals_new_path, predictions)
    log(f"💾 Saved {len(predictions)} predictions to {signals_new_path}")
    
    # Append to cumulative signals
    truly_new = append_to_all(signals_all_path, predictions)
    log(f"➕ Appended {len(truly_new)} new signals to cumulative file")
    
    # Retroactive repair of ALL historic signals for source/content/url coverage
    repair_all_signals(signals_all_path, raw_news_all_map)
    
    # Log signal distribution
    buy_count = sum(1 for p in predictions if p["predicted_signal"] == "BUY")
    sell_count = sum(1 for p in predictions if p["predicted_signal"] == "SELL")
    hold_count = sum(1 for p in predictions if p["predicted_signal"] == "HOLD")
    
    log("=" * 60)
    log(f"Step 9 Complete: {len(predictions)} signals generated")
    log(f"   📊 BUY: {buy_count}, SELL: {sell_count}, HOLD: {hold_count}")
    log("=" * 60)
    
    return predictions


if __name__ == "__main__":
    signals = run_signal_predictor()
    print(f"\n✅ Signal Predictor completed: {len(signals)} signals generated")
