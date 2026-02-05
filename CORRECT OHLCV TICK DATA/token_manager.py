import os
import json
import time
import base64
from datetime import datetime, timezone
from typing import Dict, Optional, Tuple


class TokenManager:
    """
    Manages Dhan access tokens (Web/UI tokens).
    NOTE: Web-generated Dhan tokens are NOT renewable via API.
    """

    def __init__(self, token_file_path="dhan_token.json"):
        self.token_file_path = token_file_path

    def load_token(self) -> Optional[Dict]:
        if not os.path.exists(self.token_file_path):
            print(f"[TokenManager] Token file not found: {self.token_file_path}")
            return None

        try:
            with open(self.token_file_path, "r") as f:
                return json.load(f)
        except Exception as e:
            print(f"[TokenManager] Error loading token: {e}")
            return None

    def _extract_expiry_from_jwt(self, token: str) -> int:
        try:
            parts = token.split(".")
            if len(parts) != 3:
                return 0

            payload = parts[1]
            payload += "=" * (-len(payload) % 4)
            decoded = base64.urlsafe_b64decode(payload)
            payload_data = json.loads(decoded)

            return payload_data.get("exp", 0)
        except Exception as e:
            print(f"[TokenManager] JWT expiry decode failed: {e}")
            return 0

    def is_token_expired(self, token_data: Dict, buffer_seconds: int = 300) -> bool:
        expires_at = token_data.get("expires_at")
        if not expires_at:
            return True

        now = int(time.time())
        remaining = expires_at - now

        if remaining <= buffer_seconds:
            print(
                f"[TokenManager] Token expires in {remaining}s "
                f"(Buffer: {buffer_seconds}s) -> EXPIRED / EXPIRING"
            )
            return True

        return False

    def get_valid_token(self) -> Tuple[Optional[str], Optional[str]]:
        """
        IMPORTANT:
        - Web/UI Dhan tokens are NOT renewable
        - We only validate expiry and return token
        """

        token_data = self.load_token()
        if not token_data:
            print("[TokenManager] ❌ No token data found.")
            return None, None

        access_token = token_data.get("access_token")
        client_id = token_data.get("client_id")

        if not access_token or not client_id:
            print("[TokenManager] ❌ Invalid token data.")
            return None, None

        # Ensure expiry exists
        if "expires_at" not in token_data:
            token_data["expires_at"] = self._extract_expiry_from_jwt(access_token)

        # Check expiry (NO RENEW)
        if self.is_token_expired(token_data):
            print("[TokenManager] ❌ Token expired. Please generate a new token.")
            return None, None

        return access_token, client_id


if __name__ == "__main__":
    tm = TokenManager()
    token, cid = tm.get_valid_token()

    if token:
        print(f"✅ Token valid for client {cid}")
    else:
        print("❌ Token invalid or expired")
