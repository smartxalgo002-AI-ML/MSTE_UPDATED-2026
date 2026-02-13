"""
Step 4: DeBERTa Sentiment Analysis
Reads from longformer output (Step 3), performs sentiment analysis using DeBERTa,
outputs to deberta_fin/all_news_sentiment.json and deberta_fin/news_sentiment_new.json
"""
import os
import json
import torch
from datetime import datetime
from transformers import AutoTokenizer, AutoModelForSequenceClassification

from config import (
    LOG_FILE,
    CONDENSED_NEW_PATH,
    DEBERTA_OUTPUT_DIR,
    SENTIMENT_ALL_PATH,
    SENTIMENT_NEW_PATH,
)


def log(msg: str):
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"{datetime.now()} | [deberta_step4] {msg}\n")
    print(f"[deberta_step4] {msg}")


def load_json(path: str) -> list:
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            log(f"JSON load error ({path}): {e}")
    return []


# Custom JSON encoder to round floats only at output stage
class RoundingJSONEncoder(json.JSONEncoder):
    def encode(self, obj):
        if isinstance(obj, float):
            return format(obj, '.4f')
        return super().encode(obj)
    
    def iterencode(self, obj, _one_shot=False):
        """Recursively round floats in nested structures"""
        if isinstance(obj, dict):
            obj = {k: round(v, 4) if isinstance(v, float) else v for k, v in obj.items()}
        elif isinstance(obj, list):
            obj = [round(item, 4) if isinstance(item, float) else item for item in obj]
        return super().iterencode(obj, _one_shot)


def save_json(path: str, data: list):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4, cls=RoundingJSONEncoder)


# Model config
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
MODEL_NAME = "mrm8488/deberta-v3-ft-financial-news-sentiment-analysis"
LABELS = ["negative", "neutral", "positive"]

# Lazy load model
_tokenizer = None
_model = None


def get_model():
    global _tokenizer, _model
    if _tokenizer is None:
        log(f"🚀 Loading DeBERTa model on {DEVICE}...")
        _tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
        _model = AutoModelForSequenceClassification.from_pretrained(MODEL_NAME)
        _model = _model.to(DEVICE)
        _model.eval()
        torch.set_grad_enabled(False)
        log("✔ DeBERTa model loaded")
    return _tokenizer, _model


def predict_sentiment(text: str) -> dict:
    """Predict sentiment for a piece of text."""
    tokenizer, model = get_model()
    
    inputs = tokenizer(
        text,
        return_tensors="pt",
        truncation=True,
        max_length=512
    ).to(DEVICE)
    
    with torch.no_grad():
        outputs = model(**inputs)
    
    probs = torch.softmax(outputs.logits, dim=1)[0]
    label_id = torch.argmax(probs).item()
    
    # Extract probabilities for each class (full precision, no rounding)
    # LABELS = ["negative", "neutral", "positive"]
    negative_prob = probs[0].item()
    neutral_prob = probs[1].item()
    positive_prob = probs[2].item()
    
    # Calculate sentiment score: ranges from -1 (most negative) to +1 (most positive)
    sentiment_score = positive_prob - negative_prob
    
    return {
        "sentiment": LABELS[label_id],
        "sentiment_score": sentiment_score,
        "positive_prob": positive_prob,
        "negative_prob": negative_prob,
        "neutral_prob": neutral_prob,
        "confidence": probs[label_id].item()
    }


def process_article(article: dict) -> dict:
    """Process a single article and return with sentiment."""
    text = article.get("condensed_text", "").strip()
    
    if not text:
        return None
    
    sentiment = predict_sentiment(text)
    
    return {
        "article_id": article.get("article_id"),
        "headline": article.get("headline"),
        "condensed_text": article.get("condensed_text", ""),
        "sentiment": sentiment["sentiment"],
        "sentiment_score": sentiment["sentiment_score"],
        "positive_prob": sentiment["positive_prob"],
        "negative_prob": sentiment["negative_prob"],
        "neutral_prob": sentiment["neutral_prob"],
        "confidence": sentiment["confidence"],
        "source": article.get("source"),
        "published_time": article.get("published_time"),
        "url": article.get("url"),
        "CompanyName": article.get("CompanyName", ""),
        "Symbol": article.get("Symbol", ""),
        "Sector": article.get("Sector", ""),
        "Index": article.get("Index", ""),
        "analyzed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }


def run_deberta(input_path: str = None) -> list:
    """
    Main entry point for Step 4.
    Reads from condensed_news_new.json (or custom input_path), performs sentiment analysis,
    saves to all_news_sentiment.json and news_sentiment_new.json
    Returns the list of analyzed articles from this run.
    """
    log("=" * 60)
    log("Step 4: DeBERTa Sentiment Analysis Started")
    log("=" * 60)
    log(f"🚀 Device: {DEVICE}")
    
    os.makedirs(DEBERTA_OUTPUT_DIR, exist_ok=True)
    
    # Load input (from Step 3)
    input_file = input_path or CONDENSED_NEW_PATH
    articles = load_json(input_file)
    
    if not articles:
        log(f"🟡 No articles to analyze from {input_file}")
        save_json(SENTIMENT_NEW_PATH, [])
        return []
    
    log(f"📥 Loaded {len(articles)} articles from {input_file}")
    
    # Process each article
    analyzed_articles = []
    for i, article in enumerate(articles):
        result = process_article(article)
        if result:
            analyzed_articles.append(result)
        if (i + 1) % 10 == 0:
            log(f"⏳ Analyzed {i + 1}/{len(articles)} articles...")
    
    log(f"✔ Analyzed {len(analyzed_articles)} articles")
    
    # Load existing all_news_sentiment.json for deduplication using (article_id, symbol) key
    existing = load_json(SENTIMENT_ALL_PATH)
    existing_keys = {(a.get("article_id"), a.get("Symbol")) for a in existing}
    
    # Find truly new articles using composite key
    new_analyzed = [a for a in analyzed_articles if (a.get("article_id"), a.get("Symbol")) not in existing_keys]
    
    # Append to all_news_sentiment.json
    if new_analyzed:
        all_data = existing + new_analyzed
        save_json(SENTIMENT_ALL_PATH, all_data)
        log(f"💾 Appended {len(new_analyzed)} to {SENTIMENT_ALL_PATH} (total: {len(all_data)})")
    else:
        log(f"🟡 No new articles to append to {SENTIMENT_ALL_PATH}")
    
    # Save news_sentiment_new.json (current run only)
    save_json(SENTIMENT_NEW_PATH, new_analyzed)
    log(f"🆕 Wrote {len(new_analyzed)} analyzed articles to {SENTIMENT_NEW_PATH}")
    
    # Sentiment distribution stats
    if new_analyzed:
        pos = sum(1 for a in new_analyzed if a["sentiment"] == "positive")
        neg = sum(1 for a in new_analyzed if a["sentiment"] == "negative")
        neu = sum(1 for a in new_analyzed if a["sentiment"] == "neutral")
        log(f"📊 Sentiment distribution: +{pos} / ={neu} / -{neg}")
    
    log("=" * 60)
    log(f"Step 4 Complete: {len(new_analyzed)} articles analyzed")
    log("=" * 60)
    
    return new_analyzed


if __name__ == "__main__":
    articles = run_deberta()
    print(f"\n✅ DeBERTa completed: {len(articles)} articles analyzed")
