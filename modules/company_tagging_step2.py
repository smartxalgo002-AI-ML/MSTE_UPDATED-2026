import pandas as pd
import json
import os
import re

from config import (
    MERGED_NEWS_PATH,
    MAPPING_CSV_PATH,
    TAGGED_OUTPUT_PATH,
    TAGGED_RECENT_PATH
)

# Minimum keyword length to use word boundary matching
MIN_KEYWORD_LENGTH = 4

# Generic terms that should NEVER be tagged alone (too ambiguous)
GENERIC_KEYWORDS = {
    "power", "oil", "sun", "bank", "market", "sector", "gas", "energy",
    "steel", "auto", "finance", "pharma", "tech", "infra", "capital",
    "india", "indian", "national", "state", "united", "global", "world",
    "retail", "fashion", "trade", "export", "import", "growth", "value", "focus", "dollar", "rain", "wealth",
}

# Negative context keywords: If these words appear, do NOT tag the company
# This prevents "Campus Activewear" from being tagged in news about "Hansraj College Campus"
NEGATIVE_CONTEXT_KEYWORDS = {
    "campus": [
        "college", "university", "school", "student", "education", "principal", 
        "wedding", "protest", "politics", "abvp", "sfi", "exam", "semester", 
        "faculty", "admission", "hostel", "canteen"
    ]
}

# Exclusion patterns: parent keyword -> subsidiary suffixes (skip parent if subsidiary follows)
KEYWORD_EXCLUSIONS = {
    "tiger": ["global", "brands"],
    "reliance": ["retail", "consumer", "jio", "power", "infra", "capital", "nippon"],
    "hdfc": ["bank", "amc", "life", "ergo", "sky"],
    "icici": ["bank", "prudential", "lombard", "securities", "direct"],
    "tata": ["motors", "steel", "power", "chemicals", "consumer", "communications", "elxsi", "technologies"],
    "bajaj": ["finance", "finserv", "auto", "holdings", "electricals"],
    "kotak": ["bank", "mahindra"],
    "axis": ["bank"],
    "bharti": ["airtel", "hexacom"],
    "adani": ["ports", "enterprises", "green", "power", "transmission", "wilmar", "total"],
    "aditya birla": ["capital", "fashion", "sun life"],
    "mahindra": ["mahindra", "finance", "holidays", "lifespace", "logistics"],
    "sun": ["pharma", "tv"],
    "hero": ["motocorp", "fincorp"],
    "maruti": ["suzuki"],
    "larsen": ["toubro"],
    "state bank": ["india"],
    "punjab": ["national", "sind"],
    "bank of": ["baroda", "india", "maharashtra"],
    "indian": ["oil", "bank", "hotels", "railway"],
    "power": ["grid", "finance"],
    "oil": ["india", "natural"],
    "hindustan": ["unilever", "petroleum", "zinc", "aeronautics", "copper"],
    "bharat": ["petroleum", "electronics", "forge", "heavy"],
}

# Skip headlines that are clearly macro/sector/analyst news
SKIP_HEADLINE_PATTERNS = [
    r"^union budget", r"^budget 20", r"^stocks to buy", r"^stocks to watch",
    r"^q[1-4] results:", r"^q[1-4] earnings:", r"^market update", r"^sector update",
    r"^industry leaders", r"^experts say", r"^analysts", r"^brokerages",
    r"^rbi ", r"^sebi ", r"^government ", r"^ministry ", r"^supreme court",
    r"^sensex", r"^nifty", r"^markets ", r"^stock market",
    r"top \d+ stocks", r"\d+ stocks to", r"best stocks", r"multibagger",
]

# Business/financial action keywords that indicate company-specific news
BUSINESS_ACTION_KEYWORDS = [
    "reports", "posts", "announces", "launches", "acquires", "buys", "sells",
    "invests", "raises", "cuts", "hikes", "profit", "revenue", "earnings",
    "dividend", "share", "stock", "ipo", "merger", "acquisition", "deal",
    "partnership", "agreement", "contract", "wins", "loses", "expands",
    "opens", "closes", "shuts", "layoffs", "hires", "appoints", "resigns",
    "results", "quarterly", "annual", "fy", "q1", "q2", "q3", "q4",
    "crore", "lakh", "billion", "million", "rs", "inr", "usd",
    "growth", "decline", "surge", "jumps", "falls", "drops", "rises",
    "beats", "misses", "exceeds", "guidance", "outlook", "forecast",
    "rating", "upgrade", "downgrade", "target", "buy", "sell", "hold",
]


def tag_and_save_articles():
    mapping_df = pd.read_csv(MAPPING_CSV_PATH)
    mapping_df["Keyword"] = mapping_df["Keyword"].fillna("").astype(str)

    # Build keyword -> company mapping, sorted by keyword length (longest first)
    keyword_company_pairs = []
    for _, row in mapping_df.iterrows():
        keywords = [kw.strip().lower() for kw in row["Keyword"].split(",") if kw.strip()]
        company_info = {
            "CompanyName": row["CompanyName"],
            "Symbol": row["Symbol"],
            "Sector": row.get("Sector", ""),
            "Index": row.get("Index", "")
        }
        for kw in keywords:
            if len(kw) >= MIN_KEYWORD_LENGTH:
                keyword_company_pairs.append((kw, company_info))
    
    keyword_company_pairs.sort(key=lambda x: len(x[0]), reverse=True)

    def is_generic_keyword(keyword: str) -> bool:
        """Check if keyword is too generic to tag alone."""
        return keyword.lower() in GENERIC_KEYWORDS

    def is_excluded_by_context(keyword: str, text: str) -> bool:
        """Skip parent keyword if subsidiary suffix follows."""
        keyword_lower = keyword.lower()
        for base_kw, exclusions in KEYWORD_EXCLUSIONS.items():
            if keyword_lower == base_kw or keyword_lower.startswith(base_kw + " "):
                for excl in exclusions:
                    excl_pattern = r"\b" + re.escape(keyword_lower) + r"\s+" + re.escape(excl) + r"\b"
                    if re.search(excl_pattern, text):
                        return True
        return False

    def should_skip_headline(headline: str) -> bool:
        """Skip macro/sector/analyst headlines."""
        text = headline.lower()
        for pattern in SKIP_HEADLINE_PATTERNS:
            if re.search(pattern, text):
                return True
        return False

        return False

    def has_negative_context(keyword: str, text: str) -> bool:
        """Check if text contains negative context words for this keyword."""
        keyword_lower = keyword.lower()
        if keyword_lower in NEGATIVE_CONTEXT_KEYWORDS:
            text_lower = text.lower()
            # aggressive check: any of the negative words present?
            for neg_word in NEGATIVE_CONTEXT_KEYWORDS[keyword_lower]:
                if f" {neg_word} " in f" {text_lower} ":  # basic word boundary check
                    return True
        return False

    def has_business_action(text: str) -> bool:
        """Check if text contains business/financial action keywords."""
        text_lower = text.lower()
        return any(action in text_lower for action in BUSINESS_ACTION_KEYWORDS)

    def is_full_company_name(keyword: str, company_name: str) -> bool:
        """Check if keyword is a full company name or clear alias (not just a short generic term)."""
        kw_lower = keyword.lower()
        name_lower = company_name.lower()
        
        # Full name match or substantial part of name
        if kw_lower in name_lower or name_lower in kw_lower:
            return len(kw_lower) >= 8  # Reasonably long match
        
        # Stock symbol (usually uppercase, 3-15 chars)
        if keyword.isupper() and 3 <= len(keyword) <= 15:
            return True
        
        # Multi-word keyword is more specific
        if " " in keyword and len(keyword) >= 10:
            return True
        
        return False

    def keyword_in_content(keyword: str, content: str) -> bool:
        """Check if keyword appears in content (confirms headline)."""
        if not content:
            return False
        pattern = r"\b" + re.escape(keyword.lower()) + r"\b"
        return bool(re.search(pattern, content.lower()))

    def tag_companies(headline: str, content: str = ""):
        """
        Tag companies with strict confidence rules:
        - Skip if generic/macro news
        - Require at least 2 confidence signals
        - Return [] if confidence < 90%
        """
        if not headline:
            return []
        
        if should_skip_headline(headline):
            return []
        
        tagged_companies = []
        text = headline.lower()
        full_text = (headline + " " + content).lower()
        seen_symbols = set()
        matched_keywords = set()
        
        for kw, company_info in keyword_company_pairs:
            symbol = company_info["Symbol"]
            if symbol in seen_symbols:
                continue
            
            pattern = r"\b" + re.escape(kw) + r"\b"
            match = re.search(pattern, text)
            
            if not match:
                continue
            
            # Skip if excluded by context (e.g., "reliance retail" shouldn't match "reliance")
            if is_excluded_by_context(kw, text):
                continue
                
            # Skip if negative context is present (e.g., "college campus" shouldn't match "Campus")
            if has_negative_context(kw, full_text):
                continue
            
            # Skip generic keywords unless they're part of a longer match
            if is_generic_keyword(kw):
                continue
            
            # CONFIDENCE SCORING: Need at least 2 of these conditions
            confidence_signals = 0
            
            # Signal 1: Full company name or clear alias (weight 2 — passes threshold alone)
            if is_full_company_name(kw, company_info["CompanyName"]):
                confidence_signals += 2
            
            # Signal 2: Business/financial action in headline
            if has_business_action(headline):
                confidence_signals += 1
            
            # Signal 3: Keyword confirmed in content
            if keyword_in_content(kw, content):
                confidence_signals += 1
            
            # Signal 4: Stock symbol match (very reliable)
            if kw.upper() == symbol:
                confidence_signals += 3  # Triple weight for exact symbol match
            
            # Require at least 2 confidence signals
            if confidence_signals < 2:
                continue
            
            # Skip overlapping shorter keywords
            match_start, match_end = match.start(), match.end()
            skip = False
            for prev_kw in matched_keywords:
                if kw in prev_kw or prev_kw in kw:
                    prev_pattern = r"\b" + re.escape(prev_kw) + r"\b"
                    prev_match = re.search(prev_pattern, text)
                    if prev_match:
                        if (match_start >= prev_match.start() and match_start < prev_match.end()) or \
                           (match_end > prev_match.start() and match_end <= prev_match.end()):
                            skip = True
                            break
            
            if skip:
                continue
            
            tagged_companies.append(company_info.copy())
            seen_symbols.add(symbol)
            matched_keywords.add(kw)
        
        return tagged_companies

    # Read from merged_news.json (refreshed each run)
    if not os.path.exists(MERGED_NEWS_PATH):
        print(f"No articles found at {MERGED_NEWS_PATH}")
        return []

    with open(MERGED_NEWS_PATH, "r", encoding="utf-8") as f:
        articles = json.load(f)

    if not articles:
        print("No articles in merged_news.json")
        os.makedirs(os.path.dirname(TAGGED_RECENT_PATH), exist_ok=True)
        with open(TAGGED_RECENT_PATH, "w", encoding="utf-8") as f_json:
            json.dump([], f_json, ensure_ascii=False, indent=2)
        return []

    # Load existing tagged data for deduplication using (article_id, symbol) key
    existing_data = []
    existing_keys = set()  # Composite key: (article_id, symbol)
    if os.path.exists(TAGGED_OUTPUT_PATH):
        with open(TAGGED_OUTPUT_PATH, "r", encoding="utf-8") as f_old:
            try:
                existing_data = json.load(f_old)
                existing_keys = {(item.get("article_id"), item.get("Symbol")) for item in existing_data}
            except Exception:
                existing_data = []

    tagged_rows = []
    seen_in_run = set()  # Same-run dedup: (article_id, symbol)
    
    for article in articles:
        article_id = article.get("article_id", "")
        headline = article.get("headline", "")
        content = article.get("content", "")
        tagged = tag_companies(headline, content)
        
        if tagged:
            for company in tagged:
                symbol = company["Symbol"]
                key = (article_id, symbol)
                
                # Skip if already in cumulative file OR already processed this run
                if key in existing_keys or key in seen_in_run:
                    continue
                
                tagged_rows.append({
                    "article_id": article_id,
                    "headline": headline,
                    "content": article.get("content", ""),
                    "source": article.get("source", ""),
                    "published_time": article.get("published_time", ""),
                    "scraped_at": article.get("scraped_at", ""),
                    "CompanyName": company["CompanyName"],
                    "Symbol": symbol,
                    "Sector": company["Sector"],
                    "Index": company["Index"],
                    "url": article.get("url", "")
                })
                seen_in_run.add(key)

    if not tagged_rows:
        print("No new companies tagged in this run.")
        os.makedirs(os.path.dirname(TAGGED_RECENT_PATH), exist_ok=True)
        with open(TAGGED_RECENT_PATH, "w", encoding="utf-8") as f_json:
            json.dump([], f_json, ensure_ascii=False, indent=2)
        return []

    # Append to all_tagged_news.json
    all_data = existing_data + tagged_rows
    os.makedirs(os.path.dirname(TAGGED_OUTPUT_PATH), exist_ok=True)
    with open(TAGGED_OUTPUT_PATH, "w", encoding="utf-8") as f_json:
        json.dump(all_data, f_json, ensure_ascii=False, indent=2)
    print(f"Updated cumulative tagged file: +{len(tagged_rows)} rows (total: {len(all_data)})")

    # Save recent tagged (current run only)
    os.makedirs(os.path.dirname(TAGGED_RECENT_PATH), exist_ok=True)
    with open(TAGGED_RECENT_PATH, "w", encoding="utf-8") as f_recent:
        json.dump(tagged_rows, f_recent, ensure_ascii=False, indent=2)
    print(f"Recent tagged file: {len(tagged_rows)} rows")

    return tagged_rows


def run_company_tagging():
    """Entry point for main.py"""
    return tag_and_save_articles()


if __name__ == "__main__":
    tag_and_save_articles()
