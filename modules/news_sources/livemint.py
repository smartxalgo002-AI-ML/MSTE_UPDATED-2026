import requests
from bs4 import BeautifulSoup
from datetime import datetime
import re
import os
import json
import time
import hashlib

from config import (
    LIVEMINT_RAW_NEWS_PATH as RAW_NEWS_PATH,
    LIVEMINT_RECENT_NEWS_PATH as RECENT_NEWS_PATH,
    LOG_FILE,
    MAX_ARTICLES,
)

headers = {"User-Agent": "Mozilla/5.0"}

def log(msg):
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"{datetime.now()} | [LiveMint] {msg}\n")
    print(f"[LiveMint] {msg}")

def safe_get(url, max_retries=3, timeout=10):
    for i in range(max_retries):
        try:
            response = requests.get(url, headers=headers, timeout=timeout)
            if response.status_code == 200:
                return response
            else:
                log(f"Non-200 status {response.status_code} for URL: {url}")
        except Exception as e:
            log(f"Request error: {e} (try {i+1})")
        time.sleep(2 ** i)
    return None

def extract_article_id(url):
    m = re.search(r'(\d{14})\.html', url)
    return m.group(1) if m else hashlib.md5(url.encode()).hexdigest()

def save_recent_json(new_articles):
    os.makedirs(os.path.dirname(RECENT_NEWS_PATH), exist_ok=True)
    with open(RECENT_NEWS_PATH, "w", encoding="utf-8") as f:
        json.dump(new_articles, f, indent=2, ensure_ascii=False)
    log(f"🆕 Wrote {len(new_articles)} recent articles → {RECENT_NEWS_PATH}")

def clear_recent_file():
    os.makedirs(os.path.dirname(RECENT_NEWS_PATH), exist_ok=True)
    with open(RECENT_NEWS_PATH, "w", encoding="utf-8") as f:
        json.dump([], f, indent=2, ensure_ascii=False)
    log("🧹 Cleared recent file (livemint_latest_recent.json).")

def fetch_livemint_headlines(max_articles=MAX_ARTICLES):
    try:
        url = "https://www.livemint.com/market/stock-market-news"
        response = safe_get(url)
        if not response:
            log("❌ Failed to fetch LiveMint stock-market-news page.")
            return []

        soup = BeautifulSoup(response.text, "html.parser")
        articles, seen_links = [], set()

        for a_tag in soup.find_all("a", href=True):
            link = a_tag["href"]
            if not link.startswith("https://"):
                link = "https://www.livemint.com" + link

            if "/market/stock-market-news" in link and link.endswith(".html") and link not in seen_links:
                title = a_tag.get_text(strip=True)
                if title and len(title) > 20:
                    seen_links.add(link)
                    articles.append({"headline": title, "url": link})
                    if len(articles) >= max_articles:
                        break
        return articles
    except Exception as e:
        log(f"⚠️ fetch_livemint_headlines error: {e}")
        return []

DISCLAIMER_CLASS_SELECTORS = (
    ".disclaimer, .disclaimerText, .articleDisclaimer, .disclaimer-box, .story-disclaimer"
)
DISCLAIMER_REGEXES = [
    r"(?i)^\s*disclaimer\b.*",
    r"(?i)^\s*the views (and|&)?\s*recommendations\b.*",
    r"(?i)^\s*(livemint|mint)\s+(cannot|does not)\s+(verify|endorse)\b.*",
    r"(?i)^\s*this story was auto-generated\b.*",
]
LIVEMINT_BOILERPLATE_REGEXES = [
    r"(?i)^\W*n?\s*catch\s+all\s+the\s+.*live\s*mint.*$",
    r"(?i)^\W*download\s+(the\s+)?mint(\s+news)?\s+app\b.*$",
    r"(?i)^\W*read\s+premium\s+stories.*$",
    r"(?i)^\W*log\s*in\s+to\s+our\s+website\s+to\s+save\s+your\s+bookmarks.*$",
    r"(?i)^\W*it'?ll\s+just\s+take\s+a\s+moment\.?$",
    r"(?i)^.*?exceeded\s+the\s+limit\s+to\s+bookmark\s+the\s+image.*$",
    r"(?i)^.*?remove\s+some\s+to\s+bookmark\s+this\s+image.*$",
]

def _strip_lines_by_regexes(text: str, regex_list) -> str:
    if not text:
        return text
    lines = [ln.strip() for ln in text.split("\n")]
    kept = [ln for ln in lines if not any(re.search(rx, ln) for rx in regex_list)]
    out = "\n".join(l for l in kept if l)
    return re.sub(r"\n{3,}", "\n\n", out).strip()

def strip_disclaimer_lines(text: str) -> str:
    return _strip_lines_by_regexes(text, DISCLAIMER_REGEXES)

def strip_livemint_boilerplate(text: str) -> str:
    return _strip_lines_by_regexes(text, LIVEMINT_BOILERPLATE_REGEXES)

def drop_disclaimer_nodes(soup: BeautifulSoup) -> None:
    try:
        for el in soup.select(DISCLAIMER_CLASS_SELECTORS):
            el.decompose()
        for tag in soup.find_all(["p", "div", "span", "li"], string=re.compile(r"^\s*Disclaimer\b", re.I)):
            tag.decompose()
    except Exception:
        pass

def fetch_full_article(url):
    try:
        response = safe_get(url)
        if not response:
            return None, None

        soup = BeautifulSoup(response.text, "html.parser")
        drop_disclaimer_nodes(soup)

        content = ""
        container = soup.find("div", class_="contentSec")
        if container:
            paragraphs = container.find_all("p")
            content = "\n".join(p.get_text(" ", strip=True) for p in paragraphs if p.get_text(strip=True))

        if not content:
            paragraphs = soup.find_all("p")
            content = "\n".join(p.get_text(" ", strip=True) for p in paragraphs if p.get_text(strip=True))
            if len(content) < 50:
                return None, None

        content = strip_disclaimer_lines(content)
        content = strip_livemint_boilerplate(content)

        meta_pub = soup.find("meta", attrs={"property": "article:published_time"})
        if meta_pub and meta_pub.get("content"):
            published_time = meta_pub["content"][:19].replace("T", " ")
        else:
            published_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        return content.strip(), published_time
    except Exception as e:
        log(f"⚠️ Error fetching article from {url}: {e}")
        return None, None

def save_articles_to_json(articles_data):
    os.makedirs(os.path.dirname(RAW_NEWS_PATH), exist_ok=True)
    filename = RAW_NEWS_PATH

    existing_urls = set()
    existing_article_ids = set()
    if os.path.exists(filename):
        with open(filename, "r", encoding="utf-8") as f:
            try:
                existing_data = json.load(f)
                existing_urls = {item.get("url") for item in existing_data}
                existing_article_ids = {item.get("article_id") for item in existing_data}
            except Exception:
                existing_data = []
    else:
        existing_data = []

    new_articles = [
        a for a in articles_data
        if not (a["url"] in existing_urls and a["article_id"] in existing_article_ids)
    ]

    if not new_articles:
        log("🟡 No new JSON articles to append (deduplication).")
        save_recent_json([])  # overwrite recent with empty
        return []

    all_data = existing_data + new_articles
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(all_data, f, indent=2, ensure_ascii=False)

    log(f"💾 JSON updated: {filename} ({len(new_articles)} new)")
    save_recent_json(new_articles)
    return new_articles

def fetch_and_save_articles(max_articles=MAX_ARTICLES):
    log("📡 Fetching LiveMint headlines...")
    articles = fetch_livemint_headlines(max_articles=max_articles)
    articles = list(reversed(articles))  # Oldest first
    articles_data = []

    if not articles:
        log("❌ No articles found.")
    else:
        for article in articles:
            content, published_time = fetch_full_article(article["url"])
            if content:
                article_id = extract_article_id(article["url"])
                articles_data.append({
                    "article_id": article_id,
                    "headline": article["headline"],
                    "content": content,
                    "url": article["url"],
                    "published_time": published_time,  # no normalization
                    "scraped_at": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    "source": "LiveMint"
                })
            else:
                log(f"❌ Could not extract article: {article['url']}")

        new_articles = []
        if articles_data:
            new_articles = save_articles_to_json(articles_data)

    return new_articles if articles_data else []

if __name__ == "__main__":
    added = fetch_and_save_articles()
    print(f"✅ Added {len(added)} new LiveMint articles to RAW and RECENT.")

def pull(max_articles=MAX_ARTICLES):
    articles = fetch_livemint_headlines(max_articles=max_articles)
    articles = list(reversed(articles))
    if not articles:
        log("❌ [pull] LiveMint: no headlines found.")
        return []
    out = []
    for a in articles:
        content, published_time = fetch_full_article(a["url"])
        if content:
            out.append({
                "article_id": extract_article_id(a["url"]),
                "headline": a["headline"],
                "content": content,
                "url": a["url"],
                "published_time": published_time,
                "scraped_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "source": "LiveMint",
            })
        else:
            log(f"❌ [pull] Could not extract article: {a['url']}")
    return out

