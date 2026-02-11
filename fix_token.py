import json
import base64
import time
import os

TOKEN_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "correct_ohlcv_tick_data", "dhan_token.json")

def extract_expiry(token):
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        payload = parts[1]
        payload += "=" * (-len(payload) % 4)
        decoded = base64.urlsafe_b64decode(payload)
        data = json.loads(decoded)
        return data.get("exp")
    except Exception as e:
        print(f"Error decoding JWT: {e}")
        return None

if not os.path.exists(TOKEN_FILE):
    print("❌ Token file not found!")
    exit(1)

with open(TOKEN_FILE, "r") as f:
    data = json.load(f)

token = data.get("access_token", "")
if not token:
    print("❌ No access token in file.")
    exit(1)

real_expiry = extract_expiry(token)
if not real_expiry:
    print("❌ Could not extract expiry from token string.")
    exit(1)

current_expiry = data.get("expires_at", 0)
print(f"File Expiry: {current_expiry}")
print(f"Real Expiry: {real_expiry}")

if real_expiry != current_expiry:
    print("⚠️ Mismatch detected! Updating file with real expiry...")
    data["expires_at"] = real_expiry
    data["renewed_at"] = int(time.time())
    
    with open(TOKEN_FILE, "w") as f:
        json.dump(data, f, indent=4)
    print("✅ File updated successfully.")
    
    # Check if actually expired
    now = int(time.time())
    if real_expiry < now:
        print(f"❌ WARNING: This token is EXPIRED (Expired {now - real_expiry}s ago).")
        print("Please generate a NEW token from the Dhan website.")
    else:
        print(f"✅ Token is VALID (Expires in {real_expiry - now}s).")
else:
    print("ℹ️ Timestamps match.")
    now = int(time.time())
    if real_expiry < now:
        print(f"❌ Token is EXPIRED (Expired {now - real_expiry}s ago).")
        print("Please generate a NEW token from the Dhan website.")
    else:
        print(f"✅ Token is VALID (Expires in {real_expiry - now}s).")
