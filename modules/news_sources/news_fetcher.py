# modules/news_sources/news_fetcher.py
import os
import json
from datetime import datetime

from config import MAX_ARTICLES, LOG_FILE, RECENT_MERGED_PATH

os.makedirs(os.path.dirname(RECENT_MERGED_PATH), exist_ok=True)
# Pre-create the file so it exists even if all sources fail
with open(RECENT_MERGED_PATH, "w", encoding="utf-8") as f:
    json.dump([], f, ensure_ascii=False, indent=2)


from modules.news_sources.moneycontrol import fetch_and_save_articles as fetch_moneycontrol
from modules.news_sources.livemint import fetch_and_save_articles as fetch_livemint
from modules.news_sources.the_economic_times import fetch_and_save_articles as fetch_et
from modules.news_sources.cnbc_tv18 import fetch_and_save_articles as fetch_cnbc



def log(msg: str):
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"{datetime.now()} | [news_fetcher] {msg}\n")
    print(f"[news_fetcher] {msg}")


def dedup_by_url_and_id(items):
    seen = set()
    out = []
    for a in items:
        key = (a.get("url"), a.get("article_id"))
        if key in seen:
            continue
        seen.add(key)
        out.append(a)
    return out


def fetch_all_sources(max_articles: int = MAX_ARTICLES):
    """Sequentially fetch all sources, merge, global-dedup, and write merged recent."""
    all_new = []
    sources = [
        ("Moneycontrol", fetch_moneycontrol),
        ("LiveMint", fetch_livemint),
        ("Economic Times", fetch_et),
        ("CNBC-TV18", fetch_cnbc),
    ]

    for name, fn in sources:
        try:
            log(f"▶ Fetching {name} …")
            items = fn(max_articles=max_articles) or []
            log(f"✔ {name}: {len(items)} new")
            all_new.extend(items)
        except Exception as e:
            log(f"✖ {name} failed: {e}")

    merged = dedup_by_url_and_id(all_new)
    if len(merged) != len(all_new):
        log(f"🟡 Global dedup removed {len(all_new) - len(merged)} duplicate item(s).")

    os.makedirs(os.path.dirname(RECENT_MERGED_PATH), exist_ok=True)
    with open(RECENT_MERGED_PATH, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)

    log(f"💾 Saved merged recent: {RECENT_MERGED_PATH} ({len(merged)} items)")
    return merged


if __name__ == "__main__":
    merged = fetch_all_sources()
    print(f"✅ Merged {len(merged)} new articles.")

