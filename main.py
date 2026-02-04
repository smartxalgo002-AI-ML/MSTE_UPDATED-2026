"""
News Sentiment Pipeline - Main Orchestrator
Runs all 9 steps in sequence:
1. News Fetcher (all sources)
2. Company Tagging
3. Longformer Condensation
4. DeBERTa Sentiment Analysis
5. Feature Builder
6. OHLCV Merge
7. Label Generator (BUY/SELL/HOLD)
8. XGBoost Self-Training (optional)
9. Signal Predictor (ML-based BUY/SELL/HOLD predictions)

Note: OHLCV fetcher runs independently from "Data Fetch ohlcv" folder
"""
import sys
import time
from datetime import datetime

from config import (
    OUTPUT_DIR,
    MAPPING_DIR,
    NEWS_FETCHER_OUTPUT_DIR,
    COMPANY_TAGGER_OUTPUT_DIR,
    LONGFORMER_OUTPUT_DIR,
    DEBERTA_OUTPUT_DIR,
    FEATURES_OUTPUT_DIR,
    OHLCV_MERGER_OUTPUT_DIR,
    LABELS_OUTPUT_DIR,
    MODELS_DIR,
    SIGNALS_OUTPUT_DIR,
    MAX_ARTICLES,
)

# Import step modules
from modules.news_fetcher_step1 import run_news_fetcher
from modules.company_tagging_step2 import run_company_tagging
from modules.longformer_step3 import run_longformer
from modules.deberta_step4 import run_deberta
from modules.feature_builder_step5 import run_feature_builder
from modules.ohlcv_merge_step6 import run_ohlcv_merge
from modules.label_generator_step7 import run_label_generator
from modules.xgboost_trainer_step8 import run_xgboost_training
from modules.signal_predictor_step9 import run_signal_predictor

import os


def ensure_directories():
    """Create all required output directories."""
    dirs = [
        OUTPUT_DIR,
        MAPPING_DIR,
        NEWS_FETCHER_OUTPUT_DIR,
        COMPANY_TAGGER_OUTPUT_DIR,
        LONGFORMER_OUTPUT_DIR,
        DEBERTA_OUTPUT_DIR,
        FEATURES_OUTPUT_DIR,
        OHLCV_MERGER_OUTPUT_DIR,
        LABELS_OUTPUT_DIR,
        MODELS_DIR,
        SIGNALS_OUTPUT_DIR,
    ]
    for d in dirs:
        os.makedirs(d, exist_ok=True)


def run_pipeline(max_articles: int = MAX_ARTICLES):
    """Run the complete 8-step pipeline."""
    print("\n" + "=" * 70)
    print(f"📰 NEWS SENTIMENT PIPELINE STARTED - {datetime.now()}")
    print("=" * 70)
    
    ensure_directories()
    
    # Step 1: News Fetcher
    print("\n" + "-" * 50)
    print("🔹 STEP 1: Fetching News")
    print("-" * 50)
    fetched = run_news_fetcher(max_articles=max_articles)
    print(f"   → {len(fetched)} new articles fetched")
    
    if not fetched:
        print("\n⚠️ No new articles to process. Pipeline complete.")
        return
    
    # Step 2: Company Tagging
    print("\n" + "-" * 50)
    print("🔹 STEP 2: Company Tagging")
    print("-" * 50)
    tagged = run_company_tagging()
    print(f"   → {len(tagged)} articles tagged")
    
    if not tagged:
        print("\n⚠️ No articles to process after tagging. Pipeline complete.")
        return
    
    # Step 3: Longformer Condensation
    print("\n" + "-" * 50)
    print("🔹 STEP 3: Longformer Condensation")
    print("-" * 50)
    condensed = run_longformer()
    print(f"   → {len(condensed)} articles condensed")
    
    if not condensed:
        print("\n⚠️ No articles to process after condensation. Pipeline complete.")
        return
    
    # Step 4: DeBERTa Sentiment Analysis
    print("\n" + "-" * 50)
    print("🔹 STEP 4: DeBERTa Sentiment Analysis")
    print("-" * 50)
    analyzed = run_deberta()
    print(f"   → {len(analyzed)} articles analyzed")
    
    # Step 5: Feature Builder
    print("\n" + "-" * 50)
    print("🔹 STEP 5: Feature Builder")
    print("-" * 50)
    features = run_feature_builder()
    print(f"   → {len(features)} feature vectors built")
    
    # Step 6: OHLCV Merge
    print("\n" + "-" * 50)
    print("🔹 STEP 6: OHLCV Merge")
    print("-" * 50)
    enriched = run_ohlcv_merge()
    print(f"   → {len(enriched)} rows enriched with OHLCV data")
    
    # Step 7: Label Generator
    print("\n" + "-" * 50)
    print("🔹 STEP 7: Label Generator")
    print("-" * 50)
    labels = run_label_generator()
    print(f"   → {len(labels)} labels generated")
    
    # Step 8: XGBoost Self-Training (optional - runs if enough data)
    print("\n" + "-" * 50)
    print("🔹 STEP 8: XGBoost Self-Training (Optional)")
    print("-" * 50)
    train_result = run_xgboost_training()
    if train_result.get("deployed"):
        metrics = train_result.get("metrics", {})
        print(f"   → Model deployed! Acc: {metrics.get('accuracy', 'N/A')}, F1: {metrics.get('macro_f1', 'N/A')}")
    elif train_result.get("trained"):
        print(f"   → Trained but not deployed ({train_result.get('reason', 'unknown')})")
    else:
        print(f"   → Training skipped ({train_result.get('reason', 'unknown')})")
    
    # Step 9: Signal Predictor (ML-based predictions)
    print("\n" + "-" * 50)
    print("🔹 STEP 9: Signal Predictor (ML-based)")
    print("-" * 50)
    signals = run_signal_predictor()
    print(f"   → {len(signals)} trading signals generated")
    
    # Summary
    print("\n" + "=" * 70)
    print(f"✅ PIPELINE COMPLETE - {datetime.now()}")
    print("=" * 70)
    print(f"   Fetched:     {len(fetched)} articles")
    print(f"   Tagged:      {len(tagged)} articles")
    print(f"   Condensed:   {len(condensed)} articles")
    print(f"   Analyzed:    {len(analyzed)} articles")
    print(f"   Features:    {len(features)} feature vectors")
    print(f"   Enriched:    {len(enriched)} rows with OHLCV")
    print(f"   Labels:      {len(labels)} labels generated")
    print(f"   Signals:     {len(signals)} ML predictions")
    print("=" * 70)
    
    if analyzed:
        pos = sum(1 for a in analyzed if a["sentiment"] == "positive")
        neg = sum(1 for a in analyzed if a["sentiment"] == "negative")
        neu = sum(1 for a in analyzed if a["sentiment"] == "neutral")
        print(f"   📊 Sentiment: Positive={pos}, Neutral={neu}, Negative={neg}")
    
    if labels:
        buy_count = sum(1 for l in labels if l["label"] == "BUY")
        sell_count = sum(1 for l in labels if l["label"] == "SELL")
        hold_count = sum(1 for l in labels if l["label"] == "HOLD")
        print(f"   📊 Labels: BUY={buy_count}, HOLD={hold_count}, SELL={sell_count}")
    
    if signals:
        sig_buy = sum(1 for s in signals if s["predicted_signal"] == "BUY")
        sig_sell = sum(1 for s in signals if s["predicted_signal"] == "SELL")
        sig_hold = sum(1 for s in signals if s["predicted_signal"] == "HOLD")
        print(f"   🎯 Signals: BUY={sig_buy}, HOLD={sig_hold}, SELL={sig_sell}")
    
    print("=" * 70)


def main_loop(interval_minutes: int = 5):
    """Run pipeline in a continuous loop."""
    print("🔁 Starting News Sentiment Pipeline (loop mode)")
    print(f"   Interval: {interval_minutes} minutes")
    print("   Press CTRL+C to stop.\n")
    
    try:
        while True:
            run_pipeline()
            print(f"\n⏳ Sleeping for {interval_minutes} minutes...\n")
            time.sleep(interval_minutes * 60)
    except KeyboardInterrupt:
        print("\n🛑 Pipeline stopped by user.")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--once":
        run_pipeline()
    else:
        main_loop(interval_minutes=5)
