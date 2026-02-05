import requests
from bs4 import BeautifulSoup
from datetime import datetime
import re
import os
import json
import time
import hashlib

from config import MONEYCONTROL_RAW_NEWS_PATH, MONEYCONTROL_RECENT_NEWS_PATH, LOG_FILE, MAX_ARTICLES

headers = {"User-Agent": "Mozilla/5.0"}


def log(msg):
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"{datetime.now()} | {msg}\n")
    print(msg)


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
    match = re.search(r'(\d{5,})\.html', url)
    return match.group(1) if match else hashlib.md5(url.encode()).hexdigest()


def save_recent_json(new_articles):
    os.makedirs(os.path.dirname(MONEYCONTROL_RECENT_NEWS_PATH), exist_ok=True)
    with open(MONEYCONTROL_RECENT_NEWS_PATH, "w", encoding="utf-8") as f:
        json.dump(new_articles, f, indent=2, ensure_ascii=False)
    log(f"🆕 Wrote {len(new_articles)} recent articles → {MONEYCONTROL_RECENT_NEWS_PATH}")


def clear_recent_file():
    os.makedirs(os.path.dirname(MONEYCONTROL_RECENT_NEWS_PATH), exist_ok=True)
    with open(MONEYCONTROL_RECENT_NEWS_PATH, "w", encoding="utf-8") as f:
        json.dump([], f, indent=2, ensure_ascii=False)
    log("🧹 Cleared recent file (moneycontrol_latest_recent.json).")


def fetch_moneycontrol_headlines(max_articles=MAX_ARTICLES):
    try:
        url = "https://www.moneycontrol.com/news/business/"
        response = safe_get(url)
        if not response:
            log("❌ Failed to fetch homepage.")
            return []

        soup = BeautifulSoup(response.text, "html.parser")
        articles, seen_links = [], set()

        for li in soup.find_all("li", class_="clearfix"):
            a_tag = li.find("a", href=True)
            h2_tag = li.find("h2") or li.find("h3")
            if a_tag and h2_tag:
                link = a_tag["href"]
                title = h2_tag.get_text(strip=True)
                if link.startswith("https://") and link not in seen_links and not re.search(r'(video|photo|gallery|live-blog)', link):
                    seen_links.add(link)
                    articles.append({"headline": title, "url": link})
                    if len(articles) >= max_articles:
                        break
        return articles
    except Exception as e:
        log(f"⚠️ fetch_moneycontrol_headlines error: {e}")
        return []


def fetch_full_article(url):
    try:
        response = safe_get(url)
        if not response:
            return None, None

        soup = BeautifulSoup(response.text, "html.parser")

        if "liveblog" in url or "live-blog" in url:
            content_blocks = soup.find_all("div", class_=re.compile(r"^liveBlogData$|^liveBlogDataWrap$"))
            article_text = "\n".join(block.get_text(strip=True) for block in content_blocks if block.get_text(strip=True))
            if len(article_text) > 100:
                published_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                return article_text, published_time

        possible_selectors = [
            'div#contentdata',          # Most common in new layout
            'div.content_wrapper', 
            'div.arti-flow',            # Another common wrapper
            'div#article-main', 
            'div.article_content',
            'div.arttextxml', 
            'div.maincontent', 
            'div.article_content_new',
            'div.clearfix', 
            'article',
        ]
        article_text = ""
        for selector in possible_selectors:
            container = soup.select_one(selector)
            if container:
                # Remove junk elements before extracting text
                for junk in container.select('.arttidate, .article_schedule, .social_icons, .tags_first_line, .inv_social'):
                    junk.decompose()
                    
                paragraphs = container.find_all("p")
                text_content = "\n".join(p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True))
                
                # Check for junk content
                if "My Account" in text_content[:50] or "Follow us on" in text_content[:50]:
                    continue
                    
                if len(text_content) > 100:
                    article_text = text_content
                    break

        if not article_text:
            paragraphs = soup.find_all("p")
            article_text = "\n".join(p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True))
            if len(article_text) < 100:
                return None, None

        date_tag = soup.find("div", class_="arttidate") or soup.find("div", class_="article_schedule")
        published_time = date_tag.get_text(strip=True) if date_tag else datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        return article_text.strip(), published_time

    except Exception as e:
        log(f"⚠️ Error fetching article from {url}: {e}")
        return None, None


def save_articles_to_json(articles_data):
    os.makedirs(os.path.dirname(MONEYCONTROL_RAW_NEWS_PATH), exist_ok=True)
    filename = MONEYCONTROL_RAW_NEWS_PATH

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
        save_recent_json([])  # still overwrite recent with empty
        return []

    all_data = existing_data + new_articles
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(all_data, f, indent=2, ensure_ascii=False)

    log(f"💾 JSON updated: {filename} ({len(new_articles)} new)")
    save_recent_json(new_articles)
    return new_articles


def fetch_and_save_articles(max_articles=MAX_ARTICLES):
    log("📡 Fetching Moneycontrol headlines...")
    articles = fetch_moneycontrol_headlines(max_articles=max_articles)
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
                    "published_time": published_time,
                    "scraped_at": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    "source": "Moneycontrol"
                })
            else:
                log(f"❌ Could not extract article: {article['url']}")

        new_articles = []
        if articles_data:
            new_articles = save_articles_to_json(articles_data)

    return new_articles if articles_data else []


if __name__ == "__main__":
    added = fetch_and_save_articles()
    print(f"✅ Added {len(added)} new articles to RAW and RECENT.")





def pull(max_articles=MAX_ARTICLES):
    """
    Return latest Moneycontrol articles WITHOUT writing files.
    Uses the same helpers as fetch_and_save_articles, but just returns the list.
    """
    articles = fetch_moneycontrol_headlines(max_articles=max_articles)
    articles = list(reversed(articles))  # oldest first
    articles_data = []
    if not articles:
        log("❌ [pull] Moneycontrol: no headlines found.")
        return []

    for article in articles:
        content, published_time = fetch_full_article(article["url"])
        if content:
            article_id = extract_article_id(article["url"])
            articles_data.append({
                "article_id": article_id,
                "headline": article["headline"],
                "content": content,
                "url": article["url"],
                "published_time": published_time,
                "scraped_at": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                "source": "Moneycontrol",
            })
        else:
            log(f"❌ [pull] Could not extract article: {article['url']}")
    return articles_data
