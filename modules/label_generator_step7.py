"""
Step 7: Label Generator
Converts OHLCV reaction into BUY / SELL / HOLD labels.
Rule-based, explainable, production-safe.
"""

import json
import os
from datetime import datetime

from config import (
    LOG_FILE,
    OHLCV_MERGER_NEW_PATH,
    LABELS_OUTPUT_DIR,
    LABELS_NEW_PATH,
    LABELS_ALL_PATH,
)

# ==================================================
# CONFIGURATION
# ==================================================

# Strict enough to cover costs, but sensitive enough to catch moves
BUY_THRESHOLD = 0.15    # +0.15% (covers brokerage + profit)
SELL_THRESHOLD = -0.15  # -0.15%

# ==================================================
# LOGGING
# ==================================================

def log(msg: str):
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"{datetime.now()} | [label_generator_step7] {msg}\n")
    print(f"[label_generator_step7] {msg}")

# ==================================================
# HELPERS
# ==================================================

def load_json(path: str) -> list:
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def save_json(path: str, data: list):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


def append_to_all(all_path: str, new_rows: list) -> list:
    existing = load_json(all_path)
    existing_keys = {
        (r.get("article_id"), r.get("symbol")) for r in existing
    }

    fresh = [
        r for r in new_rows
        if (r.get("article_id"), r.get("symbol")) not in existing_keys
    ]

    if fresh:
        all_data = existing + fresh
        save_json(all_path, all_data)
        log(f"💾 Appended {len(fresh)} new labels to {all_path}")
    else:
        log("🟡 No new labels to append")

    return fresh

# ==================================================
# LABEL LOGIC
# ==================================================

def generate_label(row):
    ret = row.get("return_15m")

    if ret is None:
        return "HOLD", 0.0, "missing_return"

    if ret >= BUY_THRESHOLD:
        return "BUY", abs(ret), "price_up_15m"

    if ret <= SELL_THRESHOLD:
        return "SELL", abs(ret), "price_down_15m"

    return "HOLD", abs(ret), "flat_move"

# ==================================================
# MAIN STEP-7
# ==================================================

def run_label_generator(input_path: str = None) -> list:
    log("=" * 60)
    log("Step 7: Label Generation Started")
    log("=" * 60)

    input_file = input_path or OHLCV_MERGER_NEW_PATH

    if not os.path.exists(input_file):
        log(f"⚠️ OHLCV merge output not found: {input_file}")
        return []

    rows = load_json(input_file)
    if not rows:
        log("⚠️ No rows to label")
        return []

    labeled_rows = []

    for row in rows:
        label, strength, reason = generate_label(row)

        labeled_rows.append({
            **row,
            "label": label,
            "label_strength": round(strength, 4),
            "label_reason": reason,
        })

    # Save new labels
    os.makedirs(LABELS_OUTPUT_DIR, exist_ok=True)
    save_json(LABELS_NEW_PATH, labeled_rows)
    log(f"💾 Saved labeled_news_new.json ({len(labeled_rows)} rows)")

    # Append to cumulative labels
    truly_new = append_to_all(LABELS_ALL_PATH, labeled_rows)
    log(f"➕ Appended {len(truly_new)} to all_labeled_news.json")

    log("=" * 60)
    log(f"Step 7 Complete: {len(labeled_rows)} labels generated")
    log("=" * 60)

    return labeled_rows


if __name__ == "__main__":
    labels = run_label_generator()
    print(f"\n✅ Label Generator completed: {len(labels)} labels created")
