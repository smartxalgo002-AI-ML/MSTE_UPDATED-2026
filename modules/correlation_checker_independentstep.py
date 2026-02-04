from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime, timedelta, time
from typing import List, Dict, Optional, Tuple

import pandas as pd
from zoneinfo import ZoneInfo

DEBUG = True
def dbg(msg: str):
    if DEBUG:
        print(f"[correlation_checker][DEBUG] {msg}")

MOD_DIR = Path(__file__).resolve().parent
ROOT = MOD_DIR.parent  # project root: sentiment-trade-engine/
OUT_DIR = ROOT / "output"
SIG_DIR = OUT_DIR / "signals"
CORR_DIR = OUT_DIR / "correlation"
CORR_DIR.mkdir(parents=True, exist_ok=True)

SIG_RECENT = SIG_DIR / "signals_recent.json"
SIG_FALLBACK = SIG_DIR / "signals.json"

DATA_OHLCV_ROOT = ROOT / "Data Fetch ohlcv"
MAP_CSV = ROOT / "CORRECT OHLCV TICK DATA" / "mapping_security_ids.csv"
OHLCV_BASE = DATA_OHLCV_ROOT / "data_ohlcv"

IST = ZoneInfo("Asia/Kolkata")
MARKET_OPEN = time(9, 15)
MARKET_CLOSE = time(15, 30)
HORIZON_MINUTES_DEFAULT = 60  # as per requirement

def _pick_col(df: pd.DataFrame, candidates: List[str]) -> Optional[str]:
    cl = {c.lower(): c for c in df.columns}
    for name in candidates:
        if name.lower() in cl:
            return cl[name.lower()]
    return None

def _load_mapping(map_csv: Path) -> Dict[str, str]:
    """
    Returns dict: SYMBOL (upper) -> CompanyName (as in mapping)
    Expected columns (case-insensitive): Symbol, CompanyName
    """
    if not map_csv.exists():
        raise FileNotFoundError(f"Mapping CSV not found: {map_csv}")
    df = pd.read_csv(map_csv)
    sym_col = _pick_col(df, ["Symbol", "SYMBOL", "Ticker", "Entity"])
    name_col = _pick_col(df, ["CompanyName", "Company Name", "Company", "Name"])
    if not sym_col or not name_col:
        raise ValueError(
            f"Mapping CSV must have 'Symbol' and 'CompanyName' columns (found: {list(df.columns)})"
        )
    mapping = {}
    for _, row in df.iterrows():
        sym = str(row[sym_col]).strip().upper()
        comp = str(row[name_col]).strip()
        if sym:
            mapping[sym] = comp
    dbg(f"Loaded mapping: {len(mapping)} symbols from {map_csv}")
    return mapping

def _normalize_name(s: str) -> str:
    """Loose normalization for matching folder names (ignore case, dots, extra spaces)."""
    return "".join(ch for ch in s.lower() if ch.isalnum() or ch.isspace()).strip()

def _resolve_company_folder(company_name: str) -> Optional[Path]:
    """
    Try to find the company folder under OHLCV_BASE, robust to minor punctuation differences.
    """
    if not OHLCV_BASE.exists():
        dbg(f"OHLCV_BASE does not exist: {OHLCV_BASE}")
        return None
    target_norm = _normalize_name(company_name)
    exact = OHLCV_BASE / company_name
    if exact.exists():
        return exact
    for p in OHLCV_BASE.iterdir():
        if p.is_dir() and _normalize_name(p.name) == target_norm:
            return p
    dbg(f"Could not resolve company folder for '{company_name}' under {OHLCV_BASE}")
    return None

def _find_csv_for_date(folder: Path, date_ist: datetime) -> Optional[Path]:
    """
    Files are named like: "<CompanyName> DD-MM-YYYY.csv"
    We'll match by ending with f" {DD-MM-YYYY}.csv" to avoid issues with company punctuation.
    """
    date_str = date_ist.strftime("%d-%m-%Y")
    if not folder or not folder.exists():
        return None
    for f in folder.glob("*.csv"):
        if f.name.endswith(f" {date_str}.csv"):
            return f
    dbg(f"No CSV found in {folder} for date {date_str}")
    return None

def _parse_ist_time_from_article(article: dict) -> Tuple[Optional[datetime], str]:
    """
    Parse published_time from news article.
    Handles multiple formats:
    - "January 23, 2026/ 15:53 IST"
    - "January 23, 2026 at 03:39 PM"
    - "03:56 PM | 23 Jan 2026"
    Floor to minute.
    Returns (dt_ist, source_str).
    """
    if "published_time" not in article or not article["published_time"]:
        return None, "none"
    
    raw = str(article["published_time"]).strip()
    
    # Try format: "2026-01-23 14:30:49" (ISO datetime format)
    try:
        dt = datetime.strptime(raw, "%Y-%m-%d %H:%M:%S")
        dt = dt.replace(tzinfo=IST, second=0, microsecond=0)
        return dt, "published_time"
    except Exception:
        pass
    
    # Try format: "January 23, 2026/ 15:53 IST" or "January 23, 2026/ 15:53"
    try:
        # Remove "IST" if present
        clean = raw.replace(" IST", "").strip()
        # Replace / with space
        clean = clean.replace("/", " ")
        dt = datetime.strptime(clean, "%B %d, %Y %H:%M")
        dt = dt.replace(tzinfo=IST, second=0, microsecond=0)
        return dt, "published_time"
    except Exception:
        pass
    
    # Try format: "January 23, 2026 at 03:39 PM"
    try:
        dt = datetime.strptime(raw, "%B %d, %Y at %I:%M %p")
        dt = dt.replace(tzinfo=IST, second=0, microsecond=0)
        return dt, "published_time"
    except Exception:
        pass
    
    # Try format: "03:56 PM | 23 Jan 2026"
    try:
        dt = datetime.strptime(raw, "%I:%M %p | %d %b %Y")
        dt = dt.replace(tzinfo=IST, second=0, microsecond=0)
        return dt, "published_time"
    except Exception:
        pass
    
    # Try ISO format as fallback
    try:
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        dt_utc = datetime.fromisoformat(raw)
        dt_ist = dt_utc.astimezone(IST).replace(second=0, microsecond=0)
        return dt_ist, "published_time"
    except Exception as e:
        dbg(f"Failed to parse published_time='{article.get('published_time')}' ({e})")
    
    return None, "none"

def _market_window_ok(t_ist: datetime, horizon_min: int) -> bool:
    if t_ist.tzinfo is None:
        return False
    if not (MARKET_OPEN <= t_ist.timetz().replace(tzinfo=None) <= MARKET_CLOSE):
        return False
    t2 = t_ist + timedelta(minutes=horizon_min)
    if not (MARKET_OPEN <= t2.timetz().replace(tzinfo=None) <= MARKET_CLOSE):
        return False
    return True

def _canonicalize_minute_bars(day_df: pd.DataFrame) -> pd.DataFrame:
    """
    Handle duplicate timestamps within same minute:
      - open = first
      - high = max
      - low  = min
      - close = last
      - volume = sum
      - hv/iv = last
    Assumes timestamps are in IST (naive or aware).
    """
    if day_df.empty:
        return day_df

    if "timestamp" not in day_df.columns:
        return pd.DataFrame()

    ts = pd.to_datetime(day_df["timestamp"])
    if ts.dt.tz is None:
        ts = ts.dt.tz_localize(IST)
    day_df = day_df.assign(_ts=ts).sort_values("_ts")
    minute = day_df["_ts"].dt.floor("T")

    agg = {
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
    }
    if "hv" in day_df.columns:
        agg["hv"] = "last"
    if "iv" in day_df.columns:
        agg["iv"] = "last"

    grouped = day_df.assign(minute=minute).groupby("minute", as_index=False).agg(agg)
    grouped = grouped.sort_values("minute").set_index("minute")
    return grouped

def _get_close_at(df_min: pd.DataFrame, minute_ts: datetime, allow_tolerance: bool = True) -> Optional[float]:
    """
    Get close at the given minute. If not present and tolerance is allowed,
    try minute + 1 minute (handles occasional gaps).
    """
    if df_min.empty:
        return None
    key = pd.Timestamp(minute_ts).tz_convert(IST) if minute_ts.tzinfo else pd.Timestamp(minute_ts, tz=IST)
    if key in df_min.index:
        val = df_min.loc[key, "close"]
        return float(val) if pd.notna(val) else None
    if allow_tolerance:
        key2 = key + pd.Timedelta(minutes=1)
        if key2 in df_min.index:
            val = df_min.loc[key2, "close"]
            return float(val) if pd.notna(val) else None
    return None

def _get_price_at_signal(df_min: pd.DataFrame, signal_time: datetime) -> Tuple[Optional[float], bool]:
    """
    Get the CLOSE price at signal time with the following logic:
    1. First, try to get the last available CLOSE at or before signal_time
    2. If none exists, look forward within 15 minutes for the first CLOSE
    3. Never use OPEN prices
    4. Return (price, is_fallback) where is_fallback indicates if forward search was used
    """
    if df_min.empty:
        return None, False
    
    signal_key = pd.Timestamp(signal_time).tz_convert(IST) if signal_time.tzinfo else pd.Timestamp(signal_time, tz=IST)
    
    # Try exact match first
    if signal_key in df_min.index:
        val = df_min.loc[signal_key, "close"]
        if pd.notna(val):
            return float(val), False
    
    # Try backward search: find the last CLOSE at or before signal_time
    before_mask = df_min.index <= signal_key
    before_data = df_min.loc[before_mask]
    if not before_data.empty:
        # Get the last row (most recent before signal)
        last_close = before_data.iloc[-1]["close"]
        if pd.notna(last_close):
            return float(last_close), False
    
    # Forward fallback: search within 15 minutes for first CLOSE
    end_key = signal_key + pd.Timedelta(minutes=15)
    forward_mask = (df_min.index > signal_key) & (df_min.index <= end_key)
    forward_data = df_min.loc[forward_mask]
    
    if not forward_data.empty:
        # Get the first row after signal (within 15 min tolerance)
        first_close = forward_data.iloc[0]["close"]
        if pd.notna(first_close):
            return float(first_close), True  # Mark as fallback
    
    return None, False

def _get_price_after(df_min: pd.DataFrame, target_time: datetime, tolerance_minutes: int = 10) -> Optional[float]:
    """
    Get the first available CLOSE price at or AFTER the target time.
    Forward-only search with tolerance.
    
    Args:
        df_min: DataFrame with minute bars indexed by timestamp
        target_time: The target time to search from
        tolerance_minutes: Maximum minutes to search forward (default: 10)
    
    Returns:
        First CLOSE price found at or after target_time within tolerance, or None
    """
    if df_min.empty:
        return None
    
    target_key = pd.Timestamp(target_time).tz_convert(IST) if target_time.tzinfo else pd.Timestamp(target_time, tz=IST)
    end_key = target_key + pd.Timedelta(minutes=tolerance_minutes)
    
    # Forward-only search: at or after target, within tolerance
    forward_mask = (df_min.index >= target_key) & (df_min.index <= end_key)
    forward_data = df_min.loc[forward_mask]
    
    if not forward_data.empty:
        # Get the first row at or after target time
        first_close = forward_data.iloc[0]["close"]
        if pd.notna(first_close):
            return float(first_close)
    
    return None

def _load_signals() -> tuple[list[dict], Path]:
    """
    Load news sentiment data from all_news_sentiment.json
    """
    src = OUT_DIR / "deberta_fin" / "all_news_sentiment.json"
    if not src.exists():
        raise FileNotFoundError(f"Sentiment file not found: {src}")

    with open(src, "r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, list):
        raise ValueError(f"Expected list of articles, got {type(data)}")

    dbg(f"Loaded {len(data)} articles from {src}")
    return data, src



def _get_multiple_prices(df_min: pd.DataFrame, t_ist: datetime, intervals: List[int]) -> Dict[str, Optional[float]]:
    """
    Get prices at multiple intervals after the signal time.
    Uses forward-only search with 10-minute tolerance for each interval.
    """
    prices = {}
    for interval in intervals:
        target_time = t_ist + timedelta(minutes=interval)
        price = _get_price_after(df_min, target_time, tolerance_minutes=10)
        if price is not None:
            prices[f"price_after_{interval}min"] = round(price, 2)
        else:
            prices[f"price_after_{interval}min"] = None
    return prices


def _get_price_range(df_min: pd.DataFrame, t_ist: datetime, max_interval: int) -> Tuple[Optional[float], Optional[float]]:
    """
    Get highest and lowest prices within the tracking period
    """
    if df_min.empty:
        return None, None
    
    start_key = pd.Timestamp(t_ist).tz_convert(IST) if t_ist.tzinfo else pd.Timestamp(t_ist, tz=IST)
    end_time = t_ist + timedelta(minutes=max_interval)
    end_key = pd.Timestamp(end_time).tz_convert(IST) if end_time.tzinfo else pd.Timestamp(end_time, tz=IST)
    
    # Filter data within the time range
    mask = (df_min.index >= start_key) & (df_min.index <= end_key)
    range_data = df_min.loc[mask]
    
    if range_data.empty:
        return None, None
    
    highest = round(float(range_data["high"].max()), 2) if not range_data["high"].isna().all() else None
    lowest = round(float(range_data["low"].min()), 2) if not range_data["low"].isna().all() else None
    
    return highest, lowest



def _evaluate_signal(
    article: dict,
    sym2company: Dict[str, str],
    horizon_min: int,
) -> Tuple[Optional[dict], Optional[str]]:
    """
    Process a news article and calculate correlation metrics.
    Returns (output_dict, reason_if_skipped).
    """
    sym = str(article.get("Symbol", "")).strip().upper()
    sentiment = str(article.get("sentiment", "")).strip().lower()
    
    if not sym:
        return None, "NO_SYMBOL"
    
    # Map sentiment to signal: positive=BUY, negative=SELL, neutral=HOLD
    if sentiment == "positive":
        side = "BUY"
    elif sentiment == "negative":
        side = "SELL"
    elif sentiment == "neutral":
        side = "HOLD"
    else:
        return None, "INVALID_SENTIMENT"

    t_ist, time_src = _parse_ist_time_from_article(article)
    if t_ist is None:
        return None, "TIME_PARSE_FAIL"
    dbg(f"Article {sym} {sentiment} at {t_ist.strftime('%Y-%m-%d %H:%M')} (source={time_src})")

    if not _market_window_ok(t_ist, horizon_min):
        return None, "OUT_OF_MARKET"

    company = sym2company.get(sym)
    if not company:
        return None, "NO_MAPPING"

    folder = _resolve_company_folder(company)
    if not folder:
        return None, "NO_FOLDER"

    csv_path = _find_csv_for_date(folder, t_ist)
    if not csv_path or not csv_path.exists():
        return None, f"NO_CSV:{folder.name}"

    try:
        day_df = pd.read_csv(csv_path)
    except Exception:
        return None, "CSV_READ_FAIL"

    for col in ["timestamp", "open", "high", "low", "close", "volume"]:
        if col not in day_df.columns:
            return None, "MISSING_COLUMNS"

    df_min = _canonicalize_minute_bars(day_df)
    if df_min.empty:
        return None, "NO_DATA_AFTER_CANON"

    # Updated intervals to include 20 and 90 minutes
    intervals = [2, 5, 10, 15, 20, 30, 45, 60, 90, 120, 180, 240]
    price_data = _get_multiple_prices(df_min, t_ist, intervals)

    # Get price at signal using new logic: backward search first, then forward fallback
    p0, is_fallback = _get_price_at_signal(df_min, t_ist)
    if p0 is None:
        return None, "MISSING_PRICE_T"

    p1 = price_data.get("price_after_60min")
    if p1 is None:
        return None, "MISSING_PRICE_TPLUS_1HOUR"
    
    # Get price range (highest and lowest)
    highest, lowest = _get_price_range(df_min, t_ist, max(intervals))
    
    # Calculate percent change
    percent_change = round(((p1 - p0) / p0) * 100, 2) if p0 != 0 else 0.0
    
    # Determine result based on sentiment
    # For HOLD (neutral), we skip result determination
    if side == "HOLD":
        result = "Neutral"
    else:
        correct = (p1 > p0) if side == "BUY" else (p1 < p0)
        result = "Correct" if correct else "Wrong"

    out = {
        "time": t_ist.strftime("%Y-%m-%d %H:%M"),
        "article_id": article.get("article_id", ""),
        "headline": article.get("headline", ""),
        "confidence": article.get("confidence", 0.0),
        "url": article.get("url", ""),
        "stock": sym,
        "sentiment": sentiment,
        "price_at_signal": round(float(p0), 2),
        "price_at_signal_is_fallback": is_fallback,
        **price_data,  # Add all price_after_Xmin fields
        "highest_price": highest,
        "lowest_price": lowest,
        "percent_change": percent_change,
        "result": result,
    }
    return out, None


def verify(signals: List[dict], t0_iso: Optional[str] = None, horizon: str = "5m") -> Dict[str, object]:
    """
    Verify a list of signals and write a single JSON:
      output/correlation/correlation_latest.json  (list of entries)
    Returns a small summary dict for printing/logging.
    """
    horizon = str(horizon).strip().lower()
    if horizon.endswith("h"):
        horizon_min = int(horizon[:-1]) * 60
    elif horizon.endswith("m"):
        horizon_min = int(horizon[:-1])
    else:
        horizon_min = HORIZON_MINUTES_DEFAULT


    dbg(f"OHLCV_BASE={OHLCV_BASE}")
    dbg(f"MAP_CSV={MAP_CSV}")
    dbg(f"HORIZON_MINUTES={horizon_min}")

    sym2company = _load_mapping(MAP_CSV)

    results: List[dict] = []
    processed = skipped = 0

    for article in signals:
        processed += 1
        # Extract sym and sentiment before any usage
        sym = str(article.get("Symbol", "")).strip().upper()
        sentiment = str(article.get("sentiment", "")).strip()
        
        out, reason = _evaluate_signal(article, sym2company, horizon_min=horizon_min)
        if out is None:
            skipped += 1
            if DEBUG or sym == "ADANIGREEN":
                print(f"[correlation_checker][SKIP] {sym} {sentiment} → {reason}")
            continue
        results.append(out)

    out_path = CORR_DIR / "correlation_latest.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    summary = {
        "sample_size": processed,
        "written": len(results),
        "skipped": skipped,
        "horizon_minutes": horizon_min,
        "output_file": str(out_path),
    }
    return summary

def _run_once():
    try:
        signals, src = _load_signals()
        dbg(f"Signals source used: {src}")
    except Exception as e:
        print(f"[correlation_checker] ERROR loading signals: {e}")
        return
    summary = verify(signals=signals, t0_iso=None, horizon="1h")
    print(f"[correlation_checker] Summary: {summary}")

if __name__ == "__main__":
    _run_once()