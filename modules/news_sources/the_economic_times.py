import requests
from bs4 import BeautifulSoup
from datetime import datetime
import os
import json
import hashlib
import time
import re

from config import (
    ET_RAW_NEWS_PATH as RAW_NEWS_PATH,
    ET_RECENT_NEWS_PATH as RECENT_NEWS_PATH,
    LOG_FILE,
    MAX_ARTICLES,
)

headers = {"User-Agent": "Mozilla/5.0"}

def log(msg):
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"{datetime.now()} | [EconomicTimes] {msg}\n")
    print(f"[EconomicTimes] {msg}")

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
    m = re.search(r'/articleshow/(\d+)\.cms', url)
    if m:
        return m.group(1)
    m2 = re.search(r'(\d{6,})', url)
    if m2:
        return m2.group(1)
    return hashlib.md5(url.encode()).hexdigest()

def _try_parse_many(dt_str, fmts):
    for fmt in fmts:
        try:
            return datetime.strptime(dt_str, fmt)
        except Exception:
            pass
    return None

def format_et_published(published_raw: str) -> str:
    """Normalize ET date to: 'HH:MM:SS AM/PM | DD Mon YYYY'"""
    if not published_raw:
        return None

    s = published_raw.strip().replace("IST", "").strip()
    s = re.sub(r"(?i)updated:\s*", "", s)

    dt = _try_parse_many(s, [
        "%b %d, %Y, %I:%M:%S %p",
        "%b %d, %Y, %I:%M %p",
        "%d %b %Y, %I:%M:%S %p",
        "%d %b %Y, %I:%M %p",
        "%Y-%m-%d %H:%M:%S",
    ])
    if dt:
        return dt.strftime("%I:%M:%S %p | %d %b %Y")
    return None

JUNK_PHRASES = [
    "Subscribe to", "Telegram feeds", "Top Trending Stocks:", "In Case you missed it",
    "Top Searched Companies", "Top Calculators", "Top Definitions", "Top Story Listing",
    "Top Slideshow", "Private Companies", "Top Commodities", "Top Prime Articles",
    "Top Market Pages", "Latest News", "Follow us on:", "Find this comment offensive?",
    "Stories you might be interested in", "Choose your reason below", "Reason for reporting:",
    "Will be displayed", "Your Reason has been Reported", "Log In/Connect with:", "Worry not.",
    "You’re just a step away.", "It seems like you're already an ETPrime member",
    "Log out of your current logged-in account", "Offer Exclusively For You",
    "Flat 40% Off", "ET PRIME", "ETPrime", "TimesPrime", "Docubay Subscription",
    "TOI ePaper", "ePaper", "Most Searched IFSC Codes", "New York Times Exclusives",
    "Stock Reports Plus", "BigBull Portfolio", "Stock Analyzer", "Market Mood",
    "Stock Talk Live", "Wealth Edition", "Health+ Stories", "Investment Ideas",
    "Get 1 Year Free", "Then ₹", "Special Offer", "Top Performing", "SIP’s starting",
    "Better Than Fixed Deposits", "Low Cost High Return Funds", "Promising Multi Cap Funds",
    "Complete Excel guide", "Technical Analysis Demystified", "AI For Business Professionals",
    "Financial Literacy", "Lets Crack the Billionaire Code", "Excel Essentials to Expert",
    "By Metla Sudha Sekhar", "By Dinesh Nagpal", "By CA Rahul Gupta", "By Neil Patel",
    "By Kunal Patel", "By Study at home", "By Ansh Mehra",
]
JUNK_REGEXES = [
    r"(?i)^offer.*", r"(?i)^what’s included.*", r"(?i)^read the pdf", r"(?i)^login.*",
    r"(?i)^read more.*", r"(?i)^watch live.*", r"(?i)^join now.*", r"(?i)^click here.*",
    r"(?i)^get flat .*", r"(?i)^save up to .*", r"(?i)^access .* subscription",
    r"(?i)ET\s*Prime", r"(?i)Times\s*Prime", r"(?i)Docubay", r"(?i)ePaper",
    r"(?i)Most Searched IFSC Codes", r"(?i)^by\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*$",
    r"(?i)Leadership\s*\|\s*Entrepreneurship",
    r"(?i)Complete Excel guide", r"(?i)Technical Analysis & Candlestick Theory",
    r"(?i)Financial Literacy", r"(?i)Lets Crack the Billionaire Code",
    r"(?i)Excel Essentials to Expert", r"(?i)AI For Business Professionals",
]

def looks_like_ad_or_nav(line: str) -> bool:
    if any(phrase in line for phrase in JUNK_PHRASES):
        return True
    for rx in JUNK_REGEXES:
        if re.search(rx, line.strip()):
            return True
    if re.match(r"(?i)^(all|top|best|most)\b.*(funds|stocks|ideas|indices|courses)", line):
        return True
    if len(line) > 200 and line.count(" ") < 5:
        return True
    return False

def clean_article_content(article_text):
    lines = [l.strip() for l in article_text.split("\n")]
    cleaned = []
    for line in lines:
        if not line:
            continue
        if looks_like_ad_or_nav(line):
            continue
        cleaned.append(line)
    final = "\n".join(cleaned)
    final = re.sub(r"\n{3,}", "\n\n", final).strip()
    return final

def clean_synopsis_text(text: str) -> str:
    if not text:
        return ""
    s = " ".join(text.split())
    s = re.sub(r"(?i)\b(read more|also read|watch|live updates)\b.*", "", s).strip()
    return s

def _extract_article_body(soup: BeautifulSoup) -> str:
    candidates = []
    candidates.extend(soup.select('[itemprop="articleBody"]'))
    node = soup.select_one('#artText') or soup.select_one('.artText') or soup.select_one('#artTextWSJ')
    if node:
        candidates.append(node)

    if not candidates:
        normals = soup.find_all("div", class_="Normal")
        if normals:
            text = "\n".join(d.get_text(" ", strip=True) for d in normals if d.get_text(strip=True))
            return text

    if candidates:
        text = "\n".join(el.get_text(" ", strip=True) for el in candidates if el.get_text(strip=True))
        if text:
            return text

    paragraphs = soup.find_all("p")
    return "\n".join(p.get_text(" ", strip=True) for p in paragraphs if p.get_text(strip=True))

def fetch_et_headlines_with_synopsis(max_articles=MAX_ARTICLES):
    url = "https://economictimes.indiatimes.com/markets/stocks/news"
    response = safe_get(url)
    if not response:
        log("❌ Failed to fetch ET homepage.")
        return []

    soup = BeautifulSoup(response.text, "html.parser")
    articles, seen_links = [], set()
    article_links = soup.find_all('a', href=re.compile(r'/articleshow/\d+\.cms'))

    for a_tag in article_links:
        link = "https://economictimes.indiatimes.com" + a_tag["href"]
        if link in seen_links:
            continue

        parent_div = a_tag.find_parent('div')
        title = a_tag.get_text(strip=True)
        syn = None

        if parent_div:
            syn_candidates = [
                parent_div.find("p", class_=re.compile(r"synop|summary|desc", re.I)),
                parent_div.find("div", class_=re.compile(r"synop|summary|desc", re.I)),
                parent_div.find("p"),
            ]
            for cand in syn_candidates:
                if cand and cand.get_text(strip=True):
                    syn = clean_synopsis_text(cand.get_text(" ", strip=True))
                    break

        if title and len(title) > 20 and syn and len(syn) > 30:
            seen_links.add(link)
            articles.append({"headline": title, "url": link, "synopsis": syn})
            if len(articles) >= max_articles:
                break

    return articles

def fetch_full_article_et(url):
    response = safe_get(url)
    if not response:
        return None, None

    soup = BeautifulSoup(response.text, "html.parser")
    raw_text = _extract_article_body(soup)
    if not raw_text or len(raw_text) < 80:
        return None, None

    cleaned = clean_article_content(raw_text)
    if len(cleaned) < 80:
        return None, None

    published_time = None

    meta_time = soup.find("meta", attrs={"property": "article:publishedTime"})
    if meta_time and meta_time.get("content"):
        published_time = format_et_published(meta_time["content"])

    if not published_time:
        meta_ptime = soup.find("meta", attrs={"name": "ptime"})
        if meta_ptime and meta_ptime.get("content"):
            published_time = format_et_published(meta_ptime["content"])

    if not published_time:
        time_tag = soup.find("time")
        if time_tag:
            dt_str = time_tag.get("datetime") or time_tag.get_text(strip=True)
            published_time = format_et_published(dt_str)

    if not published_time:
        for cls in ["date", "time", "dateline"]:
            possible = soup.find("span", class_=re.compile(cls, re.I)) or \
                       soup.find("div", class_=re.compile(cls, re.I))
            if possible and possible.get_text(strip=True):
                published_time = format_et_published(possible.get_text(strip=True))
                if published_time:
                    break

    if not published_time:
        text = soup.get_text()
        match = re.search(r'(?:Published|Updated|Last updated):\s*(.*?)\s*(?:IST|GMT)', text, re.I)
        if match:
            published_time = format_et_published(match.group(1))

    if not published_time:
        log(f"⚠️ Could not fetch published time for {url}")
        return None, None

    return cleaned.strip(), published_time

def _save_recent_json(new_articles):
    os.makedirs(os.path.dirname(RECENT_NEWS_PATH), exist_ok=True)
    with open(RECENT_NEWS_PATH, "w", encoding="utf-8") as f:
        json.dump(new_articles, f, ensure_ascii=False, indent=2)
    log(f"🆕 Wrote {len(new_articles)} recent articles → {RECENT_NEWS_PATH}")

def _clear_recent_file():
    os.makedirs(os.path.dirname(RECENT_NEWS_PATH), exist_ok=True)
    with open(RECENT_NEWS_PATH, "w", encoding="utf-8") as f:
        json.dump([], f, ensure_ascii=False, indent=2)
    log("🧹 Cleared recent file (et_latest_recent.json).")

def save_articles_to_json(articles_data):
    os.makedirs(os.path.dirname(RAW_NEWS_PATH), exist_ok=True)
    filename = RAW_NEWS_PATH

    existing_urls, existing_ids = set(), set()
    if os.path.exists(filename):
        with open(filename, "r", encoding="utf-8") as f:
            try:
                existing = json.load(f)
            except Exception:
                existing = []
        existing_urls = {it.get("url") for it in existing}
        existing_ids  = {it.get("article_id") for it in existing}
    else:
        existing = []

    new_articles = [
        a for a in articles_data
        if not (a["url"] in existing_urls and a["article_id"] in existing_ids)
    ]

    if not new_articles:
        log("🟡 No new JSON articles to append (deduplication).")
        _clear_recent_file()
        return []

    all_data = existing + new_articles
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(all_data, f, ensure_ascii=False, indent=2)

    log(f"💾 JSON updated: {filename} ({len(new_articles)} new)")
    _save_recent_json(new_articles)
    return new_articles

def fetch_and_save_articles(max_articles=MAX_ARTICLES):
    log("📡 Fetching Economic Times headlines (with synopsis)...")
    articles = fetch_et_headlines_with_synopsis(max_articles=max_articles)
    articles = list(reversed(articles))  # oldest first
    articles_data = []

    if not articles:
        log("❌ No articles with synopsis found.")
        _clear_recent_file()
        return []

    for article in articles:
        content, published_time = fetch_full_article_et(article["url"])
        if content:
            article_id = extract_article_id(article["url"])
            articles_data.append({
                "article_id": article_id,
                "headline": article["headline"],
                "content": content,
                "url": article["url"],
                "published_time": published_time,  # keep ET style (e.g., "10:03:00 PM | 26 Sep 2025")
                "scraped_at": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                "source": "Economic Times",
            })
        else:
            log(f"❌ Could not extract article: {article['url']}")

    if not articles_data:
        _clear_recent_file()
        return []

    return save_articles_to_json(articles_data)

if __name__ == "__main__":
    added = fetch_and_save_articles(max_articles=10)
    print(f"✅ Added {len(added)} new ET articles to RAW and RECENT.")

