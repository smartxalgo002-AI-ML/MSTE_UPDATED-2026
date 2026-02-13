"""
Historic Dataset Training Script

One-time script to process historic dataset and train initial XGBoost model.
This script:
1. Loads all historic JSON files from historic_dataset folder
2. Runs sentiment analysis using DeBERTa
3. Calculates returns and generates labels
4. Trains XGBoost model
5. Creates flag file to prevent re-training

Usage:
    python train_historic.py
    python train_historic.py --force  # Force re-train even if already trained
"""

import os
import sys
import json
import glob
import numpy as np
from datetime import datetime
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import BASE_DIR, MODELS_DIR, LOG_FILE
from modules.deberta_step4 import predict_sentiment
from modules.xgboost_trainer_step8 import (
    FEATURE_COLUMNS, LABEL_MAP, MODEL_NAME,
    extract_xy, save_json, log
)

import joblib
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, f1_score, confusion_matrix, recall_score
from xgboost import XGBClassifier

# Configuration
HISTORIC_DATA_DIR = os.path.join(BASE_DIR, "historic_dataset")
HISTORIC_FLAG_FILE = os.path.join(MODELS_DIR, ".historic_trained")
HISTORIC_MODEL_PATH = os.path.join(MODELS_DIR, f"{MODEL_NAME}_historic.pkl")
HISTORIC_META_PATH = os.path.join(MODELS_DIR, f"{MODEL_NAME}_historic_meta.json")
LATEST_MODEL_PATH = os.path.join(MODELS_DIR, f"{MODEL_NAME}_latest.pkl")
META_PATH = os.path.join(MODELS_DIR, f"{MODEL_NAME}_meta.json")


def log_historic(msg):
    """Log message with historic prefix."""
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"{datetime.now()} | [train_historic] {msg}\n")
    print(f"[train_historic] {msg}")


def load_historic_data():
    """Load all JSON files from historic_dataset folder."""
    log_historic(f"Loading historic data from: {HISTORIC_DATA_DIR}")
    
    if not os.path.exists(HISTORIC_DATA_DIR):
        log_historic(f"❌ Historic dataset directory not found: {HISTORIC_DATA_DIR}")
        return []
    
    json_files = glob.glob(os.path.join(HISTORIC_DATA_DIR, "*.json"))
    log_historic(f"Found {len(json_files)} JSON files")
    
    all_articles = []
    for file_path in json_files:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, list):
                    all_articles.extend(data)
                else:
                    all_articles.append(data)
        except Exception as e:
            log_historic(f"⚠️ Error loading {file_path}: {e}")
            continue
    
    log_historic(f"Loaded {len(all_articles)} total articles from historic dataset")
    return all_articles


def calculate_return_and_label(article):
    """
    Calculate return from OHLCV data and generate label.
    
    Uses 15-minute timeframe for consistency with live data.
    """
    try:
        # Get signal price and 15-minute close
        open_price = article.get("open_at_signal")
        close_15m = article.get("close_15min")
        
        if open_price is None or close_15m is None or open_price == 0:
            return None, None, None
        
        # Calculate return percentage
        return_15m = ((close_15m - open_price) / open_price) * 100
        
        # Calculate volatility (high-low range / open)
        high_15m = article.get("high_15min", close_15m)
        low_15m = article.get("low_15min", close_15m)
        volatility_15m = ((high_15m - low_15m) / open_price) * 100 if open_price != 0 else 0
        
        # Generate label based on return thresholds
        if return_15m >= 0.5:
            label = "BUY"
            label_strength = return_15m
            label_reason = "price_up_15m"
        elif return_15m <= -0.5:
            label = "SELL"
            label_strength = abs(return_15m)
            label_reason = "price_down_15m"
        else:
            label = "HOLD"
            label_strength = abs(return_15m)
            label_reason = "flat_move"
        
        return {
            "return_15m": round(return_15m, 4),
            "volatility_15m": round(volatility_15m, 4),
            "label": label,
            "label_strength": round(label_strength, 4),
            "label_reason": label_reason
        }
    
    except Exception as e:
        log_historic(f"⚠️ Error calculating return: {e}")
        return None


def process_historic_article(article):
    """
    Process a single historic article:
    1. Run sentiment analysis
    2. Calculate features
    3. Generate label
    """
    try:
        # Extract headline
        headline = article.get("headline", "")
        if not headline:
            return None
        
        # Run sentiment analysis using DeBERTa
        try:
            sentiment_result = predict_sentiment(headline)
            
            # Validate that we got a dictionary back
            if not isinstance(sentiment_result, dict):
                log_historic(f"⚠️ Invalid sentiment result type for article {article.get('article_id')}: {type(sentiment_result)}")
                return None
                
            # Validate required fields
            required_fields = ["sentiment", "sentiment_score", "confidence", 
                             "positive_prob", "negative_prob", "neutral_prob"]
            if not all(field in sentiment_result for field in required_fields):
                log_historic(f"⚠️ Missing fields in sentiment result for article {article.get('article_id')}")
                return None
                
        except Exception as e:
            log_historic(f"⚠️ Sentiment analysis failed for article {article.get('article_id')}: {e}")
            return None
        
        # Calculate return and label
        price_data = calculate_return_and_label(article)
        if price_data is None:
            return None
        
        # Build feature vector matching live data format
        processed = {
            "article_id": article.get("article_id"),
            "symbol": article.get("symbols", ""),
            "headline": headline,
            "sentiment": sentiment_result["sentiment"],
            "sentiment_score": sentiment_result["sentiment_score"],
            "confidence": sentiment_result["confidence"],
            "positive_prob": sentiment_result["positive_prob"],
            "negative_prob": sentiment_result["negative_prob"],
            "neutral_prob": sentiment_result["neutral_prob"],
            "news_source_score": article.get("news_source_score", 0.7),
            "is_regulatory_news": article.get("is_regulatory_news", 0),
            "is_negative_event": article.get("is_negative_event", 0),
            "company_mention_strength": article.get("company_mentioned_count", 0),
            "time_decay_15m": 1.0,  # Historic data treated as fresh
            
            # Market Features (Legacy) - prioritize historic data
            "pre_news_momentum_5m": article.get("pre_news_momentum_5m", 0.0),
            "pre_news_momentum_30m": article.get("pre_news_momentum_30m", 0.0),
            "pre_news_volume_ratio": article.get("pre_news_volume_ratio", 1.0),
            "intraday_volatility": article.get("intraday_volatility", 0.0),
            "pre_news_price": article.get("pre_news_price", 0.0),

            # Pre-Market / Pre-News History (New Concept)
            # 1. Snapshot at signal
            "open_at_signal": article.get("open_at_signal"),
            "high_at_signal": article.get("high_at_signal"),
            "low_at_signal": article.get("low_at_signal"),
            "close_at_signal": article.get("close_at_signal"),
            "volume_at_signal": article.get("volume_at_signal"),

            # 2. Granular Lookback (1m, 2m... 30m)
            # We copy these directly from historic JSON inputs
            # 1 min
            "open_1min": article.get("open_1min"), "high_1min": article.get("high_1min"), "low_1min": article.get("low_1min"), "close_1min": article.get("close_1min"), "volume_1min": article.get("volume_1min"), "volatility_1min_pre_news": article.get("volatility_1min_pre_news"),
            # 2 min
            "open_2min": article.get("open_2min"), "high_2min": article.get("high_2min"), "low_2min": article.get("low_2min"), "close_2min": article.get("close_2min"), "volume_2min": article.get("volume_2min"), "volatility_2min_pre_news": article.get("volatility_2min_pre_news"),
            # 5 min
            "open_5min": article.get("open_5min"), "high_5min": article.get("high_5min"), "low_5min": article.get("low_5min"), "close_5min": article.get("close_5min"), "volume_5min": article.get("volume_5min"), "volatility_5min_pre_news": article.get("volatility_5min_pre_news"),
            # 10 min
            "open_10min": article.get("open_10min"), "high_10min": article.get("high_10min"), "low_10min": article.get("low_10min"), "close_10min": article.get("close_10min"), "volume_10min": article.get("volume_10min"), "volatility_10min_pre_news": article.get("volatility_10min_pre_news"),
            # 15 min - NOTE: Historic JSON likely uses _15min NOT _15min_pre. Check key names. Assuming standard _15min.
            "open_15min": article.get("open_15min_pre") or article.get("open_15min"), 
            "high_15min": article.get("high_15min_pre") or article.get("high_15min"), 
            "low_15min": article.get("low_15min_pre") or article.get("low_15min"), 
            "close_15min": article.get("close_15min_pre") or article.get("close_15min"), 
            "volume_15min": article.get("volume_15min_pre") or article.get("volume_15min"), 
            "volatility_15min_pre_news": article.get("volatility_15min_pre_news"),
            # 20 min
            "open_20min": article.get("open_20min"), "high_20min": article.get("high_20min"), "low_20min": article.get("low_20min"), "close_20min": article.get("close_20min"), "volume_20min": article.get("volume_20min"), "volatility_20min_pre_news": article.get("volatility_20min_pre_news"),
            # 30 min
            "open_30min": article.get("open_30min"), "high_30min": article.get("high_30min"), "low_30min": article.get("low_30min"), "close_30min": article.get("close_30min"), "volume_30min": article.get("volume_30min"), "volatility_30min_pre_news": article.get("volatility_30min_pre_news"),

            "return_15m": price_data["return_15m"],
            "volatility_15m": price_data["volatility_15m"],
            "label": price_data["label"],
            "label_strength": price_data["label_strength"],
            "label_reason": price_data["label_reason"]
        }
        
        return processed
    
    except Exception as e:
        log_historic(f"⚠️ Error processing article {article.get('article_id')}: {e}")
        return None


def train_on_historic_data(processed_articles):
    """Train XGBoost model on processed historic data."""
    log_historic("=" * 60)
    log_historic("Training XGBoost model on historic data")
    log_historic("=" * 60)
    
    # Extract features and labels
    X, y = extract_xy(processed_articles)
    
    if len(X) == 0:
        log_historic("❌ No valid training data extracted")
        return False
    
    log_historic(f"📊 Training samples: {len(X)}")
    log_historic(f"📊 Class distribution:")
    for label_name, label_id in LABEL_MAP.items():
        count = np.sum(y == label_id)
        pct = (count / len(y)) * 100
        log_historic(f"   {label_name}: {count} ({pct:.1f}%)")
    
    # Split data
    X_train, X_val, y_train, y_val = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )
    
    # Configure device
    device_params = {}
    try:
        import torch
        if torch.cuda.is_available():
            log_historic("🚀 Training on GPU")
            device_params = {
                "tree_method": "hist",
                "device": "cuda"
            }
        else:
            log_historic("💻 Training on CPU (GPU available but not used)")
            device_params = {
                "n_jobs": -1
            }
    except ImportError:
        log_historic("💻 Training on CPU (Torch not found)")
        device_params = {
            "n_jobs": -1
        }

    # Calculate sample weights to handle class imbalance (HOLD bias)
    from sklearn.utils.class_weight import compute_sample_weight
    sample_weights = compute_sample_weight(
        class_weight='balanced',
        y=y_train
    )
    
    # Boost BUY/SELL weights slightly more to be aggressive
    buy_idx = np.where(y_train == LABEL_MAP["BUY"])[0]
    sell_idx = np.where(y_train == LABEL_MAP["SELL"])[0]
    sample_weights[buy_idx] *= 1.5
    sample_weights[sell_idx] *= 1.5

    # Train model
    log_historic("Training XGBoost classifier...")
    model = XGBClassifier(
        n_estimators=200,
        max_depth=5,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        objective="multi:softprob",
        num_class=3,
        eval_metric="mlogloss",
        random_state=42,
        **device_params
    )
    
    model.fit(X_train, y_train, sample_weight=sample_weights)
    
    # Evaluate
    preds = model.predict(X_val)
    accuracy = accuracy_score(y_val, preds)
    macro_f1 = f1_score(y_val, preds, average="macro")
    cm = confusion_matrix(y_val, preds)
    recalls = recall_score(y_val, preds, average=None)
    
    metrics = {
        "accuracy": round(accuracy, 4),
        "macro_f1": round(macro_f1, 4),
        "buy_recall": round(recalls[LABEL_MAP["BUY"]], 4),
        "sell_recall": round(recalls[LABEL_MAP["SELL"]], 4),
        "confusion_matrix": cm.tolist(),
    }
    
    # Save model
    os.makedirs(MODELS_DIR, exist_ok=True)
    
    joblib.dump(model, HISTORIC_MODEL_PATH)
    joblib.dump(model, LATEST_MODEL_PATH)  # Also save as latest
    
    # Save metadata
    metadata = {
        "model_version": "historic_v1",
        "trained_at": datetime.utcnow().isoformat(),
        "training_rows": len(processed_articles),
        "data_source": "historic_dataset",
        "class_distribution": {
            k: round(float(np.mean(y == v) * 100), 2)
            for k, v in LABEL_MAP.items()
        },
        "validation_metrics": metrics,
        "deployed": True,
    }
    
    save_json(HISTORIC_META_PATH, metadata)
    save_json(META_PATH, metadata)  # Also save as latest
    
    # Create flag file
    with open(HISTORIC_FLAG_FILE, 'w') as f:
        f.write(f"Historic model trained at: {datetime.now().isoformat()}\n")
    
    log_historic(f"✅ Model saved: {HISTORIC_MODEL_PATH}")
    log_historic(f"📊 Accuracy: {metrics['accuracy']} | Macro-F1: {metrics['macro_f1']}")
    log_historic(f"📊 BUY Recall: {metrics['buy_recall']} | SELL Recall: {metrics['sell_recall']}")
    log_historic("=" * 60)
    
    return True


def main(force_retrain=False):
    """Main function to run historic training."""
    print("\n" + "=" * 70)
    print("HISTORIC DATASET TRAINING")
    print("=" * 70)
    
    # Check if already trained
    if os.path.exists(HISTORIC_FLAG_FILE) and not force_retrain:
        log_historic("✅ Historic model already trained (flag file exists)")
        log_historic(f"   To re-train, delete {HISTORIC_FLAG_FILE} or use --force")
        
        if os.path.exists(HISTORIC_META_PATH):
            with open(HISTORIC_META_PATH, 'r') as f:
                meta = json.load(f)
            log_historic(f"   Existing model metrics:")
            log_historic(f"   Accuracy: {meta['validation_metrics']['accuracy']}")
            log_historic(f"   Macro-F1: {meta['validation_metrics']['macro_f1']}")
        
        return
    
    # Load historic data
    articles = load_historic_data()
    if not articles:
        log_historic("❌ No historic data found")
        return
    
    # Process articles
    log_historic(f"Processing {len(articles)} historic articles...")
    processed = []
    
    for i, article in enumerate(articles):
        if i % 100 == 0:
            log_historic(f"Progress: {i}/{len(articles)}")
        
        result = process_historic_article(article)
        if result:
            processed.append(result)
    
    log_historic(f"✅ Successfully processed {len(processed)}/{len(articles)} articles")
    
    if len(processed) < 100:
        log_historic("❌ Not enough valid data to train (need at least 100 samples)")
        return
    
    # Train model
    success = train_on_historic_data(processed)
    
    if success:
        print("\n" + "=" * 70)
        print("✅ HISTORIC TRAINING COMPLETE!")
        print("=" * 70)
        print(f"Model saved to: {HISTORIC_MODEL_PATH}")
        print(f"Processed articles: {len(processed)}")
        print("=" * 70)


if __name__ == "__main__":
    force = "--force" in sys.argv
    main(force_retrain=force)
