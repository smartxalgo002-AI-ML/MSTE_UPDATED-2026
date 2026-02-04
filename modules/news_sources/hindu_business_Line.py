import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import os
import json
import re
import time
import hashlib

# --- Global Configuration ---
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"}
BL_LATEST_NEWS_URL = "https://www.thehindubusinessline.com/latest-news/"
TARGET_TIME_FORMAT = '%B %d, %Y at %I:%M %p' 
# ---

# =========================
# Core Utility Functions
# =========================

def log(msg):
    """Writes a timestamped message to a log file."""
    os.makedirs("logs", exist_ok=True)
    with open("logs/bl_scrape_log.txt", "a", encoding="utf-8") as f:
        f.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | {msg}\n")

def safe_get(url, max_retries=3, timeout=10):
    """Performs an HTTP GET request with retries and exponential backoff."""
    for i in range(max_retries):
        try:
            response = requests.get(url, headers=HEADERS, timeout=timeout)
            if response.status_code == 200:
                return response
            else:
                log(f"Non-200 status {response.status_code} for URL: {url}")
        except Exception as e:
            log(f"Request error: {e} (try {i+1}) for URL: {url}")
        time.sleep(2 ** i)
    return None

# =========================
# Content Cleaning Functions
# =========================

DISCLAIMER_CLASS_SELECTORS = (
    ".disclaimer, .disclaimerText, .articleDisclaimer, .disclaimer-box, .story-disclaimer, .tag_wrap, .commenting-plugin"
)

DISCLAIMER_REGEXES = [
    r"(?i)^\s*disclaimer\b.*",
    r"(?i)^\s*the views (and|&)?\s*recommendations\b.*",
    r"(?i)^\W*copyright\s*©.*thg\s*publishing\b.*",
    r"(?i)^\s*this story was auto-generated\b.*",
]

BL_BOILERPLATE_REGEXES = [
    r"(?i)^\W*know\s*more\s*about\s*our\s*data\s*security\b.*",
    r"(?i)^\W*catch\s+all\s+the\s+business\s+news.*$",
    r"(?i)^\W*comments\s+have\s+to\s+be\s+in\s+english\b.*",
    r"(?i)^\W*we\s+have\s+migrated\s+to\s+a\s+new\s+commenting\s+platform\b.*",
    r"(?i)^\W*terms\s+&\s+conditions\s*\|\s*institutional\s+subscriber.*",
    r"^\s*(\+|-)?\s*\d{1,4}(,\d{3})?(\.\d{2})?",
    r"(?i)^\s*(get|connect)\s+with\s+us\s*$",
    r"(?i)^\s*to\s+enjoy\s+additional\s+benefits\s*$",
    r"(?i)^\s*get\s+businessline\s+apps\s+on\s*$",
    r"^\s*\| Photo Credit\s*:",
    r"(?i)^\s*istock\.com\s*$",
]

def drop_disclaimer_nodes(soup: BeautifulSoup) -> None:
    """Removes HTML nodes commonly containing disclaimers, ads, or comment sections."""
    for el in soup.select(DISCLAIMER_CLASS_SELECTORS):
        el.decompose()
    for tag in soup.find_all(["p", "div", "span", "li"], string=re.compile(r"^\s*Disclaimer\b", re.I)):
        try:
            tag.decompose()
        except Exception:
            pass

def strip_lines_by_regexes(text: str, regex_list) -> str:
    """Strips lines from text if they match any of the provided regexes."""
    if not text:
        return text
    lines = [ln.strip() for ln in text.split("\n")]
    kept = []
    for ln in lines:
        if not ln:
            continue
        if any(re.search(rx, ln) for rx in regex_list):
            continue
        kept.append(ln)
    out = "\n".join(kept)
    out = re.sub(r"\n{3,}", "\n\n", out).strip()
    return out

def strip_disclaimer_lines(text: str) -> str:
    return strip_lines_by_regexes(text, DISCLAIMER_REGEXES)

def strip_bl_boilerplate(text: str) -> str:
    return strip_lines_by_regexes(text, BL_BOILERPLATE_REGEXES)

# =========================
# The Hindu Business Line Specific Logic
# =========================

def extract_bl_article_id(url):
    """
    Extracts the numerical article ID from the URL (e.g., 70108651) 
    or falls back to MD5 hash if no number is found.
    """
    match = re.search(r'article(\d+)\.ece', url)
    if match:
        return match.group(1) 
    
    return hashlib.md5(url.encode()).hexdigest()

def clean_headline(headline):
    """
    Cleans headline by removing category labels and timestamps that may be included.
    Examples:
    - "Markets10:59 | Nov 17, 2025Boom in IPO..." -> "Boom in IPO..."
    - "Personal Finance11:01 | Nov 17, 2025Working couple..." -> "Working couple..."
    - "Commodities12:32 | Nov 17, 2025Glut-haunted..." -> "Glut-haunted..."
    - "Gold & Silver12:59 | Nov 17, 2025Gold, silver..." -> "Gold, silver..."
    """
    if not headline:
        return headline
    
    # Comprehensive list of categories (including new ones found)
    categories = [
        "Markets", "Stocks", "News", "Companies", "Economy", "Personal Finance",
        "Agri Business", "Education", "National", "Commodity Calls", "Commodities",
        "Info-tech", "Money & Banking", "Gold & Silver", "World", "Opinion",
        "Portfolio", "Technical Analysis", "Pulse"
    ]
    
    # Escape special regex characters in category names and join with |
    categories_pattern = "|".join(re.escape(cat) for cat in categories)
    
    # Pattern to match: CategoryName + Time (HH:MM | Mon DD, YYYY) + Headline
    # Handle both cases: with/without spaces between category, time, and date
    # This regex matches: CategoryName + HH:MM | Mon DD, YYYY (with optional spaces)
    headline = re.sub(
        rf'^({categories_pattern})\s*\d{{1,2}}:\d{{2}}\s*\|\s*[A-Za-z]+\s+\d{{1,2}},\s*\d{{4}}\s*',
        '',
        headline,
        flags=re.IGNORECASE
    )
    
    # Also handle cases where there's no space between category and time (e.g., "Markets10:59")
    headline = re.sub(
        rf'^({categories_pattern})\d{{1,2}}:\d{{2}}\s*\|\s*[A-Za-z]+\s+\d{{1,2}},\s*\d{{4}}\s*',
        '',
        headline,
        flags=re.IGNORECASE
    )
    
    # Remove any remaining timestamp patterns at the start: "HH:MM | Mon DD, YYYY"
    headline = re.sub(
        r'^\d{1,2}:\d{2}\s*\|\s*[A-Za-z]+\s+\d{1,2},\s*\d{4}\s*',
        '',
        headline,
        flags=re.IGNORECASE
    )
    
    return headline.strip()

def fetch_bl_headlines(max_articles=10):
    """Fetches article headlines and URLs from The Hindu Business Line Latest News page."""
    print(f"Attempting to fetch {max_articles} headlines from: {BL_LATEST_NEWS_URL}")
    try:
        response = safe_get(BL_LATEST_NEWS_URL)
        if not response:
            log("❌ Failed to fetch BL latest news page.")
            return []

        soup = BeautifulSoup(response.text, "html.parser")
        articles, seen_links = [], set()

        # Try to find article containers first (more structured approach)
        # Look for common article patterns: article tags, divs with article classes, list items
        article_containers = (
            soup.find_all("article") +
            soup.find_all("div", class_=re.compile(r"article|story|news|item", re.I)) +
            soup.find_all("li", class_=re.compile(r"article|story|news|item", re.I))
        )
        
        # If we found containers, extract from them
        if article_containers:
            for container in article_containers:
                if len(articles) >= max_articles:
                    break
                    
                # Find link in container
                link_tag = container.find("a", href=True)
                if not link_tag:
                    continue
                    
                link = link_tag["href"]
                if not link.startswith("http"):
                    link = "https://www.thehindubusinessline.com" + link

                # Check if it's a valid article link
                # Accept any article URL ending with .ece from thehindubusinessline.com
                # Exclude non-article pages (homepage, category listings, etc.)
                is_valid_article = (
                    link.endswith(".ece")
                    and "thehindubusinessline.com" in link
                    and link not in seen_links
                    and "/latest-news/" not in link  # Exclude the listing page itself
                    and not link.endswith("/latest-news/")
                )
                
                if is_valid_article:
                    title = link_tag.get_text(strip=True)
                    # Also try to find title in h1, h2, h3, or title attribute
                    if not title or len(title) < 20:
                        title_elem = container.find(["h1", "h2", "h3", "h4"], class_=re.compile(r"title|headline", re.I))
                        if title_elem:
                            title = title_elem.get_text(strip=True)
                    
                    # Clean the headline to remove category and timestamp prefixes
                    title = clean_headline(title)
                    
                    if title and len(title) > 20 and not title.lower().startswith(('read', 'click', 'more', 'view')):
                        seen_links.add(link)
                        articles.append({"headline": title, "url": link})
        
        # Fallback: if we didn't find enough articles via containers, use the original method
        if len(articles) < max_articles:
            all_links = soup.find_all("a", href=True)
            
            for a_tag in all_links:
                if len(articles) >= max_articles:
                    break
                    
                link = a_tag["href"]
                if not link.startswith("http"):
                    link = "https://www.thehindubusinessline.com" + link

                title = a_tag.get_text(strip=True)
                
                # Clean the headline to remove category and timestamp prefixes
                title = clean_headline(title)

                # Updated filter: accept any article ending with .ece from thehindubusinessline.com
                # This will catch articles from ALL sections, not just the listed ones
                is_valid_article = (
                    link.endswith(".ece")
                    and "thehindubusinessline.com" in link
                    and link not in seen_links
                    and "/latest-news/" not in link  # Exclude the listing page itself
                    and not link.endswith("/latest-news/")
                )
                
                if is_valid_article:
                    if title and len(title) > 20 and not title.lower().startswith(('read', 'click', 'more', 'view', 'subscribe')):
                        seen_links.add(link)
                        articles.append({"headline": title, "url": link})
        
        return articles
    except Exception as e:
        log(f"⚠️ fetch_bl_headlines error: {e}")
        return []

def fetch_full_bl_article(url):
    """Fetches the full content and published time for a Business Line article."""
    
    # Default to current time, this will be overwritten if data is found
    published_time = datetime.now().strftime(TARGET_TIME_FORMAT)
    
    try:
        response = safe_get(url)
        if not response:
            return None, None

        soup = BeautifulSoup(response.text, "html.parser")

        # 1. Content Extraction & Cleaning
        drop_disclaimer_nodes(soup)
        content = ""
        container = soup.find("div", class_="artbody")
        if not container:
            container = soup.find("div", class_="article-content")
        if container:
            content = container.get_text("\n", strip=True) 
        if len(content) < 50:
            paragraphs = soup.find_all("p")
            content = "\n".join(p.get_text(" ", strip=True) for p in paragraphs if p.get_text(strip=True))

        if len(content) < 50:
            return None, None

        content = strip_disclaimer_lines(content)
        content = strip_bl_boilerplate(content) 

        start_marker_match = re.search(r'S\s*tock Market today', content, flags=re.IGNORECASE)
        if start_marker_match:
            content = content[start_marker_match.start():]
            content = re.sub(r'S\s*tock Market today.*?for \d{1,2}th\s+\w+\s+\d{4}', '', content, flags=re.DOTALL | re.IGNORECASE).strip()
            content = re.sub(r"\n{3,}", "\n\n", content).strip()


        # 4. Extract Published time (Final Logic Block)
        
        # --- PRIORITY 1: Search the VISIBLE text in the RAW HTML FIRST (Matches what users see, IST time) ---
        # Updated regex to match: "Updated - November 13, 2025 at 08:34 PM"
        raw_time_match = re.search(
            r'(?:Updated|Published on|Published)\s*[-—:]?\s*([A-Za-z]+\s+\d{1,2},\s*\d{4})\s*(?:at\s*(\d{1,2}:\d{2})\s*(AM|PM|am|pm))?',
            response.text, 
            flags=re.IGNORECASE
        )
        
        if raw_time_match:
            date_part = raw_time_match.group(1).strip()
            time_part = raw_time_match.group(2)
            ampm_part = raw_time_match.group(3)
            
            try:
                if time_part and ampm_part:
                    # Found actual time in visible text - use it (this is what users see, likely IST)
                    date_time_str = f"{date_part} {time_part} {ampm_part.upper()}"
                    dt_obj = datetime.strptime(date_time_str, '%B %d, %Y %I:%M %p')
                    published_time = dt_obj.strftime(TARGET_TIME_FORMAT)
                    return content, published_time
                else:
                    # Only date found - check nearby text for time
                    match_pos = raw_time_match.end()
                    nearby_text = response.text[max(0, match_pos-50):match_pos+200]
                    time_nearby = re.search(r'(\d{1,2}:\d{2})\s*(AM|PM|am|pm)', nearby_text, flags=re.IGNORECASE)
                    if time_nearby:
                        time_str = time_nearby.group(1)
                        ampm_str = time_nearby.group(2).upper()
                        date_time_str = f"{date_part} {time_str} {ampm_str}"
                        dt_obj = datetime.strptime(date_time_str, '%B %d, %Y %I:%M %p')
                        published_time = dt_obj.strftime(TARGET_TIME_FORMAT)
                        return content, published_time
            except Exception as e:
                log(f"Visible text time parse failed for {url}: {e}")
        
        # --- PRIORITY 2: Fallback to Metadata Tags (if visible text doesn't have time) ---
        meta_pub = soup.find("meta", attrs={"property": "article:published_time"})
        if meta_pub and meta_pub.get("content"):
            try:
                meta_content = meta_pub["content"].strip()
                # Convert UTC (Z) to IST (UTC+5:30)
                if meta_content.endswith('Z'):
                    meta_content = meta_content[:-1] + '+00:00'
                    dt_obj = datetime.fromisoformat(meta_content)
                    # Add 5 hours 30 minutes to convert UTC to IST
                    dt_obj = dt_obj + timedelta(hours=5, minutes=30)
                    published_time = dt_obj.strftime(TARGET_TIME_FORMAT)
                    return content, published_time
                else:
                    dt_obj = datetime.fromisoformat(meta_content.replace('Z', '+00:00'))
                    published_time = dt_obj.strftime(TARGET_TIME_FORMAT)
                    return content, published_time
            except Exception as e:
                log(f"Meta tag parse failed for {url}: {e}")
        
        # Try alternative meta tag
        meta_pub_alt = soup.find("meta", attrs={"name": "publish-date"})
        if meta_pub_alt and meta_pub_alt.get("content"):
            try:
                meta_content = meta_pub_alt["content"].strip()
                if meta_content.endswith('Z'):
                    meta_content = meta_content[:-1] + '+00:00'
                    dt_obj = datetime.fromisoformat(meta_content)
                    dt_obj = dt_obj + timedelta(hours=5, minutes=30)  # Convert to IST
                    published_time = dt_obj.strftime(TARGET_TIME_FORMAT)
                    return content, published_time
                else:
                    dt_obj = datetime.fromisoformat(meta_content.replace('Z', '+00:00'))
                    published_time = dt_obj.strftime(TARGET_TIME_FORMAT)
                    return content, published_time
            except Exception as e:
                log(f"Alternative meta tag parse failed for {url}: {e}")
        
        # --- PRIORITY 3: Last resort - use date only if found ---
        if raw_time_match:
            date_part = raw_time_match.group(1).strip()
            try:
                date_time_str = f"{date_part} 12:00 AM"
                dt_obj = datetime.strptime(date_time_str, '%B %d, %Y %I:%M %p')
                published_time = dt_obj.strftime(TARGET_TIME_FORMAT)
            except Exception as e:
                log(f"Date-only parse failed for {url}: {e}")
                
        # If all else failed, the default (current time) is returned
        return content, published_time

    except Exception as e:
        log(f"⚠️ Error fetching BL article: {url} | {e}")
        return None, None

# =========================
# Data Management Functions
# (Unchanged since they are correct)
# =========================

def save_articles_to_json(articles_data):
    """Saves new articles to a JSON file, deduplicating against existing entries."""
    os.makedirs("1_data/raw_articles", exist_ok=True)
    filename = "1_data/raw_articles/hindubusinessline_latest.json"

    existing_urls = set()
    existing_article_ids = set()
    existing_data = []

    if os.path.exists(filename):
        with open(filename, "r", encoding="utf-8") as f:
            try:
                existing_data = json.load(f)
                existing_urls = {item.get("url") for item in existing_data}
                existing_article_ids = {item.get("article_id") for item in existing_data}
            except Exception:
                log(f"⚠️ Error loading existing JSON file: {filename}. Starting fresh.")
                existing_data = []

    new_articles = [
        a for a in articles_data
        if a["url"] not in existing_urls and a["article_id"] not in existing_article_ids
    ]

    if not new_articles:
        print("\n🟡 No new Hindu Business Line articles to append (URL/ID deduplication).")
        return []

    all_data = existing_data + new_articles
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(all_data, f, indent=2, ensure_ascii=False)
    print(f"\n💾 JSON updated: {filename} ({len(new_articles)} new)")

    print("\n✅ Newly added Hindu Business Line articles:")
    for art in new_articles:
        print(f"- {art['article_id']}: {art['headline']} | Scraped at: {art['scraped_at']} | URL: {art['url']}")
    return new_articles

def fetch_and_save_articles(max_articles=10):
    """Main execution function to orchestrate the scraping process."""
    print("📡 Starting Hindu Business Line Latest News Scraper...")
    articles = fetch_bl_headlines(max_articles=max_articles)
    
    if articles:
        print(f"\n🔍 Found {len(articles)} potential articles in the feed.")
        for idx, art in enumerate(articles):
            print(f"   [{idx+1}/{len(articles)}] {art['headline']}")
        print("-" * 50)
    
    articles = list(reversed(articles))
    articles_data = []

    if not articles:
        print("❌ No articles found to process.")
        return

    print(f"Starting content fetch for {len(articles)} articles...")
    for i, article in enumerate(articles, 1):
        print(f"\n🔹 Processing Article {i}/{len(articles)}")
        print(f"📰 {article['headline']}")
        print(f"🔗 {article['url']}")

        time.sleep(1)

        content, published_time = fetch_full_bl_article(article["url"])
        if content:
            article_id = extract_bl_article_id(article["url"])
            preview = re.sub(r"\s{2,}", " ", content.replace("\n", " ")).strip()
            print(f"🆔 Article ID: {article_id}")
            print(f"🕒 Published: {published_time}")
            print(f"📄 Preview: {preview[:100]}...\n")

            articles_data.append({
                "article_id": article_id,
                "headline": article["headline"],
                "content": content,
                "url": article["url"],
                "published_time": published_time,
                "scraped_at": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                "source": "The Hindu Business Line"
            })
        else:
            log(f"❌ Could not extract full BL article content: {article['url']}")
            print(f"❌ Could not extract content.")

    if articles_data:
        save_articles_to_json(articles_data)
    
    print("\n\n--- Scraper Finished ---")

if __name__ == "__main__":
    fetch_and_save_articles(max_articles=10)