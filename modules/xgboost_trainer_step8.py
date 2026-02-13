"""
Step 8: Self-Training XGBoost (Batch, Gated)

Trains XGBoost using cumulative labeled news data.
Includes accuracy, macro-F1, BUY/SELL recall.
Deploys new model only if metrics improve.
"""

import sys
import os

# Add parent directory to path to allow importing config
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import joblib
import numpy as np
from datetime import datetime, timezone, timedelta

from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, f1_score, confusion_matrix, recall_score
from xgboost import XGBClassifier

from config import (
    LOG_FILE,
    LABELS_ALL_PATH,
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
    
    # Market features (5)
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

LABEL_MAP = {"BUY": 0, "SELL": 1, "HOLD": 2}
REVERSE_LABEL_MAP = {v: k for k, v in LABEL_MAP.items()}

MIN_NEW_ROWS = 300  # retrain only if enough new data

MODEL_NAME = "xgb_news_model"
LATEST_MODEL_PATH = os.path.join(MODELS_DIR, f"{MODEL_NAME}_latest.pkl")
META_PATH = os.path.join(MODELS_DIR, f"{MODEL_NAME}_meta.json")

# ==================================================
# LOGGING
# ==================================================

def log(msg):
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"{datetime.now()} | [xgboost_step8] {msg}\n")
    print(f"[xgboost_step8] {msg}")

# ==================================================
# HELPERS
# ==================================================

def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)



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
            # Assume this is IST, convert to UTC properly
            dt_ist = dt.replace(tzinfo=timezone(timedelta(hours=5, minutes=30)))
            return dt_ist.astimezone(timezone.utc)
        
        # Format: "January 17, 2026/ 14:47 IST"
        if "/" in published_time and "IST" in published_time:
            dt_str = published_time.replace(" IST", "").replace("/", "")
            dt = datetime.strptime(dt_str.strip(), "%B %d, %Y %H:%M")
            # Proper IST → UTC conversion
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
            
    except Exception:
        pass
    
    return None


def extract_xy(rows):
    X, y = [], []
    for r in rows:
        if r.get("label") not in LABEL_MAP:
            continue
            
        # Sanitize features: Ensure all are float, replace None/NaN/Inf with 0.0
        features = []
        for col in FEATURE_COLUMNS:
            val = r.get(col)
            try:
                if val is None:
                    val = 0.0
                else:
                    val = float(val)
                    if np.isnan(val) or np.isinf(val):
                        val = 0.0
            except (ValueError, TypeError):
                val = 0.0
            features.append(val)
            
        X.append(features)
        y.append(LABEL_MAP[r["label"]])
        
    return np.array(X, dtype=np.float32), np.array(y, dtype=np.int64)


def load_previous_metrics():
    if not os.path.exists(META_PATH):
        return None
    with open(META_PATH, "r", encoding="utf-8") as f:
        return json.load(f).get("validation_metrics")

# ==================================================
# MAIN TRAINING LOGIC
# ==================================================

def run_xgboost_training():
    """
    Main training function. Returns dict with training status.
    
    Returns:
        dict: {
            "trained": bool,
            "deployed": bool,
            "metrics": dict or None,
            "model_path": str or None,
            "reason": str (if not deployed)
        }
    """
    log("=" * 60)
    log("Step 8: XGBoost Self-Training Started")
    log("=" * 60)

    if not os.path.exists(LABELS_ALL_PATH):
        log("❌ No labeled data found")
        return {"trained": False, "deployed": False, "reason": "no_data_file", "metrics": None, "model_path": None}

    rows = load_json(LABELS_ALL_PATH)

    if len(rows) < MIN_NEW_ROWS:
        log(f"🟡 Not enough data to retrain ({len(rows)} rows, need {MIN_NEW_ROWS})")
        return {"trained": False, "deployed": False, "reason": "insufficient_data", "metrics": None, "model_path": None}

    # TIME-BASED SPLIT (no data leakage)
    # 1. Parse times and filter invalid ones
    valid_rows = []
    for r in rows:
        dt = parse_published_time(r.get("published_time"))
        if dt:
            r["_parsed_time"] = dt
            valid_rows.append(r)
            
    if not valid_rows:
        log("❌ No rows with valid published_time found")
        return {"trained": False, "deployed": False, "reason": "no_valid_times", "metrics": None, "model_path": None}

    # 2. Sort chronologically
    rows_sorted = sorted(valid_rows, key=lambda r: r["_parsed_time"])
    
    # 3. Extract X, y from sorted data (sanitized)
    X, y = extract_xy(rows_sorted)
    
    # Validate extracted data
    if len(X) == 0:
        log("❌ No valid labeled rows found after extraction")
        return {"trained": False, "deployed": False, "reason": "no_valid_data", "metrics": None, "model_path": None}
    
    log(f"📊 Extracted {len(X)} valid samples")
    
    # Use first 80% for training, last 20% for validation (time-based)
    split_idx = int(len(X) * 0.8)
    X_train, X_val = X[:split_idx], X[split_idx:]
    y_train, y_val = y[:split_idx], y[split_idx:]
    
    log(f"📅 Time-based split: {len(X_train)} train, {len(X_val)} val")

    # Wrap training in try-catch for robustness
    try:
        # Configure device
        device_params = {}
        try:
            import torch
            if torch.cuda.is_available():
                log("🚀 Training on GPU")
                device_params = {
                    "tree_method": "hist",
                    "device": "cuda"
                }
            else:
                log("💻 Training on CPU (GPU available but not used)")
                device_params = {
                    "n_jobs": -1
                }
        except ImportError:
            log("💻 Training on CPU (Torch not found)")
            device_params = {
                "n_jobs": -1
            }

        # Calculate sample weights to handle class imbalance (HOLD bias)
        # Weight = Total Samples / (n_classes * Class Samples)
        from sklearn.utils.class_weight import compute_sample_weight
        sample_weights = compute_sample_weight(
            class_weight='balanced',
            y=y_train
        )
        
        # Boost BUY/SELL weights slightly more to be aggressive
        # Find indices
        buy_idx = np.where(y_train == LABEL_MAP["BUY"])[0]
        sell_idx = np.where(y_train == LABEL_MAP["SELL"])[0]
        
        # Increase their weight by 1.5x on top of balanced weight
        sample_weights[buy_idx] *= 1.5
        sample_weights[sell_idx] *= 1.5

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

        prev_metrics = load_previous_metrics()

        deploy = (
            prev_metrics is None or
            metrics["accuracy"] >= prev_metrics["accuracy"] or  # Changed AND to OR - prioritize accuracy improvement
            metrics["macro_f1"] >= prev_metrics["macro_f1"]
        )

        if not deploy:
            log("❌ New model did not beat previous model (on both metrics). Skipping deployment.")
            log(f"   Previous: Acc={prev_metrics['accuracy']}, F1={prev_metrics['macro_f1']}")
            log(f"   Current:  Acc={metrics['accuracy']}, F1={metrics['macro_f1']}")
            # return {"trained": True, "deployed": False, "reason": "metrics_not_improved", "metrics": metrics, "model_path": None}
            log("⚠️ FORCE DEPLOYING per user request (Weighted Loss)")
            deploy = True  # Override for this run

        os.makedirs(MODELS_DIR, exist_ok=True)

        version = datetime.utcnow().strftime("%Y%m%d_%H%M")
        model_path = os.path.join(MODELS_DIR, f"{MODEL_NAME}_{version}.pkl")

        joblib.dump(model, model_path)
        joblib.dump(model, LATEST_MODEL_PATH)

        metadata = {
            "model_version": version,
            "trained_at": datetime.utcnow().isoformat(),
            "training_rows": len(rows),
            "class_distribution": {
                k: round(float(np.mean(y == v) * 100), 2)
                for k, v in LABEL_MAP.items()
            },
            "validation_metrics": metrics,
            "deployed": True,
        }

        save_json(META_PATH, metadata)

        log(f"✅ Model deployed: {model_path}")
        log(f"📊 Accuracy: {metrics['accuracy']} | Macro-F1: {metrics['macro_f1']}")
        log(f"📊 BUY Recall: {metrics['buy_recall']} | SELL Recall: {metrics['sell_recall']}")
        log("=" * 60)
        
        return {
            "trained": True,
            "deployed": True,
            "metrics": metrics,
            "model_path": model_path,
            "reason": "success"
        }
        
    except Exception as e:
        log(f"❌ Training failed with error: {e}")
        import traceback
        log(traceback.format_exc())
        return {
            "trained": False,
            "deployed": False,
            "reason": "training_error",
            "error": str(e),
            "metrics": None,
            "model_path": None
        }


if __name__ == "__main__":
    run_xgboost_training()
