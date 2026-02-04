"""
Step 8: Self-Training XGBoost (Batch, Gated)

Trains XGBoost using cumulative labeled news data.
Includes accuracy, macro-F1, BUY/SELL recall.
Deploys new model only if metrics improve.
"""

import json
import os
import joblib
import numpy as np
from datetime import datetime

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


def extract_xy(rows):
    X, y = [], []
    for r in rows:
        if r.get("label") not in LABEL_MAP:
            continue
        X.append([r.get(col, 0.0) for col in FEATURE_COLUMNS])
        y.append(LABEL_MAP[r["label"]])
    return np.array(X), np.array(y)


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

    X, y = extract_xy(rows)
    
    # Validate extracted data
    if len(X) == 0:
        log("❌ No valid labeled rows found after extraction")
        return {"trained": False, "deployed": False, "reason": "no_valid_data", "metrics": None, "model_path": None}
    
    log(f"📊 Extracted {len(X)} valid samples")
    
    # Wrap training in try-catch for robustness
    try:
        X_train, X_val, y_train, y_val = train_test_split(
            X, y, test_size=0.2, random_state=42, stratify=y
        )

        # Configure device
        device_params = {}
        import torch
        if torch.cuda.is_available():
            log("🚀 Training on GPU")
            device_params = {
                "tree_method": "hist",
                "device": "cuda"
            }
        else:
            log("💻 Training on CPU")
            device_params = {
                "n_jobs": -1
            }

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

        model.fit(X_train, y_train)

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
            (metrics["accuracy"] >= prev_metrics["accuracy"] and
             metrics["macro_f1"] >= prev_metrics["macro_f1"])
        )

        if not deploy:
            log("❌ New model did not beat previous model. Skipping deployment.")
            log(f"   Previous: Acc={prev_metrics['accuracy']}, F1={prev_metrics['macro_f1']}")
            log(f"   Current:  Acc={metrics['accuracy']}, F1={metrics['macro_f1']}")
            return {"trained": True, "deployed": False, "reason": "metrics_not_improved", "metrics": metrics, "model_path": None}

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
