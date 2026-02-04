
"""
Live Accuracy Tracker Script
===========================
Based on the concept defined in live_accuracy_concept.md.

This script calculates the "Live Accuracy" of the model by comparing:
1. Predictions from output/signals/all_signals.json
2. Actual outcomes from output/labels/labeled_news_new.json

Features:
- Matches predictions to actual labels by article_id
- Calculates Overall Accuracy
- Calculates Class-wise Precision (BUY/SELL/HOLD)
- Shows specific successes and failures
- Handles UTC/IST timestamp parsing
"""

import json
import os
from datetime import datetime
from collections import defaultdict

# --- Configuration ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SIGNALS_PATH = os.path.join(BASE_DIR, "output", "signals", "all_signals.json")
LABELS_PATH = os.path.join(BASE_DIR, "output", "labels", "labeled_news_new.json")

def load_json(path):
    if not os.path.exists(path):
        print(f"⚠️ File not found: {path}")
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"❌ Error loading {path}: {e}")
        return []

def calculate_live_accuracy():
    print("="*60)
    print(" 📊 LIVE MODEL PERFORMANCE TRACKER")
    print("="*60)

    # 1. Load Data
    signals = load_json(SIGNALS_PATH)
    labels = load_json(LABELS_PATH)
    
    if not signals or not labels:
        print("⚠️ Waiting for data... (Pipeline needs to run longer)")
        return

    print(f"🔹 Loaded {len(signals)} predictions")
    print(f"🔹 Loaded {len(labels)} actual labels")
    print("-" * 60)

    # 2. Index Actual Labels by Article ID
    label_map = {item["article_id"]: item for item in labels}

    # 3. Compare Predictions vs Actuals
    correct = 0
    total_evaluated = 0
    
    class_stats = {
        "BUY": {"correct": 0, "total": 0},
        "SELL": {"correct": 0, "total": 0},
        "HOLD": {"correct": 0, "total": 0}
    }

    recent_results = []

    for pred in signals:
        article_id = pred.get("article_id")
        
        # Skip if we don't have an actual label yet (price hasn't moved enough time)
        if article_id not in label_map:
            continue
            
        actual = label_map[article_id]
        
        pred_signal = pred.get("predicted_signal")
        actual_signal = actual.get("label")
        
        # Count totals
        total_evaluated += 1
        class_stats[pred_signal]["total"] += 1
        
        # Check correctness
        is_correct = (pred_signal == actual_signal)
        if is_correct:
            correct += 1
            class_stats[pred_signal]["correct"] += 1
            status_icon = "✅"
        else:
            status_icon = "❌"
            
        # Store for display
        recent_results.append({
            "symbol": pred.get("symbol"),
            "pred": pred_signal,
            "actual": actual_signal,
            "return": actual.get("return_15m", 0.0),
            "status": status_icon
        })

    # 4. Display Results
    if total_evaluated == 0:
        print("⚠️ No matched predictions yet. Wait 15 mins for labels to generate.")
        return

    accuracy = (correct / total_evaluated) * 100
    
    print(f"\n📈 OVERALL ACCURACY: {accuracy:.2f}% ({correct}/{total_evaluated})")
    print("\n🔹 Class-wise Precision:")
    
    for signal_type in ["BUY", "SELL", "HOLD"]:
        stats = class_stats[signal_type]
        if stats["total"] > 0:
            precision = (stats["correct"] / stats["total"]) * 100
            print(f"   {signal_type}: {precision:.1f}% ({stats['correct']}/{stats['total']})")
        else:
            print(f"   {signal_type}: N/A (0 predictions)")

    print("\n🔹 Recent Matches:")
    for res in recent_results[-10:]: # Show last 10
        print(f"   {res['status']} {res['symbol']}: Pred {res['pred']} | Actual {res['actual']} (Return: {res['return']*100:.2f}%)")

    print("\n" + "="*60)

import time

if __name__ == "__main__":
    while True:
        os.system('cls' if os.name == 'nt' else 'clear')  # Clear console
        print(f"🔄 Last Updated: {datetime.now().strftime('%H:%M:%S')}")
        calculate_live_accuracy()
        print("\n⏳ Next update in 60 seconds... (Ctrl+C to stop)")
        time.sleep(60)
