"""
Step 1: News Fetcher
Fetches news from all 4 sources (Moneycontrol, LiveMint, CNBC-TV18, Economic Times)
Saves per-source: all_*.json (permanent/append) and *_new.json (current run only)
Creates merged_news.json with all sources combined
"""
import os
import json
from datetime import datetime

from config import (
    MAX_ARTICLES,
    LOG_FILE,
    NEWS_FETCHER_OUTPUT_DIR,
    MONEYCONTROL_ALL_PATH,
    MONEYCONTROL_NEW_PATH,
    LIVEMINT_ALL_PATH,
    LIVEMINT_NEW_PATH,
    CNBC_ALL_PATH,
    CNBC_NEW_PATH,
    ET_ALL_PATH,
    ET_NEW_PATH,
    BUSINESS_TODAY_ALL_PATH,
    BUSINESS_TODAY_NEW_PATH,
    HINDU_BL_ALL_PATH,
    HINDU_BL_NEW_PATH,
    MERGED_NEWS_ALL_PATH,
    MERGED_NEWS_NEW_PATH,
)

from modules.news_sources.moneycontrol import pull as pull_moneycontrol
from modules.news_sources.livemint import pull as pull_livemint
from modules.news_sources.the_economic_times import fetch_and_save_articles as fetch_et
from modules.news_sources.cnbc_tv18 import fetch_and_save_articles as fetch_cnbc
from modules.news_sources.business_today import collect_candidate_links, extract_content_and_time, extract_article_id as bt_extract_id
from modules.news_sources.hindu_business_line import fetch_bl_headlines, fetch_full_bl_article, extract_bl_article_id


def fetch_business_today(max_articles: int = 12) -> list:
    """Fetch articles from Business Today and return in standard format."""
    candidates = collect_candidate_links(max_links=max_articles)
    if not candidates:
        return []
    
    results = []
    for c in candidates:
        content, published = extract_content_and_time(c["url"])
        if not content:
            continue
        aid = bt_extract_id(c["url"])
        results.append({
            "article_id": aid,
            "headline": c["headline"],
            "content": content,
            "url": c["url"],
            "published_time": published,
            "scraped_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "source": "BusinessToday"
        })
    return results


def fetch_hindu_business_line(max_articles: int = 10) -> list:
    """Fetch articles from Hindu Business Line and return in standard format."""
    articles = fetch_bl_headlines(max_articles=max_articles)
    if not articles:
        return []
    
    results = []
    for article in articles:
        content, published_time = fetch_full_bl_article(article["url"])
        if not content:
            continue
        article_id = extract_bl_article_id(article["url"])
        results.append({
            "article_id": article_id,
            "headline": article["headline"],
            "content": content,
            "url": article["url"],
            "published_time": published_time,
            "scraped_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "source": "The Hindu Business Line"
        })
    return results


def log(msg: str):
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"{datetime.now()} | [news_fetcher_step1] {msg}\n")
    print(f"[news_fetcher_step1] {msg}")


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
        json.dump(data, f, ensure_ascii=False, indent=2)


def dedup_articles(articles: list) -> list:
    """Deduplicate by article_id"""
    seen = set()
    out = []
    for a in articles:
        aid = a.get("article_id")
        if aid in seen:
            continue
        seen.add(aid)
        out.append(a)
    return out


def append_to_all(all_path: str, new_articles: list) -> list:
    """
    Append new_articles to all_path, deduplicating by article_id.
    Returns the list of truly new articles that were appended.
    """
    existing = load_json(all_path)
    existing_ids = {a.get("article_id") for a in existing}
    
    fresh = [a for a in new_articles if a.get("article_id") not in existing_ids]
    
    if fresh:
        all_data = existing + fresh
        save_json(all_path, all_data)
        log(f"💾 Appended {len(fresh)} new to {all_path} (total: {len(all_data)})")
    else:
        log(f"🟡 No new articles to append to {all_path}")
    
    return fresh


def fetch_source(name: str, fetch_fn, all_path: str, new_path: str, max_articles: int) -> list:
    """
    Fetch from a single source, save to all_*.json and *_new.json
    Returns the list of new articles from this run.
    """
    log(f"▶ Fetching {name}...")
    
    try:
        if name in ["Moneycontrol", "LiveMint"]:
            articles = fetch_fn(max_articles=max_articles)
        else:
            articles = fetch_fn(max_articles=max_articles)
        
        if not articles:
            log(f"🟡 {name}: No articles fetched")
            save_json(new_path, [])
            return []
        
        log(f"✔ {name}: Fetched {len(articles)} articles")
        
        fresh = append_to_all(all_path, articles)
        save_json(new_path, fresh)
        log(f"🆕 {name}: Wrote {len(fresh)} new articles to {new_path}")
        
        return fresh
        
    except Exception as e:
        log(f"✖ {name} failed: {e}")
        save_json(new_path, [])
        return []


def run_news_fetcher(max_articles: int = MAX_ARTICLES) -> list:
    """
    Main entry point for Step 1.
    Fetches from all sources, saves per-source files, creates merged_news.json
    Returns the list of all new articles from this run.
    """
    log("=" * 60)
    log("Step 1: News Fetcher Started")
    log("=" * 60)
    
    os.makedirs(NEWS_FETCHER_OUTPUT_DIR, exist_ok=True)
    
    all_new = []
    
    # Moneycontrol
    new_mc = fetch_source(
        "Moneycontrol",
        pull_moneycontrol,
        MONEYCONTROL_ALL_PATH,
        MONEYCONTROL_NEW_PATH,
        max_articles
    )
    all_new.extend(new_mc)
    
    # LiveMint
    new_lm = fetch_source(
        "LiveMint",
        pull_livemint,
        LIVEMINT_ALL_PATH,
        LIVEMINT_NEW_PATH,
        max_articles
    )
    all_new.extend(new_lm)
    
    # Economic Times (uses fetch_and_save_articles which handles its own file saving)
    log("▶ Fetching Economic Times...")
    try:
        et_articles = fetch_et(max_articles=max_articles)
        if et_articles:
            log(f"✔ Economic Times: {len(et_articles)} new articles")
            all_new.extend(et_articles)
        else:
            log("🟡 Economic Times: No new articles")
    except Exception as e:
        log(f"✖ Economic Times failed: {e}")
    
    # CNBC-TV18 (uses fetch_and_save_articles which handles its own file saving)
    log("▶ Fetching CNBC-TV18...")
    try:
        cnbc_articles = fetch_cnbc(max_articles=max_articles)
        if cnbc_articles:
            log(f"✔ CNBC-TV18: {len(cnbc_articles)} new articles")
            all_new.extend(cnbc_articles)
        else:
            log("🟡 CNBC-TV18: No new articles")
    except Exception as e:
        log(f"✖ CNBC-TV18 failed: {e}")
    
    # Business Today
    log("▶ Fetching Business Today...")
    try:
        bt_articles = fetch_business_today(max_articles=max_articles)
        if bt_articles:
            fresh_bt = append_to_all(BUSINESS_TODAY_ALL_PATH, bt_articles)
            save_json(BUSINESS_TODAY_NEW_PATH, fresh_bt)
            log(f"✔ Business Today: {len(fresh_bt)} new articles")
            all_new.extend(fresh_bt)
        else:
            log("🟡 Business Today: No articles fetched")
            save_json(BUSINESS_TODAY_NEW_PATH, [])
    except Exception as e:
        log(f"✖ Business Today failed: {e}")
        save_json(BUSINESS_TODAY_NEW_PATH, [])
    
    # Hindu Business Line
    log("▶ Fetching Hindu Business Line...")
    try:
        hbl_articles = fetch_hindu_business_line(max_articles=max_articles)
        if hbl_articles:
            fresh_hbl = append_to_all(HINDU_BL_ALL_PATH, hbl_articles)
            save_json(HINDU_BL_NEW_PATH, fresh_hbl)
            log(f"✔ Hindu Business Line: {len(fresh_hbl)} new articles")
            all_new.extend(fresh_hbl)
        else:
            log("🟡 Hindu Business Line: No articles fetched")
            save_json(HINDU_BL_NEW_PATH, [])
    except Exception as e:
        log(f"✖ Hindu Business Line failed: {e}")
        save_json(HINDU_BL_NEW_PATH, [])
    
    # Deduplicate merged
    merged = dedup_articles(all_new)
    if len(merged) != len(all_new):
        log(f"🟡 Global dedup removed {len(all_new) - len(merged)} duplicate(s)")
    
    # Save news_new.json (current run only)
    save_json(MERGED_NEWS_NEW_PATH, merged)
    log(f"💾 Saved news_new.json ({len(merged)} articles)")
    
    # Append to all_news.json (cumulative)
    truly_new = append_to_all(MERGED_NEWS_ALL_PATH, merged)
    log(f"➕ Appended {len(truly_new)} to all_news.json (cumulative)")
    
    log("=" * 60)
    log(f"Step 1 Complete: {len(merged)} new articles fetched")
    log("=" * 60)
    
    return merged


if __name__ == "__main__":
    articles = run_news_fetcher()
    print(f"\n✅ News Fetcher completed: {len(articles)} new articles")
