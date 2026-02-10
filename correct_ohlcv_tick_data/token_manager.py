import os
import json
import time
import base64
import requests
from datetime import datetime, timezone
from typing import Dict, Optional, Tuple


class TokenManager:
    """
    Manages Dhan access tokens with automatic renewal capability.
    Tokens are renewed automatically using Dhan's /v2/RenewToken API.
    """

    def __init__(self, token_file_path="dhan_token.json"):
        self.token_file_path = token_file_path
        self.last_loaded_token = None  # The token string that was last successfully loaded/notified


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

    def save_token(self, token_data: Dict) -> bool:
        """Save token data to file"""
        try:
            with open(self.token_file_path, "w") as f:
                json.dump(token_data, f, indent=4)
            return True
        except Exception as e:
            print(f"[TokenManager] Error saving token: {e}")
            return False

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

    def is_token_expired(self, token_data: Dict, buffer_seconds: int = 21600) -> bool:
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

    def renew_token(self, current_token: str, client_id: str) -> Optional[Dict]:
        """
        Renew the access token using Dhan's /v2/RenewToken API.
        
        Returns:
            Updated token data dict or None on failure
        """
        print("[TokenManager] 🔄 Attempting token renewal...")
        
        renew_url = "https://api.dhan.co/v2/RenewToken"
        headers = {
            "access-token": current_token,
            "dhanClientId": client_id
        }
        
        try:
            response = requests.get(renew_url, headers=headers, timeout=10)
            response.raise_for_status()
            
            renew_data = response.json()
            new_token = renew_data.get("access_token")
            
            if not new_token:
                print(f"[TokenManager] ❌ Renewal failed: No token in response")
                return None
            
            # Extract new expiry
            new_expiry = self._extract_expiry_from_jwt(new_token)
            
            # Create updated token data
            updated_token_data = {
                "access_token": new_token,
                "client_id": client_id,
                "expires_at": new_expiry,
                "renewed_at": int(time.time())
            }
            
            # Save to file
            if self.save_token(updated_token_data):
                print(f"[TokenManager] ✅ Token renewed successfully! New expiry: {new_expiry}")
                return updated_token_data
            else:
                print("[TokenManager] ❌ Failed to save renewed token")
                return None
                
        except requests.exceptions.RequestException as e:
            print(f"[TokenManager] ❌ Renewal API request failed: {e}")
            return None
        except Exception as e:
            print(f"[TokenManager] ❌ Renewal error: {e}")
            return None

    def get_valid_token(self) -> Tuple[Optional[str], Optional[str]]:
        """
        Get a valid access token, renewing automatically if expired/expiring.
        
        Returns:
            Tuple of (access_token, client_id) or (None, None) on failure
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

        # Check if token needs renewal
        if self.is_token_expired(token_data):
            print("[TokenManager] Token expired/expiring. Attempting renewal...")
            renewed_data = self.renew_token(access_token, client_id)
            
            if renewed_data:
                self.last_loaded_token = renewed_data["access_token"]
                return renewed_data["access_token"], renewed_data["client_id"]
            else:
                print("[TokenManager] ❌ Token renewal failed. Please regenerate token manually.")
                return None, None

        self.last_loaded_token = access_token
        return access_token, client_id

    def has_token_changed(self) -> bool:
        """
        Checks if the token in the file is different from self.last_loaded_token.
        This is useful for long-running processes to detect external updates or 
        internal renewals that they haven't picked up yet.
        """
        token_data = self.load_token()
        if not token_data:
            return False
        
        on_disk_token = token_data.get("access_token")
        if not on_disk_token:
            return False
            
        changed = on_disk_token != self.last_loaded_token
        if changed:
            print(f"[TokenManager] Detection: Token on disk has changed!")
            
        return changed



if __name__ == "__main__":
    tm = TokenManager()
    token, cid = tm.get_valid_token()

    if token:
        print(f"✅ Token valid for client {cid}")
    else:
        print("❌ Token invalid or expired")

