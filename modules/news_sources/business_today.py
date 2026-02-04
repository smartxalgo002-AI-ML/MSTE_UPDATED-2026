# businesstoday_root_scraper.py
import requests, os, json, re, time, hashlib
from bs4 import BeautifulSoup
from datetime import datetime

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

def safe_get(url, max_retries=3, timeout=12):
    for i in range(max_retries):
        try:
            r = requests.get(url, headers=HEADERS, timeout=timeout)
            if r.status_code == 200:
                return r
            else:
                print(f"Warning: {url} returned {r.status_code}")
        except Exception as e:
            print(f"Request error ({i+1}/{max_retries}) for {url}: {e}")
        time.sleep(1 + 2*i)
    return None

def extract_article_id(url):
    m = re.search(r'(\d{6,})', url)
    return m.group(1) if m else hashlib.md5(url.encode()).hexdigest()

# remove small boilerplate nodes if present
DISCLAIMER_SELECTORS = (".disclaimer", ".story-disclaimer", ".disclaimer-box")
def drop_boilerplate(soup):
    for sel in DISCLAIMER_SELECTORS:
        for el in soup.select(sel):
            try: el.decompose()
            except: pass

# --- stricter section skip rules ---
SECTION_PREFIXES = [
    r'/markets/?',
    r'/bt-tv/?',
    r'/magazine/?',
    r'/visualstories',
    r'/mutual-funds',
    r'/india-today',
    r'/btbazaar',
    r'/tech-today',
    r'/money-today',
    r'/industry',
    r'/events',
    r'/bt500',
    r'/bt-reels',
    r'/news/?',
    r'/weather',
    r'/education',
    r'/election',
    r'/pms-today'
]

def looks_like_high_level_section(url):
    """
    Return True if url matches a known section prefix *and* it does NOT contain
    a strong article signal (.html or a long numeric id).
    """
    # strong article signals
    has_html = '.html' in url.lower()
    has_digits = bool(re.search(r'\d{5,}', url))
    for pref in SECTION_PREFIXES:
        if re.search(pref, url, re.I):
            # if it's a section prefix and lacks article signals -> treat as section
            if not (has_html or has_digits or '/story/' in url or '/article/' in url):
                return True
    return False

def is_article_page(soup, content_text):
    """
    Return True if the page looks like a single article (not a listing).
    Heuristics:
      - meta article:published_time OR og:type == article (strong signal)
      - AND content length >= 300 chars and at least 2 paragraphs > 80 chars
    If no meta/og signals, require content_len >= 500 and >= 3 long paragraphs.
    """
    meta_pub = soup.find("meta", {"property": "article:published_time"}) or soup.find("meta", {"name": "publication_date"})
    og = soup.find("meta", {"property": "og:type"})
    og_article = og and og.get("content") and "article" in og.get("content").lower()

    paragraphs = [ln.strip() for ln in content_text.splitlines() if len(ln.strip()) > 80]
    long_par_count = len(paragraphs)
    content_len = len(content_text or "")

    if meta_pub or og_article:
        return content_len >= 300 and long_par_count >= 2

    return content_len >= 500 and long_par_count >= 3

# --- candidate collection (now stricter) ---
def collect_candidate_links(root_url="https://www.businesstoday.in/markets/stocks", max_links=20):
    print("Fetching index:", root_url)
    resp = safe_get(root_url)
    if not resp: return []
    soup = BeautifulSoup(resp.text, "html.parser")

    links = []
    seen = set()

    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if href.startswith("/"):
            link = "https://www.businesstoday.in" + href
        elif href.startswith("http"):
            link = href
        else:
            continue

        # skip obvious section/landing prefixes unless they have a clear article signal
        if looks_like_high_level_section(link):
            continue

        # avoid galleries/videos/tags
        if any(x in link for x in ["/photos/", "/photo-", "/gallery", "/videos/", "/video/", "/slideshow", "/amp/amp", "/tag/", "/tags/"]):
            continue

        # Require one of:
        #  - .html in URL
        #  - a long numeric id in URL
        #  - '/story/' or '/article/' in URL
        # Otherwise likely a section/landing page and will be skipped.
        if not ('.html' in link.lower() or re.search(r'\d{5,}', link) or '/story/' in link or '/article/' in link):
            # fallback: allow if anchor text is a strong headline AND link contains at least two path segments (avoid nav links)
            title_candidate = a.get_text(" ", strip=True)
            path_segments = [p for p in re.split(r'[/\?#]', link) if p]
            if not title_candidate or len(title_candidate) < 12 or len(path_segments) < 3:
                continue

        title = (a.get_text(" ", strip=True) or "").strip()
        if not title or len(title) < 12:
            parent = a.find_parent(["h1","h2","h3","h4"])
            if parent:
                title = parent.get_text(" ", strip=True)

        if not title or len(title) < 12:
            continue

        if link in seen:
            continue
        seen.add(link)
        links.append({"url": link, "headline": title})
        if len(links) >= max_links:
            break

    # fallback: crawl home page for article links (same stricter rules)
    if not links:
        home = safe_get("https://www.businesstoday.in")
        if home:
            s2 = BeautifulSoup(home.text, "html.parser")
            for a in s2.find_all("a", href=True):
                href = a["href"].strip()
                if href.startswith("/"):
                    link = "https://www.businesstoday.in" + href
                elif href.startswith("http"):
                    link = href
                else:
                    continue
                if looks_like_high_level_section(link):
                    continue
                if "businesstoday.in" in link and re.search(r'\d{5,}', link):
                    title = (a.get_text(" ", strip=True) or "")
                    if title and len(title) > 10 and link not in seen:
                        seen.add(link)
                        links.append({"url": link, "headline": title})
                        if len(links) >= max_links: break

    print(f"Found {len(links)} candidate links.")
    return links

# --- extraction with article-page verification ---
def extract_content_and_time(url):
    resp = safe_get(url)
    if not resp:
        return None, None
    soup = BeautifulSoup(resp.text, "html.parser")
    drop_boilerplate(soup)

    # Try common article containers (ordered)
    selectors = [
        'div[itemprop="articleBody"]',
        'article',
        'div.story-detail__content',
        'div.article-content',
        'div.articleText',
        'div#articleBody',
        'div#content',
        'div.content',
        'div.blog-content',
        'div.story-content'
    ]
    content = ""
    for sel in selectors:
        node = soup.select_one(sel)
        if node:
            ps = node.find_all("p")
            if ps:
                content = "\n".join(p.get_text(" ", strip=True) for p in ps if p.get_text(strip=True))
            else:
                content = node.get_text(" ", strip=True)
        if content and len(content) > 120:
            break

    # last-resort: aggregate long <p> tags from the page
    if not content or len(content) < 120:
        ps = soup.find_all("p")
        blocks = []
        for p in ps:
            t = p.get_text(" ", strip=True)
            if t and len(t) > 30:
                blocks.append(t)
        if blocks:
            content = "\n".join(blocks)

    if not content or len(content) < 80:
        return None, None

    # quick clean
    content = re.sub(r'\n{3,}', '\n\n', content).strip()
    content = "\n".join([ln for ln in content.splitlines() if not re.match(r'^\s*Disclaimer\b', ln, re.I)])

    # Final article detection: skip if page looks like a listing/section
    if not is_article_page(soup, content):
        return None, None

    # published time: meta tags, <time>, or visible 'Updated' text
    published = None
    meta = soup.find("meta", {"property": "article:published_time"}) or soup.find("meta", {"name": "publication_date"})
    if meta and meta.get("content"):
        published = meta["content"][:19].replace("T", " ")
    if not published:
        time_tag = soup.find("time")
        if time_tag and time_tag.get("datetime"):
            published = time_tag["datetime"][:19].replace("T", " ")
        elif time_tag:
            published = time_tag.get_text(" ", strip=True)

    if not published:
        # look for "Updated : Oct 18, 2025" style
        upd = soup.find(string=re.compile(r"Updated\s*[:\-]\s*\w+", re.I))
        if upd:
            published = upd.strip()
    if not published:
        # meta name pubdate or dc.date
        meta2 = soup.find("meta", {"name":"pubdate"}) or soup.find("meta", {"name":"PublishDate"}) or soup.find("meta", {"name":"DC.date.issued"})
        if meta2 and meta2.get("content"):
            published = meta2["content"]

    if not published:
        published = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    return content, published

def save_json(items, outpath="1_data/raw_articles/businesstoday_latest.json"):
    os.makedirs(os.path.dirname(outpath), exist_ok=True)
    existing = []
    existing_urls = set()
    existing_ids = set()
    if os.path.exists(outpath):
        try:
            with open(outpath, "r", encoding="utf-8") as f:
                existing = json.load(f)
                existing_urls = {it.get("url") for it in existing if it.get("url")}
                existing_ids = {it.get("article_id") for it in existing if it.get("article_id")}
        except Exception as e:
            print("Could not load existing file:", e)
            existing = []

    new = [it for it in items if it["url"] not in existing_urls and it["article_id"] not in existing_ids]
    if not new:
        print("No new articles to append.")
        return []

    combined = existing + new
    with open(outpath, "w", encoding="utf-8") as f:
        json.dump(combined, f, indent=2, ensure_ascii=False)
    print(f"Wrote {len(new)} new article(s) to {outpath}")
    for a in new:
        print(f"- {a['article_id']} | {a['headline'][:80]}")

    return new

def run(max_articles=12):
    candidates = collect_candidate_links(max_links=max_articles)
    if not candidates:
        print("No candidates found.")
        return
    results = []
    for c in candidates:
        print("\nProcessing:", c["url"])
        content, published = extract_content_and_time(c["url"])
        if not content:
            print(" -> Could not extract content, skipping.")
            continue
        aid = extract_article_id(c["url"])
        results.append({
            "article_id": aid,
            "headline": c["headline"],
            "content": content,
            "url": c["url"],
            "published_time": published,
            "scraped_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "source": "BusinessToday"
        })
    if results:
        save_json(results)
    else:
        print("No articles extracted.")

if __name__ == "__main__":
    run(max_articles=12)
