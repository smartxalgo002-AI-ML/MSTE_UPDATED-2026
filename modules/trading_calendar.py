"""
Trading Calendar Module

Centralized trading day and market hours detection for NSE/BSE.
Handles weekends, holidays, and session calculations.
"""

from datetime import datetime, date, time, timedelta
from typing import Tuple
import pytz

# IST Timezone
IST = pytz.timezone('Asia/Kolkata')

# NSE Trading Hours
MARKET_OPEN = time(9, 15)
MARKET_CLOSE = time(15, 30)

# NSE/BSE Holidays for 2026
NSE_HOLIDAYS_2026 = [
    "2026-01-15",  # Makar Sankranti
    "2026-01-26",  # Republic Day
    "2026-03-03",  # Maha Shivaratri
    "2026-03-26",  # Holi
    "2026-03-31",  # Id-Ul-Fitr
    "2026-04-03",  # Ram Navami
    "2026-04-14",  # Dr. Ambedkar Jayanti / Mahavir Jayanti
    "2026-05-01",  # Maharashtra Day
    "2026-05-28",  # Eid-ul-Adha
    "2026-06-26",  # Muharram
    "2026-09-14",  # Ganesh Chaturthi
    "2026-10-02",  # Gandhi Jayanti
    "2026-10-20",  # Dussehra
    "2026-11-10",  # Diwali (Laxmi Pujan)
    "2026-11-24",  # Gurunanak Jayanti
    "2026-12-25",  # Christmas
]

def is_trading_day(date_obj: date) -> Tuple[bool, str]:
    """
    Check if given date is a trading day.
    
    Args:
        date_obj: date object to check
        
    Returns:
        (is_trading, reason): Tuple of bool and reason string
    """
    # Weekend check (Monday=0, Sunday=6)
    weekday = date_obj.weekday()
    if weekday >= 5:  # Saturday or Sunday
        day_name = date_obj.strftime('%A')
        return False, f"Weekend ({day_name})"
    
    # Holiday check
    date_str = date_obj.strftime("%Y-%m-%d")
    if date_str in NSE_HOLIDAYS_2026:
        return False, f"NSE Holiday ({date_str})"
    
    return True, "Trading Day"


def is_market_hours(datetime_obj: datetime) -> Tuple[bool, str]:
    """
    Check if given datetime falls within market hours (09:15-15:30 IST).
    
    Args:
        datetime_obj: datetime object (can be naive or timezone-aware)
        
    Returns:
        (is_market_hours, reason): Tuple of bool and reason string
    """
    # Convert to IST if needed
    if datetime_obj.tzinfo is None:
        dt_ist = IST.localize(datetime_obj)
    else:
        dt_ist = datetime_obj.astimezone(IST)
    
    # Check if trading day first
    is_trading, reason = is_trading_day(dt_ist.date())
    if not is_trading:
        return False, reason
    
    # Check time
    time_only = dt_ist.time()
    if MARKET_OPEN <= time_only <= MARKET_CLOSE:
        return True, "Market Hours"
    elif time_only < MARKET_OPEN:
        return False, "Before Market Open"
    else:
        return False, "After Market Close"


def get_previous_trading_session_date(news_datetime: datetime) -> date:
    """
    Get the previous trading session date relative to news timestamp.
    
    Args:
        news_datetime: News publication datetime
        
    Returns:
        date object of previous trading session
    """
    # Convert to IST if needed
    if news_datetime.tzinfo is None:
        dt_ist = IST.localize(news_datetime)
    else:
        dt_ist = news_datetime.astimezone(IST)
    
    # Start checking from yesterday
    check_date = dt_ist.date() - timedelta(days=1)
    
    # Keep going back until we find a trading day
    max_attempts = 30  # Protect against infinite loop
    for _ in range(max_attempts):
        is_trading, _ = is_trading_day(check_date)
        if is_trading:
            return check_date
        check_date -= timedelta(days=1)
    
    raise ValueError(f"Could not find previous trading day within 30 days of {news_datetime}")


def get_next_trading_session_date(news_datetime: datetime) -> date:
    """
    Get the next trading session date relative to news timestamp.
    
    Args:
        news_datetime: News publication datetime
        
    Returns:
        date object of next trading session
    """
    # Convert to IST if needed
    if news_datetime.tzinfo is None:
        dt_ist = IST.localize(news_datetime)
    else:
        dt_ist = news_datetime.astimezone(IST)
    
    # Start checking from tomorrow
    check_date = dt_ist.date() + timedelta(days=1)
    
    # Keep going forward until we find a trading day
    max_attempts = 30  # Protect against infinite loop
    for _ in range(max_attempts):
        is_trading, _ = is_trading_day(check_date)
        if is_trading:
            return check_date
        check_date += timedelta(days=1)
    
    raise ValueError(f"Could not find next trading day within 30 days of {news_datetime}")


def sanitize_for_filename(company_name: str) -> str:
    """Sanitize company name for use in file paths."""
    return company_name.replace(" ", "_").replace("/", "_").replace("\\", "_")


def load_ohlcv_for_session(symbol: str, session_date: date) -> 'pd.DataFrame':
    """
    Load 1-min OHLCV CSV for a symbol on a specific date.
    
    Args:
        symbol: Stock symbol/company name
        session_date: Trading session date
        
    Returns:
        DataFrame with OHLCV data, or None if file not found
    """
    import pandas as pd
    import os
    
    # Assume OHLCV data is stored in: data_ohlcv/group_XX/[CompanyName]/[CompanyName] DD-MM-YYYY.csv
    base_dir = os.environ.get("TICKS_BASE_DIR", "data_ohlcv")
    sanitized_name = sanitize_for_filename(symbol)
    date_str = session_date.strftime("%d-%m-%Y")
    
    file_path = os.path.join(base_dir, "group_XX", sanitized_name,  f"{sanitized_name} {date_str}.csv")
    
    if not os.path.exists(file_path):
        return None
    
    df = pd.read_csv(file_path)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    return df.sort_values("timestamp")


def get_close_price_at_session(symbol: str, session_date: date, close_time: str = "15:30") -> float:
    """
    Get closing price at specific session and time.
    
    Args:
        symbol: Stock symbol
        session_date: Trading session date
        close_time: Time string (HH:MM format)
        
    Returns:
        Close price at that session, or None if not available
    """
    import pandas as pd
    from datetime import datetime
    
    # Load OHLCV data for that session
    df = load_ohlcv_for_session(symbol, session_date)
    if df is None or df.empty:
        return None
    
    # Parse target time
    hour, minute = map(int, close_time.split(":"))
    target_time = IST.localize(datetime.combine(session_date, time(hour, minute)))
    
    # Find candle at or before target time
    df_before = df[df["timestamp"] <= target_time]
    if df_before.empty:
        return None
    
    # Return close price of last available candle
    return float(df_before.iloc[-1]["close"])


def get_max_price_in_window(symbol: str, session_date: date, start_time: str, end_time: str) -> float:
    """
    Get maximum price in a time window on a specific session.
    
    Args:
        symbol: Stock symbol
        session_date: Trading session date
        start_time: Window start (HH:MM format)
        end_time: Window end (HH:MM format)
        
    Returns:
        Maximum price in window, or None if data not available
    """
    import pandas as pd
    from datetime import datetime
    
    # Load OHLCV data for that session
    df = load_ohlcv_for_session(symbol, session_date)
    if df is None or df.empty:
        return None
    
    # Parse start and end times
    start_hour, start_min = map(int, start_time.split(":"))
    end_hour, end_min = map(int, end_time.split(":"))
    
    window_start = IST.localize(datetime.combine(session_date, time(start_hour, start_min)))
    window_end = IST.localize(datetime.combine(session_date, time(end_hour, end_min)))
    
    # Filter candles within window
    df_window = df[(df["timestamp"] >= window_start) & (df["timestamp"] <= window_end)]
    if df_window.empty:
        return None
    
    # Return max of high prices in window
    return float(df_window["high"].max())


def parse_flexible_date(date_str: str) -> datetime:
    """
    Parse various date formats into a datetime object.
    Returns None if parsing fails.
    """
    if not date_str:
        return None
        
    date_str = date_str.strip()
    
    try:
        # 1. ISO Format (2026-02-16T10:00:00)
        return datetime.fromisoformat(date_str.replace('Z', '+00:00'))
    except ValueError:
        pass
        
    try:
        # 2. "2026-02-16 10:00:00" (Space separator)
        if "-" in date_str and ":" in date_str:
            return datetime.strptime(date_str[:19], "%Y-%m-%d %H:%M:%S")
    except ValueError:
        pass

    try:
        # 3. "10:49:00 AM | 13 Feb 2026"
        if "|" in date_str:
            time_part, date_part = date_str.split("|")
            time_part = time_part.strip()
            date_part = date_part.strip()
            fmt = "%d %b %Y %I:%M:%S %p" if len(time_part.split(":")) == 3 else "%d %b %Y %I:%M %p"
            return datetime.strptime(f"{date_part} {time_part}", fmt)
    except ValueError:
        pass

    try:
        # 4. "February 16, 2026/ 10:35 IST"
        if "/" in date_str and "IST" in date_str:
            clean_str = date_str.replace(" IST", "").replace("/", "")
            return datetime.strptime(clean_str.strip(), "%B %d, %Y %H:%M")
    except ValueError:
        pass
        
    try:
        # 5. "February 16, 2026 at 09:47 AM"
        if " at " in date_str:
            return datetime.strptime(date_str, "%B %d, %Y at %I:%M %p")
    except ValueError:
        pass
        
    return None

def detect_regime(news_time_str: str) -> str:
    """
    Detect the regime based on news publication time.
    
    Regimes:
    - 'intraday': Trading day + Market Hours (09:15-15:30)
    - 'after_market': Trading day + After 15:30
    - 'weekend_holiday': Non-trading day or pre-market
    
    Args:
        news_time_str: News published_time string
        
    Returns:
        'intraday', 'after_market', or 'weekend_holiday'
    """
    # 1. Parse the time
    news_time = parse_flexible_date(news_time_str)
    
    if news_time is None:
        # Fallback: Try primitive ISO replacement if strict parsing failed
        try:
             news_time = datetime.fromisoformat(news_time_str.replace('Z', '+00:00').replace(' ', 'T'))
        except:
             # If all parsing fails, we cannot determine regime.
             # Defaulting to 'weekend_holiday' is the safest "do nothing" state.
             print(f"[Regime] ❌ Could not parse date: '{news_time_str}' -> Defaulting to weekend_holiday")
             return 'weekend_holiday'

    # 2. Localize to IST
    if news_time.tzinfo is None:
        news_time = IST.localize(news_time)
    else:
        news_time = news_time.astimezone(IST)
    
    # 3. Check if trading day
    is_trading, reason = is_trading_day(news_time.date())
    if not is_trading:
        # print(f"[Regime] {news_time} is Non-Trading ({reason})")
        return 'weekend_holiday'
    
    # 4. Check market hours
    # Note: Pre-market (before 9:15) is effectively "before intraday", 
    # but for signaling purposes, we often treat it as 'weekend_holiday' (wait) 
    # or 'after_market' (prepare). 
    # Let's check strict hours.
    time_only = news_time.time()
    
    if MARKET_OPEN <= time_only <= MARKET_CLOSE:
        return 'intraday'
    elif time_only > MARKET_CLOSE:
        return 'after_market'
    else:
        # Before market open (00:00 - 09:15)
        # Should be treated as 'weekend_holiday' for "label calculation" purposes (calculating labels for TODAY)
        # OR 'after_market' of previous day? 
        # Usually we treat pre-market news as setting up for TODAY's open.
        # But if we return 'weekend_holiday', the system might skip immediate processing.
        # Let's stick to 'weekend_holiday' for now to be safe, or 'after_market' if we want to signal 'hold/pending'.
        return 'weekend_holiday'


if __name__ == "__main__":
    # Quick tests
    print("=== Trading Calendar Tests ===\n")
    
    # Test 1: Weekend detection
    test_saturday = date(2026, 2, 14)
    is_trading, reason = is_trading_day(test_saturday)
    print(f"2026-02-14 (Saturday): {is_trading} - {reason}")
    
    # Test 2: Holiday detection
    test_holiday = date(2026, 1, 26)
    is_trading, reason = is_trading_day(test_holiday)
    print(f"2026-01-26 (Republic Day): {is_trading} - {reason}")
    
    # Test 3: Normal trading day
    test_monday = date(2026, 2, 16)
    is_trading, reason = is_trading_day(test_monday)
    print(f"2026-02-16 (Monday): {is_trading} - {reason}")
    
    # Test 4: Market hours
    test_dt = IST.localize(datetime(2026, 2, 16, 10, 30))
    in_hours, reason = is_market_hours(test_dt)
    print(f"\n2026-02-16 10:30 IST: {in_hours} - {reason}")
    
    # Test 5: Session calculations
    friday_evening = IST.localize(datetime(2026, 2, 14, 18, 0))
    prev_session = get_previous_trading_session_date(friday_evening)
    next_session = get_next_trading_session_date(friday_evening)
    print(f"\nNews Time: Friday 2026-02-14 18:00")
    print(f"Previous Trading Session: {prev_session}")
    print(f"Next Trading Session: {next_session}")

    print("\n=== Special Format Tests ===")
    dates_to_test = [
        "February 16, 2026/ 10:35 IST",
        "February 16, 2026 at 09:47 AM",
        "10:49:00 AM | 13 Feb 2026",
        "2026-02-16T10:00:00"
    ]
    for d in dates_to_test:
        regime = detect_regime(d)
        print(f"'{d}' -> {regime}")
