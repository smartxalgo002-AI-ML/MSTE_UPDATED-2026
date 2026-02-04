# modules/news_sources/cnbc_tv18.py
import os, re, json, time, hashlib, sys
from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse, urlunparse

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from dateutil import parser as date_parser


PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "../")
)

if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from config import (
    CNBC_RAW_NEWS_PATH as RAW_NEWS_PATH,
    CNBC_RECENT_NEWS_PATH as RECENT_NEWS_PATH,
    LOG_FILE,
    MAX_ARTICLES,
)

BASE_URL = "https://www.cnbctv18.com/latest-news/"
SCROLLS = 3

# ====== Logging ======
def log(msg: str):
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"{datetime.now()} | [CNBC-TV18] {msg}\n")
    print(f"[CNBC-TV18] {msg}")

# ====== Helpers ======
def normalize_url(url: str) -> str:
    p = urlparse(url)
    return urlunparse(p._replace(query="", fragment=""))

def get_article_id(url: str) -> str:
    u = normalize_url(url)
    m = re.search(r"(\d+)\.htm$", u)
    return m.group(1) if m else hashlib.md5(u.encode("utf-8")).hexdigest()

def is_valid_article(url: str) -> bool:
    if not url:
        return False
    u = normalize_url(url)
    return (
        u.startswith("https://www.cnbctv18.com/") and
        u.endswith(".htm") and
        "web-stories" not in u and
        "/live-" not in u and "/live/" not in u
    )

def ist_tz():
    return timezone(timedelta(hours=5, minutes=30))

def to_ist(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=ist_tz())
    return dt.astimezone(ist_tz())

def is_today_ist_dt(dt_ist: datetime) -> bool:
    return dt_ist.date() == datetime.now(ist_tz()).date()

def fmt_display(dt_ist: datetime) -> str:
    return dt_ist.strftime("%I:%M %p | %d %b %Y")

def load_json(path: str):
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            log(f"JSON load error: {e}")
    return []

def save_json(path: str, data: list):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ====== Selenium ======
def make_driver():
    opts = Options()
    opts.add_argument("--headless=new")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=opts)

def wait_for(driver, selector, by=By.CSS_SELECTOR, timeout=8):
    try:
        return WebDriverWait(driver, timeout).until(EC.presence_of_element_located((by, selector)))
    except:
        return None

def scroll_page(driver, pause=1.0, max_scrolls=SCROLLS):
    h = driver.execute_script("return document.body.scrollHeight")
    for _ in range(max_scrolls):
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(pause)
        nh = driver.execute_script("return document.body.scrollHeight")
        if nh == h:
            break
        h = nh

# ====== Scraping ======
def scrape_article(driver, url: str):
    try:
        driver.get(url)
        wait_for(driver, "h1")

        # Headline
        h1 = driver.find_elements(By.TAG_NAME, "h1")
        headline = h1[0].text.strip() if h1 else ""
        if not headline:
            return None

        # Content (prefer JSON-LD articleBody)
        content = ""
        for sc in driver.find_elements(By.XPATH, '//script[@type="application/ld+json"]'):
            try:
                data = json.loads(sc.get_attribute("innerHTML"))
                if isinstance(data, dict) and data.get("articleBody"):
                    content = str(data["articleBody"]).strip()
                    break
            except:
                pass
        if not content:
            paras = driver.find_elements(By.CSS_SELECTOR, "div.article__content p, article p")
            content = " ".join([p.text for p in paras if p.text.strip()])

        # Published time
        published_raw = None
        for mt in driver.find_elements(By.CSS_SELECTOR, 'meta[itemprop="datePublished"], meta[property="article:published_time"]'):
            c = mt.get_attribute("content")
            if c:
                published_raw = c
                break
        if not published_raw:
            tnodes = driver.find_elements(By.TAG_NAME, "time")
            if tnodes:
                published_raw = tnodes[0].get_attribute("datetime") or tnodes[0].text
        if not published_raw:
            return None

        try:
            dt = date_parser.parse(published_raw)
        except:
            return None

        dt_ist = to_ist(dt)
        if not is_today_ist_dt(dt_ist):
            return None  # only keep *today* items

        return {
            "article_id": get_article_id(url),
            "headline": headline,
            "content": content.strip(),
            "url": normalize_url(url),
            "published_time": fmt_display(dt_ist),   # 'HH:MM AM/PM | DD Mon YYYY'
            "scraped_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "source": "CNBC-TV18",
        }
    except Exception as e:
        log(f"Error scraping: {url} | {e}")
        return None

def fetch_latest_links(driver):
    driver.get(BASE_URL)
    wait_for(driver, "a")
    scroll_page(driver, pause=1.0, max_scrolls=SCROLLS)

    anchors = driver.find_elements(By.TAG_NAME, "a")
    links, seen = [], set()
    for a in anchors:
        try:
            href = a.get_attribute("href")
            if is_valid_article(href):
                u = normalize_url(href)
                if u not in seen:
                    links.append(u)
                    seen.add(u)
        except:
            pass
    return links

# ====== Persist (per-source RAW+RECENT with dedup) ======
def _save_recent(new_articles):
    os.makedirs(os.path.dirname(RECENT_NEWS_PATH), exist_ok=True)
    save_json(RECENT_NEWS_PATH, new_articles)
    log(f"🆕 Wrote {len(new_articles)} recent → {RECENT_NEWS_PATH}")

def _clear_recent():
    os.makedirs(os.path.dirname(RECENT_NEWS_PATH), exist_ok=True)
    save_json(RECENT_NEWS_PATH, [])
    log("🧹 Cleared recent file (cnbc_latest_recent.json).")

def save_articles_to_json(articles_data):
    os.makedirs(os.path.dirname(RAW_NEWS_PATH), exist_ok=True)
    existing = load_json(RAW_NEWS_PATH)
    existing_urls = {it.get("url") for it in existing}
    existing_ids  = {it.get("article_id") for it in existing}

    # Dedup rule: drop only if BOTH url AND article_id already exist
    new_articles = [
        a for a in articles_data
        if not (a["url"] in existing_urls and a["article_id"] in existing_ids)
    ]

    if not new_articles:
        log("🟡 No new CNBC-TV18 articles to append (dedup).")
        _clear_recent()
        return []

    all_data = existing + new_articles
    save_json(RAW_NEWS_PATH, all_data)
    log(f"💾 JSON updated: {RAW_NEWS_PATH} (+{len(new_articles)} new, total {len(all_data)})")

    _save_recent(new_articles)
    return new_articles

# ====== Public entrypoint (contract) ======
def fetch_and_save_articles(max_articles: int = MAX_ARTICLES):
    log("📡 Fetching CNBC-TV18 Latest News (today IST only)…")
    driver = make_driver()
    try:
        links = fetch_latest_links(driver)
        if not links:
            log("❌ No links found.")
            _clear_recent()
            return []

        batch = []
        for url in links:
            if len(batch) >= max_articles:
                break
            rec = scrape_article(driver, url)
            if rec:
                batch.append(rec)
            time.sleep(0.5)

        if not batch:
            log("ℹ️ No valid 'today' articles.")
            _clear_recent()
            return []

        # Oldest first for stable writes
        def parse_disp(disp: str) -> datetime:
            return datetime.strptime(disp, "%I:%M %p | %d %b %Y")
        batch.sort(key=lambda a: parse_disp(a["published_time"]))

        return save_articles_to_json(batch)
    finally:
        try: driver.quit()
        except: pass

if __name__ == "__main__":
    added = fetch_and_save_articles()
    print(f"✅ Added {len(added)} new CNBC-TV18 articles to RAW and RECENT.")

