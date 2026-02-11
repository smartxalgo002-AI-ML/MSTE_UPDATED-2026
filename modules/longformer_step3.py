"""
Step 3: Longformer Text Condensation
Reads from company_tagger output (Step 2), condenses article text using Longformer,
outputs to longformer/all_condensed_news.json and longformer/condensed_news_new.json
"""
import os
import json
import torch
import nltk
from datetime import datetime
from transformers import AutoTokenizer, LongformerModel
from nltk.tokenize import sent_tokenize

from config import (
    LOG_FILE,
    TAGGED_NEW_PATH,
    LONGFORMER_OUTPUT_DIR,
    CONDENSED_ALL_PATH,
    CONDENSED_NEW_PATH,
)


def log(msg: str):
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"{datetime.now()} | [longformer_step3] {msg}\n")
    print(f"[longformer_step3] {msg}")


def load_json(path: str) -> list:
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            log(f"JSON load error ({path}): {e}")
    return []


def save_json(path: str, data: list):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


# Setup NLTK
nltk.download("punkt", quiet=True)
nltk.download("punkt_tab", quiet=True)

# Model config
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
MODEL_NAME = "allenai/longformer-base-4096"
MAX_TOKENS = 1024
TOP_SENTENCES = 5

# Lazy load model
_tokenizer = None
_model = None


def get_model():
    global _tokenizer, _model
    if _tokenizer is None:
        log(f"🚀 Loading Longformer model on {DEVICE}...")
        _tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
        _model = LongformerModel.from_pretrained(MODEL_NAME).to(DEVICE)
        _model.eval()
        log("✔ Longformer model loaded")
    return _tokenizer, _model


def condense_text(text: str) -> str:
    """Condense text to top N sentences using Longformer scoring."""
    sentences = sent_tokenize(text)
    if len(sentences) <= TOP_SENTENCES:
        return text
    
    tokenizer, model = get_model()
    
    inputs = tokenizer(
        text,
        return_tensors="pt",
        truncation=True,
        max_length=MAX_TOKENS
    ).to(DEVICE)
    
    with torch.no_grad():
        outputs = model(**inputs)
    
    # Lightweight sentence scoring based on token count
    scores = []
    for sent in sentences:
        sent_inputs = tokenizer(
            sent,
            return_tensors="pt",
            truncation=True,
            max_length=128
        )
        score = sent_inputs["input_ids"].shape[1]
        scores.append(score)
    
    top_idx = sorted(
        range(len(scores)),
        key=lambda i: scores[i],
        reverse=True
    )[:TOP_SENTENCES]
    
    top_idx.sort()
    return " ".join(sentences[i] for i in top_idx)


def process_article(article: dict) -> dict:
    """Process a single article and return condensed version."""
    headline = article.get("headline", "")
    content = article.get("content", "")
    full_text = f"{headline}. {content}".strip()
    
    if not full_text:
        return None
    
    condensed = condense_text(full_text)
    
    return {
        "article_id": article.get("article_id"),
        "headline": headline,
        "condensed_text": condensed,
        "source": article.get("source"),
        "published_time": article.get("published_time"),
        "url": article.get("url"),
        "CompanyName": article.get("CompanyName", ""),
        "Symbol": article.get("Symbol", ""),
        "Sector": article.get("Sector", ""),
        "Index": article.get("Index", ""),
        "condensed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }


def run_longformer(input_path: str = None) -> list:
    """
    Main entry point for Step 3.
    Reads from tagged_new.json (or custom input_path), condenses text,
    saves to all_condensed_news.json and condensed_news_new.json
    Returns the list of condensed articles from this run.
    """
    log("=" * 60)
    log("Step 3: Longformer Condensation Started")
    log("=" * 60)
    log(f"🚀 Device: {DEVICE}")
    
    os.makedirs(LONGFORMER_OUTPUT_DIR, exist_ok=True)
    
    # Load input (from Step 2)
    input_file = input_path or TAGGED_NEW_PATH
    articles = load_json(input_file)
    
    if not articles:
        log(f"🟡 No articles to process from {input_file}")
        save_json(CONDENSED_NEW_PATH, [])
        return []
    
    log(f"📥 Loaded {len(articles)} articles from {input_file}")
    
    # Process each article
    condensed_articles = []
    for i, article in enumerate(articles):
        result = process_article(article)
        if result:
            condensed_articles.append(result)
        if (i + 1) % 10 == 0:
            log(f"⏳ Processed {i + 1}/{len(articles)} articles...")
    
    log(f"✔ Condensed {len(condensed_articles)} articles")
    
    # Load existing all_condensed_news.json for deduplication using (article_id, symbol) key
    existing = load_json(CONDENSED_ALL_PATH)
    existing_keys = {(a.get("article_id"), a.get("Symbol")) for a in existing}
    
    # Find truly new articles using composite key
    new_condensed = [a for a in condensed_articles if (a.get("article_id"), a.get("Symbol")) not in existing_keys]
    
    # Append to all_condensed_news.json
    if new_condensed:
        all_data = existing + new_condensed
        save_json(CONDENSED_ALL_PATH, all_data)
        log(f"💾 Appended {len(new_condensed)} to {CONDENSED_ALL_PATH} (total: {len(all_data)})")
    else:
        log(f"🟡 No new articles to append to {CONDENSED_ALL_PATH}")
    
    # Save condensed_news_new.json (current run only)
    save_json(CONDENSED_NEW_PATH, new_condensed)
    log(f"🆕 Wrote {len(new_condensed)} condensed articles to {CONDENSED_NEW_PATH}")
    
    log("=" * 60)
    log(f"Step 3 Complete: {len(new_condensed)} articles condensed")
    log("=" * 60)
    
    return new_condensed


if __name__ == "__main__":
    articles = run_longformer()
    print(f"\n✅ Longformer completed: {len(articles)} articles condensed")
