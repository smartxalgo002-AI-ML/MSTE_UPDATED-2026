import os
import sys
import csv
import json
import time
import struct
import threading
from datetime import datetime, timedelta, timezone
import websocket
import pandas as pd
import numpy as np
from collections import deque
from token_manager import TokenManager

# =========================
# CONFIGURATION
# =========================
# Initialize token manager
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TOKEN_PATH = os.path.join(BASE_DIR, "dhan_token.json")

token_manager = TokenManager(TOKEN_PATH)

# Global Variables (Updated dynamically)
ACCESS_TOKEN, CLIENT_ID = None, None
WS_URL = None

def update_global_token():
    """Update global token variables and WS_URL from TokenManager"""
    global ACCESS_TOKEN, CLIENT_ID, WS_URL
    
    # Load token data first
    token_data = token_manager.load_token()
    if not token_data:
        return False
    
    at = token_data.get("access_token")
    cid = token_data.get("client_id")
    
    if not at or not cid:
        return False
    
    # Only attempt renewal if token expires within 1 hour (not 6 hours)
    # This prevents premature API calls that return 400 errors
    if token_manager.is_token_expired(token_data, buffer_seconds=3600):  # 1 hour
        print("[Token] Expiring soon, attempting renewal...")
        at, cid = token_manager.get_valid_token()
        if not at or not cid:
            # If renewal fails, check if current token is still usable
            expires_at = token_data.get("expires_at", 0)
            remaining = expires_at - int(time.time())
            if remaining > 0:
                print(f"[Token] Renewal failed but token still valid for {remaining/3600:.2f}h")
                at = token_data.get("access_token")
                cid = token_data.get("client_id")
            else:
                return False
    
    ACCESS_TOKEN, CLIENT_ID = at, cid
    WS_URL = f"wss://api-feed.dhan.co?version=2&token={ACCESS_TOKEN}&clientId={CLIENT_ID}&authType=2"
    return True

# Initial token load
if not update_global_token():
     raise RuntimeError("❌ Failed to load valid token. Please check dhan_token.json")


print(f"[Config] Using Client ID: {CLIENT_ID}")
print(f"[Config] Token length: {len(ACCESS_TOKEN)} chars")
print(f"[Config] Token starts with: {ACCESS_TOKEN[:20]}...")
print(f"[Config] WebSocket URL: wss://api-feed.dhan.co?version=2&token=***&clientId={CLIENT_ID}&authType=2")



OUTPUT_ROOT = os.path.join(os.getenv("TICKS_BASE_DIR", "data_ohlcv"), "group_XX")
CSV_PATH = os.path.join(BASE_DIR, "mapping_security_ids.csv")
PRINT_TICKS = True

HV_WINDOW = 60  # number of past candles to calculate HV

# WebSocket Connection Parameters - Optimized to prevent IP blocking
SUBSCRIPTION_BATCH_SIZE = 20           # Reduced from 50 to 20 instruments per batch
SUBSCRIPTION_BATCH_DELAY = 1.2         # Increased from 1.0 to 1.2 seconds between batches
MAX_PER_CONNECTION = 350               # Split across multiple connections (was 2500)
MAX_SUBSCRIPTION_RETRIES = 3           # Retry failed subscriptions
RETRY_DELAY = 5.0                      # Delay between retries in seconds

# Time-driven candle closing configuration
GRACE_WINDOW_SECONDS = 2  # Accept ticks up to 2 seconds after minute boundary
CANDLE_CLOSE_SECOND = 2  # Close candles at HH:MM:02 IST

# =========================
# Load SECURITY_IDs from CSV
# =========================
companies_df = pd.read_csv(CSV_PATH)
SECURITY_IDS = companies_df["SECURITY_ID"].astype(str).tolist()
SECID_TO_COMPANY = dict(zip(companies_df["SECURITY_ID"].astype(str), companies_df["CompanyName"]))

print(f"[Config] Loaded {len(SECURITY_IDS)} SECURITY_IDs from {CSV_PATH}")

# IST timezone
IST = timezone(timedelta(hours=5, minutes=30))
IST_OFFSET_SECONDS = 5 * 3600 + 30 * 60

# Market hours (IST)
MARKET_OPEN_HOUR = 9
MARKET_OPEN_MINUTE = 15
MARKET_CLOSE_HOUR = 15
MARKET_CLOSE_MINUTE = 30

# =========================
# File helpers
# =========================
def ensure_dir(path):
    os.makedirs(path, exist_ok=True)

def sanitize_for_filename(name: str) -> str:
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 -_.")
    cleaned = "".join(ch for ch in name if ch in allowed).strip()
    return cleaned or "UNKNOWN"

def out_file_path_for_symbol(company_name: str, ts_ist: datetime=None) -> str:
    date_str = (ts_ist or datetime.now(IST)).strftime("%d-%m-%Y")
    comp_dir = os.path.join(OUTPUT_ROOT, sanitize_for_filename(company_name))
    ensure_dir(comp_dir)
    return os.path.join(comp_dir, f"{sanitize_for_filename(company_name)} {date_str}.csv")

def ensure_ohlcv_header(fpath: str):
    if not os.path.exists(fpath) or os.path.getsize(fpath) == 0:
        with open(fpath, "w", newline="") as f:
            csv.writer(f).writerow(["timestamp", "open", "high", "low", "close", "volume", "hv", "iv"])

def write_ohlcv(candle):
    """Write OHLCV candle to CSV. No duplicate checking needed with single-authority closing."""
    company = candle["company"]
    
    fpath = out_file_path_for_symbol(company, candle["minute"])
    ensure_ohlcv_header(fpath)
    with open(fpath, "a", newline="") as f:
        csv.writer(f).writerow([
            candle["minute"].strftime("%Y-%m-%d %H:%M:%S"),
            f"{candle['open']:.2f}",
            f"{candle['high']:.2f}",
            f"{candle['low']:.2f}",
            f"{candle['close']:.2f}",
            candle["volume"],
            f"{candle.get('hv', 0):.4f}",
            f"{candle.get('iv', 0):.4f}"
        ])
    if PRINT_TICKS:
        print(f"[CLOSED] {company} {candle['minute'].strftime('%Y-%m-%d %H:%M:%S')} "
              f"O:{candle['open']:.2f} H:{candle['high']:.2f} "
              f"L:{candle['low']:.2f} C:{candle['close']:.2f} V:{candle['volume']} "
              f"HV:{candle.get('hv',0):.4f} IV:{candle.get('iv',0):.4f}")

# =========================
# LTT -> IST conversion
# =========================
def ltt_to_ist(ltt_value):
    try:
        ts = int(ltt_value)
    except Exception:
        ts = ltt_value

    if ts > 10**11:  # ms → s
        ts = ts // 1000

    dt_ist = datetime.fromtimestamp(ts, tz=timezone.utc).astimezone(IST)
    now_ist = datetime.now(IST)

    if dt_ist - now_ist > timedelta(hours=3):
        old = dt_ist
        dt_ist = dt_ist - timedelta(seconds=IST_OFFSET_SECONDS)
        print(f"[TimeFix] Adjusted future LTT {old.isoformat()} -> {dt_ist.isoformat()}")

    return dt_ist

# =========================
# Candle aggregation - TIME-DRIVEN ARCHITECTURE
# =========================
lock = threading.Lock()
# Candles indexed by (company, minute) for deterministic closing
candles = {}  # {(company, minute_timestamp): candle_dict}
closed_candles = []  # Queue of candles to write (populated by closer thread)
stop_flag = False  # Signal to stop all threads

# Maintain last N closes for HV calculation
last_n_closes = {company: deque(maxlen=HV_WINDOW) for company in SECID_TO_COMPANY.values()}

def compute_hv(close_prices):
    """
    Calculate annualized historical volatility for intraday market data.
    Uses 252 trading days × 390 market minutes per day (9:15 AM - 3:30 PM IST).
    """
    if len(close_prices) < 2:
        return 0
    
    log_returns = np.diff(np.log(close_prices))
    
    # Handle edge cases: no variance or all zeros
    if len(log_returns) == 0 or np.all(log_returns == 0):
        return 0
    
    # Correct annualization: 252 trading days × 390 market minutes/day
    hv = np.std(log_returns) * np.sqrt(252 * 390)
    
    return hv if not np.isnan(hv) and not np.isinf(hv) else 0

def is_tick_acceptable(tick_time, current_time):
    """
    Check if tick is within acceptable time window.
    Accepts ticks for current minute or previous minute within grace window.
    """
    tick_minute = tick_time.replace(second=0, microsecond=0)
    current_minute = current_time.replace(second=0, microsecond=0)
    
    # Accept ticks for current minute
    if tick_minute == current_minute:
        return True
    
    # Accept ticks for previous minute if within grace window
    if tick_minute == current_minute - timedelta(minutes=1):
        return current_time.second <= GRACE_WINDOW_SECONDS
    
    return False

def process_tick(secid: str, ltp: float, ltq: int, ltt: int):
    """
    Process incoming tick and update candles.
    NEVER closes candles - that's done by candle_closer_loop().
    Only UPDATES active candles within grace window.
    """
    ts = ltt_to_ist(ltt)
    now_ist = datetime.now(IST)
    minute_start = ts.replace(second=0, microsecond=0)
    company = SECID_TO_COMPANY.get(secid, secid)
    
    # Reject ticks outside grace window
    if not is_tick_acceptable(ts, now_ist):
        if PRINT_TICKS:
            print(f"[REJECT] {company} tick at {ts.strftime('%H:%M:%S')} is too old (now: {now_ist.strftime('%H:%M:%S')})")
        return
    
    candle_key = (company, minute_start)
    
    with lock:
        current = candles.get(candle_key)
        
        if current is None:
            # Create new candle
            candles[candle_key] = {
                "company": company,
                "minute": minute_start,
                "open": ltp,
                "high": ltp,
                "low": ltp,
                "close": ltp,
                "volume": int(ltq or 0),
                "hv": 0,
                "iv": 0
            }
            last_n_closes[company].append(ltp)
            if PRINT_TICKS:
                print(f"[TICK-NEW] {company} {ts.strftime('%H:%M:%S')} "
                      f"O:{ltp:.2f} H:{ltp:.2f} L:{ltp:.2f} C:{ltp:.2f} V:{ltq}")
        else:
            # Update existing candle
            current["high"] = max(current["high"], ltp)
            current["low"] = min(current["low"], ltp)
            current["close"] = ltp
            current["volume"] += int(ltq or 0)
            last_n_closes[company].append(ltp)
            current["hv"] = compute_hv(list(last_n_closes[company]))
            if PRINT_TICKS:
                print(f"[TICK-UPD] {company} {ts.strftime('%H:%M:%S')} "
                      f"O:{current['open']:.2f} H:{current['high']:.2f} "
                      f"L:{current['low']:.2f} C:{current['close']:.2f} V:{current['volume']} "
                      f"HV:{current['hv']:.4f} IV:{current['iv']:.4f}")

def candle_closer_loop():
    """
    Time-driven candle closing thread.
    Closes candles exactly at HH:MM:02 IST for deterministic behavior.
    This is the SINGLE AUTHORITY for candle closes.
    """
    global stop_flag
    while not stop_flag:
        time.sleep(0.5)  # Check twice per second for precision
        now_ist = datetime.now(IST)
        
        # Close candles at exactly 2 seconds past each minute
        if now_ist.second == CANDLE_CLOSE_SECOND:
            # Close candles for the previous minute
            minute_to_close = (now_ist - timedelta(minutes=1)).replace(second=0, microsecond=0)
            
            with lock:
                # Find all candles for this minute
                keys_to_close = [k for k in candles.keys() if k[1] == minute_to_close]
                
                if keys_to_close:
                    print(f"[CLOSER] Closing {len(keys_to_close)} candles for {minute_to_close.strftime('%H:%M')}")
                
                for key in keys_to_close:
                    candle = candles.pop(key)
                    closed_candles.append(candle)
            
            # Brief sleep to avoid double-trigger
            time.sleep(0.6)

def flusher_loop():
    """Write closed candles to disk."""
    global stop_flag
    while not stop_flag:
        time.sleep(1)
        with lock:
            while closed_candles:
                c = closed_candles.pop(0)
                try:
                    write_ohlcv(c)
                except Exception as e:
                    print("[Flusher] write error:", e)

# =========================
# WebSocket decode
# =========================
decode_stats = {"total": 0, "too_short": 0, "wrong_header": 0, "processed": 0, "errors": 0}

def decode_full_packet_and_aggregate(msg: bytes):
    decode_stats["total"] += 1
    try:
        if len(msg) < 62:
            decode_stats["too_short"] += 1
            if decode_stats["too_short"] == 1:
                print(f"[Decode] Message too short: {len(msg)} bytes (expected >= 62). First 20 bytes: {msg[:20].hex() if len(msg) >= 20 else msg.hex()}")
            return
        if msg[0] != 8:
            decode_stats["wrong_header"] += 1
            if decode_stats["wrong_header"] == 1:
                print(f"[Decode] Wrong header byte: {msg[0]} (expected 8). First 20 bytes: {msg[:20].hex()}")
            return
        security_id = str(struct.unpack("<I", msg[4:8])[0])
        ltp = struct.unpack("<f", msg[8:12])[0]
        ltq = struct.unpack("<H", msg[12:14])[0]  # Unsigned short to prevent negative volumes
        ltt = struct.unpack("<I", msg[14:18])[0]
        
        if decode_stats["processed"] == 0:
            print(f"[Decode] Successfully decoded first tick: SECID={security_id}, LTP={ltp:.2f}, LTQ={ltq}, LTT={ltt}")
        
        decode_stats["processed"] += 1
        process_tick(security_id, float(ltp), int(ltq), int(ltt))
    except Exception as e:
        decode_stats["errors"] += 1
        if decode_stats["errors"] <= 3:
            print(f"[Decode] error: {e}")
            import traceback
            traceback.print_exc()

# =========================
# WebSocket client
# =========================
def get_subscription_payload(ids):
    return json.dumps({
        "RequestCode": 21,
        "FeedType": "FULL",
        "InstrumentCount": len(ids),
        "InstrumentList": [{"ExchangeSegment": "NSE_EQ", "SecurityId": sid} for sid in ids]
    })

class DhanClient:
    def __init__(self, token_manager, sec_ids, batch_size=SUBSCRIPTION_BATCH_SIZE, batch_delay=SUBSCRIPTION_BATCH_DELAY):
        self.token_manager = token_manager
        self.sec_ids = sec_ids
        self.ws = None
        self.stop_flag = False
        self.msg_count = 0
        self.last_msg_time = None
        self.batch_size = batch_size
        self.batch_delay = batch_delay
        self.subscription_sent = False
        self.subscription_start_time = None
        self.reconnect_requested = False


    def on_open(self, ws):
        self.ws = ws
        self.subscription_start_time = time.time()
        # Batch subscriptions if there are many instruments
        total = len(self.sec_ids)
        if total <= self.batch_size:
            # Single batch
            subscription_payload = get_subscription_payload(self.sec_ids)
            print(f"[WS] Sending subscription payload for {total} instruments...")
            print(f"[WS] Payload length: {len(subscription_payload)} chars")
            ws.send(subscription_payload)
            print(f"[WS] Subscribed {total} instruments in 1 batch.")
            self.subscription_sent = True
        else:
            # Multiple batches
            num_batches = (total + self.batch_size - 1) // self.batch_size
            print(f"[WS] Splitting {total} instruments into {num_batches} batches of ~{self.batch_size} each...")
            self._send_batched_subscriptions(ws, num_batches)
            elapsed = time.time() - self.subscription_start_time
            print(f"[WS] All subscriptions sent in {elapsed:.1f}s")
        print(f"[WS] Waiting for tick data...")

    def _send_batched_subscriptions(self, ws, num_batches):
        failed_batches = []
        for i in range(num_batches):
            start_idx = i * self.batch_size
            end_idx = min(start_idx + self.batch_size, len(self.sec_ids))
            batch_ids = self.sec_ids[start_idx:end_idx]
            subscription_payload = get_subscription_payload(batch_ids)
            print(f"[WS] Sending batch {i+1}/{num_batches} ({len(batch_ids)} instruments)...")
            
            # Retry logic for failed sends
            sent = False
            for attempt in range(MAX_SUBSCRIPTION_RETRIES):
                try:
                    ws.send(subscription_payload)
                    sent = True
                    break
                except Exception as e:
                    if attempt < MAX_SUBSCRIPTION_RETRIES - 1:
                        print(f"[WS] send failed on batch {i+1} (attempt {attempt+1}/{MAX_SUBSCRIPTION_RETRIES}): {e}")
                        time.sleep(RETRY_DELAY)
                    else:
                        print(f"[WS] send failed on batch {i+1} after {MAX_SUBSCRIPTION_RETRIES} attempts: {e}")
                        failed_batches.append((i+1, batch_ids))
            
            
            if sent and i < num_batches - 1:
                time.sleep(self.batch_delay)  # Consistent delay between all batches
        
        self.subscription_sent = True
        print(f"[WS] Completed all {num_batches} subscription batches ({len(self.sec_ids)} total instruments).")
        if failed_batches:
            print(f"[WS] WARNING: {len(failed_batches)} batches failed to send. Instruments: {sum(len(b[1]) for b in failed_batches)}")

    def on_message(self, ws, message):
        self.msg_count += 1
        self.last_msg_time = datetime.now(IST)
        if self.msg_count == 1:
            print(f"[WS] First message received! Type: {type(message)}, Length: {len(message) if hasattr(message, '__len__') else 'N/A'}")
            if isinstance(message, (bytes, bytearray)):
                print(f"[WS] First 20 bytes: {message[:20].hex() if len(message) >= 20 else message.hex()}")
        if self.msg_count % 100 == 0:
            print(f"[WS] Received {self.msg_count} messages so far...")
        
        if isinstance(message, (bytes, bytearray)):
            decode_full_packet_and_aggregate(message)
        else:
            if self.msg_count <= 5:
                print(f"[WS] Received non-binary message (msg #{self.msg_count}): {str(message)[:100]}")

    def on_error(self, ws, error):
        error_str = str(error)
        # Suppress noise when we purposefully closed the connection
        if self.stop_flag or self.reconnect_requested:
            return

        print(f"[WS] error (Client ID: {CLIENT_ID}): {error}")
        
        # Check for client ID specific issues
        if "429" in error_str or "Too many requests" in error_str or "blocked" in error_str.lower():
            print(f"[WS] ⚠️  RATE LIMIT/BLOCK DETECTED for Client ID: {CLIENT_ID}")
            print(f"[WS] Possible reasons why this client ID differs from your working one:")
            print(f"[WS]   1. Different subscription tier (lower rate limits)")
            print(f"[WS]   2. Account restrictions or needs activation")
            print(f"[WS]   3. Token might be invalid or expired")
            print(f"[WS]   4. Client ID might be on a trial/demo account")
        
        # Suppress 'NoneType' attribute errors which can happen during race conditions in shutdown
        if "NoneType" not in error_str:
            import traceback
            traceback.print_exc()


    def on_close(self, ws, code, msg):
        if not self.stop_flag and not self.reconnect_requested:
            print("[WS] closed:", code, msg)


    def run_forever(self):
        backoff = 1
        while not self.stop_flag:
            try:
                # Always fetch fresh token/ID and generate URL before connecting
                at, cid = self.token_manager.get_valid_token()
                if not at:
                    print(f"[WS] ❌ Cannot connect: Failed to get valid token. Retrying in 30s...")
                    time.sleep(30)
                    continue
                
                url = f"wss://api-feed.dhan.co?version=2&token={at}&clientId={cid}&authType=2"
                print(f"[WS] Attempting connection with Client ID: {cid}")
                self.ws = websocket.WebSocketApp(
                    url,
                    on_open=self.on_open,
                    on_message=self.on_message,
                    on_error=self.on_error,
                    on_close=self.on_close
                )
                self.reconnect_requested = False
                self.ws.run_forever(ping_interval=20, ping_timeout=10)
            except Exception as e:
                error_str = str(e)
                print(f"[WS] Connection attempt failed: {e}")

                # Check for rate limit specifically during connection/handshake
                if "429" in error_str or "Too many requests" in error_str:
                    print(f"\n{'!'*60}")
                    print(f"⚠️  RATELIMIT DETECTED: Your IP is currently blocked by Dhan.")
                    print(f"⚠️  System will COOL DOWN for 5 MINUTES to let the block clear.")
                    print(f"⚠️  Please DO NOT restart the script; let it wait.")
                    print(f"{'!'*60}\n")
                    time.sleep(300) # Mandatory 5 minute wait
                    backoff = 30 # Reset backoff to something sensible after long wait
                else:
                    # Regular backoff for other errors
                    time.sleep(backoff)
                    backoff = min(backoff * 2, 60)
                
            if self.stop_flag:
                break

    def stop(self):
        self.stop_flag = True
        try:
            if self.ws:
                self.ws.close()
        except Exception:
            pass

# =========================
# MAIN
# =========================
def sleep_until_next_market_open():
    """Sleep until 09:10 AM IST next trading day"""
    now_ist = datetime.now(IST)
    
    # Target: Today 09:00 AM
    target = now_ist.replace(hour=9, minute=0, second=0, microsecond=0)
    
    # If already past 09:00, target tomorrow 09:00
    if now_ist > target:
        target += timedelta(days=1)

        
    # Example logic for weekends could be added here if needed
    # For now, just simplistic next-day logic
    
    wait_seconds = (target - now_ist).total_seconds()
    hours = wait_seconds / 3600
    print(f"[System] Sleeping for {hours:.2f} hours until {target.strftime('%Y-%m-%d %H:%M:%S')} IST...")
    
    # Sleep in chunks to allow CTRL+C
    while wait_seconds > 0:
        chunk = min(wait_seconds, 60)
        time.sleep(chunk)
        wait_seconds -= chunk
        
def run_daily_session():
    """Run one daily session from now until market close"""
    global stop_flag, closed_candles, candles, last_n_closes
    
    now_ist = datetime.now(IST)
    current_time = now_ist.time()
    
    # 1. PRE-CHECK: If market is already closed, don't start anything
    if current_time.hour > 15 or (current_time.hour == 15 and current_time.minute >= 31):
        print(f"[System] Market is currently closed ({now_ist.strftime('%H:%M:%S')} IST). Skipping session.")
        return

    # 2. PRE-CHECK: If it's too early, wait until pre-market
    target_start = now_ist.replace(hour=9, minute=0, second=0, microsecond=0)
    if now_ist < target_start:
        wait_secs = (target_start - now_ist).total_seconds()
        print(f"[System] Market hasn't opened yet. Waiting {wait_secs/60:.1f} mins until 09:00 AM IST...")
        return # Let the main loop handle the sleep

    # Reset state for the new session
    stop_flag = False
    closed_candles = []
    candles = {}
    last_n_closes = {company: deque(maxlen=HV_WINDOW) for company in SECID_TO_COMPANY.values()}
    
    print("Starting OHLCV capture (1-minute candles)…")
    print(f"\n{'='*60}")
    print(f"CLIENT ID DIAGNOSTICS")
    print(f"{'='*60}")
    print(f"Current Client ID: {CLIENT_ID}")
    print(f"Total instruments to subscribe: {len(SECURITY_IDS)}")
    print(f"\n⚠️  If this client ID has different rate limits than your working one:")
    print(f"   - Consider reducing MAX_PER_CONNECTION (currently {MAX_PER_CONNECTION})")
    print(f"{'='*60}\n")
    websocket.enableTrace(False)

    ensure_dir(OUTPUT_ROOT)

    # Start threads
    t_flusher = threading.Thread(target=flusher_loop, daemon=True)
    t_flusher.start()
    
    t_closer = threading.Thread(target=candle_closer_loop, daemon=True)
    t_closer.start()
    print(f"[System] Candle closer started - closes at HH:MM:{CANDLE_CLOSE_SECOND:02d} IST")

    clients = []
    threads = []
    total = len(SECURITY_IDS)
    start = 0
    while start < total:
        grp = SECURITY_IDS[start:start+MAX_PER_CONNECTION]
        c = DhanClient(token_manager, grp)
        t = threading.Thread(target=c.run_forever, daemon=True)
        clients.append(c)
        threads.append(t)
        t.start()
        start += MAX_PER_CONNECTION
        if start < total:
            print(f"[System] Waiting 5s before starting next connection group...")
            time.sleep(5)

    # Token watcher to handle automatic renewal and signal reconnections
    def token_watcher_loop():
        nonlocal clients
        print("[System] Token watcher thread started.")
        while not stop_flag:
            try:
                # Check for renewal/updates every 5 minutes
                # Use a small buffer to trigger renewal well before actual expiry
                at, cid = token_manager.get_valid_token()
                
                # Check if any client needs to reconnect due to token change
                if token_manager.has_token_changed():
                    print("[System] 🔄 Token change detected! Signaling all clients to reconnect...")
                    for c in clients:
                        c.reconnect_requested = True
                        if c.ws:
                            c.ws.close() # This will trigger run_forever to loop and get new token
                
            except Exception as e:
                print(f"[System] Token watcher error: {e}")
            
            # Sleep in chunks to remain responsive to stop_flag
            for _ in range(300): # 300 seconds = 5 minutes
                if stop_flag: break
                time.sleep(1)

    t_watcher = threading.Thread(target=token_watcher_loop, daemon=True)
    t_watcher.start()


    def check_market_close():
        """Check if market is closed and return True if we should stop"""
        now_ist = datetime.now(IST)
        current_time = now_ist.time()
        
        # Stop if it's past 15:31 IST
        if current_time.hour > 15 or (current_time.hour == 15 and current_time.minute >= 31):
            return True
        return False
    
    try:
        now_ist = datetime.now(IST)
        print(f"[Info] Current time: {now_ist.strftime('%Y-%m-%d %H:%M:%S')} IST")
        print(f"[Info] Market closes at {MARKET_CLOSE_HOUR}:{MARKET_CLOSE_MINUTE:02d} IST. Script will auto-stop at 15:31 IST.")
        last_status_minute = -1
        last_stats_print = time.time()
        
        while True:
            time.sleep(1)
            now_ist = datetime.now(IST)
            current_minute = now_ist.minute
            
            # Print stats every 30 seconds
            if time.time() - last_stats_print >= 30:
                last_stats_print = time.time()
                total_msgs = sum(c.msg_count for c in clients)
                print(f"[Stats] Clients: {len(clients)}, Messages: {total_msgs}, Decoded: {decode_stats['processed']}, "
                      f"Candles in memory: {len(candles)}, Closed pending: {len(closed_candles)}")
            
            # Print status every minute near close
            if current_minute != last_status_minute and now_ist.hour >= 15:
                if now_ist.hour == 15 and current_minute == 30:
                    print(f"[Status] Market closing at 15:30 IST. Will stop soon...")
                last_status_minute = current_minute
            
            # Check if market is closed
            if check_market_close():
                print(f"[Market Close] Market closed. Stopping data collection at {now_ist.strftime('%H:%M:%S')} IST...")
                break
                
    except KeyboardInterrupt:
        print("KeyboardInterrupt detected. Stopping session...")
        raise  # Propagate to main loop to exit completely
        
    finally:
        print("Stopping threads...")
        stop_flag = True
        for c in clients:
            c.stop()
        for t in threads:
            t.join(timeout=3)
        with lock:
            for c in closed_candles:
                write_ohlcv(c)
            for _, candle in candles.items():
                write_ohlcv(candle)
        print("Session End: Cleanup complete.")


# =========================
# MAIN LOOP (Runs Forever)
# =========================
if __name__ == "__main__":
    try:
        while True:
            # 1. Update Token (Auto-Renew if needed) before session starts
            print("\n[System] Checking Token Validity...")
            ACCESS_TOKEN, CLIENT_ID = token_manager.get_valid_token()
            
            if not ACCESS_TOKEN:
                print("[System] ❌ Failed to get valid token. Retrying in 60s...")
                time.sleep(60)
                continue
                
            # Update global variables so run_daily_session uses the new token/client
            WS_URL = f"wss://api-feed.dhan.co?version=2&token={ACCESS_TOKEN}&clientId={CLIENT_ID}&authType=2"
            
            # 2. Run the daily trading session
            run_daily_session()
            
            # 2. After session ends (at 15:31), go to sleep until next morning
            print("\n" + "="*60)
            print("MARKET CLOSED FOR TODAY")
            print("System will now sleep until next market open (09:00 AM IST)")
            print("="*60 + "\n")
            
            sleep_until_next_market_open()
            
            # 3. Updates token before starting next session (if needed)
            # TokenManager handles renewal automatically inside get_valid_token logic
            # but we can force refresh if we wanted to. Current logic re-reads on init.
            print("Waking up! Preparing for new trading session...")
            
    except KeyboardInterrupt:
        print("\n[System] Permanently stopped by user (CTRL+C). Goodbye!")
        sys.exit(0)
    except Exception as e:
        print(f"\n[System] CRITICAL ERROR: {e}")
        import traceback
        traceback.print_exc()
        print("Restarting loop in 60 seconds...")
        time.sleep(60)